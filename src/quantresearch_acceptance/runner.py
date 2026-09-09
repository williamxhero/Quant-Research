"""Execution half of the acceptance-plan interface."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .core import AcceptanceFailure, AcceptancePlan, PlanStep

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
    def install(
        self, plan_identity: str, wheels: tuple[Path, ...]
    ) -> InstalledEnvironment: ...


class PlanRunner:
    """Run L0-L3 while keeping process, build, and install adapters replaceable."""

    def __init__(
        self,
        process: ProcessPort,
        wheel_builder: WheelBuilderPort,
        wheel_installer: WheelInstallerPort,
        *,
        on_event: EventSink | None = None,
    ) -> None:
        self._process = process
        self._wheel_builder = wheel_builder
        self._wheel_installer = wheel_installer
        self._on_event = on_event or (lambda _event: None)

    def run(self, plan: AcceptancePlan) -> RunReceipt:
        self._validate_plan(plan)
        source_environment = _sanitized_environment()
        process_count = 0
        replay_count = 0
        completed: list[str] = []
        installed: InstalledEnvironment | None = None
        installed_steps = tuple(
            step for step in plan.steps if step.environment == "installed-no-source"
        )
        if installed_steps:
            wheels = self._wheel_builder.build(plan.identity, plan.owners)
            if not wheels:
                raise AcceptanceFailure("public-contract plan produced no wheels")
            installed = self._wheel_installer.install(plan.identity, wheels)
            _validate_no_source_environment(installed)

        for step in plan.steps:
            repetitions = step.replay_count
            for replay in range(1, repetitions + 1):
                environment = source_environment
                cwd = Path(".")
                python = "python"
                if step.environment == "installed-no-source":
                    if installed is None:
                        raise AcceptanceFailure("installed step has no environment")
                    environment = _sanitized_environment(installed.environment)
                    cwd = installed.cwd
                    python = str(installed.python).replace("\\", "/")
                junit = _replay_junit(step, replay)
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
                    raise AcceptanceFailure(
                        f"acceptance step exceeded timeout: {step.step_id}"
                    )
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
        if len(plan.identity) != 64 or plan.artifact_root.find(plan.identity) < 0:
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
