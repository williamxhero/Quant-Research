"""Shared process-safe harness for installed-wheel acceptance tracers."""

from __future__ import annotations

import importlib.metadata
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
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
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
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()
        raise InstalledWheelFailure(
            f"command timed out after {timeout_seconds}s: {' '.join(command)}\n"
            f"{stdout}{stderr}"
        ) from exc
    if process.returncode:
        raise InstalledWheelFailure(
            f"command failed ({process.returncode}): {' '.join(command)}\n{stdout}{stderr}"
        )
    return stdout


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        return
    os.killpg(process.pid, signal.SIGKILL)


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
            raise InstalledWheelFailure(f"{repository} did not produce exactly one wheel")
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
        [str(python), "-c", "import sys; print('.'.join(map(str, sys.version_info[:2])))"],
        cwd=isolated,
        environment=environment,
        timeout_seconds=30,
    ).strip()
    if version != "3.12":
        raise InstalledWheelFailure(f"isolated interpreter is not Python 3.12: {version}")
    return python


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
            raise InstalledWheelFailure(f"{repository} production source differs from baseline")
        run_command(
            ["git", "diff", "--quiet", "--", "src"],
            cwd=cwd,
            environment=environment,
            timeout_seconds=30,
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
        }
    return verified
