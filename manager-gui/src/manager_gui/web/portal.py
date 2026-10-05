"""Read-only Strategy Reporting static Portal adapter and renderer.

This module consumes an explicitly published ``ManagerReadModel`` v0 payload
from the Strategy Reporting report-source seam.  It keeps source publication
metadata separate from the generated static artifact, exposes renderer and
verification/rebuild metadata, and renders stable metadata links without
opening the report, triggering a rebuild, or treating the Portal as canonical
research state.

The public integration seam is :func:`render_portal_view`.  It accepts either
an already-read envelope or a provider whose only operation is the existing
``read`` seam.  Deterministic fixtures are synthetic and never inspect a
filesystem, SQLite database, or Strategy Reporting implementation.
"""

# HTML fragments intentionally use readable long lines.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from html import escape
from typing import Protocol, cast, runtime_checkable

from ..models import (
    Availability,
    Derivation,
    JSONValue,
    ManagerReadModel,
    ReadModelError,
    ReadModelStatus,
    SourceReference,
)
from ..provider import ManagerDataProvider
from .i18n import Translator
from .i18n.catalog.l5_portal import page_translator
from .locators import public_locator
from .navigation import context_link
from .status import DisplayState, render_operational_state, render_status_block

REPORT_SOURCE_RESOURCE = "report_source"
"""The versioned public read resource for Strategy Reporting metadata."""

PORTAL_RESOURCE = REPORT_SOURCE_RESOURCE
REPORTING_PORTAL_RESOURCE = REPORT_SOURCE_RESOURCE
PORTAL_INTEGRATION_HOOK = "manager_gui.web.portal.render_portal_view"


@runtime_checkable
class ReportSourceProvider(Protocol):
    """Read-only public seam for Strategy Reporting report-source metadata.

    The seam deliberately mirrors :class:`ManagerDataProvider` so a mounted
    S6 integration can use the same shell/provider boundary.  There is no
    publish, rebuild, run, retry, or other mutation operation here.
    """

    def read(
        self,
        resource: str = REPORT_SOURCE_RESOURCE,
        *,
        snapshot_token: str | None = None,
    ) -> ManagerReadModel:
        """Read one published report-source envelope."""


class PortalArtifactState(StrEnum):
    """Portal-specific state of the static generated artifact."""

    READY = "ready"
    MISSING = "missing"
    NOT_GENERATED = "not-generated"
    PARTIAL = "partial"
    INTEGRITY_FAILURE = "integrity-failure"
    API_UNAVAILABLE = "api-unavailable"


# Names used by callers that describe the same page-local state differently.
ReportArtifactState = PortalArtifactState
PortalState = PortalArtifactState


class ReportVerifyStatus(StrEnum):
    """Status values commonly published by the report verification step."""

    VERIFIED = "verified"
    FAILED = "failed"
    NOT_VERIFIED = "not_verified"
    UNKNOWN = "unknown"


class ReportRebuildStatus(StrEnum):
    """Status values that describe rebuild metadata without running a rebuild."""

    NOT_REQUESTED = "not_requested"
    NOT_GENERATED = "not_generated"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


VerifyStatus = ReportVerifyStatus
RebuildStatus = ReportRebuildStatus


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _mapping(value: object) -> Mapping[str, object] | None:
    return cast(Mapping[str, object], value) if isinstance(value, Mapping) else None


def _first_text(item: Mapping[str, object], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = _text(item.get(key))
        if value is not None:
            return value
    return None


def _nested_mapping(item: Mapping[str, object], keys: Sequence[str]) -> Mapping[str, object] | None:
    for key in keys:
        value = _mapping(item.get(key))
        if value is not None:
            return value
    return None


def _normalise(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    return text.lower().strip().replace("-", "_").replace(" ", "_")


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    if isinstance(value, Mapping):
        return (value,)
    return ()


def _source_ids(value: object) -> tuple[str, ...]:
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    if isinstance(value, Mapping):
        source_id = _first_text(value, ("source_id", "source_ref", "sourceId", "id"))
        return (source_id,) if source_id else ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values: list[str] = []
        for entry in value:
            values.extend(_source_ids(entry))
        return tuple(dict.fromkeys(values))
    return ()


def _source_reference(
    value: object,
    source_refs: Mapping[str, SourceReference],
) -> tuple[str | None, SourceReference | None]:
    ids = _source_ids(value)
    if not ids:
        return None, None
    source_id = ids[0]
    return source_id, source_refs.get(source_id)


def _locator(
    item: Mapping[str, object],
    source_refs: Mapping[str, SourceReference],
    *,
    source_keys: Sequence[str] = ("source_ref", "source_id", "source_ref_id"),
) -> tuple[str | None, str | None]:
    direct = _first_text(item, ("locator", "source_locator", "source_url", "url", "href", "uri"))
    source_id, source = _source_reference(
        next((item[key] for key in source_keys if key in item), None), source_refs
    )
    if direct is not None:
        return source_id, direct
    return (source_id, source.locator if source is not None else None)


def _source_publication_item(
    payload: Mapping[str, object],
) -> Mapping[str, object] | None:
    for key in (
        "source_publication",
        "sourcePublication",
        "report_source",
        "reportSource",
        "publication",
        "source",
    ):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            return {"source_ref": raw.strip()}
        nested = _mapping(raw)
        if nested is not None:
            return nested
    # A source publication may be published as a flat report-source record.
    if any(
        key in payload
        for key in (
            "publication_id",
            "source_publication_id",
            "source_id",
            "source_ref",
        )
    ):
        return payload
    return None


def _artifact_item(payload: Mapping[str, object]) -> Mapping[str, object] | None:
    nested = _nested_mapping(
        payload,
        (
            "generated_artifact",
            "generatedArtifact",
            "report_artifact",
            "reportArtifact",
            "artifact",
            "generated",
        ),
    )
    if nested is not None:
        return nested
    if any(key in payload for key in ("artifact_id", "artifactId")):
        return payload
    return None


def _explicit_artifact_state(payload: Mapping[str, object]) -> PortalArtifactState | None:
    raw = _first_text(
        payload,
        (
            "portal_state",
            "portal_status",
            "artifact_state",
            "artifact_status",
            "generated_artifact_status",
            "generated_status",
        ),
    )
    if raw is None:
        nested = _nested_mapping(payload, ("generated_artifact", "generatedArtifact", "artifact"))
        if nested is not None:
            raw = _first_text(nested, ("state", "status", "artifact_state", "artifact_status"))
    selected = _normalise(raw)
    if selected is None:
        return None
    aliases = {
        "ready": PortalArtifactState.READY,
        "known": PortalArtifactState.READY,
        "complete": PortalArtifactState.READY,
        "missing": PortalArtifactState.MISSING,
        "not_generated": PortalArtifactState.NOT_GENERATED,
        "not_built": PortalArtifactState.NOT_GENERATED,
        "not_published": PortalArtifactState.NOT_GENERATED,
        "partial": PortalArtifactState.PARTIAL,
        "integrity_failure": PortalArtifactState.INTEGRITY_FAILURE,
        "digest_mismatch": PortalArtifactState.INTEGRITY_FAILURE,
        "api_unavailable": PortalArtifactState.API_UNAVAILABLE,
    }
    return aliases.get(selected)


def _status_text(value: object) -> str | None:
    if isinstance(value, Mapping):
        return _first_text(value, ("status", "state", "value", "result"))
    return _text(value)


@dataclass(frozen=True, slots=True)
class ReportSourcePublication:
    """Published report-source metadata, kept separate from the artifact."""

    publication_id: str
    title: str | None = None
    version: str | None = None
    revision: str | None = None
    locator: str | None = None
    published_at: str | None = None
    source_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.publication_id, str) or not self.publication_id.strip():
            raise ValueError("publication_id must be a non-empty string")
        for name in ("title", "version", "revision", "locator", "published_at", "source_ref"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string or None")

    @property
    def source_id(self) -> str | None:
        """Compatibility alias for the public source reference identity."""

        return self.source_ref

    @property
    def source_locator(self) -> str | None:
        return self.locator

    def to_dict(self) -> dict[str, object]:
        return {
            "publication_id": self.publication_id,
            "title": self.title,
            "version": self.version,
            "revision": self.revision,
            "locator": self.locator,
            "published_at": self.published_at,
            "source_ref": self.source_ref,
        }


SourcePublication = ReportSourcePublication


@dataclass(frozen=True, slots=True)
class GeneratedReportArtifact:
    """Metadata for a generated static artifact; no artifact is opened here."""

    artifact_id: str
    report_id: str | None = None
    title: str | None = None
    locator: str | None = None
    renderer: str | None = None
    renderer_version: str | None = None
    generated_at: str | None = None
    verify_status: str | None = None
    rebuild_status: str | None = None
    digest: str | None = None
    source_publication_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, str) or not self.artifact_id.strip():
            raise ValueError("artifact_id must be a non-empty string")
        for name in (
            "report_id",
            "title",
            "locator",
            "renderer",
            "renderer_version",
            "generated_at",
            "verify_status",
            "rebuild_status",
            "digest",
            "source_publication_id",
        ):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string or None")

    @property
    def version(self) -> str | None:
        """Renderer version alias for clients that call it simply ``version``."""

        return self.renderer_version

    @property
    def verify(self) -> str | None:
        return self.verify_status

    @property
    def rebuild(self) -> str | None:
        return self.rebuild_status

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "report_id": self.report_id,
            "title": self.title,
            "locator": self.locator,
            "renderer": self.renderer,
            "renderer_version": self.renderer_version,
            "generated_at": self.generated_at,
            "verify_status": self.verify_status,
            "rebuild_status": self.rebuild_status,
            "digest": self.digest,
            "source_publication_id": self.source_publication_id,
        }


GeneratedArtifact = GeneratedReportArtifact


@dataclass(frozen=True, slots=True)
class ReportPortalEntry:
    """One report-index row with independent source and artifact metadata."""

    report_id: str | None
    title: str | None
    source_publication: ReportSourcePublication | None
    generated_artifact: GeneratedReportArtifact | None
    artifact_state: PortalArtifactState

    @property
    def source(self) -> ReportSourcePublication | None:
        return self.source_publication

    @property
    def artifact(self) -> GeneratedReportArtifact | None:
        return self.generated_artifact

    @property
    def renderer(self) -> str | None:
        return self.generated_artifact.renderer if self.generated_artifact is not None else None

    @property
    def renderer_version(self) -> str | None:
        return (
            self.generated_artifact.renderer_version
            if self.generated_artifact is not None
            else None
        )

    @property
    def verify_status(self) -> str | None:
        return self.generated_artifact.verify_status if self.generated_artifact is not None else None

    @property
    def rebuild_status(self) -> str | None:
        return self.generated_artifact.rebuild_status if self.generated_artifact is not None else None

    def to_dict(self) -> dict[str, object]:
        return {
            "report_id": self.report_id,
            "title": self.title,
            "source_publication": (
                None if self.source_publication is None else self.source_publication.to_dict()
            ),
            "generated_artifact": (
                None if self.generated_artifact is None else self.generated_artifact.to_dict()
            ),
            "artifact_state": self.artifact_state.value,
        }


PortalReport = ReportPortalEntry
ReportIndexEntry = ReportPortalEntry


@dataclass(frozen=True, slots=True)
class PortalViewModel:
    """Typed projection of a Strategy Reporting report-source envelope."""

    read_model: ManagerReadModel
    report_id: str | None
    title: str | None
    source_publication: ReportSourcePublication | None
    generated_artifact: GeneratedReportArtifact | None
    artifact_state: PortalArtifactState
    reports: tuple[ReportPortalEntry, ...] = ()

    @classmethod
    def from_read_model(cls, model: ManagerReadModel) -> PortalViewModel:
        payload = _mapping(model.data) or {}
        source_refs = {source.source_id: source for source in model.source_refs}
        source_item = _source_publication_item(payload)
        source_publication: ReportSourcePublication | None = None
        if source_item is not None:
            source_id, source_locator = _locator(source_item, source_refs)
            publication_id = _first_text(
                source_item,
                ("publication_id", "publicationId", "source_publication_id", "sourcePublicationId", "id"),
            )
            if publication_id is None and source_id is not None:
                publication_id = source_id
            if publication_id is not None:
                source_publication = ReportSourcePublication(
                    publication_id=publication_id,
                    title=_first_text(source_item, ("title", "name", "label")),
                    version=_first_text(source_item, ("version", "publication_version", "source_version")),
                    revision=_first_text(source_item, ("revision", "source_revision")),
                    locator=source_locator,
                    published_at=_first_text(source_item, ("published_at", "publishedAt", "released_at")),
                    source_ref=source_id
                    or _first_text(source_item, ("source_ref", "source_id", "sourceRef", "sourceId")),
                )

        artifact_item = _artifact_item(payload)
        generated_artifact: GeneratedReportArtifact | None = None
        if artifact_item is not None:
            artifact_id = _first_text(artifact_item, ("artifact_id", "artifactId", "id"))
            if artifact_id is not None:
                renderer_item = _nested_mapping(artifact_item, ("renderer", "render"))
                renderer = _first_text(artifact_item, ("renderer_name", "renderer_id", "renderer"))
                renderer_version = _first_text(
                    artifact_item,
                    ("renderer_version", "rendererVersion", "version"),
                )
                if renderer_item is not None:
                    renderer = renderer or _first_text(renderer_item, ("name", "id", "renderer"))
                    renderer_version = renderer_version or _first_text(
                        renderer_item, ("version", "renderer_version")
                    )
                verify_item = _nested_mapping(artifact_item, ("verify", "verification"))
                rebuild_item = _nested_mapping(artifact_item, ("rebuild", "rebuild_info"))
                generated_artifact = GeneratedReportArtifact(
                    artifact_id=artifact_id,
                    report_id=_first_text(artifact_item, ("report_id", "reportId"))
                    or _first_text(payload, ("report_id", "reportId")),
                    title=_first_text(artifact_item, ("title", "name", "label")),
                    locator=_first_text(artifact_item, ("locator", "artifact_locator", "url", "href", "uri")),
                    renderer=renderer,
                    renderer_version=renderer_version,
                    generated_at=_first_text(
                        artifact_item, ("generated_at", "generatedAt", "built_at", "published_at")
                    ),
                    verify_status=_status_text(artifact_item.get("verify_status"))
                    or _status_text(artifact_item.get("verification_status"))
                    or _status_text(verify_item),
                    rebuild_status=_status_text(artifact_item.get("rebuild_status"))
                    or _status_text(rebuild_item),
                    digest=_first_text(artifact_item, ("digest", "hash", "sha256")),
                    source_publication_id=_first_text(
                        artifact_item,
                        ("source_publication_id", "sourcePublicationId", "publication_id"),
                    )
                    or (source_publication.publication_id if source_publication is not None else None),
                )

        state = _portal_state(model, payload, source_publication, generated_artifact)
        report_id = _first_text(payload, ("report_id", "reportId", "id")) or (
            generated_artifact.report_id if generated_artifact is not None else None
        )
        title = _first_text(payload, ("title", "name", "label")) or (
            source_publication.title if source_publication is not None else None
        )
        indexed_entries = _portal_index_entries(model, payload)
        if indexed_entries:
            first = indexed_entries[0]
            return cls(
                read_model=model,
                report_id=report_id or first.report_id,
                title=title or first.title,
                source_publication=source_publication or first.source_publication,
                generated_artifact=generated_artifact or first.generated_artifact,
                artifact_state=(state if state is not PortalArtifactState.MISSING else first.artifact_state),
                reports=indexed_entries,
            )
        reports = (
            ReportPortalEntry(
                report_id=report_id,
                title=title,
                source_publication=source_publication,
                generated_artifact=generated_artifact,
                artifact_state=state,
            ),
        ) if report_id or source_publication is not None or generated_artifact is not None else ()
        return cls(
            read_model=model,
            report_id=report_id,
            title=title,
            source_publication=source_publication,
            generated_artifact=generated_artifact,
            artifact_state=state,
            reports=reports,
        )

    @property
    def source(self) -> ReportSourcePublication | None:
        return self.source_publication

    @property
    def report_source(self) -> ReportSourcePublication | None:
        return self.source_publication

    @property
    def artifact(self) -> GeneratedReportArtifact | None:
        return self.generated_artifact

    @property
    def state(self) -> PortalArtifactState:
        return self.artifact_state

    @property
    def renderer(self) -> str | None:
        return self.generated_artifact.renderer if self.generated_artifact is not None else None

    @property
    def renderer_version(self) -> str | None:
        return (
            self.generated_artifact.renderer_version
            if self.generated_artifact is not None
            else None
        )

    @property
    def verify_status(self) -> str | None:
        return self.generated_artifact.verify_status if self.generated_artifact is not None else None

    @property
    def rebuild_status(self) -> str | None:
        return self.generated_artifact.rebuild_status if self.generated_artifact is not None else None

    @property
    def is_canonical_research_state(self) -> bool:
        """Portal publications are never asserted to be canonical research state."""

        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "report_id": self.report_id,
            "title": self.title,
            "source_publication": (
                None if self.source_publication is None else self.source_publication.to_dict()
            ),
            "generated_artifact": (
                None if self.generated_artifact is None else self.generated_artifact.to_dict()
            ),
            "artifact_state": self.artifact_state.value,
            "reports": [entry.to_dict() for entry in self.reports],
            "canonical_research_state": False,
            "availability": self.read_model.availability.to_dict(),
            "as_of": self.read_model.as_of,
            "snapshot_token": self.read_model.snapshot_token,
        }

    @property
    def report_index(self) -> tuple[ReportPortalEntry, ...]:
        return self.reports

    @property
    def entries(self) -> tuple[ReportPortalEntry, ...]:
        return self.reports

    @property
    def source_publications(self) -> tuple[ReportSourcePublication, ...]:
        return tuple(
            entry.source_publication
            for entry in self.reports
            if entry.source_publication is not None
        )


def _portal_index_items(payload: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    for key in ("reports", "report_index", "reportIndex", "entries", "items"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            nested = _portal_index_items(value)
            if nested:
                return nested
        items = tuple(item for item in _sequence(value) if isinstance(item, Mapping))
        if items:
            return cast(tuple[Mapping[str, object], ...], items)
    return ()


def _portal_index_entries(
    model: ManagerReadModel,
    payload: Mapping[str, object],
) -> tuple[ReportPortalEntry, ...]:
    entries: list[ReportPortalEntry] = []
    for item in _portal_index_items(payload):
        clean = dict(item)
        for key in ("reports", "report_index", "reportIndex", "entries", "items"):
            clean.pop(key, None)
        nested_report = _mapping(clean.get("report"))
        if nested_report is not None:
            clean = {**clean, **nested_report}
        item_model = ManagerReadModel(
            data=cast(JSONValue, clean),
            source_refs=model.source_refs,
            as_of=model.as_of,
            snapshot_token=model.snapshot_token,
            derivation=model.derivation,
            availability=model.availability,
            errors=model.errors,
        )
        parsed = PortalViewModel.from_read_model(item_model)
        entries.append(
            ReportPortalEntry(
                report_id=parsed.report_id,
                title=parsed.title,
                source_publication=parsed.source_publication,
                generated_artifact=parsed.generated_artifact,
                artifact_state=parsed.artifact_state,
            )
        )
    return tuple(entries)


def _portal_state(
    model: ManagerReadModel,
    payload: Mapping[str, object],
    source_publication: ReportSourcePublication | None,
    artifact: GeneratedReportArtifact | None,
) -> PortalArtifactState:
    status = model.availability.status
    if status is ReadModelStatus.API_UNAVAILABLE:
        return PortalArtifactState.API_UNAVAILABLE
    if status is ReadModelStatus.INTEGRITY_FAILURE:
        return PortalArtifactState.INTEGRITY_FAILURE
    if status is ReadModelStatus.MISSING:
        return PortalArtifactState.MISSING
    explicit = _explicit_artifact_state(payload)
    if explicit is not None:
        return explicit
    if artifact is not None:
        verify = _normalise(artifact.verify_status)
        if verify in {"failed", "failure", "invalid", "digest_mismatch"}:
            return PortalArtifactState.INTEGRITY_FAILURE
        if source_publication is None or (
            status is ReadModelStatus.KNOWN and not model.availability.complete
        ):
            return PortalArtifactState.PARTIAL
        return PortalArtifactState.READY
    if source_publication is not None:
        return PortalArtifactState.NOT_GENERATED
    if status is ReadModelStatus.KNOWN and not model.availability.complete:
        return PortalArtifactState.PARTIAL
    if status is not ReadModelStatus.MISSING:
        # A blocked/stale/incomparable read is not evidence that Portal metadata
        # was never published; keep the local state non-empty while the shared
        # status block carries the source-level limitation.
        return PortalArtifactState.PARTIAL
    return PortalArtifactState.MISSING


def _source_link(
    source: ReportSourcePublication | None,
    context: str | Mapping[str, object] | None,
    *,
    report_id: str | None,
) -> str | None:
    if source is None:
        return None
    return context_link(
        context,
        view="portal",
        report_id=report_id,
        source_publication_id=source.publication_id,
    )


def _artifact_link(
    artifact: GeneratedReportArtifact | None,
    context: str | Mapping[str, object] | None,
    *,
    report_id: str | None,
) -> str | None:
    if artifact is None:
        return None
    return context_link(context, view="portal", report_id=report_id, artifact_id=artifact.artifact_id)


def _is_portal_fixture(model: ManagerReadModel) -> bool:
    """Recognise only the shipped synthetic Portal envelope for display translation."""

    return model.derivation.version == "report-source-fixture-v0" and all(
        source.owner == "strategy-reporting"
        and source.schema == "strategy-reporting.report-source.v0"
        and source.revision == "fixture-v0"
        and source.locator.startswith("fixture://strategy-reporting/")
        for source in model.source_refs
    )


_FIXTURE_TEXT_KEYS: Mapping[str, str] = {
    "Fixture Strategy Reporting source publication": "l5.portal.fixture.source_title",
    "Fixture static Strategy Report": "l5.portal.fixture.artifact_title",
}

_FIXTURE_STATUS_KEYS: Mapping[str, str] = {
    "No Strategy Reporting report source is recorded in the requested scope.": "l5.portal.fixture.missing_reason",
    "The approved public report-source API is unavailable in this environment.": "l5.portal.fixture.api_reason",
    "No private SQLite or filesystem fallback is permitted for Portal metadata.": "l5.portal.fixture.api_error",
    "The generated artifact failed its declared integrity verification.": "l5.portal.fixture.integrity_reason",
    "The published artifact digest does not match the declared digest.": "l5.portal.fixture.integrity_error",
    "The source publication is available, but no generated artifact is published.": "l5.portal.fixture.not_generated_reason",
    "The static artifact has not been generated; no rebuild was triggered.": "l5.portal.fixture.not_generated_error",
    "The publication and artifact are present, but renderer verification metadata is incomplete.": "l5.portal.fixture.partial_reason",
    "Renderer version and verification status are not recorded.": "l5.portal.fixture.partial_error",
    "The fixture contains source publication and generated artifact metadata.": "l5.portal.fixture.complete_reason",
}


def _fixture_copy(value: str | None, translator: Translator, *, fixture: bool) -> str | None:
    if value is None or not fixture:
        return None
    key = _FIXTURE_TEXT_KEYS.get(value) or _FIXTURE_STATUS_KEYS.get(value)
    return translator.t(key) if key is not None else None


def _owner_display(
    value: str | None,
    translator: Translator,
    *,
    fixture: bool,
    missing_key: str = "l5.portal.missing_unconfirmed",
    fixture_key: str | None = None,
    opaque: bool = False,
) -> str:
    if value is None:
        return escape(translator.t(missing_key))
    if fixture and fixture_key is not None:
        return escape(translator.t(fixture_key))
    attribute = 'translate="no"' if opaque else 'data-owner-text="true"'
    return f'<span {attribute}>{translator.source_text(value)}</span>'


def _status_label(
    value: str | None,
    translator: Translator,
    *,
    domain: str,
    fixture: bool,
) -> str:
    if value is None:
        return escape(translator.t("l5.portal.missing_unconfirmed"))
    normalized = _normalise(value) or value
    return translator.label(domain, normalized)


def _render_publication(
    publication: ReportSourcePublication | None,
    *,
    query_context: str | Mapping[str, object] | None,
    report_id: str | None,
    translator: Translator,
    fixture: bool,
) -> str:
    if publication is None:
        return (
            '<article class="portal-source-publication" data-source-publication-state="missing">'
            f"<h2>{escape(translator.t('l5.portal.source.heading'))}</h2>"
            f'<p class="portal-missing">{escape(translator.t("l5.portal.source.missing"))}</p>'
            "</article>"
        )
    internal = _source_link(publication, query_context, report_id=report_id)
    safe_locator = public_locator(publication.locator)
    locator = (
        f'<a class="portal-source-locator" href="{escape(safe_locator, quote=True)}">'
        f'<span translate="no">{translator.source_text(safe_locator)}</span></a>'
        if safe_locator
        else escape(translator.t("l5.portal.missing_unconfirmed"))
    )
    stable = (
        f'<a class="portal-source-link" data-link-kind="source-publication" href="{escape(internal or "#", quote=True)}">'
        f"{escape(translator.t('l5.portal.open_source'))}</a>"
        if internal
        else ""
    )
    return (
        f'<article class="portal-source-publication" data-source-publication-id="{escape(publication.publication_id, quote=True)}" '
        'data-source-publication-state="published">'
        f"<h2>{escape(translator.t('l5.portal.source.heading'))}</h2>"
        "<dl class=\"portal-details\">"
        f'<div><dt>{escape(translator.t("l5.portal.source.publication_id"))}</dt><dd><span translate="no">{translator.source_text(publication.publication_id)}</span></dd></div>'
        f'<div><dt>{escape(translator.t("l5.portal.source.title"))}</dt><dd>{_owner_display(publication.title, translator, fixture=fixture, fixture_key="l5.portal.fixture.source_title")}</dd></div>'
        f'<div><dt>{escape(translator.t("l5.portal.source.version"))}</dt><dd>{_owner_display(publication.version, translator, fixture=fixture, opaque=True)}</dd></div>'
        f'<div><dt>{escape(translator.t("l5.portal.source.revision"))}</dt><dd>{_owner_display(publication.revision, translator, fixture=fixture, opaque=True)}</dd></div>'
        f'<div><dt>{escape(translator.t("l5.portal.source.published_at"))}</dt><dd>{_owner_display(publication.published_at, translator, fixture=fixture, opaque=True)}</dd></div>'
        f'<div><dt>{escape(translator.t("l5.portal.source.locator"))}</dt><dd>{locator}</dd></div>'
        f'<div><dt>{escape(translator.t("l5.portal.source.stable_link"))}</dt><dd>{stable or escape(translator.t("l5.portal.missing_unconfirmed"))}</dd></div>'
        "</dl></article>"
    )


def _render_artifact(
    artifact: GeneratedReportArtifact | None,
    *,
    state: PortalArtifactState,
    query_context: str | Mapping[str, object] | None,
    report_id: str | None,
    translator: Translator,
    fixture: bool,
) -> str:
    if artifact is None:
        message_key = {
            PortalArtifactState.MISSING: "l5.portal.artifact.missing",
            PortalArtifactState.NOT_GENERATED: "l5.portal.artifact.not_generated",
            PortalArtifactState.API_UNAVAILABLE: "l5.portal.artifact.api_unavailable",
        }.get(state, "l5.portal.artifact.unavailable")
        return (
            f'<article class="portal-generated-artifact" data-artifact-state="{state.value}">'
            f"<h2>{escape(translator.t('l5.portal.artifact.heading'))}</h2>"
            f'<p class="portal-missing">{escape(translator.t(message_key))}</p>'
            "</article>"
        )
    internal = _artifact_link(artifact, query_context, report_id=report_id)
    safe_locator = public_locator(artifact.locator)
    locator = (
        f'<a class="portal-artifact-locator" href="{escape(safe_locator, quote=True)}">'
        f'<span translate="no">{translator.source_text(safe_locator)}</span></a>'
        if safe_locator
        else escape(translator.t("l5.portal.missing_unconfirmed"))
    )
    stable = (
        f'<a class="portal-artifact-link" data-link-kind="generated-artifact" href="{escape(internal or "#", quote=True)}">'
        f"{escape(translator.t('l5.portal.open_artifact'))}</a>"
        if internal
        else ""
    )
    return (
        f'<article class="portal-generated-artifact" data-artifact-id="{escape(artifact.artifact_id, quote=True)}" '
        f'data-artifact-state="{state.value}" '
        f'data-verify-status="{escape(_normalise(artifact.verify_status) or "", quote=True)}" '
        f'data-rebuild-status="{escape(_normalise(artifact.rebuild_status) or "", quote=True)}">'
        f"<h2>{escape(translator.t('l5.portal.artifact.heading'))}</h2>"
        "<dl class=\"portal-details\">"
        f'<div><dt>{escape(translator.t("l5.portal.artifact.id"))}</dt><dd><span translate="no">{translator.source_text(artifact.artifact_id)}</span></dd></div>'
        f'<div><dt>{escape(translator.t("l5.portal.artifact.title"))}</dt><dd>{_owner_display(artifact.title, translator, fixture=fixture, fixture_key="l5.portal.fixture.artifact_title")}</dd></div>'
        f'<div><dt>{escape(translator.t("l5.portal.artifact.locator"))}</dt><dd>{locator}</dd></div>'
        f'<div><dt>{escape(translator.t("l5.portal.artifact.renderer"))}</dt><dd>{_owner_display(artifact.renderer, translator, fixture=fixture, opaque=True)}</dd></div>'
        f'<div><dt>{escape(translator.t("l5.portal.artifact.renderer_version"))}</dt><dd>{_owner_display(artifact.renderer_version, translator, fixture=fixture, opaque=True)}</dd></div>'
        f'<div><dt>{escape(translator.t("l5.portal.artifact.generated_at"))}</dt><dd>{_owner_display(artifact.generated_at, translator, fixture=fixture, opaque=True)}</dd></div>'
        f'<div><dt>{escape(translator.t("l5.portal.artifact.verify_status"))}</dt><dd>{_status_label(artifact.verify_status, translator, domain="l5_portal_verify", fixture=fixture)}</dd></div>'
        f'<div><dt>{escape(translator.t("l5.portal.artifact.rebuild_status"))}</dt><dd>{_status_label(artifact.rebuild_status, translator, domain="l5_portal_rebuild", fixture=fixture)}</dd></div>'
        f'<div><dt>{escape(translator.t("l5.portal.artifact.digest"))}</dt><dd>{_owner_display(artifact.digest, translator, fixture=fixture, opaque=True)}</dd></div>'
        f'<div><dt>{escape(translator.t("l5.portal.artifact.stable_link"))}</dt><dd>{stable or escape(translator.t("l5.portal.missing_unconfirmed"))}</dd></div>'
        "</dl></article>"
    )


def _render_report_index(
    entries: Sequence[ReportPortalEntry],
    *,
    query_context: str | Mapping[str, object] | None,
    translator: Translator,
    fixture: bool,
) -> str:
    if len(entries) <= 1:
        return ""
    rows: list[str] = []
    for entry in entries:
        state_copy = entry.artifact_state.value
        rows.append(
            f'<article class="portal-report-entry" data-report-id="{escape(entry.report_id or "", quote=True)}" '
            f'data-portal-state="{escape(state_copy, quote=True)}">'
            f"<h2>{_owner_display(entry.title or entry.report_id, translator, fixture=fixture, fixture_key='l5.portal.fixture.artifact_title', missing_key='l5.portal.untitled_report', opaque=entry.title is None)}</h2>"
            f"{_render_publication(entry.source_publication, query_context=query_context, report_id=entry.report_id, translator=translator, fixture=fixture)}"
            f"{_render_artifact(entry.generated_artifact, state=entry.artifact_state, query_context=query_context, report_id=entry.report_id, translator=translator, fixture=fixture)}"
            "</article>"
        )
    return f'<section class="portal-report-index" aria-label="{escape(translator.t("l5.portal.report_index"), quote=True)}">' + "".join(rows) + "</section>"


def _fixture_status_model(model: ManagerReadModel, translator: Translator) -> ManagerReadModel:
    """Translate only exact reason/error prose from the shipped fixture envelope."""

    if not _is_portal_fixture(model):
        return model
    reason = _fixture_copy(model.availability.reason, translator, fixture=True)
    errors = tuple(
        replace(error, message=_fixture_copy(error.message, translator, fixture=True) or error.message)
        for error in model.errors
    )
    return replace(
        model,
        availability=replace(model.availability, reason=reason or model.availability.reason),
        errors=errors,
    )


_STATE_COPY_KEYS: Mapping[PortalArtifactState, str] = {
    PortalArtifactState.MISSING: "l5.portal.state.missing",
    PortalArtifactState.NOT_GENERATED: "l5.portal.state.not_generated",
    PortalArtifactState.INTEGRITY_FAILURE: "l5.portal.state.integrity_failure",
    PortalArtifactState.API_UNAVAILABLE: "l5.portal.state.api_unavailable",
    PortalArtifactState.PARTIAL: "l5.portal.state.partial",
    PortalArtifactState.READY: "l5.portal.state.ready",
}


def render_portal(
    view_or_model: PortalViewModel | ManagerReadModel,
    *,
    base_path: str = "/",
    query: str | Mapping[str, object] | None = None,
    query_context: str | Mapping[str, object] | None = None,
    translator: Translator | None = None,
) -> str:
    """Render a read-only Strategy Reporting Portal metadata fragment.

    ``base_path`` is retained for compatibility with other page hooks; query
    context is opaque and only used to construct stable local metadata links.
    No link is an instruction to rebuild, run, publish, or mutate a report.
    """

    selected_translator = page_translator(translator)
    context = (
        query_context if query_context is not None else query if query is not None else base_path
    )
    view = view_or_model if isinstance(view_or_model, PortalViewModel) else PortalViewModel.from_read_model(view_or_model)
    model = view.read_model
    fixture = _is_portal_fixture(model)
    observed = (
        _owner_display(model.as_of, selected_translator, fixture=fixture, opaque=True)
        if model.as_of
        else escape(selected_translator.t("l5.portal.unavailable"))
    )
    snapshot = (
        _owner_display(model.snapshot_token, selected_translator, fixture=fixture, opaque=True)
        if model.snapshot_token
        else escape(selected_translator.t("l5.portal.unavailable"))
    )
    source_ids = (
        f'<span translate="no">{selected_translator.source_text(selected_translator.join(source.source_id for source in model.source_refs))}</span>'
        if model.source_refs
        else escape(selected_translator.t("l5.portal.none_recorded"))
    )
    state_copy = selected_translator.t(_STATE_COPY_KEYS[view.artifact_state])
    state_label = selected_translator.label("l5_portal_state", view.artifact_state.value)
    operational_state = (
        DisplayState.READY
        if view.artifact_state is PortalArtifactState.READY
        else DisplayState.EMPTY
        if view.artifact_state is PortalArtifactState.MISSING
        else DisplayState.PARTIAL
        if view.artifact_state is PortalArtifactState.PARTIAL
        else DisplayState.ERROR
    )
    report_sections = _render_report_index(
        view.reports,
        query_context=context,
        translator=selected_translator,
        fixture=fixture,
    )
    if not report_sections:
        report_sections = (
            _render_publication(
                view.source_publication,
                query_context=context,
                report_id=view.report_id,
                translator=selected_translator,
                fixture=fixture,
            )
            + _render_artifact(
                view.generated_artifact,
                state=view.artifact_state,
                query_context=context,
                report_id=view.report_id,
                translator=selected_translator,
                fixture=fixture,
            )
        )
    pieces = [
        f'<section class="portal-page" data-integration-hook="portal-view" '
        f'data-portal-state="{view.artifact_state.value}" data-boundary="static-publication-not-canonical">',
        f'<p class="eyebrow">{escape(selected_translator.t("l5.portal.eyebrow"))}</p>',
        f'<h1 class="page-title" data-page-title tabindex="-1">{escape(selected_translator.t("l5.portal.title"))}</h1>',
        f'<p class="page-intro">{escape(selected_translator.t("l5.portal.intro"))}</p>',
        f'<p class="boundary-note" data-boundary="static-publication-not-canonical"><strong>{escape(selected_translator.t("l5.portal.boundary_heading"))}</strong> '
        f'{escape(selected_translator.t("l5.portal.boundary"))}</p>',
        f'<p class="context-line portal-context"><span><strong>{escape(selected_translator.t("l5.portal.report"))}</strong> {_owner_display(view.report_id, selected_translator, fixture=fixture)}</span>'
        f'<span><strong>{escape(selected_translator.t("l5.portal.observed"))}</strong> {observed}</span>'
        f'<span><strong>{escape(selected_translator.t("l5.portal.snapshot"))}</strong> {snapshot}</span>'
        f'<span><strong>{escape(selected_translator.t("l5.portal.sources"))}</strong> {source_ids}</span></p>',
        render_status_block(_fixture_status_model(model, selected_translator), translator=selected_translator),
        f'<section class="portal-state-summary" data-portal-state-summary="{view.artifact_state.value}">'
        f"<strong>{state_label}</strong> {escape(state_copy)}</section>",
        render_operational_state(
            operational_state,
            translator=selected_translator,
            detail=state_copy,
        ),
        report_sections,
        "</section>",
    ]
    return "".join(pieces)


def read_report_source(
    provider: ManagerDataProvider | ReportSourceProvider,
    *,
    snapshot_token: str | None = None,
) -> ManagerReadModel:
    """Read only the approved public report-source resource."""

    return provider.read(REPORT_SOURCE_RESOURCE, snapshot_token=snapshot_token)


def report_source_view(
    provider: ManagerDataProvider | ReportSourceProvider,
    *,
    snapshot_token: str | None = None,
) -> PortalViewModel:
    """Read the approved report-source resource once and build its view model."""

    return PortalViewModel.from_read_model(
        read_report_source(provider, snapshot_token=snapshot_token)
    )


def render_portal_view(
    source: ManagerDataProvider | ReportSourceProvider | ManagerReadModel,
    *,
    snapshot_token: str | None = None,
    base_path: str = "/",
    query: str | Mapping[str, object] | None = None,
    query_context: str | Mapping[str, object] | None = None,
    translator: Translator | None = None,
) -> str:
    """Public S6 integration hook accepting a provider or cached envelope."""

    model = (
        source
        if isinstance(source, ManagerReadModel)
        else report_source_view(source, snapshot_token=snapshot_token).read_model
    )
    return render_portal(
        model,
        base_path=base_path,
        query=query,
        query_context=query_context,
        translator=translator,
    )


# --- deterministic fixtures ---------------------------------------------------


class PortalFixtureState(StrEnum):
    """Synthetic states needed to exercise the Portal read-only contract."""

    COMPLETE = "complete"
    MISSING = "missing"
    EMPTY = "missing"
    NOT_GENERATED = "not_generated"
    PARTIAL = "partial"
    INTEGRITY_FAILURE = "integrity_failure"
    API_UNAVAILABLE = "api_unavailable"


PORTAL_FIXTURE_STATES = tuple(state.value for state in PortalFixtureState)
REPORT_SOURCE_FIXTURE_STATES = PORTAL_FIXTURE_STATES


def _fixture_state(value: PortalFixtureState | str) -> PortalFixtureState:
    if isinstance(value, PortalFixtureState):
        return value
    normalised = _normalise(value)
    if normalised == "empty":
        normalised = "missing"
    if normalised is None:
        raise ValueError(f"unknown Portal fixture state: {value!r}")
    try:
        return PortalFixtureState(normalised)
    except ValueError as exc:
        raise ValueError(f"unknown Portal fixture state: {value!r}") from exc


def _fixture_source(source_id: str, locator: str, *, kind: str) -> SourceReference:
    return SourceReference(
        source_id=source_id,
        owner="strategy-reporting",
        kind=kind,
        locator=locator,
        schema="strategy-reporting.report-source.v0",
        revision="fixture-v0",
    )


def _fixture_envelope(
    *,
    data: Mapping[str, object],
    source_refs: tuple[SourceReference, ...],
    as_of: str | None,
    snapshot_token: str | None,
    status: ReadModelStatus,
    complete: bool,
    reason: str,
    errors: tuple[ReadModelError, ...] = (),
    retryable: bool = False,
) -> ManagerReadModel:
    return ManagerReadModel(
        data=cast(JSONValue, dict(data)),
        source_refs=source_refs,
        as_of=as_of,
        snapshot_token=snapshot_token,
        derivation=Derivation(
            kind="direct",
            inputs=tuple(source.source_id for source in source_refs),
            version="report-source-fixture-v0",
        ),
        availability=Availability(
            status=status,
            complete=complete,
            reason=reason,
            retryable=retryable,
        ),
        errors=errors,
    )


def build_portal_fixture(state: PortalFixtureState | str = PortalFixtureState.COMPLETE) -> ManagerReadModel:
    """Build deterministic Strategy Reporting metadata without storage access."""

    selected = _fixture_state(state)
    source = _fixture_source(
        "report-source-publication-fixture-1",
        "fixture://strategy-reporting/source/publication-1",
        kind="static-source-publication",
    )
    artifact_source = _fixture_source(
        "report-generated-artifact-fixture-1",
        "fixture://strategy-reporting/artifact/report-1/index.html",
        kind="static-generated-artifact",
    )
    publication: dict[str, object] = {
        "publication_id": "source-publication-fixture-1",
        "title": "Fixture Strategy Reporting source publication",
        "version": "source-v1",
        "revision": "source-revision-1",
        "locator": source.locator,
        "published_at": "2026-10-03T08:00:00Z",
        "source_ref": source.source_id,
    }
    artifact: dict[str, object] = {
        "artifact_id": "generated-artifact-fixture-1",
        "report_id": "strategy-report-fixture-1",
        "title": "Fixture static Strategy Report",
        "locator": artifact_source.locator,
        "renderer": "strategy-reporting-static",
        "renderer_version": "renderer-v1",
        "generated_at": "2026-10-03T08:30:00Z",
        "verify_status": "verified",
        "rebuild_status": "not_requested",
        "digest": "sha256:fixture-report-artifact-v1",
        "source_publication_id": publication["publication_id"],
    }
    if selected is PortalFixtureState.MISSING:
        return _fixture_envelope(
            data={},
            source_refs=(),
            as_of=None,
            snapshot_token=None,
            status=ReadModelStatus.MISSING,
            complete=False,
            reason="No Strategy Reporting report source is recorded in the requested scope.",
        )
    if selected is PortalFixtureState.API_UNAVAILABLE:
        api_source = _fixture_source(
            "report-source-public-api",
            "fixture://strategy-reporting/public-report-source",
            kind="public-report-source-api",
        )
        return _fixture_envelope(
            data={},
            source_refs=(api_source,),
            as_of=None,
            snapshot_token=None,
            status=ReadModelStatus.API_UNAVAILABLE,
            complete=False,
            reason="The approved public report-source API is unavailable in this environment.",
            retryable=True,
            errors=(
                ReadModelError(
                    code="report_source_api_unavailable",
                    message="No private SQLite or filesystem fallback is permitted for Portal metadata.",
                    source_ref=api_source.source_id,
                    retryable=True,
                ),
            ),
        )
    if selected is PortalFixtureState.INTEGRITY_FAILURE:
        failed_artifact = dict(artifact)
        failed_artifact["verify_status"] = "failed"
        failed_artifact["digest"] = "sha256:fixture-observed-invalid"
        return _fixture_envelope(
            data={
                "report_id": "strategy-report-fixture-1",
                "title": "Fixture Strategy Report",
                "source_publication": publication,
                "generated_artifact": failed_artifact,
            },
            source_refs=(source, artifact_source),
            as_of="2026-10-03T08:31:00Z",
            snapshot_token="report-source-integrity-failure-v0",
            status=ReadModelStatus.INTEGRITY_FAILURE,
            complete=False,
            reason="The generated artifact failed its declared integrity verification.",
            errors=(
                ReadModelError(
                    code="report_artifact_digest_mismatch",
                    message="The published artifact digest does not match the declared digest.",
                    source_ref=artifact_source.source_id,
                    details={
                        "expected": "sha256:fixture-report-artifact-v1",
                        "observed": "sha256:fixture-observed-invalid",
                    },
                ),
            ),
        )
    if selected is PortalFixtureState.NOT_GENERATED:
        return _fixture_envelope(
            data={
                "report_id": "strategy-report-fixture-1",
                "title": "Fixture Strategy Report",
                "source_publication": publication,
                "artifact_state": "not_generated",
            },
            source_refs=(source,),
            as_of="2026-10-03T08:00:00Z",
            snapshot_token="report-source-not-generated-v0",
            status=ReadModelStatus.KNOWN,
            complete=False,
            reason="The source publication is available, but no generated artifact is published.",
            errors=(
                ReadModelError(
                    code="report_artifact_not_generated",
                    message="The static artifact has not been generated; no rebuild was triggered.",
                    source_ref=source.source_id,
                ),
            ),
        )
    if selected is PortalFixtureState.PARTIAL:
        partial_artifact = dict(artifact)
        partial_artifact["renderer_version"] = None
        partial_artifact["verify_status"] = None
        return _fixture_envelope(
            data={
                "report_id": "strategy-report-fixture-1",
                "title": "Fixture Strategy Report",
                "source_publication": publication,
                "generated_artifact": partial_artifact,
            },
            source_refs=(source, artifact_source),
            as_of="2026-10-03T08:30:00Z",
            snapshot_token="report-source-partial-v0",
            status=ReadModelStatus.KNOWN,
            complete=False,
            reason="The publication and artifact are present, but renderer verification metadata is incomplete.",
            errors=(
                ReadModelError(
                    code="report_artifact_metadata_partial",
                    message="Renderer version and verification status are not recorded.",
                    source_ref=artifact_source.source_id,
                ),
            ),
        )
    return _fixture_envelope(
        data={
            "report_id": "strategy-report-fixture-1",
            "title": "Fixture Strategy Report",
            "source_publication": publication,
            "generated_artifact": artifact,
        },
        source_refs=(source, artifact_source),
        as_of="2026-10-03T08:31:00Z",
        snapshot_token="report-source-complete-v0",
        status=ReadModelStatus.KNOWN,
        complete=True,
        reason="The fixture contains source publication and generated artifact metadata.",
    )


build_report_source_fixture = build_portal_fixture
build_report_portal_fixture = build_portal_fixture


@dataclass(frozen=True, slots=True)
class PortalFixtureProvider:
    """Read-only provider for deterministic report-source fixtures."""

    state: PortalFixtureState

    def __init__(self, state: PortalFixtureState | str = PortalFixtureState.COMPLETE) -> None:
        object.__setattr__(self, "state", _fixture_state(state))

    def read(
        self,
        resource: str = REPORT_SOURCE_RESOURCE,
        *,
        snapshot_token: str | None = None,
    ) -> ManagerReadModel:
        if resource != REPORT_SOURCE_RESOURCE:
            raise ValueError(f"Portal fixture does not serve resource {resource!r}")
        del snapshot_token
        return build_portal_fixture(self.state)


ReportSourceFixtureProvider = PortalFixtureProvider


def portal_fixture_provider(
    state: PortalFixtureState | str = PortalFixtureState.COMPLETE,
) -> PortalFixtureProvider:
    """Return a deterministic provider suitable for focused Portal tests."""

    return PortalFixtureProvider(state)


report_source_fixture_provider = portal_fixture_provider
fixture_report_source_provider = portal_fixture_provider
portal_view_model = PortalViewModel
ReportPortalViewModel = PortalViewModel
StrategyReportingPortalViewModel = PortalViewModel
render_report_portal_view = render_portal_view


__all__ = [
    "PORTAL_FIXTURE_STATES",
    "PORTAL_INTEGRATION_HOOK",
    "PORTAL_RESOURCE",
    "REPORTING_PORTAL_RESOURCE",
    "REPORT_SOURCE_FIXTURE_STATES",
    "REPORT_SOURCE_RESOURCE",
    "GeneratedArtifact",
    "GeneratedReportArtifact",
    "PortalArtifactState",
    "PortalFixtureProvider",
    "PortalFixtureState",
    "PortalState",
    "PortalViewModel",
    "RebuildStatus",
    "ReportArtifactState",
    "ReportIndexEntry",
    "ReportPortalEntry",
    "ReportPortalViewModel",
    "ReportRebuildStatus",
    "ReportSourceFixtureProvider",
    "ReportSourceProvider",
    "ReportSourcePublication",
    "ReportVerifyStatus",
    "SourcePublication",
    "StrategyReportingPortalViewModel",
    "VerifyStatus",
    "build_portal_fixture",
    "build_report_portal_fixture",
    "build_report_source_fixture",
    "fixture_report_source_provider",
    "portal_fixture_provider",
    "portal_view_model",
    "read_report_source",
    "render_portal",
    "render_portal_view",
    "render_report_portal_view",
    "report_source_fixture_provider",
    "report_source_view",
]
