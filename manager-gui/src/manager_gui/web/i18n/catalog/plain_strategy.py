"""UI-only, validated bilingual explanations of supplied strategy records."""

# Reader sentences intentionally remain complete and deterministic.
# ruff: noqa: E501
from ..translator import M

ENTRIES = {
    "plain.strategy.descriptor_status": M(
        "记录中的状态（不能据此断言实际测试结果）",
        "Recorded status (not a confirmed observed test result)",
    ),
    "plain.strategy.title": M(
        "买卖和挑选股票的办法写了什么？", "What do the stock selection and trading rules say?"
    ),
    "plain.strategy.unnamed": M("未命名的办法记录", "Unnamed method record"),
    "plain.strategy.not_found": M(
        "没有找到所选办法的记录，不能借用另一套办法的条件。",
        "The selected method record was not found. Another method's conditions cannot be substituted.",
    ),
    "plain.strategy.incomplete": M(
        "这份说明还不能当作完整可执行的买卖办法；提供的条件与关键缺口如下。",
        "This description is not yet a complete executable trading method. Supplied conditions and important gaps follow.",
    ),
    "plain.strategy.signal_question": M("什么叫买卖提示？", "What is a trading signal?"),
    "plain.strategy.signal_definition": M(
        "按记录中的条件发出的买入或卖出提示，不代表已经实际买卖股票。",
        "A suggestion to buy or sell when recorded conditions hold; it does not mean stocks have actually been traded.",
    ),
    "plain.strategy.entry": M("什么时候提示买入？", "When is buying suggested?"),
    "plain.strategy.exit": M("什么时候提示卖出？", "When is selling suggested?"),
    "plain.strategy.universe": M("怎样挑选股票？", "How are stocks selected?"),
    "plain.strategy.risk_controls": M("怎样限制可能的损失？", "How are possible losses limited?"),
    "plain.strategy.timing": M("在什么时刻检查条件？", "When are conditions checked?"),
    "plain.strategy.missing": M("这部分条件未提供。", "These conditions were not provided."),
    "plain.strategy.unexplained": M(
        "记录提供了配置，但没有说明它具体怎样判断；可打开对应记录核对，不能据此补出条件。",
        "Configuration was supplied without an explanation of how it decides. Open the corresponding record to check it; missing conditions cannot be invented.",
    ),
    "plain.strategy.positive": M(
        "提供的信号为正时提示买入；这个信号怎样计算还需核对记录。",
        "The rule suggests buying when the supplied signal is positive; how that signal is calculated still needs checking in the record.",
    ),
    "plain.strategy.negative": M(
        "提供的信号为负时提示卖出；这个信号怎样计算还需核对记录。",
        "The rule suggests selling when the supplied signal is negative; how that signal is calculated still needs checking in the record.",
    ),
    "plain.strategy.execution_unknown": M(
        "实际买卖时刻和股票价格未提供。买卖提示不是实际成交，不能据此复现完整买卖。",
        "Actual execution time and stock price were not provided. Signals are not executions and cannot reproduce complete trades.",
    ),
    "plain.strategy.execution_partial": M(
        "实际买卖细节未完整提供，或目前无法核对。买卖提示不是实际成交，不能据此复现完整买卖。",
        "Execution details were not fully provided or cannot currently be verified. Signals are not executions and cannot reproduce complete trades.",
    ),
    "plain.strategy.execution": M(
        "实际买卖时刻和股票价格的记录", "Recorded execution time and stock price"
    ),
    "plain.strategy.period": M("实际测试期间", "Actual test period"),
    "plain.strategy.market": M("实际测试市场", "Actually tested market"),
    "plain.strategy.currency": M("金额的币种", "Currency of amounts"),
    "plain.strategy.costs": M("买卖费用", "Trading costs"),
    "plain.strategy.period_unknown": M(
        "实际测试期间未提供，不能从规则检查时刻推断。",
        "The actual test period was not provided; it cannot be inferred from rule timing.",
    ),
    "plain.strategy.market_unknown": M(
        "实际测试市场未提供；挑选股票的配置不说明在这些市场分别测试过。",
        "Actually tested markets were not provided. Stock selection configuration does not establish separate tests in those markets.",
    ),
    "plain.strategy.currency_unknown": M(
        "币种未提供，不能默认人民币或换算金额。",
        "Currency was not provided. CNY cannot be assumed and amounts cannot be converted.",
    ),
    "plain.strategy.costs_unknown": M(
        "买卖费用及是否扣除未提供，不能判断扣除买卖费用后的赚亏。",
        "Trading costs and whether they were deducted were not provided. Profit or loss after deducting trading costs cannot be established.",
    ),
    "plain.strategy.costs_boundary": M(
        "配置中的买卖费用不证明测试结果已扣除买卖费用。",
        "Configured trading costs do not establish that a test result deducted them.",
    ),
    "plain.strategy.conditions": M(
        "在哪些条件下有测试记录？", "Which conditions have test records?"
    ),
    "plain.strategy.conditions_unknown": M(
        "没有找到适用或不适用条件的测试记录；不表示明确没有测试过。",
        "No test records of applicable or invalidating conditions were found; this does not mean they were explicitly never tested.",
    ),
    "plain.strategy.untested": M(
        "未分别测试的市场仍然未知，不能推断成功、失败或普遍适用。",
        "Untested markets remain unknown. Success, failure, or general applicability cannot be inferred.",
    ),
    "plain.strategy.descriptor": M(
        "描述条件不是实际测试结果，不能据此说在哪些市场有效。",
        "A descriptive condition is not an observed test result and cannot establish effectiveness in a market.",
    ),
    "plain.strategy.condition_unnamed": M("未命名的条件记录", "Unnamed condition record"),
    "plain.strategy.outcome": M("这条条件的测试结果", "Test outcome for this condition"),
    "plain.strategy.time": M("这条条件的测试期间或时刻", "Test period or time for this condition"),
    "plain.strategy.scope": M("这条记录覆盖哪里", "Scope covered by this record"),
    "plain.strategy.evidence": M("记录提供的相关依据", "Related evidence supplied in the record"),
    "plain.strategy.revisions": M("版本具体改了什么？", "What exactly changed between versions?"),
    "plain.strategy.modification": M(
        "修改不等于效果改善。需要同期间、市场、数据和买卖费用条件的结果才能继续核对。",
        "A modification is not evidence of improvement. Results with matching periods, markets, data, and trading costs are needed for further checks.",
    ),
    "plain.strategy.revisions_unknown": M(
        "没有找到版本修改记录；不能猜测改动或修改原因。",
        "No revision change records were found. Changes and reasons cannot be guessed.",
    ),
    "plain.strategy.revision": M("这份版本记录", "This revision record"),
    "plain.strategy.parent": M("由哪个版本修改", "Parent revision"),
    "plain.strategy.changes": M("具体修改", "Specific changes"),
    "plain.strategy.reason": M("记录中的修改原因", "Recorded reason for the change"),
    "plain.strategy.result": M("记录中的结果", "Recorded result"),
    "plain.strategy.limitations": M("记录中的限制", "Recorded limitations"),
    "plain.strategy.supported": M(
        "记录称这条条件得到测试支持；不代表其他条件也成立。",
        "The record says this condition was supported by the test, not that other conditions hold.",
    ),
    "plain.strategy.failed": M(
        "记录称这条条件未通过测试；不代表未测试的其他条件也失败。",
        "The record says this condition failed the test; no failure is implied for other untested conditions.",
    ),
    "plain.strategy.not_evaluated": M(
        "这条条件明确尚未测试。", "This condition is explicitly not yet tested."
    ),
    "plain.strategy.daily_movement": M(
        "想挑每日股票价格上下变动幅度较小的股票。幅度是与前一个交易日结束时的股票价格相比涨跌多少。",
        "The intention is to select stocks with smaller daily up/down stock-price movements: how much the closing stock price rose or fell relative to the previous trading day.",
    ),
    "plain.strategy.threshold_unknown": M(
        "“较小”的标准未提供，不能补出具体阈值。",
        "The threshold for “smaller” was not provided and cannot be invented.",
    ),
    "plain.strategy.threshold": M("记录提供的“较小”标准", "Supplied threshold for “smaller”"),
    "plain.strategy.day_question": M("什么叫交易日？", "What is a trading day?"),
    "plain.strategy.day_definition": M(
        "可以买卖股票的日子。前一个交易日不一定是日历上的昨天。",
        "A day when stocks can be traded. The previous trading day is not necessarily calendar yesterday.",
    ),
    "plain.strategy.mean_question": M(
        "这份编造示例怎样计算平均价？",
        "How does this fabricated example calculate its mean stock price?",
    ),
    "plain.strategy.mean_definition": M(
        "每个交易日分别计算：把当天及之前 19 个交易日结束时的股票价格相加，再除以 20。前一个交易日用那一天的平均价，当天用当天的平均价。",
        "Calculate separately for each trading day: add the closing stock prices for that day and the preceding 19 trading days, then divide by 20. The previous trading day uses its own mean; the current day uses its own mean.",
    ),
    "plain.strategy.daily_timing": M(
        "这份编造示例每天交易结束后比较一次。",
        "This fabricated example compares once after trading ends each trading day.",
    ),
    "plain.strategy.daily_entry": M(
        "两条同时满足才提示买入：前一个交易日结束时不高于那一天的平均价；当天结束时高于当天的平均价。比较的是各自结束时的股票价格与各自的 20 个交易日平均价。",
        "Both conditions must hold to suggest buying: the previous close is at or below its own mean; the current close is above its own mean. Each closing stock price is compared with its own 20-trading-day mean.",
    ),
    "plain.strategy.daily_exit": M(
        "两条同时满足才提示卖出：前一个交易日结束时不低于那一天的平均价；当天结束时低于当天的平均价。比较的是各自结束时的股票价格与各自的 20 个交易日平均价。",
        "Both conditions must hold to suggest selling: the previous close is at or above its own mean; the current close is below its own mean. Each closing stock price is compared with its own 20-trading-day mean.",
    ),
    "plain.strategy.fake_amounts": M(
        "如有展示金额，它们仍是编造素材，不是按这份不完整规则实际运行算出的结果。",
        "Any displayed amounts remain fabricated material, not results of an actual run of these incomplete rules.",
    ),
    "plain.strategy.comparison_title": M(
        "两个对象哪里不同，能公平比较吗？",
        "What differs between these objects, and can they be compared fairly?",
    ),
    "plain.strategy.no_comparison": M(
        "没有读到完整的两个比较对象，不能借用其他对象的结果。",
        "Two complete comparison objects were not read. Other objects' results cannot be substituted.",
    ),
    "plain.strategy.unnamed_object": M("未命名的比较对象", "Unnamed comparison object"),
    "plain.strategy.side_definition": M(
        "这里 {left} 指左侧对象，{right} 指右侧对象；下文和依据沿用记录提供的同一名称。",
        "{left} refers to the left object and {right} to the right object. The same supplied names are used below and in supporting records.",
    ),
    "plain.strategy.no_winner": M(
        "这里逐项核对比较条件，不能选出赢家或补出完整赚亏结果。配置相同不等于效果一样好。",
        "This page checks comparison conditions one by one; it cannot select a winner or invent complete profit/loss results. Matching configuration does not mean equal performance.",
    ),
    "plain.strategy.axis.equal": M(
        "这项记录值相同，只说明这项条件匹配。",
        "These recorded values match, establishing only that this condition matches.",
    ),
    "plain.strategy.axis.different": M(
        "这项条件不同，不能把不同条件下的结果当成谁更好的证明。",
        "These conditions differ. Results under different conditions cannot establish which object is better.",
    ),
    "plain.strategy.axis.missing": M(
        "这项条件未完整提供，目前不能核对是否匹配。",
        "This condition was not fully provided, so a match cannot be checked.",
    ),
    "plain.strategy.axis.not_comparable": M(
        "这项必要比较条件缺失或不一致，当前不能公平比较。",
        "A necessary comparison condition is absent or inconsistent; a fair comparison is currently refused.",
    ),
    "plain.strategy.axis.identity": M(
        "比较的是同一类对象吗？", "Are these the same kind of object?"
    ),
    "plain.strategy.axis.eligibility": M(
        "记录允许这样比较吗？", "Do the records permit this comparison?"
    ),
    "plain.strategy.axis.source_generation": M(
        "提供记录的版本一致吗？", "Do the supplied record versions match?"
    ),
    "plain.strategy.axis.snapshot": M(
        "读取的是同一批记录吗？", "Were the same set of records read?"
    ),
    "plain.strategy.axis.data_version": M(
        "股票价格等数据的版本一致吗？", "Do versions of stock prices and other data match?"
    ),
    "plain.strategy.axis.universe": M(
        "测试了哪些市场或股票？", "Which markets or stocks were tested?"
    ),
    "plain.strategy.axis.time_range": M(
        "用了哪段期间的股票价格？", "Which periods of stock prices were used?"
    ),
    "plain.strategy.axis.protocol": M(
        "测试采用的步骤和要求一致吗？", "Do test procedures and requirements match?"
    ),
    "plain.strategy.axis.randomness": M(
        "随机挑选等安排一致吗？", "Do random-selection settings match?"
    ),
    "plain.strategy.axis.costs": M("怎样处理买卖费用？", "How are trading costs treated?"),
    "plain.strategy.axis.fills": M(
        "按什么时刻和股票价格计算实际买卖？", "Which time and stock price are used for executions?"
    ),
    "plain.strategy.axis.metric_definition": M(
        "结果的计算方式一致吗？", "Do result calculation methods match?"
    ),
    "plain.strategy.axis.evidence_sections": M(
        "比较用了哪些结果记录？", "Which result records are used for comparison?"
    ),
    "plain.strategy.axis.currency": M("金额币种一致吗？", "Do the currencies of amounts match?"),
    "plain.strategy.factor": M(
        "因子是用于描述或挑选股票的一项量，不是完整买卖办法。买入、卖出和实际买卖条件仍需各自提供。",
        "A factor is a measure used to describe or select stocks, not a complete trading method. Buy, sell, and execution conditions must be supplied separately.",
    ),
    "plain.strategy.main_conditions": M(
        "主要办法条件和实际买卖细节已提供；这说明记录写了什么，不证明测试赚钱或规则实现正确。",
        "The main method conditions and execution details are supplied. This describes the record, not proof of profitable tests or a correct implementation.",
    ),
    "plain.strategy.drawdown": M(
        "配置把从资金总值最高点往下减少的比例限制在 {percent}%；这是记录的风险限制，不是实际亏损结果。",
        "The configuration limits the fall from the highest total account value to {percent}%. This is a recorded risk limit, not an observed loss.",
    ),
    "plain.strategy.selection_scope": M(
        "记录指定的挑选范围：{scope}。这不说明在这些市场分别测试过。",
        "Configured selection scope: {scope}. This does not establish separate tests in these markets.",
    ),
    "plain.strategy.decision_delay": M(
        "记录要求延后 {n} 个数据间隔判断；间隔长度和实际钟点未提供，不能默认下一天成交。",
        "The record delays decisions by {n} data intervals. Actual clock time was not provided, and neither was the interval length; next-day execution cannot be assumed.",
    ),
    "plain.strategy.commission": M(
        "配置中每买卖 10,000 单位金额另外支付 {n} 单位的买卖费用；币种仍须由记录说明。这不证明测试金额已扣除买卖费用。",
        "The configuration charges {n} units in trading costs per 10,000 units traded. Currency still requires a record. This does not establish that test amounts deducted trading costs.",
    ),
    "plain.strategy.execution_time": M("实际买卖时刻", "Execution time"),
    "plain.strategy.execution_price": M("实际买卖的股票价格", "Execution stock price"),
    "plain.strategy.axis.unverified": M(
        "读取不完整、过时或对应资料有问题，目前不能核对这项比较条件；下面仅保留提供的记录值。",
        "The read is incomplete, out of date, or has source issues. We cannot currently verify this comparison condition; supplied record values remain below.",
    ),
    "plain.strategy.supplement": M(
        "补充：专业字段与原有核对内容", "Supplement: technical fields and existing checks"
    ),
}
