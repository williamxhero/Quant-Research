"""#408 RM-V1D.3: real deletion, real interruption, real restart, real replay.

What makes these tests different from the ones they build on.

#397 / #398 / #401 each proved a rebuild by ``del``-ing a Python object and
reconstructing it from a record that never left memory.  #404's U6 test did the
same for two records at once.  #396 was the only ticket that touched a real
file, and it touched one file, for one module, in one process.

Everything below uses a **real directory**: the formal records and the
append-only Exposure journal are written to disk, the rebuildable projections
are written beside them and then really deleted with ``Path.unlink`` /
``Path.rmdir``, a persisted record is really truncated and really doctored, the
Exposure journal is really torn mid-write, and one test recovers the store from
a **fresh Python interpreter** that never saw the objects that wrote it.
``builtins.open`` is instrumented across the recovery so "it did not read the
cache" is an observed fact rather than a claim.
"""

from __future__ import annotations

import builtins
import json
import subprocess
import sys
from pathlib import Path

import pytest

from ._research_currency_test import (
    _NEW_CUTOFF,
    _OLD_CUTOFF,
    _correction,
    _exposure,
    _fact,
    _view,
)
from ._research_currency_test import _declaration as _context_declaration
from ._research_currency_test import _visibility_request as _reporting_request
from ._research_exposure_test import _delivery, _event, _uncertainty
from .core import AcceptanceFailure
from .research_context import freeze_research_context
from .research_currency import (
    REPORTING_DECLARATION_SCHEMA,
    SourceCurrencyView,
    freeze_reporting_projection,
)
from .research_exposure import ExposureLog
from .research_pagination import (
    PAGINATED_DECLARATION_SCHEMA,
    freeze_paginated_research_context,
)
from .research_recovery import (
    DISCARDABLE_OBJECTS,
    PRESERVED_OBJECTS,
    RECOVERY_STAGES,
    RECOVERY_STATUSES,
    RecoveryRefusal,
    discard_projections,
    recover_end_to_end,
    write_recovery_store,
)

_CONTEXT_MATERIALS = ("counter-1", "experience-1", "support-1")


# --- the end-to-end fixture: one declaration, four seams ----------------------


def _plan() -> dict[str, object]:
    """A retrieval plan that agrees with the #401 declaration it pages for."""

    return {
        "retrieval_id": "retrieval-408",
        "ordering_key": "ordering:frozen-v1",
        "trimming_policy": "trimming:unit-atomic-v1",
        "policy_version": "v1",
        "page_size": 2,
        "page_budget": 4,
        "record_budget": 8,
        "cursor": {
            "cursor_id": "cursor-0",
            "snapshot_id": "snapshot-2026-09-10",
            "ordering_key": "ordering:frozen-v1",
            "position": "start",
            "page_index": 0,
        },
    }


def _record(source_id: str, sort_key: str) -> dict[str, str]:
    return {
        "source_id": source_id,
        "sort_key": sort_key,
        "published_at": "2026-09-01T00:00:00Z",
    }


def _pages() -> list[dict[str, object]]:
    return [
        {
            "page_index": 0,
            "cursor_in": "cursor-0",
            "cursor_out": "cursor-1",
            "status": "ok",
            "exhausted": False,
            "records": [_record("counter-1", "k-01"), _record("experience-1", "k-02")],
        },
        {
            "page_index": 1,
            "cursor_in": "cursor-1",
            "cursor_out": "cursor-2",
            "status": "ok",
            "exhausted": True,
            "records": [_record("support-1", "k-03")],
        },
    ]


def _paginated(**overrides: object):
    declaration = overrides.pop("declaration", None)
    return freeze_paginated_research_context(
        {
            "schema": PAGINATED_DECLARATION_SCHEMA,
            "context": _context_declaration() if declaration is None else declaration,
            "retrieval": {"plan": _plan(), "pages": _pages()},
        }
    )


def _projection(**overrides: object):
    """The Reporting projection over the *same* declaration the pages served."""

    declaration = overrides.pop("declaration", None)
    context = freeze_research_context(
        _context_declaration() if declaration is None else declaration
    )
    value: dict[str, object] = {
        "schema": REPORTING_DECLARATION_SCHEMA,
        "context_record": context.public_record(),
        "currency": _view(),
        "knowledge_cutoff": _NEW_CUTOFF,
        "correction_id": "correction-1",
        # `replay_coverage: limited` with no stored body: the digest is an
        # identity, and this ticket must never manufacture the body back.
        "exposure": _exposure(context.identity),
    }
    value.update(overrides)
    return freeze_reporting_projection(value)


def _events(context_identity: str, *, delivered: bool = True) -> list[dict[str, object]]:
    """The journal as #396 would really have written it, sequence numbers and all."""

    log = ExposureLog()
    log.append(_event("context_prepared", context_identity=context_identity))
    if delivered:
        log.append(
            _event(
                "envelope_delivered",
                context_identity=context_identity,
                delivery=_delivery(content_ref=None, coverage="limited"),
            )
        )
    return log.export()


def _store(root: Path, *, declaration: object | None = None, delivered: bool = True):
    paginated = _paginated(declaration=declaration)
    projection = _projection(declaration=declaration)
    assert paginated.context.identity == projection.context.identity
    return (
        write_recovery_store(
            root,
            context_record=json.loads(json.dumps(paginated.public_record())),
            reporting_record=json.loads(json.dumps(projection.public_record())),
            exposure_events=tuple(
                _events(paginated.context.identity, delivered=delivered)
            ),
        ),
        paginated,
        projection,
    )


def _request(**overrides: object) -> dict[str, object]:
    return _reporting_request(**overrides)


def _audited_open(recorded: list[str]):
    real_open = builtins.open

    def spy(file, *args, **kwargs):  # type: ignore[no-untyped-def]
        recorded.append(str(file))
        return real_open(file, *args, **kwargs)

    return spy, real_open


# --- AC1: really delete the rebuildable scope, really recover ----------------


def test_ac1_deleting_every_projection_on_disk_still_recovers_identity_and_boundary(
    tmp_path: Path,
) -> None:
    """The headline: rm the projections directory, recover the same everything.

    Unlike #404's U6 test, the records are not in memory -- they are files, and
    the objects that produced them are gone before the recovery starts.
    """

    store, paginated, projection = _store(tmp_path / "workspace")
    before = recover_end_to_end(store.root, _request())
    assert before.status == "recovered"

    deleted = discard_projections(store)
    assert deleted == tuple(
        [f"projections/{name}" for name in DISCARDABLE_OBJECTS] + ["projections/"]
    )
    assert not store.discardable.exists()
    # Every formal object survived the delete, byte for byte.
    for name in PRESERVED_OBJECTS:
        assert (store.preserved / name).exists()

    after = recover_end_to_end(store.root, _request())
    assert after.status == "recovered"
    assert after.context_identity == paginated.identity
    assert after.projection_identity == projection.identity
    assert after.reporting_boundary == before.reporting_boundary
    assert after.readback() == before.readback()
    assert after.reporting_boundary is not None and "conditional_conclusions" in (
        after.reporting_boundary
    )


def test_ac1_the_recovery_never_opens_a_discardable_object(tmp_path: Path) -> None:
    """Observed, not asserted: the seam reads the formal scope only."""

    store, _paginated, _projection = _store(tmp_path / "workspace")
    opened: list[str] = []
    spy, real_open = _audited_open(opened)
    builtins.open = spy  # type: ignore[assignment]
    try:
        outcome = recover_end_to_end(store.root, _request())
    finally:
        builtins.open = real_open  # type: ignore[assignment]

    assert outcome.status == "recovered"
    touched = [name for name in opened if "projections" in name.replace("\\", "/")]
    assert touched == [], f"the recovery opened {touched!r}"
    assert outcome.readback()["used_discardable_projection"] is False
    assert outcome.read_objects == tuple(sorted(PRESERVED_OBJECTS))


def test_ac1_the_rebuild_seam_has_no_engine_to_spend_through() -> None:
    """Literally: two parameters, a store and the reader's current authority."""

    import inspect

    parameters = set(inspect.signature(recover_end_to_end).parameters)
    assert parameters == {"root", "visibility_request"}


def test_ac1_a_recovery_publishes_zero_run_model_and_budget_counts(tmp_path: Path) -> None:
    store, _paginated, _projection = _store(tmp_path / "workspace")
    discard_projections(store)
    readback = recover_end_to_end(store.root, _request()).readback()
    assert readback["new_backtests"] == 0
    assert readback["model_invocations"] == 0
    assert readback["budget_reservations"] == 0
    assert readback["used_fresh_retrieval"] is False
    assert readback["used_fixture_substitute"] is False
    assert readback["grants_eligibility"] is False


def test_ac1_the_discardable_scope_cannot_reach_a_formal_object(tmp_path: Path) -> None:
    store, _paginated, _projection = _store(tmp_path / "workspace")
    (store.discardable / "not-declared.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RecoveryRefusal):
        discard_projections(store)
    # The refusal deleted nothing formal, and stopped inside its own scope.
    for name in PRESERVED_OBJECTS:
        assert (store.preserved / name).exists()


# --- AC2: three failures, three outcomes, no substitution --------------------


@pytest.mark.parametrize("missing", PRESERVED_OBJECTS)
def test_ac2_a_deleted_formal_record_is_facts_missing_not_a_rebuild(
    tmp_path: Path, missing: str
) -> None:
    store, _paginated, _projection = _store(tmp_path / "workspace")
    # The cache still holds every source id -- and is still not consulted.
    assert (store.discardable / "retrieval_cache.json").exists()
    (store.preserved / missing).unlink()

    outcome = recover_end_to_end(store.root, _request())
    assert outcome.status == "facts_missing"
    assert outcome.missing_objects == (missing,)
    assert outcome.context_identity is None
    assert outcome.projection_identity is None
    assert outcome.corrupted_objects == ()


def test_ac2_a_truncated_record_is_content_corrupted_not_a_missing_fact(
    tmp_path: Path,
) -> None:
    """A real half-written file, not a synthetic flag."""

    store, _paginated, _projection = _store(tmp_path / "workspace")
    target = store.preserved / "paginated_context.json"
    body = target.read_bytes()
    target.write_bytes(body[: len(body) // 2])

    outcome = recover_end_to_end(store.root, _request())
    assert outcome.status == "content_corrupted"
    assert outcome.corrupted_objects == ("paginated_context.json",)
    assert outcome.missing_objects == ()
    assert outcome.context_identity is None


def test_ac2_a_doctored_record_that_still_parses_is_content_corrupted(
    tmp_path: Path,
) -> None:
    store, _paginated, _projection = _store(tmp_path / "workspace")
    target = store.preserved / "reporting_projection.json"
    record = json.loads(target.read_text("utf-8"))
    record["declaration"]["knowledge_cutoff"] = "2026-10-01T00:00:00Z"
    target.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")), encoding="utf-8")

    outcome = recover_end_to_end(store.root, _request())
    assert outcome.status == "content_corrupted"
    assert "reporting_projection.json" in outcome.corrupted_objects


def test_ac2_a_restricted_reader_gets_a_third_outcome_that_leaks_nothing(
    tmp_path: Path,
) -> None:
    store, paginated, projection = _store(tmp_path / "workspace")
    # Missing *and* unauthorized: the reader learns only that they may not read.
    (store.preserved / "paginated_context.json").unlink()

    outcome = recover_end_to_end(store.root, _request(authorized=False))
    assert outcome.status == "authorization_restricted"
    assert outcome.missing_objects == ()
    assert outcome.corrupted_objects == ()
    body = json.dumps(outcome.readback())
    for leak in (
        *PRESERVED_OBJECTS,
        *DISCARDABLE_OBJECTS,
        *_CONTEXT_MATERIALS,
        paginated.identity,
        projection.identity,
    ):
        assert leak not in body


def test_ac2_the_three_unsafe_outcomes_are_distinct_and_enumerated() -> None:
    assert RECOVERY_STATUSES == (
        "recovered",
        "facts_missing",
        "authorization_restricted",
        "content_corrupted",
    )
    assert len(set(RECOVERY_STATUSES)) == 4


def test_ac2_a_leftover_cache_cannot_fake_a_complete_rebuild(tmp_path: Path) -> None:
    """The cache is deliberately left in place, and the record is deleted."""

    store, _paginated, _projection = _store(tmp_path / "workspace")
    cache = json.loads((store.discardable / "retrieval_cache.json").read_text("utf-8"))
    assert sorted(cache["cached_source_ids"]) == list(_CONTEXT_MATERIALS)
    (store.preserved / "paginated_context.json").unlink()

    outcome = recover_end_to_end(store.root, _request())
    assert outcome.status == "facts_missing"
    assert outcome.readback()["used_discardable_projection"] is False


# --- AC3: real interruption, uncertain stays uncertain -----------------------


def test_ac3_a_real_torn_journal_leaves_the_context_uncertain_never_unseen(
    tmp_path: Path,
) -> None:
    """The process died mid-append; the consumer may well have received it."""

    store, paginated, _projection = _store(tmp_path / "workspace", delivered=False)
    journal = store.preserved / "exposure.jsonl"
    with journal.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write('{"schema":"quant-research.research-exposure-event.v1","event_ty')

    outcome = recover_end_to_end(store.root, _request())
    assert outcome.status == "recovered"
    assert outcome.reconciliation is not None
    assert outcome.reconciliation.torn_tail is True
    assert outcome.reconciliation.uncertain_actions != ()
    assert outcome.context_exposure == "uncertain"
    assert outcome.context_exposure != "unseen"
    assert outcome.reconciliation.resend_allowed is False
    assert outcome.readback()["reconciliation"]["reapplied_confirmed_side_effects"] is False
    # And the Context itself still recovers: an interrupted delivery is not a
    # corrupted store.
    assert outcome.context_identity == paginated.identity


def test_ac3_reconciliation_runs_before_any_re_delivery(tmp_path: Path) -> None:
    store, _paginated, _projection = _store(tmp_path / "workspace")
    outcome = recover_end_to_end(store.root, _request())
    assert outcome.stages == RECOVERY_STAGES
    assert outcome.stages[0] == "reconcile_delivery"
    assert outcome.stages.index("reconcile_delivery") < outcome.stages.index(
        "redeliver_under_current_authorization"
    )


def test_ac3_an_uncertain_delivery_needs_a_public_receipt_and_is_never_resent(
    tmp_path: Path,
) -> None:
    """Lost receipt after send: reconcile on public evidence, never resend."""

    store, paginated, _projection = _store(tmp_path / "workspace", delivered=False)
    journal = store.preserved / "exposure.jsonl"
    identity = paginated.context.identity
    _append(journal, _event("delivery_uncertain", context_identity=identity,
                            uncertainty=_uncertainty()))

    log = ExposureLog.load(journal)
    action_key = log.action_keys[0]
    assert log.state(action_key) == "delivery_uncertain"
    # A blind resend -- an envelope with no receipt -- is refused outright.
    with pytest.raises(AcceptanceFailure):
        log.append(
            _event(
                "envelope_delivered",
                context_identity=identity,
                delivery=_delivery(receipt_ref=None, content_ref=None, coverage="limited"),
            )
        )
    assert log.state(action_key) == "delivery_uncertain"

    # A real public receipt reconciles it; it is never washed back to unseen.
    confirmed = _event(
        "envelope_delivered",
        context_identity=identity,
        delivery=_delivery(content_ref=None, coverage="limited"),
    )
    log.append(confirmed)
    assert log.state(action_key) == "delivered"
    assert log.context_exposure(identity) == "exposed"


def test_ac3_a_duplicate_receipt_event_re_applies_no_side_effect(tmp_path: Path) -> None:
    store, paginated, _projection = _store(tmp_path / "workspace")
    journal = store.preserved / "exposure.jsonl"
    log = ExposureLog.load(journal)
    action_key = log.action_keys[0]
    before = log.readback(action_key)

    identity = paginated.context.identity
    duplicate = _event(
        "envelope_delivered",
        context_identity=identity,
        delivery=_delivery(content_ref=None, coverage="limited"),
    )
    log.append(duplicate)
    assert log.readback(action_key) == before

    # The same key with a *different* input is a conflict, not a second delivery.
    with pytest.raises(AcceptanceFailure):
        log.append(
            _event(
                "envelope_delivered",
                context_identity=identity,
                delivery=_delivery(content_ref="approved-store:other", coverage="full"),
            )
        )
    assert log.readback(action_key) == before


def test_ac3_an_uncertain_delivery_gains_no_independent_validation(tmp_path: Path) -> None:
    store, paginated, _projection = _store(tmp_path / "workspace", delivered=False)
    journal = store.preserved / "exposure.jsonl"
    _append(
        journal,
        _event(
            "delivery_uncertain",
            context_identity=paginated.context.identity,
            uncertainty=_uncertainty(),
        ),
    )
    outcome = recover_end_to_end(store.root, _request())
    readback = outcome.readback()
    assert readback["grants_eligibility"] is False
    log = ExposureLog.load(journal)
    assert log.usage_history()["grants_eligibility"] is False


def test_ac3_an_unreadable_journal_is_corruption_not_a_clean_slate(tmp_path: Path) -> None:
    """A half-overwritten journal must not read as "nothing was ever sent"."""

    store, _paginated, _projection = _store(tmp_path / "workspace")
    journal = store.preserved / "exposure.jsonl"
    journal.write_text("not json at all\n", encoding="utf-8")
    outcome = recover_end_to_end(store.root, _request())
    assert outcome.status == "content_corrupted"
    assert outcome.corrupted_objects == ("exposure.jsonl",)
    assert outcome.context_exposure is None


# --- AC4: historical replay costs nothing and states its coverage -----------


def test_ac4_a_digest_without_a_body_replays_only_as_limited(tmp_path: Path) -> None:
    store, _paginated, _projection = _store(tmp_path / "workspace")
    discard_projections(store)
    outcome = recover_end_to_end(store.root, _request())
    assert outcome.replay is not None
    assert outcome.replay.reconstruction == "limited"
    assert outcome.replay.declared_coverage == "limited"
    assert outcome.replay.payload_present is False
    readback = outcome.readback()
    assert readback["replay"]["payload_present"] is False
    assert readback["model_invocations"] == 0


def test_ac4_a_replay_under_a_revoked_authorization_is_denied(tmp_path: Path) -> None:
    store, _paginated, _projection = _store(tmp_path / "workspace")
    outcome = recover_end_to_end(store.root, _request(authorized=False))
    assert outcome.status == "authorization_restricted"
    assert outcome.replay is None


# --- AC5: revocation, and a correction that moves only the current view ------


def test_ac5_a_correction_moves_the_current_store_and_not_the_old_one(
    tmp_path: Path,
) -> None:
    """Two real stores, one cutoff apart, and one owner correction between them."""

    old_root = tmp_path / "as-of-2026-09-10"
    new_root = tmp_path / "as-of-2026-09-30"
    old_store, old_paginated, _old_projection = _store(old_root)
    _new_store, _new_paginated, _new_projection = _store(new_root)

    old_before = recover_end_to_end(old_store.root, _request()).readback()
    old_bytes = (old_store.preserved / "paginated_context.json").read_bytes()

    # The owner publishes a correction the old snapshot could not have known.
    base = SourceCurrencyView.parse(_view(corrections=[], currency_facts=[]))
    corrected = base.append_correction(_correction("correction-408"))
    corrected = SourceCurrencyView.parse(
        {
            **corrected.as_dict(),
            "currency_facts": [_fact("fact-408", "data-1", "superseded")],
        }
    )
    current = _projection()
    historical = freeze_reporting_projection(
        {
            "schema": REPORTING_DECLARATION_SCHEMA,
            "context_record": current.context.public_record(),
            "currency": corrected.as_dict(),
            "knowledge_cutoff": _OLD_CUTOFF,
            "correction_id": None,
            "exposure": _exposure(current.context.identity),
        }
    )
    published = freeze_reporting_projection(
        {
            "schema": REPORTING_DECLARATION_SCHEMA,
            "context_record": current.context.public_record(),
            "currency": corrected.as_dict(),
            "knowledge_cutoff": _NEW_CUTOFF,
            "correction_id": "correction-408",
            "exposure": _exposure(current.context.identity),
        }
    )

    # The old store is untouched, on disk and in its public identity.
    assert (old_store.preserved / "paginated_context.json").read_bytes() == old_bytes
    old_after = recover_end_to_end(old_store.root, _request()).readback()
    assert old_after == old_before
    assert old_after["context_identity"] == old_paginated.identity

    # The correction reaches the current brief and not the historical one.
    assert historical.readback()["published_corrections"] == []
    assert [
        entry["correction_id"] for entry in published.readback()["published_corrections"]
    ] == ["correction-408"]
    assert historical.context.identity == published.context.identity


def test_ac5_revoked_authorization_cannot_be_bypassed_by_an_old_store(
    tmp_path: Path,
) -> None:
    store, _paginated, _projection = _store(tmp_path / "workspace")
    allowed = recover_end_to_end(store.root, _request())
    assert allowed.status == "recovered"
    revoked = recover_end_to_end(store.root, _request(authorized=False))
    assert revoked.status == "authorization_restricted"
    assert revoked.context_identity is None
    # And the refusal rewrote nothing: the store still recovers for a reader
    # who *is* authorized.
    assert recover_end_to_end(store.root, _request()).readback() == allowed.readback()


# --- AC6 / U1-U6: the real-execution slice this ticket adds ------------------


def test_u6_a_fresh_python_process_recovers_the_same_identity(tmp_path: Path) -> None:
    """A real process restart: nothing this interpreter holds is available.

    #396's interruption tests reloaded a file inside the same interpreter.
    This spawns a new one, with its own import of the package, and compares its
    public answer with ours.
    """

    store, paginated, projection = _store(tmp_path / "workspace")
    discard_projections(store)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request()), encoding="utf-8")

    program = (
        "import json,sys\n"
        "from quantresearch_acceptance.research_recovery import recover_end_to_end\n"
        "root, request = sys.argv[1], json.load(open(sys.argv[2], encoding='utf-8'))\n"
        "print(json.dumps(recover_end_to_end(root, request).readback(), sort_keys=True))\n"
    )
    source_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "-c", program, str(store.root), str(request_path)],
        capture_output=True,
        text=True,
        cwd=str(source_root),
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    restarted = json.loads(completed.stdout.strip().splitlines()[-1])

    assert restarted["status"] == "recovered"
    assert restarted["context_identity"] == paginated.identity
    assert restarted["projection_identity"] == projection.identity
    assert restarted["new_backtests"] == 0
    assert restarted["model_invocations"] == 0
    assert restarted["budget_reservations"] == 0
    assert restarted["used_discardable_projection"] is False
    in_process = recover_end_to_end(store.root, _request()).readback()
    assert restarted == json.loads(json.dumps(in_process, sort_keys=True))


def test_u6_the_deleted_object_list_and_public_identity_are_submitted_evidence(
    tmp_path: Path,
) -> None:
    """The exact before/after counters #443 rolls up."""

    store, paginated, projection = _store(tmp_path / "workspace")
    before = recover_end_to_end(store.root, _request()).readback()
    deleted = discard_projections(store)
    after = recover_end_to_end(store.root, _request()).readback()

    assert deleted == (
        "projections/display_projection.json",
        "projections/fts5_index.json",
        "projections/lineage_graph.json",
        "projections/retrieval_cache.json",
        "projections/",
    )
    assert before["context_identity"] == after["context_identity"] == paginated.identity
    assert before["projection_identity"] == after["projection_identity"] == projection.identity
    assert after["new_backtests"] == after["model_invocations"] == 0
    assert after["budget_reservations"] == 0
    assert store.readback()["preserved_objects"] == list(PRESERVED_OBJECTS)


def test_ac7_the_recovery_needs_no_optional_service_and_no_private_source(
    tmp_path: Path,
) -> None:
    """V1 sign-off with nothing running: the module is standard library only."""

    import ast

    source = Path(__file__).resolve().parent / "research_recovery.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= set(sys.stdlib_module_names)
    for forbidden in ("opa", "mlflow", "optuna", "sqlalchemy", "networkx", "langgraph"):
        assert forbidden not in imported
    # And it really does run here, with none of them installed.
    store, _paginated, _projection = _store(tmp_path / "workspace")
    assert recover_end_to_end(store.root, _request()).status == "recovered"


def test_ac7_the_reporting_boundary_is_owner_facts_with_canonical_readback(
    tmp_path: Path,
) -> None:
    store, _paginated, _projection = _store(tmp_path / "workspace")
    first = recover_end_to_end(store.root, _request()).readback()
    second = recover_end_to_end(store.root, _request()).readback()
    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["reporting_boundary"] == sorted(first["reporting_boundary"])
    assert "current_candidate" in first["reporting_boundary"]


# --- A0-H02 / A0-P02: the A0 reference slice, and what stays pending ---------


def test_a0_h02_the_contract_slice_runs_on_437_shaped_fixtures_only(
    tmp_path: Path,
) -> None:
    """A0-H02 is proved at contract level; its real-asset half is `pending`.

    #441 published no round-one research asset in this repository and #442
    confirmed there is no owner-authorized engine configuration, so `A0-ROUND-1`
    and `A0-ROUND-2` are both `pending` in `docs/research/a0/a0_delivery_index`.
    There is no real frozen public research asset to delete and recover here.
    This test therefore proves the *contract* on #437-shaped synthetic
    fixtures, and says so; it is not evidence that A0-H02's real-asset
    requirement is met.
    """

    store, paginated, _projection = _store(tmp_path / "workspace")
    deleted = discard_projections(store)
    outcome = recover_end_to_end(store.root, _request())
    assert outcome.status == "recovered"
    assert outcome.context_identity == paginated.identity
    assert len(deleted) == len(DISCARDABLE_OBJECTS) + 1
    # Zero new backtest, LLM call or budget reservation, from the seam itself.
    assert outcome.readback()["new_backtests"] == 0
    assert outcome.readback()["model_invocations"] == 0
    assert outcome.readback()["budget_reservations"] == 0


def test_a0_h02_the_real_asset_slice_is_pending_and_never_mocked() -> None:
    """The delivery index still says `pending`; nothing here overrides it."""

    index = Path(__file__).resolve().parents[2] / "docs/research/a0/a0_delivery_index.json"
    if not index.exists():  # pragma: no cover - /docs is git-ignored in this repo
        pytest.skip("the A0 delivery index is not present in this checkout")
    register = json.loads(index.read_text("utf-8"))["artifacts"]
    artifacts = {item["id"]: item["status"] for item in register}
    assert artifacts["A0-ROUND-1"] == "pending"
    assert artifacts["A0-ROUND-2"] == "pending"
    assert artifacts["A0-FIXTURES-ORACLE"] == "pending"


def test_a0_p02_process_interruption_lost_receipt_and_duplicate_on_the_delivery_boundary(
    tmp_path: Path,
) -> None:
    """A0-P02, all three, on a real file at the A0 delivery boundary."""

    store, paginated, _projection = _store(tmp_path / "workspace", delivered=False)
    journal = store.preserved / "exposure.jsonl"
    identity = paginated.context.identity

    # 1. Process interruption: a torn tail, written as a torn tail.
    with journal.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write('{"schema":"quant-research.research-exposure-event.v1","event')
    interrupted = recover_end_to_end(store.root, _request())
    assert interrupted.context_exposure == "uncertain"

    # 2. Lost receipt: recorded conservatively, reconciled, never resent blind.
    rebuilt = ExposureLog()
    rebuilt.append(_event("context_prepared", context_identity=identity))
    rebuilt.append(
        _event(
            "delivery_uncertain",
            context_identity=identity,
            uncertainty=_uncertainty(reason="receipt_lost"),
        )
    )
    _rewrite(journal, rebuilt.export())
    lost = recover_end_to_end(store.root, _request())
    assert lost.reconciliation is not None
    assert lost.reconciliation.uncertain_actions != ()
    assert lost.reconciliation.resend_allowed is False

    # 3. Duplicate event: recovered, not re-applied.
    log = ExposureLog.load(journal)
    key = log.action_keys[0]
    before = log.readback(key)
    log.append(
        _event(
            "delivery_uncertain",
            context_identity=identity,
            uncertainty=_uncertainty(reason="receipt_lost"),
        )
    )
    assert log.readback(key) == before

    # And the digest-only record still supports a limited replay at most.
    assert lost.replay is not None
    assert lost.replay.reconstruction == "limited"


def test_a0_the_injected_records_stay_inside_the_test_scope(tmp_path: Path) -> None:
    """Manual correction / revocation / failure injection touches no real asset."""

    store, _paginated, _projection = _store(tmp_path / "workspace")
    assert str(store.root).startswith(str(tmp_path))
    repository = Path(__file__).resolve().parents[2]
    assert not str(store.root).startswith(str(repository))
    (store.preserved / "paginated_context.json").unlink()
    assert recover_end_to_end(store.root, _request()).status == "facts_missing"
    # No file inside the repository changed: the whole store lives in tmp_path.
    assert list(tmp_path.iterdir()) == [store.root]


def _append(path: Path, event: dict[str, object]) -> None:
    """Append one event through the real log, so the journal stays canonical."""

    log = ExposureLog.load(path)
    log.append(event)
    _rewrite(path, log.export())


def _rewrite(path: Path, events: list[dict[str, object]]) -> None:
    path.write_bytes(
        b"".join(
            json.dumps(event, sort_keys=True, separators=(",", ":")).encode() + b"\n"
            for event in events
        )
    )
