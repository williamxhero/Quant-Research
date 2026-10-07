from ..translator import M

ENTRIES = {
    "material.period": M("记录期间", "Recorded period"),
    "material.period_unknown": M("期间未提供", "Period not supplied"),
    "material.unit.USD": M("美元", "US dollars"),
    "material.unit.CNY": M("人民币元", "Chinese yuan"),
    "material.unit.EUR": M("欧元", "Euros"),
    "material.category": M("材料类别", "Material category"),
    "material.category_unknown": M(
        "类别未提供，不能称为报告", "Category not supplied; this cannot be called a report"
    ),
    "material.report": M("报告", "Report"),
    "material.record": M("记录", "Record"),
    "material.plan": M("计划", "Plan"),
    "material.rules": M("买卖办法说明", "Trading rules description"),
    "material.comparison": M("比较表", "Comparison table"),
    "material.summary": M("摘要", "Summary"),
    "material.report_question": M("什么叫报告？", "What is a report?"),
    "material.report_definition": M(
        "报告是测试结束后写下的结果记录。这里只展示已提供的范围与内容；材料类别不证明研究成功。",
        "A report records results after a test ends. Only the supplied scope and content "
        "are shown here; the category does not prove research success.",
    ),
    "material.plan_question": M("什么叫计划？", "What is a plan?"),
    "material.plan_definition": M(
        "计划是测试前的安排，不证明已经执行。",
        "A plan describes arrangements before a test; it does not prove execution.",
    ),
    "material.rules_question": M(
        "买卖办法说明写什么？", "What does a trading rules description contain?"
    ),
    "material.rules_definition": M(
        "它说明何时给出买卖提示及怎样挑选股票；未提供的实际成交时间、价格与条件仍然未知。",
        "It describes trading signals and stock selection; "
        "missing execution times, prices and conditions remain unknown.",
    ),
    "material.comparison_question": M("比较表说明什么？", "What does a comparison table show?"),
    "material.comparison_definition": M(
        "它并列已提供的内容；范围或买卖费用不同、未知时不能据此选出赢家。",
        "It places supplied content side by side; differing or unknown scope "
        "or trading costs do not establish a winner.",
    ),
    "material.summary_question": M("摘要能代替原文吗？", "Can a summary replace the original?"),
    "material.summary_definition": M(
        "摘要只是一段概述，不证明已经核对原文。",
        "A summary is an overview, not proof that the original was checked.",
    ),
    "material.design_question": M("设计说明什么？", "What does a design describe?"),
    "material.design_definition": M(
        "设计说明打算怎样测试和使用哪些条件，不证明已经执行或得到结果。",
        "A design describes intended tests and conditions, not proof of execution or results.",
    ),
    "material.retrospective_question": M("复盘回顾什么？", "What does a retrospective review?"),
    "material.retrospective_definition": M(
        "复盘回顾已记录的过程与问题；它不能代替原始记录，也不证明研究成功。",
        "A retrospective reviews the recorded process and problems; "
        "it does not replace original records or prove research success.",
    ),
    "material.raw-evidence_question": M("什么叫原始证据？", "What is raw evidence?"),
    "material.raw-evidence_definition": M(
        "原始证据是供核对的来源记录，不是对结果的解释；名称不证明内容已经核验。",
        "Raw evidence is source material to check, not an interpretation of results; "
        "the category does not prove the content was verified.",
    ),
    "material.future-idea_question": M("什么叫未来设想？", "What is a future idea?"),
    "material.future-idea_definition": M(
        "未来设想是尚未承诺实施的想法，不是已经执行的研究或结果。",
        "A future idea is an idea not yet committed for implementation, "
        "not executed research or a result.",
    ),
    "material.external-source_question": M("什么叫外部资料？", "What is an external source?"),
    "material.external-source_definition": M(
        "外部资料来自研究记录之外；引用它不表示已经核验或采纳其中的结论。",
        "An external source comes from outside the research record; "
        "citing it does not mean its conclusions were verified or adopted.",
    ),
    "material.author": M("作者", "Author"),
    "material.author_unknown": M("作者未提供", "Author not supplied"),
    "material.date": M("材料日期", "Material date"),
    "material.date_unknown": M("材料日期未提供", "Material date not supplied"),
    "material.scope": M("内容范围", "Content scope"),
    "material.scope_unknown": M(
        "范围未提供，不能视为全部研究", "Scope not supplied; this is not all research"
    ),
    "material.version": M("材料版本", "Material version"),
    "material.version_unknown": M("版本未提供", "Version not supplied"),
    "material.original": M("已提供的来源原文", "Supplied source original"),
    "material.original_boundary": M(
        "以上是来源原文，保持原样；界面说明不替作者补结论。",
        "The source text above is unchanged; "
        "UI explanations do not add conclusions for its author.",
    ),
    "material.summary_only": M(
        "只有摘要，不能称为已核对原文", "Summary only; this is not a checked original"
    ),
    "material.original_unknown": M(
        "原文未提供，当前不能核对原文", "Original not supplied; it cannot be checked here"
    ),
    "material.members": M("集合包含哪些成员？", "Which members are in this collection?"),
    "material.currency": M("金额币种", "Amount currency"),
    "material.currency_unknown": M(
        "币种未提供，不套用示例币种", "Currency not supplied; no example currency is assumed"
    ),
    "material.cost_unknown": M(
        "是否扣除买卖费用未提供", "Whether trading costs were deducted is not supplied"
    ),
    "material.cost_question": M("什么叫买卖费用？", "What are trading costs?"),
    "material.cost_definition": M(
        "每次买卖股票时另外支付的钱。",
        "Money paid in addition each time stocks are bought or sold.",
    ),
    "material.starting_amount": M("记录的开始金额", "Recorded starting amount"),
    "material.ending_amount": M("记录的结束金额", "Recorded ending amount"),
    "material.amount": M("记录的金额", "Recorded amount"),
}
