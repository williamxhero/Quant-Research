"""Build five-repository SPEC-015 acceptance and run with installed wheels only."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


PACKAGE_REPOSITORIES = (
    "strategy-workspace",
    "quant-runtime",
    "apex-research",
    "strategy-reporting",
)
INSTALLED_TESTS = (
    (
        "strategy-workspace",
        ("tests/test_lineage_query.py",),
    ),
    (
        "quant-runtime",
        ("tests/test_architecture.py",),
    ),
    (
        "apex-research",
        (
            "tests/test_qualification_policy.py",
            "tests/test_qualification_evaluation.py",
            "tests/test_qualification_validation.py",
            "tests/test_qualification_robustness.py",
            "tests/test_qualification_history.py",
            "tests/test_qualification_cli.py",
        ),
    ),
    (
        "strategy-reporting",
        ("tests/test_workspace_roundtrip.py",),
    ),
)


class TracerFailure(RuntimeError):
    pass


def _run(command: list[str], *, cwd: Path, environment: dict[str, str]) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise TracerFailure(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"{completed.stdout}{completed.stderr}"
        )
    return completed.stdout


def build_and_run(repository_root: Path) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    for repository in PACKAGE_REPOSITORIES:
        if not (repository_root / repository / "pyproject.toml").is_file():
            raise TracerFailure(f"repository is unavailable: {repository}")
    with tempfile.TemporaryDirectory(prefix="spec015-installed-") as temporary:
        isolated = Path(temporary).resolve()
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        dist = isolated / "dist"
        dist.mkdir()
        wheels: list[Path] = []
        for repository in PACKAGE_REPOSITORIES:
            before = set(dist.glob("*.whl"))
            _run(
                ["uv", "build", "--wheel", "--out-dir", str(dist)],
                cwd=repository_root / repository,
                environment=environment,
            )
            built = set(dist.glob("*.whl")) - before
            if len(built) != 1:
                raise TracerFailure(f"{repository} did not produce exactly one wheel")
            wheels.extend(built)
        virtual_environment = isolated / "venv"
        _run(["uv", "venv", str(virtual_environment)], cwd=isolated, environment=environment)
        python = (
            virtual_environment / "Scripts" / "python.exe"
            if os.name == "nt"
            else virtual_environment / "bin" / "python"
        )
        _run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                *(str(wheel) for wheel in wheels),
                "pytest>=8.3,<9",
            ],
            cwd=isolated,
            environment=environment,
        )
        for repository, targets in INSTALLED_TESTS:
            _run(
                [
                    str(python),
                    "-m",
                    "pytest",
                    "-q",
                    *(str(repository_root / repository / target) for target in targets),
                ],
                cwd=isolated,
                environment=environment,
            )
        output = _run(
            [
                str(python),
                str(Path(__file__).resolve()),
                "--repository-root",
                str(repository_root),
                "--smoke-root",
                str(isolated / "workspace"),
            ],
            cwd=isolated,
            environment=environment,
        )
        try:
            result = json.loads(output)
        except json.JSONDecodeError as exc:
            raise TracerFailure(f"installed tracer emitted invalid JSON: {output}") from exc
        if result.get("ok") is not True:
            raise TracerFailure(f"installed tracer failed: {result}")
        result["repositories"] = ["quant-research", *PACKAGE_REPOSITORIES]
        result["installed_tests"] = [
            f"{repository}/{target}"
            for repository, targets in INSTALLED_TESTS
            for target in targets
        ]
        return result


def smoke(repository_root: Path, smoke_root: Path) -> dict[str, Any]:
    import apex_research
    import quant_runtime
    import strategy_reporting
    import strategy_workspace
    from apex_research import (
        QualificationDecision,
        QualificationEvaluation,
        QualificationEvaluationRequest,
        QualificationEvaluator,
        QualificationHistoryReader,
        QualificationPolicy,
        QualificationRetirement,
        QualificationRetirementRequest,
        QualificationService,
    )
    from strategy_workspace import WorkspaceClient

    if "PYTHONPATH" in os.environ:
        raise TracerFailure("installed tracer inherited PYTHONPATH")
    source_root = repository_root.resolve()
    modules = (apex_research, quant_runtime, strategy_reporting, strategy_workspace)
    module_paths = {}
    for module in modules:
        module_path = Path(str(module.__file__)).resolve()
        if module_path.is_relative_to(source_root):
            raise TracerFailure(f"source-tree import is forbidden: {module_path}")
        module_paths[module.__name__] = str(module_path)
    public_types = (
        QualificationPolicy,
        QualificationEvaluationRequest,
        QualificationEvaluation,
        QualificationEvaluator,
        QualificationDecision,
        QualificationRetirementRequest,
        QualificationRetirement,
        QualificationHistoryReader,
        QualificationService,
    )
    if any(value.__module__ != "apex_research.qualification" for value in public_types):
        raise TracerFailure("qualification public exports do not resolve to the installed owner")
    workspace = WorkspaceClient(smoke_root)
    workspace.init()
    if workspace.list_records(limit=1) != []:
        raise TracerFailure("installed Workspace smoke root is not isolated")
    return {
        "ok": True,
        "pythonpath": "cleared",
        "module_paths": module_paths,
        "qualification_exports": [value.__name__ for value in public_types],
        "workspace_publication_count": 0,
        "production_sources_unchanged": [
            "strategy-workspace",
            "quant-runtime",
            "strategy-reporting",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--smoke-root", type=Path)
    arguments = parser.parse_args(argv)
    try:
        result = (
            smoke(arguments.repository_root, arguments.smoke_root)
            if arguments.smoke_root is not None
            else build_and_run(arguments.repository_root)
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
