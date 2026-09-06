"""Shared process-safe harness for installed-wheel acceptance tracers."""

from __future__ import annotations

import hashlib
import importlib.metadata
import inspect
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType

import tomllib

_COMMAND_LOCK = threading.Lock()


class InstalledWheelFailure(RuntimeError):
    """An isolated build, install, or smoke phase failed closed."""

    def __init__(self, message: str, *, returncode: int | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode


def sanitized_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    """Return a deterministic test environment without caller pytest/source injection."""
    environment = dict(os.environ if source is None else source)
    for name in (
        "PYTHONPATH",
        "PYTEST_ADDOPTS",
        "PYTEST_PLUGINS",
        "VIRTUAL_ENV",
    ):
        environment.pop(name, None)
    for name in tuple(environment):
        if name.startswith(("GIT_", "HATCH_", "UV_")) or name == "SOURCE_DATE_EPOCH":
            environment.pop(name)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def run_command(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: int,
) -> str:
    with _COMMAND_LOCK:
        return _run_command(
            command,
            cwd=cwd,
            environment=environment,
            timeout_seconds=timeout_seconds,
        )


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: int,
) -> str:
    subreaper_baseline = _prepare_posix_containment()
    creationflags = (
        subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000004 if os.name == "nt" else 0
    )
    cwd = Path(os.path.abspath(cwd))
    try:
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
    except OSError as exc:
        raise InstalledWheelFailure(
            f"command could not start: {' '.join(command)}: {exc}"
        ) from exc
    job_handle: int | None = None
    process_start_time = (
        None
        if os.name == "nt"
        else _posix_process_map().get(process.pid, (None, None))[1]
    )
    descendant_pids: dict[int, int] = {}
    tracker_stop: threading.Event | None = None
    tracker: threading.Thread | None = None
    try:
        job_handle = _assign_windows_kill_job(process)
        _resume_windows_process(process)
        if os.name != "nt":
            tracker_stop = threading.Event()
            tracker = threading.Thread(
                target=_track_posix_descendants,
                args=(process.pid, descendant_pids, tracker_stop),
                daemon=True,
            )
            tracker.start()
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(
            process,
            job_handle=job_handle,
            descendant_pids=dict(descendant_pids),
            subreaper_baseline=subreaper_baseline,
            process_start_time=process_start_time,
        )
        _stop_descendant_tracker(tracker, tracker_stop)
        tracker = None
        tracker_stop = None
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
        _terminate_process_tree(
            process,
            job_handle=job_handle,
            descendant_pids=dict(descendant_pids),
            subreaper_baseline=subreaper_baseline,
            process_start_time=process_start_time,
        )
        _stop_descendant_tracker(tracker, tracker_stop)
        tracker = None
        tracker_stop = None
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
        elif os.name != "nt":
            _terminate_process_tree(
                process,
                job_handle=None,
                descendant_pids=dict(descendant_pids),
                subreaper_baseline=subreaper_baseline,
                process_start_time=process_start_time,
            )
        _stop_descendant_tracker(tracker, tracker_stop)
    if process.returncode:
        raise InstalledWheelFailure(
            f"command failed ({process.returncode}): {' '.join(command)}\n{stdout}{stderr}",
            returncode=process.returncode,
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
    process: subprocess.Popen[str],
    *,
    job_handle: int | None,
    descendant_pids: dict[int, int] | None = None,
    subreaper_baseline: dict[int, int] | None = None,
    process_start_time: int | None = None,
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
    if (
        process_start_time is not None
        and _posix_process_map().get(process.pid, (None, None))[1] == process_start_time
    ):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for pid, start_time in (descendant_pids or {}).items():
        _kill_posix_identity(pid, start_time)
    _kill_owned_subreaper_children(descendant_pids or {}, subreaper_baseline or {})


def _prepare_posix_containment() -> dict[int, int]:
    if os.name == "nt":
        return {}
    proc = Path("/proc")
    if not proc.is_dir():
        raise InstalledWheelFailure(
            "POSIX installed-wheel commands require /proc process containment"
        )
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    if not hasattr(libc, "prctl") or libc.prctl(36, 1, 0, 0, 0) != 0:
        raise InstalledWheelFailure(
            "POSIX installed-wheel commands require child-subreaper containment"
        )
    return {
        pid: start_time
        for pid, (parent, start_time) in _posix_process_map().items()
        if parent == os.getpid()
    }


def _kill_posix_identity(pid: int, start_time: int) -> None:
    if _posix_process_map().get(pid, (None, None))[1] != start_time:
        return
    pidfd_open = getattr(os, "pidfd_open", None)
    pidfd_send_signal = getattr(signal, "pidfd_send_signal", None)
    if pidfd_open is not None and pidfd_send_signal is not None:
        try:
            descriptor = pidfd_open(pid)
        except ProcessLookupError:
            return
        try:
            if _posix_process_map().get(pid, (None, None))[1] == start_time:
                pidfd_send_signal(descriptor, signal.SIGKILL)
        finally:
            os.close(descriptor)
        return
    if _posix_process_map().get(pid, (None, None))[1] != start_time:
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _kill_owned_subreaper_children(
    owned: dict[int, int], baseline: dict[int, int]
) -> None:
    if os.name == "nt":
        return
    for _ in range(4):
        process_map = _posix_process_map()
        candidates = dict(owned)
        candidates.update(
            {
                pid: start_time
                for pid, (parent, start_time) in process_map.items()
                if parent == os.getpid() and baseline.get(pid) != start_time
            }
        )
        children = {
            pid: start_time
            for pid, (parent, start_time) in process_map.items()
            if pid in candidates and candidates[pid] == start_time
        }
        if not children:
            return
        for pid, start_time in children.items():
            _kill_posix_identity(pid, start_time)
        for pid in children:
            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                pass


def _posix_parent_map() -> dict[int, int]:
    return {pid: parent for pid, (parent, _start) in _posix_process_map().items()}


def _posix_process_map() -> dict[int, tuple[int, int]]:
    process_by_pid: dict[int, tuple[int, int]] = {}
    try:
        process_paths = tuple(Path("/proc").iterdir())
    except OSError:
        return process_by_pid
    for process_path in process_paths:
        if not process_path.name.isdigit():
            continue
        try:
            stat = (process_path / "stat").read_text(encoding="utf-8")
            fields = stat[stat.rindex(")") + 2 :].split()
            process_by_pid[int(process_path.name)] = (int(fields[1]), int(fields[19]))
        except (OSError, ValueError, IndexError):
            continue
    return process_by_pid


def _stop_descendant_tracker(
    tracker: threading.Thread | None, stop: threading.Event | None
) -> None:
    if tracker is None or stop is None:
        return
    stop.set()
    tracker.join(timeout=1)


def _track_posix_descendants(
    root_pid: int, descendants: dict[int, int], stop: threading.Event
) -> None:
    """Remember descendants even if they later detach from the original process group."""
    tracked_parents = {root_pid}
    while not stop.is_set():
        process_map = _posix_process_map()
        changed = True
        while changed:
            changed = False
            for pid, (parent, start_time) in process_map.items():
                if parent in tracked_parents and pid not in tracked_parents:
                    tracked_parents.add(pid)
                    descendants[pid] = start_time
                    changed = True
        time.sleep(0.005)


def build_wheels(
    repository_root: Path,
    repositories: Iterable[str],
    dist: Path,
    environment: dict[str, str],
) -> tuple[Path, ...]:
    wheels: list[Path] = []
    for repository in repositories:
        build_repository = _validated_repository_path(repository_root / repository)
        before = set(dist.glob("*.whl"))
        run_command(
            ["uv", "build", "--wheel", "--out-dir", str(dist)],
            cwd=build_repository,
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
    visibility_guard = inspect.getsource(path_exposes_source)
    launcher = f"""
import json
from pathlib import Path
import sys
import pytest

payload = json.loads({payload!r})
prefix = Path(sys.prefix).resolve()
source_roots = tuple(Path(value).resolve() for value in payload["source_roots"])
{visibility_guard}
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
        cwd = _validated_repository_path(repository_root / repository)
        head = run_command(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            environment=environment,
            timeout_seconds=30,
        ).strip()
        build_roots = _declared_build_roots(cwd)
        run_command(
            ["git", "diff", "--quiet", baseline, "HEAD", "--", *build_roots],
            cwd=cwd,
            environment=environment,
            timeout_seconds=30,
        )
        run_command(
            ["git", "diff", "--quiet", "--", *build_roots],
            cwd=cwd,
            environment=environment,
            timeout_seconds=30,
        )
        tracked = set(
            run_command(
                ["git", "ls-files", "--", *build_roots],
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
            ["git", "diff", "--cached", "--quiet", "--", *build_roots],
            cwd=cwd,
            environment=environment,
            timeout_seconds=30,
        )
        verified[repository] = {
            "baseline": baseline,
            "head": head,
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


def verify_source_topology(
    repository: Path, environment: dict[str, str] | None = None
) -> dict[str, object]:
    """Fail closed on linked build inputs and attest the complete source topology."""
    repository = _validated_repository_path(
        repository,
        require_git=environment is not None,
        environment=environment,
    )
    source_files = _source_build_inputs(repository)
    result: dict[str, object] = {
        "source_files": source_files,
        "source_fingerprint": _source_fingerprint(repository, source_files),
    }
    if environment is not None:
        inside_work_tree = run_command(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repository,
            environment=environment,
            timeout_seconds=30,
        ).strip()
        if inside_work_tree != "true":
            raise InstalledWheelFailure(
                f"wheel source repository is not a Git work tree: {repository}"
            )
        index_lines = run_command(
            ["git", "ls-files", "-v"],
            cwd=repository,
            environment=environment,
            timeout_seconds=30,
        ).splitlines()
        special_index_entries = sorted(
            line[2:] for line in index_lines if len(line) >= 3 and line[0] != "H"
        )
        if special_index_entries:
            raise InstalledWheelFailure(
                "wheel build inputs use unsafe Git index flags: "
                + ", ".join(special_index_entries)
            )
        run_command(
            ["git", "diff", "--quiet"],
            cwd=repository,
            environment=environment,
            timeout_seconds=30,
        )
        run_command(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repository,
            environment=environment,
            timeout_seconds=30,
        )
        tracked = set(
            run_command(
                ["git", "ls-files"],
                cwd=repository,
                environment=environment,
                timeout_seconds=30,
            ).splitlines()
        )
        declared_inputs = set(source_files)
        missing = sorted(path for path in tracked if not (repository / path).is_file())
        if missing:
            raise InstalledWheelFailure(
                "tracked wheel build inputs are absent from the work tree: "
                + ", ".join(missing)
            )
        untracked = sorted(declared_inputs - tracked)
        if untracked:
            raise InstalledWheelFailure(
                "repository has untracked wheel build inputs: " + ", ".join(untracked)
            )
        unexpected = run_command(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=repository,
            environment=environment,
            timeout_seconds=30,
        ).splitlines()
        if unexpected:
            raise InstalledWheelFailure(
                "repository has untracked attestation inputs: "
                + ", ".join(sorted(unexpected))
            )
        source_files = sorted(tracked)
        for relative in source_files:
            path = repository / relative
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise InstalledWheelFailure(
                    f"repository attestation input is a symbolic link or junction: {path}"
                )
        result["source_files"] = source_files
        result["source_fingerprint"] = _source_fingerprint(repository, source_files)
        result["head"] = run_command(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            environment=environment,
            timeout_seconds=30,
        ).strip()
    return result


def _validated_repository_path(
    repository: Path,
    *,
    require_git: bool = False,
    environment: dict[str, str] | None = None,
) -> Path:
    """Resolve only ordinary directories or verified sibling Git worktree links."""
    unresolved = Path(os.path.abspath(repository))
    linked = (
        unresolved.is_symlink() or getattr(unresolved, "is_junction", lambda: False)()
    )
    resolved = unresolved.resolve(strict=True)

    def verify_git_root() -> None:
        top_level = run_command(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=resolved,
            environment=sanitized_environment(environment),
            timeout_seconds=30,
        ).strip()
        if Path(top_level).resolve() != resolved:
            raise InstalledWheelFailure(
                f"repository path is not an exact Git work-tree root: {unresolved}"
            )
        pyproject = resolved / "pyproject.toml"
        if pyproject.is_file():
            document = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            project = document.get("project", {})
            project_name = project.get("name") if isinstance(project, dict) else None
            if isinstance(project_name, str) and project_name.lower().replace(
                "_", "-"
            ) != (resolved.name.lower().replace("_", "-")):
                raise InstalledWheelFailure(
                    f"repository project identity does not match its root: {unresolved}"
                )

    if not linked and require_git:
        verify_git_root()
        return resolved
    if not linked:
        return resolved
    worktree_pool = unresolved.parent.parent.resolve()
    marker = resolved / ".git"
    if (
        worktree_pool.name != ".worktrees"
        or resolved.parent != worktree_pool
        or not marker.is_file()
    ):
        raise InstalledWheelFailure(
            f"repository link is not a verified sibling Git worktree: {unresolved}"
        )
    marker_text = marker.read_text(encoding="utf-8").strip()
    if not marker_text.startswith("gitdir:"):
        raise InstalledWheelFailure(
            f"repository worktree marker is invalid: {unresolved}"
        )
    git_dir = Path(marker_text.split(":", 1)[1].strip()).resolve(strict=True)
    backpointer = git_dir / "gitdir"
    common_pointer = git_dir / "commondir"
    if not backpointer.is_file() or not common_pointer.is_file():
        raise InstalledWheelFailure(
            f"repository worktree metadata is incomplete: {unresolved}"
        )
    linked_marker = Path(backpointer.read_text(encoding="utf-8").strip()).resolve(
        strict=True
    )
    common_dir = (git_dir / common_pointer.read_text(encoding="utf-8").strip()).resolve(
        strict=True
    )
    if linked_marker != marker.resolve(strict=True) or not common_dir.is_dir():
        raise InstalledWheelFailure(
            f"repository worktree metadata does not point back to its link: {unresolved}"
        )
    if require_git:
        verify_git_root()
    return resolved


def _source_build_inputs(repository: Path) -> list[str]:
    repository = repository.resolve()
    inputs: list[str] = []
    for relative_root in _declared_build_roots(repository):
        unresolved_root = repository / relative_root
        if not unresolved_root.exists():
            raise InstalledWheelFailure(
                f"declared wheel build input is missing: {relative_root}"
            )
        if (
            unresolved_root.is_symlink()
            or getattr(unresolved_root, "is_junction", lambda: False)()
        ):
            raise InstalledWheelFailure(
                f"production source root is a symbolic link or junction: {unresolved_root}"
            )
        paths = (
            (unresolved_root,)
            if unresolved_root.is_file()
            else tuple(sorted(unresolved_root.rglob("*")))
        )
        for path in paths:
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
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
                relative = resolved.relative_to(repository)
            except ValueError as exc:
                raise InstalledWheelFailure(
                    f"production source resolves outside its repository: {path}"
                ) from exc
            inputs.append(relative.as_posix())
    return sorted(set(inputs))


def _declared_build_roots(repository: Path) -> list[str]:
    pyproject_path = repository / "pyproject.toml"
    roots = {"pyproject.toml", "src"}
    if not pyproject_path.is_file():
        return ["src"]
    document = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = document.get("project", {})
    if isinstance(project, dict):
        for field in ("readme", "license"):
            value = project.get(field)
            if isinstance(value, str):
                roots.add(value)
            elif isinstance(value, dict) and isinstance(value.get("file"), str):
                roots.add(str(value["file"]))
        license_files = project.get("license-files", ())
        if isinstance(license_files, list):
            for pattern in license_files:
                if isinstance(pattern, str):
                    roots.update(
                        path.relative_to(repository).as_posix()
                        for path in repository.glob(pattern)
                        if path.is_file()
                    )
    build_system = document.get("build-system", {})
    if isinstance(build_system, dict):
        backend_paths = build_system.get("backend-path", ())
        if isinstance(backend_paths, list):
            roots.update(path for path in backend_paths if isinstance(path, str))
    tool = document.get("tool", {})
    hatch = tool.get("hatch", {}) if isinstance(tool, dict) else {}
    build = hatch.get("build", {}) if isinstance(hatch, dict) else {}
    targets = build.get("targets", {}) if isinstance(build, dict) else {}
    wheel = targets.get("wheel", {}) if isinstance(targets, dict) else {}
    if isinstance(build, dict):
        for field in ("include", "only-include"):
            patterns = build.get(field, ())
            if isinstance(patterns, list):
                for pattern in patterns:
                    if isinstance(pattern, str):
                        roots.update(
                            path.relative_to(repository).as_posix()
                            for path in repository.glob(pattern.lstrip("/"))
                            if path.is_file()
                        )
        artifacts = build.get("artifacts", ())
        if isinstance(artifacts, list):
            for pattern in artifacts:
                if isinstance(pattern, str):
                    roots.update(
                        path.relative_to(repository).as_posix()
                        for path in repository.glob(pattern.lstrip("/"))
                        if path.is_file()
                    )
        force_include = build.get("force-include", {})
        if isinstance(force_include, dict):
            roots.update(str(source) for source in force_include)
        hooks = build.get("hooks", {})
        if isinstance(hooks, dict):
            for hook in hooks.values():
                if isinstance(hook, dict) and isinstance(hook.get("path"), str):
                    roots.add(str(hook["path"]))
        if "custom" in hooks and (repository / "hatch_build.py").is_file():
            roots.add("hatch_build.py")
    metadata = hatch.get("metadata", {}) if isinstance(hatch, dict) else {}
    metadata_hooks = metadata.get("hooks", {}) if isinstance(metadata, dict) else {}
    if isinstance(metadata_hooks, dict):
        for hook in metadata_hooks.values():
            if isinstance(hook, dict) and isinstance(hook.get("path"), str):
                roots.add(str(hook["path"]))
    if isinstance(wheel, dict):
        for field in ("include", "only-include"):
            patterns = wheel.get(field, ())
            if isinstance(patterns, list):
                for pattern in patterns:
                    if isinstance(pattern, str):
                        roots.update(
                            path.relative_to(repository).as_posix()
                            for path in repository.glob(pattern.lstrip("/"))
                            if path.is_file()
                        )
        target_hooks = wheel.get("hooks", {})
        if isinstance(target_hooks, dict):
            for hook in target_hooks.values():
                if isinstance(hook, dict) and isinstance(hook.get("path"), str):
                    roots.add(str(hook["path"]))
        wheel_artifacts = wheel.get("artifacts", ())
        if isinstance(wheel_artifacts, list):
            for pattern in wheel_artifacts:
                if isinstance(pattern, str):
                    roots.update(
                        path.relative_to(repository).as_posix()
                        for path in repository.glob(pattern.lstrip("/"))
                        if path.is_file()
                    )
        for package in wheel.get("packages", ()):
            if isinstance(package, str) and not package.startswith("src/"):
                roots.add(package)
        force_include = wheel.get("force-include", {})
        if isinstance(force_include, dict):
            roots.update(str(source) for source in force_include)
    return sorted(roots)


def snapshot_repository(
    repository: Path, destination: Path, source_files: Iterable[str]
) -> None:
    """Copy an attested repository closure into an isolated build snapshot."""
    repository = _validated_repository_path(
        repository,
        require_git=True,
        environment=sanitized_environment(),
    )
    destination.mkdir(parents=True, exist_ok=False)
    for relative in source_files:
        source = repository / relative
        target = destination / relative
        if not source.is_file() or source.is_symlink():
            raise InstalledWheelFailure(
                f"attested snapshot input is unavailable: {source}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        target.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)


def _source_fingerprint(repository: Path, source_files: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for relative in source_files:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((repository / relative).resolve().read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
