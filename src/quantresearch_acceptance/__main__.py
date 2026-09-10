"""Command-line interface for deterministic acceptance planning."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from .cache import ArtifactCache
from .core import AcceptanceFailure, AcceptanceSelector
from .local import (
    FixedBaseProver,
    JsonlEventSink,
    LocalWheelBuilder,
    LocalWheelInstaller,
    build_fixed_base_diff,
)
from .migration import migrate_legacy_scope
from .observability import audit_performance
from .runner import PlanRunner, SubprocessProcess


def _read_json(path: Path) -> object:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise AcceptanceFailure(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceFailure(f"cannot read JSON {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quantresearch-acceptance")
    commands = parser.add_subparsers(dest="command", required=True)
    select = commands.add_parser("select")
    select.add_argument("--scope", type=Path, required=True)
    select.add_argument("--diff", type=Path, required=True)
    select.add_argument("--phase", choices=("spec", "release"), required=True)
    audit = commands.add_parser("audit")
    audit.add_argument("--history", type=Path, required=True)
    migrate = commands.add_parser("migrate")
    migrate.add_argument("--scope", type=Path, required=True)
    execute = commands.add_parser("execute")
    execute.add_argument("--scope", type=Path, required=True)
    execute.add_argument("--diff", type=Path, required=True)
    execute.add_argument("--phase", choices=("spec",), default="spec")
    execute.add_argument("--repository-root", type=Path, required=True)
    execute.add_argument(
        "--owner-root",
        action="append",
        default=[],
        metavar="OWNER=PATH",
        help="Override an owner repository location without changing the frozen scope.",
    )
    diff_command = commands.add_parser("diff")
    diff_command.add_argument("--scope", type=Path, required=True)
    diff_command.add_argument("--repository-root", type=Path, required=True)
    diff_command.add_argument("--owner-root", action="append", default=[], metavar="OWNER=PATH")
    diff_command.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "select":
            scope = _read_json(arguments.scope)
            diff = _read_json(arguments.diff)
            if not isinstance(scope, dict) or not isinstance(diff, dict):
                raise AcceptanceFailure("scope and diff must be JSON objects")
            result = AcceptanceSelector().select(scope, diff, phase=arguments.phase).as_dict()
        elif arguments.command == "audit":
            history = _read_json(arguments.history)
            if not isinstance(history, list):
                raise AcceptanceFailure("history must be a JSON list")
            audit_performance(history)
            result = {"ok": True, "records": len(history)}
        elif arguments.command == "migrate":
            scope = _read_json(arguments.scope)
            if not isinstance(scope, dict):
                raise AcceptanceFailure("legacy scope must be a JSON object")
            result = migrate_legacy_scope(scope).as_dict()
        elif arguments.command == "diff":
            scope = _read_json(arguments.scope)
            if not isinstance(scope, dict):
                raise AcceptanceFailure("scope must be a JSON object")
            repository_root = arguments.repository_root.resolve()
            repository_paths, _source_patterns = _owner_paths(
                scope, repository_root, arguments.owner_root
            )
            result = build_fixed_base_diff(
                scope,
                repository_paths,
                ignored_paths=(arguments.scope,),
            )
            if arguments.output is not None:
                arguments.output.parent.mkdir(parents=True, exist_ok=True)
                arguments.output.write_text(
                    json.dumps(result, sort_keys=True, separators=(",", ":")),
                    encoding="utf-8",
                )
        else:
            scope = _read_json(arguments.scope)
            diff = _read_json(arguments.diff)
            if not isinstance(scope, dict) or not isinstance(diff, dict):
                raise AcceptanceFailure("scope and diff must be JSON objects")
            plan = AcceptanceSelector().select(scope, diff, phase=arguments.phase)
            repository_root = arguments.repository_root.resolve()
            repository_paths, source_patterns = _owner_paths(
                scope, repository_root, arguments.owner_root
            )
            artifact_root = repository_root / plan.artifact_root
            artifact_root.mkdir(parents=True, exist_ok=True)
            plan_path = repository_root / plan.plan_destination
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(
                json.dumps(plan.as_dict(), sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            cache = ArtifactCache(repository_root / ".runtime/acceptance-cache")
            isolated_root = Path(tempfile.mkdtemp(prefix="quantresearch-acceptance-"))
            completed_runs = _completed_runs(repository_root / plan.event_log, plan.identity)
            try:
                receipt = PlanRunner(
                    SubprocessProcess(),
                    LocalWheelBuilder(scope, repository_paths, artifact_root),
                    LocalWheelInstaller(isolated_root, tuple(repository_paths.values())),
                    unchanged_prover=FixedBaseProver(
                        repository_paths,
                        source_patterns,
                        cache,
                        artifact_root,
                    ),
                    repository_paths=repository_paths,
                    evidence_base=repository_root,
                    completed_runs=completed_runs,
                    on_event=JsonlEventSink(repository_root / plan.event_log),
                ).run(plan)
            finally:
                shutil.rmtree(isolated_root, ignore_errors=True)
            result = {
                "ok": True,
                "plan_identity": receipt.plan_identity,
                "process_count": receipt.process_count,
                "replay_process_count": receipt.replay_process_count,
                "plan": plan.plan_destination,
                "events": plan.event_log,
            }
    except AcceptanceFailure as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


def _owner_paths(
    scope: dict[str, object], repository_root: Path, overrides: list[str]
) -> tuple[dict[str, Path], dict[str, tuple[str, ...]]]:
    override_map: dict[str, Path] = {}
    for value in overrides:
        if "=" not in value:
            raise AcceptanceFailure(f"invalid owner-root override: {value}")
        owner, raw_path = value.split("=", 1)
        if not owner or owner in override_map or not raw_path:
            raise AcceptanceFailure(f"invalid owner-root override: {value}")
        override_map[owner] = Path(raw_path).resolve()
    raw_owners = scope.get("owners")
    if not isinstance(raw_owners, dict) or set(override_map) - set(raw_owners):
        raise AcceptanceFailure("owner-root override names an unknown owner")
    paths: dict[str, Path] = {}
    patterns: dict[str, tuple[str, ...]] = {}
    for owner, raw_config in raw_owners.items():
        if not isinstance(owner, str) or not isinstance(raw_config, dict):
            raise AcceptanceFailure("scope owner configuration is invalid")
        repository = raw_config.get("repository")
        source_patterns = raw_config.get("source_patterns")
        if not isinstance(repository, str) or not isinstance(source_patterns, list):
            raise AcceptanceFailure("scope owner configuration is invalid")
        paths[owner] = override_map.get(owner, (repository_root / repository).resolve())
        patterns[owner] = tuple(source_patterns)
    return paths, patterns


def _completed_runs(path: Path, plan_identity: str) -> frozenset[tuple[str, int]]:
    completed: set[tuple[str, int]] = set()
    if not path.is_file():
        return frozenset()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if (
                isinstance(event, dict)
                and event.get("event") == "step_finished"
                and event.get("plan_identity") == plan_identity
                and isinstance(event.get("step_id"), str)
                and isinstance(event.get("replay"), int)
            ):
                completed.add((event["step_id"], event["replay"]))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceFailure(f"cannot resume event evidence: {exc}") from exc
    return frozenset(completed)


if __name__ == "__main__":
    raise SystemExit(main())
