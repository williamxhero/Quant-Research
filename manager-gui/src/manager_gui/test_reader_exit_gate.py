"""R1 exit-gate evidence for Reader projection, modes, and boundaries."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from html import unescape
from urllib.parse import parse_qsl, urlsplit

import pytest

from manager_gui import (
    FORBIDDEN_PROVIDER_METHODS,
    FixtureState,
    fixture_provider,
    public_provider_methods,
)
from manager_gui.models import Derivation, SourceReference
from manager_gui.reader import (
    ClaimKind,
    ReaderAvailabilityStatus,
    ReaderFixtureState,
    ReaderProjection,
    build_reader_fixture,
    project_reader_model,
)
from manager_gui.web import ManagerGUIApp
from manager_gui.web.i18n import Locale, Translator
from manager_gui.web.i18n.catalog.reader import (
    render_availability_explanation,
    render_claim_explanation,
)

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
MODES = ("reader", "expert", "raw")
EXPECTED_AVAILABILITY = {
    "empty": ReaderAvailabilityStatus.MISSING,
    "complete": ReaderAvailabilityStatus.KNOWN,
    "partial": ReaderAvailabilityStatus.KNOWN,
    "blocked": ReaderAvailabilityStatus.BLOCKED,
    "stale": ReaderAvailabilityStatus.STALE,
    "incomparable": ReaderAvailabilityStatus.INCOMPARABLE,
    "integrity_failure": ReaderAvailabilityStatus.INTEGRITY_FAILURE,
    "api_unavailable": ReaderAvailabilityStatus.API_UNAVAILABLE,
    "not_evaluated": ReaderAvailabilityStatus.NOT_EVALUATED,
    "cursor_expired": ReaderAvailabilityStatus.STALE,
    "snapshot_drift": ReaderAvailabilityStatus.STALE,
}


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("fixture", tuple(FixtureState))
def test_reader_i18n_mode_fixture_matrix(route: str, fixture: FixtureState) -> None:
    """17 routes x 11 states x 3 modes x 2 locales keep the shell contract stable."""

    app = ManagerGUIApp(default_fixture=fixture)
    base = (
        f"/?view={route}&fixture={fixture.value}&scope=A0&root=record-1"
        "&filter=state%3Dknown&filter=owner%3Dfixture&filter=&snapshot_token=s1"
    )
    expected_json = app.render_json(base)
    expected_export = app.render_export(base)
    source_model = app.read_model(app.request_state(base))
    for mode in MODES:
        for locale in ("zh-CN", "en"):
            url = f"{base}&mode={mode}&lang={locale}"
            document = app.render(url)
            assert f'<html lang="{locale}">' in document
            assert document.count('class="reader-mode-link"') == 3
            assert 'data-sample-banner="fixture"' in document
            match = re.search(
                r'<script id="reader-contract" type="application/json">(.*?)</script>',
                document,
                re.DOTALL,
            )
            assert match is not None
            payload = json.loads(match.group(1))
            projection = ReaderProjection.from_dict(payload["projection"])
            assert payload["mode"] == mode
            assert projection.to_dict()["data"] == source_model.data
            assert projection.source_refs == source_model.source_refs
            assert projection.raw_source.raw_bytes == source_model.to_json().encode("utf-8")
            assert app.render_json(url) == expected_json
            assert app.render_export(url) == expected_export
            raw_match = re.search(r'<pre class="raw-json"[^>]*>(.*?)</pre>', document, re.DOTALL)
            assert raw_match is not None
            assert unescape(raw_match.group(1)) == expected_json


def test_story_legacy_mode_survives_reader_mode_switch() -> None:
    app = ManagerGUIApp(default_fixture=FixtureState.COMPLETE)
    document = app.render(
        "/?view=stories&fixture=complete&mode=evidence&lang=en"
        "&scope=A0&filter=campaign&snapshot_token=s1"
    )
    links = re.findall(r'class="reader-mode-link"[^>]+href="([^"]+)"', document)
    assert len(links) == 3
    expert_link = next(unescape(link) for link in links if "mode=expert" in unescape(link))
    query = parse_qsl(urlsplit(expert_link).query, keep_blank_values=True)
    assert ("mode", "expert") in query
    assert ("story_mode", "evidence") in query
    assert ("filter", "campaign") in query
    switched = app.render(expert_link)
    assert 'data-reader-mode="expert"' in switched
    assert 'data-story-mode="evidence"' in switched


def test_reader_claim_gap_and_availability_matrix_is_typed_and_neutral() -> None:
    for state in ReaderFixtureState:
        projection = build_reader_fixture(state)
        assert projection.availability.status is EXPECTED_AVAILABILITY[state.value]
        assert projection.sample_data is not None

        source_ids = {reference.source_id for reference in projection.source_refs}
        for claim in projection.claims + projection.limitations + projection.unknowns:
            assert claim.source_refs
            assert {reference.source_id for reference in claim.source_refs} <= source_ids
            assert set(claim.derivation.inputs) <= source_ids
            assert claim.explanation_key
            if claim.kind in {ClaimKind.DERIVED, ClaimKind.INTERPRETED}:
                assert claim.derivation.rule
                assert claim.derivation.version
            else:
                assert claim.derivation.kind == "direct"
            if claim.kind in {ClaimKind.KNOWN, ClaimKind.OWNER_TEXT}:
                assert claim.availability.status is ReaderAvailabilityStatus.KNOWN
            elif claim.kind is ClaimKind.DERIVED:
                assert claim.availability.status is ReaderAvailabilityStatus.DERIVED
            elif claim.kind is ClaimKind.INTERPRETED:
                assert claim.availability.status is ReaderAvailabilityStatus.INTERPRETED
            elif claim.kind is ClaimKind.MISSING:
                assert claim.availability.status in {
                    ReaderAvailabilityStatus.MISSING,
                    ReaderAvailabilityStatus.NOT_EVALUATED,
                    ReaderAvailabilityStatus.API_UNAVAILABLE,
                }
            elif claim.kind is ClaimKind.BLOCKED:
                assert claim.availability.status in {
                    ReaderAvailabilityStatus.BLOCKED,
                    ReaderAvailabilityStatus.INTEGRITY_FAILURE,
                }
            else:
                assert claim.availability.status.value == claim.kind.value.lower()

        for locale in Locale:
            translator = Translator(locale, strict=True)
            explanation = render_availability_explanation(translator, projection.availability)
            assert explanation
            if projection.availability.reason is not None:
                assert projection.availability.reason in explanation
            for claim in projection.claims + projection.limitations + projection.unknowns:
                rendered = render_claim_explanation(translator, claim)
                assert rendered == render_claim_explanation(translator, claim)
                assert all(source.source_id in rendered for source in claim.source_refs)
                if claim.kind is ClaimKind.DERIVED:
                    assert claim.derivation.rule is not None
                    assert claim.derivation.rule in rendered
                if claim.is_gap and claim.availability.reason is not None:
                    assert claim.availability.reason in rendered
        encoded = projection.to_json().lower()
        assert '"success"' not in encoded
        assert '"failure"' not in encoded


def test_reader_fixture_and_owner_matrix_keeps_sample_provenance_separate() -> None:
    for state in FixtureState:
        fixture_projection = build_reader_fixture(state)
        assert fixture_projection.sample_data is not None

        owner_model = fixture_provider(state).read("atlas")
        owner_ref = SourceReference(
            f"owner-{state.value}",
            "owner-system",
            "public-record",
            f"https://owner.invalid/records/{state.value}",
            schema="owner-v1",
            revision=state.value,
        )
        owner_model = replace(
            owner_model,
            source_refs=(owner_ref,),
            derivation=Derivation("direct", inputs=(owner_ref.source_id,), version="owner-v1"),
        )
        owner_projection = project_reader_model(owner_model, resource="atlas")
        assert owner_projection.sample_data is None
        assert owner_projection.source_refs == (owner_ref,)
        assert owner_projection.raw_source.raw_bytes == owner_model.to_json().encode("utf-8")

        class OwnerProvider:
            def read(
                self,
                resource: str = "atlas",
                *,
                snapshot_token: str | None = None,
                owner_model: object = owner_model,
            ):
                del resource, snapshot_token
                return owner_model

        document = ManagerGUIApp(OwnerProvider()).render(
            f"/?view=atlas&fixture={state.value}&mode=reader"
        )
        assert 'data-sample-banner="fixture"' not in document
        assert "owner.invalid" in document


def test_reader_projection_preserves_v0_shape_and_read_only_provider_boundary() -> None:
    provider = fixture_provider(FixtureState.COMPLETE)
    app = ManagerGUIApp(provider)
    model = provider.read("atlas")
    expected_json = model.to_json(indent=2)

    assert public_provider_methods(provider) == ("read",)
    assert not FORBIDDEN_PROVIDER_METHODS.intersection(public_provider_methods(provider))
    assert set(model.to_dict()) == {
        "schema",
        "data",
        "source_refs",
        "as_of",
        "snapshot_token",
        "derivation",
        "availability",
        "errors",
    }
    for mode in MODES:
        for locale in ("zh-CN", "en"):
            url = f"/?view=atlas&fixture=complete&mode={mode}&lang={locale}"
            assert app.render_json(url) == expected_json
            assert "reader-projection" not in app.render_json(url)
            export = app.render_export(url)
            assert "reader-projection" not in export
            assert '"mode"' not in export

    projection = app.reader_projection("/?view=atlas&fixture=complete")
    assert projection.raw_source.raw_bytes == model.to_json().encode("utf-8")
    assert projection.mode_reference("expert").sha256 == projection.raw_source.sha256
    assert projection.mode_reference("raw").sha256 == projection.raw_source.sha256
