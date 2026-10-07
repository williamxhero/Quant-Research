from __future__ import annotations

import json
from collections.abc import Mapping
from html import escape

from .documents import _document_type
from .i18n import Translator

MATERIAL_RECORD_KINDS = {
    "test_report": "report",
    "report": "report",
    "test-report": "report",
    "plan": "plan",
    "test_plan": "plan",
    "strategy_rules": "rules",
    "strategy_description": "rules",
    "rules": "rules",
    "comparison": "comparison",
    "comparison_table": "comparison",
    "record": "record",
    "summary": "summary",
}


def render_material_details(record: Mapping[str, object], translator: Translator) -> str:
    def t(key: str) -> str:
        return escape(translator.t("material." + key))

    def value(*keys: str) -> str | None:
        for key in keys:
            candidate = record.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
        return None

    def owner(text: object) -> str:
        wording = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
        return f'<span data-owner-text="true" translate="no">{escape(wording)}</span>'

    kind = value("document_type", "record_type", "type", "kind", "category")
    document_type = _document_type(kind)
    category = (
        document_type.value if document_type is not None else MATERIAL_RECORD_KINDS.get(kind or "")
    )
    body = '<section class="material-reading">'
    if record.get("fabricated_example") is True:
        body += f'<p class="sample-note">{escape(translator.t("plain.result.sample"))}</p>'
    # Closed UI categories use the existing catalog; unknown owner wording stays raw.
    kind_markup = (
        escape(translator.label("documents.type", document_type.value))
        if document_type is not None
        else t(category) if category else owner(kind) if kind else t("category_unknown")
    )
    body += f"<p>{t('category')}: {kind_markup}</p>"
    if category == "report":
        body += (
            f'<p class="plain-definition"><strong>{t("report_question")}</strong>'
            f'{t("report_definition")}</p>'
        )
    if category in {
        "plan", "rules", "comparison", "summary", "design", "retrospective",
        "raw-evidence", "future-idea", "external-source",
    }:
        body += (
            f'<p class="plain-definition"><strong>{t(category + "_question")}</strong>'
            f'{t(category + "_definition")}</p>'
        )
    for label, keys, missing in (
        ("author", ("author",), "author_unknown"),
        (
            "date",
            ("date", "published_at", "publishedAt", "released_at", "created_at"),
            "date_unknown",
        ),
        ("scope", ("scope",), "scope_unknown"),
        ("period", ("period",), "period_unknown"),
        (
            "version",
            ("version", "revision", "document_version", "publication_version", "source_version",
             "source_revision"),
            "version_unknown",
        ),
    ):
        text = value(*keys)
        body += f"<p>{t(label)}: {owner(text) if text else t(missing)}</p>"
    summary = value("summary", "safe_summary", "description")
    if summary:
        body += f"<h3>{t('summary')}</h3><p>{owner(summary)}</p>"
    original = value("original_text", "text", "content")
    if original:
        body += (
            f'<h3>{t("original")}</h3><pre data-owner-text="true" translate="no">'
            f'{escape(original)}</pre>'
        )
        body += f"<p>{t('original_boundary')}</p>"
    elif not value("original_source_id"):
        body += f"<p>{t('summary_only' if summary else 'original_unknown')}</p>"
    members = record.get("members")
    if isinstance(members, (list, tuple)) and members:
        body += (
            f"<h3>{t('members')}</h3><ul>"
            + "".join(f"<li>{owner(member)}</li>" for member in members)
            + "</ul>"
        )
    if any(
        key in record
        for key in ("starting_amount", "ending_amount", "amount", "currency", "costs_included")
    ):
        currency = value("currency")
        units = {"CNY", "USD", "EUR"}
        unit = (
            escape(translator.t("material.unit." + currency))
            if currency in units
            else owner(currency)
            if currency
            else t("currency_unknown")
        )
        body += f"<p>{t('currency')}: {unit}</p>"
        costs = record.get("costs_included")
        cost = (
            escape(
                translator.t(
                    "plain.result.cost_included" if costs else "plain.result.cost_excluded"
                )
            )
            if type(costs) is bool
            else t("cost_unknown")
        )
        body += (
            f'<p class="plain-definition"><strong>{t("cost_question")}</strong>'
            f'{t("cost_definition")}</p><p>{cost}</p>'
        )
        for key in ("starting_amount", "ending_amount", "amount"):
            if key in record:
                body += f"<p>{t(key)}: {owner(record[key])} · {unit} · {cost}</p>"
    return body + "</section>"
