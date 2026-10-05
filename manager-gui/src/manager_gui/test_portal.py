"""Focused S6-T2 tests for the Strategy Reporting Portal read-only seam."""

from __future__ import annotations

from typing import cast

from manager_gui import Availability, Derivation, ManagerReadModel, ReadModelStatus, SourceReference
from manager_gui.models import JSONValue
from manager_gui.provider import FORBIDDEN_PROVIDER_METHODS, public_provider_methods
from manager_gui.web.i18n import Translator
from manager_gui.web.portal import (
    PORTAL_INTEGRATION_HOOK,
    REPORT_SOURCE_RESOURCE,
    PortalArtifactState,
    PortalFixtureState,
    PortalViewModel,
    build_portal_fixture,
    portal_fixture_provider,
    render_portal,
    render_portal_view,
)


def _portal_model(
    data: object, status: ReadModelStatus = ReadModelStatus.KNOWN
) -> ManagerReadModel:
    source = SourceReference(
        source_id="report-source",
        owner="strategy-reporting",
        kind="public-report-source",
        locator="fixture://tests/report-source",
        schema="test.report-source.v0",
        revision="r1",
    )
    return ManagerReadModel(
        data=cast(JSONValue, data),
        source_refs=(source,),
        as_of="2026-10-03T12:00:00Z",
        snapshot_token="portal-test-v1",
        derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v0"),
        availability=Availability(status=status, complete=status is ReadModelStatus.KNOWN),
    )


def test_complete_fixture_keeps_source_publication_and_generated_artifact_separate() -> None:
    view = PortalViewModel.from_read_model(build_portal_fixture(PortalFixtureState.COMPLETE))

    assert view.artifact_state is PortalArtifactState.READY
    assert view.source_publication is not None
    assert view.generated_artifact is not None
    assert view.source_publication.publication_id == "source-publication-fixture-1"
    assert view.generated_artifact.artifact_id == "generated-artifact-fixture-1"
    assert view.renderer == "strategy-reporting-static"
    assert view.renderer_version == "renderer-v1"
    assert view.verify_status == "verified"
    assert view.rebuild_status == "not_requested"
    assert view.is_canonical_research_state is False

    rendered = render_portal(
        view, query_context={"fixture": "complete", "page": 2}, translator=Translator("en")
    )
    for marker in (
        'data-integration-hook="portal-view"',
        'data-portal-state="ready"',
        "Source publication",
        "Generated artifact",
        "strategy-reporting-static",
        "renderer-v1",
        "verified",
        "not_requested",
        "not canonical research state",
        "view=portal",
        "source_publication_id=source-publication-fixture-1",
        "artifact_id=generated-artifact-fixture-1",
    ):
        assert marker in rendered
    assert "page=2" not in rendered


def test_missing_and_not_generated_are_distinct() -> None:
    missing = PortalViewModel.from_read_model(build_portal_fixture("missing"))
    not_generated = PortalViewModel.from_read_model(build_portal_fixture("not-generated"))

    assert missing.artifact_state is PortalArtifactState.MISSING
    assert not_generated.artifact_state is PortalArtifactState.NOT_GENERATED
    assert missing.source_publication is None
    assert not_generated.source_publication is not None
    assert not_generated.generated_artifact is None
    assert 'data-portal-state="missing"' in render_portal(missing)
    not_generated_html = render_portal(not_generated, translator=Translator("en"))
    assert 'data-portal-state="not-generated"' in not_generated_html
    assert "has not been generated" in not_generated_html


def test_integrity_and_api_unavailable_states_are_explicit() -> None:
    integrity = PortalViewModel.from_read_model(build_portal_fixture("integrity_failure"))
    unavailable = PortalViewModel.from_read_model(build_portal_fixture("api_unavailable"))

    assert integrity.artifact_state is PortalArtifactState.INTEGRITY_FAILURE
    assert integrity.generated_artifact is not None
    assert integrity.generated_artifact.verify_status == "failed"
    assert unavailable.artifact_state is PortalArtifactState.API_UNAVAILABLE
    assert unavailable.generated_artifact is None
    assert 'data-status="integrity_failure"' in render_portal(integrity)
    assert 'data-status="api_unavailable"' in render_portal(unavailable)
    unavailable_html = render_portal(unavailable, translator=Translator("en"))
    assert "No private SQLite or filesystem fallback" in unavailable_html


def test_adapter_parses_renderer_mapping_and_nested_verify_rebuild_status() -> None:
    model = _portal_model(
        {
            "report_id": "report-1",
            "source_publication": {
                "publication_id": "publication-1",
                "version": "source-v2",
                "source_ref": "report-source",
            },
            "generated_artifact": {
                "artifact_id": "artifact-1",
                "renderer": {"name": "static-renderer", "version": "r3"},
                "verify": {"status": "verified"},
                "rebuild": {"status": "succeeded"},
                "locator": "fixture://reports/report-1/index.html",
            },
        }
    )
    view = PortalViewModel.from_read_model(model)

    assert view.source_publication is not None
    assert view.source_publication.locator == "fixture://tests/report-source"
    assert view.generated_artifact is not None
    assert view.generated_artifact.renderer == "static-renderer"
    assert view.generated_artifact.renderer_version == "r3"
    assert view.generated_artifact.verify_status == "verified"
    assert view.generated_artifact.rebuild_status == "succeeded"
    assert view.artifact_state is PortalArtifactState.READY


def test_report_index_keeps_each_report_source_and_artifact_distinct() -> None:
    model = _portal_model(
        {
            "reports": [
                {
                    "report_id": "report-a",
                    "title": "Report A",
                    "source_publication": {
                        "publication_id": "publication-a",
                        "locator": "fixture://reports/a/source",
                    },
                    "generated_artifact": {
                        "artifact_id": "artifact-a",
                        "locator": "fixture://reports/a/index.html",
                        "renderer": "static",
                        "renderer_version": "v1",
                        "verify_status": "verified",
                    },
                },
                {
                    "report_id": "report-b",
                    "title": "Report B",
                    "source_publication": {
                        "publication_id": "publication-b",
                        "locator": "fixture://reports/b/source",
                    },
                    "artifact_state": "not_generated",
                },
            ]
        }
    )
    view = PortalViewModel.from_read_model(model)

    assert [entry.report_id for entry in view.reports] == ["report-a", "report-b"]
    assert view.reports[0].generated_artifact is not None
    assert view.reports[1].generated_artifact is None
    assert view.reports[1].artifact_state is PortalArtifactState.NOT_GENERATED
    rendered = render_portal(view, query_context={"fixture": "index"})
    assert 'class="portal-report-index"' in rendered
    assert 'data-report-id="report-a"' in rendered
    assert 'data-report-id="report-b"' in rendered
    assert "artifact_id=artifact-a" in rendered
    assert "source_publication_id=publication-b" in rendered


def test_provider_hook_reads_report_source_once_and_preserves_snapshot() -> None:
    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def read(
            self,
            resource: str = "atlas",
            *,
            snapshot_token: str | None = None,
        ) -> ManagerReadModel:
            self.calls.append((resource, snapshot_token))
            return build_portal_fixture("complete")

    provider = CountingProvider()
    rendered = render_portal_view(
        provider, snapshot_token="requested-v2", query={"fixture": "complete"}
    )

    assert provider.calls == [(REPORT_SOURCE_RESOURCE, "requested-v2")]
    assert 'data-integration-hook="portal-view"' in rendered
    assert "report-source-complete-v0" in rendered


def test_fixture_provider_is_read_only_and_rejects_unrelated_resources() -> None:
    provider = portal_fixture_provider("complete")

    assert provider.read().availability.status is ReadModelStatus.KNOWN
    assert public_provider_methods(provider) == ("read",)
    assert FORBIDDEN_PROVIDER_METHODS.isdisjoint(public_provider_methods(provider))
    try:
        provider.read("atlas")
    except ValueError as error:
        assert "does not serve resource" in str(error)
    else:  # pragma: no cover - the fixture must keep its seam boundary
        raise AssertionError("Portal fixture provider served an unrelated resource")


def test_public_hook_has_stable_contract_marker() -> None:
    assert PORTAL_INTEGRATION_HOOK == "manager_gui.web.portal.render_portal_view"
    assert "artifact_id=artifact-1" in render_portal_view(
        _portal_model(
            {
                "report_id": "report-1",
                "generated_artifact": {"artifact_id": "artifact-1"},
            }
        ),
        query_context={"fixture": "complete", "page": 4},
    )


def test_complete_fixture_localizes_page_copy_and_preserves_opaque_values() -> None:
    model = build_portal_fixture("complete")
    chinese = render_portal(model)
    english = render_portal(model, translator=Translator("en"))

    assert "报告门户" in chinese
    assert "来源发布记录" in chinese
    assert "生成制品" in chinese
    assert "渲染器" in chinese
    assert "核验状态" in chinese
    assert "重建状态" in chinese
    assert "摘要哈希" in chinese
    assert "样例策略报告来源发布记录" in chinese
    assert "样例静态策略报告" in chinese
    assert "Strategy Reporting Portal" not in chinese
    assert "Source publication" not in chinese
    assert "Generated artifact" not in chinese
    assert "Strategy Reporting Portal" in english
    assert "Source publication" in english
    assert "Generated artifact" in english
    assert "Fixture Strategy Reporting source publication" in english
    assert "Fixture static Strategy Report" in english
    for opaque in (
        "source-publication-fixture-1",
        "generated-artifact-fixture-1",
        "strategy-reporting-static",
        "renderer-v1",
        "sha256:fixture-report-artifact-v1",
        "fixture://strategy-reporting/source/publication-1",
    ):
        assert opaque in chinese
        assert opaque in english
    assert 'data-boundary="static-publication-not-canonical"' in chinese
    assert "rebuild" not in chinese.lower() or "重建" in chinese
    assert "run" not in chinese.lower()


def test_portal_states_have_localized_labels_in_both_locales() -> None:
    expected = {
        "complete": ("ready", "就绪", "Ready"),
        "missing": ("missing", "未记录", "Missing"),
        "not_generated": ("not-generated", "尚未生成", "Not generated"),
        "partial": ("partial", "部分可用", "Partial"),
        "integrity_failure": ("integrity-failure", "完整性校验失败", "Integrity failure"),
        "api_unavailable": ("api-unavailable", "API 不可用", "API unavailable"),
    }
    for fixture, (state, chinese_label, english_label) in expected.items():
        chinese = render_portal(build_portal_fixture(fixture))
        english = render_portal(build_portal_fixture(fixture), translator=Translator("en"))
        assert f'data-portal-state="{state}"' in chinese
        assert chinese_label in chinese
        assert english_label in english
        assert f'data-portal-state="{state}"' in english


def test_portal_index_aria_and_context_links_are_localized_and_stable() -> None:
    model = _portal_model(
        {
            "reports": [
                {
                    "report_id": "report-a",
                    "title": "Report A",
                    "source_publication": {"publication_id": "publication-a"},
                    "generated_artifact": {"artifact_id": "artifact-a"},
                },
                {
                    "report_id": "report-b",
                    "title": "Report B",
                    "source_publication": {"publication_id": "publication-b"},
                    "artifact_state": "not_generated",
                },
            ]
        }
    )
    context = "/?view=portal&fixture=complete&lang=en&panel=events&report=keep"
    english = render_portal(model, query_context=context, translator=Translator("en"))
    chinese = render_portal(model, query_context=context)
    assert 'aria-label="Report index"' in english
    assert 'aria-label="报告索引"' in chinese
    for document in (english, chinese):
        assert "panel=events" in document
        assert "report=keep" in document
        assert "report_id=report-a" in document
        assert "artifact_id=artifact-a" in document
        assert "source_publication_id=publication-b" in document
        assert '<button' not in document


def test_portal_pseudo_locale_marks_every_page_owned_string() -> None:
    pseudo = render_portal(
        build_portal_fixture("complete"), translator=Translator("en", pseudo=True)
    )
    assert "⟦Strategy Reporting Portal" in pseudo
    assert "⟦Source publication" in pseudo
    assert "⟦Generated artifact" in pseudo
    assert "source-publication-fixture-1" in pseudo


def test_portal_keeps_owner_text_escaped_and_raw_model_language_neutral() -> None:
    owner_title = '<script>alert("owner")</script> & owner'
    owner_digest = 'sha256:<x>&"'
    model = _portal_model(
        {
            "report_id": 'report-<id>"',
            "title": owner_title,
            "source_publication": {
                "publication_id": 'publication-<id>"',
                "title": owner_title,
                "locator": "https://example.test/source?a=1&b=2",
            },
            "generated_artifact": {
                "artifact_id": 'artifact-<id>"',
                "title": owner_title,
                "locator": "javascript:alert(1)",
                "renderer": owner_title,
                "renderer_version": "owner-v1",
                "verify_status": "verified",
                "rebuild_status": "not_requested",
                "digest": owner_digest,
            },
        }
    )
    before = model.to_json()
    chinese = render_portal(model)
    english = render_portal(model, translator=Translator("en"))
    assert model.to_json() == before
    for document in (chinese, english):
        assert owner_title not in document
        assert "&lt;script&gt;alert(&quot;owner&quot;)&lt;/script&gt; &amp; owner" in document
        assert "javascript:alert(1)" not in document
        assert "owner-v1" in document
        assert "sha256:&lt;x&gt;&amp;&quot;" in document
        assert 'data-owner-text="true"' in document
        assert "report-&lt;id&gt;" in document
