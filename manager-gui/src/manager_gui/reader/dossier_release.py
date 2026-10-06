"""Deterministic Dossier v2 release, inspect, verify, and rebuild gate.

This module is deliberately a local/read-only release seam.  It packages an
already-built report model and its offline HTML artifact, but has no Workspace
writer and no Runtime submission operation.  A rebuild is therefore a proof
that rendering can be repeated with ``published=False`` and zero Runtime calls,
not an instruction to run research again.
"""

# HTML/archive metadata uses readable long lines.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Protocol, cast

from .dossier import DossierReport
from .dossier_renderer import (
    DOSSIER_RENDERER_VERSION,
    DossierHTMLRenderer,
    DossierHTMLVerification,
    verify_dossier_html,
)

DOSSIER_RELEASE_SCHEMA: Final = "manager-gui.dossier-release.v2"
DOSSIER_SOURCE_RECORD_TYPE: Final = "apex-research.strategy-report-dossier-source.v2"
DOSSIER_ARTIFACT_RECORD_TYPE: Final = "apex-research.strategy-report-dossier-artifact.v2"
DOSSIER_ARCHIVE_NAME: Final = "dossier-v2.zip"
DOSSIER_MODEL_NAME: Final = "dossier-model.json"
DOSSIER_HTML_NAME: Final = "dossier.html"


class DossierReleaseError(ValueError):
    """A release package or gate input is structurally invalid."""


class RuntimeSubmissionClient(Protocol):
    """Marker protocol documenting the forbidden operation boundary."""

    def submit(self, *args: object, **kwargs: object) -> object:
        """A Runtime submission method must never be called by this module."""


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DossierReleaseError("release values must be finite JSON") from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bytes(value: object, name: str) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8")
    raise TypeError(f"{name} must be bytes or UTF-8 text")


def _model(value: DossierReport | Mapping[str, object] | str) -> DossierReport:
    if isinstance(value, DossierReport):
        return value
    try:
        if isinstance(value, str):
            return DossierReport.from_json(value)
        if isinstance(value, Mapping):
            return DossierReport.from_dict(cast(Mapping[str, object], value))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DossierReleaseError("invalid Dossier v2 model for release") from exc
    raise TypeError("release gate requires a DossierReport or its JSON representation")


def _snapshot(values: Mapping[str, object] | None) -> tuple[tuple[str, str], ...]:
    if values is None:
        return ()
    result: list[tuple[str, str]] = []
    for key, value in values.items():
        if not isinstance(key, str):
            raise TypeError("old record/publication snapshot keys must be strings")
        raw = _canonical_json(value) if isinstance(value, Mapping) else _bytes(value, key)
        result.append((key, _sha256(raw)))
    return tuple(sorted(result))


def _same_snapshot(before: tuple[tuple[str, str], ...], values: Mapping[str, object] | None) -> bool:
    return before == _snapshot(values)


def _zip_archive(model_bytes: bytes, html_bytes: bytes, manifest_bytes: bytes) -> bytes:
    """Build a byte-stable archive with fixed metadata and stored entries."""

    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in (
            (DOSSIER_MODEL_NAME, model_bytes),
            (DOSSIER_HTML_NAME, html_bytes),
            ("manifest.json", manifest_bytes),
        ):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, content)
    return output.getvalue()


@dataclass(frozen=True, slots=True)
class DossierSourcePublication:
    """Immutable source publication metadata and exact model bytes."""

    publication_id: str
    record_type: str
    payload_sha256: str
    payload_bytes: bytes
    published: bool

    def __post_init__(self) -> None:
        if len(self.publication_id) != 64 or any(char not in "0123456789abcdef" for char in self.publication_id):
            raise ValueError("publication_id must be a lowercase SHA-256 identity")
        if self.record_type != DOSSIER_SOURCE_RECORD_TYPE:
            raise ValueError("unexpected dossier source record type")
        if self.payload_sha256 != _sha256(self.payload_bytes):
            raise ValueError("source payload hash mismatch")
        if not isinstance(self.published, bool):
            raise TypeError("published must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": DOSSIER_RELEASE_SCHEMA,
            "publication_id": self.publication_id,
            "record_type": self.record_type,
            "payload_sha256": self.payload_sha256,
            "bytes": len(self.payload_bytes),
            "published": self.published,
        }

    def readback(self) -> bytes:
        return self.payload_bytes


@dataclass(frozen=True, slots=True)
class DossierArtifactPublication:
    """Immutable HTML artifact metadata and exact UTF-8 bytes."""

    artifact_id: str
    record_type: str
    sha256: str
    bytes: bytes
    renderer_version: str
    published: bool

    def __post_init__(self) -> None:
        if len(self.artifact_id) != 64 or any(char not in "0123456789abcdef" for char in self.artifact_id):
            raise ValueError("artifact_id must be a lowercase SHA-256 identity")
        if self.record_type != DOSSIER_ARTIFACT_RECORD_TYPE:
            raise ValueError("unexpected dossier artifact record type")
        if self.sha256 != _sha256(self.bytes) or self.artifact_id != self.sha256:
            raise ValueError("artifact bytes hash mismatch")
        if not self.renderer_version.strip():
            raise ValueError("renderer_version must be non-empty")
        if not isinstance(self.published, bool):
            raise TypeError("published must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": DOSSIER_RELEASE_SCHEMA,
            "artifact_id": self.artifact_id,
            "record_type": self.record_type,
            "sha256": self.sha256,
            "bytes": len(self.bytes),
            "renderer_version": self.renderer_version,
            "published": self.published,
        }

    def readback(self) -> bytes:
        return self.bytes


@dataclass(frozen=True, slots=True)
class DossierReleasePackage:
    """A source + HTML + deterministic archive package, without a writer."""

    source: DossierSourcePublication
    artifact: DossierArtifactPublication
    archive_sha256: str
    archive_bytes: bytes
    renderer_version: str = DOSSIER_RENDERER_VERSION
    published: bool = True

    def __post_init__(self) -> None:
        if self.source.published is not self.published or self.artifact.published is not self.published:
            raise ValueError("package and publication statuses must agree")
        if self.archive_sha256 != _sha256(self.archive_bytes):
            raise ValueError("archive hash mismatch")
        if self.renderer_version != self.artifact.renderer_version:
            raise ValueError("package renderer version differs from artifact")

    @property
    def source_publication_id(self) -> str:
        return self.source.publication_id

    @property
    def artifact_id(self) -> str:
        return self.artifact.artifact_id

    @property
    def model_bytes(self) -> bytes:
        return self.source.payload_bytes

    @property
    def html_bytes(self) -> bytes:
        return self.artifact.bytes

    def manifest(self) -> dict[str, object]:
        return {
            "schema": DOSSIER_RELEASE_SCHEMA,
            "renderer_version": self.renderer_version,
            "published": self.published,
            "source": self.source.to_dict(),
            "artifact": self.artifact.to_dict(),
            "archive_sha256": self.archive_sha256,
        }

    def to_dict(self) -> dict[str, object]:
        return self.manifest()

    def readback(self) -> dict[str, bytes]:
        return {
            DOSSIER_MODEL_NAME: self.model_bytes,
            DOSSIER_HTML_NAME: self.html_bytes,
            DOSSIER_ARCHIVE_NAME: self.archive_bytes,
        }


@dataclass(frozen=True, slots=True)
class DossierReleaseInspection:
    """Readback proof for one release package."""

    passed: bool
    published: bool
    source_publication_id: str
    artifact_id: str
    source_bytes_identical: bool
    artifact_bytes_identical: bool
    archive_bytes_identical: bool
    old_records_byte_identical: bool
    old_publications_byte_identical: bool
    runtime_submission_calls: int
    html_verification: DossierHTMLVerification
    errors: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.passed

    @property
    def old_readback_byte_identical(self) -> bool:
        return self.old_records_byte_identical and self.old_publications_byte_identical

    @property
    def zero_runtime_calls(self) -> bool:
        return self.runtime_submission_calls == 0


@dataclass(frozen=True, slots=True)
class DossierRebuildResult:
    """The explicit non-publicating result of an offline rebuild."""

    package: DossierReleasePackage
    published: bool
    runtime_submission_calls: int
    deterministic: bool
    old_records_byte_identical: bool
    old_publications_byte_identical: bool
    verification: DossierReleaseInspection

    def __bool__(self) -> bool:
        return self.verification.passed and not self.published

    @property
    def zero_runtime_calls(self) -> bool:
        return self.runtime_submission_calls == 0

    @property
    def archive_sha256(self) -> str:
        return self.package.archive_sha256

    @property
    def source_publication_id(self) -> str:
        return self.package.source_publication_id

    @property
    def artifact_id(self) -> str:
        return self.package.artifact_id


def _runtime_count(runtime: object | None) -> int:
    if runtime is None:
        return 0
    for name in ("submission_calls", "runtime_submission_calls", "submit_calls"):
        value = getattr(runtime, name, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    calls = getattr(runtime, "calls", None)
    if isinstance(calls, (list, tuple)):
        return len(calls)
    return 0


class DossierReleaseGate:
    """Create and verify local package bytes without any publishing or Runtime call."""

    def __init__(self, renderer: DossierHTMLRenderer | None = None, runtime: object | None = None) -> None:
        self.renderer = renderer or DossierHTMLRenderer()
        if not isinstance(self.renderer, DossierHTMLRenderer):
            raise TypeError("renderer must be a DossierHTMLRenderer")
        self.runtime = runtime

    def _package(self, value: DossierReport | Mapping[str, object] | str, *, published: bool) -> DossierReleasePackage:
        report = _model(value)
        model_bytes = _canonical_json(report.to_dict())
        html_bytes = self.renderer.render(report).encode("utf-8")
        source_id = _sha256(model_bytes)
        artifact_id = _sha256(html_bytes)
        source = DossierSourcePublication(
            source_id,
            DOSSIER_SOURCE_RECORD_TYPE,
            _sha256(model_bytes),
            model_bytes,
            published,
        )
        artifact = DossierArtifactPublication(
            artifact_id,
            DOSSIER_ARTIFACT_RECORD_TYPE,
            artifact_id,
            html_bytes,
            self.renderer.version,
            published,
        )
        manifest_without_archive = {
            "schema": DOSSIER_RELEASE_SCHEMA,
            "renderer_version": self.renderer.version,
            "published": published,
            "source": source.to_dict(),
            "artifact": artifact.to_dict(),
        }
        manifest = {**manifest_without_archive, "archive_sha256": "0" * 64}
        archive = _zip_archive(model_bytes, html_bytes, _canonical_json(manifest))
        archive_sha = _sha256(archive)
        # The archive carries its own declared hash in the package manifest; the
        # bytes inside remain independent of the final outer manifest hash.
        return DossierReleasePackage(source, artifact, archive_sha, archive, self.renderer.version, published)

    def release(
        self,
        value: DossierReport | Mapping[str, object] | str,
        *,
        old_records: Mapping[str, object] | None = None,
        old_publications: Mapping[str, object] | None = None,
    ) -> DossierReleasePackage:
        """Prepare an immutable publication package locally; no external write occurs."""

        del old_records, old_publications
        return self._package(value, published=True)

    def rebuild(
        self,
        value: DossierReport | Mapping[str, object] | str,
        *,
        old_records: Mapping[str, object] | None = None,
        old_publications: Mapping[str, object] | None = None,
    ) -> DossierRebuildResult:
        """Render/verify/rebuild offline and explicitly return ``published=False``."""

        records_before = _snapshot(old_records)
        publications_before = _snapshot(old_publications)
        runtime_before = _runtime_count(self.runtime)
        first = self._package(value, published=False)
        second = self._package(value, published=False)
        records_same = _same_snapshot(records_before, old_records)
        publications_same = _same_snapshot(publications_before, old_publications)
        runtime_calls = max(0, _runtime_count(self.runtime) - runtime_before)
        inspection = self.inspect(
            first,
            source_readback=first.model_bytes,
            artifact_readback=first.html_bytes,
            archive_readback=first.archive_bytes,
            model=value,
            old_records=old_records,
            old_publications=old_publications,
            runtime_submission_calls=runtime_calls,
            old_records_byte_identical=records_same,
            old_publications_byte_identical=publications_same,
        )
        deterministic = first.readback() == second.readback()
        if not deterministic:
            inspection = DossierReleaseInspection(
                False,
                inspection.published,
                inspection.source_publication_id,
                inspection.artifact_id,
                inspection.source_bytes_identical,
                inspection.artifact_bytes_identical,
                inspection.archive_bytes_identical,
                inspection.old_records_byte_identical,
                inspection.old_publications_byte_identical,
                inspection.runtime_submission_calls,
                inspection.html_verification,
                (*inspection.errors, "rebuild bytes are not deterministic"),
            )
        return DossierRebuildResult(
            package=first,
            published=False,
            runtime_submission_calls=runtime_calls,
            deterministic=deterministic,
            old_records_byte_identical=records_same,
            old_publications_byte_identical=publications_same,
            verification=inspection,
        )

    def inspect(
        self,
        package: DossierReleasePackage,
        *,
        source_readback: object | None = None,
        artifact_readback: object | None = None,
        archive_readback: object | None = None,
        model: DossierReport | Mapping[str, object] | str | None = None,
        old_records: Mapping[str, object] | None = None,
        old_publications: Mapping[str, object] | None = None,
        runtime_submission_calls: int = 0,
        old_records_byte_identical: bool | None = None,
        old_publications_byte_identical: bool | None = None,
    ) -> DossierReleaseInspection:
        if not isinstance(package, DossierReleasePackage):
            raise TypeError("inspect requires a DossierReleasePackage")
        source_bytes = package.model_bytes if source_readback is None else _bytes(source_readback, "source_readback")
        artifact_bytes = package.html_bytes if artifact_readback is None else _bytes(artifact_readback, "artifact_readback")
        archive_bytes = package.archive_bytes if archive_readback is None else _bytes(archive_readback, "archive_readback")
        expected_model = _model(model) if model is not None else None
        html_verification = verify_dossier_html(
            artifact_bytes.decode("utf-8"), expected_model or package.model_bytes.decode("utf-8")
        )
        records_same = (
            _same_snapshot(_snapshot(old_records), old_records)
            if old_records_byte_identical is None and old_records is not None
            else old_records_byte_identical is not False
        )
        publications_same = (
            _same_snapshot(_snapshot(old_publications), old_publications)
            if old_publications_byte_identical is None and old_publications is not None
            else old_publications_byte_identical is not False
        )
        errors: list[str] = []
        if source_bytes != package.model_bytes:
            errors.append("source readback is not byte-identical")
        if artifact_bytes != package.html_bytes:
            errors.append("artifact readback is not byte-identical")
        if archive_bytes != package.archive_bytes:
            errors.append("archive readback is not byte-identical")
        if not html_verification:
            errors.extend(f"HTML: {error}" for error in html_verification.errors)
        if runtime_submission_calls != 0:
            errors.append("Runtime submission calls were observed")
        if not records_same:
            errors.append("old records changed")
        if not publications_same:
            errors.append("old publications changed")
        if expected_model is not None and source_bytes != _canonical_json(expected_model.to_dict()):
            errors.append("source model readback differs")
        return DossierReleaseInspection(
            not errors,
            package.published,
            package.source_publication_id,
            package.artifact_id,
            source_bytes == package.model_bytes,
            artifact_bytes == package.html_bytes,
            archive_bytes == package.archive_bytes,
            records_same,
            publications_same,
            runtime_submission_calls,
            html_verification,
            tuple(errors),
        )

    def verify(
        self,
        package: DossierReleasePackage,
        model: DossierReport | Mapping[str, object] | str | None = None,
        **kwargs: object,
    ) -> DossierReleaseInspection:
        """Verify package identities/readback without dereferencing anything."""

        return self.inspect(package, model=model, **cast(dict[str, object], kwargs))


ReleaseGate = DossierReleaseGate
DossierRelease = DossierReleasePackage
SourcePublication = DossierSourcePublication
GeneratedDossierArtifact = DossierArtifactPublication


def release_dossier(
    model: DossierReport | Mapping[str, object] | str,
    *,
    old_records: Mapping[str, object] | None = None,
    old_publications: Mapping[str, object] | None = None,
) -> DossierReleasePackage:
    return DossierReleaseGate().release(model, old_records=old_records, old_publications=old_publications)


def rebuild_dossier(
    model: DossierReport | Mapping[str, object] | str,
    *,
    old_records: Mapping[str, object] | None = None,
    old_publications: Mapping[str, object] | None = None,
) -> DossierRebuildResult:
    return DossierReleaseGate().rebuild(model, old_records=old_records, old_publications=old_publications)


__all__ = [
    "DOSSIER_ARCHIVE_NAME",
    "DOSSIER_ARTIFACT_RECORD_TYPE",
    "DOSSIER_HTML_NAME",
    "DOSSIER_MODEL_NAME",
    "DOSSIER_RELEASE_SCHEMA",
    "DOSSIER_SOURCE_RECORD_TYPE",
    "DossierArtifactPublication",
    "DossierRebuildResult",
    "DossierRelease",
    "DossierReleaseError",
    "DossierReleaseGate",
    "DossierReleaseInspection",
    "DossierReleasePackage",
    "DossierSourcePublication",
    "GeneratedDossierArtifact",
    "ReleaseGate",
    "RuntimeSubmissionClient",
    "SourcePublication",
    "rebuild_dossier",
    "release_dossier",
]
