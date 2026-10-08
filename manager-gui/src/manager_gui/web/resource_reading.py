from __future__ import annotations

from html import escape

from ..models import ManagerReadModel, ReadModelStatus
from .i18n import Translator
from .status import render_status_block

RESOURCES = frozenset(
    {
        "genomes",
        "genome_conditions",
        "genome_comparison",
        "memory",
        "failure_patterns",
        "failure_grouping",
        "evidence_comparison",
        "methodology",
    }
)


def render_resource_reading(
    model: ManagerReadModel,
    *,
    resource: str,
    title: str,
    page: str,
    translator: Translator,
) -> str:
    if model.availability.status is not ReadModelStatus.API_UNAVAILABLE:
        return page
    notice = (
        f'<section data-resource-reading="{resource}" '
        f'data-status="{model.availability.status.value}" role="note">'
        f'<p>{translator.html("resource_reading.cannot_list")}</p></section>'
    )
    if model.data:
        return notice + page
    return (
        f'<section class="resource-reading-page"><h1>{escape(title)}</h1>{notice}'
        f'{render_status_block(model, translator=translator)}'
        f'<details><summary>{translator.html("reader.raw_source")}</summary>'
        f'<pre translate="no">{escape(model.to_json(indent=2))}</pre></details></section>'
    )
