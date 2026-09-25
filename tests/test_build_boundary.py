from __future__ import annotations

import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.slow
def test_build_artifacts_contain_only_the_public_package_scope(tmp_path: Path) -> None:
    output = subprocess.run(
        ["uv", "build", "--out-dir", str(tmp_path)],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert output.returncode == 0
    entries = sorted(tmp_path.iterdir())
    unexpected = [
        entry.name
        for entry in entries
        if entry.name != ".gitignore"
        and not entry.name.endswith(".tar.gz")
        and entry.suffix != ".whl"
    ]
    assert unexpected == []
    artifacts = [
        entry for entry in entries if entry.name.endswith(".tar.gz") or entry.suffix == ".whl"
    ]
    assert len(artifacts) == 2

    sdist = next(artifact for artifact in artifacts if artifact.name.endswith(".tar.gz"))
    wheel = next(artifact for artifact in artifacts if artifact.suffix == ".whl")
    sdist_names = _archive_names_from_sdist(sdist)
    wheel_names = _archive_names_from_wheel(wheel)

    for names in (sdist_names, wheel_names):
        assert names
        assert all(not _is_local_only_path(name) for name in names), names


def _archive_names_from_sdist(path: Path) -> tuple[str, ...]:
    with tarfile.open(path, mode="r:gz") as archive:
        return tuple(member.name.replace("\\", "/") for member in archive.getmembers())


def _archive_names_from_wheel(path: Path) -> tuple[str, ...]:
    with zipfile.ZipFile(path) as archive:
        return tuple(name.replace("\\", "/") for name in archive.namelist())


def _is_local_only_path(name: str) -> bool:
    parts = set(Path(name).parts)
    return bool(
        parts
        & {
            ".scratch",
            "runtime",
            "WILLSTOCKQuantResearchruntimeworkspace",
            "apex-research",
            "strategy-workspace",
            "quant-runtime",
            "strategy-reporting",
            "tests",
            "tools",
            "artifacts",
            "dist",
        }
    )
