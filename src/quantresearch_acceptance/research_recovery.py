"""#408 RM-V1D.3: end-to-end recovery across a real store.

#397 proved a Context rebuilds from its declaration, #398 proved the pages
behind it, #401 proved a display projection can be dropped, and #396 proved an
interrupted delivery stays uncertain.  Each of those proofs lives inside one
module and inside one Python process: an object is ``del``-ed and rebuilt from a
record that never left memory.

This module closes the remaining seam, which is the one the ticket actually
asks about: **a store on disk, whose rebuildable parts are really deleted, and
whose formal parts are read back by a process that was not there when they were
written.**

The store has exactly two scopes, and the whole module exists to keep them
apart.

**Preserved** -- the formal Workspace records, the exact artifacts, and the
frozen policy / template / manifest.  These are the only things recovery is
allowed to read.  Deleting one is a *fact* that is missing, never something to
be papered over.

**Discardable** -- the retrieval cache, the adopted FTS5 / display projections
and the in-memory lineage graph.  (NetworkX is absent from this package by
#401's decision, so the "in-memory graph" here is the same bounded adjacency
list the rest of the seam uses.)  Every one of these may be deleted at any time,
and recovery must not notice.

Four rules shape everything below.

**Recovery reads the formal scope and nothing else.**  ``recover_end_to_end``
takes a store root and a *current* visibility request.  It takes no engine, no
read model, no retrieval callable and no fallback source, so there is literally
nothing for it to spend a backtest, a model call or a budget reservation
through.  A leftover cache or a fixture cannot stand in for a missing fact
because the seam has no way to reach one.

**Three failures stay three failures.**  ``facts_missing`` (a formal record is
gone), ``authorization_restricted`` (the *current* reader may not have it) and
``content_corrupted`` (the bytes no longer reproduce their recorded digest) are
distinct outcomes.  None of them may impersonate a recovery, and a restricted
answer publishes no identity, no object name and no count at all.

**Reconciliation comes before re-delivery.**  The append-only Exposure log is
read first, from disk, with #396's conservative loader: a torn tail leaves a
prepared action ``delivery_uncertain`` rather than unseen, because the local
write failing proves nothing about what the external consumer received.
Recovery never resends, and never re-applies a side effect that is already
confirmed -- the log's own append is idempotent on an unchanged input.

**A digest is not a body.**  Replay coverage is whatever #396 recorded at
delivery time.  When only a digest survives, the reconstruction is ``limited``
and says so; the model is never re-invoked and no fresh retrieval is run to
manufacture the original request or answer after the fact.

What this module deliberately does not do: it adds no dependency, opens no
network, spawns no process, keeps no index of its own, and publishes no
efficiency figure.  It is standard library and ``pathlib`` only.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .core import AcceptanceFailure
from .research_currency import (
    deliver_reporting_projection,
    reconstruct_reporting_projection,
)
from .research_exposure import ExposureLog, ExposureReplay, replay_exposure_delivery
from .research_pagination import (
    deliver_paginated_research_brief,
    reconstruct_paginated_research_context,
)
from .research_visibility import evaluate_visibility_request

RECOVERY_STORE_SCHEMA = "quant-research.research-recovery-store.v1"
RECOVERY_MANIFEST_SCHEMA = "quant-research.research-recovery-manifest.v1"
RECOVERY_READBACK_SCHEMA = "quant-research.research-recovery-readback.v1"

#: The formal scope, relative to ``<root>/preserved``.  Every one of these is
#: required: a missing one is an honest ``facts_missing``, never a rebuild from
#: whatever else happens to be lying around.
PRESERVED_OBJECTS: tuple[str, ...] = (
    "exposure.jsonl",
    "manifest.json",
    "paginated_context.json",
    "reporting_projection.json",
)

#: The rebuildable scope, relative to ``<root>/projections``.  Deleting all of
#: them is the normal case this ticket proves, not an error.
DISCARDABLE_OBJECTS: tuple[str, ...] = (
    "display_projection.json",
    "fts5_index.json",
    "lineage_graph.json",
    "retrieval_cache.json",
)

PRESERVED_DIR = "preserved"
DISCARDABLE_DIR = "projections"

RecoveryStatus = Literal[
    "recovered",
    "facts_missing",
    "authorization_restricted",
    "content_corrupted",
]

RECOVERY_STATUSES: tuple[str, ...] = (
    "recovered",
    "facts_missing",
    "authorization_restricted",
    "content_corrupted",
)

#: The fixed order recovery runs in, published on every outcome so that
#: "reconciliation happened first" is a checkable fact rather than a promise.
RECOVERY_STAGES: tuple[str, ...] = (
    "reconcile_delivery",
    "check_current_authorization",
    "check_formal_facts",
    "check_record_integrity",
    "rebuild_from_formal_records",
    "redeliver_under_current_authorization",
)


class RecoveryRefusal(AcceptanceFailure):
    """The store was asked for something the two scopes do not allow."""


def _digest(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True)
class DeliveryReconciliation:
    """What the append-only delivery record says, before anything is re-sent."""

    torn_tail: bool
    states: tuple[tuple[str, str], ...]
    uncertain_actions: tuple[str, ...]

    @property
    def resend_allowed(self) -> bool:
        """Never.  A local checkpoint is not proof the consumer saw nothing."""

        return False

    def as_dict(self) -> dict[str, object]:
        return {
            "torn_tail": self.torn_tail,
            "states": [{"action_key": key, "state": state} for key, state in self.states],
            "uncertain_actions": list(self.uncertain_actions),
            "resend_allowed": self.resend_allowed,
            # Reconciliation reads the record; it re-applies nothing that the
            # record already confirms.
            "reapplied_confirmed_side_effects": False,
        }


@dataclass(frozen=True, slots=True)
class RecoveryStore:
    """A real directory with a formal scope and a rebuildable scope."""

    root: Path
    #: The #398 paginated identity, which is what the manifest freezes.
    context_identity: str
    projection_identity: str
    #: Observed at write time.  ``exposure.jsonl`` is an append-only journal, so
    #: its entry is an observation rather than a contract.
    digests: tuple[tuple[str, str], ...]

    @property
    def preserved(self) -> Path:
        return self.root / PRESERVED_DIR

    @property
    def discardable(self) -> Path:
        return self.root / DISCARDABLE_DIR

    def readback(self) -> dict[str, object]:
        return {
            "schema": RECOVERY_STORE_SCHEMA,
            "context_identity": self.context_identity,
            "projection_identity": self.projection_identity,
            "preserved_objects": list(PRESERVED_OBJECTS),
            "discardable_objects": list(DISCARDABLE_OBJECTS),
            "digests": [{"object": name, "digest": digest} for name, digest in self.digests],
        }


@dataclass(frozen=True, slots=True)
class RecoveryOutcome:
    """The public result of recovering one store under one current authorization."""

    status: RecoveryStatus
    stages: tuple[str, ...]
    context_identity: str | None
    projection_identity: str | None
    reporting_boundary: tuple[str, ...] | None
    missing_objects: tuple[str, ...]
    corrupted_objects: tuple[str, ...]
    reconciliation: DeliveryReconciliation | None
    context_exposure: str | None
    replay: ExposureReplay | None
    read_objects: tuple[str, ...]

    def readback(self) -> dict[str, object]:
        return {
            "schema": RECOVERY_READBACK_SCHEMA,
            "status": self.status,
            "stages": list(self.stages),
            "context_identity": self.context_identity,
            "projection_identity": self.projection_identity,
            "reporting_boundary": (
                None if self.reporting_boundary is None else list(self.reporting_boundary)
            ),
            "missing_objects": list(self.missing_objects),
            "corrupted_objects": list(self.corrupted_objects),
            "reconciliation": (
                None if self.reconciliation is None else self.reconciliation.as_dict()
            ),
            "context_exposure": self.context_exposure,
            "replay": None if self.replay is None else self.replay.as_dict(),
            "read_objects": list(self.read_objects),
            # The four claims this ticket exists to make, stated by the seam
            # rather than by a comment in a test.
            "used_discardable_projection": False,
            "used_fresh_retrieval": False,
            "used_fixture_substitute": False,
            "new_backtests": 0,
            "model_invocations": 0,
            "budget_reservations": 0,
            "grants_eligibility": False,
        }


def write_recovery_store(
    root: Path,
    *,
    context_record: Mapping[str, object],
    reporting_record: Mapping[str, object],
    exposure_events: tuple[Mapping[str, object], ...],
) -> RecoveryStore:
    """Lay out both scopes on disk and freeze the formal manifest over them.

    The discardable scope is derived here, from the formal records, exactly as a
    cache or a display index would be.  That is the point: it holds nothing the
    formal records do not already hold, so losing it can lose nothing.
    """

    root = Path(root)
    preserved = root / PRESERVED_DIR
    discardable = root / DISCARDABLE_DIR
    preserved.mkdir(parents=True, exist_ok=True)
    discardable.mkdir(parents=True, exist_ok=True)

    context_identity = context_record.get("paginated_identity")
    projection_identity = reporting_record.get("projection_identity")
    if not isinstance(context_identity, str) or not isinstance(projection_identity, str):
        raise RecoveryRefusal("a formal record is missing its public identity")

    bodies: dict[str, bytes] = {
        "paginated_context.json": _canonical(context_record),
        "reporting_projection.json": _canonical(reporting_record),
        "exposure.jsonl": b"".join(_canonical(event) + b"\n" for event in exposure_events),
    }
    for name, body in bodies.items():
        (preserved / name).write_bytes(body)

    # The frozen manifest: policy, template and the digests of the exact
    # artifacts.  It is itself a preserved object, and it is written last.
    inner = _mapping(context_record.get("declaration"), "context record declaration")
    declaration = _mapping(inner.get("context"), "context declaration")
    #: ``exposure.jsonl`` is deliberately *not* digested here.  It is an
    #: append-only journal that legitimately grows and that a real interruption
    #: legitimately tears; freezing a digest over it would turn #396's
    #: ``delivery_uncertain`` recovery into a false corruption report.  Its
    #: integrity is #396's conservative loader instead.
    manifest = {
        "schema": RECOVERY_MANIFEST_SCHEMA,
        "context_identity": context_identity,
        "projection_identity": projection_identity,
        "policy": declaration.get("policy"),
        "snapshot": declaration.get("snapshot"),
        "objects": [
            {"object": name, "digest": _digest(body)}
            for name, body in sorted(bodies.items())
            if name != "exposure.jsonl"
        ],
    }
    manifest_body = _canonical(manifest)
    (preserved / "manifest.json").write_bytes(manifest_body)

    digests = tuple(
        sorted({**{name: _digest(body) for name, body in bodies.items()},
                "manifest.json": _digest(manifest_body)}.items())
    )

    # The rebuildable scope, derived from what is already formal.
    _write_discardable(discardable, context_record, reporting_record)

    return RecoveryStore(
        root=root,
        context_identity=context_identity,
        projection_identity=projection_identity,
        digests=digests,
    )


def _write_discardable(
    directory: Path,
    context_record: Mapping[str, object],
    reporting_record: Mapping[str, object],
) -> None:
    inner = _mapping(context_record.get("declaration"), "context record declaration")
    declaration = _mapping(inner.get("context"), "context declaration")
    sources = declaration.get("sources")
    source_ids = sorted(
        str(item.get("source_id"))
        for item in (sources if isinstance(sources, list) else [])
        if isinstance(item, Mapping)
    )
    payloads: dict[str, object] = {
        "retrieval_cache.json": {"cached_source_ids": source_ids},
        "fts5_index.json": {"terms": {source_id: [source_id] for source_id in source_ids}},
        "lineage_graph.json": {"adjacency": {source_id: [] for source_id in source_ids}},
        "display_projection.json": {
            "projection_identity": reporting_record.get("projection_identity"),
            "rendered_source_ids": source_ids,
        },
    }
    for name, payload in payloads.items():
        (directory / name).write_bytes(_canonical(payload))


def discard_projections(store: RecoveryStore) -> tuple[str, ...]:
    """Really delete every rebuildable object, and return what was deleted.

    Nothing formal is reachable from here: the walk is confined to the
    discardable directory, and a sub-directory or an unexpected name is a
    refusal rather than a wider delete.
    """

    directory = store.discardable
    if not directory.exists():
        return ()
    deleted: list[str] = []
    for child in sorted(directory.iterdir()):
        if child.is_dir():
            raise RecoveryRefusal("the discardable scope holds no sub-directories")
        if child.name not in DISCARDABLE_OBJECTS:
            raise RecoveryRefusal(f"{child.name} is not a declared discardable object")
        child.unlink()
        deleted.append(f"{DISCARDABLE_DIR}/{child.name}")
    directory.rmdir()
    deleted.append(f"{DISCARDABLE_DIR}/")
    return tuple(deleted)


def recover_end_to_end(root: Path, visibility_request: Mapping[str, object]) -> RecoveryOutcome:
    """Recover a Context, its reporting boundary and its delivery record.

    Two parameters, on purpose: a store and the reader's *current* authority.
    There is no engine, no read model and no retrieval callable, so this seam
    cannot run a backtest, invoke a model or reserve a budget even by mistake.
    """

    root = Path(root)
    preserved = root / PRESERVED_DIR
    stages: list[str] = []
    read: list[str] = []

    # 1. Reconciliation first.  The delivery record is read before anything is
    #    rebuilt or handed back, so a locally completed write never stands in
    #    for an external receipt.
    log, exposure_unreadable = _load_exposure(preserved / "exposure.jsonl")
    if (preserved / "exposure.jsonl").exists():
        read.append("exposure.jsonl")
    reconciliation = _reconcile(log)
    stages.append(RECOVERY_STAGES[0])

    # 2. Current authorization, checked on this read and again on every
    #    re-delivery below.  A restricted answer carries nothing at all.
    decision = evaluate_visibility_request(visibility_request)
    if not decision.deliverable:
        return RecoveryOutcome(
            status="authorization_restricted",
            stages=tuple([*stages, RECOVERY_STAGES[1]]),
            context_identity=None,
            projection_identity=None,
            reporting_boundary=None,
            missing_objects=(),
            corrupted_objects=(),
            reconciliation=None,
            context_exposure=None,
            replay=None,
            read_objects=(),
        )
    stages.append(RECOVERY_STAGES[1])

    # 3. Every formal fact must be present.  Nothing is substituted for one.
    missing = tuple(name for name in PRESERVED_OBJECTS if not (preserved / name).exists())
    if missing:
        return _incomplete("facts_missing", stages, RECOVERY_STAGES[2], missing, (), reconciliation)
    stages.append(RECOVERY_STAGES[2])

    # 4. ... and must still be the bytes the manifest froze.
    corrupted, manifest = _check_integrity(preserved, exposure_unreadable)
    read.extend(name for name in PRESERVED_OBJECTS if name not in read)
    if corrupted:
        return _incomplete(
            "content_corrupted", stages, RECOVERY_STAGES[3], (), corrupted, reconciliation
        )
    stages.append(RECOVERY_STAGES[3])

    # 5. Rebuild from the formal records alone.
    context_record = json.loads((preserved / "paginated_context.json").read_text("utf-8"))
    reporting_record = json.loads((preserved / "reporting_projection.json").read_text("utf-8"))
    try:
        context = reconstruct_paginated_research_context(context_record)
        projection = reconstruct_reporting_projection(reporting_record)
    except AcceptanceFailure:
        # A record that parses but no longer reproduces its own identity is
        # corrupt content, not an absent fact and not a permission problem.
        return _incomplete(
            "content_corrupted",
            stages,
            RECOVERY_STAGES[4],
            (),
            ("paginated_context.json", "reporting_projection.json"),
            reconciliation,
        )
    if context.identity != manifest.get("context_identity") or (
        projection.identity != manifest.get("projection_identity")
    ):
        return _incomplete(
            "content_corrupted",
            stages,
            RECOVERY_STAGES[4],
            (),
            ("manifest.json",),
            reconciliation,
        )
    stages.append(RECOVERY_STAGES[4])

    # 6. Re-deliver, under the same current authorization.
    brief = deliver_paginated_research_brief(context, visibility_request)
    report = deliver_reporting_projection(projection, visibility_request)
    boundary = _boundary(report)
    exposure_state = log.context_exposure(context.context.identity)
    replay = _replay(log, context.context.identity, visibility_request)
    stages.append(RECOVERY_STAGES[5])

    return RecoveryOutcome(
        status="recovered",
        stages=tuple(stages),
        context_identity=str(brief.get("paginated_identity")),
        projection_identity=str(report.get("projection_identity")),
        reporting_boundary=boundary,
        missing_objects=(),
        corrupted_objects=(),
        reconciliation=reconciliation,
        context_exposure=exposure_state,
        replay=replay,
        read_objects=tuple(sorted(read)),
    )


def _incomplete(
    status: RecoveryStatus,
    stages: list[str],
    stage: str,
    missing: tuple[str, ...],
    corrupted: tuple[str, ...],
    reconciliation: DeliveryReconciliation,
) -> RecoveryOutcome:
    return RecoveryOutcome(
        status=status,
        stages=tuple([*stages, stage]),
        context_identity=None,
        projection_identity=None,
        reporting_boundary=None,
        missing_objects=missing,
        corrupted_objects=corrupted,
        reconciliation=reconciliation,
        context_exposure=None,
        replay=None,
        read_objects=(),
    )


def _load_exposure(path: Path) -> tuple[ExposureLog, bool]:
    """#396's conservative loader, with an unreadable file kept as a fact.

    An unreadable delivery record is reported at the integrity stage.  It is
    never silently treated as "no delivery ever happened", which would wash an
    exposure back to unseen.
    """

    try:
        return ExposureLog.load(path), False
    except (AcceptanceFailure, UnicodeDecodeError):
        return ExposureLog(), True


def _reconcile(log: ExposureLog) -> DeliveryReconciliation:
    states = tuple(
        (key, str(log.state(key))) for key in log.action_keys if log.state(key) is not None
    )
    return DeliveryReconciliation(
        torn_tail=log.torn_tail,
        states=states,
        uncertain_actions=tuple(key for key, state in states if state == "delivery_uncertain"),
    )


def _check_integrity(
    preserved: Path, exposure_unreadable: bool
) -> tuple[tuple[str, ...], Mapping[str, object]]:
    try:
        manifest = json.loads((preserved / "manifest.json").read_text("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ("manifest.json",), {}
    if not isinstance(manifest, Mapping) or manifest.get("schema") != RECOVERY_MANIFEST_SCHEMA:
        return ("manifest.json",), {}
    entries = manifest.get("objects")
    corrupted: list[str] = ["exposure.jsonl"] if exposure_unreadable else []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, Mapping):
            return ("manifest.json",), {}
        name = str(entry.get("object"))
        observed = _digest((preserved / name).read_bytes())
        if observed != entry.get("digest") and name not in corrupted:
            corrupted.append(name)
    return tuple(sorted(corrupted)), manifest


def _boundary(report: Mapping[str, object]) -> tuple[str, ...] | None:
    brief = report.get("published_brief")
    if not isinstance(brief, Mapping):
        return None
    fields = brief.get("fields")
    if not isinstance(fields, Mapping):
        return None
    return tuple(sorted(fields))


def _replay(
    log: ExposureLog,
    context_identity: str,
    visibility_request: Mapping[str, object],
) -> ExposureReplay | None:
    """#396's replay, with no loader supplied.

    Passing no ``load_envelope`` is the honest position for a recovered store:
    the body is not here, so the reconstruction is ``limited`` and says so.
    Nothing is re-fetched and no model is re-invoked to fill the gap.
    """

    for key in log.action_keys:
        events = log.events(key)
        if events and events[0].context_identity == context_identity:
            replay, _payload = replay_exposure_delivery(log, key, visibility_request)
            return replay
    return None


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RecoveryRefusal(f"{label} is invalid")
    return value


__all__ = [
    "DISCARDABLE_OBJECTS",
    "PRESERVED_OBJECTS",
    "RECOVERY_MANIFEST_SCHEMA",
    "RECOVERY_READBACK_SCHEMA",
    "RECOVERY_STAGES",
    "RECOVERY_STATUSES",
    "RECOVERY_STORE_SCHEMA",
    "DeliveryReconciliation",
    "RecoveryOutcome",
    "RecoveryRefusal",
    "RecoveryStatus",
    "RecoveryStore",
    "discard_projections",
    "recover_end_to_end",
    "write_recovery_store",
]
