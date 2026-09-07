"""Build wheels and run the bounded SPEC-023 tracer without source imports."""

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
REPOSITORIES = ("strategy-workspace", "quant-runtime", "apex-research", "strategy-reporting")
TESTS = (
    ("apex-research", "tests/test_factor_research_benchmark.py"),
    ("quant-runtime", "tests/test_benchmark_exec.py"),
)


class TracerFailure(RuntimeError):
    pass


def _environment() -> dict[str, str]:
    value = {
        key: item
        for key, item in os.environ.items()
        if key.upper() not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
    }
    value["PYTHONDONTWRITEBYTECODE"] = "1"
    return value


def _run(
    command: list[str], *, cwd: Path, environment: dict[str, str], timeout: int = TIMEOUT_SECONDS
) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
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
import sys
import apex_research
import quant_runtime
import strategy_reporting
import strategy_workspace
from apex_research import BenchmarkScoringPolicy, FrozenBenchmarkSuite
from apex_research.adapters import QuantRuntimeAdapter
from quant_runtime.cli import runtime_capabilities
adapter = QuantRuntimeAdapter(command=(sys.executable, '-m', 'quant_runtime.cli'))
benchmark_transport = adapter.execute_benchmark(
  source=b'def evaluate(rows):\\n    return []\\n',
  fixture=b'{"rows":[]}',
  entrypoint='factor.py:evaluate',
  sandbox_profile={'max_source_bytes': 4096, 'max_input_bytes': 4096},
  transport_limits={'source_bytes': 4096, 'fixture_bytes': 4096, 'result_bytes': 4096},
  execution_mode='production_attested_oci',
  timeout_seconds=30,
)
print(json.dumps({
  'versions': [apex_research.__version__, quant_runtime.__version__],
  'exports': [BenchmarkScoringPolicy.__name__, FrozenBenchmarkSuite.__name__],
  'runtime_capability': runtime_capabilities(),
  'benchmark_transport': {
    'status': benchmark_transport['status'],
    'execution_id': benchmark_transport['execution_id'],
  },
  'module_roots': [
    apex_research.__file__, quant_runtime.__file__, strategy_reporting.__file__,
    strategy_workspace.__file__
  ],
}, sort_keys=True))
"""
    output = _run([str(python), "-I", "-c", script], cwd=cwd, environment=environment)
    value = json.loads(output)
    if not isinstance(value, dict):
        raise TracerFailure("installed identity smoke did not return an object")
    roots = value.get("module_roots")
    if not isinstance(roots, list) or any("site-packages" not in str(item) for item in roots):
        raise TracerFailure("installed identity smoke imported a source checkout")
    return value


def run(repositories: dict[str, Path]) -> dict[str, Any]:
    environment = _environment()
    with tempfile.TemporaryDirectory(prefix="spec023-installed-") as temporary:
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
        nodes: list[dict[str, str]] = []
        for replay in (1, 2):
            for repository_name, relative_test in TESTS:
                test = repositories[repository_name] / relative_test
                _run(
                    [str(python), "-I", "-m", "pytest", "-q", str(test)],
                    cwd=root,
                    environment=environment,
                )
                nodes.append({"replay": str(replay), "test": relative_test, "status": "passed"})
        identities = [
            _identity_smoke(python, root, environment),
            _identity_smoke(python, root, environment),
        ]
        if identities[0] != identities[1]:
            raise TracerFailure("installed benchmark identity smoke drifted across replay")
        return {
            "ok": True,
            "schema": "quant-research.spec-023-installed-tracer.v1",
            "pythonpath": "cleared",
            "replays": 2,
            "nodes": nodes,
            "identity_sha256": hashlib.sha256(
                json.dumps(identities[0], sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "wheels": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(wheels)
            },
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in REPOSITORIES:
        parser.add_argument(f"--{name}", type=Path, required=True)
    arguments = parser.parse_args(argv)
    repositories = {name: getattr(arguments, name.replace("-", "_")).resolve() for name in REPOSITORIES}
    try:
        result = run(repositories)
    except (OSError, TracerFailure, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
