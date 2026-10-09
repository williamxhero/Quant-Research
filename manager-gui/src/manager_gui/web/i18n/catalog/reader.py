"""Reader R1-T2 bilingual copy and deterministic template seam.

The Reader projection stores stable explanation keys, not prose.  This module
owns the corresponding zh-CN/en messages and a small typed rendering seam for
those messages.  ``catalog.__init__`` registers this additive namespace exactly
once in the validated process-wide registry.

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

# Generated Reader boundary reasons are opaque tokens in the projection.  They
# are rendered here so page adapters never store or display generated prose.
READER_REASON_KEYS: Mapping[str, str] = MappingProxyType(
    {
        "reader.reason.conclusion_missing": "reader.reason.conclusion_missing",
        "reader.reason.source_reference_missing": "reader.reason.source_reference_missing",
        "reader.reason.source_missing": "reader.reason.source_missing",
        "reader.reason.artifact_missing": "reader.reason.artifact_missing",
        "reader.reason.lineage_relation_missing": "reader.reason.lineage_relation_missing",
        "reader.reason.relation_reason_missing": "reader.reason.relation_reason_missing",
        "reader.reason.scope_incomplete": "reader.reason.scope_incomplete",
        "reader.reason.record_missing": "reader.reason.record_missing",
        "reader.reason.no_comparison": "reader.reason.no_comparison",
        "reader.reason.comparison_equal": "reader.reason.comparison_equal",
        "reader.reason.comparison_different": "reader.reason.comparison_different",
        "reader.reason.comparison_missing": "reader.reason.comparison_missing",
        "reader.reason.comparison_not_comparable": "reader.reason.comparison_not_comparable",
    }
)

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
        "reader.availability.reason": ReaderTemplateSpec(
            "reader.availability.reason", ("text",)
        ),
        **{
            key: ReaderTemplateSpec(key)
            for key in READER_REASON_KEYS.values()
        },
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
    "reader.atlas.question": M(
        "研究过什么、现在走到哪里、还能沿着哪些前沿继续查看？",
        "What was researched, where has it reached, and which frontiers can be followed next?",
    ),
    "reader.atlas.object_heading": M("研究内容", "Research content"),
    "reader.atlas.object": M("研究对象或主题", "Research object or topic"),
    "reader.atlas.question_heading": M("研究问题", "Research question"),
    "reader.atlas.process_heading": M("研究过程", "Research process"),
    "reader.atlas.result_heading": M("当前结果", "Current result"),
    "reader.atlas.scope_heading": M("范围", "Scope"),
    "reader.atlas.unknowns_heading": M("还不知道什么", "What is not known yet"),
    "reader.atlas.evidence_heading": M("证据与入口", "Evidence and entry points"),
    "reader.atlas.metadata": M("总览元数据", "Atlas metadata"),
    "reader.atlas.expert_heading": M("专业研究内容", "Expert research content"),
    "reader.atlas.related_stories": M("相关研究入口", "Related research entries"),
    "reader.atlas.sample": M(
        "编造的示例，不是你的研究记录。",
        "A fabricated example, not your research record.",
    ),
    "reader.atlas.content_unavailable": M(
        "这项内容目前不可用；公开研究记录没有提供它，界面不会仅凭读取状态推断结果。",
        "This content is currently unavailable; the public research record does not provide it, and no result is inferred from read status alone.",
    ),
    "reader.atlas.scope_unknown": M(
        "研究范围目前未记录；不能仅凭读取状态认定范围。",
        "The research scope is currently unavailable; read status alone does not establish it.",
    ),
    "reader.atlas.evidence_unavailable": M(
        "证据入口目前不可用；公开研究记录没有提供可追溯的证据内容。",
        "Evidence entry points are currently unavailable; the public research record provides no traceable evidence content.",
    ),
    "reader.atlas.confirmed": M(
        "此页只列出已命名来源支持的总览声明。",
        "This page lists only overview claims supported by named sources.",
    ),
    "reader.atlas.unknown": M(
        "总览中哪些内容仍未记录、受阻或无法比较？",
        "Which overview items remain unrecorded, blocked, or incomparable?",
    ),
    "reader.atlas.why": M(
        "按来源范围、读取可用性和可复现派生规则解释总览。",
        "Explain the overview through source scope, read availability, and reproducible rules.",
    ),
    "reader.story.question": M(
        "为什么研究、怎样尝试、发生了什么，以及下一步能否追溯？",
        "Why was this researched, what was tried, what happened, and what can be traced next?",
    ),
    "reader.story.confirmed": M(
        "故事链只列出有来源范围的研究声明。",
        "The story chain lists only research claims with a named source scope.",
    ),
    "reader.story.unknown": M(
        "故事链中的哪些阶段尚未记录、尚未评估或不能判断？",
        "Which story stages are unrecorded, unevaluated, or undetermined?",
    ),
    "reader.story.why": M(
        "按故事来源、读取可用性和派生边界解释每个节点。",
        "Explain each story node through its sources, read availability, and derivation boundary.",
    ),
    "reader.genome.question": M(
        "这项策略的结构是什么，以及哪些有效性信息被明确记录？",
        "What is this strategy's structure, and which validity information is explicitly recorded?",
    ),
    "reader.genome.confirmed": M(
        "这里展示数据、信号、股票池、入场、出场、仓位规模和风险控制的来源支持字段。",
        "This shows source-backed fields for data, signals, Universe, entry, exit, sizing, and risk controls.",
    ),
    "reader.genome.unknown": M(
        "缺失字段、未评估条件和未记录资格不会被改写成成功或失败。",
        "Missing fields, unevaluated conditions, and unrecorded qualification are not rewritten as success or failure.",
    ),
    "reader.genome.why": M(
        "结构与有效性分开呈现；每项内容都保留来源范围和阅读器派生边界。",
        "Structure and validity are shown separately; every item retains its source scope and Reader derivation boundary.",
    ),
    "reader.conditions.question": M(
        "哪些条件适用、失效、已记录、未记录或尚未评估？",
        "Which conditions apply, invalidate, are recorded, unrecorded, or not yet evaluated?",
    ),
    "reader.conditions.confirmed": M(
        "这里只显示明确分类的适用条件、失效条件、描述性观察和反例。",
        "Only explicitly classified applicability, invalidation, descriptor, and counterexample records are shown.",
    ),
    "reader.conditions.unknown": M(
        "没有记录不等于条件成立；未评估、阻塞和缺失仍保持各自状态。",
        "No record does not mean a condition holds; unevaluated, blocked, and missing remain distinct states.",
    ),
    "reader.conditions.why": M(
        "条件结论只来自带来源的记录，且记录条件不证明策略有效。",
        "Condition statements come only from sourced records, and recorded conditions do not prove strategy effectiveness.",
    ),
    "reader.revisions.question": M(
        "策略从哪个父版本演进，发生了什么变化，以及有哪些结果和限制？",
        "From which parent revision did the strategy evolve, what changed, and what results and limits were recorded?",
    ),
    "reader.revisions.confirmed": M(
        "演进树只显示属主明确记录的父子关系、变化、原因、证据、结果和限制。",
        "The evolution tree shows only owner-recorded parent/child links, changes, reasons, evidence, results, and limits.",
    ),
    "reader.revisions.unknown": M(
        "未记录的原因不会被推测；修订编号、新旧时间或变化数量不代表更好。",
        "Unrecorded reasons are not inferred; revision numbers, recency, and change counts do not mean better.",
    ),
    "reader.revisions.why": M(
        "每个节点保留身份和来源，并链接到基因组、条件、证据和比较。",
        "Each node retains identity and sources and links to Genome, conditions, Evidence, and comparison.",
    ),
    "reader.comparison.title": M("比较阅读器", "Comparison Reader"),
    "reader.comparison.question": M(
        "两个对象在哪些明确口径上相同、不同、缺失或无法比较？",
        "On which explicit axes are the two objects equal, different, missing, or not comparable?",
    ),
    "reader.comparison.confirmed": M(
        "这里只显示有来源和派生边界支持的逐轴比较；无法比较不会被改写成不同。",
        "Only axis comparisons with named sources and derivation boundaries are shown; not comparable is never rewritten as different.",
    ),
    "reader.comparison.unknown": M(
        "身份、资格、来源生成或快照缺失时，不能声称对象相同或不同。",
        "When identity, eligibility, source generation, or snapshot is missing, equality or difference cannot be claimed.",
    ),
    "reader.comparison.why": M(
        "每个轴保留属主值、来源、可用性和派生规则；没有共同口径时不计算排名或成功率。",
        "Each axis retains owner values, sources, availability, and derivation; no ranking or success rate is calculated without a common basis.",
    ),
    "reader.comparison.axis": M("比较轴", "Comparison axis"),
    "reader.comparison.axis.identity": M("身份", "Identity"),
    "reader.comparison.axis.eligibility": M("资格", "Eligibility"),
    "reader.comparison.axis.source_generation": M("来源生成", "Source generation"),
    "reader.comparison.axis.snapshot": M("快照", "Snapshot"),
    "reader.comparison.axis.data_version": M("数据版本", "Data version"),
    "reader.comparison.axis.universe": M("标的集合", "Universe"),
    "reader.comparison.axis.time_range": M("时间范围", "Time range"),
    "reader.comparison.axis.protocol": M("协议", "Protocol"),
    "reader.comparison.axis.randomness": M("随机性", "Randomness"),
    "reader.comparison.axis.costs": M("成本", "Costs"),
    "reader.comparison.axis.fills": M("成交", "Fills"),
    "reader.comparison.axis.metric_definition": M("指标定义", "Metric definition"),
    "reader.comparison.axis.evidence_sections": M("证据章节", "Evidence sections"),
    "reader.comparison.axis.currency": M("货币", "Currency"),
    "reader.comparison.state": M("状态", "State"),
    "reader.comparison.availability": M("可用性", "Availability"),
    "reader.comparison.left": M("左侧对象", "Left object"),
    "reader.comparison.right": M("右侧对象", "Right object"),
    "reader.comparison.reason": M("这意味着什么", "What this means"),
    "reader.comparison.sources": M("来源与派生", "Source and derivation"),
    "reader.comparison.equal": M("相同", "Equal"),
    "reader.comparison.different": M("不同", "Different"),
    "reader.comparison.missing": M("缺失", "Missing"),
    "reader.comparison.not_comparable": M("无法比较", "Not comparable"),
    "reader.comparison.reason.equal": M(
        "两侧已发布值相同；这不是有效性结论。",
        "The published values match; this is not a validity conclusion.",
    ),
    "reader.comparison.reason.different": M(
        "两侧已发布值不同；差异本身不表示哪一侧更好。",
        "The published values differ; the difference alone does not say which side is better.",
    ),
    "reader.comparison.reason.missing": M(
        "该轴没有两侧都具备的明确记录；没有默认值被补入。",
        "Both sides do not have an explicit record for this axis; no default was filled in.",
    ),
    "reader.comparison.reason.not_comparable": M(
        "该轴的身份、资格、来源生成、快照或协议不一致或缺失，因此拒绝比较。",
        "Identity, eligibility, source generation, snapshot, or protocol is inconsistent or missing, so comparison is refused.",
    ),
    "reader.comparison.no_comparison": M(
        "当前范围没有明确的对象比较记录。",
        "No explicit object comparison is recorded in this scope.",
    ),
    "reader.comparison.no_statistics": M(
        "没有共同分母、时间口径或协议支持；不生成成功率、排名或有效性结论。",
        "Without a common denominator, time basis, or protocol, no success rate, ranking, or validity conclusion is generated.",
    ),
    "reader.comparison.refused": M(
        "比较已拒绝；请先补齐共同身份和口径。",
        "Comparison was refused; establish a shared identity and basis before comparing.",
    ),
    "reader.comparison.expert_heading": M("专业比较字段", "Expert comparison fields"),
    "reader.comparison.raw_heading": M("原始 ManagerReadModel v0", "Raw ManagerReadModel v0"),
    "reader.comparison.related": M("比较相关入口", "Related comparison entry points"),
    "reader.comparison.object_reader": M("对象阅读器", "Object Reader"),
    "reader.comparison.evidence": M("证据阅读器", "Evidence Reader"),
    "reader.comparison.lineage": M("谱系阅读器", "Lineage Reader"),
    "reader.comparison.not_recorded": M("未记录", "Not recorded"),
    "reader.evidence.question": M(
        "当前结论能沿明确记录的证据、来源和制品追溯到哪里？",
        "How far can the current conclusion be traced through explicitly recorded evidence, sources, and artifacts?",
    ),
    "reader.evidence.confirmed": M(
        "候选证据、符合协议的证据和来源只按属主记录的类别呈现。",
        "Candidate evidence, protocol-conforming evidence, and sources are shown only under their owner-recorded classes.",
    ),
    "reader.evidence.unknown": M(
        "未记录的证据、来源、制品或评估状态不能被补成成功或失败。",
        "Unrecorded evidence, sources, artifacts, or evaluation states are not filled in as success or failure.",
    ),
    "reader.evidence.why": M(
        "追溯链保留原始来源、派生方式和可用性；缺口保持为缺口。",
        "The trace keeps original sources, derivation, and availability; gaps remain gaps.",
    ),
    "reader.lineage.title": M("谱系阅读器", "Lineage Reader"),
    "reader.lineage.eyebrow": M("只读谱系追溯", "Read-only lineage trace"),
    "reader.lineage.intro": M(
        "这里保留属主发布的节点、边、来源和快照；相邻记录不会被推断为谱系。",
        "Published nodes, edges, sources, and snapshots are retained here; adjacent records are never inferred as lineage.",
    ),
    "reader.lineage.question": M(
        "当前证据和结论之间有哪些明确发布的谱系关系？",
        "Which lineage relations between the current evidence and conclusion are explicitly published?",
    ),
    "reader.lineage.confirmed": M(
        "只呈现已发布的节点、边和关系类型，不从相邻记录推断关联。",
        "Only published nodes, edges, and relation types are shown; adjacency never infers an association.",
    ),
    "reader.lineage.unknown": M(
        "没有明确边或关联原因时，无法得出谱系结论。",
        "Without an explicit edge or association reason, no lineage conclusion can be drawn.",
    ),
    "reader.lineage.why": M(
        "谱系表逐项标明关系、原因、来源和可用性，并显示缺失边界。",
        "The lineage table separates relation, reason, source, and availability and shows missing boundaries.",
    ),
    "reader.no_conclusion": M(
        "当前没有属主记录支持结论；无法得出结论。",
        "No owner record currently supports a conclusion; no conclusion can be drawn.",
    ),
    "reader.no_gaps": M(
        "当前范围没有额外记录的知识缺口。",
        "No additional knowledge gap is recorded in this scope.",
    ),
    "reader.no_sources": M(
        "来源引用未记录；无法得出结论。",
        "Source references are not recorded; no conclusion can be drawn.",
    ),
    "reader.derivation.unrecorded": M("未记录", "Not recorded"),
    "reader.next_step": M("继续查看下一步", "Continue to the next step"),
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
    "reader.sample.banner.fixed": M(
        "样例数据，不代表真实研究结果",
        "Sample data; not a real research result.",
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
    "reader.availability.reason": M(
        "来源可用性说明：{text}", "Availability note from the source: {text}"
    ),
    "reader.reason.conclusion_missing": M(
        "当前没有属主记录支持结论；无法得出结论。",
        "No owner record currently supports a conclusion; no conclusion can be drawn.",
    ),
    "reader.reason.source_reference_missing": M(
        "来源引用未能在当前来源范围内解析。",
        "A source reference cannot be resolved within the current source scope.",
    ),
    "reader.reason.source_missing": M(
        "来源未发布或当前不可用。", "The source is not published or is unavailable here."
    ),
    "reader.reason.artifact_missing": M(
        "制品未发布或当前不可用。", "The artifact is not published or is unavailable here."
    ),
    "reader.reason.lineage_relation_missing": M(
        "谱系关系未在当前范围内发布。",
        "The lineage relation is not published in the current scope.",
    ),
    "reader.reason.relation_reason_missing": M(
        "关联原因未明确记录；无法得出关联原因。",
        "The association reason is not explicitly recorded; no reason can be concluded.",
    ),
    "reader.reason.scope_incomplete": M(
        "证据与谱系范围不完整；无法得出完整结论。",
        "The evidence and lineage scope is incomplete; no complete conclusion can be drawn.",
    ),
    "reader.reason.record_missing": M(
        "当前范围没有已发布记录。", "No record is published in the current scope."
    ),
    "reader.reason.no_comparison": M(
        "当前没有明确记录支持比较；无法得出比较结论。",
        "No explicit comparison is recorded; no comparison conclusion can be drawn.",
    ),
    "reader.reason.comparison_equal": M(
        "该轴两侧已发布值相同；这不是有效性结论。",
        "The published values on this axis match; this is not a validity conclusion.",
    ),
    "reader.reason.comparison_different": M(
        "该轴两侧已发布值不同；差异本身不表示哪一侧更好。",
        "The published values on this axis differ; the difference alone does not say which side is better.",
    ),
    "reader.reason.comparison_missing": M(
        "该轴没有两侧都具备的明确记录；没有默认值被补入。",
        "Both sides do not have an explicit record for this axis; no default was filled in.",
    ),
    "reader.reason.comparison_not_comparable": M(
        "该轴身份、资格、来源生成、快照或协议不一致或缺失，因此拒绝比较。",
        "Identity, eligibility, source generation, snapshot, or protocol is inconsistent or missing, so comparison is refused.",
    ),
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
    # R4 Memory/Failure Reader copy. Identifiers, reasons and owner text stay
    # runtime values and are never placed in this catalogue.
    "reader.memory.title": M("研究记忆阅读器", "Research Memory Reader"),
    "reader.memory.question": M(
        "当前范围明确记录了哪些研究记忆、关联和政策？",
        "Which research memories, associations, and policies are explicitly recorded in this scope?",
    ),
    "reader.memory.confirmed": M(
        "正式研究记忆、普通失败记录和 GUI 派生模式保持为不同层次。",
        "Formal Research Memory, ordinary failure records, and GUI-derived patterns remain separate layers.",
    ),
    "reader.memory.unknown": M(
        "未记录、未评估或无法追溯的内容不会被补成结论。",
        "Unrecorded, unevaluated, or untraceable content is not filled in as a conclusion.",
    ),
    "reader.memory.why": M(
        "每项内容只来自公开读取模型中明确命名的记录和来源。",
        "Each item comes only from explicitly named records and sources in the public read model.",
    ),
    "reader.failure.title": M("失败追溯阅读器", "Failure Trace Reader"),
    "reader.failure.question": M(
        "哪些失败经验被明确记录，状态和来源能追溯到哪里？",
        "Which failure experiences are explicitly recorded, and how far can their state and sources be traced?",
    ),
    "reader.failure.confirmed": M(
        "成功、失败、阻塞、未评估、过时和不可比较保持各自语义。",
        "Success, failure, blocked, not evaluated, stale, and incomparable remain distinct semantics.",
    ),
    "reader.failure.unknown": M(
        "没有来源或没有明确谱系的记录不能被猜测关联。",
        "Records without sources or explicit lineage are not linked by inference.",
    ),
    "reader.failure.why": M(
        "失败记录、正式记忆和派生模式分别保留其属主边界与派生规则。",
        "Failure records, Formal Memory, and Derived patterns retain their respective owner boundaries and rules.",
    ),
    "reader.memory.empty": M(
        "当前范围没有记录正式研究记忆条目。",
        "No formal Research Memory entries are recorded in this scope.",
    ),
    "reader.failure.empty": M(
        "当前范围没有记录失败记录或派生模式。",
        "No failure records or derived patterns are recorded in this scope.",
    ),
    "reader.memory.missing_source": M("未记录或未确认来源", "Missing or unconfirmed source"),
    "reader.memory.open_record": M("打开记录", "Open record"),
    "reader.memory.layer_label": M("记录层", "Record layer"),
    "reader.failure.state_label": M("记录状态", "Record state"),
    "reader.memory.layer.formal_research_memory": M("正式研究记忆", "Formal Research Memory"),
    "reader.memory.layer.failure_record": M("普通失败记录", "Ordinary failure record"),
    "reader.memory.layer.gui_derived": M("GUI 派生模式", "GUI-derived pattern"),
    "reader.memory.where_produced": M("产生位置与谱系", "Where produced and lineage"),
    "reader.memory.limitations": M("限制与边界", "Limitations and boundaries"),
    "reader.memory.counterexample": M("反例与冲突", "Counterexample and conflict"),
    "reader.memory.not_recorded": M("未明确记录", "Not explicitly recorded"),
    "reader.failure.state.success": M("成功", "Success"),
    "reader.failure.state.failure": M("失败", "Failure"),
    "reader.failure.state.blocked": M("已阻塞", "Blocked"),
    "reader.failure.state.not_evaluated": M("未评估", "Not evaluated"),
    "reader.failure.state.stale": M("已过时", "Stale"),
    "reader.failure.state.incomparable": M("不可比较", "Incomparable"),
    "reader.failure.state.missing": M("未记录", "Missing"),
    "reader.failure.state.unknown": M("未知", "Unknown"),
    "reader.global.unavailable": M(
        "此路由尚未发布专用阅读器投影。",
        "A dedicated Reader projection is not published for this route.",
    ),
    "reader.global.unavailable_detail": M(
        "当前只显示已发布的读取范围；没有属主记录时无法得出结论。",
        "Only the published read scope is shown; without an owner record, no conclusion can be drawn.",
    ),
    "reader.global.route_context": M("阅读器路由", "Reader route"),
}


# Validate this namespace at import time before the central registry registers it.
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


def render_reader_reason(
    translator: Translator,
    reason: str,
    *,
    as_html: bool = False,
) -> str | None:
    """Render a generated boundary token, or return ``None`` for owner text."""

    key = READER_REASON_KEYS.get(reason)
    if key is None:
        return None
    return translator.html(key) if as_html else translator.t(key)


def _claim_source_detail(
    translator: Translator,
    claim: ReaderClaim,
    *,
    as_html: bool,
) -> str:
    """Render the typed source/derivation detail that explains one claim."""

    if claim.kind is ClaimKind.DERIVED:
        rule = claim.derivation.rule
        if rule is None:  # guarded by ReaderClaim, kept explicit for type checkers
            raise ValueError("derived claims require a derivation rule")
        return render_reader_template(
            translator,
            "reader.derivation.detail",
            params=ReaderTemplateParams(value=rule),
            source_refs=claim.source_refs,
            as_html=as_html,
        )
    if claim.is_gap:
        reason = claim.availability.reason
        generated = render_reader_reason(translator, reason, as_html=as_html) if reason else None
        if generated is not None:
            source = render_reader_template(
                translator,
                "reader.source.reference",
                source_refs=claim.source_refs,
                as_html=as_html,
            )
            return f"{generated} {source}"
        key = "reader.gap.detail" if claim.kind is ClaimKind.MISSING else "reader.limitation.detail"
        return render_reader_template(
            translator,
            key,
            params=ReaderTemplateParams(
                value=reason or claim.kind.value,
            ),
            source_refs=claim.source_refs,
            as_html=as_html,
        )
    return render_reader_template(
        translator,
        "reader.source.reference",
        source_refs=claim.source_refs,
        as_html=as_html,
    )


def render_claim_explanation(
    translator: Translator,
    claim: ReaderClaim,
    *,
    as_html: bool = False,
) -> str:
    """Render a fixed claim sentence plus its typed source detail.

    ``OwnerText`` is passed as source text and is never translated.  The
    additional detail is selected by claim kind and can only receive the
    claim's source references, derivation rule, and availability reason.
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
    base = render_reader_template(translator, key, params=params, as_html=as_html)
    detail = _claim_source_detail(translator, claim, as_html=as_html)
    return f"{base} {detail}"


def render_availability_explanation(
    translator: Translator,
    availability: ReaderAvailability | ReaderAvailabilityStatus | str,
    *,
    as_html: bool = False,
) -> str:
    """Render a fixed status explanation and the typed availability reason."""

    reason: str | None = None
    if isinstance(availability, ReaderAvailability):
        status = availability.status
        reason = availability.reason
    else:
        try:
            status = ReaderAvailabilityStatus(availability)
        except (TypeError, ValueError) as exc:
            raise TypeError("availability must be ReaderAvailability or ReaderAvailabilityStatus") from exc
    key = AVAILABILITY_EXPLANATION_KEYS[status]
    base = render_reader_template(
        translator, key, params=ReaderTemplateParams(), as_html=as_html
    )
    if reason is None:
        return base
    generated = render_reader_reason(translator, reason, as_html=as_html)
    if generated is not None:
        return f"{base} {generated}"
    detail = render_reader_template(
        translator,
        "reader.availability.reason",
        params=ReaderTemplateParams(text=reason),
        as_html=as_html,
    )
    return f"{base} {detail}"


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
    "READER_REASON_KEYS",
    "READER_TEMPLATES",
    "SAMPLE_BANNER_KEY",
    "ReaderTemplateParams",
    "ReaderTemplateSpec",
    "reader_catalog_policy_violations",
    "render_availability_explanation",
    "render_claim_explanation",
    "render_projection_summary",
    "render_reader_reason",
    "render_reader_template",
    "render_summary",
]
