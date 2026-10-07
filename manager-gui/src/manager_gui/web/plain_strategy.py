"""Plain reading of already supplied public records; no new owner facts or reads."""

# HTML fragments keep readable markup at the call site, like the existing readers.
# ruff: noqa: E501
from __future__ import annotations

import json
from collections.abc import Mapping
from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .comparison_reader import ComparisonReaderComparison

from ..models import ManagerReadModel
from .genome import GenomeFilters, GenomeViewModel
from .i18n import Translator
from .navigation import query_values
from .source_support import source_support_entry, source_support_impact, source_support_usable

CONDITION_COLLECTION_KEYS = (
    "conditions",
    "condition_evidence",
    "applicability_conditions",
    "invalidation_conditions",
    "failure_conditions",
    "counterexamples",
    "descriptors",
)
REVISION_COLLECTION_KEYS = (
    "revisions",
    "strategy_revisions",
    "evolution",
    "revision_tree",
    "history",
)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _wording(record: Mapping[str, object], *keys: str) -> str | None:
    return next((text for key in keys if (text := _text(record.get(key))) is not None), None)


def _owner(value: object) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return f'<span data-owner-text="true" translate="no">{escape(text)}</span>'


def _t(translator: Translator, key: str, **params: object) -> str:
    return escape(translator.t("plain.strategy." + key, **params))


def _support(record: Mapping[str, object], model: ManagerReadModel) -> str:
    # Supply the actual adjacent record, including nested rule/axis content.
    # Never ask container traversal to guess a side from a shared source pointer.
    source = _wording(record, "source_ref", "source_id")
    if source is None and len(model.source_refs) == 1:
        source = model.source_refs[0].source_id
    return source_support_entry(source or "", record=record) or ""


def _pointers(model: ManagerReadModel) -> str:
    return "".join(source_support_entry(ref.source_id) or "" for ref in model.source_refs)


def _rule(value: object, key: str, translator: Translator) -> str:
    if value in (None, "", {}, []):
        return _t(translator, "missing")
    record = _mapping(value)
    wording = _wording(record, "description", "text", "summary")
    if wording is not None:
        return _owner(wording)
    rule = record.get("rule")
    if key == "entry" and rule == "signal_positive":
        return _t(translator, "positive")
    if key == "exit" and rule == "signal_negative":
        return _t(translator, "negative")
    if key == "universe" and (scope := _text(record.get("scope"))) is not None:
        return _t(translator, "selection_scope", scope=scope).replace(
            escape(scope), _owner(scope), 1
        )
    drawdown = record.get("max_drawdown")
    if (
        key == "risk_controls"
        and isinstance(drawdown, (int, float))
        and not isinstance(drawdown, bool)
        and 0 <= drawdown <= 1
    ):
        return _t(translator, "drawdown", percent=f"{drawdown * 100:g}")
    lag = record.get("decision_lag_bars")
    if key == "timing" and type(lag) is int and lag >= 0:
        return _t(translator, "decision_delay", n=lag)
    commission = record.get("commission_bps")
    if (
        key == "costs"
        and isinstance(commission, (int, float))
        and not isinstance(commission, bool)
        and commission >= 0
    ):
        return _t(translator, "commission", n=commission)
    return _t(translator, "unexplained")


def render_plain_strategy(
    model: ManagerReadModel,
    *,
    query_context: str,
    translator: Translator,
) -> str:
    catalog = GenomeViewModel.from_read_model(
        model, filters=GenomeFilters.from_query(query_context)
    ).catalog
    selected_id = query_values(query_context).get("genome_id")
    selected = tuple(
        record for record in catalog if selected_id is None or record.genome_id == selected_id
    )
    if not selected:
        body = f"<p>{_t(translator, 'not_found')}</p>{source_support_impact()}{_pointers(model)}"
    else:
        body = "".join(
            _strategy(record.raw, record.behavior, model, translator) for record in selected
        )
    return f'<section class="plain-result plain-strategy">{body}</section>'


def _strategy(
    record: Mapping[str, object],
    behavior: Mapping[str, object],
    model: ManagerReadModel,
    translator: Translator,
    *,
    display_name: str | None = None,
) -> str:
    title = display_name or _wording(record, "title", "name", "label")
    heading = _owner(title) if title else _t(translator, "unnamed")
    content = f"<h2>{heading}</h2>"
    if record.get("fabricated_example") is True:
        content += f'<p class="sample-note">{escape(translator.t("plain.result.sample"))}</p>'
    content += source_support_impact(record)
    usable = source_support_usable(record)
    wording = _wording(record, "strategy_summary", "description", "summary", "behavior_summary")
    if wording:
        content += f"<p>{_owner(wording)}</p>"
    timing = _mapping(behavior.get("timing"))
    execution = {key: timing.get(key) for key in ("execution_time", "execution_price")}
    execution_complete = all(value not in (None, "", [], {}) for value in execution.values())
    execution_usable = usable and source_support_usable(timing)
    main_conditions = (
        execution_complete
        and execution_usable
        and all(
            source_support_usable(_mapping(behavior.get(key)))
            for key in ("universe", "entry", "exit", "risk_controls", "timing")
        )
        and all(
            _wording(_mapping(behavior.get(key)), "description", "text", "summary")
            for key in ("universe", "entry", "exit", "risk_controls", "timing")
        )
    )
    kind = _wording(record, "record_type", "type", "kind")
    classification = (
        "factor"
        if kind in ("factor", "stock_factor")
        else "main_conditions"
        if main_conditions and usable
        else "incomplete"
    )
    content += f"<p>{_t(translator, classification)}</p>"
    content += f'<p class="plain-definition"><strong>{_t(translator, "signal_question")}</strong>{_t(translator, "signal_definition")}</p>'
    daily = (
        record.get("fabricated_example") is True
        and all(
            source_support_usable(_mapping(behavior.get(key)))
            for key in ("entry", "exit", "timing")
        )
        and _mapping(behavior.get("entry")).get("rule")
        == "daily_close_crosses_above_20_trading_day_mean"
        and _mapping(behavior.get("exit")).get("rule")
        == "daily_close_crosses_below_20_trading_day_mean"
        and _mapping(behavior.get("timing")).get("evaluation") == "each_trading_day_close"
    )
    for key in ("universe", "entry", "exit", "risk_controls", "timing"):
        value = behavior.get(key)
        value_record = _mapping(value)
        value_usable = usable and source_support_usable(value_record)
        explanation = (
            _rule(value, key, translator) if value_usable else _t(translator, "unexplained")
        )
        if (
            value_usable
            and key == "universe"
            and _mapping(value).get("selection_goal") == "smaller_daily_stock_price_changes"
        ):
            explanation = _t(translator, "daily_movement")
            threshold = _mapping(value).get("threshold")
            explanation += " " + (
                _t(translator, "threshold_unknown")
                if threshold is None
                else _t(translator, "threshold") + ": " + _owner(threshold)
            )
        if value_usable and daily and key in ("entry", "exit", "timing"):
            explanation = _t(translator, "daily_" + key)
        supplied = {**record, "behavior": {key: value}} if key in behavior else record
        content += (
            f"<section><h3>{_t(translator, key)}</h3>{source_support_impact(value_record)}"
            f"<p>{explanation}</p>{_support(supplied, model)}</section>"
        )
    if daily and usable:
        for key in ("day", "mean"):
            content += f'<p class="plain-definition"><strong>{_t(translator, key + "_question")}</strong>{_t(translator, key + "_definition")}</p>'
        content += f"<p>{_t(translator, 'fake_amounts')}</p>"
    if execution_complete and execution_usable:
        content += _fields(execution, {key: (key,) for key in execution}, translator)
    else:
        has_details = any(value not in (None, "", [], {}) for value in execution.values())
        gap = "execution_partial" if has_details else "execution_unknown"
        content += f"<p>{_t(translator, gap)}</p>"
        if has_details:
            content += _fields(execution, {key: (key,) for key in execution}, translator)
    content += f'<p class="plain-definition"><strong>{escape(translator.t("plain.result.cost_question"))}</strong>{escape(translator.t("plain.result.cost_definition"))}</p>'
    for key, value in (
        ("period", record.get("test_period")),
        ("market", record.get("tested_market")),
        ("currency", record.get("currency")),
        ("costs", behavior.get("costs")),
    ):
        rendered = (
            (_rule(value, key, translator) if key == "costs" else _owner(value))
            if value not in (None, "", [], {})
            and usable
            and (key != "costs" or source_support_usable(_mapping(value)))
            else _t(translator, key + "_unknown")
        )
        content += (
            f"<h3>{_t(translator, key)}</h3>{source_support_impact(_mapping(value))}"
            f"<p>{rendered}</p>"
        )
        if key == "costs" and value:
            content += f"<p>{_t(translator, 'costs_boundary')}</p>"
    content += _conditions(record, model, translator)
    content += _revisions(record, model, translator)
    content += _support(record, model)
    return f"<article>{content}</article>"


def _items(value: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(item for item in value if isinstance(item, Mapping))
    return ()


def _fields(
    record: Mapping[str, object],
    fields: Mapping[str, tuple[str, ...]],
    translator: Translator,
    *,
    interpret_outcome: bool = True,
) -> str:
    rows = []
    for label, aliases in fields.items():
        value = next(
            (record[key] for key in aliases if record.get(key) not in (None, "", {}, [])), None
        )
        if (
            label == "outcome"
            and interpret_outcome
            and value in ("supported", "failed", "not_evaluated")
        ):
            rendered = _t(translator, str(value))
        else:
            rendered = _owner(value) if value is not None else _t(translator, "missing")
        caption = "descriptor_status" if label == "outcome" and not interpret_outcome else label
        rows.append(f"<div><dt>{_t(translator, caption)}</dt><dd>{rendered}</dd></div>")
    return "<dl>" + "".join(rows) + "</dl>"


def _conditions(
    record: Mapping[str, object], model: ManagerReadModel, translator: Translator
) -> str:
    content = f"<h3>{_t(translator, 'conditions')}</h3><p>{_t(translator, 'untested')}</p>"
    count = 0
    for collection in CONDITION_COLLECTION_KEYS:
        for item in _items(record.get(collection)):
            count += 1
            wording = _wording(
                item, "title", "description", "text", "condition", "statement", "descriptor", "name"
            )
            content += f"<section><h4>{_owner(wording) if wording else _t(translator, 'condition_unnamed')}</h4>"
            descriptor = collection == "descriptors" or item.get("category", item.get("kind")) in (
                "descriptor",
                "observation",
                "descriptive_observation",
            )
            if descriptor:
                content += f"<p>{_t(translator, 'descriptor')}</p>"
            content += source_support_impact(item)
            content += _fields(
                item,
                {
                    "outcome": ("outcome", "result", "status"),
                    "time": ("time", "time_range", "period"),
                    "scope": ("scope", "market", "universe"),
                    "evidence": ("evidence", "evidence_refs"),
                    "limitations": ("limitations", "limitations_note", "limits"),
                },
                translator,
                interpret_outcome=not descriptor and source_support_usable(item),
            )
            content += _support(item, model) + "</section>"
    if not count:
        content += f"<p>{_t(translator, 'conditions_unknown')}</p>"
    return content


def _revisions(
    record: Mapping[str, object], model: ManagerReadModel, translator: Translator
) -> str:
    content = f"<h3>{_t(translator, 'revisions')}</h3><p>{_t(translator, 'modification')}</p>"
    revisions = [record] if _wording(record, "revision_id", "revisionId", "revision") else []
    for key in REVISION_COLLECTION_KEYS:
        raw = record.get(key)
        revisions.extend(
            _items(raw.get("revisions"))
            if isinstance(raw, Mapping) and "revisions" in raw
            else _items(raw)
        )
    for item in revisions:
        content += source_support_impact(item)
        content += _fields(
            item,
            {
                "revision": ("revision_id", "revisionId", "revision", "id", "record_id"),
                "parent": (
                    "parent_revision",
                    "parent_revision_id",
                    "parentRevision",
                    "parent_id",
                    "parent",
                ),
                "changes": ("changes", "change_set", "diff"),
                "reason": ("reason", "owner_reason", "rationale"),
                "evidence": ("evidence", "evidence_refs"),
                "result": ("result", "outcome"),
                "limitations": ("limitations", "limits"),
            },
            translator,
        )
        content += _support(item, model)
    if not revisions:
        content += f"<p>{_t(translator, 'revisions_unknown')}</p>"
    return content


def _comparison_value(value: object, axis: str, translator: Translator) -> str:
    if value in (None, "", [], {}):
        return _t(translator, "missing")
    record = _mapping(value)
    if axis == "costs" and type(record.get("costs_included")) is bool:
        key = "cost_included" if record["costs_included"] else "cost_excluded"
        return (
            escape(translator.t("plain.result." + key))
            + " "
            + _rule(record, "costs", translator)
            + " "
            + _owner(record)
        )
    return _owner(value)


def render_plain_comparison(
    comparison: ComparisonReaderComparison | None,
    model: ManagerReadModel,
    *,
    translator: Translator,
) -> str:
    definition = _t(translator, "side_definition", left="A", right="B")
    for label in ("A", "B"):
        definition = definition.replace(label, f'<span translate="no">{label}</span>', 1)
    body = f"<p>{definition}</p><p>{_t(translator, 'no_winner')}</p>"
    body += source_support_impact()
    if comparison is None:
        body += f"<p>{_t(translator, 'no_comparison')}</p>{_pointers(model)}"
    else:
        sides = tuple(_mapping(comparison.raw.get(key)) for key in ("left", "right"))
        names = tuple(
            f"{label}: "
            + (
                _wording(side, "title", "name", "label")
                or translator.t("plain.strategy.unnamed_object")
            )
            for label, side in zip(("A", "B"), sides, strict=True)
        )
        for side, name in zip(sides, names, strict=True):
            if isinstance(side.get("behavior"), Mapping):
                body += _strategy(
                    side, _mapping(side["behavior"]), model, translator, display_name=name
                )
                continue
            body += f"<article><h2>{_owner(name)}</h2>"
            if side.get("fabricated_example") is True:
                body += f"<p>{escape(translator.t('plain.result.sample'))}</p>"
            wording = _wording(side, "description", "summary", "text")
            if wording:
                body += f"<p>{_owner(wording)}</p>"
            body += source_support_impact(side)
            if _wording(side, "revision_id", "revisionId", "revision"):
                body += _revisions(side, model, translator)
            body += _support(side, model) + "</article>"
        body += f'<p class="plain-definition"><strong>{escape(translator.t("plain.result.cost_question"))}</strong>{escape(translator.t("plain.result.cost_definition"))}</p>'
        for axis in comparison.axes:
            key = axis.axis.value
            body += f"<section><h3>{_t(translator, 'axis.' + key)}</h3>"
            usable = (
                model.availability.complete
                and all(source_support_usable(side) for side in sides)
                and source_support_usable(axis.raw)
                and all(
                    source_support_usable(_mapping(value))
                    for value in (axis.left_value, axis.right_value)
                )
            )
            if axis.raw:
                body += source_support_impact(axis.raw)
            body += (
                f"<p>{_t(translator, 'axis.' + (axis.state.value if usable else 'unverified'))}</p>"
            )
            if axis.owner_reason and axis.reason:
                body += f"<p>{_owner(axis.reason)}</p>"
            body += "<dl>"
            for side, name, value in zip(
                sides, names, (axis.left_value, axis.right_value), strict=True
            ):
                body += (
                    f"<div><dt>{_owner(name)}</dt><dd>{source_support_impact(_mapping(value))}"
                    f"{_comparison_value(value, key, translator)}</dd></div>"
                )
                # Keep explicit declarations or the actual side record as support,
                # not an arbitrary sibling discovered through a source pointer.
                support_record = axis.raw if axis.raw else side
                body += "<div><dd>" + _support(support_record, model) + "</dd></div>"
            body += "</dl></section>"
    return f'<section class="plain-result plain-comparison">{body}</section>'
