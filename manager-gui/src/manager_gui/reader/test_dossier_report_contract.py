"""Regression checks for the V1.2-REPORT additions over the merged Dossier core."""

from __future__ import annotations

import json
from pathlib import Path

from manager_gui.reader.dossier import (
    CURRENT_DOSSIER_SOURCE_REFS,
    LOCK_TYPE,
    PROOF_TYPE,
    DossierRecordRef,
    DossierReportBuilder,
    DossierSourceRefs,
)
from manager_gui.reader.dossier_cli import main as dossier_main
from manager_gui.reader.dossier_release import DossierReleaseGate
from manager_gui.reader.dossier_schema import DOSSIER_REPORT_JSON_SCHEMA

from .test_dossier import Provider, _fixture, _root


def _holdout_model():
    records, refs = _fixture()
    lock_id, lock = _root(
        LOCK_TYPE,
        "record_id",
        {"schema": LOCK_TYPE, "status": "locked", "results": "not_accessed"},
    )
    proof_id, proof = _root(
        PROOF_TYPE,
        "record_id",
        {"schema": PROOF_TYPE, "status": "not_accessed", "holdout_results": "not_evaluated"},
    )
    records.update({lock_id: lock, proof_id: proof})
    refs = DossierSourceRefs(
        refs.matrix,
        refs.t2,
        refs.report_source,
        refs.quarantine,
        refs.conclusion,
        DossierRecordRef(lock_id, LOCK_TYPE),
        DossierRecordRef(proof_id, PROOF_TYPE),
    )
    return DossierReportBuilder(Provider(records)).build(refs)


def test_current_source_refs_bind_exact_primary_holdout_records() -> None:
    assert CURRENT_DOSSIER_SOURCE_REFS.has_holdout_boundary
    assert CURRENT_DOSSIER_SOURCE_REFS.holdout_lock is not None
    assert CURRENT_DOSSIER_SOURCE_REFS.holdout_proof is not None
    assert CURRENT_DOSSIER_SOURCE_REFS.holdout_lock.record_type == LOCK_TYPE
    assert CURRENT_DOSSIER_SOURCE_REFS.holdout_proof.record_type == PROOF_TYPE
    assert len(CURRENT_DOSSIER_SOURCE_REFS.records()) == 7


def test_holdout_state_round_trips_and_direct_metrics_stay_unavailable() -> None:
    model = _holdout_model()
    restored = type(model).from_json(model.to_json())

    assert restored == model
    holdout = next(section for section in model.sections if section.name == "holdout_lock")
    assert holdout.status == "evaluated"
    assert any(
        fact.status == "evaluated" and str(fact.value) in {"locked", "not_accessed"}
        for evidence in holdout.evidence
        for fact in evidence.facts
    )


def test_release_inspection_preserves_nonzero_runtime_count() -> None:
    model = _holdout_model()
    package = DossierReleaseGate().release(model)
    result = DossierReleaseGate().inspect(package, model=model, runtime_submission_calls=3)

    assert result.runtime_submission_calls == 3
    assert not result.passed
    assert any("Runtime" in error for error in result.errors)


def test_report_schema_and_cli_are_available_without_external_dependencies(
    tmp_path: Path, capsys
) -> None:
    model = _holdout_model()
    model_path = tmp_path / "model.json"
    model_path.write_text(model.to_json(), encoding="utf-8")

    assert DOSSIER_REPORT_JSON_SCHEMA["$id"] == "urn:manager-gui:dossier-report:v2"
    source_refs_schema = DOSSIER_REPORT_JSON_SCHEMA["properties"]["source_refs"]
    assert "holdout_lock" in source_refs_schema["anyOf"][0]["required"]  # type: ignore[index]

    exit_code = dossier_main(["rebuild", "--model", str(model_path)])
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["published"] is False
    assert output["runtime_submission_calls"] == 0
    assert output["verification"]["published"] is False


def test_missing_holdout_pair_is_rejected() -> None:
    _, refs = _fixture()
    try:
        DossierSourceRefs(
            refs.matrix,
            refs.t2,
            refs.report_source,
            refs.quarantine,
            refs.conclusion,
            DossierRecordRef("0" * 64, LOCK_TYPE),
        )
    except ValueError as exc:
        assert "together" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("a Holdout lock without its access proof must fail closed")
