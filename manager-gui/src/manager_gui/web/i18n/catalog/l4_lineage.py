"""Bilingual copy and closed-vocabulary labels for the Lineage page."""

from __future__ import annotations

from ..translator import M, label_key


_RECORD_TYPES: dict[str, M] = {
    "conclusion": M("结论", "Conclusion"),
    "evidence": M("证据", "Evidence"),
    "artifact": M("制品", "Artifact"),
    "genome": M("策略基因组", "Strategy Genome"),
    "memory": M("研究记忆", "Research Memory"),
    "memory_entry": M("记忆条目", "Memory entry"),
    "run": M("运行", "Run"),
    "campaign": M("研究活动", "Campaign"),
    "candidate": M("候选对象", "Candidate"),
    "source_document": M("来源文档", "Source document"),
    "document": M("文档", "Document"),
    "strategy": M("策略", "Strategy"),
    "strategy_family": M("策略族", "Strategy family"),
    "study": M("研究", "Study"),
    "hypothesis": M("研究假设", "Hypothesis"),
    "failure": M("失败记录", "Failure"),
    "pattern": M("模式", "Pattern"),
    "qualification": M("资格评定", "Qualification"),
    "replication": M("复现", "Replication"),
    "revalidation": M("重新验证", "Revalidation"),
}

_RELATIONS: dict[str, M] = {
    "produces": M("生成", "produces"),
    "supports": M("支持", "supports"),
    "informs": M("为……提供信息", "informs"),
    "derives": M("派生出", "derives"),
    "derived_from": M("派生自", "derived from"),
    "supersedes": M("取代", "supersedes"),
    "documents": M("记录于", "documents"),
    "cites": M("引用", "cites"),
    "references": M("引用", "references"),
    "contains": M("包含", "contains"),
    "depends_on": M("依赖", "depends on"),
    "executes": M("执行", "executes"),
    "generated": M("生成", "generated"),
    "validates": M("验证", "validates"),
    "records": M("记录", "records"),
    "associated_with": M("关联于", "associated with"),
}

_DIRECTIONS: dict[str, M] = {
    "upstream": M("上游", "Upstream"),
    "downstream": M("下游", "Downstream"),
    "both": M("双向", "Both directions"),
}

_PATH_STATES: dict[str, M] = {
    "found": M("已找到路径", "Path found"),
    "not-found": M("未找到路径", "Path not found"),
    "not-established": M("尚未确定", "Not established"),
    "not-applicable": M("不适用", "Not applicable"),
}

_STATUSES: dict[str, M] = {
    "recorded": M("已记录", "Recorded"),
    "not_evaluated": M("未评估", "Not evaluated"),
}

_FIXTURE_LABELS: dict[str, M] = {
    "conclusion": M("协议结论", "Protocol conclusion"),
    "evidence": M("协议证据", "Protocol evidence"),
    "replication_evidence": M("复现证据", "Replication evidence"),
    "superseded_evidence": M("已被取代的证据", "Superseded evidence"),
    "artifact": M("证据报告", "Evidence report"),
    "run": M("正式运行", "Formal run"),
    "campaign": M("研究活动", "Research campaign"),
    "candidate": M("候选对象", "Candidate"),
    "genome": M("策略基因组", "Strategy genome"),
    "memory": M("研究记忆", "Research memory"),
    "document": M("协议文档", "Protocol document"),
    "orphan_document": M("未关联的笔记", "Unlinked note"),
    "large_record": M("记录 {number}", "Record {number}"),
}

_FAILURES: dict[str, M] = {
    "cursor_expired": M("游标已过期", "Cursor expired"),
    "cursor_mismatch": M("游标不匹配", "Cursor mismatch"),
    "snapshot_drift": M("快照漂移", "Snapshot drift"),
    "unknown_schema": M("未知 Schema", "Unknown schema"),
    "hash_mismatch": M("哈希不匹配", "Hash mismatch"),
    "integrity_failure": M("完整性校验失败", "Integrity failure"),
    "source_unavailable": M("来源不可用", "Source unavailable"),
    "source_blocked": M("来源受阻", "Source blocked"),
    "incomparable": M("快照不可比较", "Incomparable snapshots"),
    "invalid_payload": M("谱系载荷无效", "Invalid lineage payload"),
    "bound_exceeded": M("超出边界", "Bounds exceeded"),
    "root_not_found": M("未找到根记录", "Root record not found"),
}

_TEXT: dict[str, M] = {
    "lineage.not_recorded": M("未记录或未确认", "Missing / Unconfirmed"),
    "lineage.unavailable": M("不可用", "Unavailable"),
    "lineage.none_recorded": M("未记录", "None recorded"),
    "lineage.not_recorded_short": M("未记录", "Not recorded"),
    "lineage.hash_verified": M("已核验", "verified"),
    "lineage.hash_not_verified": M("未核验", "not verified"),
    "lineage.derivation_inputs": M("输入：{inputs}", "inputs: {inputs}"),
    "lineage.derivation_inputs_prefix": M("输入：", "inputs: "),
    "lineage.derivation_unrecorded": M("派生方式未记录", "Derivation not recorded"),
    "lineage.no_owner_page": M("其他属主页面", "other owner page"),
    "lineage.other_page": M("其他页面", "other page"),
    "lineage.other_page_missing": M("此快照页面未记录该记录", "not recorded on this snapshot page"),
    "lineage.edge_sentence": M(
        "{source} —{relation}→ {target}", "{source} —{relation}→ {target}"
    ),
    "lineage.node_accessible": M(
        "{label}，{record_type}，深度 {depth}{root}{path}",
        "{label}, {record_type}, depth {depth}{root}{path}",
    ),
    "lineage.root_suffix": M("，根记录", ", root"),
    "lineage.path_suffix": M("，位于最短证据路径", ", on the shortest evidence path"),
    "lineage.svg_title": M("谱系图", "Lineage graph"),
    "lineage.svg_description": M(
        "显示本页 {nodes} 条记录和 {edges} 个关系的有界谱系图。",
        "Bounded lineage graph showing {nodes} records and {edges} relations on this page.",
    ),
    "lineage.graph_caption": M(
        "谱系图：本页有 {nodes} 条记录和 {edges} 个关系。箭头指向数据流动方向。",
        "Lineage graph: {nodes} records and {edges} relations on this page. Arrows point in the direction value flows.",
    ),
    "lineage.skip_table": M("跳转到等价表格", "Skip to the equivalent table"),
    "lineage.graph_region": M("谱系图，可滚动", "Lineage graph, scrollable"),
    "lineage.node_title": M("{label}（{id}）", "{label} ({id})"),
    "lineage.step": M("第 {number} 步", "Step {number}"),
    "lineage.trace_from_here": M("从此处追溯", "Trace from here"),
    "lineage.edges_region": M("谱系关系表，可滚动", "Lineage relations table, scrollable"),
    "lineage.edges_caption": M(
        "本页记录之间的关系（{count}）", "Relations among the records on this page ({count})"
    ),
    "lineage.no_edges": M("本页记录之间没有关系。", "No relations connect the records on this page."),
    "lineage.off_page": M(
        "还有 {count} 个关系连接到此视图其他页面的记录；可通过分页链接查看。",
        "{count} further relation(s) connect these records to records on other pages of this view; use the page links to reach them.",
    ),
    "lineage.table_heading": M("谱系表格", "Lineage table"),
    "lineage.table_intro": M("图中的同一组记录与关系，同时以可访问表格和文本呈现。", "The same records and relations as the graph, as accessible tables and text."),
    "lineage.records_region": M("谱系记录表，可滚动", "Lineage records table, scrollable"),
    "lineage.records_caption": M(
        "本页记录（边界内共 {total} 条）", "Records on this page ({count} of {total} within the bounds)"
    ),
    "lineage.text_view": M("文本视图", "Text view"),
    "lineage.relations_text": M("谱系关系文本", "Lineage relations as text"),
    "lineage.col_record": M("记录", "Record"),
    "lineage.col_type": M("类型", "Type"),
    "lineage.col_status": M("状态", "Status"),
    "lineage.col_depth": M("深度", "Depth"),
    "lineage.col_evidence_path": M("证据路径", "Evidence path"),
    "lineage.col_hash": M("哈希", "Hash"),
    "lineage.col_as_of": M("截至时间", "As of"),
    "lineage.col_sources": M("来源", "Sources"),
    "lineage.col_derivation": M("派生方式", "Derivation"),
    "lineage.col_actions": M("操作", "Actions"),
    "lineage.col_from": M("起点", "From"),
    "lineage.col_relation": M("关系", "Relation"),
    "lineage.col_to": M("终点", "To"),
    "lineage.node_trace_action": M("从此记录开始追溯", "Trace from this record"),
    "lineage.path_heading": M("最短证据路径", "Shortest evidence path"),
    "lineage.shortest_path_summary": M(
        "到 {target} 的最短路径：边界内共 {count} 个关系。",
        "Shortest path to {target}: {count} relation(s) within the bounds.",
    ),
    "lineage.path_not_established": M(
        "尚未确定：仍有属主页面未读取，因此本页未显示证据路径并不能证明路径不存在。",
        "Not established: further owner pages exist, so the absence of an evidence path on this page is not proof that none exists.",
    ),
    "lineage.path_not_found": M(
        "在此完整快照的深度 {depth}、所选方向、关系和记录类型范围内，未找到证据路径。",
        "No evidence path exists within depth {depth}, the selected direction, relations, and record types in this complete snapshot.",
    ),
    "lineage.inspector_heading": M("详情面板", "Inspector"),
    "lineage.inspector_missing": M(
        "记录 {record} 未记录于此快照页面。", "Record {record} is not recorded in this snapshot page."
    ),
    "lineage.inspector_outside_bounds": M(
        "此记录位于当前深度、关系或记录类型边界之外。",
        "This record lies outside the current depth, relation, or record-type bounds.",
    ),
    "lineage.label_record_id": M("记录 ID", "Record ID"),
    "lineage.label": M("标签", "Label"),
    "lineage.label_snapshot": M("快照", "Snapshot"),
    "lineage.label_source_refs": M("来源引用", "Source refs"),
    "lineage.incoming": M("传入关系", "Incoming relations"),
    "lineage.outgoing": M("传出关系", "Outgoing relations"),
    "lineage.relation_from": M("来自", "from"),
    "lineage.relation_to": M("指向", "to"),
    "lineage.trace_from_record": M("从此记录开始追溯", "Trace from this record"),
    "lineage.disconnected_heading": M("未连接的记录", "Unconnected records"),
    "lineage.disconnected_partial": M(
        "尚未确定：后续属主页面中的记录可能与这些记录相连。",
        "Not determined: records on further owner pages may connect these.",
    ),
    "lineage.disconnected_complete": M(
        "此快照中没有关系将这些记录连接到根记录。",
        "No relation in this snapshot connects these records to the root.",
    ),
    "lineage.disconnected_none_partial": M(
        "本页没有；后续属主页面可能还有记录。", "None on this page; further owner pages may hold more."
    ),
    "lineage.disconnected_none_complete": M(
        "没有：本页中的每条记录都与根记录相连。",
        "None: every record on this page is connected to the root.",
    ),
    "lineage.outside_bounds": M(
        "有 {count} 条已连接记录位于当前深度、关系或记录类型边界之外。",
        "{count} connected record(s) lie outside the current depth, relation, or record-type bounds.",
    ),
    "lineage.bounds_heading": M("边界", "Bounds"),
    "lineage.applied_bounds": M(
        "已应用：方向 {direction}；深度 {depth}；每页记录数 {page_size}；关系 {relations}；记录类型 {record_types}。",
        "Applied: direction {direction}; depth {depth}; page size {page_size}; relations {relations}; record types {record_types}.",
    ),
    "lineage.bounds_limit": M(
        "扩展深度最多为 {depth}，每个属主页面最多读取 {nodes} 条记录。",
        "Expansion never exceeds depth {depth} or {nodes} records per owner page.",
    ),
    "lineage.none_selected_all": M("未选择 = 全部", "none selected = all"),
    "lineage.all": M("全部", "all"),
    "lineage.direction": M("方向", "Direction"),
    "lineage.depth": M("深度", "Depth"),
    "lineage.page_size": M("每页记录数", "Page size"),
    "lineage.record_types": M("记录类型", "Record types"),
    "lineage.apply_bounds": M("应用边界", "Apply bounds"),
    "lineage.partial_heading": M("部分谱系", "Partial lineage"),
    "lineage.partial_explanation": M(
        "当前仅显示一个有界属主页面，且仍有后续页面或来源数据不完整。此处缺少记录、关系、连接或证据路径，不代表其不存在。",
        "This is one bounded owner page and further pages exist or the source is incomplete. A missing record, relation, connection, or evidence path here is not evidence of absence.",
    ),
    "lineage.dangling_edges": M(
        "有 {count} 个关系引用了其他属主页面中的记录。",
        "{count} relation(s) reference records on other owner pages.",
    ),
    "lineage.next_page": M("下一属主页面", "Next owner page"),
    "lineage.next_page_snapshot": M(
        "（固定使用快照 {snapshot}；不会合并不同快照的页面。）",
        " (pins snapshot {snapshot}; pages are never merged across snapshots).",
    ),
    "lineage.failure_heading": M("谱系暂不展示", "Lineage withheld"),
    "lineage.failure_explanation": M(
        "无法信任此数据，因此不显示图、表格或证据路径；也不会合并其他快照或页面的数据。",
        "No graph, table, or evidence path is shown for data that cannot be trusted; nothing is merged from other snapshots or pages.",
    ),
    "lineage.restart": M("从当前快照重新开始", "Restart from the current snapshot"),
    "lineage.restart_explanation": M(
        "（清除游标和固定快照；不会合并数据。）",
        " (clears the cursor and pinned snapshot; nothing is merged).",
    ),
    "lineage.empty_scope": M("此范围没有已发布的谱系记录。", "No lineage records are published in this scope."),
    "lineage.empty_owner_page": M("此属主页面尚无谱系记录。", "No lineage records are on this owner page yet."),
    "lineage.page_eyebrow": M("谱系 · 只读", "Lineage · read-only"),
    "lineage.page_title": M("谱系", "Lineage"),
    "lineage.page_intro": M(
        "跨结论、证据、制品、策略基因组、研究记忆和运行查看有界溯源信息及下游影响。关系按已发布内容原样展示。",
        "Bounded provenance and downstream impact across conclusions, evidence, artifacts, Genomes, Memory, and runs. Relations are shown exactly as published.",
    ),
    "lineage.observed": M("观察时间", "Observed"),
    "lineage.snapshot": M("快照", "Snapshot"),
    "lineage.derivation": M("派生方式", "Derivation"),
    "lineage.sources": M("来源", "Sources"),
    "lineage.raw_json": M("原始 JSON", "Raw JSON"),
    "lineage.partial_status_reason": M("此有界页面不是完整的谱系范围。", "This bounded page is not the complete lineage scope."),
    "lineage.fixture_reason.complete": M("样例包含已发布的谱系投影。", "The fixture contains the published lineage projection."),
    "lineage.fixture_reason.partial": M("仅发布了第一个谱系页面。", "Only the first lineage page is published."),
    "lineage.fixture_reason.cursor_expired": M("谱系游标已过期。", "The lineage cursor expired."),
    "lineage.fixture_reason.snapshot_drift": M("谱系页面快照与读取的快照不同。", "The lineage page snapshot differs from the snapshot that was read."),
    "lineage.fixture_reason.hash_mismatch": M("谱系记录未通过其声明的哈希校验。", "A lineage record failed its declared hash check."),
    "lineage.fixture_reason.api_unavailable": M("批准的公开谱系读取接口不可用。", "The approved public lineage read API is unavailable."),
    "lineage.fixture_reason.empty": M("此范围没有已发布的谱系记录。", "No lineage records are published in this scope."),
    "lineage.fixture_reason.blocked": M("批准的谱系读取接口已阻塞。", "The approved lineage read seam is blocked."),
    "lineage.fixture_reason.incomparable": M("谱系输入属于不兼容的快照。", "The lineage inputs belong to incompatible snapshots."),
    "lineage.fixture_reason.stale": M("此谱系页面作为过时的历史投影保留。", "The lineage page is retained as a stale historical projection."),
    "lineage.fixture_reason.not_evaluated": M("此谱系页面包含尚未评估的证据记录。", "This lineage page contains evidence records that have not been evaluated."),
    "lineage.fixture_reason.shared_snapshot_drift": M("谱系页面快照与读取的快照不同。", "The lineage page snapshot differs from the snapshot that was read."),
    "lineage.fixture_reason.shared_integrity_failure": M("谱系记录未通过其声明的哈希校验。", "A lineage record failed its declared hash check."),
    "lineage.fixture_error.partial": M("仍有后续谱系页面；不能据此证明缺少关系。", "Further lineage pages exist; absence of a link is not proven."),
    "lineage.fixture_error.cursor_expired": M("游标已不再有效。", "The cursor is no longer valid."),
    "lineage.fixture_error.api_unavailable": M("谱系读取不得回退到私有存储。", "No private-storage fallback is permitted for lineage reads."),
    "lineage.note.unknown_direction": M(
        "未知方向 <code>{value}</code> 已忽略，显示双向关系。",
        "Unknown direction <code>{value}</code> ignored; showing both.",
    ),
    "lineage.note.unknown_relation": M(
        "未知关系 <code>{value}</code> 已忽略。", "Unknown relation <code>{value}</code> ignored."
    ),
    "lineage.note.unknown_record_type": M(
        "未知记录类型 <code>{value}</code> 已忽略。",
        "Unknown record type <code>{value}</code> ignored.",
    ),
    "lineage.note.invalid_integer": M(
        "{name} 的值 <code>{value}</code> 无效，已使用默认值 {default}。",
        "Invalid {name} <code>{value}</code> ignored; using {default}.",
    ),
    "lineage.note.clamped_integer": M(
        "{name} 的值 {value} 超出 {low}..{high}，已使用 {clamped}。",
        "{name} {value} is outside {low}..{high}; using {clamped}.",
    ),
}

ENTRIES: dict[str, M] = {
    **{label_key("lineage_record_type", value): entry for value, entry in _RECORD_TYPES.items()},
    **{label_key("lineage_relation", value): entry for value, entry in _RELATIONS.items()},
    **{label_key("lineage_direction", value): entry for value, entry in _DIRECTIONS.items()},
    **{label_key("lineage_path_state", value): entry for value, entry in _PATH_STATES.items()},
    **{label_key("lineage_status", value): entry for value, entry in _STATUSES.items()},
    **{f"lineage.fixture_label.{value}": entry for value, entry in _FIXTURE_LABELS.items()},
    **{f"lineage.failure.{value}": entry for value, entry in _FAILURES.items()},
    **_TEXT,
}

__all__ = ["ENTRIES"]
