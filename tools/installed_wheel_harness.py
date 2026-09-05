"""Shared process-safe harness for installed-wheel acceptance tracers."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import signal
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType


class InstalledWheelFailure(RuntimeError):
    """An isolated build, install, or smoke phase failed closed."""


def run_command(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: int,
) -> str:
    creationflags = (
        subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000004 if os.name == "nt" else 0
    )
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
        start_new_session=os.name != "nt",
    )
    job_handle: int | None = None
    try:
        job_handle = _assign_windows_kill_job(process)
        _resume_windows_process(process)
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process, job_handle=job_handle)
        job_handle = None
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
            stdout, stderr = "", "process pipes remained open after tree termination"
        raise InstalledWheelFailure(
            f"command timed out after {timeout_seconds}s: {' '.join(command)}\n"
            f"{stdout}{stderr}"
        ) from exc
    except BaseException:
        _terminate_process_tree(process, job_handle=job_handle)
        job_handle = None
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
        raise
    finally:
        if job_handle is not None:
            _close_windows_handle(job_handle)
    if process.returncode:
        raise InstalledWheelFailure(
            f"command failed ({process.returncode}): {' '.join(command)}\n{stdout}{stderr}"
        )
    return stdout


def _assign_windows_kill_job(process: subprocess.Popen[str]) -> int | None:
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_ulonglong)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        process.kill()
        raise InstalledWheelFailure("failed to create Windows process Job Object")
    limits = ExtendedLimitInformation()
    limits.BasicLimitInformation.LimitFlags = 0x00002000
    configured = kernel32.SetInformationJobObject(
        job,
        9,
        ctypes.byref(limits),
        ctypes.sizeof(limits),
    )
    assigned = kernel32.AssignProcessToJobObject(
        job,
        wintypes.HANDLE(int(process._handle)),  # type: ignore[attr-defined]
    )
    if not configured or not assigned:
        kernel32.CloseHandle(job)
        process.kill()
        raise InstalledWheelFailure(
            "failed to own subprocess tree with a Windows Job Object"
        )
    return int(job)


def _resume_windows_process(process: subprocess.Popen[str]) -> None:
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    ntdll.NtResumeProcess.argtypes = (wintypes.HANDLE,)
    ntdll.NtResumeProcess.restype = ctypes.c_long
    status = ntdll.NtResumeProcess(
        wintypes.HANDLE(int(process._handle)),  # type: ignore[attr-defined]
    )
    if status != 0:
        process.kill()
        raise InstalledWheelFailure("failed to resume Job-owned Windows subprocess")


def _close_windows_handle(handle: int | None) -> None:
    if os.name == "nt" and handle is not None:
        import ctypes
        from ctypes import wintypes

        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(
            wintypes.HANDLE(handle)
        )


def _terminate_process_tree(
    process: subprocess.Popen[str], *, job_handle: int | None
) -> None:
    if os.name == "nt":
        if job_handle is not None:
            _close_windows_handle(job_handle)
            return
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def build_wheels(
    repository_root: Path,
    repositories: Iterable[str],
    dist: Path,
    environment: dict[str, str],
) -> tuple[Path, ...]:
    wheels: list[Path] = []
    for repository in repositories:
        before = set(dist.glob("*.whl"))
        run_command(
            ["uv", "build", "--wheel", "--out-dir", str(dist)],
            cwd=repository_root / repository,
            environment=environment,
            timeout_seconds=300,
        )
        built = set(dist.glob("*.whl")) - before
        if len(built) != 1:
            raise InstalledWheelFailure(
                f"{repository} did not produce exactly one wheel"
            )
        wheels.extend(built)
    return tuple(wheels)


def create_installed_environment(
    isolated: Path,
    wheels: Iterable[Path],
    environment: dict[str, str],
    *,
    install_pytest: bool,
) -> Path:
    virtual_environment = isolated / "venv"
    run_command(
        ["uv", "venv", "--python", "3.12", str(virtual_environment)],
        cwd=isolated,
        environment=environment,
        timeout_seconds=120,
    )
    python = (
        virtual_environment / "Scripts" / "python.exe"
        if os.name == "nt"
        else virtual_environment / "bin" / "python"
    )
    requirements = [str(path) for path in wheels]
    if install_pytest:
        requirements.append("pytest>=8.3,<9")
    run_command(
        ["uv", "pip", "install", "--python", str(python), *requirements],
        cwd=isolated,
        environment=environment,
        timeout_seconds=600,
    )
    version = run_command(
        [
            str(python),
            "-c",
            "import sys; print('.'.join(map(str, sys.version_info[:2])))",
        ],
        cwd=isolated,
        environment=environment,
        timeout_seconds=30,
    ).strip()
    if version != "3.12":
        raise InstalledWheelFailure(
            f"isolated interpreter is not Python 3.12: {version}"
        )
    return python


def run_installed_pytest(
    python: Path,
    targets: Iterable[Path],
    package_names: Iterable[str],
    source_roots: Iterable[Path],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: int,
    pytest_args: Iterable[str] = (),
) -> str:
    payload = json.dumps(
        {
            "targets": [str(path.resolve()) for path in targets],
            "packages": sorted(package_names),
            "source_roots": [str(path.resolve()) for path in source_roots],
            "pytest_args": list(pytest_args),
        },
        sort_keys=True,
    )
    launcher = f"""
import json
from pathlib import Path
import sys
import pytest

payload = json.loads({payload!r})
prefix = Path(sys.prefix).resolve()
source_roots = tuple(Path(value).resolve() for value in payload["source_roots"])
def path_exposes_source(source, candidate):
    return candidate == source or candidate.is_relative_to(source) or source.is_relative_to(candidate)
def assert_no_source_visibility():
    for entry in sys.path:
        if not entry:
            continue
        resolved = Path(entry).resolve()
        if any(path_exposes_source(source, resolved) for source in source_roots):
            raise RuntimeError(f"source root is import-visible: {{resolved}}")
assert_no_source_visibility()
exit_code = pytest.main(["-q", "-p", "no:cacheprovider", *payload["pytest_args"], *payload["targets"]])
assert_no_source_visibility()
loaded = {{}}
for name, module in sorted(sys.modules.items()):
    if not any(name == package or name.startswith(package + ".") for package in payload["packages"]):
        continue
    location = getattr(module, "__file__", None)
    if location is None:
        continue
    resolved = Path(location).resolve()
    if not resolved.is_relative_to(prefix):
        raise RuntimeError(f"loaded module escaped installed environment: {{name}}={{resolved}}")
    loaded[name] = str(resolved)
print(json.dumps({{"exit_code": exit_code, "loaded_modules": loaded}}, sort_keys=True))
raise SystemExit(exit_code)
"""
    isolated_environment = dict(environment)
    isolated_environment.pop("PYTHONPATH", None)
    isolated_environment["PYTHONSAFEPATH"] = "1"
    return run_command(
        [str(python), "-I", "-c", launcher],
        cwd=cwd,
        environment=isolated_environment,
        timeout_seconds=timeout_seconds,
    )


def installed_distribution_manifest(
    modules: Iterable[ModuleType],
    distributions: Iterable[str],
) -> dict[str, str]:
    environment_root = Path(sys.prefix).resolve()
    for module in modules:
        module_path = Path(str(module.__file__)).resolve()
        if not module_path.is_relative_to(environment_root):
            raise InstalledWheelFailure(
                f"module is not installed under the isolated environment: {module.__name__}"
            )
    return {
        distribution: importlib.metadata.version(distribution)
        for distribution in sorted(distributions)
    }


def verify_unchanged_sources(
    repository_root: Path,
    baselines: dict[str, str],
    environment: dict[str, str],
) -> dict[str, dict[str, str]]:
    verified: dict[str, dict[str, str]] = {}
    for repository, baseline in sorted(baselines.items()):
        cwd = repository_root / repository
        head = run_command(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            environment=environment,
            timeout_seconds=30,
        ).strip()
        baseline_tree = run_command(
            ["git", "rev-parse", f"{baseline}:src"],
            cwd=cwd,
            environment=environment,
            timeout_seconds=30,
        ).strip()
        head_tree = run_command(
            ["git", "rev-parse", "HEAD:src"],
            cwd=cwd,
            environment=environment,
            timeout_seconds=30,
        ).strip()
        if head_tree != baseline_tree:
            raise InstalledWheelFailure(
                f"{repository} production source differs from baseline"
            )
        run_command(
            ["git", "diff", "--quiet", "--", "src"],
            cwd=cwd,
            environment=environment,
            timeout_seconds=30,
        )
        tracked = set(
            run_command(
                ["git", "ls-files", "--", "src"],
                cwd=cwd,
                environment=environment,
                timeout_seconds=30,
            ).splitlines()
        )
        source_files = _source_build_inputs(cwd)
        untracked = [path for path in source_files if path not in tracked]
        if untracked:
            raise InstalledWheelFailure(
                f"{repository} has untracked production source: {', '.join(untracked)}"
            )
        run_command(
            ["git", "diff", "--cached", "--quiet", "--", "src"],
            cwd=cwd,
            environment=environment,
            timeout_seconds=30,
        )
        verified[repository] = {
            "baseline": baseline,
            "head": head,
            "source_tree": head_tree,
            "source_fingerprint": _source_fingerprint(cwd, source_files),
        }
    return verified


def path_exposes_source(source: Path, candidate: Path) -> bool:
    """Return whether a sys.path entry can expose any part of a source tree."""
    source = source.resolve()
    candidate = candidate.resolve()
    return (
        candidate == source
        or candidate.is_relative_to(source)
        or source.is_relative_to(candidate)
    )


def verify_source_topology(repository: Path) -> dict[str, object]:
    """Fail closed on linked build inputs and attest the complete source topology."""
    source_files = _source_build_inputs(repository)
    return {
        "source_files": source_files,
        "source_fingerprint": _source_fingerprint(repository, source_files),
    }


def _source_build_inputs(repository: Path) -> list[str]:
    unresolved_source_root = repository / "src"
    source_root_is_junction = getattr(
        unresolved_source_root, "is_junction", lambda: False
    )()
    if unresolved_source_root.is_symlink() or source_root_is_junction:
        raise InstalledWheelFailure(
            f"production source root is a symbolic link or junction: {unresolved_source_root}"
        )
    source_root = unresolved_source_root.resolve()
    inputs: list[str] = []
    for path in sorted(source_root.rglob("*")):
        is_junction = getattr(path, "is_junction", lambda: False)()
        if path.is_symlink() or is_junction:
            raise InstalledWheelFailure(
                f"production source contains a symbolic link or junction: {path}"
            )
        if (
            not path.is_file()
            or "__pycache__" in path.parts
            or path.suffix in {".pyc", ".pyo"}
        ):
            continue
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(source_root)
        except ValueError as exc:
            raise InstalledWheelFailure(
                f"production source resolves outside its repository: {path}"
            ) from exc
        inputs.append("src/" + relative.as_posix())
    return inputs


def _source_fingerprint(repository: Path, source_files: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for relative in source_files:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((repository / relative).resolve().read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
