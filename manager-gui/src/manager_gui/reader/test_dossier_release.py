"""Adversarial contract tests for the Dossier v2 release gate."""

from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from dataclasses import replace
from io import BytesIO

import pytest

from manager_gui.reader.dossier import DossierReport, DossierReportBuilder, DossierValue
from manager_gui.reader.dossier_release import (
    DOSSIER_HTML_NAME,
    DOSSIER_MODEL_NAME,
    DossierReleaseError,
    DossierReleaseGate,
)
from manager_gui.reader.dossier_renderer import DossierHTMLRenderer

from .test_dossier import Provider, _fixture


def _model() -> DossierReport:
    records, refs = _fixture()
    return DossierReportBuilder(Provider(records)).build(refs)


def _model_with_quarantine_proof() -> DossierReport:
    """Add an owner fact proving that a quarantine entry is excluded."""

    report = _model()
    quarantine = next(section for section in report.sections if section.name == "quarantine")
    evidence = quarantine.evidence[0]
    fact = DossierValue(
        path="/entries/0/included",
        value=False,
        status="evaluated",
        derivation="presentation-derived",
        derivation_reason="copied from the quarantine owner record",
        sources=(
            {
                "record": evidence.source.to_dict(),
                "selector": "/entries/0/included",
                "artifact": None,
            },
        ),
    )
    updated_evidence = replace(
        evidence, facts=tuple(sorted((*evidence.facts, fact), key=lambda item: item.path))
    )
    updated_quarantine = replace(quarantine, evidence=(updated_evidence,))
    sections = tuple(
        updated_quarantine if section.name == "quarantine" else section
        for section in report.sections
    )
    return replace(report, sections=sections)


class _Reader:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.calls: list[str] = []

    def read_publication(self, publication_id: str) -> bytes:
        self.calls.append(publication_id)
        return self.values[publication_id]


class _MutatingReader(_Reader):
    def __init__(self, mutate_id: str) -> None:
        super().__init__()
        self.mutate_id = mutate_id
        self.reads = 0

    def read_publication(self, publication_id: str) -> bytes:
        self.reads += 1
        value = super().read_publication(publication_id)
        if self.reads == 12:
            self.values[self.mutate_id] = b"changed after baseline snapshot"
        return value


class _RuntimeSpy:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def submit(self, *_args: object, **_kwargs: object) -> None:
        self.calls.append("submit")
        raise AssertionError("the release gate must not submit to Runtime")


def _ids(model: DossierReport) -> tuple[str, ...]:
    return tuple(ref.record_id for ref in model.source_refs.records())


def _seed_reader(reader: _Reader, model: DossierReport, package: object) -> None:
    assert hasattr(package, "source_publication_id")
    assert hasattr(package, "artifact_id")
    assert hasattr(package, "archive_sha256")
    typed_package = package
    reader.values.update({record_id: b"old public record" for record_id in _ids(model)})
    reader.values["a" * 64] = b"old publication"
    reader.values[typed_package.source_publication_id] = typed_package.model_bytes  # type: ignore[attr-defined]
    reader.values[typed_package.artifact_id] = typed_package.html_bytes  # type: ignore[attr-defined]
    reader.values[typed_package.archive_sha256] = typed_package.archive_bytes  # type: ignore[attr-defined]


def test_prepare_is_unpublished_and_all_bytes_are_deterministic() -> None:
    model = _model()
    first = DossierReleaseGate().release(model)
    second = DossierReleaseGate().release(model)

    assert first.published is False
    assert first.source.published is False
    assert first.artifact.published is False
    assert first.readback() == second.readback()
    assert first.archive_sha256 == hashlib.sha256(first.archive_bytes).hexdigest()
    with zipfile.ZipFile(BytesIO(first.archive_bytes)) as archive:
        assert archive.namelist() == [DOSSIER_MODEL_NAME, DOSSIER_HTML_NAME, "manifest.json"]
        assert archive.read(DOSSIER_MODEL_NAME) == first.model_bytes
        assert archive.read(DOSSIER_HTML_NAME) == first.html_bytes
        manifest = json.loads(archive.read("manifest.json"))
        assert "archive_sha256" not in manifest
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
        assert all(
            info.create_system == 0 and info.external_attr == 0o600 << 16
            for info in archive.infolist()
        )


def test_inspect_never_uses_package_self_readback_as_public_proof() -> None:
    model = _model()
    package = DossierReleaseGate().release(model)

    inspection = DossierReleaseGate().verify(package, model)

    assert not inspection
    assert inspection.external_readback_verified is False
    assert any(
        "self-readback" in error or "public readback" in error for error in inspection.errors
    )
    assert package.published is False


def test_rebuild_is_twice_deterministic_and_has_structural_zero_runtime_calls() -> None:
    model = _model()
    runtime = _RuntimeSpy()
    before = copy.deepcopy(model.to_dict())

    result = DossierReleaseGate(runtime=runtime).rebuild(model)

    assert result.published is False
    assert result.package.published is False
    assert result.deterministic is True
    assert result.runtime_submission_calls == 0
    assert result.zero_runtime_calls is True
    assert runtime.calls == []
    assert model.to_dict() == before
    assert not result.verification  # no caller public reader means no proof


def test_external_readback_can_mark_published_only_with_exact_ids_and_boundaries() -> None:
    model = _model_with_quarantine_proof()
    gate = DossierReleaseGate()
    package = gate.release(model)
    reader = _Reader()
    _seed_reader(reader, model, package)

    published = gate.publish(
        package,
        public_reader=reader,
        baseline_refs=model.source_refs,
        current_root_ids=_ids(model),
        old_publication_ids=("a" * 64,),
    )

    assert published.published is True
    assert published.source.published is True
    assert published.artifact.published is True
    assert published.publication_proof is not None
    assert published.publication_proof.archive_sha256 == published.archive_sha256


def test_rebuild_verifies_external_bytes_without_publishing_or_runtime_calls() -> None:
    model = _model_with_quarantine_proof()
    gate = DossierReleaseGate()
    package = gate.release(model)
    reader = _Reader()
    _seed_reader(reader, model, package)

    result = gate.rebuild(
        model,
        public_reader=reader,
        baseline_refs=model.source_refs,
        current_root_ids=_ids(model),
        old_publication_ids=("a" * 64,),
    )

    assert result.published is False
    assert result.package.published is False
    assert result.deterministic is True
    assert result.zero_runtime_calls is True
    assert result.verification.passed
    assert result.verification.published is False
    assert result.verification.external_readback_verified is True
    assert result.old_records_byte_identical is True
    assert result.old_publications_byte_identical is True


def test_mutated_old_or_current_readback_fails_closed() -> None:
    model = _model_with_quarantine_proof()
    gate = DossierReleaseGate()
    package = gate.release(model)
    reader = _MutatingReader(_ids(model)[0])
    _seed_reader(reader, model, package)

    with pytest.raises(DossierReleaseError, match="readback proof failed closed"):
        gate.publish(
            package,
            public_reader=reader,
            baseline_refs=model.source_refs,
            current_root_ids=_ids(model),
            old_publication_ids=("a" * 64,),
        )


def test_tampered_source_html_and_archive_are_reported_without_throwing() -> None:
    gate = DossierReleaseGate()
    package = gate.release(_model())

    source = gate.inspect(package, source_readback=b"not JSON")
    html = gate.inspect(package, artifact_readback=b"\xff")
    archive = gate.inspect(package, archive_readback=b"not a zip")

    assert not source and any("source" in error for error in source.errors)
    assert not html and any("HTML" in error for error in html.errors)
    assert not archive and any("archive" in error.lower() for error in archive.errors)


def test_invalid_renderer_version_and_missing_explicit_old_ids_fail_closed() -> None:
    with pytest.raises(DossierReleaseError, match="renderer version"):
        DossierReleaseGate(renderer=DossierHTMLRenderer("wrong-version"))

    model = _model()
    with pytest.raises(DossierReleaseError, match="old_publication_ids"):
        DossierReleaseGate().publish(
            DossierReleaseGate().release(model),
            public_reader=_Reader(),
            baseline_refs=model.source_refs,
            current_root_ids=_ids(model),
        )


def test_release_does_not_accept_mapping_self_snapshots_as_proof() -> None:
    with pytest.raises(DossierReleaseError, match="does not prove old readback"):
        DossierReleaseGate().release(_model(), old_records={"a" * 64: b"before"})
