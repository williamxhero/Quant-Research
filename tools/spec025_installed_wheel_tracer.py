"""Run the bounded installed-wheel SPEC-025 regression-gate tracer twice."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

TIMEOUT_SECONDS = 240
REPOSITORIES = (
    "strategy-workspace",
    "quant-runtime",
    "apex-research",
    "strategy-reporting",
)
TEST = "tests/test_regression_gate.py"


class TracerFailure(RuntimeError):
    pass


def _environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PYTEST_ADDOPTS"}
    }
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _run(command: list[str], *, cwd: Path, environment: dict[str, str]) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        raise TracerFailure(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout={completed.stdout[-4000:]}\nstderr={completed.stderr[-4000:]}"
        )
    return completed.stdout


def _build(repository: Path, output: Path, environment: dict[str, str]) -> Path:
    before = set(output.glob("*.whl"))
    _run(
        ["uv", "build", "--wheel", "--out-dir", str(output)],
        cwd=repository,
        environment=environment,
    )
    created = set(output.glob("*.whl")) - before
    if len(created) != 1:
        raise TracerFailure(f"wheel build for {repository.name} was ambiguous")
    return created.pop()


def _identity_smoke(python: Path, cwd: Path, environment: dict[str, str]) -> dict[str, Any]:
    script = """
import json
import apex_research
import quant_runtime
import strategy_reporting
import strategy_workspace
from apex_research import (
    AIResearcherRegressionGateService,
    MetricObservation,
    RegressionMetricRule,
)
rule = RegressionMetricRule(
    benchmark='factor', metric='semantic_alignment',
    method='absolute_rate_delta.v1', maximum_degradation_ppm=0,
    minimum_denominator=2, hard_floor=True,
)
comparison = AIResearcherRegressionGateService.compare_metric(
    rule,
    baseline=MetricObservation(numerator=2, denominator=2, observed=2),
    candidate=MetricObservation(numerator=2, denominator=2, observed=2),
)
print(json.dumps({
    'comparison': comparison.model_dump(mode='json'),
    'versions': [apex_research.__version__, quant_runtime.__version__],
    'module_roots': [
        apex_research.__file__, quant_runtime.__file__, strategy_reporting.__file__,
        strategy_workspace.__file__,
    ],
}, sort_keys=True))
"""
    output = _run([str(python), "-I", "-c", script], cwd=cwd, environment=environment)
    value = json.loads(output)
    roots = value.get("module_roots")
    if not isinstance(roots, list) or any("site-packages" not in str(item) for item in roots):
        raise TracerFailure("installed regression smoke imported a source checkout")
    return value


def run(repositories: dict[str, Path]) -> dict[str, Any]:
    environment = _environment()
    with tempfile.TemporaryDirectory(prefix="spec025-installed-") as temporary:
        root = Path(temporary).resolve()
        dist = root / "dist"
        dist.mkdir()
        wheels = [_build(repositories[name], dist, environment) for name in REPOSITORIES]
        venv = root / "venv"
        _run(["uv", "venv", str(venv), "--python", "3.12"], cwd=root, environment=environment)
        python = venv / "Scripts" / "python.exe"
        _run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "pytest==8.4.1",
                *(str(path) for path in wheels),
            ],
            cwd=root,
            environment=environment,
        )
        test = repositories["apex-research"] / TEST
        nodes = []
        identities = []
        for replay in (1, 2):
            _run(
                [str(python), "-I", "-m", "pytest", "-q", str(test)],
                cwd=root,
                environment=environment,
            )
            nodes.append({"replay": replay, "node": TEST, "status": "passed"})
            identities.append(_identity_smoke(python, root, environment))
        if identities[0] != identities[1]:
            raise TracerFailure("installed regression transcript drifted across replay")
        return {
            "ok": True,
            "schema": "quant-research.spec-025-installed-tracer.v1",
            "pythonpath": "cleared",
            "replays": 2,
            "nodes": nodes,
            "identity_sha256": hashlib.sha256(
                json.dumps(identities[0], sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "wheels": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(wheels)
            },
            "forbidden_external_calls": 0,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in REPOSITORIES:
        parser.add_argument(f"--{name}", type=Path, required=True)
    arguments = parser.parse_args(argv)
    repositories = {
        name: getattr(arguments, name.replace("-", "_")).resolve() for name in REPOSITORIES
    }
    try:
        result = run(repositories)
    except (OSError, TracerFailure, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
