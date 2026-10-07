from ..translator import M

ENTRIES = {
    "pipeline.lineage_title": M("这些内容有哪些已记录的关联？", "How are these records connected?"),
    "pipeline.lineage_intro": M(
        "图和表列出同一组已提供的内容及关联。没有记录为什么关联时，就不能补猜原因。",
        "The graph and table show the same supplied records and relationships. "
        "If no reason was recorded, none is inferred.",
    ),
    "pipeline.story.intent": M("当时想知道什么？", "What question was recorded?"),
    "pipeline.story.initial_hypothesis": M("当时想测试什么想法？", "What hypothesis was recorded?"),
    "pipeline.story.research_design": M("测试前怎样安排？", "How was the test planned?"),
    "pipeline.story.attempts": M("做了哪些尝试？", "What attempts were recorded?"),
    "pipeline.story.evidence": M("记录提供了哪些结果材料？", "What result material was supplied?"),
    "pipeline.story.failures": M("记录写明了哪些问题？", "What problems were recorded?"),
    "pipeline.story.follow_up": M("测试之后又做了什么？", "What happened after the test?"),
    "pipeline.story.missing.intent": M(
        "当时想知道什么的记录未提供，不能补猜动机。",
        "No question or intent record was supplied; no motive is inferred.",
    ),
    "pipeline.story.missing.initial_hypothesis": M(
        "准备测试的想法未提供。", "No hypothesis record was supplied."
    ),
    "pipeline.story.missing.research_design": M(
        "测试前的安排未提供，不能据此说没有安排过。",
        "No test-plan record was supplied; this does not establish that no plan existed.",
    ),
    "pipeline.story.missing.attempts": M(
        "尝试的过程未提供，不能据此说没有测试过。",
        "No attempt record was supplied; this does not establish that no test was run.",
    ),
    "pipeline.story.missing.evidence": M(
        "其他结果材料未提供。", "No additional result material was supplied."
    ),
    "pipeline.story.missing.failures": M(
        "问题的记录未提供，不能据此判断没有问题。",
        "No problem record was supplied; this does not establish there were no problems.",
    ),
    "pipeline.story.missing.follow_up": M(
        "后来的动作未提供，不能补造修改办法或再次测试的计划。",
        "No later action was supplied; no change or retest plan is invented.",
    ),
    "pipeline.open_lineage": M(
        "查看这条记录指向的关联关系", "Read the relationships referenced by this record"
    ),
    "pipeline.relation_boundary": M(
        "记录中的关联关系不等于原因。", "A recorded relationship is not a cause."
    ),
    "pipeline.atlas_title": M("当前可以阅读哪些研究？", "Which research objects can be read now?"),
    "pipeline.open_story": M(
        "阅读「{name}」的研究过程与结果", "Read the process and results for “{name}”"
    ),
    "pipeline.object_result_missing": M(
        "这个对象没有提供具体研究结果，不能用执行状态代替。",
        "No specific research result was provided for this object; "
        "execution status is not a substitute.",
    ),
    "pipeline.no_research_objects": M(
        "当前列表没有明确标识为研究活动、研究或办法系列的对象；其他记录仍列在统计输入中。",
        "No object in this list is explicitly identified as a campaign, study, or strategy family. "
        "Other records are retained in the calculation inputs.",
    ),
    "support.count": M(
        "当前已提供且经过筛选的列表有 {n} 条不同记录。",
        "{n} distinct records in the currently supplied, filtered list.",
    ),
    "support.count_unit": M("单位：记录，不是研究或测试。", "Unit: records, not studies or tests."),
    "support.count_rule": M(
        "页面统计：先应用当前列表筛选，再按明确的类型和编号计算不同记录数。额外查询条件原样保留，不猜它们的含义。",
        "GUI calculation: apply the current list filters, "
        "then count distinct explicit record identities. "
        "Additional query context is retained without guessing its meaning.",
    ),
    "support.count_dedup": M(
        "去重规则：记录类型和稳定编号。",
        "Deduplication: record type and stable identifier.",
    ),
    "support.count_complete": M(
        "已提供列表在这次读取范围内完整；不代表接入了所有研究。",
        "The supplied list is complete for this read, "
        "not necessarily the entire research collection.",
    ),
    "support.count_partial": M(
        "已提供范围不完整，尚不能确定整个集合的数量。",
        "The supplied range is incomplete; no full collection total is established.",
    ),
    "support.filters": M(
        "实际筛选与保留的查询：{filters}", "Applied filters and retained query: {filters}"
    ),
    "support.count_inputs": M(
        "核对记录数量的全部已提供输入", "Check all supplied inputs to the record count"
    ),
    "support.all_inputs": M(
        "全部已提供的统计输入（{n} 行）", "All supplied calculation inputs ({n} rows)"
    ),
    "support.open": M("核对「{name}」的已提供内容", "Check supplied content for “{name}”"),
    "support.open_unnamed": M("核对已提供的来源内容", "Check the supplied source content"),
    "support.gap_unnamed": M("查看当前无法核对的原因", "See why this content cannot be checked"),
    "support.heading_unnamed": M("来源名称未提供", "No source title was provided"),
    "support.query": M("筛选与保留的查询条件", "Filters and retained query context"),
    "support.raw_record": M("按原样核对完整记录", "Check the complete record unchanged"),
    "support.title": M("来源 {source} 的已提供内容", "Supplied content for source {source}"),
    "support.unnamed": M("未命名来源", "unnamed source"),
    "support.gap_entry": M("查看为何不能核对「{name}」", "See why “{name}” cannot be checked"),
    "support.unverified_content": M(
        "以下保留已提供的文字供核对，但不能作为可用原文或已核验依据。",
        "The supplied text is retained below for inspection, "
        "not as a usable original or verified support.",
    ),
    "support.record_content": M(
        "已提供这条公开记录中的正文；这不证明已核对作者的全部原文。",
        "A body was supplied in this public record; "
        "this does not prove the author's full original was checked.",
    ),
    "support.record_original": M(
        "已提供结构化记录，并另附原文；记录字段与来源作者原话分开显示。",
        "A structured record and a separate original were supplied. "
        "Record fields and original source wording are shown separately.",
    ),
    "support.version_change": M(
        "原文与结果的版本不同；不能将它们拼成同一条结论。",
        "Original and result versions differ; they cannot be combined into one conclusion.",
    ),
    "support.conflict": M(
        "相互冲突的来源分别保留；不能挑选其中一份当成共同结论。",
        "Conflicting supplied sources are shown separately; "
        "no source is selected as a consensus conclusion.",
    ),
    "support.restricted": M(
        "来源已报告访问受限；保留文字不能作为已核验支持，受限原因未提供时仍未知。",
        "The source reports restricted access; retained text is not verified support. "
        "The cause remains unknown unless supplied.",
    ),
    "support.unsafe": M(
        "已提供地址不安全或不是浏览器地址；不会打开它，保留文字不表示地址已可访问。",
        "The supplied locator is unsafe or not a browser address; it will not be opened. "
        "Retained text does not establish that the locator is accessible.",
    ),
    "support.source_failure": M(
        "来源报告了读取、版本或完整性问题；对应文字不能作为已核验支持。",
        "The source reports a read, version, or integrity problem; "
        "the corresponding text is not verified support.",
    ),
    "support.original_missing": M(
        "对应来源没有提供可读原文，无法核对原报告。",
        "The matching source did not supply a readable original; "
        "the original report cannot be checked.",
    ),
    "support.close": M("关闭依据并回到入口", "Close support and return to its entry"),
    "support.structured": M(
        "结构化记录；没有提供报告原文。",
        "Structured record; no original report was supplied.",
    ),
    "support.fields": M("已提供公开记录中的全部字段", "All fields in the supplied public record"),
    "support.title_missing": M("原文标题未提供", "No original title was provided"),
    "support.excerpt": M("已提供原文中的匹配摘录", "Matching excerpt from the supplied original"),
    "support.original": M("阅读已提供的原文", "Read the supplied original"),
    "support.unlocated": M(
        "已有可读原文，但尚未找到支持这句话的位置，不能把原文存在当成支持。",
        "A readable original is available, but no supporting location for this statement "
        "has been established. Availability is not support.",
    ),
    "support.impact.blocked": M(
        "访问或所需能力受限；不能确认这次测试是否达到目标，受限原因未说明时仍未知。",
        "Access or a capability is blocked; "
        "the content cannot establish whether this test met its target. "
        "The cause remains unknown unless supplied.",
    ),
    "support.impact.stale": M(
        "已提供内容对应旧版本；不能确认这次测试是否达到目标，也不能将新旧内容混用。",
        "The supplied content is stale; it cannot establish whether this test met its target. "
        "Old and new content must not be combined.",
    ),
    "support.impact.integrity_failure": M(
        "内容完整性检查失败；不能确认这次测试是否达到目标，保留的内容不是已核验依据。",
        "Content integrity failed; it cannot establish whether this test met its target. "
        "Retained content is not verified support.",
    ),
    "support.impact.api_unavailable": M(
        "公开读取失败；不能确认这次测试是否达到目标，不会改读私有文件补齐。",
        "The public read failed; it cannot establish whether this test met its target. "
        "Private files will not be read to fill the gap.",
    ),
    "support.impact.missing": M(
        "所需内容缺失；不能确认这次测试是否达到目标。没找到记录不等于没有做过测试。",
        "Required content is missing; it cannot establish whether this test met its target. "
        "A missing record does not mean no test was run.",
    ),
    "support.impact.incomparable": M(
        "已提供条件不能直接比较；不能据此选择优胜者。",
        "The supplied conditions cannot be compared directly; they cannot establish a winner.",
    ),
    "support.impact.errors": M(
        "公开读取报告了错误；这些内容不能确认这次测试是否达到目标。以下保留已报告的原因，不补猜原因。",
        "The public read reported errors; "
        "this content cannot establish whether this test met its target. "
        "Reported reasons are retained below; no cause is guessed.",
    ),
    "support.impact.partial": M(
        "这里只读到部分内容，未读到的内容可能影响判断；不代表全部研究。",
        "Only part of the content was read. Unread content may affect the determination; "
        "this is not the full research collection.",
    ),
    "support.pointer": M(
        "只有来源编号和地址，没有提供可读内容，目前无法核对。安全地址不表示已读到内容。",
        "Only a source reference and locator were supplied, without readable content. "
        "It cannot currently be checked. A safe locator does not mean content was read.",
    ),
}
