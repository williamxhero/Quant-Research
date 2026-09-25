from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tomllib
import venv
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = "src/quantresearch_acceptance/"
# Both root-level and in-package pollution must be excluded, including ordinary
# Python/JSON names which cannot be recognized by a directory-name blacklist.
_POLLUTION = (
    "generated.py",
    "generated.json",
    "generated/__init__.py",
    "generated/strategy.py",
    "generated/result.json",
    "_local_test.py",
    ".scratch/quant-runtime-linux-venv/bin/python",
    "runtime/ledger.json",
    "runtime/strategy.py",
    "Workspace/private/state.json",
    "WILLSTOCKQuantResearchruntimeworkspace/private.json",
    "strategy-workspace/private/ledger.json",
    "apex-research/local.py",
    "quant-runtime/local.py",
    "strategy-reporting/report.json",
    "tests/test_private.py",
    "tools/debug.py",
    "artifacts/result.json",
    "dist/previous.whl",
    "docs/private.md",
)


@dataclass(frozen=True)
class ReleaseBuild:
    checkout: Path
    package_files: frozenset[str]
    distribution: str
    artifacts: dict[str, Path]


def _run(argv: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=180, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.fixture(scope="module", params=("clean", "polluted"))
def release_build(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> ReleaseBuild:
    root = tmp_path_factory.mktemp(f"release-{request.param}")
    checkout = root / "checkout"
    # Copy only Git-tracked files, but use current working-tree contents so this
    # regression exercises uncommitted fixes too. Never traverse local workspaces.
    tracked = _run(["git", "ls-files", "-z"], cwd=_REPO_ROOT).split("\0")[:-1]
    for name in tracked:
        target = checkout / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_REPO_ROOT / name, target)
    package_files = frozenset(name for name in tracked if name.startswith(_PACKAGE))
    assert package_files
    if request.param == "polluted":
        for base in (checkout, checkout / _PACKAGE):
            for name in _POLLUTION:
                target = base / name
                assert not target.exists(), target
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("build-boundary-pollution\n", encoding="utf-8")

    output = root / "from-sdist"
    # uv build builds the wheel from the sdist. Also build a wheel directly from
    # the polluted tree so a narrow sdist cannot hide an unsafe wheel selector.
    _run(["uv", "build", "--out-dir", str(output)], cwd=checkout)
    direct = root / "direct-wheel"
    _run(["uv", "build", "--wheel", "--out-dir", str(direct)], cwd=checkout)
    (sdist,) = output.glob("*.tar.gz")
    (wheel,) = output.glob("*.whl")
    (direct_wheel,) = direct.glob("*.whl")
    assert {p.name for p in output.iterdir()} <= {sdist.name, wheel.name, ".gitignore"}
    assert {p.name for p in direct.iterdir()} <= {direct_wheel.name, ".gitignore"}
    project = tomllib.loads((checkout / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    distribution = f"{project['name'].replace('-', '_')}-{project['version']}"
    return ReleaseBuild(
        checkout,
        package_files,
        distribution,
        {"sdist": sdist, "sdist-wheel": wheel, "direct-wheel": direct_wheel},
    )


@pytest.mark.slow
@pytest.mark.parametrize("artifact", ("sdist", "sdist-wheel", "direct-wheel"))
def test_build_artifacts_contain_only_the_public_package_scope(
    release_build: ReleaseBuild, artifact: str
) -> None:
    """Build subprocesses exceed the ordinary two-second test budget."""
    path = release_build.artifacts[artifact]
    if artifact == "sdist":
        with tarfile.open(path, mode="r:gz") as archive:
            members = [member for member in archive.getmembers() if not member.isdir()]
            assert all(member.isfile() for member in members)
            names = [
                PurePosixPath(member.name).relative_to(release_build.distribution).as_posix()
                for member in members
            ]
        # Packaging decision: README is the release documentation; docs/evidence
        # and docs/research remain checkout-only historical research, not package
        # resources. Keep every tracked package file, including acceptance nodes.
        expected = set(release_build.package_files) | {"README.md", "pyproject.toml", "PKG-INFO"}
        # Hatch may retain the checkout's VCS exclusion metadata in an sdist.
        assert set(names) - {".gitignore"} == expected
    else:
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
        metadata = {"METADATA", "WHEEL", "entry_points.txt", "RECORD"}
        expected = {name.removeprefix("src/") for name in release_build.package_files} | {
            f"{release_build.distribution}.dist-info/{name}" for name in metadata
        }
        assert set(names) == expected
    assert len(names) == len(set(names)), "Duplicate archive members"


@pytest.mark.slow
@pytest.mark.parametrize("artifact", ("sdist-wheel", "direct-wheel"))
def test_wheel_imports_from_temporary_site_packages_without_source_precedence(
    release_build: ReleaseBuild, artifact: str, tmp_path: Path
) -> None:
    """Build, venv creation, install and import exceed the ordinary test budget."""
    environment = tmp_path / "environment"
    venv.EnvBuilder(with_pip=False).create(environment)
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    _run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--no-index",
            "--no-deps",
            str(release_build.artifacts[artifact]),
        ],
        cwd=tmp_path,
    )
    # A hostile inherited PYTHONPATH must not make this an accidental source test.
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        str(root / "src") for root in (_REPO_ROOT, release_build.checkout)
    )
    provenance = json.loads(
        _run(
            [
                str(python),
                "-I",
                "-c",
                "import json, sys, sysconfig; "
                "import quantresearch_acceptance as package; "
                "from quantresearch_acceptance import _installed_test; "
                "_installed_test.test_installed_wheel_has_no_source_checkout_precedence(); "
                "_installed_test.test_installed_selector_replays_the_frozen_public_contract(); "
                "_installed_test.test_installed_marker_and_release_train_contracts(); "
                "print(json.dumps({'package': package.__file__, 'prefix': sys.prefix, "
                "'sites': [sysconfig.get_path('purelib'), sysconfig.get_path('platlib')], "
                "'sys_path': sys.path}))",
            ],
            cwd=tmp_path,
            env=env,
        )
    )
    package = Path(provenance["package"]).resolve()
    assert Path(provenance["prefix"]).resolve() == environment.resolve()
    sites = [Path(site).resolve() for site in provenance["sites"]]
    assert all(site.is_relative_to(environment.resolve()) for site in sites)
    assert any(package == site / "quantresearch_acceptance" / "__init__.py" for site in sites)
    for checkout in (_REPO_ROOT, release_build.checkout):
        assert not package.is_relative_to(checkout.resolve())
        assert all(
            not Path(entry).resolve().is_relative_to(checkout.resolve())
            for entry in provenance["sys_path"]
        )
    _run([str(python), "-I", "-m", "quantresearch_acceptance", "--help"], cwd=tmp_path, env=env)
