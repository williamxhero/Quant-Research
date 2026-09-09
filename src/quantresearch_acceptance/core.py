"""The deep acceptance-plan module.

Callers provide a reviewed acceptance scope, a fixed-base diff, and a phase.  The
module owns validation, impact selection, canonicalization, and plan identity.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Any, Literal, Mapping

Phase = Literal["spec", "release"]
_SHA = re.compile(r"[0-9a-f]{40}")
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}")
_SPEC = re.compile(r"(?:SPEC|TEST)-[0-9]{3}[A-Z]?")
_LEVELS = ("L0", "L1", "L2", "L3", "L4", "L5")


class AcceptanceFailure(ValueError):
    """An acceptance input is unsafe, stale, ambiguous, or incomplete."""


@dataclass(frozen=True, slots=True)
class SourceFingerprint:
    path: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class OwnerProof:
    owner: str
    repository: str
    fixed_sha: str
    source_fingerprint: str
    import_names: tuple[str, ...]
    build_argv: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlanStep:
    step_id: str
    owner: str
    level: str
    argv: tuple[str, ...]
    budget_seconds: int
    timeout_seconds: int
    markers: tuple[str, ...]
    sources: tuple[str, ...]
    direct_tests: tuple[str, ...]
    junit: str
    replay_count: int = 1
    environment: str = "source"


@dataclass(frozen=True, slots=True)
class AcceptancePlan:
    schema: str
    identity: str
    spec: str
    phase: Phase
    fixed_bases: tuple[tuple[str, str], ...]
    owners: tuple[str, ...]
    levels: tuple[str, ...]
    fingerprints: tuple[SourceFingerprint, ...]
    source_fingerprints: tuple[tuple[str, str], ...]
    owner_proofs: tuple[OwnerProof, ...]
    steps: tuple[PlanStep, ...]
    marker_policy: tuple[str, ...]
    ordinary_exclusion: str
    artifact_root: str
    event_log: str
    plan_destination: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "identity": self.identity,
            "spec": self.spec,
            "phase": self.phase,
            "fixed_bases": dict(self.fixed_bases),
            "owners": list(self.owners),
            "levels": list(self.levels),
            "fingerprints": [
                {"path": item.path, "fingerprint": item.fingerprint}
                for item in self.fingerprints
            ],
            "source_fingerprints": dict(self.source_fingerprints),
            "owner_proofs": [
                {
                    "owner": item.owner,
                    "repository": item.repository,
                    "fixed_sha": item.fixed_sha,
                    "source_fingerprint": item.source_fingerprint,
                    "import_names": list(item.import_names),
                    "build_argv": list(item.build_argv),
                }
                for item in self.owner_proofs
            ],
            "steps": [
                {
                    "step_id": item.step_id,
                    "owner": item.owner,
                    "level": item.level,
                    "argv": list(item.argv),
                    "budget_seconds": item.budget_seconds,
                    "timeout_seconds": item.timeout_seconds,
                    "markers": list(item.markers),
                    "sources": list(item.sources),
                    "direct_tests": list(item.direct_tests),
                    "junit": item.junit,
                    "replay_count": item.replay_count,
                    "environment": item.environment,
                }
                for item in self.steps
            ],
            "marker_policy": list(self.marker_policy),
            "ordinary_exclusion": self.ordinary_exclusion,
            "artifact_root": self.artifact_root,
            "event_log": self.event_log,
            "plan_destination": self.plan_destination,
        }


class AcceptanceSelector:
    """Validate acceptance inputs and emit one immutable deterministic plan."""

    def select(
        self,
        scope: Mapping[str, object],
        fixed_base_diff: Mapping[str, object],
        *,
        phase: Phase,
    ) -> AcceptancePlan:
        if phase not in ("spec", "release"):
            raise AcceptanceFailure(f"unknown acceptance phase: {phase}")
        parsed_scope = _Scope.parse(scope)
        parsed_diff = _Diff.parse(fixed_base_diff)
        if parsed_scope.fixed_bases != parsed_diff.fixed_bases:
            raise AcceptanceFailure("fixed-base diff drifted from acceptance scope")
        if any(
            owner.source_fingerprint != parsed_diff.source_fingerprints[owner.name]
            for owner in parsed_scope.owners
        ):
            raise AcceptanceFailure("source fingerprint drifted from acceptance scope")

        owner_by_source: dict[str, str] = {}
        direct_tests: set[str] = set()
        public_contract_change = False
        for source in parsed_diff.changed_sources:
            owners = tuple(
                owner.name
                for owner in parsed_scope.owners
                if any(source.path.startswith(prefix) for prefix in owner.source_prefixes)
            )
            if len(owners) != 1:
                meaning = "unmapped" if not owners else "ambiguous"
                raise AcceptanceFailure(f"{meaning} changed source: {source.path}")
            if source.path not in parsed_scope.source_to_direct_tests:
                raise AcceptanceFailure(f"unmapped changed source: {source.path}")
            owner_by_source[source.path] = owners[0]
            direct_tests.update(parsed_scope.source_to_direct_tests[source.path])
            public_contract_change |= source.path in parsed_scope.public_contract_sources

        impacted_owners = tuple(sorted(set(owner_by_source.values())))
        selected_levels = ["L0", "L1", "L2"]
        if public_contract_change:
            selected_levels.append("L3")
        if phase == "release":
            selected_levels.extend(name for name in ("L4", "L5") if name in parsed_scope.levels)

        steps: list[PlanStep] = []
        for level_name in selected_levels:
            level = parsed_scope.levels.get(level_name)
            if level is None:
                raise AcceptanceFailure(f"selected level is not configured: {level_name}")
            selected_commands = [
                command for command in level.commands if command.owner in impacted_owners
            ]
            if not selected_commands:
                raise AcceptanceFailure(f"selected level has no impacted command: {level_name}")
            for index, command in enumerate(selected_commands, start=1):
                tests = tuple(sorted(direct_tests))
                argv = _expand_argv(command.argv, direct_tests=tests)
                steps.append(
                    PlanStep(
                        step_id=f"{level_name.lower()}-{command.owner}-{index}",
                        owner=command.owner,
                        level=level_name,
                        argv=argv,
                        budget_seconds=level.budget_seconds,
                        timeout_seconds=historical_timeout(
                            command.history_samples_seconds,
                            budget_seconds=level.budget_seconds,
                        ),
                        markers=command.markers,
                        sources=tuple(
                            source.path
                            for source in parsed_diff.changed_sources
                            if owner_by_source[source.path] == command.owner
                        ),
                        direct_tests=tests,
                        junit=f"{level_name.lower()}-{command.owner}-{index}.xml",
                        replay_count=2 if level_name == "L3" else 1,
                        environment=(
                            "installed-no-source" if level_name == "L3" else "source"
                        ),
                    )
                )

        owner_proofs = tuple(
            OwnerProof(
                owner=owner.name,
                repository=owner.repository,
                fixed_sha=owner.fixed_base,
                source_fingerprint=parsed_diff.source_fingerprints[owner.name],
                import_names=owner.import_names,
                build_argv=owner.build_argv,
            )
            for owner in parsed_scope.owners
            if owner.name not in impacted_owners
        )
        material = {
            "schema": "quant-research.acceptance-plan.v1",
            "spec": parsed_scope.spec,
            "phase": phase,
            "fixed_bases": dict(parsed_scope.fixed_bases),
            "owners": list(impacted_owners),
            "levels": selected_levels,
            "fingerprints": [
                {"path": item.path, "fingerprint": item.fingerprint}
                for item in parsed_diff.changed_sources
            ],
            "source_fingerprints": dict(sorted(parsed_diff.source_fingerprints.items())),
            "owner_proofs": [
                {
                    "owner": item.owner,
                    "repository": item.repository,
                    "fixed_sha": item.fixed_sha,
                    "source_fingerprint": item.source_fingerprint,
                    "import_names": list(item.import_names),
                    "build_argv": list(item.build_argv),
                }
                for item in owner_proofs
            ],
            "steps": [
                {
                    "step_id": item.step_id,
                    "owner": item.owner,
                    "level": item.level,
                    "argv": list(item.argv),
                    "budget_seconds": item.budget_seconds,
                    "timeout_seconds": item.timeout_seconds,
                    "markers": list(item.markers),
                    "sources": list(item.sources),
                    "direct_tests": list(item.direct_tests),
                    "junit": item.junit,
                    "replay_count": item.replay_count,
                    "environment": item.environment,
                }
                for item in steps
            ],
            "marker_policy": list(parsed_scope.allowed_markers),
            "ordinary_exclusion": parsed_scope.ordinary_exclusion,
            "evidence": parsed_scope.evidence,
        }
        identity = hashlib.sha256(_canonical_json(material)).hexdigest()
        artifact_root = parsed_scope.evidence["artifact_root"].replace(
            "{plan_id}", identity
        )
        resolved_steps = tuple(
            replace(item, junit=f"{artifact_root}/{item.junit}") for item in steps
        )
        return AcceptancePlan(
            schema="quant-research.acceptance-plan.v1",
            identity=identity,
            spec=parsed_scope.spec,
            phase=phase,
            fixed_bases=parsed_scope.fixed_bases,
            owners=impacted_owners,
            levels=tuple(selected_levels),
            fingerprints=parsed_diff.changed_sources,
            source_fingerprints=tuple(sorted(parsed_diff.source_fingerprints.items())),
            owner_proofs=owner_proofs,
            steps=resolved_steps,
            marker_policy=parsed_scope.allowed_markers,
            ordinary_exclusion=parsed_scope.ordinary_exclusion,
            artifact_root=artifact_root,
            event_log=f"{artifact_root}/{parsed_scope.evidence['event_log']}",
            plan_destination=f"{artifact_root}/{parsed_scope.evidence['plan']}",
        )


@dataclass(frozen=True, slots=True)
class _Owner:
    name: str
    fixed_base: str
    repository: str
    source_prefixes: tuple[str, ...]
    import_names: tuple[str, ...]
    build_argv: tuple[str, ...]
    source_fingerprint: str


@dataclass(frozen=True, slots=True)
class _Command:
    owner: str
    argv: tuple[str, ...]
    markers: tuple[str, ...]
    history_samples_seconds: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class _Level:
    budget_seconds: int
    commands: tuple[_Command, ...]


@dataclass(frozen=True, slots=True)
class _Scope:
    spec: str
    owners: tuple[_Owner, ...]
    fixed_bases: tuple[tuple[str, str], ...]
    public_contract_sources: frozenset[str]
    source_to_direct_tests: dict[str, tuple[str, ...]]
    levels: dict[str, _Level]
    allowed_markers: tuple[str, ...]
    ordinary_exclusion: str
    evidence: dict[str, str]

    @classmethod
    def parse(cls, value: Mapping[str, object]) -> _Scope:
        _exact_fields(
            value,
            {
                "schema",
                "spec",
                "owners",
                "public_contract_sources",
                "source_to_direct_tests",
                "levels",
                "marker_policy",
                "evidence",
            },
            "acceptance scope",
        )
        if value["schema"] != "quant-research.acceptance-scope.v2":
            raise AcceptanceFailure("acceptance scope schema is invalid")
        spec = value["spec"]
        if not isinstance(spec, str) or _SPEC.fullmatch(spec) is None:
            raise AcceptanceFailure("acceptance scope spec is invalid")
        raw_owners = _mapping(value["owners"], "owners")
        owners: list[_Owner] = []
        prefixes: list[tuple[str, str]] = []
        for name in sorted(raw_owners):
            raw_owner = _mapping(raw_owners[name], f"owner {name}")
            _exact_fields(
                raw_owner,
                {
                    "fixed_base",
                    "repository",
                    "source_prefixes",
                    "import_names",
                    "build_argv",
                    "source_fingerprint",
                },
                f"owner {name}",
            )
            sha = _string(raw_owner["fixed_base"], f"owner {name} fixed base")
            if _SHA.fullmatch(sha) is None:
                raise AcceptanceFailure(f"owner {name} fixed base is invalid")
            raw_prefixes = _canonical_strings(
                raw_owner["source_prefixes"], f"owner {name} source prefixes"
            )
            source_prefixes = tuple(_prefix(item) for item in raw_prefixes)
            for prefix in source_prefixes:
                prefixes.append((prefix, name))
            owners.append(
                _Owner(
                    name=name,
                    fixed_base=sha,
                    repository=(
                        "."
                        if raw_owner["repository"] == "."
                        else _path(raw_owner["repository"])
                    ),
                    source_prefixes=source_prefixes,
                    import_names=_canonical_strings(
                        raw_owner["import_names"], f"owner {name} import names"
                    ),
                    build_argv=_argv(raw_owner["build_argv"]),
                    source_fingerprint=_fingerprint(
                        raw_owner["source_fingerprint"], f"owner {name} source fingerprint"
                    ),
                )
            )
        for index, (prefix, owner) in enumerate(prefixes):
            for other_prefix, other_owner in prefixes[index + 1 :]:
                if owner != other_owner and (
                    prefix.startswith(other_prefix) or other_prefix.startswith(prefix)
                ):
                    raise AcceptanceFailure(
                        f"ambiguous owner source prefixes: {owner}, {other_owner}"
                    )
        mapping = _mapping(value["source_to_direct_tests"], "source mapping")
        source_to_direct_tests = {
            _path(source): _canonical_paths(tests, f"tests for {source}")
            for source, tests in sorted(mapping.items())
        }
        public_sources = frozenset(
            _canonical_paths(value["public_contract_sources"], "public contracts")
        )
        if not public_sources <= set(source_to_direct_tests):
            raise AcceptanceFailure("public contract source lacks a direct-test mapping")
        raw_levels = _mapping(value["levels"], "levels")
        if any(name not in _LEVELS for name in raw_levels):
            raise AcceptanceFailure("acceptance scope contains an unknown level")
        levels: dict[str, _Level] = {}
        for name in sorted(raw_levels, key=_LEVELS.index):
            raw_level = _mapping(raw_levels[name], f"level {name}")
            _exact_fields(raw_level, {"budget_seconds", "commands"}, f"level {name}")
            budget = raw_level["budget_seconds"]
            if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
                raise AcceptanceFailure(f"level {name} budget is invalid")
            commands: list[_Command] = []
            for raw in _list(raw_level["commands"], f"level {name} commands"):
                command = _mapping(raw, f"level {name} command")
                _exact_fields(
                    command,
                    {"owner", "argv", "markers", "history_samples_seconds"},
                    f"level {name} command",
                )
                owner = _string(command["owner"], "command owner")
                if owner not in raw_owners:
                    raise AcceptanceFailure(f"command owner is unknown: {owner}")
                # History becomes the timeout source in TEST-001.3; validate its shape now.
                history = _list(command["history_samples_seconds"], "history samples")
                if not history or any(
                    not isinstance(item, (int, float))
                    or isinstance(item, bool)
                    or not math.isfinite(item)
                    or item <= 0
                    for item in history
                ):
                    raise AcceptanceFailure("history samples are invalid")
                commands.append(
                    _Command(
                        owner=owner,
                        argv=_argv(command["argv"]),
                        markers=_canonical_strings(command["markers"], "markers", empty=True),
                        history_samples_seconds=tuple(float(item) for item in history),
                    )
                )
            if not commands:
                raise AcceptanceFailure(f"level {name} has no commands")
            levels[name] = _Level(budget, tuple(commands))
        marker_policy = _mapping(value["marker_policy"], "marker policy")
        _exact_fields(marker_policy, {"allowed", "ordinary_exclusion"}, "marker policy")
        allowed = _canonical_strings(marker_policy["allowed"], "allowed markers")
        if allowed != ("connected", "oci", "release", "slow"):
            raise AcceptanceFailure("marker policy is not canonical")
        if any(
            marker not in allowed
            for level in levels.values()
            for command in level.commands
            for marker in command.markers
        ):
            raise AcceptanceFailure("command uses an unknown marker")
        exclusion = _string(marker_policy["ordinary_exclusion"], "ordinary exclusion")
        if exclusion != "not slow and not oci and not connected and not release":
            raise AcceptanceFailure("ordinary marker exclusion is invalid")
        evidence_raw = _mapping(value["evidence"], "evidence")
        _exact_fields(evidence_raw, {"artifact_root", "event_log", "plan"}, "evidence")
        evidence = {name: _path(item) for name, item in evidence_raw.items()}
        if "{plan_id}" not in evidence["artifact_root"]:
            raise AcceptanceFailure("artifact root must contain {plan_id}")
        return cls(
            spec=spec,
            owners=tuple(owners),
            fixed_bases=tuple((owner.name, owner.fixed_base) for owner in owners),
            public_contract_sources=public_sources,
            source_to_direct_tests=source_to_direct_tests,
            levels=levels,
            allowed_markers=allowed,
            ordinary_exclusion=exclusion,
            evidence=evidence,
        )


@dataclass(frozen=True, slots=True)
class _Diff:
    fixed_bases: tuple[tuple[str, str], ...]
    source_fingerprints: dict[str, str]
    changed_sources: tuple[SourceFingerprint, ...]

    @classmethod
    def parse(cls, value: Mapping[str, object]) -> _Diff:
        _exact_fields(
            value,
            {"schema", "fixed_bases", "source_fingerprints", "changed_sources"},
            "fixed-base diff",
        )
        if value["schema"] != "quant-research.fixed-base-diff.v1":
            raise AcceptanceFailure("fixed-base diff schema is invalid")
        bases = _mapping(value["fixed_bases"], "diff fixed bases")
        fixed_bases: list[tuple[str, str]] = []
        for owner, raw_sha in sorted(bases.items()):
            sha = _string(raw_sha, f"diff fixed base {owner}")
            if _SHA.fullmatch(sha) is None:
                raise AcceptanceFailure(f"diff fixed base is invalid: {owner}")
            fixed_bases.append((owner, sha))
        raw_fingerprints = _mapping(value["source_fingerprints"], "source fingerprints")
        if set(raw_fingerprints) != set(bases):
            raise AcceptanceFailure("owner source fingerprints are incomplete")
        source_fingerprints = {
            owner: _fingerprint(raw, f"owner source fingerprint {owner}")
            for owner, raw in sorted(raw_fingerprints.items())
        }
        changed: list[SourceFingerprint] = []
        previous = ""
        for raw in _list(value["changed_sources"], "changed sources"):
            item = _mapping(raw, "changed source")
            _exact_fields(item, {"path", "fingerprint"}, "changed source")
            path = _path(item["path"])
            fingerprint = _string(item["fingerprint"], "source fingerprint")
            if _FINGERPRINT.fullmatch(fingerprint) is None:
                raise AcceptanceFailure(f"source fingerprint is invalid: {path}")
            if path <= previous:
                raise AcceptanceFailure("changed sources are not canonical")
            previous = path
            changed.append(SourceFingerprint(path, fingerprint))
        if not changed:
            raise AcceptanceFailure("fixed-base diff has no changed sources")
        return cls(tuple(fixed_bases), source_fingerprints, tuple(changed))


def _expand_argv(argv: tuple[str, ...], *, direct_tests: tuple[str, ...]) -> tuple[str, ...]:
    expanded: list[str] = []
    for token in argv:
        if token == "{direct_tests}":
            expanded.extend(direct_tests)
        else:
            expanded.append(token)
    return tuple(expanded)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def historical_timeout(
    samples_seconds: list[float] | tuple[float, ...], *, budget_seconds: int
) -> int:
    """Return nearest-rank p95 plus a bounded 25% margin, clamped to budget."""
    if (
        not samples_seconds
        or not isinstance(budget_seconds, int)
        or isinstance(budget_seconds, bool)
        or budget_seconds <= 0
        or any(
            not isinstance(item, (int, float))
            or isinstance(item, bool)
            or not math.isfinite(item)
            or item <= 0
            for item in samples_seconds
        )
    ):
        raise AcceptanceFailure("historical timeout evidence is invalid")
    ordered = sorted(float(item) for item in samples_seconds)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    margin = min(60.0, max(5.0, p95 * 0.25))
    return min(budget_seconds, max(1, math.ceil(p95 + margin)))


def _exact_fields(value: Mapping[str, object], expected: set[str], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise AcceptanceFailure(f"{label} fields are invalid")


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise AcceptanceFailure(f"{label} is invalid")
    return value


def _list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise AcceptanceFailure(f"{label} is invalid")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise AcceptanceFailure(f"{label} is invalid")
    return value


def _fingerprint(value: object, label: str) -> str:
    fingerprint = _string(value, label)
    if _FINGERPRINT.fullmatch(fingerprint) is None:
        raise AcceptanceFailure(f"{label} is invalid")
    return fingerprint


def _canonical_strings(
    value: object, label: str, *, empty: bool = False
) -> tuple[str, ...]:
    values = _list(value, label)
    if (not values and not empty) or any(not isinstance(item, str) or not item for item in values):
        raise AcceptanceFailure(f"{label} is invalid")
    if values != sorted(set(values)):
        raise AcceptanceFailure(f"{label} is not canonical")
    return tuple(values)


def _canonical_paths(value: object, label: str) -> tuple[str, ...]:
    values = _canonical_strings(value, label)
    return tuple(_path(item) for item in values)


def _path(value: object) -> str:
    path = _string(value, "path").replace("\\", "/")
    pure = PurePosixPath(path)
    if (
        path.startswith("/")
        or pure.is_absolute()
        or any(part in ("", ".", "..") for part in pure.parts)
        or str(pure) != path
    ):
        raise AcceptanceFailure(f"path is not normalized: {value}")
    return path


def _prefix(value: object) -> str:
    prefix = _string(value, "source prefix").replace("\\", "/")
    if not prefix.endswith("/"):
        raise AcceptanceFailure(f"source prefix must end with '/': {value}")
    _path(prefix[:-1])
    return prefix


def _argv(value: object) -> tuple[str, ...]:
    raw = _list(value, "argv")
    if not raw or any(not isinstance(item, str) or not item for item in raw):
        raise AcceptanceFailure("argv is invalid")
    argv = tuple(raw)
    if any("\x00" in item or "\n" in item or "\r" in item for item in argv):
        raise AcceptanceFailure("argv contains an unsafe token")
    return argv
