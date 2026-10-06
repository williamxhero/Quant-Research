"""Focused tests for the Dossier v2 release and offline rebuild gate."""

from __future__ import annotations

import copy
import zipfile
from io import BytesIO

import pytest

from manager_gui.reader.dossier import DossierReportBuilder
from manager_gui.reader.dossier_release import DossierReleaseGate

from .test_dossier import Provider, _fixture


def _model():
    records, refs = _fixture()
    return DossierReportBuilder(Provider(records)).build(refs)


class _RuntimeMustNotBeCalled:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def submit(self, *_: object, **__: object) -> None:
        raise AssertionError("rebuild must never submit to Runtime")


def test_rebuild_is_unpublished_deterministic_and_read_only() -> None:
    model = _model()
    old_records = {"old-source": b"source bytes", "old-matrix": {"version": 1}}
    old_publications = {"old-report": b"published report bytes"}
    old_records_before = copy.deepcopy(old_records)
    old_publications_before = copy.deepcopy(old_publications)
    runtime = _RuntimeMustNotBeCalled()

    result = DossierReleaseGate(runtime=runtime).rebuild(
        model,
        old_records=old_records,
        old_publications=old_publications,
    )

    assert result.published is False
    assert result.package.published is False
    assert result.deterministic
    assert result.zero_runtime_calls
    assert result.verification.passed
    assert result.verification.old_readback_byte_identical
    assert runtime.calls == []
    assert old_records == old_records_before
    assert old_publications == old_publications_before
    assert result.source_publication_id == result.package.source_publication_id
    assert result.artifact_id == result.package.artifact_id
    assert len(result.archive_sha256) == 64


def test_release_readback_contains_formal_hashes_and_immutable_archive() -> None:
    package = DossierReleaseGate().release(_model())

    assert package.published
    assert package.source_publication_id == package.source.payload_sha256
    assert package.artifact_id == package.artifact.sha256
    assert package.archive_sha256
    with zipfile.ZipFile(BytesIO(package.archive_bytes)) as archive:
        assert archive.namelist() == ["dossier-model.json", "dossier.html", "manifest.json"]
        assert archive.read("dossier-model.json") == package.model_bytes
        assert archive.read("dossier.html") == package.html_bytes
    assert DossierReleaseGate().verify(package, _model()).passed


def test_tampered_artifact_and_old_snapshot_fail_closed() -> None:
    gate = DossierReleaseGate()
    package = gate.release(_model())
    tampered = gate.inspect(
        package,
        artifact_readback=package.html_bytes + b"tampered",
        old_records_byte_identical=False,
    )

    assert not tampered
    assert not tampered.artifact_bytes_identical
    assert not tampered.old_records_byte_identical
    assert any("byte-identical" in error or "changed" in error for error in tampered.errors)

    with pytest.raises(TypeError):
        gate.verify(object())  # type: ignore[arg-type]
