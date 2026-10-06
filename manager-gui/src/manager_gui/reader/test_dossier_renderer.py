"""Focused tests for the deterministic offline Dossier v2 HTML renderer."""

from __future__ import annotations

import copy
from dataclasses import replace

from manager_gui.reader.dossier import DossierReportBuilder
from manager_gui.reader.dossier_renderer import (
    DOSSIER_BANNER_TEXT,
    DossierHTMLRenderer,
    inspect_dossier_html,
    validate_chart_palette,
    verify_dossier_html,
)

from .test_dossier import Provider, _fixture


def _model():
    records, refs = _fixture()
    return DossierReportBuilder(Provider(records)).build(refs)


def test_render_is_deterministic_self_contained_and_accessible() -> None:
    model = _model()
    renderer = DossierHTMLRenderer()
    first = renderer.render(model)
    second = renderer.render(model.to_json())
    inspection = inspect_dossier_html(first)

    assert first == second
    assert inspection.passed
    assert inspection.self_contained
    assert inspection.has_boundary_banner
    assert DOSSIER_BANNER_TEXT in first
    assert inspection.has_accessible_table
    assert inspection.fact_count > 0
    assert "https://" not in first
    assert "cdn" not in first.lower()
    assert verify_dossier_html(first, model).passed


def test_report_model_is_the_only_source_and_hostile_text_is_escaped() -> None:
    model_data = copy.deepcopy(_model().to_dict())
    model_data["title"] = '<img src=x onerror="alert(1)">'  # type: ignore[index]
    model = type(_model()).from_dict(model_data)
    output = DossierHTMLRenderer().render(model)

    assert '<img src=x' not in output
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in output
    assert "workspace-artifact://" not in output or "data-tooltip" in output


def test_boundary_banner_remains_persistent_when_model_banner_is_custom() -> None:
    model = replace(_model(), banner="owner supplied boundary text")

    output = DossierHTMLRenderer().render(model)

    assert f'<span>{DOSSIER_BANNER_TEXT}</span>' in output
    assert 'class="boundary-detail">模型声明：owner supplied boundary text</span>' in output


def test_chart_geometry_stays_inside_viewbox_and_theme_uses_selected_palette() -> None:
    output = DossierHTMLRenderer().render(_model())

    assert 'width="100.000%"' not in output
    assert 'fill="var(--chart-' in output
    assert "--chart-0:#2a78d6" in output
    assert "--chart-0:#3987e5" in output
    assert "window.matchMedia('(prefers-color-scheme: dark)')" in output
    assert 'aria-describedby="tooltip"' in output
    assert "event.currentTarget.getBoundingClientRect()" in output


def test_palette_validation_covers_both_selected_themes() -> None:
    result = validate_chart_palette()

    assert result
    assert result.passed
    assert result.light_contrast > 1.5
    assert result.dark_contrast > 3.0
