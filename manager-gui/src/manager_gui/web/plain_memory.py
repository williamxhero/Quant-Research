"""UI-only explanations of supplied lessons, attempts and grouping inputs.

Execution and goal outcomes are deliberately read from original explicit fields,
not the published Reader projection's historical success/failure buckets.
"""
# HTML fragments follow the existing server-rendered page convention.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, localcontext
from html import escape

from .i18n import Translator
from .source_support import (
    source_support_computation,
    source_support_entry,
    source_support_impact,
    source_support_usable,
)


def value(record: Mapping[str, object], *keys: str) -> object | None:
    for key in keys:
        item = record.get(key)
        if item is not None and item not in ("", [], {}):
            return item
    return None


def owner(value: object) -> str:
    """Preserve supplied free text, including whitespace, without translating it."""
    return f'<span data-owner-text="true" translate="no">{escape(str(value))}</span>'


def t(translator: Translator, key: str, **params: object) -> str:
    return escape(translator.t("plain.memory." + key, **params))


def _number(value: object) -> Decimal | None:
    if type(value) not in {int, float}:
        return None
    number = Decimal(str(value))
    return number if number.is_finite() else None


def _format(number: Decimal) -> str:
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _fields(record: Mapping[str, object], translator: Translator) -> str:
    rows = []
    for key in (
        "starting_amount",
        "ending_amount",
        "currency",
        "period",
        "costs_included",
        "target_profit_at_least",
        "target_costs_included",
    ):
        supplied = value(record, key)
        if key.endswith("costs_included"):
            content = (
                translator.html(
                    "plain.result.cost_included"
                    if supplied is True
                    else "plain.result.cost_excluded"
                )
                if type(supplied) is bool
                else translator.html("plain.result.missing")
            )
        elif key == "currency" and supplied in {"CNY", "USD", "EUR"}:
            content = translator.html("plain.result.unit." + str(supplied))
        else:
            content = (
                owner(supplied) if supplied is not None else translator.html("plain.result.missing")
            )
        rows.append(
            f"<div><dt>{translator.html('plain.result.field.' + key)}</dt><dd>{content}</dd></div>"
        )
    return "<dl>" + "".join(rows) + "</dl>"


def _financial_result(
    record: Mapping[str, object], translator: Translator, execution: str
) -> tuple[str, str | None]:
    start, end = _number(record.get("starting_amount")), _number(record.get("ending_amount"))
    currency = value(record, "currency")
    costs = record.get("costs_included")
    if (
        execution not in {"completed", "finished"}
        or start is None
        or end is None
        or not isinstance(currency, str)
        or value(record, "period") is None
        or type(costs) is not bool
        or not source_support_usable(record)
    ):
        return t(translator, "amount_unknown"), None
    # Precision follows supplied decimal lengths; no conversion or rate is inferred.
    with localcontext() as arithmetic:
        arithmetic.prec = len(format(start, "f")) + len(format(end, "f")) + 2
        profit = end - start
    unit = (
        translator.t("plain.result.unit." + currency)
        if currency in {"CNY", "USD", "EUR"}
        else currency
    )
    result = (
        translator.html(
            "plain.result.profit" if profit > 0 else "plain.result.loss",
            amount=_format(profit.copy_abs()),
            unit=unit,
        )
        if profit
        else translator.html("plain.result.flat")
    )
    target = _number(record.get("target_profit_at_least"))
    target_cost = record.get("target_costs_included")
    if target is None:
        return result, None
    if type(target_cost) is not bool:
        return result + " " + translator.html("plain.result.target_cost_unknown"), None
    if target_cost != costs:
        return result + " " + translator.html("plain.result.target_cost_mismatch"), None
    return result + " " + translator.html("plain.result.calculation"), "met" if profit >= target else "missed"


def render_case_group(
    record: Mapping[str, object],
    *,
    translator: Translator,
    rule: str | None,
    scope: tuple[str, ...],
    sample_count: int | None,
    inputs: tuple[tuple[str, Mapping[str, object] | None], ...],
    query_context: str,
    complete: bool,
    sample: bool = False,
) -> str:
    """Explain the supplied grouping, without recomputing its published outcome."""
    title = value(record, "title", "label", "name")
    cases = []
    missing = False
    all_inputs = []
    known = 0
    for identifier, supplied in inputs:
        content = supplied is not None and any(
            value(supplied, key) is not None
            for key in (
                "safe_summary",
                "summary",
                "text",
                "description",
                "reason",
                "stop_reason",
                "actual_result",
                "execution_status",
                "status",
                "outcome",
                "goal_outcome",
            )
        )
        if content and supplied is not None:
            known += 1
            cases.append(render_attempt(supplied, translator=translator, sample=sample))
            all_inputs.append(supplied)
        else:
            missing = True
            cases.append(f"<p>{t(translator, 'input_missing', identifier=identifier)}</p>")
            all_inputs.append(supplied if supplied is not None else {"record_id": identifier})
    complete = complete and not missing
    published_unit = value(record, "count_unit", "sample_unit")
    dedup = value(record, "deduplication", "dedup_rule")
    filters = value(record, "filters", "applied_filters")
    point = value(record, "observable_grouping_point", "observable_phenomenon")
    sample_note = (
        translator.html("plain.result.sample")
        if sample or record.get("fabricated_example") is True
        else ""
    )
    fields = (
        ("observable", owner(point) if point is not None else t(translator, "observable_unknown")),
        ("rule", owner(rule) if rule is not None else t(translator, "rule_unknown")),
        (
            "scope",
            " · ".join(owner(item) for item in scope) if scope else t(translator, "scope_unknown"),
        ),
        (
            "published_count",
            owner(sample_count) if sample_count is not None else t(translator, "count_unknown"),
        ),
        (
            "count_unit",
            owner(published_unit) if published_unit is not None else t(translator, "unit_unknown"),
        ),
        ("dedup", owner(dedup) if dedup is not None else t(translator, "dedup_unknown")),
        ("filters", owner(filters) if filters is not None else t(translator, "filters_unknown")),
    )
    rows = "".join(
        f"<div><dt>{t(translator, key)}</dt><dd>{content}</dd></div>" for key, content in fields
    )
    computation = source_support_computation(
        tuple(all_inputs),
        filters=query_context,
        complete=complete,
        description=translator.t("plain.memory.input_count_rule"),
    )
    support = (
        source_support_entry(
            str(value(record, "source_ref", "source_id", "group_id", "pattern_id") or ""),
            record=record,
        )
        or ""
    )
    return (
        '<section class="plain-memory-group">'
        f"<h3>{owner(title) if title is not None else t(translator, 'group_title')}</h3>"
        f'<p class="sample-note">{sample_note}</p>{source_support_impact(record)}'
        f"<p>{t(translator, 'similar_not_cause')}</p><dl>{rows}</dl>"
        f"<p>{t(translator, 'identified', n=known)}</p>"
        f"<p>{translator.html('support.count_complete' if complete else 'support.count_partial')}</p>"
        f"<p>{t(translator, 'input_count_rule')}</p><p>{computation}</p>"
        f"<h4>{t(translator, 'cases')}</h4>{''.join(cases)}<p>{support}</p></section>"
    )


def _selection(record: Mapping[str, object], translator: Translator) -> str:
    if record.get("selection_measure") != "daily_stock_price_change":
        return ""
    content = (
        f'<p class="plain-definition"><strong>{t(translator, "change_question")}</strong> '
        f"{t(translator, 'change_definition')}</p>"
    )
    if record.get("selection_direction") == "smaller":
        content += f"<p>{t(translator, 'smaller')}</p>"
        threshold = value(record, "selection_threshold")
        content += f"<p>{owner(threshold) if threshold is not None else t(translator, 'threshold_unknown')}</p>"
    return content


def render_attempt(
    record: Mapping[str, object],
    *,
    translator: Translator,
    lesson: bool = False,
    sample: bool = False,
) -> str:
    title = value(record, "title", "label", "name", "heading")
    execution = value(record, "execution_status", "test_status", "status", "state")
    token = str(execution or "").lower().replace("-", "_")
    goal = str(value(record, "goal_outcome", "target_outcome") or "").lower().replace("-", "_")
    state = "unknown"
    if token in {"not_tested", "not_run", "not_started", "not_evaluated"}:
        state = "not_tested"
    elif token in {"stopped", "aborted", "cancelled", "interrupted"}:
        state = "stopped"
    elif token in {"completed", "finished"}:
        state = (
            "missed"
            if goal in {"not_met", "missed"}
            else "met"
            if goal == "met"
            else "ended_unknown"
        )
    financial, calculated_goal = _financial_result(record, translator, token)
    if calculated_goal and state == "ended_unknown":
        state = "calculated_met" if calculated_goal == "met" else "missed"
    if not source_support_usable(record):
        state = "unknown"
    reason = value(record, "failure_reason", "stop_reason", "reason")
    summary = value(
        record, "lesson", "safe_summary", "summary", "description", "detail", "message", "text"
    )
    source = value(record, "source_ref", "source_id")
    identifier = value(record, "memory_id", "failure_id", "record_id", "id")
    support = source_support_entry(str(source or identifier or ""), record=record) or ""
    target = value(record, "original_target", "target_before_test")
    actual = value(record, "actual_result", "result_summary")
    follow_up = value(record, "follow_up", "retest", "retry")
    limits = value(record, "limitations", "limitation", "bounds", "conditions")
    author = value(record, "author")
    report_summary = value(record, "memory_type", "record_type") in {
        "report_summary",
        "report_ending_summary",
    }
    nature = t(
        translator,
        "report_summary" if report_summary else "independent_lesson" if lesson else "attempt",
    )
    report_boundary = (
        f"<p>{t(translator, 'same_report')}</p>"
        f'<p class="plain-definition"><strong>{translator.html("plain.result.report_question")}</strong> '
        f"{translator.html('plain.result.report_definition')}</p>"
        if report_summary
        else ""
    )
    origin = value(
        record,
        "attempt_id",
        "run_id",
        "report_id",
        "original_source_id",
        "where_produced",
        "origin",
        "produced_by",
        "lineage",
    )
    sample_markup = (
        f'<p class="sample-note">{translator.html("plain.result.sample")}</p>'
        if sample or record.get("fabricated_example") is True
        else ""
    )
    return (
        '<section class="plain-memory-record">'
        f"{sample_markup}<p>{nature}</p>{report_boundary}"
        f"<h3>{owner(title) if title is not None else t(translator, 'untitled')}</h3>"
        f"{source_support_impact(record)}<p>{t(translator, 'state.' + state)}</p>"
        f"<p>{owner(summary) if summary is not None else t(translator, 'text_unknown')}</p>"
        f"<h4>{t(translator, 'reason')}</h4>"
        f"<p>{owner(reason) if reason is not None else t(translator, 'reason_unknown')}</p>"
        f'<p class="plain-definition"><strong>{translator.html("plain.result.target_question")}</strong> '
        f"{translator.html('plain.result.target_definition')}</p>"
        f"<h4>{t(translator, 'target')}</h4><p>{owner(target) if target is not None else t(translator, 'target_unknown') if record.get('target_profit_at_least') is None else ''}</p>"
        f"<h4>{t(translator, 'actual')}</h4><p>{owner(actual) if actual is not None else ''}</p>"
        f"<p>{financial}</p>{_fields(record, translator)}"
        f'<p class="plain-definition"><strong>{translator.html("plain.result.cost_question")}</strong> '
        f"{translator.html('plain.result.cost_definition')}</p>"
        f"<h4>{translator.html('plain.result.follow_up_title')}</h4>"
        f"<p>{owner(follow_up) if follow_up is not None else translator.html('plain.result.follow_up_missing')}</p>"
        f"<h4>{translator.html('plain.result.limitations_title')}</h4>"
        f"<p>{owner(limits) if limits is not None else t(translator, 'limits_unknown')}</p>"
        f"<h4>{t(translator, 'origin')}</h4>"
        f"<p>{owner(origin) if origin is not None else t(translator, 'origin_unknown')}</p>"
        f"{_selection(record, translator)}<p>{t(translator, 'bounded')}</p>"
        f"<p>{owner(author) if author is not None else translator.html('plain.result.author_unknown')}</p>"
        f"<p>{support}</p></section>"
    )
