"""Focused tests for the immutable, read-only Dossier v2 projection."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import FrozenInstanceError

import pytest

from manager_gui.reader.dossier import (
    CONCLUSION_TYPE,
    CURRENT_DOSSIER_SOURCE_REFS,
    DOSSIER_SECTION_ORDER,
    FACTS_TYPE,
    MATRIX_TYPE,
    QUARANTINE_TYPE,
    SOURCE_TYPE,
    T2_TYPE,
    DossierArtifactRef,
    DossierReport,
    DossierReportBuilder,
    DossierSourceProvider,
    DossierSourceRefs,
    DossierValue,
)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _root(
    record_type: str, identity_field: str, payload: dict[str, object]
) -> tuple[str, dict[str, object]]:
    identity = dict(payload)
    identity.pop(identity_field, None)
    record_id = _sha(identity)
    payload[identity_field] = record_id
    return record_id, {
        "schema": "quant-research.publication.v1",
        "record_id": record_id,
        "record_type": record_type,
        "payload": payload,
        "artifacts": [],
        "lineage": [],
    }


def _fixture() -> tuple[dict[str, dict[str, object]], DossierSourceRefs]:
    runtime_id, runtime = _root(
        FACTS_TYPE,
        "facts_id",
        {"schema": FACTS_TYPE, "artifacts": []},
    )
    matrix_id, matrix = _root(
        MATRIX_TYPE,
        "matrix_id",
        {
            "schema": MATRIX_TYPE,
            "cells": [
                {
                    "cell_id": "cell-1",
                    "data_role": "development",
                    "score": 0.5,
                    "runtime_facts": {"record_id": runtime_id, "record_type": FACTS_TYPE},
                }
            ],
        },
    )
    t2_id, t2 = _root(
        T2_TYPE,
        "source_id",
        {
            "schema": T2_TYPE,
            "matrix": {"record_id": matrix_id, "record_type": MATRIX_TYPE},
            "cells": [],
        },
    )
    quarantine_id, quarantine = _root(
        QUARANTINE_TYPE,
        "quarantine_id",
        {"schema": QUARANTINE_TYPE, "entries": []},
    )
    source_id, source = _root(
        SOURCE_TYPE,
        "source_id",
        {
            "schema": SOURCE_TYPE,
            "constraints": {
                "current_matrix": matrix_id,
                "current_t2_source": t2_id,
                "quarantine": quarantine_id,
            },
            "conclusion": None,
        },
    )
    conclusion_id, conclusion = _root(
        CONCLUSION_TYPE,
        "conclusion_id",
        {
            "schema": CONCLUSION_TYPE,
            "evidence": [
                {"record_id": matrix_id, "record_type": MATRIX_TYPE},
                {"record_id": t2_id, "record_type": T2_TYPE},
                {"record_id": source_id, "record_type": SOURCE_TYPE},
                {"record_id": quarantine_id, "record_type": QUARANTINE_TYPE},
            ],
            "scope": {"data_roles": ["development", "validation"]},
        },
    )
    refs = DossierSourceRefs(
        matrix={"record_id": matrix_id, "record_type": MATRIX_TYPE},
        t2={"record_id": t2_id, "record_type": T2_TYPE},
        report_source={"record_id": source_id, "record_type": SOURCE_TYPE},
        quarantine={"record_id": quarantine_id, "record_type": QUARANTINE_TYPE},
        conclusion={"record_id": conclusion_id, "record_type": CONCLUSION_TYPE},
    )
    return {
        record["record_id"]: record
        for record in (matrix, t2, source, quarantine, conclusion, runtime)
    }, refs


class Provider:
    def __init__(self, records: dict[str, dict[str, object]]) -> None:
        self.records = copy.deepcopy(records)
        self.calls: list[tuple[str, str]] = []
        self.artifacts: dict[str, bytes] = {}

    def get_record(self, record_id: str) -> Mapping[str, object] | None:
        self.calls.append(("record", record_id))
        return copy.deepcopy(self.records.get(record_id))

    def verify_artifact(self, ref: Mapping[str, object]) -> Mapping[str, object]:
        self.calls.append(("verify", str(ref["uri"])))
        return {"verified": True, "artifact": dict(ref)}

    def read_artifact(self, uri: str) -> bytes:
        self.calls.append(("artifact", uri))
        return self.artifacts[uri]

    def list_records(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("dossier must not discover records")

    def latest(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("dossier must not select latest records")

    def get_run(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("dossier must not read Runtime runs")

    def get_result(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("dossier must not read Runtime results")

    def publish(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("dossier must not publish")


def test_protocol_has_only_read_record_and_artifact_operations() -> None:
    assert set(DossierSourceProvider.__dict__) >= {
        "get_record",
        "verify_artifact",
        "read_artifact",
    }
    assert not {
        "list_records",
        "latest",
        "get_run",
        "get_result",
        "publish",
    } & set(DossierSourceProvider.__dict__)


def test_build_is_deterministic_round_trippable_immutable_and_read_only() -> None:
    records, refs = _fixture()
    provider = Provider(records)
    before = copy.deepcopy(provider.records)
    first = DossierReportBuilder(provider).build(refs)
    second = DossierReportBuilder(provider).build(refs)

    assert first.to_json() == second.to_json()
    assert DossierReport.from_json(first.to_json()) == first
    assert tuple(section.name for section in first.sections) == DOSSIER_SECTION_ORDER
    assert provider.records == before
    assert all(operation == "record" for operation, _ in provider.calls)
    with pytest.raises(FrozenInstanceError):
        first.title = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        first.sections[0].evidence = ()  # type: ignore[misc]


def test_numeric_values_retain_path_status_derivation_and_source() -> None:
    records, refs = _fixture()
    model = DossierReportBuilder(Provider(records)).build(refs)
    values = [
        value
        for section in model.sections
        for evidence in section.evidence
        for value in evidence.facts
    ]
    score = next(value for value in values if value.path.endswith("/score"))
    assert score.value == 0.5
    assert score.status == "evaluated"
    assert score.derivation == "presentation-derived"
    assert score.sources[0].record.record_id == refs.matrix.record_id
    assert score.sources[0].selector.endswith("/score")


def test_unavailable_and_corrupt_artifacts_fail_closed() -> None:
    records, refs = _fixture()
    artifact_bytes = b'{"schema":"quant-runtime.nautilus-reporting-input.v1","stats":{"x":1}}'
    artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()
    artifact = {
        "schema": "quant-research.artifact-ref.v1",
        "uri": f"workspace-artifact://sha256/{artifact_sha}",
        "sha256": artifact_sha,
        "bytes": len(artifact_bytes),
        "media_type": "application/json",
        "record_schema": "quant-runtime.nautilus-reporting-input.v1",
        "logical_role": "native-statistics",
        "name": "run/native_statistics.json",
    }
    runtime_id = next(
        record_id for record_id, record in records.items() if record["record_type"] == FACTS_TYPE
    )
    records[runtime_id]["payload"]["artifacts"] = [artifact]
    provider = Provider(records)
    provider.artifacts[artifact["uri"]] = b"corrupt"
    model = DossierReportBuilder(provider).build(refs)
    values = [
        value
        for section in model.sections
        for evidence in section.evidence
        for value in evidence.facts
    ]
    assert any(value.status == "not_evaluated" for value in values)
    assert not any(value.derivation == "Runtime-native" for value in values)


def test_invalid_reference_prefix_and_unavailable_value_are_rejected() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        DossierSourceRefs(
            matrix={"record_id": "short", "record_type": MATRIX_TYPE},
            t2=CURRENT_DOSSIER_SOURCE_REFS.t2,
            report_source=CURRENT_DOSSIER_SOURCE_REFS.report_source,
            quarantine=CURRENT_DOSSIER_SOURCE_REFS.quarantine,
            conclusion=CURRENT_DOSSIER_SOURCE_REFS.conclusion,
        )
    with pytest.raises(ValueError, match="artifact URI"):
        DossierArtifactRef(uri="file:///tmp/x", sha256="0" * 64, name="x")
    with pytest.raises(ValueError, match="not_evaluated"):
        DossierValue(
            path="/metric",
            value=1,
            status="not_evaluated",
            derivation="not_evaluated",
            derivation_reason="missing",
            sources=(
                {
                    "record": CURRENT_DOSSIER_SOURCE_REFS.matrix.to_dict(),
                    "selector": "/metric",
                    "artifact": None,
                },
            ),
            reason="missing",
        )
