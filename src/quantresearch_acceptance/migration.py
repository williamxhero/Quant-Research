"""Compatibility migration for prior acceptance-scope evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from .core import AcceptanceFailure


@dataclass(frozen=True, slots=True)
class LegacyScopeMigration:
    schema: str
    source_schema: str
    source_digest: str
    spec: str
    required_installed_tracers: tuple[str, ...]
    deferred_release_tracers: tuple[str, ...]
    source_document: dict[str, object]
    migrated_scope: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "source_schema": self.source_schema,
            "source_digest": self.source_digest,
            "spec": self.spec,
            "required_installed_tracers": list(self.required_installed_tracers),
            "deferred_release_tracers": list(self.deferred_release_tracers),
            "source_document": self.source_document,
            "migrated_scope": self.migrated_scope,
        }


def migrate_legacy_scope(value: Mapping[str, object]) -> LegacyScopeMigration:
    """Lift a strict v1 scope into v2 without discarding its recorded proof."""
    required = {
        "schema",
        "spec",
        "baseline_heads",
        "product_changed_paths",
        "selection_maintenance_paths",
        "required_installed_tracers",
        "deferred_release_tracers",
    }
    if (
        not isinstance(value, Mapping)
        or value.get("schema") != "quant-research.acceptance-scope.v1"
        or not required <= set(value)
        or not isinstance(value.get("test_protocol"), Mapping)
    ):
        raise AcceptanceFailure("legacy acceptance scope is invalid")
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    digest = hashlib.sha256(canonical).hexdigest()
    baselines = value["baseline_heads"]
    protocol = value["test_protocol"]
    if not isinstance(baselines, Mapping) or not isinstance(protocol, Mapping):
        raise AcceptanceFailure("legacy acceptance scope is invalid")
    owners: dict[str, object] = {}
    for owner, sha in sorted(baselines.items()):
        if not isinstance(owner, str) or not isinstance(sha, str):
            raise AcceptanceFailure("legacy baseline is invalid")
        prefixes = ["docs/", "tools/"] if owner == "quant-research" else [f"{owner}/"]
        import_name = {
            "quant-research": "quantresearch_acceptance",
            "quant-runtime": "quant_runtime",
            "strategy-workspace": "strategy_workspace",
            "strategy-reporting": "strategy_reporting",
            "apex-research": "apex_research",
        }.get(owner)
        if import_name is None:
            raise AcceptanceFailure(f"unknown legacy owner: {owner}")
        owners[owner] = {
            "fixed_base": sha,
            "repository": "." if owner == "quant-research" else owner,
            "diff_prefixes": prefixes,
            "source_patterns": ["pyproject.toml", "src/"]
            if owner != "quant-research"
            else ["docs/", "tools/"],
            "import_names": [import_name],
            "build_argv": ["uv", "build", "--wheel", "--out-dir", "{wheel_dir}"],
            "source_fingerprint": "sha256:"
            + hashlib.sha256(f"legacy-v1\0{owner}\0{sha}".encode()).hexdigest(),
        }
    raw_levels = protocol.get("levels")
    raw_mapping = protocol.get("source_to_direct_tests")
    if not isinstance(raw_levels, Mapping) or not isinstance(raw_mapping, Mapping):
        raise AcceptanceFailure("legacy test protocol is invalid")
    levels: dict[str, object] = {}
    for name, raw_level in raw_levels.items():
        if not isinstance(name, str) or not isinstance(raw_level, Mapping):
            raise AcceptanceFailure("legacy level is invalid")
        budget = raw_level.get("budget_seconds")
        commands = raw_level.get("commands")
        if not isinstance(budget, int) or not isinstance(commands, list):
            raise AcceptanceFailure("legacy level is invalid")
        migrated_commands = []
        for command in commands:
            if not isinstance(command, Mapping):
                raise AcceptanceFailure("legacy command is invalid")
            migrated_commands.append(
                {
                    "owner": command["repository"]
                    if command["repository"] != "."
                    else "quant-research",
                    "argv": command["argv"],
                    "markers": [],
                    "history_samples_seconds": [budget],
                }
            )
        levels[name] = {"budget_seconds": budget, "commands": migrated_commands}
    changed_paths = sorted(
        set(value["product_changed_paths"])  # type: ignore[arg-type]
        | set(value["selection_maintenance_paths"])  # type: ignore[arg-type]
    )
    mapping = {str(path): list(tests) for path, tests in sorted(raw_mapping.items())}
    for path in changed_paths:
        mapping.setdefault(path, ["tools/test_verify_public_seam_architecture.py"])
    migrated_scope = {
        "schema": "quant-research.acceptance-scope.v2",
        "spec": value["spec"],
        "owners": owners,
        "public_contract_sources": sorted(value["product_changed_paths"]),  # type: ignore[arg-type]
        "source_to_direct_tests": mapping,
        "levels": levels,
        "marker_policy": {
            "allowed": ["connected", "oci", "release", "slow"],
            "ordinary_exclusion": "not slow and not oci and not connected and not release",
        },
        "evidence": {
            "artifact_root": "artifacts/acceptance/{plan_id}",
            "event_log": "events.jsonl",
            "plan": "plan.json",
        },
    }
    required_tracers = tuple(value["required_installed_tracers"])  # type: ignore[arg-type]
    deferred_tracers = tuple(value["deferred_release_tracers"])  # type: ignore[arg-type]
    return LegacyScopeMigration(
        schema="quant-research.acceptance-scope-migration.v1",
        source_schema="quant-research.acceptance-scope.v1",
        source_digest=digest,
        spec=str(value["spec"]),
        required_installed_tracers=required_tracers,
        deferred_release_tracers=deferred_tracers,
        source_document=dict(value),
        migrated_scope=migrated_scope,
    )
