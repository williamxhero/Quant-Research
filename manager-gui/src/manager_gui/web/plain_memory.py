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
        elif key == "currency" and isinstance(supplied, str) and supplied in {"CNY", "USD", "EUR"}:
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
        or not source_support_usable(record, require_complete=True)
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
    return result + " " + translator.html(
        "plain.result.calculation"
    ), "met" if profit >= target else "missed"


_INPUT_IDS = ("record_id", "recordId", "participant_id", "id", "run_id", "failure_id", "memory_id")


def _input_content(record: Mapping[str, object]) -> bool:
    return any(
        value(record, key) is not None
        for key in (
            "safe_summary",
            "summary",
            "text",
            "description",
            "reason",
            "failure_reason",
            "stop_reason",
            "actual_result",
            "execution_status",
            "status",
            "outcome",
            "goal_outcome",
        )
    )


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
    candidates: tuple[Mapping[str, object], ...] = (),
) -> str:
    """Explain the supplied grouping, without recomputing its published outcome."""
    title = value(record, "title", "label", "name")
    inline = value(record, "participants", "members", "records", "failures", "inputs")
    extra_inputs: list[tuple[str, Mapping[str, object]]] = []
    if isinstance(inline, (list, tuple)):
        inline_records = tuple(item for item in inline if isinstance(item, Mapping))
        candidates += inline_records
        named = {identifier for identifier, _ in inputs}
        for item in inline_records:
            identity = value(item, *_INPUT_IDS)
            identifier = identity if isinstance(identity, str) else ""
            if not identifier or identifier not in named:
                extra_inputs.append((identifier, item))
                named.add(identifier)
    membership_gap = bool(inputs and extra_inputs)
    inputs += tuple(extra_inputs)
    cases = [f"<p>{t(translator, 'membership_gap')}</p>"] if membership_gap else []
    missing = membership_gap
    all_inputs = []
    known_ids: set[str] = set()
    for identifier, supplied in inputs:
        matches: list[Mapping[str, object]] = []
        for item in candidates:
            if (
                identifier in (item.get(key) for key in _INPUT_IDS)
                and _input_content(item)
                and item not in matches
            ):
                matches.append(item)
        if supplied is None or not _input_content(supplied):
            # An explicit reference can use a uniquely supplied record, never an arbitrary sibling.
            supplied = matches[0] if len(matches) == 1 else supplied
        if len(matches) > 1:
            missing = True
            cases.append(f"<p>{t(translator, 'input_conflict')}</p>")
            for contender in matches:
                if contender != supplied:
                    cases.append(render_attempt(contender, translator=translator, sample=sample))
                    all_inputs.append(contender)
        content = supplied is not None and _input_content(supplied)
        if content and supplied is not None:
            missing = missing or not source_support_usable(supplied, require_complete=True)
            explicit_id = value(
                supplied,
                "record_id",
                "recordId",
                "participant_id",
                "id",
                "run_id",
                "failure_id",
                "memory_id",
            )
            if isinstance(explicit_id, str) and explicit_id.strip():
                known_ids.add(explicit_id)
            else:
                missing = True
                cases.append(f"<p>{t(translator, 'identity_unknown')}</p>")
            cases.append(render_attempt(supplied, translator=translator, sample=sample))
            all_inputs.append(supplied)
        else:
            missing = True
            cases.append(
                f"<p>{t(translator, 'input_missing', identifier='').rstrip()}{owner(identifier)}</p>"
            )
            all_inputs.append(supplied if supplied is not None else {"record_id": identifier})
    published_unit = value(record, "count_unit", "sample_unit")
    dedup = value(record, "deduplication", "dedup_rule")
    filters = value(record, "filters", "applied_filters")
    group_status = value(record, "status", "state")
    unreadable_group = isinstance(group_status, str) and group_status in {
        "blocked",
        "stale",
        "integrity_failure",
        "api_unavailable",
        "missing",
        "incomparable",
    }
    group_impact = (
        translator.html("support.impact." + group_status)
        if unreadable_group and isinstance(group_status, str)
        else ""
    )
    count_mismatch = (
        published_unit == "records" and sample_count is not None and sample_count != len(known_ids)
    )
    count_gap = t(translator, "count_mismatch") if count_mismatch else ""
    complete = bool(
        complete
        and not missing
        and not unreadable_group
        and not count_mismatch
        and inputs
        and rule
        and scope
        and sample_count is not None
        and published_unit is not None
        and dedup is not None
        and filters is not None
        and source_support_usable(record, require_complete=True)
    )
    point = value(record, "observable_grouping_point", "observable_phenomenon")
    aggregation = value(record, "aggregation", "derivation", "pattern_aggregation")
    metadata = aggregation if isinstance(aggregation, Mapping) else {}
    raw_rule = value(
        record, "rule", "grouping_rule", "aggregation_rule", "derivation_rule", "pattern_rule"
    )
    if raw_rule is None:
        raw_rule = value(
            metadata, "rule", "grouping_rule", "aggregation_rule", "derivation_rule", "pattern_rule"
        )
    raw_scope = value(record, "input_scope", "scope", "source_scope")
    if raw_scope is None:
        raw_scope = value(metadata, "input_scope", "scope", "source_scope")
    rule_content = (
        owner(raw_rule)
        if raw_rule is not None
        else owner(rule)
        if rule is not None
        else t(translator, "rule_unknown")
    )
    scope_content = (
        " · ".join(owner(item) for item in raw_scope)
        if isinstance(raw_scope, (list, tuple))
        else owner(raw_scope)
        if raw_scope is not None
        else " · ".join(owner(item) for item in scope)
        if scope
        else t(translator, "scope_unknown")
    )
    sample_note = (
        translator.html("plain.result.sample")
        if sample or record.get("fabricated_example") is True
        else ""
    )
    fields = (
        ("observable", owner(point) if point is not None else t(translator, "observable_unknown")),
        ("rule", rule_content),
        ("scope", scope_content),
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
        f'<p class="sample-note">{sample_note}</p>{source_support_impact(record, require_original=True)}<p>{group_impact}</p>'
        f"<p>{t(translator, 'similar_not_cause')}</p><dl>{rows}</dl>"
        f"<p>{t(translator, 'identified', n=len(known_ids))}</p><p>{count_gap}</p>"
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


def _disagree(record: Mapping[str, object], *keys: str) -> bool:
    meanings = {
        "completed": "ended",
        "finished": "ended",
        "stopped": "stopped",
        "aborted": "stopped",
        "cancelled": "stopped",
        "interrupted": "stopped",
        "not_tested": "not_run",
        "not_run": "not_run",
        "not_started": "not_run",
        "not_evaluated": "not_run",
        "met": "met",
        "not_met": "missed",
        "missed": "missed",
    }
    tokens = {
        meanings[normalised]
        for key in keys
        if isinstance(raw := record.get(key), str)
        if (normalised := raw.lower().replace("-", "_")) in meanings
    }
    return len(tokens) > 1


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
    fields_disagree = _disagree(
        record, "execution_status", "test_status", "status", "state"
    ) or _disagree(record, "goal_outcome", "target_outcome")
    financial, calculated_goal = _financial_result(
        record, translator, "" if fields_disagree else token
    )
    if calculated_goal and state in {"met", "missed"} and calculated_goal != state:
        state = "conflicting"
    outcome = str(value(record, "outcome", "result", "status") or "").lower().replace("-", "_")
    failed_marker = outcome in {"failed", "failure", "error", "execution_error"}
    goal_gap = t(translator, "goal_fields_gap") if failed_marker else ""
    if failed_marker and state == "met":
        state = "ended_unknown"
    if calculated_goal and state == "ended_unknown" and not goal and not failed_marker:
        state = "calculated_met" if calculated_goal == "met" else "missed"
    if fields_disagree:
        state = "fields_conflict"
    if not source_support_usable(record, require_complete=True):
        state = "unknown"
    reason = value(record, "failure_reason", "stop_reason", "reason")
    summary = value(
        record, "lesson", "safe_summary", "summary", "description", "detail", "message", "text"
    )
    source = value(record, "source_ref", "source_id")
    identifier = value(record, "memory_id", "failure_id", "record_id", "id")
    target = value(record, "original_target", "target_before_test")
    actual = value(record, "actual_result", "result_summary")
    follow_up = value(record, "follow_up", "retest", "retry")
    limits = value(record, "limitations", "limitation", "bounds", "conditions")
    author = value(record, "author")
    record_kind = value(record, "memory_type", "record_type")
    report_summary = isinstance(record_kind, str) and record_kind in {
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
    explanation = (
        '<section class="plain-memory-record">'
        f"{sample_markup}<p>{nature}</p>{report_boundary}"
        f"<h3>{owner(title) if title is not None else t(translator, 'untitled')}</h3>"
        f"{source_support_impact(record, require_original=True)}<p>{t(translator, 'state.' + state)}</p><p>{goal_gap}</p>"
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
        "</section>"
    )
    support = (
        source_support_entry(
            str(source or identifier or ""),
            record=record,
            explanation=explanation,
        )
        or ""
    )
    return explanation + f"<p>{support}</p>"
