"""Run SPEC-026 through the TEST-001 fixed-diff and installed-wheel Adapter."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCOPE = "docs/architecture-admissions/spec-026.acceptance-scope.v2.json"
NODES = (
    "strategy_reporting._campaign_installed_test::test_installed_campaign_cli_and_public_workspace_adapter",
    "strategy_reporting._campaign_installed_test::test_installed_campaign_verify_rebuild_and_portal_are_deterministic",
)
UNCHANGED_SOURCE_BASELINES = {
    "apex-research": "4582fa6407366c56f4b31138dfdebf5da8c1e839",
    "quant-runtime": "9f513c02ce2e1180a2b8fe5c1ea96ff4592b4860",
    "strategy-workspace": "f5e186dc4a88a86e8df39d86daaba2844d08c44b",
}
TIMEOUT_SECONDS = 900


class TracerFailure(RuntimeError):
    pass


def run(repository_root: Path, owner_roots: dict[str, Path]) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    required = {
        "quant-research",
        "apex-research",
        "quant-runtime",
        "strategy-reporting",
        "strategy-workspace",
    }
    if set(owner_roots) != required:
        raise TracerFailure("SPEC-026 tracer requires exactly five owner roots")
    _verify_architecture(repository_root, owner_roots)
    scope = repository_root / SCOPE
    overrides = [
        token
        for owner, path in sorted(owner_roots.items())
        for token in ("--owner-root", f"{owner}={path.resolve()}")
    ]
    environment = _environment()
    with tempfile.TemporaryDirectory(prefix="spec026-test001-") as temporary:
        fixed_diff = Path(temporary) / "fixed-diff.json"
        _command(
            (
                sys.executable,
                "-m",
                "quantresearch_acceptance",
                "diff",
                "--scope",
                str(scope),
                "--repository-root",
                str(repository_root),
                *overrides,
                "--output",
                str(fixed_diff),
            ),
            cwd=repository_root,
            environment=environment,
        )
        output = _command(
            (
                sys.executable,
                "-m",
                "quantresearch_acceptance",
                "execute",
                "--scope",
                str(scope),
                "--diff",
                str(fixed_diff),
                "--phase",
                "spec",
                "--repository-root",
                str(repository_root),
                *overrides,
            ),
            cwd=repository_root,
            environment=environment,
        )
    receipt = json.loads(output.splitlines()[-1])
    if receipt.get("ok") is not True or receipt.get("replay_process_count") != 2:
        raise TracerFailure("TEST-001 did not complete exactly two installed replays")
    return {
        **receipt,
        "schema": "quant-research.spec-026-installed-tracer.v1",
        "nodes": list(NODES),
        "unchanged_sources": UNCHANGED_SOURCE_BASELINES,
    }


def _verify_architecture(repository_root: Path, owner_roots: dict[str, Path]) -> None:
    path = repository_root / "tools/verify_public_seam_architecture.py"
    spec = importlib.util.spec_from_file_location("spec026_public_seam_verifier", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._scan_spec026_campaign_reporting_seams(
        repository_root,
        required=True,
        owner_roots=owner_roots,
    )


def _command(argv: tuple[str, ...], *, cwd: Path, environment: dict[str, str]) -> str:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode:
        raise TracerFailure(
            f"command failed ({completed.returncode}): {argv!r}\n"
            f"stdout={completed.stdout[-4000:]}\nstderr={completed.stderr[-4000:]}"
        )
    return completed.stdout


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "PYTEST_ADDOPTS"):
        environment.pop(name, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--owner-root", action="append", default=[], metavar="OWNER=PATH")
    arguments = parser.parse_args(argv)
    try:
        roots = _parse_roots(arguments.repository_root, arguments.owner_root)
        result = run(arguments.repository_root, roots)
    except (OSError, ValueError, subprocess.SubprocessError, TracerFailure) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


def _parse_roots(repository_root: Path, values: list[str]) -> dict[str, Path]:
    roots = {"quant-research": repository_root.resolve()}
    for value in values:
        if "=" not in value:
            raise TracerFailure(f"invalid owner root: {value}")
        owner, raw_path = value.split("=", 1)
        if not owner or owner in roots or not raw_path:
            raise TracerFailure(f"invalid owner root: {value}")
        roots[owner] = Path(raw_path).resolve()
    return roots


if __name__ == "__main__":
    raise SystemExit(main())
