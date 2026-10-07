from ..translator import M

ENTRIES = {
    "plain.result.title": M("这次测试的记录说了什么？", "What does this test record say?"),
    "plain.result.evidence_title": M("核对这条测试结果记录", "Check this test result record"),
    "plain.result.untitled": M("测试报告未提供标题", "No test report title was provided"),
    "plain.result.test": M(
        "这里的测试是用过去的股票价格计算会赚还是亏，不是现在真的买卖股票。",
        "A test calculates profit or loss using past stock prices. It does not trade stocks now.",
    ),
    "plain.result.report_question": M("什么叫报告？", "What is a report?"),
    "plain.result.report_definition": M(
        "报告是测试结束后写下的结果记录。这里显示报告对应记录中已提供的金额和条件，不表示已经读到报告全文。",
        "A report records results after a test. This page shows amounts and conditions "
        "provided in the associated record, not a report we have read in full.",
    ),
    "plain.result.cost_question": M("什么叫买卖费用？", "What are trading costs?"),
    "plain.result.cost_definition": M(
        "每次买卖股票时另外支付的钱。扣除和未扣除买卖费用的金额不能混用。",
        "Money paid in addition when buying or selling stocks. "
        "Amounts with and without these costs are not interchangeable.",
    ),
    "plain.result.target_question": M("什么叫原定目标？", "What is the original target?"),
    "plain.result.target_definition": M(
        "测试前定下来的目标，不是已经赚到的钱。",
        "A target set before the test, not money already earned.",
    ),
    "plain.result.amount": M(
        "从 {start} {starting_unit}开始，{cost}有 {end} {unit}。",
        "Starting with {start} {starting_unit}, the ending amount is {end} {unit}, {cost}.",
    ),
    "plain.result.short.CNY": M("元", "CNY"),
    "plain.result.profit": M("赚了 {amount} {unit}。", "The profit is {amount} {unit}."),
    "plain.result.loss": M("亏了 {amount} {unit}。", "The loss is {amount} {unit}."),
    "plain.result.flat": M("没有赚也没有亏。", "There is no profit or loss."),
    "plain.result.target_missed": M(
        "没有达到至少赚 {target} {unit}的原定目标。",
        "It did not meet the original target of a profit of at least {target} {unit}.",
    ),
    "plain.result.target_met": M(
        "达到至少赚 {target} {unit}的原定目标。",
        "It met the original target of a profit of at least {target} {unit}.",
    ),
    "plain.result.target_cost_unknown": M(
        "原定目标是否扣除买卖费用未提供，不能直接核对原定目标。",
        "The target's trading-cost treatment was not provided, "
        "so the target cannot be checked directly.",
    ),
    "plain.result.target_cost_mismatch": M(
        "结果和原定目标处理买卖费用的方式不同，不能直接核对原定目标。",
        "The result and target treat trading costs differently, "
        "so the target cannot be checked directly.",
    ),
    "plain.result.field.target_costs_included": M(
        "原定目标是否扣除买卖费用", "Target trading-cost treatment"
    ),
    "plain.result.target_unknown": M(
        "原定目标未提供，不能判断是否达到目标。",
        "The original target was not provided, so it cannot be checked.",
    ),
    "plain.result.amount_unknown": M(
        "金额、币种或是否扣除买卖费用尚不明确，不能据此计算赚亏或判断是否达到目标。",
        "Amounts, currency, or trading-cost treatment are unclear. "
        "Profit, loss, and whether the target was met cannot be calculated from this record.",
    ),
    "plain.result.cost_included": M("扣除买卖费用后", "after deducting trading costs"),
    "plain.result.cost_excluded": M("未扣除买卖费用时", "without deducting trading costs"),
    "plain.result.unit.CNY": M("元（人民币）", "CNY"),
    "plain.result.unit.USD": M("美元", "USD"),
    "plain.result.unit.EUR": M("欧元", "EUR"),
    "plain.result.period": M(
        "这次记录提供的测试期间：{period}。", "Test period supplied in this record: {period}."
    ),
    "plain.result.period_unknown": M(
        "测试期间未提供，还不知道用了哪几年的股票价格。",
        "The test period was not provided. We do not know which years of stock prices were used.",
    ),
    "plain.result.limits": M(
        "这条金额记录只能说明这一次测试，不能据此判断其他年份或修改办法后的结果；这些情况需要查看对应记录。",
        "This amount record describes only this test. It cannot establish results "
        "for other years or changed rules; those require their own records.",
    ),
    "plain.result.no_content": M(
        "这条记录只提供了报告的编号，没有结果文字或金额，目前无法核对。",
        "This record provides only a report reference, with no result wording or amounts to check.",
    ),
    "plain.result.open_record": M(
        "查看这条测试结果记录中的文字", "Check the wording in this test result record"
    ),
    "plain.result.author_unknown": M("作者未提供。", "No author was provided."),
    "plain.result.author": M(
        "记录提供的作者：{author}。", "Author supplied in the record: {author}."
    ),
    "plain.result.source_text": M("记录中的原话", "Original wording in the record"),
    "plain.result.text_unknown": M(
        "这条记录没有提供结果文字。", "This record did not provide result wording."
    ),
    "plain.result.open": M("查看测试报告里写的金额", "Check the amounts in the test report record"),
    "plain.result.fields": M("这条记录中的金额和条件", "Amounts and conditions in this record"),
    "plain.result.calculation": M(
        "已提供且可核对的结束金额减去开始金额，得到赚亏；"
        "买卖费用的处理相同时，才能与原定目标比较。下面列出参与计算的值。",
        "When inputs are usable, profit or loss is the ending amount minus the starting amount. "
        "The target can only be compared with the same trading-cost treatment. "
        "The inputs are listed below.",
    ),
    "plain.result.no_full_report": M(
        "这里只核对上述记录内容，尚未核对报告原文。",
        "Only the record contents above are checked here. "
        "The original report has not been checked.",
    ),
    "plain.result.source_missing": M(
        "没有找到这条结果对应的来源，不能继续与报告核对。",
        "No matching source was found for this result, so it cannot be checked against the report.",
    ),
    "plain.result.not_found": M(
        "当前公开内容没有提供与这次选择匹配的测试结果记录，不能用另一份记录代替。",
        "The public content does not provide a test result record matching this selection. "
        "Another record cannot substitute for it.",
    ),
    "plain.result.unsafe": M(
        "这条结果的来源不能安全查看，不能继续与报告核对。",
        "The source for this result cannot be viewed safely, "
        "so it cannot be checked against the report.",
    ),
    "plain.result.unavailable": M(
        "当前结果内容不完整或不能用于判断；这里只保留已提供的记录，不能确认当前测试是否达到目标。",
        "The current result content is incomplete or unavailable for a determination. "
        "The supplied record is retained, but whether the current test met its target "
        "cannot be confirmed.",
    ),
    "plain.result.snapshot_drift": M(
        "读到的记录与这次选择的版本不一致，目前不能核对这次结果。",
        "The record does not match the selected snapshot. This result cannot currently be checked.",
    ),
    "plain.result.partial": M(
        "这里只读到了部分内容，未读到的内容可能影响判断。",
        "Only part of the content was read. Unread content may affect the determination.",
    ),
    "plain.result.scope": M(
        "测试结果记录 · 这里只读，不买卖股票", "Test result record · read-only, no stock trading"
    ),
    "plain.result.sample": M(
        "编造的示例，不是你的研究记录。", "A fabricated example, not your research record."
    ),
    "plain.result.field.starting_amount": M("开始金额", "Starting amount"),
    "plain.result.field.ending_amount": M("结束金额", "Ending amount"),
    "plain.result.field.currency": M("金额单位", "Currency"),
    "plain.result.field.costs_included": M("是否扣除买卖费用", "Trading-cost treatment"),
    "plain.result.field.target_profit_at_least": M(
        "原定目标：至少赚多少", "Original minimum profit target"
    ),
    "plain.result.field.period": M("测试期间", "Test period"),
    "plain.result.missing": M("未提供", "Not provided"),
}
