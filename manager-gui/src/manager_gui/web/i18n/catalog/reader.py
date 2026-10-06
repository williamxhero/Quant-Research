"""Bilingual copy owned by Reader v1.

R1-T4 imports and registers :data:`ENTRIES` at the central catalog boundary.
This module deliberately has no registration side effect so the R1-T2 slice can
be tested in isolation and cannot change the existing v0 page catalog.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..translator import M

READER_SECTION_KEYS: Mapping[str, str] = {
    "question": "reader.section.question",
    "known": "reader.section.known",
    "unknowns": "reader.section.unknowns",
    "why": "reader.section.why",
}

READER_CLAIM_EXPLANATION_KEYS: Mapping[str, str] = {
    "known": "reader.claim.known",
    "derived": "reader.claim.derived",
    "interpreted": "reader.claim.interpreted",
    "missing": "reader.claim.missing",
    "blocked": "reader.claim.blocked",
    "stale": "reader.claim.stale",
    "incomparable": "reader.claim.incomparable",
    "owner_text": "reader.claim.owner_text",
}

READER_LABEL_KEYS: Mapping[str, str] = {
    "source": "reader.label.source",
    "source_refs": "reader.label.source_refs",
    "derivation": "reader.label.derivation",
    "limitation": "reader.label.limitation",
    "gap": "reader.label.gap",
    "source_note": "reader.label.source_note",
    "owner_text": "reader.label.owner_text",
    "owner_fact": "reader.label.owner_fact",
    "raw_record": "reader.label.raw_record",
    "raw_value": "reader.label.raw_value",
    "raw_json": "reader.label.raw_json",
    "as_of": "reader.label.as_of",
    "snapshot_token": "reader.label.snapshot_token",
}

READER_MODE_LABEL_KEYS: Mapping[str, str] = {
    "reader": "label.reader_mode.reader",
    "expert": "label.reader_mode.expert",
    "raw": "label.reader_mode.raw",
}

ENTRIES: Mapping[str, M] = {
    "reader.section.question": M("这页回答什么", "What this page answers"),
    "reader.section.known": M("当前能确认什么", "What can currently be established"),
    "reader.section.unknowns": M("还不知道什么", "What is still unknown"),
    "reader.section.why": M("为什么这样说", "Why this is stated"),
    "reader.claim.known": M(
        "系统记录到来源公开发布的值。这表示已有记录，不表示研究证明了该结论。",
        "The system records a value published by the source. "
        "This establishes a record, not proof of a research conclusion.",
    ),
    "reader.claim.derived": M(
        "这是依据具名输入和规则可复现地计算的 {term:gui_derived_view}，不是新的属主事实。",
        "This is a reproducible {term:gui_derived_view} computed from named inputs "
        "and a named rule, not a new owner fact.",
    ),
    "reader.claim.interpreted": M(
        "这是来源发布的解读，不是新的属主事实，也不表示已验证。",
        "This is an interpretation published by the source, not a new owner fact "
        "or a verified result.",
    ),
    "reader.claim.missing": M(
        "当前来源范围内尚无可用记录。无法判断，不表示该值或关系不存在。",
        "No record is currently available in this source scope. "
        "A determination cannot be made; this does not mean the value or relationship is absent.",
    ),
    "reader.claim.blocked": M(
        "前置条件或读取关口阻止了判定。当前无法判断，不表示研究失败。",
        "A prerequisite or read gate prevents a determination. "
        "The result cannot currently be determined; this is not a research failure.",
    ),
    "reader.claim.stale": M(
        "这份记录已过时，只能作为历史来源查看，不能作为完整的当前事实。",
        "This record is stale. It can be inspected as a historical source, "
        "not used as complete current truth.",
    ),
    "reader.claim.incomparable": M(
        "比较所需的条件不兼容或不完整。当前不可比较，不推断优劣或成败。",
        "The conditions required for comparison are incompatible or incomplete. "
        "The objects cannot currently be compared; no ranking or outcome is inferred.",
    ),
    "reader.claim.owner_text": M(
        "以下是属主原文，按原样保留；不是 GUI 生成的解释或独立验证的结论。",
        "The following is the owner's original text, retained unchanged; "
        "it is not a GUI-generated explanation or an independently verified conclusion.",
    ),
    "reader.availability.not_evaluated": M(
        "当前来源范围尚未发布评估结果。未评估不表示成功或失败。",
        "No evaluation result has been published in this source scope. "
        "Not evaluated means neither success nor failure.",
    ),
    "reader.availability.integrity_failure": M(
        "来源未通过完整性核验，不能据此判断研究结果；这不是研究失败的结论。",
        "The source failed integrity verification and cannot establish a research result; "
        "this is not a conclusion that the research failed.",
    ),
    "reader.availability.api_unavailable": M(
        "批准的公开读取 API 当前不可用。无法读取不表示没有记录，不回退到私有存储。",
        "The approved public read API is currently unavailable. "
        "An unreadable source is not an empty record set; no private-storage fallback is used.",
    ),
    "reader.sample.banner": M(
        "样例数据，不代表真实研究结果。",
        "Sample data; not real research results.",
    ),
    "reader.label.source": M("{term:source}", "{term:source}"),
    "reader.label.source_refs": M("{term:source_reference}", "{term:source_reference}"),
    "reader.label.derivation": M("{term:derivation}", "{term:derivation}"),
    "reader.label.limitation": M("限制", "Limitation"),
    "reader.label.gap": M("知识缺口", "Knowledge gap"),
    "reader.label.source_note": M("来源说明", "Source note"),
    "reader.label.owner_text": M("属主原文", "Owner text"),
    "reader.label.owner_fact": M("属主记录事实", "Owner-recorded fact"),
    "reader.label.raw_record": M("原始记录", "Raw record"),
    "reader.label.raw_value": M("原始机器值", "Raw machine value"),
    "reader.label.raw_json": M("{term:raw_json}", "{term:raw_json}"),
    "reader.label.as_of": M("{term:as_of}", "{term:as_of}"),
    "reader.label.snapshot_token": M("{term:snapshot_token}", "{term:snapshot_token}"),
    "reader.boundary.raw": M(
        "原始记录、机器值和来源引用保持原样；阅读解释不会改写来源。",
        "Raw records, machine values and source references remain unchanged; "
        "Reader explanations do not rewrite the source.",
    ),
    "reader.derivation.direct": M(
        "直接来自标明的公开来源，未据此补充未记录的事实。",
        "Directly from the named public source; no unrecorded facts are added.",
    ),
    "reader.derivation.derived": M(
        'GUI 派生规则 <code translate="no">{name}</code>（版本 '
        '<code translate="no">{value}</code>）；结果不是新的属主事实。',
        'GUI derivation rule <code translate="no">{name}</code> '
        '(version <code translate="no">{value}</code>); the result is not a new owner fact.',
    ),
    "reader.derivation.interpreted": M(
        '来源解读规则 <code translate="no">{name}</code>（版本 '
        '<code translate="no">{value}</code>）；不是独立验证的结论。',
        'Source interpretation rule <code translate="no">{name}</code> '
        '(version <code translate="no">{value}</code>); not an independently verified conclusion.',
    ),
    "reader.source.reference": M(
        '来源引用 <code translate="no">{source_id}</code>：'
        '<code translate="no">{href}</code>',
        'Source reference <code translate="no">{source_id}</code>: '
        '<code translate="no">{href}</code>',
    ),
    "reader.source.count": M(
        "当前范围有 {n} 条来源引用。数量不表示证据强度。",
        {
            "one": "There is {n} source reference in this scope. "
            "The count is not evidence strength.",
            "other": "There are {n} source references in this scope. "
            "The count is not evidence strength.",
        },
    ),
    "reader.summary.claim_count": M(
        "当前引用了 {n} 条带来源的陈述。数量不表示研究成功或结论已验证。",
        {
            "one": "This summary references {n} sourced claim. "
            "The count establishes neither research success nor a verified conclusion.",
            "other": "This summary references {n} sourced claims. "
            "The count establishes neither research success nor a verified conclusion.",
        },
    ),
    "reader.summary.gap_count": M(
        "当前引用了 {n} 项知识缺口。无法判断的内容不视为失败。",
        {
            "one": "This summary references {n} knowledge gap. "
            "An undetermined result is not treated as a failure.",
            "other": "This summary references {n} knowledge gaps. "
            "An undetermined result is not treated as a failure.",
        },
    ),
    "label.reader_mode.reader": M("阅读模式", "Reader mode"),
    "label.reader_mode.expert": M("专业模式", "Expert mode"),
    "label.reader_mode.raw": M("原始模式", "Raw mode"),
    "label.reader_claim.known": M("{term:known}", "{term:known}"),
    "label.reader_claim.derived": M("{term:derived}", "{term:derived}"),
    "label.reader_claim.interpreted": M("{term:interpreted}", "{term:interpreted}"),
    "label.reader_claim.missing": M("{term:missing}", "{term:missing}"),
    "label.reader_claim.blocked": M("{term:blocked}", "{term:blocked}"),
    "label.reader_claim.stale": M("{term:stale}", "{term:stale}"),
    "label.reader_claim.incomparable": M("{term:incomparable}", "{term:incomparable}"),
    "label.reader_claim.owner_text": M("属主原文", "Owner text"),
}

__all__ = [
    "ENTRIES",
    "READER_CLAIM_EXPLANATION_KEYS",
    "READER_LABEL_KEYS",
    "READER_MODE_LABEL_KEYS",
    "READER_SECTION_KEYS",
]
