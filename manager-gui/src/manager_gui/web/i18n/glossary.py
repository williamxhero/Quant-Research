"""Frozen Chinese terminology shared by every Manager GUI catalog.

Catalog text references a term as ``{term:<id>}``, so changing a translation here
updates the whole site.  The registry is deliberately data-only: it has no import
dependency on the catalog or translator modules and can therefore be used while
those modules validate their own entries.

The module also exposes the audit constants used by later catalog tickets and can
be executed as ``python -m manager_gui.web.i18n.glossary`` to print a generated
Markdown review table.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class Term:
    """One frozen term: its English and Chinese forms and spellings to avoid."""

    id: str
    en: str
    zh: str
    zh_short: str | None = None
    note: str | None = None
    forbidden_zh: tuple[str, ...] = ()


def _registry(terms: Iterable[Term]) -> Mapping[str, Term]:
    registry: dict[str, Term] = {}
    for term in terms:
        if term.id in registry:
            raise ValueError(f"duplicate term id: {term.id!r}")
        registry[term.id] = term
    return MappingProxyType(registry)


def _term(
    term_id: str,
    en: str,
    zh: str,
    zh_short: str,
    note: str,
    *forbidden_zh: str,
) -> Term:
    """Build a term while keeping every registered field explicit at the call site."""

    return Term(
        id=term_id,
        en=en,
        zh=zh,
        zh_short=zh_short,
        note=note,
        forbidden_zh=tuple(forbidden_zh),
    )


TERMS: Mapping[str, Term] = _registry(
    (
        # UI and common shell vocabulary.
        _term(
            "manager_gui",
            "Manager GUI",
            "Manager GUI",
            "Manager GUI",
            "品牌名按 #655 第 7 节保留拉丁文，不作意译。",
        ),
        _term(
            "read_only",
            "read-only",
            "只读",
            "只读",
            "沿用 manager-gui README 的只读边界说明。",
        ),
        _term(
            "atlas",
            "Atlas",
            "研究总览",
            "总览",
            "#655 第 7 节将 Atlas 定为研究总览，避免把产品名直接展示给用户。",
        ),
        _term(
            "inspector",
            "Inspector",
            "详情面板",
            "详情",
            "沿用 #655 第 7 节对 Inspector 的界面职责描述。",
        ),
        _term(
            "raw_json",
            "Raw JSON",
            "原始 JSON",
            "原始 JSON",
            "JSON 是 #655 规定的白名单拉丁词，数据载荷保持原样。",
        ),
        _term(
            "snapshot",
            "Snapshot",
            "快照",
            "快照",
            "沿用 manager-gui README 的 source snapshot 语义。",
        ),
        _term(
            "snapshot_token",
            "Snapshot token",
            "快照令牌",
            "令牌",
            "#655 将 snapshot token 视为不透明请求状态而非业务结论。",
        ),
        _term(
            "as_of",
            "As of",
            "截至时间",
            "截至",
            "#655 第 7 节规定 as of 与 observed 统一使用截至时间。",
        ),
        _term(
            "known_at",
            "Known at",
            "系统获知时间",
            "获知时间",
            "沿用 #655 第 7 节对 known at 的系统观测语义。",
        ),
        _term(
            "source",
            "Source",
            "来源",
            "来源",
            "沿用 ManagerReadModel 的 source reference 及来源链路用词。",
        ),
        _term(
            "source_reference",
            "Source reference",
            "来源引用",
            "来源引用",
            "#655 第 7 节把 source reference 作为公开、稳定的来源指针。",
        ),
        _term(
            "provenance",
            "Provenance",
            "溯源信息",
            "溯源",
            "沿用根 README 对来源、记录、制品和谱系关系的溯源表达。",
        ),
        _term(
            "derivation",
            "Derivation",
            "派生方式",
            "派生",
            "沿用 ManagerReadModel v0 的 derivation 字段及 direct/derived 区分。",
        ),
        _term(
            "cursor",
            "Cursor",
            "游标",
            "游标",
            "沿用 Search 与 Lineage 分页合同；游标是请求状态，不是业务证据。",
        ),
        _term(
            "opaque_reference",
            "Opaque reference",
            "不透明引用",
            "不透明引用",
            "#655 明确要求 id、locator 和令牌按不透明引用原样传播。",
        ),
        _term(
            "fixture",
            "fixture",
            "样例数据",
            "样例",
            "#655 规定 fixture 是结构测试用样例数据，不得冒充正式数据。",
            "夹具",
        ),
        _term(
            "owner",
            "owner",
            "属主",
            "属主",
            "沿用 #655 的 owner 边界：属主自由文本原样展示，不由 GUI 猜译。",
        ),
        # Research lifecycle vocabulary.
        _term(
            "campaign",
            "Campaign",
            "研究活动",
            "研究活动",
            "#655 第 7 节采用研究活动；研究语境中不用军事化译法。",
            "战役",
        ),
        _term(
            "hypothesis",
            "Hypothesis",
            "研究假设",
            "研究假设",
            "根 README 的策略研究流程把 Hypothesis 与来源资料并列。",
        ),
        _term(
            "protocol",
            "protocol",
            "研究协议",
            "研究协议",
            "#472、#475 使用研究方法协议；protocol 不缩成统计协议。",
        ),
        _term(
            "candidate",
            "Candidate",
            "候选对象",
            "候选对象",
            "Candidate IR 同时覆盖 Factor、Model、Strategy，故总称不能写成候选策略。",
            "候选策略",
        ),
        _term(
            "candidate_factor",
            "Candidate Factor",
            "候选因子",
            "候选因子",
            "沿用 Candidate IR 的 Factor 子类，作为候选对象的类型标签。",
        ),
        _term(
            "candidate_model",
            "Candidate Model",
            "候选模型",
            "候选模型",
            "沿用 Candidate IR 的 Model 子类，作为候选对象的类型标签。",
        ),
        _term(
            "candidate_strategy",
            "Candidate Strategy",
            "候选策略",
            "候选策略",
            "仅在明确的 Strategy 子类语境使用候选策略，不作 Candidate 总称。",
        ),
        _term(
            "run",
            "Run",
            "运行",
            "运行",
            "根 README 将 Runtime run 译作运行；它不等同于回测或研究结论。",
        ),
        _term(
            "experiment",
            "Experiment",
            "试验",
            "试验",
            "沿用研究活动中的 experiment 语义，与一次运行的执行事实区分。",
        ),
        _term(
            "evidence",
            "Evidence",
            "证据",
            "证据",
            "根 README 的 Evidence v2 和 #655 第 7 节均使用证据。",
        ),
        _term(
            "qualification",
            "Qualification",
            "资格评定",
            "资格评定",
            "暂定资格评定；这是研究状态阶梯，关口语义仍待 owner 确认。",
            "准入评定",
        ),
        _term(
            "replication",
            "Replication",
            "复现",
            "复现",
            "根 README 的复现与持续再验证章节使用复现，不译为复制。",
        ),
        _term(
            "revalidation",
            "Revalidation",
            "重新验证",
            "重新验证",
            "根 README 的复现与持续再验证章节使用重新验证。",
            "再验证",
        ),
        _term(
            "conclusion",
            "Conclusion",
            "结论",
            "结论",
            "沿用 Evidence v2 到报告链路中的研究结论语义。",
        ),
        _term(
            "decision",
            "Decision",
            "决策",
            "决策",
            "沿用研究编排和证据门对下一步决策的用词。",
        ),
        _term(
            "focused_research",
            "Focused research",
            "专项研究",
            "专项研究",
            "根 README 将 focused refinement 归入有界研究策略，译为专项研究。",
        ),
        _term(
            "strategy_family",
            "Strategy family",
            "策略族",
            "策略族",
            "与 Research Memory 的候选族区分；strategy family 仅指策略类别。",
        ),
        # Controlled statuses.
        _term(
            "known",
            "Known",
            "已记录",
            "已记录",
            "与 Missing 的未记录成对；已记录只表示系统有记录，不暗示已核实。",
            "已确认",
        ),
        _term(
            "derived",
            "Derived",
            "已派生",
            "已派生",
            "沿用根 README 对 GUI 派生视图和派生分组的明确标记。",
        ),
        _term(
            "interpreted",
            "Interpreted",
            "已解读",
            "已解读",
            "沿用来源发布的解读语义，不把解读提升为新的属主事实。",
        ),
        _term(
            "missing",
            "Missing",
            "未记录",
            "未记录",
            "与 Known 的已记录成对；缺失只表示没有公开记录。",
        ),
        _term(
            "blocked",
            "Blocked",
            "已阻塞",
            "已阻塞",
            "#655 明确要求前置条件未满足时 fail closed，统一写已阻塞。",
            "已阻断",
        ),
        _term(
            "stale",
            "Stale",
            "已过时",
            "已过时",
            "#655 将 Stale 与游标过期分开；状态译为已过时，过期保留给游标。",
            "过期",
        ),
        _term(
            "incomparable",
            "Incomparable",
            "不可比较",
            "不可比较",
            "根 README 要求比较条件不一致时显式报告不可比较。",
        ),
        _term(
            "integrity_failure",
            "Integrity failure",
            "完整性校验失败",
            "完整性失败",
            "沿用 ManagerReadModel v0 的错误与可用性状态语义。",
        ),
        _term(
            "api_unavailable",
            "API unavailable",
            "API 不可用",
            "API 不可用",
            "API 是 #655 规定的白名单拉丁词；不可用状态不伪装成空结果。",
        ),
        _term(
            "not_evaluated",
            "Not evaluated",
            "未评估",
            "未评估",
            "根 README 对没有原生证据的能力明确标记为 not_evaluated。",
        ),
        _term(
            "unconfirmed",
            "Unconfirmed",
            "未确认",
            "未确认",
            "与未记录并列表示公开指针尚未确认，不推断为不存在。",
        ),
        _term(
            "cursor_expired",
            "Cursor expired",
            "游标已过期",
            "游标过期",
            "#655 保留过期给 cursor，避免与 Stale 的已过时混淆。",
        ),
        _term(
            "snapshot_drift",
            "Snapshot drift",
            "快照漂移",
            "快照漂移",
            "沿用 #655 对不同资源快照不可混用及漂移的 fail-closed 约束。",
        ),
        # Strategy Genome and conditions.
        _term(
            "strategy_genome",
            "Strategy Genome",
            "策略基因组",
            "策略基因组",
            "#655 第 7 节和 S2 路由均使用 Strategy Genome 的研究对象语义。",
        ),
        _term(
            "behavior_projection",
            "Behavior projection",
            "行为投影",
            "行为投影",
            "沿用 Strategy Genome 对可观察行为投影的领域用词。",
        ),
        _term(
            "validation_binding",
            "Validation binding",
            "验证绑定",
            "验证绑定",
            "沿用 Genome 将验证结果绑定到内容身份的语义。",
        ),
        _term(
            "content_hash",
            "Content hash",
            "内容哈希",
            "内容哈希",
            "根 README 和 ManagerReadModel 使用 hash 作为稳定内容身份的一部分。",
        ),
        _term(
            "lifecycle",
            "Lifecycle",
            "生命周期",
            "生命周期",
            "沿用 Genome 生命周期字段，描述对象阶段而不是页面导航状态。",
        ),
        _term(
            "applicable_condition",
            "Applicable condition",
            "适用条件",
            "适用条件",
            "沿用 Genome Conditions 页面，把条件与行为证据分开呈现。",
        ),
        _term(
            "invalidating_condition",
            "Invalidating condition",
            "失效条件",
            "失效条件",
            "沿用条件证据对使候选结论失效的明确描述。",
        ),
        _term(
            "descriptive_observation",
            "Descriptive observation",
            "描述性观察",
            "描述性观察",
            "沿用条件页面的观察语义；描述性观察不自动成为研究结论。",
        ),
        # Evidence and artifact vocabulary.
        _term(
            "evidence_ledger",
            "Evidence Ledger",
            "证据账本",
            "账本",
            "#472、#474 使用研究账本；ledger 统一译为账本而不是台账。",
            "台账",
        ),
        _term(
            "evidence_grade",
            "Evidence grade",
            "证据等级",
            "证据等级",
            "沿用 Evidence v2 对证据强度和门槛层级的表达。",
        ),
        _term(
            "evidence_category",
            "Evidence category",
            "证据类别",
            "证据类别",
            "沿用 Evidence v2 对不同来源证据类别的分类。",
        ),
        _term(
            "candidate_evidence",
            "Candidate evidence",
            "候选证据",
            "候选证据",
            "根 README 明确 Qlib 结果只能作为候选证据。",
        ),
        _term(
            "protocol_conforming_evidence",
            "Protocol-conforming evidence",
            "符合研究协议的证据",
            "协议符合证据",
            "#655 第 7 节要求 protocol-conforming evidence 使用完整研究协议语义。",
        ),
        _term(
            "artifact",
            "artifact",
            "制品",
            "制品",
            "根 README 第 24 行写不可变制品；generated artifact 也沿用制品。",
            "产物",
        ),
        _term(
            "generated_artifact",
            "generated artifact",
            "生成制品",
            "生成制品",
            "根 README 的 generated-code 与不可变制品边界要求保持生成制品说法。",
        ),
        _term(
            "verify",
            "verify",
            "核验",
            "核验",
            "根 README 对报告提供 verify / rebuild；verify 统一译为核验。",
        ),
        _term(
            "hash_mismatch",
            "Hash mismatch",
            "哈希不匹配",
            "哈希不匹配",
            "沿用制品验证对内容身份不一致的 fail-closed 错误语义。",
        ),
        # Lineage vocabulary.
        _term(
            "lineage",
            "lineage",
            "谱系",
            "谱系",
            "根 README 第 31 行写 record/artifact 和谱系；不用血缘。",
            "血缘",
        ),
        _term(
            "shortest_evidence_path",
            "Shortest evidence path",
            "最短证据路径",
            "最短路径",
            "S4 Evidence Trace 与 Lineage 路由使用最短证据路径。",
        ),
        _term(
            "upstream",
            "upstream",
            "上游",
            "上游",
            "沿用谱系图的方向性边标签；上游只表示显式发布的来源关系。",
        ),
        _term(
            "downstream",
            "downstream",
            "下游",
            "下游",
            "沿用谱系图的方向性边标签；下游不代表自动推断的因果关系。",
        ),
        # Research Memory vocabulary.
        _term(
            "research_memory",
            "Research Memory",
            "研究记忆",
            "研究记忆",
            "#655 第 7 节将 Research Memory 作为研究事实的长期回读视图。",
        ),
        _term(
            "formal_research_memory",
            "Formal Research Memory",
            "正式研究记忆",
            "正式记忆",
            "沿用 S3 对 Formal Research Memory 与普通失败记录的边界。",
        ),
        _term(
            "gui_derived_view",
            "GUI-derived view",
            "GUI 派生视图",
            "派生视图",
            "沿用 S3 约定；GUI 派生视图不能冒充属主事实。",
        ),
        _term(
            "candidate_family",
            "Candidate family",
            "候选族",
            "候选族",
            "Research Memory 的 family 覆盖因子、模型和策略候选。",
        ),
        _term(
            "family_memory",
            "Candidate-family memory",
            "候选族记忆",
            "族记忆",
            "沿用 S3 对 family-memory 的聚合记忆语义。",
        ),
        _term(
            "failure_category",
            "Failure category",
            "失败类别",
            "失败类别",
            "沿用 Memory failure 与 Failure Patterns 路由的分类字段。",
        ),
        _term(
            "inclusion",
            "Inclusion",
            "纳入",
            "纳入",
            "沿用研究记忆对候选纳入条件的审计字段。",
        ),
        _term(
            "exclusion",
            "Exclusion",
            "排除",
            "排除",
            "沿用研究记忆对候选排除条件的审计字段。",
        ),
        # Methodology vocabulary.
        _term(
            "methodology",
            "Methodology",
            "研究方法库",
            "方法库",
            "#655 第 7 节明确将 Methodology 作为版本化研究方法库。",
        ),
        _term(
            "workflow",
            "Workflow",
            "工作流程",
            "工作流程",
            "根 README 的推荐工作流使用工作流程，不与研究协议混同。",
        ),
        _term(
            "statistical_protocol",
            "Statistical protocol",
            "统计协议",
            "统计协议",
            "统计协议是研究协议的一个子范围，沿用 #655 的层级区分。",
        ),
        _term(
            "policy",
            "Policy",
            "政策",
            "政策",
            "根 README 多处使用比较政策、权限政策和数据政策。",
        ),
        _term(
            "benchmark",
            "Benchmark",
            "基准",
            "基准",
            "根 README 的 Benchmark 与回归门章节固定使用基准。",
        ),
        _term(
            "operational_constraint",
            "Operational constraint",
            "运行约束",
            "运行约束",
            "沿用研究编排对预算、资源和运行边界的约束语义。",
        ),
        # History and document vocabulary.
        _term(
            "source_event",
            "Source event",
            "来源事件",
            "来源事件",
            "S5 History 路由把来源事件作为只读历史记录。",
        ),
        _term(
            "source_document",
            "Source document",
            "来源文档",
            "来源文档",
            "根 README 与 S5 Source Documents 路由统一使用来源文档。",
        ),
        _term(
            "plan",
            "Plan",
            "计划",
            "计划",
            "#655 第 7 节把 plan 作为来源文档的文档类型。",
        ),
        _term(
            "design",
            "Design",
            "设计",
            "设计",
            "#655 第 7 节把 design 作为来源文档的文档类型。",
        ),
        _term(
            "report",
            "Report",
            "报告",
            "报告",
            "根 README 将 Strategy Reporting 产出的报告作为公开交付。",
        ),
        _term(
            "retrospective",
            "Retrospective",
            "复盘",
            "复盘",
            "根 README 已使用复盘；保留其对研究过程的回顾语义。",
        ),
        _term(
            "future_idea",
            "Future idea",
            "未来设想",
            "未来设想",
            "AGENTS.md 规定未立项的个人设想统一归档为未来设想。",
        ),
        _term(
            "external_source",
            "External source",
            "外部资料",
            "外部资料",
            "根 README 区分外部研究资料与属主已发布事实。",
        ),
        _term(
            "raw_evidence",
            "Raw evidence",
            "原始证据",
            "原始证据",
            "沿用 Evidence v2 的原始证据与解释层分离原则。",
        ),
        _term(
            "reverse_citations",
            "Reverse citations",
            "被引用于",
            "被引用于",
            "S5 Source Documents 双向链接使用被引用于，不使用反向引用。",
            "反向引用",
        ),
        _term(
            "approved_catalog_boundary",
            "Approved catalog boundary",
            "批准目录边界",
            "目录边界",
            "沿用 Source Documents 对已批准目录及其边界的只读约束。",
        ),
        # Search and Portal vocabulary.
        _term(
            "search",
            "Search",
            "搜索",
            "搜索",
            "S5 Search 路由和 #655 第 7 节均固定使用搜索。",
        ),
        _term(
            "global_no_match",
            "Global no-match",
            "全局无匹配",
            "全局无匹配",
            "#655 区分全局无匹配与当前页无结果，避免误报范围。",
        ),
        _term(
            "report_portal",
            "Portal",
            "报告门户",
            "报告门户",
            "#655 明确 Portal 的中文为报告门户，首次出现可说明策略报告。",
        ),
        _term(
            "source_publication",
            "Source publication",
            "来源发布记录",
            "发布记录",
            "S5 Portal 保持 source publication 与 generated artifact 元数据分离。",
        ),
        _term(
            "renderer",
            "Renderer",
            "渲染器",
            "渲染器",
            "根 README 的 Portal 元数据包含 renderer 与版本信息。",
        ),
        _term(
            "digest",
            "Digest",
            "摘要哈希",
            "摘要哈希",
            "沿用 Portal 的 digest 字段；摘要哈希用于确认内容身份。",
        ),
        _term(
            "approved_index",
            "Approved index",
            "已批准索引",
            "批准索引",
            "Search 只对已批准索引做确定性字面匹配。",
        ),
        _term(
            "deterministic_literal_match",
            "Deterministic literal match",
            "确定性字面匹配",
            "字面匹配",
            "#655 禁止改变搜索语义；命中由已批准索引上的确定性字面匹配产生。",
        ),
        _term(
            "rebuild",
            "rebuild",
            "重建",
            "重建",
            "根 README 对报告提供 verify / rebuild；rebuild 只重建已发布输入。",
        ),
    )
)

# These are the exact Latin UI/data words reserved by #655.  Owner-provided
# identifiers, hashes and locators are values rather than translated UI words.
LATIN_ALLOWLIST = frozenset(
    {"ID", "JSON", "API", "URL", "SHA-256", "Schema", "GUI", "ManagerReadModel v0"}
)
LATIN_WHITELIST = LATIN_ALLOWLIST
ALLOWED_LATIN_TERMS = LATIN_ALLOWLIST

# Names accepted by catalog placeholder audits.  ``term`` references are
# glossary references and intentionally do not belong to this set.
PLACEHOLDER_ALLOWLIST = frozenset(
    {
        "artifact_id",
        "as_of",
        "campaign",
        "cursor",
        "date",
        "document_id",
        "failure_id",
        "fixture",
        "genome_id",
        "href",
        "id",
        "left_genome_id",
        "memory_id",
        "n",
        "name",
        "page",
        "page_size",
        "panel",
        "pattern_id",
        "q",
        "query",
        "record_id",
        "right_genome_id",
        "scope",
        "snapshot_token",
        "source_id",
        "strategy_family",
        "study",
        "text",
        "value",
        "view",
    }
)
PLACEHOLDER_WHITELIST = PLACEHOLDER_ALLOWLIST
ALLOWED_PLACEHOLDERS = PLACEHOLDER_ALLOWLIST

# A flat view is convenient for tests and catalog linting.  ``过期`` is included
# because it is specifically reserved for cursor expiration, not Stale.
FORBIDDEN_ZH = frozenset(
    spelling for term in TERMS.values() for spelling in term.forbidden_zh
)


def _entry_texts(entry: object) -> Iterable[tuple[str, str]]:
    """Yield textual fields from an M-like catalog entry without importing it."""

    for field in ("zh", "en"):
        value = getattr(entry, field, None)
        if isinstance(value, str):
            yield field, value
        elif isinstance(value, Mapping):
            for form, text in value.items():
                if isinstance(text, str):
                    yield f"{field}.{form}", text
    if isinstance(entry, str):
        yield "text", entry


def find_forbidden_translations(
    catalog: Mapping[str, object],
) -> tuple[tuple[str, str, str], ...]:
    """Return ``(catalog_key, field, forbidden_spelling)`` matches.

    The function is deliberately duck-typed so tests and future catalog linting
    can inspect ``M`` entries without creating an import cycle with ``translator``.
    It does not mutate or register the supplied catalog.
    """

    matches: list[tuple[str, str, str]] = []
    for key, entry in catalog.items():
        for field, text in _entry_texts(entry):
            for spelling in sorted(FORBIDDEN_ZH):
                # "过期" is intentionally reserved for cursor_expired; Stale uses
                # "已过时", but the approved cursor term is "游标已过期".
                if spelling == "过期" and "cursor_expired" in str(key):
                    continue
                if spelling in text:
                    matches.append((str(key), field, spelling))
    return tuple(matches)


def _markdown_cell(value: str) -> str:
    """Escape the two Markdown table characters used by generated fields."""

    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def render_markdown() -> str:
    """Render the current registry as a deterministic Markdown review table."""

    lines = [
        "# Manager GUI 中文术语表",
        "",
        "本表由 `manager_gui.web.i18n.glossary` 的 `TERMS` 注册表生成。",
        "",
        "| ID | English | 中文 | 简称 | 说明 | 禁用译法 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for term in TERMS.values():
        forbidden = "、".join(term.forbidden_zh) if term.forbidden_zh else "—"
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(value)
                for value in (
                    term.id,
                    term.en,
                    term.zh,
                    term.zh_short or "—",
                    term.note or "—",
                    forbidden,
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    """Print the generated glossary for review or redirection to a file."""

    print(render_markdown(), end="")


__all__ = [
    "ALLOWED_LATIN_TERMS",
    "ALLOWED_PLACEHOLDERS",
    "FORBIDDEN_ZH",
    "LATIN_ALLOWLIST",
    "LATIN_WHITELIST",
    "PLACEHOLDER_ALLOWLIST",
    "PLACEHOLDER_WHITELIST",
    "TERMS",
    "Term",
    "_registry",
    "find_forbidden_translations",
    "main",
    "render_markdown",
]


if __name__ == "__main__":
    main()
