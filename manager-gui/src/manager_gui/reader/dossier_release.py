"""Fail-closed deterministic preparation and public-readback gate for Dossier v2.

The gate has no Workspace or Runtime writer.  ``release`` only prepares local bytes and
always returns ``published=False``.  ``publish`` can mark a package published only when an
explicit public readback provider returns the exact source, HTML, and archive bytes, and
when the caller's explicitly named old/current records are unchanged around the work.
"""

from __future__ import annotations

# Release metadata and HTML/archive checks use readable long lines.
# ruff: noqa: E501
import builtins
import hashlib
import io
import json
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final, Protocol, TypeAlias, cast

from .dossier import (
    DossierEvidence,
    DossierRecordRef,
    DossierReport,
    DossierSection,
    DossierSourceRefs,
    DossierValue,
)
from .dossier_renderer import (
    DOSSIER_RENDERER_VERSION,
    DossierHTMLInspection,
    DossierHTMLRenderer,
    DossierHTMLVerification,
    verify_dossier_html,
)
from .interim_monitor import InterimMonitorDescriptor

DOSSIER_RELEASE_SCHEMA: Final = "manager-gui.dossier-release.v2"
DOSSIER_SOURCE_RECORD_TYPE: Final = "apex-research.strategy-report-dossier-source.v2"
DOSSIER_ARTIFACT_RECORD_TYPE: Final = "apex-research.strategy-report-dossier-artifact.v2"
DOSSIER_ARCHIVE_NAME: Final = "dossier-v2.zip"
DOSSIER_MODEL_NAME: Final = "dossier-model.json"
DOSSIER_HTML_NAME: Final = "dossier.html"
_MANIFEST_NAME: Final = "manifest.json"
_SHA256_HEX: Final = frozenset("0123456789abcdef")


class DossierReleaseError(ValueError):
    """A package, model, or release proof is invalid."""


class RuntimeSubmissionClient(Protocol):
    """The forbidden boundary is documented, but never accepted as a dependency."""

    def submit(self, *args: object, **kwargs: object) -> object:
        """A Runtime submission method must never be called by this module."""


PublicReadback: TypeAlias = bytes | bytearray | str | Mapping[str, object]


class DossierPublicReadbackProvider(Protocol):
    """Exact public readback seam used by the gate.

    A provider must return the public bytes (or a mapping/string whose canonical UTF-8
    representation is those bytes) for the exact supplied SHA-256 publication ID.  It has
    no discovery, latest, write, or Runtime operation.
    """

    def read_publication(self, publication_id: str) -> PublicReadback:
        """Read one exact immutable public publication by ID."""


# Short aliases make the seam easy to find without changing the canonical name.
DossierPublicReader = DossierPublicReadbackProvider
PublicReadbackProvider = DossierPublicReadbackProvider


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
        raise DossierReleaseError("release values must be finite canonical JSON") from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _valid_sha(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in _SHA256_HEX for c in value):
        raise DossierReleaseError(f"{name} must be a lowercase SHA-256 ID")
    return value


def _bytes(value: object, name: str) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, Mapping):
        return _canonical_json(value)
    raise DossierReleaseError(f"{name} must be bytes, UTF-8 text, or a JSON object")


def _model(value: DossierReport | Mapping[str, object] | str) -> DossierReport:
    try:
        if isinstance(value, DossierReport):
            return value
        if isinstance(value, str):
            return DossierReport.from_json(value)
        if isinstance(value, Mapping):
            return DossierReport.from_dict(cast(Mapping[str, object], value))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DossierReleaseError("invalid Dossier v2 model for release") from exc
    raise TypeError("release gate requires a DossierReport or its JSON representation")


def _record_ids(value: object, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, DossierSourceRefs):
        values: Iterable[object] = value.records()
    elif isinstance(value, (DossierRecordRef, str)):
        values = (value,)
    elif isinstance(value, Mapping):
        values = tuple(value.keys())
    elif isinstance(value, Sequence):
        values = value
    else:
        raise TypeError(f"{name} must be an explicit ID sequence")
    result: list[str] = []
    for entry in values:
        if isinstance(entry, DossierRecordRef):
            entry = entry.record_id
        elif isinstance(entry, Mapping):
            entry = entry.get("record_id")
        result.append(_valid_sha(entry, f"{name}[]"))
    if len(set(result)) != len(result):
        raise DossierReleaseError(f"{name} contains duplicate IDs")
    return tuple(result)


def _read_provider(provider: DossierPublicReadbackProvider, publication_id: str, name: str) -> bytes:
    try:
        value = provider.read_publication(publication_id)
    except Exception as exc:
        raise DossierReleaseError(f"{name} public readback is unavailable: {publication_id}") from exc
    if value is None:
        raise DossierReleaseError(f"{name} public readback is unavailable: {publication_id}")
    try:
        return _bytes(value, f"{name} readback")
    except (TypeError, ValueError, DossierReleaseError) as exc:
        raise DossierReleaseError(f"{name} public readback is invalid: {publication_id}") from exc


def _try_read_provider(
    provider: DossierPublicReadbackProvider, publication_id: str, name: str
) -> tuple[bytes | None, str | None]:
    try:
        return _read_provider(provider, publication_id, name), None
    except DossierReleaseError as exc:
        return None, str(exc)


def _try_bytes(value: object, name: str) -> tuple[bytes | None, str | None]:
    try:
        return _bytes(value, name), None
    except DossierReleaseError as exc:
        return None, str(exc)


def _snapshot(
    provider: DossierPublicReadbackProvider | None,
    ids: tuple[str, ...],
    name: str,
) -> _ReadbackSnapshot:
    if provider is None:
        return _ReadbackSnapshot((), (f"{name} public readback provider is required",))
    digests: list[tuple[str, str]] = []
    errors: list[str] = []
    for publication_id in ids:
        try:
            payload = _read_provider(provider, publication_id, name)
        except DossierReleaseError as exc:
            errors.append(str(exc))
        else:
            digests.append((publication_id, _sha256(payload)))
    return _ReadbackSnapshot(tuple(digests), tuple(errors))


@dataclass(frozen=True, slots=True)
class _ReadbackSnapshot:
    values: tuple[tuple[str, str], ...]
    errors: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.errors

    def unchanged(self, other: _ReadbackSnapshot) -> bool:
        return self.complete and other.complete and self.values == other.values


def _zip_archive(model_bytes: bytes, html_bytes: bytes, manifest_bytes: bytes) -> bytes:
    """Build an archive whose bytes do not depend on clock, platform, or permissions."""

    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name, content in (
            (DOSSIER_MODEL_NAME, model_bytes),
            (DOSSIER_HTML_NAME, html_bytes),
            (_MANIFEST_NAME, manifest_bytes),
        ):
            info = zipfile.ZipInfo(filename=name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = 0o600 << 16
            info.flag_bits = 0
            archive.writestr(info, content)
    return output.getvalue()


@dataclass(frozen=True, slots=True)
class DossierSourcePublication:
    """Immutable model publication metadata and exact canonical model bytes."""

    publication_id: str
    record_type: str
    payload_sha256: str
    payload_bytes: bytes
    published: bool = False

    def __post_init__(self) -> None:
        _valid_sha(self.publication_id, "publication_id")
        if self.record_type != DOSSIER_SOURCE_RECORD_TYPE:
            raise ValueError("unexpected dossier source record type")
        if self.payload_sha256 != _sha256(self.payload_bytes):
            raise ValueError("source payload hash mismatch")
        if self.publication_id != self.payload_sha256:
            raise ValueError("source publication identity differs from payload")
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
    """Immutable deterministic HTML artifact metadata and exact UTF-8 bytes."""

    artifact_id: str
    record_type: str
    sha256: str
    bytes: object
    renderer_version: str
    published: bool = False

    def __post_init__(self) -> None:
        _valid_sha(self.artifact_id, "artifact_id")
        if self.record_type != DOSSIER_ARTIFACT_RECORD_TYPE:
            raise ValueError("unexpected dossier artifact record type")
        if not isinstance(self.bytes, builtins.bytes):
            raise TypeError("artifact bytes must be bytes")
        payload = cast(builtins.bytes, self.bytes)
        if self.sha256 != _sha256(payload) or self.artifact_id != self.sha256:
            raise ValueError("artifact bytes hash mismatch")
        if self.renderer_version != DOSSIER_RENDERER_VERSION:
            raise ValueError("unsupported dossier renderer version")
        if not isinstance(self.published, bool):
            raise TypeError("published must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": DOSSIER_RELEASE_SCHEMA,
            "artifact_id": self.artifact_id,
            "record_type": self.record_type,
            "sha256": self.sha256,
            "bytes": len(cast(builtins.bytes, self.bytes)),
            "renderer_version": self.renderer_version,
            "published": self.published,
        }

    def readback(self) -> builtins.bytes:
        return cast(builtins.bytes, self.bytes)


@dataclass(frozen=True, slots=True)
class DossierPublicationProof:
    """The exact IDs whose external public bytes verified one package."""

    source_publication_id: str
    artifact_id: str
    archive_sha256: str

    def __post_init__(self) -> None:
        _valid_sha(self.source_publication_id, "source_publication_id")
        _valid_sha(self.artifact_id, "artifact_id")
        _valid_sha(self.archive_sha256, "archive_sha256")

    def to_dict(self) -> dict[str, str]:
        return {
            "source_publication_id": self.source_publication_id,
            "artifact_id": self.artifact_id,
            "archive_sha256": self.archive_sha256,
        }


@dataclass(frozen=True, slots=True)
class DossierReleasePackage:
    """A deterministic local package; publication is a separately proved state."""

    source: DossierSourcePublication
    artifact: DossierArtifactPublication
    archive_sha256: str
    archive_bytes: bytes
    renderer_version: str = DOSSIER_RENDERER_VERSION
    published: bool = False
    publication_proof: DossierPublicationProof | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.published, bool):
            raise TypeError("published must be boolean")
        if self.source.published is not self.published or self.artifact.published is not self.published:
            raise ValueError("package and publication statuses must agree")
        if self.archive_sha256 != _sha256(self.archive_bytes):
            raise ValueError("archive hash mismatch")
        if self.renderer_version != DOSSIER_RENDERER_VERSION:
            raise ValueError("unsupported dossier renderer version")
        if self.renderer_version != self.artifact.renderer_version:
            raise ValueError("package renderer version differs from artifact")
        if self.published and self.publication_proof is None:
            raise ValueError("published package requires external public readback proof")
        if not self.published and self.publication_proof is not None:
            raise ValueError("unpublished package cannot carry publication proof")
        if self.publication_proof is not None and (
            self.publication_proof.source_publication_id != self.source_publication_id
            or self.publication_proof.artifact_id != self.artifact_id
            or self.publication_proof.archive_sha256 != self.archive_sha256
        ):
            raise ValueError("publication proof IDs differ from package IDs")

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
        return self.artifact.readback()

    def manifest(self) -> dict[str, object]:
        """Return the external manifest; the archive itself never hashes itself."""

        return {
            "schema": DOSSIER_RELEASE_SCHEMA,
            "renderer_version": self.renderer_version,
            "published": self.published,
            "source": self.source.to_dict(),
            "artifact": self.artifact.to_dict(),
            "archive_sha256": self.archive_sha256,
            "publication_proof": None
            if self.publication_proof is None
            else self.publication_proof.to_dict(),
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
    """Fail-closed result of local integrity and external readback verification."""

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
    external_readback_verified: bool = False
    source_identity_verified: bool = False
    renderer_version_verified: bool = False
    archive_verified: bool = False
    holdout_state_verified: bool = False
    quarantine_exclusion_verified: bool = False

    def __bool__(self) -> bool:
        return self.passed

    @property
    def old_readback_byte_identical(self) -> bool:
        return self.old_records_byte_identical and self.old_publications_byte_identical

    @property
    def zero_runtime_calls(self) -> bool:
        return self.runtime_submission_calls == 0

    @property
    def not_evaluated(self) -> bool:
        return not self.passed and not self.errors


@dataclass(frozen=True, slots=True)
class DossierRebuildResult:
    """An offline deterministic rebuild, always explicitly unpublished."""

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


def _invalid_html(error: str) -> DossierHTMLVerification:
    try:
        inspection = DossierHTMLRenderer().inspect("")
    except Exception:  # pragma: no cover - defensive fallback for a replaced renderer
        inspection = DossierHTMLInspection(
            html_sha256="",
            model_sha256=None,
            self_contained=False,
            has_boundary_banner=False,
            has_accessible_table=False,
            has_theme_toggle=False,
            has_filters=False,
            has_tabs=False,
            has_tooltips=False,
            has_responsive_layout=False,
            has_chart=False,
            fact_count=0,
        )
    return DossierHTMLVerification(False, (error,), inspection, None)


def _verify_archive(
    archive_bytes: bytes,
    package: DossierReleasePackage,
    model_bytes: bytes,
    html_bytes: bytes,
) -> tuple[bool, tuple[str, ...]]:
    errors: list[str] = []
    if _sha256(archive_bytes) != package.archive_sha256:
        errors.append("archive SHA-256 differs from external manifest")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            names = archive.namelist()
            expected_names = [DOSSIER_MODEL_NAME, DOSSIER_HTML_NAME, _MANIFEST_NAME]
            if names != expected_names:
                errors.append("archive entry names/order are invalid")
            if len(names) != len(set(names)):
                errors.append("archive contains duplicate entries")
            for info in archive.infolist():
                if info.date_time != (1980, 1, 1, 0, 0, 0):
                    errors.append("archive entry timestamp is not fixed")
                if info.create_system != 0 or info.external_attr != 0o600 << 16:
                    errors.append("archive entry metadata is not fixed")
                if info.compress_type != zipfile.ZIP_STORED:
                    errors.append("archive entries must be stored without compression")
            actual_model = archive.read(DOSSIER_MODEL_NAME)
            actual_html = archive.read(DOSSIER_HTML_NAME)
            manifest_bytes = archive.read(_MANIFEST_NAME)
            if actual_model != model_bytes:
                errors.append("archive model bytes differ from package source")
            if actual_html != html_bytes:
                errors.append("archive HTML bytes differ from package artifact")
            try:
                manifest = json.loads(manifest_bytes.decode("utf-8"))
                if not isinstance(manifest, Mapping):
                    raise ValueError("manifest is not an object")
                expected_manifest = {
                    "schema": DOSSIER_RELEASE_SCHEMA,
                    "renderer_version": package.renderer_version,
                    "published": False,
                    "source": replace(package.source, published=False).to_dict(),
                    "artifact": replace(package.artifact, published=False).to_dict(),
                }
                if dict(manifest) != expected_manifest:
                    errors.append("archive manifest differs from the external manifest")
                if "archive_sha256" in manifest:
                    errors.append("archive manifest must not contain a self hash")
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                errors.append("archive manifest is invalid JSON")
    except (zipfile.BadZipFile, KeyError, OSError, ValueError) as exc:
        errors.append(f"archive is invalid: {exc}")
    return not errors, tuple(errors)


def _typed_sections(report: DossierReport) -> tuple[DossierSection, ...]:
    """DossierReport normalizes its union-typed sections during construction."""

    return cast(tuple[DossierSection, ...], report.sections)


def _typed_evidence(section: DossierSection) -> tuple[DossierEvidence, ...]:
    """DossierSection normalizes its union-typed evidence during construction."""

    return cast(tuple[DossierEvidence, ...], section.evidence)


def _typed_facts(evidence: DossierEvidence) -> tuple[DossierValue, ...]:
    """DossierEvidence normalizes its union-typed facts during construction."""

    return cast(tuple[DossierValue, ...], evidence.facts)


def _model_safety(
    report: DossierReport, descriptor: InterimMonitorDescriptor
) -> tuple[bool, bool, tuple[str, ...]]:
    """Check the non-result boundary using both model and immutable descriptor."""

    errors: list[str] = []
    if report.holdout_results != "not_evaluated":
        errors.append("holdout results must remain not_evaluated")
    if not isinstance(report.banner, str) or "holdout" not in report.banner.lower():
        errors.append("model boundary banner does not state the Holdout boundary")
    if any(
        value != "forbidden"
        for value in (
            report.qualification_inference,
            report.causal_inference,
            report.production_approval_inference,
        )
    ):
        errors.append("profitability/causal/production inference policy is not forbidden")
    if descriptor.identity_sha256 != descriptor.ref().record_id:
        errors.append("interim monitor descriptor identity is invalid")
    if descriptor.status != "registered_not_started" or descriptor.mode != "descriptive_only_non_primary":
        errors.append("interim monitor descriptor is not locked to the deferred mode")
    if descriptor.primary_holdout.evaluation_before_data_complete:
        errors.append("holdout descriptor permits access before data completion")

    holdout = next((section for section in _typed_sections(report) if section.name == "holdout_lock"), None)
    if holdout is None:
        errors.append("model holdout state is missing")
    elif holdout.status == "not_evaluated" and not holdout.reason:
        errors.append("model holdout state has no deferred reason")
    elif holdout.status == "evaluated":
        allowed = {"locked", "not_accessed", "deferred", "not_evaluated"}
        text = " ".join(
            str(fact.value).lower()
            for evidence in _typed_evidence(holdout)
            for fact in _typed_facts(evidence)
            if fact.status == "evaluated"
        )
        if not any(marker in text for marker in allowed):
            errors.append("model holdout evidence does not prove locked/not_accessed/deferred state")
    holdout_ok = not any("holdout" in error.lower() for error in errors)

    quarantine = next((section for section in _typed_sections(report) if section.name == "quarantine"), None)
    quarantine_ok = False
    if quarantine is not None and quarantine.status == "evaluated":
        for evidence in _typed_evidence(quarantine):
            for fact in _typed_facts(evidence):
                path = fact.path.lower()
                value = str(fact.value).lower()
                if fact.status == "evaluated" and (
                    ("excluded" in path or "exclude" in path or "included" in path or "selected" in path)
                    and (fact.value is False or value in {"excluded", "quarantined", "not_included", "none"})
                ):
                    quarantine_ok = True
    if not quarantine_ok:
        errors.append("quarantine exclusion proof is missing; status is not_evaluated")
    return holdout_ok, quarantine_ok, tuple(errors)


def _model_for_package(package: DossierReleasePackage) -> tuple[DossierReport | None, tuple[str, ...]]:
    try:
        report = DossierReport.from_json(package.model_bytes.decode("utf-8"))
    except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return None, (f"source model readback is invalid: {exc}",)
    canonical = _canonical_json(report.to_dict())
    if canonical != package.model_bytes:
        return None, ("source model bytes are not canonical Dossier v2 JSON",)
    if _sha256(canonical) != package.source_publication_id:
        return None, ("source publication identity does not match model bytes",)
    return report, ()


class DossierReleaseGate:
    """Prepare deterministic bytes and optionally verify already-published readbacks."""

    def __init__(
        self,
        renderer: DossierHTMLRenderer | None = None,
        runtime: RuntimeSubmissionClient | None = None,
        descriptor: InterimMonitorDescriptor | None = None,
    ) -> None:
        del runtime  # The gate has no Runtime seam and therefore cannot call or count it.
        self.renderer = renderer or DossierHTMLRenderer()
        if not isinstance(self.renderer, DossierHTMLRenderer):
            raise TypeError("renderer must be a DossierHTMLRenderer")
        if self.renderer.version != DOSSIER_RENDERER_VERSION:
            raise DossierReleaseError("renderer version is not the registered Dossier renderer")
        self.descriptor = descriptor or InterimMonitorDescriptor()
        if not isinstance(self.descriptor, InterimMonitorDescriptor):
            raise TypeError("descriptor must be an InterimMonitorDescriptor")
        self.descriptor = InterimMonitorDescriptor.from_wire(self.descriptor.to_wire())

    def _package(self, value: DossierReport | Mapping[str, object] | str) -> DossierReleasePackage:
        report = _model(value)
        model_bytes = _canonical_json(report.to_dict())
        try:
            html_bytes = self.renderer.render(report).encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise DossierReleaseError("Dossier HTML rendering failed") from exc
        source_id = _sha256(model_bytes)
        artifact_id = _sha256(html_bytes)
        source = DossierSourcePublication(
            source_id, DOSSIER_SOURCE_RECORD_TYPE, source_id, model_bytes, False
        )
        artifact = DossierArtifactPublication(
            artifact_id,
            DOSSIER_ARTIFACT_RECORD_TYPE,
            artifact_id,
            html_bytes,
            self.renderer.version,
            False,
        )
        inner_manifest = _canonical_json(
            {
                "schema": DOSSIER_RELEASE_SCHEMA,
                "renderer_version": self.renderer.version,
                "published": False,
                "source": source.to_dict(),
                "artifact": artifact.to_dict(),
            }
        )
        archive = _zip_archive(model_bytes, html_bytes, inner_manifest)
        return DossierReleasePackage(source, artifact, _sha256(archive), archive, self.renderer.version)

    def release(
        self,
        value: DossierReport | Mapping[str, object] | str,
        *,
        old_records: Mapping[str, object] | None = None,
        old_publications: Mapping[str, object] | None = None,
    ) -> DossierReleasePackage:
        """Prepare local bytes only; this method can never claim publication."""

        if old_records is not None or old_publications is not None:
            raise DossierReleaseError(
                "release does not prove old readback; use publish/rebuild with a public reader"
            )
        return self._package(value)

    prepare = release

    def _ids(
        self,
        report: DossierReport,
        baseline_refs: object | None,
        current_root_ids: object | None,
        old_publication_ids: object | None,
        old_records: Mapping[str, object] | None,
        old_publications: Mapping[str, object] | None,
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        baseline = _record_ids(
            report.source_refs if baseline_refs is None else baseline_refs, "baseline_refs"
        )
        current = _record_ids(
            report.source_refs if current_root_ids is None else current_root_ids, "current_root_ids"
        )
        old = _record_ids(
            tuple(old_publications) if old_publication_ids is None and old_publications is not None else old_publication_ids,
            "old_publication_ids",
        )
        if old_records is not None and baseline_refs is None:
            baseline = _record_ids(tuple(old_records), "old_records")
        required = {ref.record_id for ref in report.source_refs.records()}
        missing_baseline = required - set(baseline)
        missing_current = required - set(current)
        if missing_baseline:
            raise DossierReleaseError("baseline_refs must explicitly include every current dossier root")
        if missing_current:
            raise DossierReleaseError("current_root_ids must explicitly include every current dossier root")
        if not old:
            raise DossierReleaseError("old_publication_ids must explicitly name old publications")
        return baseline, current, old

    def _inspect_values(
        self,
        package: DossierReleasePackage,
        *,
        source_readback: bytes | None,
        artifact_readback: bytes | None,
        archive_readback: bytes | None,
        model: DossierReport | Mapping[str, object] | str | None,
        baseline_before: _ReadbackSnapshot,
        baseline_after: _ReadbackSnapshot,
        current_before: _ReadbackSnapshot,
        current_after: _ReadbackSnapshot,
        old_before: _ReadbackSnapshot,
        old_after: _ReadbackSnapshot,
        external_readback_verified: bool,
        runtime_submission_calls: int = 0,
    ) -> DossierReleaseInspection:
        errors: list[str] = []
        source_identical = source_readback is not None and source_readback == package.model_bytes
        artifact_identical = artifact_readback is not None and artifact_readback == package.html_bytes
        archive_identical = archive_readback is not None and archive_readback == package.archive_bytes
        if source_readback is None:
            errors.append("source public readback is required; package bytes are not proof")
        elif not source_identical:
            errors.append("source readback is not byte-identical")
        if artifact_readback is None:
            errors.append("HTML public readback is required; package bytes are not proof")
        elif not artifact_identical:
            errors.append("artifact readback is not byte-identical")
        if archive_readback is None:
            errors.append("archive public readback is required; package bytes are not proof")
        elif not archive_identical:
            errors.append("archive readback is not byte-identical")

        expected_model: DossierReport | None = None
        model_errors: tuple[str, ...] = ()
        if model is not None:
            try:
                expected_model = _model(model)
            except (TypeError, ValueError, DossierReleaseError) as exc:
                model_errors = (f"expected model is invalid: {exc}",)
        else:
            expected_model, model_errors = _model_for_package(package)
        errors.extend(model_errors)
        source_identity = False
        if source_readback is not None:
            try:
                source_report = DossierReport.from_json(source_readback.decode("utf-8"))
                source_identity = (
                    _sha256(_canonical_json(source_report.to_dict())) == package.source_publication_id
                    and source_readback == _canonical_json(source_report.to_dict())
                )
            except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"source identity verification failed: {exc}")
        if not source_identity and source_readback is not None:
            errors.append("source publication identity is not verified")
        if expected_model is not None and source_readback is not None and source_readback != _canonical_json(expected_model.to_dict()):
            errors.append("source model readback differs from expected model")

        if artifact_readback is None:
            html_verification = _invalid_html("HTML public readback is missing")
        else:
            try:
                html_text = artifact_readback.decode("utf-8")
            except UnicodeDecodeError as exc:
                html_verification = _invalid_html(f"HTML public readback is not UTF-8: {exc}")
            else:
                try:
                    html_verification = verify_dossier_html(html_text, expected_model)
                except (TypeError, ValueError, UnicodeError) as exc:
                    html_verification = _invalid_html(f"HTML verification failed: {exc}")
                if not html_verification:
                    errors.extend(f"HTML: {error}" for error in html_verification.errors)
        renderer_version = False
        if artifact_readback is not None:
            marker = f'data-renderer-version="{DOSSIER_RENDERER_VERSION}"'.encode()
            renderer_version = marker in artifact_readback
            if not renderer_version:
                errors.append("HTML renderer version is missing or differs")
        if archive_readback is not None:
            archive_ok, archive_errors = _verify_archive(
                archive_readback, package, package.model_bytes, package.html_bytes
            )
            if not archive_ok:
                errors.extend(archive_errors)
        else:
            archive_ok = False
        baseline_same = baseline_before.unchanged(baseline_after)
        current_same = current_before.unchanged(current_after)
        old_same = old_before.unchanged(old_after)
        errors.extend(baseline_before.errors)
        errors.extend(baseline_after.errors)
        errors.extend(current_before.errors)
        errors.extend(current_after.errors)
        errors.extend(old_before.errors)
        errors.extend(old_after.errors)
        if not baseline_same:
            errors.append("baseline public records changed or were not proved")
        if not current_same:
            errors.append("current root public records changed or were not proved")
        if not old_same:
            errors.append("old publication readbacks changed or were not proved")
        if not external_readback_verified:
            errors.append("external public readback proof is required; local self-readback is invalid")
        if runtime_submission_calls != 0:
            errors.append("non-zero Runtime submission count was supplied")
        if expected_model is None:
            holdout_ok = quarantine_ok = False
        else:
            holdout_ok, quarantine_ok, safety_errors = _model_safety(expected_model, self.descriptor)
            errors.extend(safety_errors)
        passed = not errors
        return DossierReleaseInspection(
            passed,
            package.published,
            package.source_publication_id,
            package.artifact_id,
            source_identical,
            artifact_identical,
            archive_identical,
            baseline_same and current_same,
            old_same,
            runtime_submission_calls,
            html_verification,
            tuple(dict.fromkeys(errors)),
            external_readback_verified,
            source_identity,
            renderer_version,
            archive_ok,
            holdout_ok,
            quarantine_ok,
        )

    def rebuild(
        self,
        value: DossierReport | Mapping[str, object] | str,
        *,
        public_reader: DossierPublicReadbackProvider | None = None,
        baseline_refs: DossierSourceRefs | Sequence[object] | None = None,
        current_root_ids: Sequence[object] | None = None,
        old_publication_ids: Sequence[object] | None = None,
        old_records: Mapping[str, object] | None = None,
        old_publications: Mapping[str, object] | None = None,
    ) -> DossierRebuildResult:
        """Render twice without a Runtime seam and compare caller-owned public snapshots."""

        report = _model(value)
        try:
            baseline, current, old = self._ids(
                report,
                baseline_refs,
                current_root_ids,
                old_publication_ids,
                old_records,
                old_publications,
            )
        except DossierReleaseError as exc:
            # Keep the result inspectable and fail closed rather than turning missing proof into success.
            baseline = current = old = ()
            id_error = str(exc)
        else:
            id_error = ""
        first = self._package(report)
        second = self._package(report)
        deterministic = first.readback() == second.readback()

        if public_reader is not None and not id_error:
            # A rebuild may verify already-published bytes, but it must never write or
            # turn the rebuilt package into a published package.  Reuse the same
            # external-reader path as inspect so source, artifact, archive, and the
            # caller's immutable snapshots are all checked byte-for-byte.
            inspection = self.inspect(
                first,
                model=report,
                public_reader=public_reader,
                baseline_refs=baseline_refs,
                current_root_ids=current_root_ids,
                old_publication_ids=old_publication_ids,
                old_records=old_records,
                old_publications=old_publications,
            )
        else:
            before_baseline = _snapshot(public_reader, baseline, "baseline")
            before_current = _snapshot(public_reader, current, "current roots")
            before_old = _snapshot(public_reader, old, "old publications")
            after_baseline = _snapshot(public_reader, baseline, "baseline")
            after_current = _snapshot(public_reader, current, "current roots")
            after_old = _snapshot(public_reader, old, "old publications")
            inspection = self._inspect_values(
                first,
                source_readback=first.model_bytes,
                artifact_readback=first.html_bytes,
                archive_readback=first.archive_bytes,
                model=report,
                baseline_before=before_baseline,
                baseline_after=after_baseline,
                current_before=before_current,
                current_after=after_current,
                old_before=before_old,
                old_after=after_old,
                external_readback_verified=False,
            )
        if id_error:
            inspection = replace(inspection, errors=(*inspection.errors, id_error), passed=False)
        if not deterministic:
            inspection = replace(
                inspection,
                passed=False,
                errors=(*inspection.errors, "rebuild bytes are not deterministic"),
            )
        records_same = inspection.old_records_byte_identical
        publications_same = inspection.old_publications_byte_identical
        return DossierRebuildResult(first, False, 0, deterministic, records_same, publications_same, inspection)

    def publish(
        self,
        value: DossierReleasePackage | DossierReport | Mapping[str, object] | str,
        *,
        public_reader: DossierPublicReadbackProvider,
        baseline_refs: DossierSourceRefs | Sequence[object] | None = None,
        current_root_ids: Sequence[object] | None = None,
        old_publication_ids: Sequence[object] | None = None,
        old_records: Mapping[str, object] | None = None,
        old_publications: Mapping[str, object] | None = None,
    ) -> DossierReleasePackage:
        """Mark a package published only after exact external readback succeeds.

        This method does not write anywhere.  The caller's publication orchestration must
        have completed before the provider can return these exact IDs.
        """

        if not hasattr(public_reader, "read_publication"):
            raise TypeError("public_reader must implement read_publication")
        if isinstance(value, DossierReleasePackage):
            package = value
            report, model_errors = _model_for_package(package)
            if model_errors:
                raise DossierReleaseError("cannot publish invalid package source model")
            assert report is not None
        else:
            report = _model(value)
            package = None
        baseline, current, old = self._ids(
            report,
            baseline_refs,
            current_root_ids,
            old_publication_ids,
            old_records,
            old_publications,
        )
        before_baseline = _snapshot(public_reader, baseline, "baseline")
        before_current = _snapshot(public_reader, current, "current roots")
        before_old = _snapshot(public_reader, old, "old publications")
        if package is None:
            package = self._package(report)
        source = _read_provider(public_reader, package.source_publication_id, "source")
        artifact = _read_provider(public_reader, package.artifact_id, "HTML artifact")
        archive = _read_provider(public_reader, package.archive_sha256, "archive")
        after_baseline = _snapshot(public_reader, baseline, "baseline")
        after_current = _snapshot(public_reader, current, "current roots")
        after_old = _snapshot(public_reader, old, "old publications")
        inspection = self._inspect_values(
            package,
            source_readback=source,
            artifact_readback=artifact,
            archive_readback=archive,
            model=report,
            baseline_before=before_baseline,
            baseline_after=after_baseline,
            current_before=before_current,
            current_after=after_current,
            old_before=before_old,
            old_after=after_old,
            external_readback_verified=True,
        )
        if not inspection:
            detail = "; ".join(inspection.errors)
            raise DossierReleaseError(f"external public readback proof failed closed: {detail}")
        proof = DossierPublicationProof(
            package.source_publication_id, package.artifact_id, package.archive_sha256
        )
        return DossierReleasePackage(
            replace(package.source, published=True),
            replace(package.artifact, published=True),
            package.archive_sha256,
            package.archive_bytes,
            package.renderer_version,
            True,
            proof,
        )

    finalize_publication = publish

    def inspect(
        self,
        package: DossierReleasePackage,
        *,
        source_readback: object | None = None,
        artifact_readback: object | None = None,
        archive_readback: object | None = None,
        model: DossierReport | Mapping[str, object] | str | None = None,
        public_reader: DossierPublicReadbackProvider | None = None,
        baseline_refs: DossierSourceRefs | Sequence[object] | None = None,
        current_root_ids: Sequence[object] | None = None,
        old_publication_ids: Sequence[object] | None = None,
        old_records: Mapping[str, object] | None = None,
        old_publications: Mapping[str, object] | None = None,
        runtime_submission_calls: int = 0,
        old_records_byte_identical: bool | None = None,
        old_publications_byte_identical: bool | None = None,
    ) -> DossierReleaseInspection:
        """Inspect without ever treating omitted/package bytes as external proof."""

        if not isinstance(package, DossierReleasePackage):
            raise TypeError("inspect requires a DossierReleasePackage")
        if old_records_byte_identical is not None or old_publications_byte_identical is not None:
            flag_error = "caller old snapshot flags are not public readback proof"
        else:
            flag_error = ""
        if public_reader is not None:
            report = _model(model) if model is not None else _model_for_package(package)[0]
            if report is None:
                report = model if isinstance(model, DossierReport) else None
            if report is None:
                return self._inspect_values(
                    package,
                    source_readback=None,
                    artifact_readback=None,
                    archive_readback=None,
                    model=model,
                    baseline_before=_ReadbackSnapshot((), ("source model is invalid",)),
                    baseline_after=_ReadbackSnapshot((), ()),
                    current_before=_ReadbackSnapshot((), ()),
                    current_after=_ReadbackSnapshot((), ()),
                    old_before=_ReadbackSnapshot((), ()),
                    old_after=_ReadbackSnapshot((), ()),
                    external_readback_verified=False,
                )
            try:
                baseline, current, old = self._ids(
                    report,
                    baseline_refs,
                    current_root_ids,
                    old_publication_ids,
                    old_records,
                    old_publications,
                )
            except (TypeError, ValueError, DossierReleaseError) as exc:
                result = self._inspect_values(
                    package,
                    source_readback=None,
                    artifact_readback=None,
                    archive_readback=None,
                    model=report,
                    baseline_before=_ReadbackSnapshot((), (str(exc),)),
                    baseline_after=_ReadbackSnapshot((), ()),
                    current_before=_ReadbackSnapshot((), ()),
                    current_after=_ReadbackSnapshot((), ()),
                    old_before=_ReadbackSnapshot((), ()),
                    old_after=_ReadbackSnapshot((), ()),
                    external_readback_verified=False,
                    runtime_submission_calls=runtime_submission_calls,
                )
            else:
                before_baseline = _snapshot(public_reader, baseline, "baseline")
                before_current = _snapshot(public_reader, current, "current roots")
                before_old = _snapshot(public_reader, old, "old publications")
                source, source_error = _try_read_provider(
                    public_reader, package.source_publication_id, "source"
                )
                artifact, artifact_error = _try_read_provider(
                    public_reader, package.artifact_id, "HTML artifact"
                )
                archive, archive_error = _try_read_provider(
                    public_reader, package.archive_sha256, "archive"
                )
                after_baseline = _snapshot(public_reader, baseline, "baseline")
                after_current = _snapshot(public_reader, current, "current roots")
                after_old = _snapshot(public_reader, old, "old publications")
                result = self._inspect_values(
                    package,
                    source_readback=source,
                    artifact_readback=artifact,
                    archive_readback=archive,
                    model=report,
                    baseline_before=before_baseline,
                    baseline_after=after_baseline,
                    current_before=before_current,
                    current_after=after_current,
                    old_before=before_old,
                    old_after=after_old,
                    external_readback_verified=not any(
                        error is not None for error in (source_error, artifact_error, archive_error)
                    ),
                    runtime_submission_calls=runtime_submission_calls,
                )
                readback_errors = tuple(
                    error for error in (source_error, artifact_error, archive_error) if error is not None
                )
                if readback_errors:
                    result = replace(
                        result,
                        passed=False,
                        errors=(*result.errors, *readback_errors),
                    )
        else:
            source, source_error = (
                (None, None)
                if source_readback is None
                else _try_bytes(source_readback, "source_readback")
            )
            artifact, artifact_error = (
                (None, None)
                if artifact_readback is None
                else _try_bytes(artifact_readback, "artifact_readback")
            )
            archive, archive_error = (
                (None, None)
                if archive_readback is None
                else _try_bytes(archive_readback, "archive_readback")
            )
            result = self._inspect_values(
                package,
                source_readback=source,
                artifact_readback=artifact,
                archive_readback=archive,
                model=model,
                baseline_before=_ReadbackSnapshot((), ("public reader is required for baseline proof",)),
                baseline_after=_ReadbackSnapshot((), ()),
                current_before=_ReadbackSnapshot((), ("public reader is required for current-root proof",)),
                current_after=_ReadbackSnapshot((), ()),
                old_before=_ReadbackSnapshot((), ("public reader is required for old-publication proof",)),
                old_after=_ReadbackSnapshot((), ()),
                external_readback_verified=False,
                runtime_submission_calls=runtime_submission_calls,
            )
            readback_errors = tuple(
                error for error in (source_error, artifact_error, archive_error) if error is not None
            )
            if readback_errors:
                result = replace(
                    result,
                    passed=False,
                    errors=(*result.errors, *readback_errors),
                )
        if flag_error:
            result = replace(result, passed=False, errors=(*result.errors, flag_error))
        return result

    def verify(
        self,
        package: DossierReleasePackage,
        model: DossierReport | Mapping[str, object] | str | None = None,
        *,
        public_reader: DossierPublicReadbackProvider | None = None,
        baseline_refs: DossierSourceRefs | Sequence[object] | None = None,
        current_root_ids: Sequence[object] | None = None,
        old_publication_ids: Sequence[object] | None = None,
        old_records: Mapping[str, object] | None = None,
        old_publications: Mapping[str, object] | None = None,
        runtime_submission_calls: int = 0,
    ) -> DossierReleaseInspection:
        """Verify package integrity and, when supplied, exact external public readback."""

        return self.inspect(
            package,
            model=model,
            public_reader=public_reader,
            baseline_refs=baseline_refs,
            current_root_ids=current_root_ids,
            old_publication_ids=old_publication_ids,
            old_records=old_records,
            old_publications=old_publications,
            runtime_submission_calls=runtime_submission_calls,
        )


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
    return DossierReleaseGate().release(
        model, old_records=old_records, old_publications=old_publications
    )


def rebuild_dossier(
    model: DossierReport | Mapping[str, object] | str,
    *,
    public_reader: DossierPublicReadbackProvider | None = None,
    baseline_refs: DossierSourceRefs | Sequence[object] | None = None,
    current_root_ids: Sequence[object] | None = None,
    old_publication_ids: Sequence[object] | None = None,
) -> DossierRebuildResult:
    return DossierReleaseGate().rebuild(
        model,
        public_reader=public_reader,
        baseline_refs=baseline_refs,
        current_root_ids=current_root_ids,
        old_publication_ids=old_publication_ids,
    )


__all__ = [
    "DOSSIER_ARCHIVE_NAME",
    "DOSSIER_ARTIFACT_RECORD_TYPE",
    "DOSSIER_HTML_NAME",
    "DOSSIER_MODEL_NAME",
    "DOSSIER_RELEASE_SCHEMA",
    "DOSSIER_SOURCE_RECORD_TYPE",
    "DossierArtifactPublication",
    "DossierPublicReadbackProvider",
    "DossierPublicReader",
    "DossierPublicationProof",
    "DossierRebuildResult",
    "DossierRelease",
    "DossierReleaseError",
    "DossierReleaseGate",
    "DossierReleaseInspection",
    "DossierReleasePackage",
    "DossierSourcePublication",
    "GeneratedDossierArtifact",
    "PublicReadbackProvider",
    "ReleaseGate",
    "RuntimeSubmissionClient",
    "SourcePublication",
    "rebuild_dossier",
    "release_dossier",
]
