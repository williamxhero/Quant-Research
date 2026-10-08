"""R4-T4 integration and exit-gate evidence for the R4 Reader surfaces."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from html import unescape
from urllib.parse import parse_qsl, urlsplit

import pytest

from manager_gui import FixtureState
from manager_gui.models import Derivation, SourceReference
from manager_gui.web import ManagerGUIApp
from manager_gui.web.evidence_lineage_reader import (
    EvidenceLineageReaderViewModel,
    build_evidence_lineage_reader_fixture,
)

R4_ROUTES = (
    "memory",
    "memory-failures",
    "failure-patterns",
    "evidence",
    "lineage",
    "strategy-genome-comparison",
    "evidence-object-comparison",
)
R4_HOOKS = {
    "memory": "memory-view",
    "memory-failures": "failure-patterns-view",
    "failure-patterns": "failure-patterns-view",
    "evidence": "evidence-view",
    "lineage": "lineage-view",
    "strategy-genome-comparison": "strategy-genome-comparison-view",
    "evidence-object-comparison": "evidence-comparison-view",
}


@pytest.mark.parametrize("route", R4_ROUTES)
@pytest.mark.parametrize("mode", ("reader", "expert", "raw"))
def test_r4_routes_mount_reader_contract_and_keep_context(route: str, mode: str) -> None:
    url = (
        f"/?view={route}&fixture=complete&mode={mode}&lang=en&scope=A0&root=record-1"
        "&filter=state%3Dknown&filter=owner%3Dfixture&filter=&snapshot_token=r4-s1"
    )
    document = ManagerGUIApp(default_fixture=FixtureState.COMPLETE).render(url)

    assert 'data-reader-contract="v1"' in document
    assert f'data-integration-hook="{R4_HOOKS[route]}"' in document
    assert 'data-sample-banner="fixture"' in document
    assert 'class="read-only-badge"' in document
    assert 'class="reader-mode-switch"' in document
    assert "filter=state%3Dknown" in document
    assert "filter=owner%3Dfixture" in document
    assert "filter=" in document
    assert "snapshot_token=r4-s1" in document
    assert "onclick" not in document
    if route == "lineage" and mode == "reader":
        assert 'class="reader-legacy-compat" hidden' in document

    mode_links = [
        unescape(href)
        for href in re.findall(r'class="reader-mode-link"[^>]+href="([^"]+)"', document)
    ]
    assert len(mode_links) == 3
    for link in mode_links:
        query = parse_qsl(urlsplit(link).query, keep_blank_values=True)
        assert query.count(("filter", "state=known")) == 1
        assert query.count(("filter", "owner=fixture")) == 1
        assert query.count(("filter", "")) == 1
        assert ("snapshot_token", "r4-s1") in query


@pytest.mark.parametrize("route", R4_ROUTES)
def test_r4_projection_claims_trace_the_same_v0_envelope(route: str) -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    url = f"/?view={route}&fixture=complete&mode=reader&lang=en"
    state = app.request_state(url)
    model = app.read_model(state)
    projection = app.reader_projection(url)

    assert projection.raw_source.raw_bytes == model.to_json().encode("utf-8")
    assert projection.to_dict()["data"] == model.to_dict()["data"]
    assert projection.source_refs == model.source_refs
    assert projection.snapshot_token == model.snapshot_token
    for claim in projection.claims + projection.limitations + projection.unknowns:
        assert claim.source_refs
        assert set(claim.derivation.inputs) <= {
            reference.source_id for reference in model.source_refs
        }
        if claim.kind.value in {"derived", "interpreted"}:
            assert claim.derivation.rule
            assert claim.derivation.version

    for mode in ("reader", "expert", "raw"):
        mode_url = url.replace("mode=reader", f"mode={mode}")
        assert app.render_json(mode_url) == model.to_json(indent=2)
        assert json.loads(app.render_export(mode_url)) == json.loads(
            app.render_export(url)
        )


@pytest.mark.parametrize(
    "fixture", (FixtureState.BLOCKED, FixtureState.STALE, FixtureState.INCOMPARABLE)
)
def test_r4_non_success_states_remain_distinct_on_reader_pages(fixture: FixtureState) -> None:
    app = ManagerGUIApp(default_fixture=fixture)
    for route in R4_ROUTES:
        document = app.render(f"/?view={route}&fixture={fixture.value}&mode=reader")
        expected_status = fixture.value
        assert f'data-status="{expected_status}"' in document
        assert 'data-sample-banner="fixture"' in document
        assert 'data-reader-contract="v1"' in document


def test_r4_owner_provider_has_no_fixture_banner_and_preserves_owner_sources() -> None:
    fixture_app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    fixture_model = fixture_app.read_model(
        fixture_app.request_state("/?view=evidence&fixture=complete")
    )
    owner_ref = SourceReference(
        source_id="owner-r4-source",
        owner="owner-system",
        kind="published-record",
        locator="https://owner.invalid/r4/source",
        schema="owner-r4-v1",
        revision="r4-1",
    )
    owner_model = replace(
        fixture_model,
        source_refs=(owner_ref,),
        derivation=Derivation("direct", inputs=(owner_ref.source_id,), version="owner-r4-v1"),
        snapshot_token="owner-r4",
    )

    class OwnerProvider:
        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            del resource, snapshot_token
            return owner_model

    document = ManagerGUIApp(OwnerProvider()).render(
        "/?view=evidence&mode=reader&lang=en&snapshot_token=owner-r4"
    )
    assert 'data-sample-banner="fixture"' not in document
    assert "owner.invalid" in document
    assert 'data-owner-text="true"' in document
    assert 'translate="no"' in document


def test_r4_lineage_relation_keeps_owner_endpoints_when_source_refs_are_present() -> None:
    view = EvidenceLineageReaderViewModel.from_read_model(
        build_evidence_lineage_reader_fixture("complete")
    )
    relation = view.relations[0]
    assert relation.source_id == "protocol-evidence-1"
    assert relation.target_id == "conclusion-1"
    assert relation.source_refs[0].source_id == "evidence-fixture-source"
