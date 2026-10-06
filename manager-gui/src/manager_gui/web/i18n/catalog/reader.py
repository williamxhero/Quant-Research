"""Reader R1-T2 bilingual copy and deterministic template seam.

The Reader projection stores stable explanation keys, not prose.  This module
owns the corresponding zh-CN/en messages and a small typed rendering seam for
those messages.  It is intentionally *not* imported by ``catalog.__init__``:
R1-T4 is the integration boundary that will register this additive namespace.

Only values represented by :class:`ReaderTemplateParams` can be supplied to a
Reader template.  Source references are validated ``SourceReference`` values,
never arbitrary prose.  The renderer delegates all copy expansion to the
existing :class:`~manager_gui.web.i18n.translator.Translator`; it does not call
an LLM or infer a research conclusion.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, cast

from manager_gui.models import SourceReference
from manager_gui.reader import (
    ClaimKind,
    ReaderAvailability,
    ReaderAvailabilityStatus,
    ReaderClaim,
    ReaderProjection,
    ReaderSummary,
    TemplateValue,
)

from ..glossary import (
    LATIN_ALLOWLIST,
    PLACEHOLDER_ALLOWLIST,
    find_forbidden_translations,
)
from ..translator import M, TranslationError, Translator, validate_entry

# ruff: noqa: E501 -- bilingual sentence pairs are kept readable at the call site.


# Stable keys consumed by ReaderProjection.explanation_key and SampleData.banner_key.
EXPLANATION_KEYS: Mapping[ClaimKind, str] = MappingProxyType(
    {
        kind: (
            "reader.claim.owner_text"
            if kind is ClaimKind.OWNER_TEXT
            else f"reader.claim.{kind.value.lower()}"
        )
        for kind in ClaimKind
    }
)

# Availability has three machine states that do not have a one-to-one ClaimKind.
# The remaining states deliberately reuse their claim explanation, keeping one
# deterministic sentence for each public gap/truth category.
AVAILABILITY_EXPLANATION_KEYS: Mapping[ReaderAvailabilityStatus, str] = MappingProxyType(
    {
        ReaderAvailabilityStatus.KNOWN: EXPLANATION_KEYS[ClaimKind.KNOWN],
        ReaderAvailabilityStatus.DERIVED: EXPLANATION_KEYS[ClaimKind.DERIVED],
        ReaderAvailabilityStatus.INTERPRETED: EXPLANATION_KEYS[ClaimKind.INTERPRETED],
        ReaderAvailabilityStatus.MISSING: EXPLANATION_KEYS[ClaimKind.MISSING],
        ReaderAvailabilityStatus.BLOCKED: EXPLANATION_KEYS[ClaimKind.BLOCKED],
        ReaderAvailabilityStatus.STALE: EXPLANATION_KEYS[ClaimKind.STALE],
        ReaderAvailabilityStatus.INCOMPARABLE: EXPLANATION_KEYS[ClaimKind.INCOMPARABLE],
        ReaderAvailabilityStatus.NOT_EVALUATED: "reader.availability.not_evaluated",
        ReaderAvailabilityStatus.INTEGRITY_FAILURE: "reader.availability.integrity_failure",
        ReaderAvailabilityStatus.API_UNAVAILABLE: "reader.availability.api_unavailable",
    }
)
SAMPLE_BANNER_KEY: Final[str] = "reader.sample.banner"

# These are the only named values a Reader template may receive.  They are
# deliberately a subset of the shared glossary's audited placeholder names.
READER_PLACEHOLDER_NAMES: Final[frozenset[str]] = frozenset(
    {"fixture", "n", "scope", "source_id", "text", "value"}
)


@dataclass(frozen=True, slots=True)
class ReaderTemplateParams:
    """Typed scalar inputs for a fixed Reader catalog template.

    ``text`` is reserved for source/owner text and is never translated.  The
    value is inserted by ``Translator`` as a parameter, so plain text remains
    unchanged and HTML output is escaped exactly once.  Unknown named
    parameters cannot be passed because this is a closed dataclass rather than
    an open ``**kwargs`` mapping.
    """

    fixture: str | None = None
    n: int | None = None
    scope: str | None = None
    source_id: str | None = None
    text: str | None = None
    value: TemplateValue = None

    def __post_init__(self) -> None:
        for name in ("fixture", "scope", "source_id"):
            item = getattr(self, name)
            if item is not None and (not isinstance(item, str) or not item.strip()):
                raise TypeError(f"{name} must be a non-empty string or None")
        if self.text is not None and not isinstance(self.text, str):
            raise TypeError("text must be source text or None")
        if self.n is not None and (not isinstance(self.n, int) or isinstance(self.n, bool)):
            raise TypeError("n must be an integer or None")
        if not isinstance(self.value, (bool, int, float, str, type(None))):
            raise TypeError("value must be a JSON scalar or None")

    def as_mapping(self) -> Mapping[str, TemplateValue]:
        """Return only explicitly supplied values for Translator expansion."""

        values: dict[str, TemplateValue] = {}
        for name in READER_PLACEHOLDER_NAMES:
            item = getattr(self, name)
            if item is not None:
                values[name] = cast(TemplateValue, item)
        return MappingProxyType(values)

    @classmethod
    def from_summary(cls, summary: ReaderSummary) -> ReaderTemplateParams:
        """Convert the v1 scalar summary parameters through the closed type seam."""

        if not isinstance(summary, ReaderSummary):
            raise TypeError("summary must be a ReaderSummary")
        unknown = set(summary.params) - READER_PLACEHOLDER_NAMES
        if unknown:
            raise ValueError(f"unsupported Reader template parameter(s): {sorted(unknown)}")
        try:
            return cls(**dict(summary.params))  # type: ignore[arg-type]
        except TypeError as exc:
            raise ValueError("summary params do not match Reader template parameter types") from exc


@dataclass(frozen=True, slots=True)
class ReaderTemplateSpec:
    """Declared inputs for one deterministic catalog template."""

    key: str
    params: tuple[str, ...] = ()
    source_refs: bool = False
    count_source_refs: bool = False


# The metadata is intentionally explicit.  It prevents a caller from turning
# a catalog lookup into an arbitrary prose generator and gives R1-T4 a stable
# integration/import surface.
READER_TEMPLATES: Mapping[str, ReaderTemplateSpec] = MappingProxyType(
    {
        "reader.sample.banner": ReaderTemplateSpec("reader.sample.banner", ("fixture",)),
        "reader.source.reference": ReaderTemplateSpec(
            "reader.source.reference", ("source_id",), source_refs=True
        ),
        "reader.source.count": ReaderTemplateSpec(
            "reader.source.count", ("n",), source_refs=True, count_source_refs=True
        ),
        "reader.derivation.detail": ReaderTemplateSpec(
            "reader.derivation.detail", ("source_id", "value"), source_refs=True
        ),
        "reader.limitation.detail": ReaderTemplateSpec(
            "reader.limitation.detail", ("source_id", "value"), source_refs=True
        ),
        "reader.gap.detail": ReaderTemplateSpec(
            "reader.gap.detail", ("source_id", "value"), source_refs=True
        ),
        "reader.summary.claim_count": ReaderTemplateSpec(
            "reader.summary.claim_count", ("n",)
        ),
        "reader.summary.gap_count": ReaderTemplateSpec(
            "reader.summary.gap_count", ("n",)
        ),
        "reader.summary.source_note": ReaderTemplateSpec(
            "reader.summary.source_note", ("text",)
        ),
        "reader.claim.owner_text": ReaderTemplateSpec("reader.claim.owner_text", ("text",)),
        "reader.claim.known": ReaderTemplateSpec("reader.claim.known"),
        "reader.claim.derived": ReaderTemplateSpec("reader.claim.derived"),
        "reader.claim.interpreted": ReaderTemplateSpec("reader.claim.interpreted"),
        "reader.claim.missing": ReaderTemplateSpec("reader.claim.missing"),
        "reader.claim.blocked": ReaderTemplateSpec("reader.claim.blocked"),
        "reader.claim.stale": ReaderTemplateSpec("reader.claim.stale"),
        "reader.claim.incomparable": ReaderTemplateSpec("reader.claim.incomparable"),
        "reader.availability.not_evaluated": ReaderTemplateSpec(
            "reader.availability.not_evaluated"
        ),
        "reader.availability.integrity_failure": ReaderTemplateSpec(
            "reader.availability.integrity_failure"
        ),
        "reader.availability.api_unavailable": ReaderTemplateSpec(
            "reader.availability.api_unavailable"
        ),
    }
)


# Reader copy is deliberately complete in both languages.  Glossary references
# keep shared terms such as Known, Derived, fixture and owner consistent.
ENTRIES: Mapping[str, M] = {
    "reader.page_question": M("这页回答什么？", "What does this page answer?"),
    "reader.currently_confirmed": M(
        "当前能确认什么？", "What can currently be confirmed?"
    ),
    "reader.not_yet_known": M("还不知道什么？", "What is not known yet?"),
    "reader.why_this_is_said": M("为什么这样说？", "Why is this stated?"),
    "reader.evidence_entry": M("证据入口", "Evidence entry point"),
    "reader.raw_source": M("原始来源", "Raw source"),
    "reader.as_of": M("截至时间", "As of"),
    "reader.snapshot": M("快照", "Snapshot"),
    "reader.source": M("来源", "Source"),
    "reader.derivation": M("派生方式", "Derivation"),
    "reader.limitation": M("限制", "Limitation"),
    "reader.gap": M("知识缺口", "Knowledge gap"),
    "reader.explanation": M("解释", "Explanation"),
    "reader.claim": M("声明", "Claim"),
    "reader.status": M("状态", "Status"),
    "reader.sample.banner": M(
        "当前显示的是样例数据，不代表真实研究结果：{fixture}",
        "The current view uses sample data and does not represent real research results: {fixture}",
    ),
    "reader.source.reference": M("来源引用：{source_id}", "Source reference: {source_id}"),
    "reader.derivation.detail": M(
        "这项内容由已命名来源按规则 {value} 派生：{source_id}",
        "This item is derived from the named source by rule {value}: {source_id}",
    ),
    "reader.limitation.detail": M(
        "限制（来源：{source_id}）：{value}",
        "Limitation (source: {source_id}): {value}",
    ),
    "reader.gap.detail": M(
        "知识缺口（来源：{source_id}）：{value}",
        "Knowledge gap (source: {source_id}): {value}",
    ),
    "reader.source.count": M(
        "当前范围有 {n} 条来源引用；数量不表示证据强度。",
        {
            "one": "There is {n} source reference in this scope; the count is not evidence strength.",
            "other": "There are {n} source references in this scope; the count is not evidence strength.",
        },
    ),
    "reader.summary.claim_count": M(
        "当前引用了 {n} 条带来源的陈述；数量不表示研究成功或结论已验证。",
        {
            "one": "This summary references {n} sourced claim; the count establishes neither research success nor a verified conclusion.",
            "other": "This summary references {n} sourced claims; the count establishes neither research success nor a verified conclusion.",
        },
    ),
    "reader.summary.gap_count": M(
        "当前引用了 {n} 项知识缺口；无法判断的内容不视为失败。",
        {
            "one": "This summary references {n} knowledge gap; an undetermined result is not treated as a failure.",
            "other": "This summary references {n} knowledge gaps; an undetermined result is not treated as a failure.",
        },
    ),
    "reader.availability.not_evaluated": M(
        "当前来源范围尚未评估；未评估不表示成功或失败。",
        "The source scope has not been evaluated; not evaluated means neither success nor failure.",
    ),
    "reader.availability.integrity_failure": M(
        "来源未通过完整性核验；这不是研究失败的结论。",
        "The source failed integrity verification; this is not a conclusion that the research failed.",
    ),
    "reader.availability.api_unavailable": M(
        "批准的公开读取 API 当前不可用；无法读取不表示没有记录。",
        "The approved public read API is unavailable; an unreadable source is not an empty record.",
    ),
    "reader.summary.source_note": M("来源说明：{text}", "Source note: {text}"),
    # Every key below is referenced by ReaderClaim.explanation_key.  None of
    # these messages turns an absence or interpretation into a success/failure.
    "reader.claim.known": M(
        "系统记录到这项内容；状态为{term:known}不等于已经核实。",
        "The system records this item; a {term:known} status does not by itself mean it was verified.",
    ),
    "reader.claim.derived": M(
        "这是按已命名输入和规则可复现地计算的 GUI 派生视图，不是新的属主事实。",
        "This is a reproducible GUI-derived view computed from named inputs and a named rule, not a new owner fact.",
    ),
    "reader.claim.interpreted": M(
        "这是来源发布的解读，不是新的属主事实。",
        "This is an interpretation published by the source, not a new owner fact.",
    ),
    "reader.claim.missing": M(
        "预期内容尚未记录；这不表示内容不存在。",
        "The expected content is not recorded yet; this does not mean it does not exist.",
    ),
    "reader.claim.blocked": M(
        "当前无法判断，因为公开读取受到策略、权限、能力或数据关口阻塞。",
        "A determination is currently blocked by a policy, permission, capability, or data gate on the public read seam.",
    ),
    "reader.claim.stale": M(
        "这项内容曾可使用，但输入、软件包或政策已经变化；当前不能把它当作最新内容。",
        "This item was once usable, but its inputs, package, or policy changed; it cannot be treated as current.",
    ),
    "reader.claim.incomparable": M(
        "请求的比较轴不完整或不兼容，因此无法作出比较判断。",
        "The requested comparison axes are incomplete or incompatible, so no comparison determination can be made.",
    ),
    "reader.claim.owner_text": M(
        "以下是属主原文；界面不会翻译或改写：{text}",
        "The following is owner text; the interface does not translate or rewrite it: {text}",
    ),
    # A second namespace-shaped set gives page code stable copy keys while the
    # label namespace remains available to Translator.label().
    "reader.mode.reader": M("阅读模式", "Reader"),
    "reader.mode.expert": M("专业模式", "Expert"),
    "reader.mode.raw": M("原始模式", "Raw"),
    "reader.mode.reader_description": M(
        "阅读模式显示可复现的人话解释。", "Reader mode shows reproducible plain-language explanations."
    ),
    "reader.mode.expert_description": M(
        "专业模式保留字段、表格和证据入口。", "Expert mode retains fields, tables, and evidence entry points."
    ),
    "reader.mode.raw_description": M(
        "原始模式显示原始 JSON、来源引用和摘要哈希。",
        "Raw mode shows raw JSON, source references, and digest hashes.",
    ),
    "label.reader_source": M("{term:source}", "{term:source}"),
    "label.reader_derivation": M("{term:derivation}", "{term:derivation}"),
    "label.reader_limitation": M("限制", "Limitation"),
    "label.reader_gap": M("知识缺口", "Knowledge gap"),
    "label.reader_explanation": M("解释", "Explanation"),
    "label.reader_claim": M("声明", "Claim"),
    "label.reader_status": M("状态", "Status"),
    "label.reader_owner_text": M("{term:owner}原文", "Owner text"),
    "label.reader_sample": M("{term:fixture}", "Sample data"),
    "label.reader_as_of": M("{term:as_of}", "{term:as_of}"),
    "label.reader_snapshot": M("{term:snapshot}", "{term:snapshot}"),
    "label.reader_source_reference": M("{term:source_reference}", "{term:source_reference}"),
    "label.reader_claim_kind.known": M("{term:known}", "{term:known}"),
    "label.reader_claim_kind.derived": M("{term:derived}", "{term:derived}"),
    "label.reader_claim_kind.interpreted": M("{term:interpreted}", "{term:interpreted}"),
    "label.reader_claim_kind.missing": M("{term:missing}", "{term:missing}"),
    "label.reader_claim_kind.blocked": M("{term:blocked}", "{term:blocked}"),
    "label.reader_claim_kind.stale": M("{term:stale}", "{term:stale}"),
    "label.reader_claim_kind.incomparable": M("{term:incomparable}", "{term:incomparable}"),
    "label.reader_claim_kind.owner_text": M("{term:owner}原文", "Owner text"),
    "label.reader_availability.known": M("{term:known}", "{term:known}"),
    "label.reader_availability.derived": M("{term:derived}", "{term:derived}"),
    "label.reader_availability.interpreted": M("{term:interpreted}", "{term:interpreted}"),
    "label.reader_availability.missing": M("{term:missing}", "{term:missing}"),
    "label.reader_availability.blocked": M("{term:blocked}", "{term:blocked}"),
    "label.reader_availability.stale": M("{term:stale}", "{term:stale}"),
    "label.reader_availability.incomparable": M("{term:incomparable}", "{term:incomparable}"),
    "label.reader_availability.not_evaluated": M("未评估", "Not evaluated"),
    "label.reader_availability.integrity_failure": M("完整性校验失败", "Integrity failure"),
    "label.reader_availability.api_unavailable": M("API 不可用", "API unavailable"),
    "label.reader_mode.reader": M("阅读模式", "Reader"),
    "label.reader_mode.expert": M("专业模式", "Expert"),
    "label.reader_mode.raw": M("原始模式", "Raw"),
}


# Validate this standalone namespace at import time, without registering it in
# the process-wide catalog.  R1-T4 may safely register ENTRIES after importing it.
for _key, _message in ENTRIES.items():
    validate_entry(_key, _message)


_PLACEHOLDER_TOKEN = re.compile(r"\{(?:term:[^{}]+|[A-Za-z_][A-Za-z0-9_]*)\}")
_LATIN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*")
_LATIN_WORDS = frozenset(
    token
    for phrase in LATIN_ALLOWLIST
    for token in _LATIN_TOKEN.findall(phrase)
)


def _catalog_texts(catalog: Mapping[str, M]) -> Sequence[tuple[str, str, str]]:
    texts: list[tuple[str, str, str]] = []
    for key, message in catalog.items():
        texts.append((key, "zh", message.zh))
        if isinstance(message.en, str):
            texts.append((key, "en", message.en))
        else:
            texts.extend((key, f"en.{form}", text) for form, text in message.en.items())
    return tuple(texts)


def reader_catalog_policy_violations(
    catalog: Mapping[str, M] = ENTRIES,
) -> tuple[tuple[str, str, str], ...]:
    """Return forbidden glossary or unapproved Latin text in Reader Chinese copy.

    Placeholder and glossary tokens are removed before the Latin audit because
    they are not rendered as literal Chinese UI text.  Owner and machine values
    are runtime parameters and are intentionally outside this catalog audit.
    """

    violations = list(find_forbidden_translations(catalog))
    for key, field, text in _catalog_texts(catalog):
        if field != "zh":
            continue
        visible = _PLACEHOLDER_TOKEN.sub("", text)
        for token in _LATIN_TOKEN.findall(visible):
            if token not in _LATIN_WORDS:
                violations.append((key, field, token))
    return tuple(violations)


def _validated_source_refs(
    source_refs: Sequence[SourceReference],
) -> tuple[SourceReference, ...]:
    if isinstance(source_refs, (str, bytes, bytearray)):
        raise TypeError("source_refs must be SourceReference values")
    refs = tuple(source_refs)
    if not all(isinstance(ref, SourceReference) for ref in refs):
        raise TypeError("source_refs must contain SourceReference values")
    if len({ref.source_id for ref in refs}) != len(refs):
        raise ValueError("source_refs must have unique source_id values")
    return refs


def _render_params(
    spec: ReaderTemplateSpec,
    params: ReaderTemplateParams,
    source_refs: tuple[SourceReference, ...],
    translator: Translator,
) -> Mapping[str, TemplateValue]:
    values = dict(params.as_mapping())
    if spec.source_refs:
        if not source_refs:
            raise ValueError(f"{spec.key} requires at least one source reference")
        if "source_id" in spec.params:
            joined = translator.join(ref.source_id for ref in source_refs)
            if params.source_id is not None and params.source_id != joined:
                raise ValueError("source_id must match the supplied source_refs")
            values["source_id"] = joined
        if spec.count_source_refs:
            if params.n is None:
                raise ValueError(f"{spec.key} requires a count")
            if params.n != len(source_refs):
                raise ValueError("n must match source_refs")
    elif source_refs:
        raise ValueError(f"{spec.key} does not accept source_refs")

    expected = set(spec.params)
    supplied = set(values)
    missing = expected - supplied
    extra = supplied - expected
    if missing:
        raise ValueError(f"{spec.key} is missing typed parameter(s): {sorted(missing)}")
    if extra:
        raise ValueError(f"{spec.key} received unsupported parameter(s): {sorted(extra)}")
    return MappingProxyType(values)


def render_reader_template(
    translator: Translator,
    key: str,
    *,
    params: ReaderTemplateParams | None = None,
    source_refs: Sequence[SourceReference] = (),
    as_html: bool = False,
) -> str:
    """Render one declared Reader template from typed values and source refs.

    The key must be in ``READER_TEMPLATES`` and all required named inputs must
    be supplied by ``ReaderTemplateParams``.  There is no open-ended prose or
    ``**kwargs`` path.  ``as_html=True`` uses the Translator's escaping path.
    """

    if not isinstance(translator, Translator):
        raise TypeError("translator must be a Translator")
    spec = READER_TEMPLATES.get(key)
    if spec is None:
        raise TranslationError(f"unknown Reader template key: {key!r}")
    selected = ReaderTemplateParams() if params is None else params
    if not isinstance(selected, ReaderTemplateParams):
        raise TypeError("params must be ReaderTemplateParams")
    refs = _validated_source_refs(source_refs)
    values = _render_params(spec, selected, refs, translator)
    if "n" in spec.params:
        count = cast(int, values["n"])
        if as_html:
            return translator.html(key, **dict(values))
        plain_values = dict(values)
        plain_values.pop("n")
        return translator.count(key, count, **plain_values)
    if as_html:
        return translator.html(key, **dict(values))
    return translator.t(key, **dict(values))


def render_claim_explanation(
    translator: Translator,
    claim: ReaderClaim,
    *,
    as_html: bool = False,
) -> str:
    """Render the stable explanation for one typed Reader claim.

    ``OwnerText`` is passed as source text and is never translated.  Every
    other claim kind has a fixed catalog sentence, so a missing/blocked/stale
    claim cannot be rewritten as a guessed outcome.
    """

    if not isinstance(claim, ReaderClaim):
        raise TypeError("claim must be a ReaderClaim")
    key = claim.explanation_key
    if key not in EXPLANATION_KEYS.values() or key not in READER_TEMPLATES:
        raise TranslationError(f"claim explanation key is not registered: {key!r}")
    if claim.kind is ClaimKind.OWNER_TEXT:
        if not isinstance(claim.value, str):
            raise TypeError("OwnerText claim value must be source text")
        params = ReaderTemplateParams(text=claim.value)
    else:
        params = ReaderTemplateParams()
    return render_reader_template(translator, key, params=params, as_html=as_html)


def render_availability_explanation(
    translator: Translator,
    availability: ReaderAvailability | ReaderAvailabilityStatus | str,
    *,
    as_html: bool = False,
) -> str:
    """Render one fixed explanation for a typed availability status."""

    if isinstance(availability, ReaderAvailability):
        status = availability.status
    else:
        try:
            status = ReaderAvailabilityStatus(availability)
        except (TypeError, ValueError) as exc:
            raise TypeError("availability must be ReaderAvailability or ReaderAvailabilityStatus") from exc
    key = AVAILABILITY_EXPLANATION_KEYS[status]
    return render_reader_template(
        translator, key, params=ReaderTemplateParams(), as_html=as_html
    )


def render_summary(
    translator: Translator,
    summary: ReaderSummary,
    *,
    as_html: bool = False,
) -> str:
    """Render a v1 summary through the closed Reader parameter type."""

    if not isinstance(summary, ReaderSummary):
        raise TypeError("summary must be a ReaderSummary")
    return render_reader_template(
        translator,
        summary.template_key,
        params=ReaderTemplateParams.from_summary(summary),
        as_html=as_html,
    )


def render_projection_summary(
    translator: Translator,
    projection: ReaderProjection,
    *,
    as_html: bool = False,
) -> str | None:
    """Render the optional summary in an exact ReaderProjection."""

    if not isinstance(projection, ReaderProjection):
        raise TypeError("projection must be a ReaderProjection")
    return (
        None
        if projection.summary is None
        else render_summary(translator, projection.summary, as_html=as_html)
    )


def _validate_reader_policy() -> None:
    names: set[str] = set()
    for spec in READER_TEMPLATES.values():
        names.update(spec.params)
    if not names <= READER_PLACEHOLDER_NAMES:
        raise TranslationError(f"Reader template names are not typed: {sorted(names)}")
    if not READER_PLACEHOLDER_NAMES <= PLACEHOLDER_ALLOWLIST:
        raise TranslationError("Reader placeholders must use the shared glossary allowlist")
    violations = reader_catalog_policy_violations()
    if violations:
        raise TranslationError(f"Reader catalog policy violation(s): {violations}")


_validate_reader_policy()


__all__ = [
    "AVAILABILITY_EXPLANATION_KEYS",
    "ENTRIES",
    "EXPLANATION_KEYS",
    "READER_PLACEHOLDER_NAMES",
    "READER_TEMPLATES",
    "SAMPLE_BANNER_KEY",
    "ReaderTemplateParams",
    "ReaderTemplateSpec",
    "reader_catalog_policy_violations",
    "render_availability_explanation",
    "render_claim_explanation",
    "render_projection_summary",
    "render_reader_template",
    "render_summary",
]
