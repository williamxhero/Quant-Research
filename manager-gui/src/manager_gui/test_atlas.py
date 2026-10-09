"""Focused tests for the T3 Atlas page-local view and renderer."""

from __future__ import annotations

from typing import cast

from manager_gui import (
    Availability,
    Derivation,
    ManagerGUIApp,
    ManagerReadModel,
    ReadModelStatus,
    SourceReference,
    fixture_provider,
)
from manager_gui.models import JSONValue
from manager_gui.testing.i18n import (
    assert_accessible,
    assert_dom_equivalent,
    assert_enum_vocabulary,
    assert_lang_propagation,
    assert_language_text,
    assert_owner_text_escaped,
    assert_pseudo_localized,
    parse_html,
)
from manager_gui.web.atlas import (
    LIFECYCLE_SPINE,
    AtlasFilters,
    AtlasViewModel,
    atlas_link,
    render_atlas,
    render_atlas_reading,
)
from manager_gui.web.i18n import Locale, Translator


def _complete_model(locale: Locale | str = Locale.EN) -> ManagerReadModel:
    source = SourceReference(
        source_id="workspace-atlas",
        owner="strategy-workspace",
        kind="public-record",
        locator="workspace://atlas",
        schema="workspace.atlas.v1",
        revision="r7",
    )
    language = Locale(locale)
    titles = {
        Locale.EN: {
            "campaign": "Campaign one",
            "hypothesis": "Hypothesis one",
            "candidate": "Candidate one",
            "run": "Run one",
            "gap": "Coverage gap",
            "gap_detail": "More dates are needed.",
            "research_gap": "Need replication evidence",
        },
        Locale.ZH_CN: {
            "campaign": "研究活动一",
            "hypothesis": "研究假设一",
            "candidate": "候选对象一",
            "run": "运行一",
            "gap": "覆盖缺口",
            "gap_detail": "需要更多日期。",
            "research_gap": "需要复现证据",
        },
    }[language]
    records = [
        {
            "id": "campaign-1",
            "record_type": "campaign",
            "title": titles["campaign"],
            "state": "active",
            "changed_at": "2026-10-03T08:00:00Z",
            "source": "workspace-atlas",
        },
        {
            "id": "hypothesis-1",
            "record_type": "hypothesis",
            "title": titles["hypothesis"],
            "state": "open",
            "changed_at": "2026-10-02T08:00:00Z",
            "source": "workspace-atlas",
            "conclusion_state": "unresolved",
            "research_gaps": [titles["research_gap"]],
        },
        {
            "id": "candidate-1",
            "record_type": "candidate",
            "title": titles["candidate"],
            "state": "blocked",
            "changed_at": "2026-10-01T08:00:00Z",
            "source": "workspace-atlas",
            "availability": "blocked",
            "frontier": True,
        },
        {
            "id": "run-1",
            "record_type": "run",
            "title": titles["run"],
            "state": "completed",
            "changed_at": "2026-09-30T08:00:00Z",
            "source": "workspace-atlas",
        },
        {"id": "evidence-1", "record_type": "evidence", "state": "recorded"},
        {"id": "qualification-1", "record_type": "qualification", "state": "pending"},
        {"id": "replication-1", "record_type": "replication", "state": "planned"},
        {"id": "revalidation-1", "record_type": "revalidation", "state": "planned"},
    ]
    return ManagerReadModel(
        data=cast(
            JSONValue,
            {
                "records": records,
                "research_gaps": [
                    {"id": "gap-1", "title": titles["gap"], "detail": titles["gap_detail"]}
                ],
            },
        ),
        source_refs=(source,),
        as_of="2026-10-03T09:00:00Z",
        snapshot_token="atlas-snapshot-7",
        derivation=Derivation(kind="direct", inputs=(source.source_id,), version="v1"),
        availability=Availability(status=ReadModelStatus.KNOWN, complete=True),
    )


def test_complete_atlas_preserves_lifecycle_and_explicit_sections() -> None:
    view = AtlasViewModel.from_read_model(_complete_model(), recent_limit=None)

    assert tuple(record.record_type for record in view.records)[:3] == (
        "campaign",
        "hypothesis",
        "candidate",
    )
    assert tuple(record_type for record_type, _ in view.lifecycle_counts) == LIFECYCLE_SPINE
    assert view.status_counts == (
        ("active", 1),
        ("blocked", 1),
        ("completed", 1),
        ("open", 1),
        ("pending", 1),
        ("planned", 2),
        ("recorded", 1),
    )
    assert [record.record_id for record in view.blocked_or_unavailable] == ["candidate-1"]
    assert [record.record_id for record in view.unresolved_conclusions] == ["hypothesis-1"]
    assert [record.record_id for record in view.frontier] == ["candidate-1"]
    assert len(view.research_gaps) == 2

    document = render_atlas(
        view, query_context="/?fixture=partial&q=alpha", translator=Translator(Locale.EN)
    )
    for label in (
        "Campaign",
        "Hypothesis",
        "Candidate",
        "Run",
        "Evidence",
        "Qualification",
        "Replication",
        "Revalidation",
    ):
        assert label in document
    assert "Recently changed" in document
    assert "Blocked or unavailable" in document
    assert "Unresolved conclusions" in document
    assert "Research gaps" in document
    assert "Navigable frontier" in document
    assert "success, ranking, or advice" in document
    assert "atlas-snapshot-7" in document


def test_empty_atlas_says_scope_has_no_records() -> None:
    model = fixture_provider("empty").read("atlas")
    view = AtlasViewModel.from_read_model(model)

    assert view.records == ()
    document = render_atlas(view, translator=Translator(Locale.EN))
    assert 'data-status="missing"' in document
    assert 'data-display-state="empty"' in document
    assert "No records are present in this scope." in document
    assert "research does not exist" not in document.lower()


def test_partial_atlas_keeps_available_records_and_context() -> None:
    model = fixture_provider("partial").read("atlas")
    view = AtlasViewModel.from_read_model(model)

    assert view.read_model.availability.complete is False
    assert [record.record_id for record in view.records] == ["campaign-fixture-1"]
    document = render_atlas(
        view, query_context="/?fixture=partial&q=campaign", translator=Translator(Locale.EN)
    )
    assert 'data-display-state="partial"' in document
    assert "Fixture campaign" in document
    assert "fixture-partial-v0" in document
    assert "campaign" in document


def test_blocked_atlas_uses_shared_status_semantics_without_fake_empty_copy() -> None:
    model = fixture_provider("blocked").read("atlas")
    document = render_atlas(
        AtlasViewModel.from_read_model(model), translator=Translator(Locale.EN)
    )

    assert 'data-status="blocked"' in document
    assert 'data-display-state="error"' in document
    assert "The approved read seam is blocked" in document
    assert "research does not exist" not in document.lower()


def test_filters_and_links_are_stable_and_preserve_query_context() -> None:
    view = AtlasViewModel.from_read_model(
        _complete_model(),
        filters=AtlasFilters(record_type="candidate", state="blocked", date="2026-10-01"),
    )

    assert [record.record_id for record in view.records] == ["candidate-1"]
    assert atlas_link(
        "candidate/1",
        query_context="/?fixture=partial&panel=events&q=alpha",
    ) == ("/?view=atlas&fixture=partial&panel=events&q=alpha&record_id=candidate%2F1")
    assert atlas_link(
        "candidate/1",
        query_context="/?q=alpha&fixture=partial",
    ) == atlas_link("candidate/1", query_context="/?fixture=partial&q=alpha")

    document = render_atlas(
        view, query_context="/?fixture=partial&q=alpha", translator=Translator(Locale.EN)
    )
    assert 'name="record_type"' in document
    assert 'name="state"' in document
    assert 'name="date"' in document
    assert 'name="source"' in document
    assert 'name="availability"' in document
    assert (
        'href="/?view=atlas&amp;fixture=partial&amp;q=alpha&amp;record_type=candidate'
        '&amp;state=blocked&amp;date=2026-10-01&amp;record_id=candidate-1"' in document
    )


def test_atlas_localizes_page_copy_and_preserves_language_query_state() -> None:
    zh_context = "/?view=atlas&fixture=complete&panel=events&q=alpha"
    en_context = zh_context + "&lang=en"
    zh_model = AtlasViewModel.from_read_model(_complete_model(Locale.ZH_CN), recent_limit=None)
    en_model = AtlasViewModel.from_read_model(_complete_model(Locale.EN), recent_limit=None)
    zh = render_atlas(zh_model, query_context=zh_context, translator=Translator(strict=True))
    en = render_atlas(
        en_model, query_context=en_context, translator=Translator(Locale.EN, strict=True)
    )

    assert "研究总览" in zh
    assert "研究活动一" in zh
    assert "研究生命周期" in zh
    assert "Recently changed" not in zh
    assert "Atlas overview" in en
    assert "Campaign one" in en
    assert "Research lifecycle" in en
    assert "研究总览" not in en
    assert 'data-record-id="campaign-1"' in zh and 'data-record-id="campaign-1"' in en
    assert 'data-record-type="campaign"' in zh and 'data-record-type="campaign"' in en
    assert_enum_vocabulary("atlas.lifecycle", LIFECYCLE_SPINE)
    assert_enum_vocabulary(
        "atlas.state",
        (
            "active",
            "open",
            "blocked",
            "ready",
            "completed",
            "recorded",
            "pending",
            "planned",
            "unresolved",
            "unknown",
            "missing",
            "unavailable",
            "api_unavailable",
        ),
    )

    assert_dom_equivalent(zh, en)
    assert_language_text(zh, Locale.ZH_CN)
    assert_language_text(en, Locale.EN)
    assert_lang_propagation(zh, None, source_url=zh_context)
    assert_lang_propagation(en, Locale.EN, source_url=en_context)
    assert_accessible(zh)
    assert_accessible(en)
    assert_pseudo_localized(
        render_atlas(
            zh_model,
            query_context=zh_context,
            translator=Translator(pseudo=True, strict=True),
        )
    )


def test_complete_atlas_fixture_has_localized_display_copy_but_keeps_payload_data() -> None:
    model = fixture_provider("complete").read("atlas")
    zh = render_atlas(model, translator=Translator(Locale.ZH_CN, strict=True))
    en = render_atlas(model, translator=Translator(Locale.EN, strict=True))

    assert "样例研究活动" in zh
    assert "Fixture campaign" in en
    zh_visible = "".join(surface.text for surface in parse_html(zh).visible_text)
    assert "Fixture campaign" not in zh_visible
    atlas_data = cast(dict[str, object], model.data)
    records = cast(list[dict[str, object]], atlas_data["records"])
    assert records[0]["title"] == "Fixture campaign"


def test_atlas_owner_title_is_escaped_once_and_remains_verbatim() -> None:
    owner_title = 'Owner <title> & "quoted" {x} 中文'
    model = ManagerReadModel(
        data=cast(
            JSONValue,
            {"records": [{"id": "owner-record", "record_type": "campaign", "title": owner_title}]},
        ),
        source_refs=(),
        as_of=None,
        snapshot_token=None,
        derivation=Derivation(kind="direct", version="v1"),
        availability=Availability(status=ReadModelStatus.KNOWN, complete=True),
    )
    markup = render_atlas(model, translator=Translator(strict=True))

    assert_owner_text_escaped(markup, owner_title)
    assert 'data-record-id="owner-record"' in markup


def test_atlas_reader_and_expert_share_explicit_story_content() -> None:
    model = fixture_provider("complete").read("atlas")

    reader = render_atlas_reading(
        model,
        query_context="/?view=atlas&fixture=complete",
        translator=Translator(Locale.EN),
        sample=True,
    )
    expert = render_atlas(
        model,
        query_context="/?view=atlas&fixture=complete",
        translator=Translator(Locale.EN),
        include_reader_surface=False,
    )

    for text in (
        "Why test the fixture strategy?",
        "Validate the complete fixture-backed research path.",
        "Frozen fixture design",
        "The fixture run completed with explicit provenance.",
        "Keep the read-only path as the integration contract.",
        "The source reference is available for inspection.",
    ):
        assert text in reader
        assert text in expert


def test_complete_atlas_reader_answers_first_screen_with_content_or_unknowns() -> None:
    model = fixture_provider("complete").read("atlas")

    reader = render_atlas_reading(
        model,
        query_context="/?view=atlas&fixture=complete",
        translator=Translator(Locale.EN),
        sample=True,
    )
    main_story = reader.split('<div class="atlas-reading-metadata"', 1)[0]

    assert "A fabricated example, not your research record." in main_story
    assert "Fixture campaign" in main_story
    for heading in (
        "Research question",
        "Current result",
        "Scope",
        "What is not known yet",
        "Evidence and entry points",
    ):
        assert heading in main_story
    assert "currently unavailable" in main_story.lower()
    assert "record_type" not in main_story
    assert "protocol" not in main_story.lower()


def test_atlas_reader_does_not_infer_result_from_owner_status() -> None:
    reader = render_atlas_reading(
        _complete_model(),
        query_context="/?view=atlas",
        translator=Translator(Locale.EN),
        sample=False,
    )
    result_section = reader.split("Current result", 1)[1].split("Scope", 1)[0]

    assert "currently unavailable" in result_section.lower()
    assert "active" not in result_section.lower()
    assert "completed" not in result_section.lower()


def test_atlas_reader_and_expert_project_all_research_story_fields_and_gaps() -> None:
    source = SourceReference(
        source_id="story-source",
        owner="owner",
        kind="public-record",
        locator="workspace://story",
        schema="story.v1",
        revision="r1",
    )
    model = ManagerReadModel(
        data=cast(
            JSONValue,
            {
                "research_object": "Object from the same model",
                "research_question": "Question from the same model",
                "research_process": "Process from the same model",
                "research_result": "Result from the same model",
                "research_scope": "Scope from the same model",
                "research_gaps": [
                    {"title": "Top gap title", "detail": "Top gap detail"}
                ],
                "records": [
                    {
                        "id": "record-1",
                        "record_type": "campaign",
                        "title": "Record object",
                        "research_gaps": [
                            {"title": "Record gap title", "detail": "Record gap detail"}
                        ],
                    }
                ],
            },
        ),
        source_refs=(source,),
        as_of=None,
        snapshot_token=None,
        derivation=Derivation(kind="direct", version="v1"),
        availability=Availability(status=ReadModelStatus.KNOWN, complete=True),
    )
    reader = render_atlas_reading(
        model, query_context="/?view=atlas", translator=Translator(Locale.EN), sample=False
    )
    expert = render_atlas(
        AtlasViewModel.from_read_model(model),
        query_context="/?view=atlas",
        translator=Translator(Locale.EN),
        include_reader_surface=False,
    )

    expected = (
        "Object from the same model",
        "Question from the same model",
        "Process from the same model",
        "Result from the same model",
        "Scope from the same model",
        "Top gap title",
        "Top gap detail",
        "Record gap title",
        "Record gap detail",
    )
    for text in expected:
        assert text in reader
        assert text in expert


def test_atlas_reader_filters_record_level_gaps_with_their_record() -> None:
    model = _complete_model()
    payload = cast(dict[str, object], model.data)
    records = cast(list[dict[str, object]], payload["records"])
    records[0]["research_gaps"] = [{"title": "Campaign-only gap", "detail": "Campaign detail"}]
    records[1]["research_gaps"] = [{"title": "Hypothesis-only gap", "detail": "Hypothesis detail"}]

    reader = render_atlas_reading(
        model,
        query_context="/?view=atlas&record_type=hypothesis",
        translator=Translator(Locale.EN),
        sample=False,
    )

    assert "Hypothesis-only gap" in reader
    assert "Hypothesis detail" in reader
    assert "Campaign-only gap" not in reader
    assert "Campaign detail" not in reader


def test_atlas_reader_owner_story_links_only_use_public_locators() -> None:
    model = _complete_model()
    payload = cast(dict[str, object], model.data)
    payload["chapters"] = {
        "intent": [
            {
                "title": "Safe and unsafe references",
                "links": [
                    {"label": "safe", "href": "https://example.com/reference"},
                    {"label": "javascript", "href": "javascript:alert(1)"},
                    {"label": "file", "href": "file:///tmp/private"},
                    {"label": "locator", "href": "not-a-public-locator"},
                ],
            }
        ]
    }

    reader = render_atlas_reading(
        model,
        query_context="/?view=atlas",
        translator=Translator(Locale.EN),
        sample=False,
    )

    assert 'href="https://example.com/reference"' in reader
    assert 'href="javascript:' not in reader
    assert 'href="file:' not in reader
    assert 'href="not-a-public-locator"' not in reader
    assert "Source cannot be opened or verified" in reader
    assert "javascript" in reader and "file" in reader and "locator" in reader


def test_real_atlas_reader_hides_system_metadata_and_shell_snapshot() -> None:
    markup = ManagerGUIApp().render("/?view=atlas&fixture=complete&mode=reader&lang=en")
    document = parse_html(markup)
    visible = " ".join(surface.text for surface in document.visible_text)
    lowered = visible.lower()

    assert visible.count("Research content") == 1
    assert lowered.index("research content") < lowered.index("open inspector")
    assert "A fabricated example, not your research record." in visible
    for system_term in (
        "Expert research content",
        "What this page answers",
        "What can be confirmed currently",
        "Derived from",
        "Snapshot",
        "schema",
        "records, not studies",
        "Unit: records",
        "fixture-workspace-campaigns",
        "Observed at",
        "strategy-workspace",
        "public-record",
        "fixture://",
    ):
        assert system_term.lower() not in lowered
    assert "fixture-complete-v0" not in lowered
    assert "atlas-reading-metadata" not in lowered


def test_real_atlas_expert_keeps_professional_research_and_system_context() -> None:
    markup = ManagerGUIApp().render("/?view=atlas&fixture=complete&mode=expert&lang=en")
    document = parse_html(markup)
    visible = " ".join(surface.text for surface in document.visible_text)

    assert "Expert research content" in visible
    assert "Snapshot" in visible
    assert "fixture-complete-v0" in visible
    assert "Research content" in visible


def test_real_atlas_reader_and_expert_share_research_fields_from_one_model() -> None:
    model = ManagerReadModel(
        data=cast(
            JSONValue,
            {
                "research_object": "Shared research topic",
                "research_question": "Shared research question",
                "research_process": "Shared research process",
                "research_result": "Shared research result",
                "research_scope": "Shared research scope",
                "research_gaps": [{"title": "Shared research unknown"}],
                "records": [
                    {
                        "id": "shared-record",
                        "record_type": "campaign",
                        "title": "Shared research record",
                        "research_gaps": [{"title": "Record-level unknown"}],
                    }
                ],
            },
        ),
        source_refs=(),
        as_of=None,
        snapshot_token=None,
        derivation=Derivation(kind="direct", version="v1"),
        availability=Availability(status=ReadModelStatus.KNOWN, complete=True),
    )

    class OwnerProvider:
        def read(self, resource: str = "atlas", *, snapshot_token: str | None = None):
            del resource, snapshot_token
            return model

    app = ManagerGUIApp(OwnerProvider())
    reader = " ".join(surface.text for surface in parse_html(
        app.render("/?view=atlas&mode=reader&lang=en")
    ).visible_text)
    expert = " ".join(surface.text for surface in parse_html(
        app.render("/?view=atlas&mode=expert&lang=en")
    ).visible_text)

    for field in (
        "Shared research topic",
        "Shared research question",
        "Shared research process",
        "Shared research result",
        "Shared research scope",
        "Shared research unknown",
        "Record-level unknown",
    ):
        assert field in reader
        assert field in expert
