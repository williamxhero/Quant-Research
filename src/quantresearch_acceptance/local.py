"""Local adapters for the acceptance module's process and wheel seams."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from .cache import ArtifactCache
from .core import AcceptanceFailure, OwnerProof
from .runner import InstalledEnvironment


def git_source_fingerprint(
    repository: Path, revision: str, source_patterns: tuple[str, ...]
) -> str:
    """Hash the canonical Git tree entries selected by an owner's source patterns."""
    command = ["git", "ls-tree", "-r", revision, "--", *source_patterns]
    completed = subprocess.run(
        command,
        cwd=repository,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if completed.returncode or not completed.stdout.strip():
        raise AcceptanceFailure(
            f"cannot fingerprint {repository} at {revision}: {completed.stderr.strip()}"
        )
    entries = sorted(line.strip() for line in completed.stdout.splitlines() if line.strip())
    return "sha256:" + hashlib.sha256("\n".join(entries).encode()).hexdigest()


def build_fixed_base_diff(
    scope: Mapping[str, object],
    repository_paths: Mapping[str, Path],
    *,
    ignored_paths: tuple[Path, ...] = (),
) -> dict[str, object]:
    """Capture committed and working-tree changes against every fixed owner base."""
    raw_owners = scope.get("owners")
    if not isinstance(raw_owners, Mapping):
        raise AcceptanceFailure("scope owners are invalid")
    ignored = {path.resolve() for path in ignored_paths}
    changed: dict[str, str] = {}
    fixed_bases: dict[str, str] = {}
    fingerprints: dict[str, str] = {}
    for owner, raw_config in sorted(raw_owners.items()):
        if not isinstance(owner, str) or not isinstance(raw_config, Mapping):
            raise AcceptanceFailure("scope owner is invalid")
        repository = repository_paths.get(owner)
        fixed = raw_config.get("fixed_base")
        source_fingerprint = raw_config.get("source_fingerprint")
        repository_name = raw_config.get("repository")
        if (
            repository is None
            or not isinstance(fixed, str)
            or not isinstance(source_fingerprint, str)
            or not isinstance(repository_name, str)
        ):
            raise AcceptanceFailure(f"scope owner is incomplete: {owner}")
        fixed_bases[owner] = fixed
        fingerprints[owner] = source_fingerprint
        local_paths: set[str] = set()
        for command in (
            ["git", "diff", "--name-only", f"{fixed}...HEAD"],
            ["git", "diff", "--name-only"],
            ["git", "diff", "--cached", "--name-only"],
            ["git", "ls-files", "--others", "--exclude-standard"],
        ):
            local_paths.update(
                line
                for line in _run(command, cwd=repository, timeout_seconds=30).splitlines()
                if line
            )
        for local in local_paths:
            absolute = (repository / local).resolve()
            if absolute in ignored:
                continue
            workspace_path = (
                local if repository_name == "." else f"{repository_name.rstrip('/')}/{local}"
            ).replace("\\", "/")
            content = absolute.read_bytes() if absolute.is_file() else b"deleted\0" + local.encode()
            changed[workspace_path] = "sha256:" + hashlib.sha256(content).hexdigest()
    if not changed:
        raise AcceptanceFailure("fixed-base diff contains no changes")
    return {
        "schema": "quant-research.fixed-base-diff.v1",
        "fixed_bases": fixed_bases,
        "source_fingerprints": fingerprints,
        "changed_sources": [
            {"path": path, "fingerprint": changed[path]} for path in sorted(changed)
        ],
    }


class LocalWheelBuilder:
    """Build the complete selected owner set once for one plan."""

    def __init__(
        self,
        scope: Mapping[str, object],
        repository_paths: Mapping[str, Path],
        work_root: Path,
    ) -> None:
        self._scope = scope
        self._repositories = repository_paths
        self._work_root = work_root
        self._built_for: str | None = None

    def build(self, plan_identity: str, owners: tuple[str, ...]) -> tuple[Path, ...]:
        if self._built_for is not None:
            raise AcceptanceFailure("wheel build phase was invoked more than once")
        self._built_for = plan_identity
        wheelhouse = self._work_root / "wheelhouse"
        wheelhouse.mkdir(parents=True, exist_ok=True)
        existing = tuple(wheelhouse.glob("*.whl"))
        if existing:
            if len(existing) != len(owners):
                raise AcceptanceFailure("resumed wheelhouse is incomplete or ambiguous")
            return tuple(sorted((path.resolve() for path in existing), key=str))
        wheels: list[Path] = []
        raw_owners = self._scope.get("owners")
        if not isinstance(raw_owners, Mapping):
            raise AcceptanceFailure("scope owners are invalid")
        for owner in owners:
            config = raw_owners.get(owner)
            repository = self._repositories.get(owner)
            if not isinstance(config, Mapping) or repository is None:
                raise AcceptanceFailure(f"missing local build configuration: {owner}")
            argv = config.get("build_argv")
            if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
                raise AcceptanceFailure(f"invalid local build argv: {owner}")
            command = [item.replace("{wheel_dir}", str(wheelhouse)) for item in argv]
            before = set(wheelhouse.glob("*.whl"))
            _run(command, cwd=repository, timeout_seconds=300)
            created = set(wheelhouse.glob("*.whl")) - before
            if len(created) != 1:
                raise AcceptanceFailure(f"owner did not build exactly one wheel: {owner}")
            wheels.extend(created)
        return tuple(sorted((path.resolve() for path in wheels), key=str))


class LocalWheelInstaller:
    """Create one no-source environment and install one selected wheel set."""

    def __init__(self, work_root: Path, source_roots: tuple[Path, ...]) -> None:
        self._work_root = work_root
        self._source_roots = source_roots
        self._installed_for: str | None = None

    def install(self, plan_identity: str, wheels: tuple[Path, ...]) -> InstalledEnvironment:
        if self._installed_for is not None:
            raise AcceptanceFailure("wheel install phase was invoked more than once")
        self._installed_for = plan_identity
        environment_root = self._work_root / "installed"
        run_root = environment_root / "run"
        run_root.mkdir(parents=True, exist_ok=True)
        venv = environment_root / "venv"
        _run(
            ["uv", "venv", "--python", "3.12", str(venv)], cwd=environment_root, timeout_seconds=120
        )
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        _run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "pytest>=8.3,<9",
                *(str(path) for path in wheels),
            ],
            cwd=environment_root,
            timeout_seconds=300,
        )
        return InstalledEnvironment(
            python=python.resolve(),
            cwd=run_root.resolve(),
            environment=_clean_environment(),
            source_roots=tuple(path.resolve() for path in self._source_roots),
        )


class FixedBaseProver:
    """Verify unchanged SHA/fingerprint and import only from a cached fixed-base wheel."""

    def __init__(
        self,
        repository_paths: Mapping[str, Path],
        owner_source_patterns: Mapping[str, tuple[str, ...]],
        cache: ArtifactCache,
        work_root: Path,
    ) -> None:
        self._repositories = repository_paths
        self._patterns = owner_source_patterns
        self._cache = cache
        self._work_root = work_root
        self._venv_python: Path | None = None

    def prove(self, proof: OwnerProof) -> None:
        repository = self._repositories.get(proof.owner)
        patterns = self._patterns.get(proof.owner)
        if repository is None or patterns is None:
            raise AcceptanceFailure(f"unchanged owner is unavailable: {proof.owner}")
        head = _run(["git", "rev-parse", "HEAD"], cwd=repository, timeout_seconds=30).strip()
        if head != proof.fixed_sha:
            raise AcceptanceFailure(f"unchanged owner SHA drifted: {proof.owner}")
        fingerprint = git_source_fingerprint(repository, proof.fixed_sha, patterns)
        if fingerprint != proof.source_fingerprint:
            raise AcceptanceFailure(f"unchanged owner fingerprint drifted: {proof.owner}")
        source_status = _run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all", "--", *patterns],
            cwd=repository,
            timeout_seconds=30,
        )
        if source_status.strip():
            raise AcceptanceFailure(f"unchanged owner working tree drifted: {proof.owner}")
        key = self._cache.key(
            owner=proof.owner,
            fixed_sha=proof.fixed_sha,
            source_fingerprint=proof.source_fingerprint,
            build_argv=proof.build_argv,
        )
        cached = self._cache.lookup(key)
        if cached is None:
            build_root = self._work_root / "fixed-build" / proof.owner
            build_root.mkdir(parents=True, exist_ok=True)
            before = set(build_root.glob("*.whl"))
            command = [item.replace("{wheel_dir}", str(build_root)) for item in proof.build_argv]
            _run(command, cwd=repository, timeout_seconds=300)
            created = set(build_root.glob("*.whl")) - before
            if len(created) != 1:
                raise AcceptanceFailure(f"fixed owner did not build one wheel: {proof.owner}")
            built = next(iter(created))
            cached = self._cache.store(key, built.read_bytes(), filename=built.name)
        python = self._proof_python()
        _run(
            ["uv", "pip", "install", "--python", str(python), str(cached)],
            cwd=self._work_root,
            timeout_seconds=300,
        )
        imports = ";".join(f"importlib.import_module({name!r})" for name in proof.import_names)
        _run(
            [str(python), "-I", "-c", f"import importlib;{imports}"],
            cwd=self._work_root,
            timeout_seconds=60,
            environment=_clean_environment(),
        )

    def _proof_python(self) -> Path:
        if self._venv_python is None:
            venv = self._work_root / "fixed-smoke-venv"
            _run(
                ["uv", "venv", "--python", "3.12", str(venv)],
                cwd=self._work_root,
                timeout_seconds=120,
            )
            self._venv_python = (
                venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            ).resolve()
        return self._venv_python


class JsonlEventSink:
    """Append canonical progress events to one plan-owned JSONL destination."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, event: dict[str, object]) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")


def _run(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    environment: dict[str, str] | None = None,
) -> str:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        text=True,
        encoding="utf-8" if argv[0] == "git" else None,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode:
        raise AcceptanceFailure(
            f"command failed ({completed.returncode}): {argv!r}\n"
            f"{completed.stdout}{completed.stderr}"
        )
    return completed.stdout


def _clean_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in ("PYTHONPATH", "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "VIRTUAL_ENV"):
        environment.pop(name, None)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment
