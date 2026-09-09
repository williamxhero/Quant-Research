"""Execution half of the acceptance-plan interface."""

from __future__ import annotations

import os
import queue
import re
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .core import AcceptanceFailure, AcceptancePlan, OwnerProof, PlanStep

EventSink = Callable[[dict[str, object]], None]


@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int
    duration_seconds: float
    output: str
    current_tests: tuple[str, ...]
    resource_samples: tuple[dict[str, float], ...]


@dataclass(frozen=True, slots=True)
class InstalledEnvironment:
    python: Path
    cwd: Path
    environment: dict[str, str]
    source_roots: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class RunReceipt:
    plan_identity: str
    process_count: int
    replay_process_count: int
    step_ids: tuple[str, ...]


class ProcessPort(Protocol):
    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        environment: dict[str, str],
        timeout_seconds: int,
        on_event: EventSink,
    ) -> ProcessResult: ...


class WheelBuilderPort(Protocol):
    def build(self, plan_identity: str, owners: tuple[str, ...]) -> tuple[Path, ...]: ...


class WheelInstallerPort(Protocol):
    def install(self, plan_identity: str, wheels: tuple[Path, ...]) -> InstalledEnvironment: ...


class UnchangedProverPort(Protocol):
    def prove(self, proof: OwnerProof) -> None: ...
    def finalize(self) -> tuple[Path, ...]: ...


class PlanRunner:
    """Run L0-L3 while keeping process, build, and install adapters replaceable."""

    def __init__(
        self,
        process: ProcessPort,
        wheel_builder: WheelBuilderPort,
        wheel_installer: WheelInstallerPort,
        *,
        unchanged_prover: UnchangedProverPort,
        repository_paths: dict[str, Path] | None = None,
        evidence_base: Path | None = None,
        completed_runs: frozenset[tuple[str, int]] = frozenset(),
        on_event: EventSink | None = None,
    ) -> None:
        self._process = process
        self._wheel_builder = wheel_builder
        self._wheel_installer = wheel_installer
        self._unchanged_prover = unchanged_prover
        self._repository_paths = repository_paths or {}
        self._evidence_base = (evidence_base or Path(".")).resolve()
        self._completed_runs = completed_runs
        self._on_event = on_event or (lambda _event: None)

    def run(self, plan: AcceptancePlan) -> RunReceipt:
        self._validate_plan(plan)
        for proof in plan.owner_proofs:
            self._unchanged_prover.prove(proof)
        fixed_wheels = self._unchanged_prover.finalize()
        source_environment = _sanitized_environment()
        process_count = 0
        replay_count = 0
        completed: list[str] = []
        installed: InstalledEnvironment | None = None
        level_durations: dict[str, float] = {}
        installed_steps = tuple(
            step for step in plan.steps if step.environment == "installed-no-source"
        )
        partial_installed = any(
            (step.step_id, replay) in self._completed_runs
            for step in installed_steps
            for replay in range(1, step.replay_count + 1)
        ) and not all(
            (step.step_id, replay) in self._completed_runs
            for step in installed_steps
            for replay in range(1, step.replay_count + 1)
        )
        installed_complete = bool(installed_steps) and all(
            (step.step_id, replay) in self._completed_runs
            for step in installed_steps
            for replay in range(1, step.replay_count + 1)
        )
        if installed_steps and not installed_complete:
            setup_started = time.monotonic()
            self._on_event(
                {
                    "event": "installed_setup_started",
                    "plan_identity": plan.identity,
                }
            )
            wheel_owners = tuple(sorted({step.owner for step in installed_steps}))
            selected_wheels = self._wheel_builder.build(plan.identity, wheel_owners)
            if not selected_wheels:
                raise AcceptanceFailure("public-contract plan produced no wheels")
            wheels = tuple(sorted((*selected_wheels, *fixed_wheels), key=str))
            installed = self._wheel_installer.install(plan.identity, wheels)
            _validate_no_source_environment(installed)
            setup_duration = time.monotonic() - setup_started
            level_durations["L3"] = setup_duration
            self._on_event(
                {
                    "event": "installed_setup_finished",
                    "plan_identity": plan.identity,
                    "duration_seconds": setup_duration,
                }
            )
            if setup_duration > min(step.budget_seconds for step in installed_steps):
                raise AcceptanceFailure("installed build/install exceeded L3 budget")

        for step in plan.steps:
            repetitions = step.replay_count
            for replay in range(1, repetitions + 1):
                if (step.step_id, replay) in self._completed_runs and not (
                    step.environment == "installed-no-source" and partial_installed
                ):
                    continue
                environment = source_environment
                cwd = self._repository_paths.get(step.owner, Path("."))
                python = "python"
                if step.environment == "installed-no-source":
                    if installed is None:
                        raise AcceptanceFailure("installed step has no environment")
                    environment = _sanitized_environment(installed.environment)
                    cwd = installed.cwd
                    python = str(installed.python).replace("\\", "/")
                junit = _replay_junit(step, replay)
                junit = str((self._evidence_base / junit).resolve()).replace("\\", "/")
                Path(junit).parent.mkdir(parents=True, exist_ok=True)
                argv = tuple(
                    token.replace("{python}", python).replace("{junit}", junit)
                    for token in step.argv
                )
                event = {
                    "event": "step_started",
                    "plan_identity": plan.identity,
                    "step_id": step.step_id,
                    "level": step.level,
                    "replay": replay,
                    "junit": junit,
                }
                self._on_event(event)
                result = self._process.run(
                    argv,
                    cwd=cwd,
                    environment=environment,
                    timeout_seconds=step.timeout_seconds,
                    on_event=self._on_event,
                )
                process_count += 1
                if step.environment == "installed-no-source":
                    replay_count += 1
                if result.returncode != 0:
                    raise AcceptanceFailure(
                        f"acceptance step failed ({result.returncode}): {step.step_id}"
                    )
                if result.duration_seconds > step.timeout_seconds:
                    raise AcceptanceFailure(f"acceptance step exceeded timeout: {step.step_id}")
                level_durations[step.level] = (
                    level_durations.get(step.level, 0.0) + result.duration_seconds
                )
                if level_durations[step.level] > step.budget_seconds:
                    raise AcceptanceFailure(f"acceptance level exceeded budget: {step.level}")
                self._on_event(
                    {
                        "event": "step_finished",
                        "plan_identity": plan.identity,
                        "step_id": step.step_id,
                        "level": step.level,
                        "replay": replay,
                        "duration_seconds": result.duration_seconds,
                    }
                )
            completed.append(step.step_id)
        return RunReceipt(plan.identity, process_count, replay_count, tuple(completed))

    @staticmethod
    def _validate_plan(plan: AcceptancePlan) -> None:
        if len(plan.identity) != 64 or plan.recomputed_identity() != plan.identity:
            raise AcceptanceFailure("acceptance plan identity drifted")
        if any(step.level not in {"L0", "L1", "L2", "L3"} for step in plan.steps):
            raise AcceptanceFailure("public runner only executes L0-L3")
        if any(step.replay_count != (2 if step.level == "L3" else 1) for step in plan.steps):
            raise AcceptanceFailure("acceptance replay count drifted")


def _replay_junit(step: PlanStep, replay: int) -> str:
    if step.replay_count == 1:
        return step.junit
    suffix = f".replay-{replay}.xml"
    return step.junit[:-4] + suffix if step.junit.endswith(".xml") else step.junit + suffix


def _sanitized_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ if source is None else source)
    for name in ("PYTHONPATH", "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "VIRTUAL_ENV"):
        environment.pop(name, None)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _validate_no_source_environment(environment: InstalledEnvironment) -> None:
    cwd = environment.cwd.resolve()
    for root in environment.source_roots:
        source = root.resolve()
        if cwd == source or cwd.is_relative_to(source):
            raise AcceptanceFailure("installed replay cwd is inside a source root")
    if "PYTHONPATH" in environment.environment:
        raise AcceptanceFailure("installed replay environment contains PYTHONPATH")


class SubprocessProcess:
    """Stream process progress and take a bounded number of CPU/I/O samples."""

    def __init__(self, *, sample_interval_seconds: float = 0.25, max_samples: int = 120) -> None:
        if sample_interval_seconds <= 0 or not 1 <= max_samples <= 1000:
            raise AcceptanceFailure("resource sampling bounds are invalid")
        self._interval = sample_interval_seconds
        self._max_samples = max_samples

    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        environment: dict[str, str],
        timeout_seconds: int,
        on_event: EventSink,
    ) -> ProcessResult:
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
                start_new_session=os.name != "nt",
            )
        except OSError as exc:
            raise AcceptanceFailure(f"acceptance process could not start: {exc}") from exc
        lines: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                lines.put(line)
            lines.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        output: list[str] = []
        current_tests: list[str] = []
        samples: list[dict[str, float]] = []
        stream_done = False
        deadline = started + timeout_seconds
        while not (stream_done and process.poll() is not None):
            if time.monotonic() >= deadline:
                _terminate_process_tree(process)
                process.wait(timeout=5)
                raise AcceptanceFailure(f"acceptance process timed out after {timeout_seconds}s")
            try:
                line = lines.get(timeout=self._interval)
            except queue.Empty:
                line = ""
            if line is None:
                stream_done = True
            elif line:
                output.append(line)
                match = re.search(r"([^\s]+\.py::[^\s]+)", line)
                if match:
                    nodeid = match.group(1)
                    current_tests.append(nodeid)
                    on_event({"event": "current_test", "nodeid": nodeid})
            if len(samples) < self._max_samples and process.poll() is None:
                sample = _sample_process(process.pid)
                samples.append(sample)
                on_event({"event": "resource_sample", **sample})
        reader.join(timeout=1)
        if process.stdout is not None:
            process.stdout.close()
        return ProcessResult(
            process.returncode or 0,
            time.monotonic() - started,
            "".join(output),
            tuple(current_tests),
            tuple(samples),
        )


def _sample_process(pid: int) -> dict[str, float]:
    if os.name == "nt":
        return _sample_windows_process(pid)
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
        ticks = float(os.sysconf("SC_CLK_TCK"))
        counters = {
            key: float(value)
            for key, value in (
                line.split(":", 1) for line in Path(f"/proc/{pid}/io").read_text().splitlines()
            )
        }
        return {
            "cpu_seconds": (float(fields[13]) + float(fields[14])) / ticks,
            "read_bytes": counters.get("read_bytes", 0.0),
            "write_bytes": counters.get("write_bytes", 0.0),
        }
    except (OSError, ValueError, IndexError):
        return {"cpu_seconds": 0.0, "read_bytes": 0.0, "write_bytes": 0.0}


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        return
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)


def _sample_windows_process(pid: int) -> dict[str, float]:
    import ctypes
    from ctypes import wintypes

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("read_operations", ctypes.c_ulonglong),
            ("write_operations", ctypes.c_ulonglong),
            ("other_operations", ctypes.c_ulonglong),
            ("read_bytes", ctypes.c_ulonglong),
            ("write_bytes", ctypes.c_ulonglong),
            ("other_bytes", ctypes.c_ulonglong),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return {"cpu_seconds": 0.0, "read_bytes": 0.0, "write_bytes": 0.0}
    try:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        counters = IoCounters()
        times_ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        io_ok = kernel32.GetProcessIoCounters(handle, ctypes.byref(counters))
        cpu = 0.0
        if times_ok:
            kernel_ticks = (kernel.dwHighDateTime << 32) | kernel.dwLowDateTime
            user_ticks = (user.dwHighDateTime << 32) | user.dwLowDateTime
            cpu = (kernel_ticks + user_ticks) / 10_000_000
        return {
            "cpu_seconds": cpu,
            "read_bytes": float(counters.read_bytes if io_ok else 0),
            "write_bytes": float(counters.write_bytes if io_ok else 0),
        }
    finally:
        kernel32.CloseHandle(handle)
