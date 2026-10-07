from ..translator import M

ENTRIES = {
    "plain.memory.state.not_tested": M(
        "记录明确说明还没有做这次测试。", "The record explicitly says this test has not been run."
    ),
    "plain.memory.state.stopped": M(
        "测试停止；这不是一份完整的测试结果。", "The test stopped; this is not a completed result."
    ),
    "plain.memory.state.missed": M(
        "测试已完成，但没有达到原定目标。",
        "The test completed but did not meet its original target.",
    ),
    "plain.memory.state.calculated_met": M(
        "页面比较已提供的金额：达到原定目标。",
        "GUI comparison of the supplied amounts: the original target was met.",
    ),
    "plain.memory.state.conflicting": M(
        "记录的目标结论与已提供金额矛盾；尚不能确定达标。",
        "The recorded goal verdict conflicts with the supplied amounts; "
        "achievement is not established.",
    ),
    "plain.memory.state.fields_conflict": M(
        "已提供的执行或目标记录彼此矛盾；尚不能确定完成或达标。",
        "Supplied execution or goal fields disagree; "
        "completion and achievement are not established.",
    ),
    "plain.memory.state.met": M(
        "记录明确说明已完成的测试达到原定目标。",
        "The record explicitly says the completed test met its original target.",
    ),
    "plain.memory.missing": M(
        "没有提供与当前选择匹配的记录；这不等于没有做过测试。",
        "No matching record was supplied; this does not mean no test was run.",
    ),
    "plain.memory.goal_fields_gap": M(
        "记录另有失败或错误标记。它不能说明测试未达金融目标，也不能用金额绕过这个差异而确认达标。",
        "The record also contains a failure marker or an error marker. It does not establish a missed "
        "financial target, and the amounts cannot bypass this discrepancy to confirm achievement.",
    ),
    "plain.memory.target": M("测试前的原定目标", "Original target set before the test"),
    "plain.memory.target_unknown": M(
        "测试前的目标未提供，不能把实际结果当成原定目标。",
        "The before-test target was not provided; actual results cannot substitute for it.",
    ),
    "plain.memory.actual": M("实际结果和条件", "Actual results and conditions"),
    "plain.memory.amount_unknown": M(
        "赚亏未知：没有完整的开始和结束金额、币种、期间或买卖费用条件，不能判断赚了还是亏了。",
        "Profit or loss is unknown: complete starting and ending amounts, currency, period, "
        "or trading-cost conditions were not supplied. Neither profit nor loss is established.",
    ),
    "plain.memory.limits_unknown": M(
        "适用条件和限制未提供。", "Conditions and limits were not supplied."
    ),
    "plain.memory.bounded": M(
        "这里只说明这条记录对应的尝试，不能推广到其他办法、期间或以后一定能不能赚钱。",
        "This describes only the attempt associated with this record, not other rules, periods, "
        "or whether they will make or lose money in future.",
    ),
    "plain.memory.report_summary": M("报告最后的总结", "Report-ending summary"),
    "plain.memory.independent_lesson": M("独立发布的经验记录", "Independent recorded lesson"),
    "plain.memory.attempt": M("已提供的尝试记录", "Supplied attempt record"),
    "plain.memory.same_report": M(
        "这段话属于同一份报告，不是第二份独立来源。",
        "This paragraph belongs to the same report, not a second independent source.",
    ),
    "plain.memory.origin": M(
        "来自哪次尝试或哪份报告？", "Which attempt or report did this come from?"
    ),
    "plain.memory.origin_unknown": M(
        "对应尝试或报告未提供，不能替它选择另一份材料。",
        "The associated attempt or report was not supplied; another cannot substitute for it.",
    ),
    "plain.memory.change_question": M(
        "什么叫每日股票价格变动？", "What is daily stock price change?"
    ),
    "plain.memory.change_definition": M(
        "与前一个交易日相比，股票价格涨跌多少。交易日是可以买卖股票的日子，不一定是日历上的昨天。",
        "Daily change means how much the stock price rose or fell "
        "compared with the previous trading day. "
        "A trading day is a day when stocks can be traded, "
        "not necessarily yesterday on the calendar.",
    ),
    "plain.memory.smaller": M(
        "记录的挑选方向是每日股票价格变动幅度较小的股票。",
        "The recorded selection seeks stocks with smaller daily stock price changes.",
    ),
    "plain.memory.threshold_unknown": M(
        "“较小”的标准未提供。", "The threshold for “smaller” was not supplied."
    ),
    "plain.memory.group_title": M("已提供案例的整理", "Grouping of supplied cases"),
    "plain.memory.similar_not_cause": M(
        "观察到的现象相似，不等于原因相同。",
        "Similar observations do not establish a shared cause.",
    ),
    "plain.memory.observable": M("哪些可观察现象相似？", "Which observed phenomena are similar?"),
    "plain.memory.observable_unknown": M(
        "具体共同现象未说明；保留下方已发布的整理规则，不替它猜原因。",
        "No concrete common phenomenon was stated. "
        "The published grouping rule below is retained; no cause is inferred.",
    ),
    "plain.memory.rule": M("按什么规则整理？", "What rule arranged these cases?"),
    "plain.memory.rule_unknown": M("整理规则未提供。", "No grouping rule was supplied."),
    "plain.memory.scope": M("整理了哪个范围？", "What range was grouped?"),
    "plain.memory.scope_unknown": M(
        "范围未提供，不能说覆盖了全部案例。",
        "No scope was supplied; full case coverage is not established.",
    ),
    "plain.memory.published_count": M("记录提供的数量", "Count supplied in the record"),
    "plain.memory.count_mismatch": M(
        "已发布记录数量与这里识别到的输入不一致；尚不能确认总量。",
        "The published record count differs from the identified inputs; no total is confirmed.",
    ),
    "plain.memory.count_unknown": M("记录未提供数量。", "No count was supplied."),
    "plain.memory.count_unit": M("记录中的数量指什么？", "What does the published count measure?"),
    "plain.memory.unit_unknown": M(
        "数量单位未提供，不能当作测试或研究数量。",
        "No count unit was supplied; it cannot be called a test or study count.",
    ),
    "plain.memory.dedup": M("重复案例怎样处理？", "How were duplicate cases handled?"),
    "plain.memory.dedup_unknown": M(
        "已发布数量的去重规则未提供。", "Deduplication for the published count was not supplied."
    ),
    "plain.memory.filters": M("记录采用了哪些筛选？", "What filters did the record use?"),
    "plain.memory.filters_unknown": M(
        "记录中的筛选未提供；当前页面查询在统计依据中按原样列出。",
        "Published filters were not supplied; "
        "the current page query is retained in the count support.",
    ),
    "plain.memory.identified": M(
        "这里识别到 {n} 条已提供内容的输入记录。",
        "{n} input records with supplied content are identified here.",
    ),
    "plain.memory.input_count_rule": M(
        "这里列出这组写明的案例。同一记录编号只计一次。缺编号或缺内容时，"
        "数量仍不确定；现象相似不能证明原因相同。",
        "These are the supplied cases named in this group. "
        "Cases sharing the same recorded number are counted once. "
        "Missing numbers or missing content leave the count uncertain; "
        "a similar observation is not proof of the same cause.",
    ),
    "plain.memory.identity_unknown": M(
        "输入编号未提供；不能把这个案例算作一条已明确识别的记录。",
        "Input identity was not supplied; "
        "this case cannot be counted as a uniquely identified record.",
    ),
    "plain.memory.cases": M("逐项查看已提供的案例", "Read each supplied case"),
    "plain.memory.membership_gap": M(
        "已提供的案例名单与编号名单不一致；这里保留写明的案例，但尚不能确认完整范围。",
        "The supplied case list differs from the identifier list. "
        "Named cases are retained here, but complete coverage is not established.",
    ),
    "plain.memory.input_conflict": M(
        "同一记录编号对应不同的已提供内容；这里不把其中一条选作确定结论。",
        "Different supplied contents share the same record number; "
        "neither is selected as definitive.",
    ),
    "plain.memory.input_missing": M(
        "引用的输入未提供内容：{identifier}", "Referenced input was not supplied: {identifier}"
    ),
    "plain.memory.technical": M("补充：专业记录核对", "Supplement: technical record details"),
    "plain.memory.untitled": M("记录未提供标题", "No record title was provided"),
    "plain.memory.text_unknown": M("具体内容未提供。", "No concrete wording was supplied."),
    "plain.memory.state.ended_unknown": M(
        "执行结束；是否达到原定目标仍未知。",
        "Execution ended; whether the original target was met is unknown.",
    ),
    "plain.memory.state.unknown": M(
        "还不能确定是否测试过、是否完成或是否达到原定目标。未知不等于失败。",
        "Whether a test was run, completed, or met its original target is unknown. "
        "Unknown is not failure.",
    ),
    "plain.memory.reason": M("记录写明的原因", "Reason stated in the record"),
    "plain.memory.reason_unknown": M(
        "原因未记录；问题类别或代码不能说明原因。",
        "No reason was recorded; the category or code does not establish a cause.",
    ),
}
