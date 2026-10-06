"""Deterministic Reader v1 copy templates.

Every method selects a fixed catalog key and accepts only an existing Reader/v0
value type.  Owner text and raw machine values have explicit pass-through methods;
no method accepts generated prose and this module has no model or LLM dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from manager_gui.models import Derivation, SourceReference
from manager_gui.web.i18n import Translator

from ..web.i18n.catalog.reader import (
    READER_CLAIM_EXPLANATION_KEYS,
    READER_LABEL_KEYS,
    READER_MODE_LABEL_KEYS,
    READER_SECTION_KEYS,
)
from .models import (
    SAMPLE_BANNER_KEY,
    ClaimKind,
    FrozenJSON,
    ProjectionMode,
    ReaderClaim,
    ReaderProjection,
    ReaderSummary,
    SampleData,
)


class ReaderSection(StrEnum):
    """The four fixed Reader page sections."""

    QUESTION = "question"
    KNOWN = "known"
    UNKNOWNS = "unknowns"
    WHY = "why"


@dataclass(frozen=True, slots=True)
class ReaderTemplates:
    """A locale-bound facade over the fixed Reader copy catalog."""

    translator: Translator

    def section(self, section: ReaderSection | str) -> str:
        """Render one fixed page-section heading."""

        selected = _section(section)
        return self.translator.t(READER_SECTION_KEYS[selected.value])

    def mode_label(self, mode: ProjectionMode | str) -> str:
        """Render the stable Reader/Expert/Raw mode label."""

        try:
            selected = ProjectionMode(mode)
        except ValueError as exc:
            raise ValueError(f"unsupported Reader mode: {mode!r}") from exc
        return self.translator.t(READER_MODE_LABEL_KEYS[selected.value])

    def claim_label(self, claim: ReaderClaim | ClaimKind) -> str:
        """Render a closed claim-kind label without translating its value."""

        kind = claim.kind if isinstance(claim, ReaderClaim) else ClaimKind(claim)
        slug = _claim_slug(kind)
        key = f"label.reader_claim.{slug}"
        return self.translator.t(key)

    def claim_explanation(self, claim: ReaderClaim) -> str:
        """Render the stable explanation selected by a validated claim kind."""

        _require_type(claim, ReaderClaim, "claim")
        return self.translator.t(READER_CLAIM_EXPLANATION_KEYS[_claim_slug(claim.kind)])

    def claim_explanations(self, projection: ReaderProjection) -> tuple[str, ...]:
        """Render explanations in projection order, without inventing claim text."""

        _require_type(projection, ReaderProjection, "projection")
        claims = (*projection.claims, *projection.limitations, *projection.unknowns)
        return tuple(self.claim_explanation(claim) for claim in claims)

    def sample_banner(self, sample_data: SampleData) -> str:
        """Render the explicit sample-data warning; no sample status is inferred."""

        _require_type(sample_data, SampleData, "sample_data")
        return self.translator.t(SAMPLE_BANNER_KEY)

    def source_label(self) -> str:
        """Render the source label."""

        return self.translator.t(READER_LABEL_KEYS["source"])

    def source_reference_label(self) -> str:
        """Render the source-reference label."""

        return self.translator.t(READER_LABEL_KEYS["source_refs"])

    def derivation_label(self) -> str:
        """Render the derivation label."""

        return self.translator.t(READER_LABEL_KEYS["derivation"])

    def limitation_label(self) -> str:
        """Render the limitation label."""

        return self.translator.t(READER_LABEL_KEYS["limitation"])

    def gap_label(self) -> str:
        """Render the knowledge-gap label."""

        return self.translator.t(READER_LABEL_KEYS["gap"])

    def source_reference(self, source: SourceReference) -> str:
        """Render a typed source reference while escaping opaque values once."""

        _require_type(source, SourceReference, "source")
        return self.translator.html(
            "reader.source.reference", source_id=source.source_id, href=source.locator
        )

    def source_references(self, sources: tuple[SourceReference, ...]) -> tuple[str, ...]:
        """Render only a tuple of existing typed source references."""

        _require_sources(sources)
        return tuple(self.source_reference(source) for source in sources)

    def source_count(self, sources: tuple[SourceReference, ...]) -> str:
        """Render a count from typed source references."""

        _require_sources(sources)
        return self.translator.count("reader.source.count", len(sources))

    def derivation(self, derivation: Derivation) -> str:
        """Render a direct, derived or interpreted v0 derivation."""

        _require_type(derivation, Derivation, "derivation")
        if derivation.kind == "direct":
            return self.translator.t("reader.derivation.direct")
        if derivation.kind == "derived":
            key = "reader.derivation.derived"
        elif derivation.kind == "interpreted":
            key = "reader.derivation.interpreted"
        else:  # The v0 constructor currently rejects this; keep the facade closed.
            raise ValueError(f"unsupported derivation kind: {derivation.kind!r}")
        if derivation.rule is None or derivation.version is None:
            raise ValueError("non-direct derivations require a rule and version")
        return self.translator.html(key, name=derivation.rule, value=derivation.version)

    def summary(self, summary: ReaderSummary, projection: ReaderProjection) -> str:
        """Render one of the fixed summary templates from a typed projection.

        ``ReaderSummary.params`` is intentionally not treated as prose.  These two
        shipped templates derive their count from the projection and accept no
        caller-supplied text, so an arbitrary template key or parameter mapping is
        rejected at this boundary.
        """

        _require_type(summary, ReaderSummary, "summary")
        _require_type(projection, ReaderProjection, "projection")
        if summary.params:
            raise ValueError("Reader summary templates do not accept arbitrary params")
        if summary.template_key == "reader.summary.claim_count":
            count = len(projection.claims)
        elif summary.template_key == "reader.summary.gap_count":
            count = len(projection.limitations) + len(projection.unknowns)
        else:
            raise ValueError(f"unsupported Reader summary template: {summary.template_key!r}")
        if not set(summary.claim_ids) <= {
            claim.claim_id
            for claim in (*projection.claims, *projection.limitations, *projection.unknowns)
        }:
            raise ValueError("summary references claims outside the projection")
        return self.translator.count(summary.template_key, count)

    def owner_text(self, value: str, *, as_html: bool = True) -> str:
        """Keep owner free text unchanged, escaping only at the HTML boundary."""

        if not isinstance(value, str):
            raise TypeError("owner text must be a string")
        return self.translator.source_text(value) if as_html else value

    def claim_value(self, claim: ReaderClaim) -> FrozenJSON:
        """Return source/raw claim data without translating or generating prose."""

        _require_type(claim, ReaderClaim, "claim")
        if claim.kind is ClaimKind.OWNER_TEXT and not isinstance(claim.value, str):
            raise ValueError("OwnerText must retain its original string")
        return claim.value


def _require_type(value: object, expected: type[object], name: str) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{name} must be a {expected.__name__}")


def _require_sources(sources: tuple[SourceReference, ...]) -> None:
    if not isinstance(sources, tuple):
        raise TypeError("sources must be a tuple of SourceReference values")
    if not all(isinstance(source, SourceReference) for source in sources):
        raise TypeError("sources must contain SourceReference values")


def _section(section: ReaderSection | str) -> ReaderSection:
    try:
        return section if isinstance(section, ReaderSection) else ReaderSection(section)
    except ValueError as exc:
        raise ValueError(f"unsupported Reader section: {section!r}") from exc


def _claim_slug(kind: ClaimKind) -> str:
    return "owner_text" if kind is ClaimKind.OWNER_TEXT else kind.value.lower()


def templates(translator: Translator) -> ReaderTemplates:
    """Construct the locale-bound Reader template facade."""

    _require_type(translator, Translator, "translator")
    return ReaderTemplates(translator)


def render_section(section: ReaderSection | str, *, translator: Translator) -> str:
    return templates(translator).section(section)


def render_mode_label(mode: ProjectionMode | str, *, translator: Translator) -> str:
    return templates(translator).mode_label(mode)


def render_claim_explanation(claim: ReaderClaim, *, translator: Translator) -> str:
    return templates(translator).claim_explanation(claim)


def render_sample_banner(sample_data: SampleData, *, translator: Translator) -> str:
    return templates(translator).sample_banner(sample_data)


def render_source_reference(source: SourceReference, *, translator: Translator) -> str:
    return templates(translator).source_reference(source)


def render_derivation(derivation: Derivation, *, translator: Translator) -> str:
    return templates(translator).derivation(derivation)


def render_summary(
    summary: ReaderSummary, projection: ReaderProjection, *, translator: Translator
) -> str:
    return templates(translator).summary(summary, projection)


def preserve_owner_text(value: str, *, translator: Translator, as_html: bool = True) -> str:
    return templates(translator).owner_text(value, as_html=as_html)


def preserve_claim_value(claim: ReaderClaim, *, translator: Translator) -> FrozenJSON:
    return templates(translator).claim_value(claim)


__all__ = [
    "SAMPLE_BANNER_KEY",
    "ReaderSection",
    "ReaderTemplates",
    "preserve_claim_value",
    "preserve_owner_text",
    "render_claim_explanation",
    "render_derivation",
    "render_mode_label",
    "render_sample_banner",
    "render_section",
    "render_source_reference",
    "render_summary",
    "templates",
]
