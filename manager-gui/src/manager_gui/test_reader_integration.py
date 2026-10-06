"""R1-T4 Reader contract integration and exit-gate tests."""

from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import parse_qsl, urlsplit

import pytest

from manager_gui import FixtureState
from manager_gui.models import MANAGER_READ_MODEL_SCHEMA
from manager_gui.reader import ClaimKind, ProjectionMode, project_read_model
from manager_gui.web import ManagerGUIApp
from manager_gui.web.i18n import Locale, Translator
from manager_gui.web.i18n.catalog import CATALOG
from manager_gui.web.i18n.catalog.reader import ENTRIES as READER_ENTRIES

ROUTES = (
    "atlas",
    "stories",
    "strategies",
    "strategy-conditions",
    "strategy-genome-comparison",
    "memory",
    "memory-failures",
    "failure-patterns",
    "evidence",
    "lineage",
    "evidence-object-comparison",
    "derived-failure-grouping",
    "methodology",
    "history",
    "source-documents",
    "search",
    "portal",
)


@pytest.mark.parametrize("locale", (Locale.ZH_CN, Locale.EN))
def test_reader_catalog_is_registered_once_in_the_default_bilingual_registry(
    locale: Locale,
) -> None:
    assert set(READER_ENTRIES) <= set(CATALOG)
    assert Translator(locale, strict=True).t("reader.page_question")
    assert Translator(locale, strict=True).t("reader.claim.missing")
    assert len(set(CATALOG)) == len(CATALOG)


def test_reader_shell_projection_is_a_public_ui_only_seam() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    projection = app.reader_projection("/?view=atlas&fixture=complete&mode=reader")

    assert projection.schema == "manager-gui.reader-projection.v1"
    assert projection.source_refs
    assert projection.availability.status.value == "known"
    assert projection.claims
    assert projection.limitations or projection.unknowns
    assert projection.sample_data is not None
    assert projection.mode_reference(ProjectionMode.EXPERT).schema == MANAGER_READ_MODEL_SCHEMA
    assert projection.mode_reference(ProjectionMode.RAW).sha256 == projection.raw_source.sha256


def test_reader_shell_projection_preserves_owner_boundary_without_sample_metadata() -> None:
    owner_model = ManagerGUIApp(default_fixture=FixtureState.COMPLETE).read_model(
        ManagerGUIApp(default_fixture=FixtureState.COMPLETE).request_state(
            "/?view=atlas&fixture=complete"
        )
    )

    class OwnerProvider:
        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            del resource, snapshot_token
            return owner_model

    app = ManagerGUIApp(OwnerProvider())
    projection = app.reader_projection("/?view=atlas&fixture=complete&mode=reader")
    assert projection.sample_data is None
    assert all(not ref.locator.startswith("fixture://") for ref in projection.source_refs) is False
    assert app.render("/?view=atlas&fixture=complete")
    assert 'data-sample-banner="fixture"' not in app.render("/?view=atlas&fixture=complete")


def test_reader_shell_contract_embeds_only_html_consumption_metadata_and_not_v0_api() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    url = (
        "/?view=atlas&fixture=complete&mode=raw&lang=en&scope=A0&root=r-1"
        "&filter=state%3Dknown&filter=owner%3Dfixture"
    )
    document = app.render(url)
    contract_match = re.search(
        r'<script id="reader-contract" type="application/json">(.*?)</script>',
        document,
        re.DOTALL,
    )
    assert contract_match is not None
    payload = json.loads(contract_match.group(1))
    assert payload["schema"] == "manager-gui.reader-shell.v1"
    assert payload["mode"] == "raw"
    assert payload["projection"]["schema"] == "manager-gui.reader-projection.v1"
    assert payload["projection"]["availability"]["status"] == "known"
    assert payload["projection"]["source_refs"]
    assert payload["projection"]["claims"]
    assert payload["projection"]["sample_data"] is not None

    assert app.render_json(url) == app.render_json(url.replace("mode=raw", "mode=reader"))
    assert app.render_export(url) == app.render_export(url.replace("mode=raw", "mode=reader"))
    assert json.loads(app.render_json(url))["schema"] == MANAGER_READ_MODEL_SCHEMA


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("mode", ("reader", "expert", "raw"))
@pytest.mark.parametrize("lang", ("zh-CN", "en"))
def test_all_reader_modes_and_locales_mount_the_same_contract_seam(
    route: str,
    mode: str,
    lang: str,
) -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    url = f"/?view={route}&fixture=complete&mode={mode}&lang={lang}&filter=a&filter=b"
    document = app.render(url)
    assert 'data-reader-contract="v1"' in document
    assert f'data-reader-mode="{mode}"' in document
    assert f'<html lang="{lang}">' in document
    assert 'class="reader-mode-switch"' in document
    assert document.count('class="reader-mode-link"') == 3
    assert "onclick" not in document
    assert '<script id="reader-contract" type="application/json">' in document
    assert document.count("filter=a") >= 1
    assert document.count("filter=b") >= 1


def test_reader_mode_links_preserve_duplicate_context_and_api_export_byte_stability() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    url = (
        "/?view=search&fixture=complete&mode=expert&lang=en&filter=a&filter=b"
        "&filter=&snapshot_token=s1"
    )
    document = app.render(url)
    links = re.findall(r'class="reader-mode-link"[^>]+href="([^"]+)"', document)
    assert len(links) == 3
    for link in links:
        query = parse_qsl(urlsplit(unescape(link)).query, keep_blank_values=True)
        assert query.count(("filter", "a")) == 1
        assert query.count(("filter", "b")) == 1
        assert query.count(("filter", "")) == 1
        assert sum(key == "mode" for key, _ in query) == 1

    base = "/?view=search&fixture=complete&filter=a&filter=b"
    assert app.render_json(base) == app.render_json(base + "&mode=raw&lang=en")
    assert app.render_export(base) == app.render_export(base + "&mode=raw&lang=en")


@pytest.mark.parametrize("state", ("partial", "blocked", "stale", "incomparable", "not_evaluated"))
def test_reader_gap_states_never_render_as_success_or_failure(state: str) -> None:
    projection = ManagerGUIApp(default_fixture=state).reader_projection(
        f"/?view=atlas&fixture={state}"
    )
    encoded = projection.to_json().lower()
    assert all(word not in encoded for word in ('"success"', '"failure"', '"pass"', '"fail"'))
    gaps = projection.limitations + projection.unknowns
    if projection.source_refs:
        assert gaps
        assert all(
            claim.kind
            in {ClaimKind.MISSING, ClaimKind.BLOCKED, ClaimKind.STALE, ClaimKind.INCOMPARABLE}
            for claim in gaps
        )


def test_projection_adapter_does_not_change_v0_model_or_add_private_storage_access() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    state = app.request_state("/?view=atlas&fixture=complete")
    model = app.read_model(state)
    projection = project_read_model(model)
    assert projection.raw_source.raw_bytes == model.to_json().encode("utf-8")
    assert projection.to_dict()["data"] == model.to_dict()["data"]
    assert not any(
        name in {"write", "update", "delete", "retry", "revalidate", "publish"}
        for name in dir(app)
        if not name.startswith("_")
    )
