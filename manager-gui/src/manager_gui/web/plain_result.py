from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, localcontext
from html import escape

from ..models import ManagerReadModel, ReadModelStatus
from .evidence import EvidenceViewModel
from .i18n import Translator
from .locators import public_locator
from .navigation import context_link, query_values
from .research_story import ResearchStoryViewModel

_FIELDS = (
    "starting_amount",
    "ending_amount",
    "currency",
    "costs_included",
    "target_profit_at_least",
    "target_costs_included",
    "period",
)
_UNITS = {"CNY", "USD", "EUR"}


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _number(value: object) -> Decimal | None:
    if type(value) not in {int, float}:
        return None
    number = Decimal(str(value))
    return number if number.is_finite() else None


def _format(number: Decimal) -> str:
    value = format(number, "f")
    return value.rstrip("0").rstrip(".") if "." in value else value


def _records(model: ManagerReadModel, view: str) -> tuple[Mapping[str, object], ...]:
    if view == "stories":
        entries = ResearchStoryViewModel.from_read_model(model).entries
        return tuple(
            entry.raw
            for entry in entries
            if entry.chapter_key == "conclusions"
            and entry.raw is not None
            and entry.raw.get("record_type") == "test_report"
        )
    return tuple(
        record.raw
        for record in EvidenceViewModel.from_read_model(model).records
        if record.raw.get("record_type") == "test_report"
    )


def render_plain_result(
    model: ManagerReadModel,
    *,
    view: str,
    query_context: str,
    translator: Translator,
    sample: bool,
) -> str | None:
    records = _records(model, view)
    query = query_values(query_context)
    record_id = query.get("record_id")
    source_id = query.get("source_id")
    selected = tuple(
        record
        for record in records
        if (record_id is None or record.get("record_id") == record_id)
        and (source_id is None or record.get("source_ref") == source_id)
    )
    if not records and not (view == "evidence" and record_id and source_id):
        return None
    requested_snapshot = query.get("snapshot_token") or query.get("snapshot")
    if requested_snapshot and model.snapshot_token != requested_snapshot:
        body = f"<p>{escape(translator.t('plain.result.snapshot_drift'))}</p>"
    elif not selected:
        body = f"<p>{escape(translator.t('plain.result.not_found'))}</p>"
    else:
        body = "".join(
            _render_record(record, model, query_context, translator, sample, view)
            for record in selected
        )
    key = "plain.result.title" if view == "stories" else "plain.result.evidence_title"
    hook = "research-story-view" if view == "stories" else "evidence-ledger-view"
    return (
        f'<section class="plain-result" data-integration-hook="{hook}" '
        f'aria-labelledby="plain-result-title"><h1 id="plain-result-title" tabindex="-1">'
        f"{escape(translator.t(key))}</h1><p>{escape(translator.t('plain.result.test'))}</p>"
        f"{body}</section>"
    )


def _render_record(
    record: Mapping[str, object],
    model: ManagerReadModel,
    query_context: str,
    translator: Translator,
    sample: bool,
    view: str,
) -> str:
    def t(key: str, **params: object) -> str:
        return escape(translator.t("plain.result." + key, **params))

    source = next(
        (ref for ref in model.source_refs if ref.source_id == record.get("source_ref")),
        None,
    )
    title = _text(record.get("title")) or _text(record.get("label"))
    title_markup = (
        f'<span data-owner-text="true">{escape(title)}</span>' if title else t("untitled")
    )
    definitions = "".join(
        f'<p class="plain-definition"><strong>{t(name + "_question")}</strong>'
        f"{t(name + '_definition')}</p>"
        for name in ("report", "cost", "target")
    )
    start = _number(record.get("starting_amount"))
    end = _number(record.get("ending_amount"))
    target = _number(record.get("target_profit_at_least"))
    currency = _text(record.get("currency"))
    unit = (
        translator.t("plain.result.unit." + currency)
        if currency is not None and currency in _UNITS
        else None
    )
    costs = record.get("costs_included")
    usable = (
        model.availability.status is ReadModelStatus.KNOWN
        and not model.errors
        and source is not None
        and public_locator(source.locator) is not None
    )
    result = t("amount_unknown")
    if not usable:
        result = t("unavailable")
    elif start is not None and end is not None and unit is not None and type(costs) is bool:
        cost = translator.t("plain.result.cost_included" if costs else "plain.result.cost_excluded")
        with localcontext() as arithmetic:
            arithmetic.prec = max(len(format(start, "f")), len(format(end, "f"))) + 2
            profit = end - start
        short_unit = translator.t("plain.result.short.CNY") if currency == "CNY" else unit
        result = t(
            "amount",
            start=_format(start),
            end=_format(end),
            starting_unit=unit,
            unit=short_unit,
            cost=cost,
        )
        result += " " + (
            t("profit" if profit > 0 else "loss", amount=_format(profit.copy_abs()), unit=unit)
            if profit
            else t("flat")
        )
        target_costs = record.get("target_costs_included")
        if target is None:
            result += " " + t("target_unknown")
        elif type(target_costs) is not bool:
            result += " " + t("target_cost_unknown")
        elif target_costs != costs:
            result += " " + t("target_cost_mismatch")
        else:
            result += " " + t(
                "target_met" if profit >= target else "target_missed",
                target=_format(target),
                unit=short_unit,
            )
    period = _text(record.get("period"))
    period_markup = t("period", period=period) if period else t("period_unknown")
    summary = _text(record.get("summary"))
    summary_markup = (
        f'<p data-owner-text="true">{escape(summary)}</p>'
        if summary
        else f"<p>{t('text_unknown')}</p>"
    )
    author = _text(record.get("author"))
    author_markup = t("author", author=author) if author else t("author_unknown")
    rows = []
    for field in _FIELDS:
        value = record.get(field)
        number = _number(value)
        display_value: str | None
        if field in {"costs_included", "target_costs_included"} and type(value) is bool:
            display_value = translator.t(
                "plain.result.cost_included" if value else "plain.result.cost_excluded"
            )
        elif field == "currency" and unit is not None:
            display_value = unit
        elif number is not None:
            display_value = _format(number)
        else:
            display_value = _text(value)
        rows.append(
            f"<div><dt>{t('field.' + field)}</dt>"
            f"<dd>{escape(display_value) if display_value else t('missing')}</dd></div>"
        )
    fields = f"<h3>{t('fields')}</h3><p>{t('calculation')}</p><dl>{''.join(rows)}</dl>"
    link = ""
    if summary is None and start is None and end is None:
        link = f"<p>{t('no_content')}</p>"
    elif source is None:
        link = f"<p>{t('source_missing')}</p>"
    elif public_locator(source.locator) is None:
        link = f"<p>{t('unsafe')}</p>"
    elif view == "stories" and _text(record.get("record_id")):
        target_url = context_link(
            query_context,
            view="evidence",
            record_id=record["record_id"],
            source_id=source.source_id,
            snapshot_token=model.snapshot_token,
        )
        link_key = "open" if start is not None or end is not None else "open_record"
        link = f'<p><a href="{escape(target_url, quote=True)}">{t(link_key)}</a></p>'
    sample_markup = f'<p class="sample-note">{t("sample")}</p>' if sample else ""
    if not model.availability.complete:
        sample_markup += f"<p>{t('partial')}</p>"
    return (
        f"<article>{sample_markup}<h2>{title_markup}</h2>{definitions}"
        f'<p class="plain-outcome">{result}</p><p>{period_markup}</p><p>{t("limits")}</p>'
        f"<h3>{t('source_text')}</h3>{summary_markup}<p>{author_markup}</p>"
        f"{fields}<p>{t('no_full_report')}</p>{link}</article>"
    )
