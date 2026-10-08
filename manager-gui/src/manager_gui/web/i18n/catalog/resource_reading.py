from ..translator import M

ENTRIES = {
    "resource_reading.cannot_list": M(
        "当前公共接口无法列出这些记录；当前可读取范围不构成完整目录，不能据此判断没有记录。",
        "The current public interface cannot list these records; the currently readable scope "
        "is not a complete catalog and cannot establish that no records exist.",
    ),
    "resource_reading.confirmed_empty": M(
        "公共读取确认：当前范围没有记录。这只描述本次读取范围，不代表其他范围或未来也没有记录。",
        "Public read confirmed: no records in the current scope. This describes only this read's "
        "scope, not other scopes or future records.",
    ),
    "resource_reading.missing": M(
        "字段或集合未记录，不能当成确认的空集合。",
        "The field or collection is not recorded; it is not a confirmed empty collection.",
    ),
    "resource_reading.object_fields": M(
        "对象存在，但所需字段或集合未记录；对象身份不等于该字段已有内容。",
        "The object exists, but the required field or collection is not recorded; "
        "object identity does not establish field content.",
    ),
    "resource_reading.partial": M(
        "当前可读取范围尚不完整；只能说明已读取的内容，不能确认完整目录为空。",
        "The currently readable scope is incomplete; only supplied content can be described, "
        "not an empty complete catalog.",
    ),
    "resource_reading.read_failed": M(
        "公共读取失败或包含来源错误；不能据此确认没有记录。已提供的内容仅保留作受限参考。",
        "Public reading failed or contains source errors; absence cannot be confirmed. "
        "Supplied content is retained only as a limited reference.",
    ),
    "resource_reading.blocked": M(
        "公共读取被阻塞；权限、政策或数据门槛未允许确认内容，不能解释为没有记录。",
        "Public reading is blocked; permission, policy or data gates prevent confirmation. "
        "This does not establish absence.",
    ),
    "resource_reading.stale": M(
        "读取结果已过时；保留的身份与内容不能作为当前有效结论。",
        "The read result is stale; retained identity and content do not establish "
        "a current conclusion.",
    ),
    "resource_reading.integrity_failure": M(
        "读取完整性验证失败；保留的引用不能作为已核验依据。",
        "Read integrity validation failed; retained references are not verified support.",
    ),
    "resource_reading.incomparable": M(
        "对象或条件不可比；不能排序、选出优胜者或迁移结论。",
        "Objects or conditions are incomparable; no ranking, winner or transferred "
        "conclusion is justified.",
    ),
    "resource_reading.supplied": M(
        "按本次公共输入呈现记录；对象已有记录不表示所有字段都有定义。",
        "Records are shown from the supplied public input; recorded objects do not imply "
        "every field is defined.",
    ),
    "resource_reading.unknown_fields": M(
        "未提供的金额、币种、费用、期间、市场、条件、目标和作者保持未知，不以示例值补齐。",
        "Unprovided amount, currency, costs, period, market, conditions, objective and author "
        "remain unknown; no example defaults fill them in.",
    ),
    "resource_reading.impact.strategies": M(
        "只有明确的基因组记录才能说明策略结构；包数量不能替代基因组目录，也不能证明策略有效。",
        "Only explicit Genome records describe strategy structure; package counts cannot replace "
        "a Genome catalog or establish effectiveness.",
    ),
    "resource_reading.impact.strategy-conditions": M(
        "缺少条件测试及依据时，无法判断适用或失效边界；描述性背景不是已验证条件。",
        "Without condition tests and support, applicability or invalidation boundaries cannot be "
        "judged; descriptive context is not a validated condition.",
    ),
    "resource_reading.impact.strategy-genome-comparison": M(
        "比较需要明确对象、条件与比较轴；基因组或证据的存在本身不能证明可比或选出更好策略。",
        "Comparison requires explicit objects, conditions and axes; Genomes or evidence alone "
        "establish neither comparability nor a better strategy.",
    ),
    "resource_reading.impact.memory": M(
        "缺少独立发布的经验及依据时，不能判断哪些经验可复用；报告总结和运行结果不会自动成为研究记忆。",
        "Without independently published experience and support, reusability cannot be judged; "
        "report summaries and run results do not automatically become Research Memory.",
    ),
    "resource_reading.impact.memory-failures": M(
        "失败经验需要失败性质、条件与依据；一次失败运行不能自动成为失败经验，未知原因不构成失败模式依据。",
        "Failure experience needs failure nature, conditions and support; a failed run does not "
        "automatically become failure experience, and an unknown cause is not a confirmed "
        "failure pattern.",
    ),
    "resource_reading.impact.failure-patterns": M(
        "没有实际失败经验和明确模式记录时，不能判断失败是否重复；失败运行数量不能替代失败模式。",
        "Without actual failure experience and explicit pattern records, repetition cannot be "
        "judged; failed-run counts do not substitute for failure patterns.",
    ),
    "resource_reading.impact.derived-failure-grouping": M(
        "分组仅沿用既有合法派生规则和实际输入；没有输入就没有分组，"
        "不增加 AI 推断，也不把分组提升为正式经验。",
        "Grouping uses only existing lawful derivation rules and actual inputs; no inputs means "
        "no groups, no AI inference, and no promotion of groups to formal experience.",
    ),
    "resource_reading.impact.evidence-object-comparison": M(
        "证据存在不等于已有比较记录或可比条件；缺少对象、期间、市场或条件时，不能凭证据选择优胜者。",
        "Evidence existence does not imply comparison records or comparable conditions; without "
        "objects, period, market or conditions, evidence cannot select a winner.",
    ),
    "resource_reading.impact.methodology": M(
        "研究方法需要明确的方法记录；包、报告或方法描述不能替代方法有效性的依据。",
        "Research methods require explicit method records; packages, reports "
        "or method descriptions "
        "do not substitute for evidence of method validity.",
    ),
}
