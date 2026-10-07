"""Top-level Manager GUI navigation translations."""

# Catalog templates are kept readable as bilingual pairs.
# ruff: noqa: E501

from collections.abc import Mapping

from ..translator import M

ENTRIES: Mapping[str, M] = {
    "nav.aria": M("管理界面分区", "Manager GUI sections"),
    "nav.reading.aria": M("按阅读任务查看内容", "Explore by reading task"),
    "nav.professional": M("全部专业页面", "All specialist pages"),
    "nav.reading.atlas": M("正在研究什么", "What is being researched"),
    "nav.reading.stories": M("一项研究怎么做的", "How a study was carried out"),
    "nav.reading.strategies": M("买卖和挑选股票的办法", "Buying, selling and selecting stocks"),
    "nav.reading.memory": M("学到的经验", "Lessons recorded"),
    "nav.reading.methodology": M("怎样检查结果", "How results are checked"),
    "nav.reading.portal": M("报告和说明", "Reports and explanations"),
    "nav.atlas.label": M("总览", "Atlas"),
    "nav.atlas.description": M("工作区地图与当前只读模型范围。", "Workspace map and current read-model scope."),
    "nav.stories.label": M("研究故事", "Stories"),
    "nav.stories.description": M("研究故事索引与溯源轨迹。", "Research story index and provenance trail."),
    "nav.strategies.label": M("策略 / {term:strategy_genome}", "Strategies / Genomes"),
    "nav.strategies.description": M("策略与策略基因组只读界面。", "Strategy and genome read surfaces."),
    "nav.strategy-conditions.label": M("基因组条件", "Genome Conditions"),
    "nav.strategy-conditions.description": M("基因组适用性、失效条件与描述证据。", "Genome applicability, invalidation, and descriptor evidence."),
    "nav.strategy-genome-comparison.label": M("基因组比较", "Genome Comparison"),
    "nav.strategy-genome-comparison.description": M("明确的基因组比较维度与溯源信息。", "Explicit Genome comparison axes and provenance."),
    "nav.memory.label": M("记忆", "Memory"),
    "nav.memory.description": M("失败知识与保留的研究记忆。", "Failure knowledge and retained research memory."),
    "nav.memory-failures.label": M("记忆失败", "Memory Failures"),
    "nav.memory-failures.description": M("正式研究记忆失败条目与明确谱系。", "Formal Memory failure entries and explicit lineage."),
    "nav.failure-patterns.label": M("失败模式", "Failure Patterns"),
    "nav.failure-patterns.description": M("普通失败与明确派生的失败模式。", "Ordinary failures and explicitly derived patterns."),
    "nav.evidence.label": M("证据", "Evidence"),
    "nav.evidence.description": M("证据谱系、来源引用与比较。", "Evidence lineage, source references, and comparisons."),
    "nav.lineage.label": M("谱系", "Lineage"),
    "nav.lineage.description": M("有界证据谱系图、表格与来源路径。", "Bounded evidence lineage graph, table, and source path."),
    "nav.evidence-object-comparison.label": M("证据比较", "Evidence Comparison"),
    "nav.evidence-object-comparison.description": M("按声明维度进行通用对象与证据比较。", "General object and evidence comparison by declared axes."),
    "nav.derived-failure-grouping.label": M("派生失败分组", "Derived Failure Grouping"),
    "nav.derived-failure-grouping.description": M("明确派生的成功与失败分组。", "Explicit Derived success and failure groupings."),
    "nav.methodology.label": M("研究方法库", "Methodology"),
    "nav.methodology.description": M("方法、契约与解读说明。", "Methods, contracts, and interpretation notes."),
    "nav.history.label": M("历史", "History"),
    "nav.history.description": M("历史快照与来源修订。", "Historical snapshots and source revisions."),
    "nav.source-documents.label": M("来源文档", "Source Documents"),
    "nav.source-documents.description": M("已批准的文档索引与记录引用。", "Approved document index and record citations."),
    "nav.search.label": M("搜索", "Search"),
    "nav.search.description": M("在已批准索引的只读模型记录中搜索。", "Search across approved read-model records."),
    "nav.portal.label": M("报告门户", "Portal"),
    "nav.portal.description": M("已发布的策略报告来源与制品元数据。", "Published Strategy Reporting source and artifact metadata."),
}
