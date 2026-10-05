"""Focused Research Story tests for S1-T4."""

from __future__ import annotations

from html import escape
from typing import cast

from manager_gui import (
    Availability,
    Derivation,
    ManagerReadModel,
    ReadModelStatus,
    SourceReference,
    fixture_provider,
)
from manager_gui.models import JSONValue
from manager_gui.testing.i18n import (
    assert_accessible,
    assert_dom_equivalent,
    assert_lang_propagation,
    assert_language_text,
    assert_owner_text_escaped,
    parse_html,
)
from manager_gui.web.i18n import Locale, Translator
from manager_gui.web.research_story import (
    ResearchStoryViewModel,
    StoryMode,
    StoryOutcome,
    render_research_story,
)


def _source(source_id: str, locator: str) -> SourceReference:
    return SourceReference(
        source_id=source_id,
        owner="research-ledger",
        kind="source-record",
        locator=locator,
        schema="research-story.v0",
        revision="r1",
    )


def _model(
    data: object, *, status: ReadModelStatus = ReadModelStatus.KNOWN, complete: bool = True
) -> ManagerReadModel:
    return ManagerReadModel(
        data=cast(JSONValue, data),
        source_refs=(
            _source("record-intent", "fixture://records/record-intent"),
            _source("record-run", "fixture://records/record-run"),
            _source("record-decision", "fixture://records/record-decision"),
        ),
        as_of="2026-10-03T12:00:00Z",
        snapshot_token="story-snapshot-1",
        derivation=Derivation(kind="direct", version="v0"),
        availability=Availability(
            status=status,
            complete=complete,
            reason="fixture story status",
            retryable=status is ReadModelStatus.API_UNAVAILABLE,
        ),
    )


def _complete_data() -> dict[str, object]:
    return {
        "campaign": {"id": "campaign-1", "title": "Momentum campaign"},
        "study": {"id": "study-1", "title": "Cross-sectional study"},
        "strategy_family": {"id": "family-1", "title": "Quality tilt"},
        "chapters": {
            "intent": {
                "record_id": "intent-1",
                "title": "Why test this?",
                "summary": "Test whether the signal survives costs.",
                "evidence_state": "known",
                "source_ref": "record-intent",
                "known_at": "2026-01-02T00:00:00Z",
            },
            "initial_hypothesis": [
                {
                    "record_id": "hypothesis-1",
                    "summary": "The signal should improve risk-adjusted returns.",
                    "outcome": "not_evaluated",
                    "source_ref": "record-intent",
                }
            ],
            "research_design": [{"title": "Frozen design", "summary": "Use the declared split."}],
            "attempts": [
                {
                    "record_id": "run-1",
                    "title": "Run one",
                    "summary": "The first run failed a data gate.",
                    "outcome": "failure",
                    "source_ref": "record-run",
                    "source_event_time": "2026-02-01T00:00:00Z",
                    "system_known_at": "2026-02-02T00:00:00Z",
                },
                {
                    "record_id": "run-2",
                    "title": "Run two",
                    "summary": "The rerun was blocked.",
                    "outcome": "blocked",
                    "source_event_time": "2026-02-03T00:00:00Z",
                },
            ],
            "evidence": [{"record_id": "evidence-1", "summary": "Cost-adjusted return table."}],
            "conclusions": [
                {
                    "record_id": "decision-1",
                    "summary": "Do not promote until the data gate is resolved.",
                    "outcome": "incomparable",
                    "source_ref": "record-decision",
                    "links": {"report": {"href": "fixture://reports/decision-1"}},
                }
            ],
            "failures": [{"title": "Data gate", "summary": "A required input was unavailable."}],
            "follow_up": [
                {"title": "Next step", "summary": "Re-run after data repair.", "outcome": "success"}
            ],
        },
    }


def test_complete_story_has_all_chapters_and_root_context() -> None:
    view = ResearchStoryViewModel.from_read_model(_model(_complete_data()))

    assert view.root.campaign_id == "campaign-1"
    assert [chapter.key for chapter in view.chapters] == [
        "intent",
        "initial_hypothesis",
        "research_design",
        "attempts",
        "evidence",
        "conclusions",
        "failures",
        "follow_up",
    ]
    assert {entry.outcome for entry in view.entries} >= {
        StoryOutcome.SUCCESS,
        StoryOutcome.FAILURE,
        StoryOutcome.BLOCKED,
        StoryOutcome.NOT_EVALUATED,
        StoryOutcome.INCOMPARABLE,
    }
    narrative = view.render(translator=Translator(Locale.EN))
    for chapter in view.chapters:
        assert f'data-chapter="{chapter.key}"' in narrative
    assert "Momentum campaign" in narrative
    assert "fixture://records/record-intent" in narrative
    assert 'Record ID: <span translate="no">intent-1</span>' in narrative


def test_all_modes_preserve_root_and_filter_context() -> None:
    model = _model(_complete_data())
    view = ResearchStoryViewModel.from_read_model(model)

    for mode in StoryMode:
        rendered = render_research_story(
            model,
            mode=mode,
            base_path="/manager?view=stories&q=gate",
            query={"tab": "current"},
            translator=Translator(Locale.EN),
        )
        assert f'data-story-mode="{mode.value}"' in rendered
        assert f'data-story-mode="{mode.value}" aria-current="page"' in rendered or (
            f'data-story-mode="{mode.value}" aria-current="false"' in rendered
        )
        assert "campaign-1" in rendered
        assert "study-1" in rendered
        assert "q=gate" in rendered
        assert "tab=current" in rendered

    assert (
        "Only explicit source event times are shown"
        in view.with_mode(StoryMode.TIMELINE).render(translator=Translator(Locale.EN))
    )


def test_timeline_uses_only_explicit_source_event_times() -> None:
    view = ResearchStoryViewModel.from_read_model(_model(_complete_data()), mode=StoryMode.TIMELINE)

    timeline = view.render(translator=Translator(Locale.EN))
    assert 'data-event-time="2026-02-01T00:00:00Z"' in timeline
    assert 'data-event-time="2026-02-03T00:00:00Z"' in timeline
    assert "Attempts / runs" not in timeline
    assert "2026-10-03T12:00:00Z" not in timeline
    assert "failed a data gate" in timeline


def test_missing_sources_and_distinct_outcomes_are_visible() -> None:
    data = {
        "campaign": "campaign-missing",
        "intent": [{"record_id": "unresolved", "summary": "No source ref", "outcome": "success"}],
        "conclusions": [
            {"summary": "Blocked conclusion", "outcome": "blocked", "source_ref": "does-not-exist"},
            {"summary": "No result", "outcome": "not_evaluated"},
        ],
    }
    rendered = render_research_story(
        _model(data), mode="evidence", translator=Translator(Locale.EN)
    )

    assert "Missing / Unconfirmed" in rendered
    assert 'data-outcome="success"' in rendered
    assert 'data-outcome="blocked"' in rendered
    assert 'data-outcome="not_evaluated"' in rendered
    assert 'data-evidence-state="missing"' in rendered
    assert 'data-evidence-state="unconfirmed"' in rendered
    assert "does-not-exist" in rendered


def test_empty_partial_blocked_and_api_unavailable_keep_shared_status_semantics() -> None:
    for status, complete, expected in (
        (ReadModelStatus.MISSING, False, 'data-display-state="empty"'),
        (ReadModelStatus.KNOWN, False, 'data-display-state="partial"'),
        (ReadModelStatus.BLOCKED, False, 'data-display-state="error"'),
        (ReadModelStatus.API_UNAVAILABLE, False, 'data-display-state="error"'),
    ):
        rendered = render_research_story(
            _model({}, status=status, complete=complete),
            mode=StoryMode.NARRATIVE,
            translator=Translator(Locale.EN),
        )
        assert f'data-status="{status.value}"' in rendered
        assert expected in rendered
        assert "No research material recorded" in rendered


def test_context_url_does_not_change_across_mode_switches_or_invent_source_urls() -> None:
    model = _model(_complete_data())
    view = ResearchStoryViewModel.from_read_model(model)

    narrative_url = view.context_url("narrative", base_path="/stories?view=stories&q=abc")
    evidence_url = view.context_url("evidence", base_path="/stories?view=stories&q=abc")
    assert "campaign=campaign-1" in narrative_url
    assert "campaign=campaign-1" in evidence_url
    assert "study=study-1" in evidence_url
    assert "strategy_family=family-1" in evidence_url
    assert "q=abc" in evidence_url
    assert "mode=narrative" in narrative_url
    assert "mode=evidence" in evidence_url
    assert "https://" not in render_research_story(model)


def test_story_localizes_each_mode_and_preserves_machine_context_in_zh_and_en() -> None:
    model = _model(_complete_data())
    owner_text = (
        "Momentum campaign",
        "Cross-sectional study",
        "Quality tilt",
        "Why test this?",
        "Test whether the signal survives costs.",
        "The signal should improve risk-adjusted returns.",
        "Frozen design",
        "Use the declared split.",
        "Run one",
        "The first run failed a data gate.",
        "Run two",
        "The rerun was blocked.",
        "Cost-adjusted return table.",
        "Do not promote until the data gate is resolved.",
        "Data gate",
        "A required input was unavailable.",
        "Next step",
        "Re-run after data repair.",
    )
    zh = render_research_story(
        model,
        mode=StoryMode.NARRATIVE,
        base_path="/?view=stories&lang=zh-CN&fixture=complete",
        query="/?view=stories&lang=zh-CN&fixture=complete&q=gate",
        translator=Translator(Locale.ZH_CN, strict=True),
    )
    en = render_research_story(
        model,
        mode=StoryMode.NARRATIVE,
        base_path="/?view=stories&lang=en&fixture=complete",
        query="/?view=stories&lang=en&fixture=complete&q=gate",
        translator=Translator(Locale.EN, strict=True),
    )

    assert "研究故事" in zh
    assert "意图与目的" in zh
    assert "叙事" in zh
    assert "Research Story" in en
    assert "Intent / purpose" in en
    evidence_en = render_research_story(
        model, mode=StoryMode.EVIDENCE, translator=Translator(Locale.EN, strict=True)
    )
    assert "Evidence state" in evidence_en
    assert 'data-story-mode="narrative"' in zh
    assert 'data-story-mode="evidence"' in en
    assert "mode=narrative" in zh and "lang=zh-CN" in zh
    assert "mode=evidence" in en and "lang=en" in en
    assert "Record ID" not in zh
    assert "研究活动" not in en

    assert_dom_equivalent(zh, en)
    assert_language_text(zh, Locale.ZH_CN, owner_text=owner_text)
    assert_language_text(en, Locale.EN, owner_text=owner_text)
    assert_lang_propagation(zh, Locale.ZH_CN)
    assert_lang_propagation(en, Locale.EN)
    assert_accessible(zh, owner_text=owner_text)
    assert_accessible(en, owner_text=owner_text)


def test_story_view_model_stores_catalog_keys_not_generated_gui_prose() -> None:
    view = ResearchStoryViewModel.from_read_model(_model(_complete_data()))
    payload = view.to_dict()
    chapters = cast(list[dict[str, object]], payload["chapters"])
    timeline_events = cast(list[dict[str, object]], payload["timeline_events"])

    assert all(str(chapter["label"]).startswith("label.story.chapter.") for chapter in chapters)
    assert all("Intent / purpose" not in str(chapter) for chapter in chapters)
    assert all("Source event" not in str(event) for event in timeline_events)
    generated_links = [
        link
        for entry in view.entries
        for link in entry.links
        if link.label is None
    ]
    assert generated_links
    assert all(link.label_key for link in generated_links)


def test_story_complete_fixture_has_localized_display_copy_but_keeps_payload_data() -> None:
    model = fixture_provider("complete").read("stories")
    view = ResearchStoryViewModel.from_read_model(model)
    zh = view.render(translator=Translator(Locale.ZH_CN, strict=True))
    en = view.render(translator=Translator(Locale.EN, strict=True))

    assert "样例研究活动" in zh
    assert "样例运行" in zh
    assert "Fixture campaign" in en
    assert "Fixture run" in en
    zh_visible = "".join(surface.text for surface in parse_html(zh).visible_text)
    assert "Fixture campaign" not in zh_visible
    assert "样例研究活动" not in "".join(surface.text for surface in parse_html(en).visible_text)
    story_data = cast(dict[str, object], model.data)
    campaign = cast(dict[str, object], story_data["campaign"])
    assert campaign["title"] == "Fixture campaign"
    assert model.to_json() == fixture_provider("complete").read("stories").to_json()


def test_story_owner_text_is_escaped_once_and_not_translated() -> None:
    owner_title = '<owner-title> & "quoted" {x} 中文'
    owner_summary = '<owner-summary> & "quoted" {x} 中文'
    data = {
        "campaign": {"id": "campaign-owner", "title": owner_title},
        "intent": [{"summary": owner_summary}],
    }
    markup = render_research_story(_model(data), translator=Translator(Locale.ZH_CN, strict=True))

    decoded = "".join(surface.text for surface in parse_html(markup).visible_text)
    assert decoded.count(owner_title) == 2
    assert decoded.count(owner_summary) == 2
    assert markup.count(escape(owner_title, quote=True)) == 3  # includes opaque data-story-root
    assert markup.count(escape(owner_summary, quote=True)) == 2
    assert "&amp;lt;owner-title" not in markup
    assert_owner_text_escaped(markup, owner_summary, expected_count=2)
    assert owner_title not in markup
    assert owner_summary not in markup
