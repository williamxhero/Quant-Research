"""Read-only Research Story view model and three-mode renderer.

The module is deliberately page-local: it consumes a ``ManagerReadModel`` and
returns an HTML fragment that a shared shell can mount at the
``research-story-view`` hook.  It never reads storage, calls a provider, or
turns missing source metadata into a guessed URL.
"""

# HTML fragment strings intentionally keep readable markup even when a line is long.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from html import escape
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..fixtures import FixtureState, build_fixture
from ..models import ManagerReadModel, ReadModelStatus, SourceReference
from .i18n import Translator
from .i18n.catalog import l3_atlas_story as _l3_atlas_story_catalog
from .status import render_status_block


class StoryMode(StrEnum):
    """The three stable reading modes exposed by a Research Story."""

    NARRATIVE = "narrative"
    EVIDENCE = "evidence"
    TIMELINE = "timeline"


class StoryOutcome(StrEnum):
    """Outcome values are intentionally not collapsed into one success flag."""

    SUCCESS = "success"
    FAILURE = "failure"
    BLOCKED = "blocked"
    NOT_EVALUATED = "not_evaluated"
    INCOMPARABLE = "incomparable"


class EvidenceState(StrEnum):
    """Evidence state shown for each story fact or entry point."""

    KNOWN = "known"
    DERIVED = "derived"
    INTERPRETED = "interpreted"
    MISSING = "missing"
    UNCONFIRMED = "unconfirmed"
    BLOCKED = "blocked"
    STALE = "stale"
    INCOMPARABLE = "incomparable"


@dataclass(frozen=True, slots=True)
class StoryRoot:
    """Stable campaign/study/strategy-family identity for one story."""

    campaign_id: str | None = None
    campaign_label: str | None = None
    study_id: str | None = None
    study_label: str | None = None
    strategy_family_id: str | None = None
    strategy_family_label: str | None = None

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.campaign_id,
                self.campaign_label,
                self.study_id,
                self.study_label,
                self.strategy_family_id,
                self.strategy_family_label,
            )
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "campaign_id": self.campaign_id,
            "campaign_label": self.campaign_label,
            "study_id": self.study_id,
            "study_label": self.study_label,
            "strategy_family_id": self.strategy_family_id,
            "strategy_family_label": self.strategy_family_label,
        }


@dataclass(frozen=True, slots=True)
class StoryLink:
    """A link backed by an explicit source locator, or an explicit missing link."""

    kind: str
    label: str | None
    target: str | None
    source_id: str | None = None
    label_key: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.target)

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "kind": self.kind,
            "label": self.label,
            "label_key": self.label_key,
            "target": self.target,
            "source_id": self.source_id,
            "available": self.available,
        }


@dataclass(frozen=True, slots=True)
class StoryEntry:
    """One source-backed (or explicitly source-missing) story entry."""

    chapter_key: str
    entry_key: str
    title: str | None
    summary: str | None
    outcome: StoryOutcome
    evidence_state: str
    record_id: str | None
    event_time: str | None
    known_at: str | None
    links: tuple[StoryLink, ...]
    raw: Mapping[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "chapter_key": self.chapter_key,
            "entry_key": self.entry_key,
            "title": self.title,
            "summary": self.summary,
            "outcome": self.outcome.value,
            "evidence_state": self.evidence_state,
            "record_id": self.record_id,
            "event_time": self.event_time,
            "known_at": self.known_at,
            "links": [link.to_dict() for link in self.links],
        }


@dataclass(frozen=True, slots=True)
class StoryChapter:
    """A fixed-order Research Story chapter."""

    key: str
    label: str
    entries: tuple[StoryEntry, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "entries": [entry.to_dict() for entry in self.entries],
        }


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    """An event admitted to the timeline only when its source time is explicit."""

    event_time: str
    category: str | None
    entry: StoryEntry


_CHAPTERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("intent", "label.story.chapter.intent", ("intent", "purpose", "research_purpose")),
    (
        "initial_hypothesis",
        "label.story.chapter.initial_hypothesis",
        ("initial_hypothesis", "hypothesis"),
    ),
    (
        "research_design",
        "label.story.chapter.research_design",
        ("research_design", "design", "methodology"),
    ),
    ("attempts", "label.story.chapter.attempts", ("attempts", "runs", "trials")),
    (
        "evidence",
        "label.story.chapter.evidence",
        ("evidence", "evidence_entries", "evidence_entry_points"),
    ),
    ("conclusions", "label.story.chapter.conclusions", ("conclusions", "decisions")),
    ("failures", "label.story.chapter.failures", ("failures", "limitations")),
    (
        "follow_up",
        "label.story.chapter.follow_up",
        ("follow_up", "followup", "evolution", "next_steps"),
    ),
)

_OUTCOME_ALIASES = {
    "success": StoryOutcome.SUCCESS,
    "succeeded": StoryOutcome.SUCCESS,
    "pass": StoryOutcome.SUCCESS,
    "passed": StoryOutcome.SUCCESS,
    "ok": StoryOutcome.SUCCESS,
    "failure": StoryOutcome.FAILURE,
    "failed": StoryOutcome.FAILURE,
    "error": StoryOutcome.FAILURE,
    "blocked": StoryOutcome.BLOCKED,
    "not_evaluated": StoryOutcome.NOT_EVALUATED,
    "not-evaluated": StoryOutcome.NOT_EVALUATED,
    "not evaluated": StoryOutcome.NOT_EVALUATED,
    "unevaluated": StoryOutcome.NOT_EVALUATED,
    "incomparable": StoryOutcome.INCOMPARABLE,
}
_EVIDENCE_ALIASES = {
    "known": EvidenceState.KNOWN.value,
    "direct": EvidenceState.KNOWN.value,
    "derived": EvidenceState.DERIVED.value,
    "interpreted": EvidenceState.INTERPRETED.value,
    "missing": EvidenceState.MISSING.value,
    "unconfirmed": EvidenceState.UNCONFIRMED.value,
    "blocked": EvidenceState.BLOCKED.value,
    "stale": EvidenceState.STALE.value,
    "incomparable": EvidenceState.INCOMPARABLE.value,
}


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _first_text(item: Mapping[str, object], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = _text(item.get(key))
        if value is not None:
            return value
    return None


def _nested_text(item: Mapping[str, object], keys: Iterable[str]) -> str | None:
    """Read explicitly named temporal fields, including one context object."""

    direct = _first_text(item, keys)
    if direct is not None:
        return direct
    for context_key in ("temporal", "context", "provenance", "source"):
        nested = _mapping(item.get(context_key))
        if nested is not None:
            value = _first_text(nested, keys)
            if value is not None:
                return value
    return None


def _normalise(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _outcome(item: Mapping[str, object]) -> StoryOutcome:
    raw = _first_text(item, ("outcome", "outcome_state", "result", "result_state"))
    if raw is None:
        candidate = _first_text(item, ("status", "state"))
        if candidate is not None and _normalise(candidate) in _OUTCOME_ALIASES:
            raw = candidate
    return _OUTCOME_ALIASES.get(_normalise(raw or ""), StoryOutcome.NOT_EVALUATED)


def _explicit_evidence_state(
    item: Mapping[str, object], *, has_source_ids: bool, has_resolved_links: bool
) -> str:
    raw = _first_text(item, ("evidence_state", "evidence_status"))
    if raw is not None:
        normalised = _normalise(raw)
        return _EVIDENCE_ALIASES.get(normalised, raw.strip())
    if has_resolved_links:
        return EvidenceState.KNOWN.value
    if has_source_ids:
        return EvidenceState.UNCONFIRMED.value
    return EvidenceState.MISSING.value


def _record_id(item: Mapping[str, object]) -> str | None:
    return _first_text(item, ("record_id", "recordId", "id", "uid", "key"))


def _entry_text(item: Mapping[str, object]) -> tuple[str | None, str | None]:
    title = _first_text(item, ("title", "name", "label", "heading"))
    summary = _first_text(
        item,
        (
            "summary",
            "description",
            "text",
            "detail",
            "value",
            "message",
            "decision",
            "purpose",
            "hypothesis",
        ),
    )
    if title is None and summary is not None:
        title = summary[:120]
    return title, summary


def _sequence(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray)):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    if isinstance(value, Mapping):
        for key in ("items", "entries", "records", "values", "runs", "events"):
            candidate = value.get(key)
            if isinstance(candidate, Sequence) and not isinstance(
                candidate, (str, bytes, bytearray)
            ):
                return tuple(candidate)
        return (value,)
    return (value,)


def _source_id_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, Mapping):
        source_id = _first_text(value, ("source_id", "sourceId", "id", "record_id"))
        return (source_id,) if source_id else ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values: list[str] = []
        for entry in value:
            values.extend(_source_id_values(entry))
        return tuple(values)
    return ()


def _source_ids(item: Mapping[str, object]) -> tuple[str, ...]:
    values: list[str] = []
    for key in (
        "source_ref",
        "source_id",
        "source_ref_id",
        "sourceRef",
        "source_refs",
        "source_ids",
        "sources",
    ):
        values.extend(_source_id_values(item.get(key)))
    return tuple(dict.fromkeys(values))


_LINK_LABEL_KEYS = {
    "artifact": "label.story.link_kind.artifact",
    "lineage": "label.story.link_kind.lineage",
    "record": "label.story.link_kind.record",
    "report": "label.story.link_kind.report",
    "source": "label.story.link_kind.source",
}


def _link_label_key(kind: str) -> str:
    return _LINK_LABEL_KEYS.get(kind, "story.link_kind.unknown")


def _link_from_mapping(value: Mapping[str, object], *, default_kind: str) -> StoryLink:
    target = _first_text(value, ("href", "url", "locator", "target", "uri"))
    kind = _first_text(value, ("kind", "type")) or default_kind
    label = _first_text(value, ("label", "title", "name"))
    if label is None:
        label = _first_text(value, ("id",))
    source_id = _first_text(value, ("source_id", "source_ref", "id"))
    return StoryLink(
        kind=kind,
        label=label,
        target=target,
        source_id=source_id,
        label_key=None if label is not None else _link_label_key(kind),
    )


def _explicit_links(item: Mapping[str, object]) -> tuple[StoryLink, ...]:
    links: list[StoryLink] = []
    raw_links = item.get("links")
    if isinstance(raw_links, Mapping):
        for key, value in raw_links.items():
            if isinstance(value, Mapping):
                links.append(_link_from_mapping(value, default_kind=str(key)))
            else:
                target = _text(value)
                kind = str(key)
                links.append(
                    StoryLink(
                        kind,
                        None,
                        target,
                        label_key=_link_label_key(kind),
                    )
                )
    elif isinstance(raw_links, Sequence) and not isinstance(raw_links, (str, bytes, bytearray)):
        for value in raw_links:
            if isinstance(value, Mapping):
                links.append(_link_from_mapping(value, default_kind="source"))
    for key, kind in (
        ("artifact", "artifact"),
        ("artifact_ref", "artifact"),
        ("artifact_url", "artifact"),
        ("report", "report"),
        ("report_ref", "report"),
        ("report_url", "report"),
        ("lineage", "lineage"),
        ("lineage_ref", "lineage"),
        ("lineage_url", "lineage"),
        ("record_url", "record"),
        ("source_url", "source"),
    ):
        value = item.get(key)
        if isinstance(value, Mapping):
            links.append(_link_from_mapping(value, default_kind=kind))
        elif value is not None:
            links.append(
                StoryLink(
                    kind=kind,
                    label=None,
                    target=_text(value),
                    label_key=_link_label_key(kind),
                )
            )
    return tuple(links)


def _resolve_links(
    item: Mapping[str, object], source_refs: Mapping[str, SourceReference]
) -> tuple[StoryLink, ...]:
    source_ids = _source_ids(item)
    links: list[StoryLink] = []
    for source_id in source_ids:
        source = source_refs.get(source_id)
        if source is None:
            links.append(
                StoryLink(
                    "source",
                    None,
                    None,
                    source_id,
                    label_key="story.source_reference",
                )
            )
        else:
            links.append(StoryLink(source.kind, source.source_id, source.locator, source.source_id))
    links.extend(_explicit_links(item))
    unique: list[StoryLink] = []
    seen: set[tuple[str, str | None, str | None, str | None, str | None]] = set()
    for link in links:
        marker = (link.kind, link.label, link.label_key, link.target, link.source_id)
        if marker not in seen:
            seen.add(marker)
            unique.append(link)
    return tuple(unique)


def _root_identity(payload: Mapping[str, object], key: str) -> tuple[str | None, str | None]:
    value: object = payload.get(key)
    if value is None:
        root = _mapping(payload.get("root")) or _mapping(payload.get("story_root"))
        if root is not None:
            value = root.get(key)
    if value is None:
        aliases = {"strategy_family": ("strategyFamily", "family")}.get(key, ())
        for alias in aliases:
            value = payload.get(alias)
            if value is not None:
                break
    if isinstance(value, Mapping):
        identity = _first_text(value, ("id", "record_id", "uid", "key"))
        label = _first_text(value, ("title", "name", "label", "display_name"))
        return identity, label
    text = _text(value)
    return text, text


def _build_root(payload: Mapping[str, object]) -> StoryRoot:
    campaign_id, campaign_label = _root_identity(payload, "campaign")
    study_id, study_label = _root_identity(payload, "study")
    family_id, family_label = _root_identity(payload, "strategy_family")
    return StoryRoot(
        campaign_id=campaign_id,
        campaign_label=campaign_label,
        study_id=study_id,
        study_label=study_label,
        strategy_family_id=family_id,
        strategy_family_label=family_label,
    )


def _chapter_value(payload: Mapping[str, object], aliases: Sequence[str]) -> object:
    chapters = _mapping(payload.get("chapters"))
    for key in aliases:
        if key in payload:
            return payload[key]
        if chapters is not None and key in chapters:
            return chapters[key]
    return None


def _time(item: Mapping[str, object], keys: Sequence[str]) -> str | None:
    return _nested_text(item, keys)


class ResearchStoryViewModel:
    """Parsed Research Story with deterministic chapter order and source links."""

    def __init__(
        self,
        model: ManagerReadModel,
        *,
        mode: StoryMode | str = StoryMode.NARRATIVE,
        root: StoryRoot,
        chapters: tuple[StoryChapter, ...],
        timeline_events: tuple[TimelineEvent, ...],
    ) -> None:
        self.model = model
        self.mode = StoryMode(mode)
        self.root = root
        self.chapters = chapters
        self.timeline_events = timeline_events

    @classmethod
    def from_read_model(
        cls, model: ManagerReadModel, *, mode: StoryMode | str = StoryMode.NARRATIVE
    ) -> ResearchStoryViewModel:
        payload = _mapping(model.data)
        if payload is None:
            payload = {}
        source_refs = {source.source_id: source for source in model.source_refs}
        root = _build_root(payload)
        chapters: list[StoryChapter] = []
        all_entries: list[StoryEntry] = []
        for chapter_key, label_key, aliases in _CHAPTERS:
            entries: list[StoryEntry] = []
            for index, raw_value in enumerate(_sequence(_chapter_value(payload, aliases)), start=1):
                if isinstance(raw_value, Mapping):
                    raw_item: Mapping[str, object] = raw_value
                else:
                    text = _text(raw_value)
                    raw_item = {"text": text} if text is not None else {}
                title, summary = _entry_text(raw_item)
                source_ids = _source_ids(raw_item)
                links = _resolve_links(raw_item, source_refs)
                entries.append(
                    StoryEntry(
                        chapter_key=chapter_key,
                        entry_key=_record_id(raw_item) or f"{chapter_key}-{index}",
                        title=title,
                        summary=summary,
                        outcome=_outcome(raw_item),
                        evidence_state=_explicit_evidence_state(
                            raw_item,
                            has_source_ids=bool(source_ids),
                            has_resolved_links=any(link.available for link in links),
                        ),
                        record_id=_record_id(raw_item),
                        event_time=_time(
                            raw_item,
                            ("source_event_time", "event_time", "occurred_at", "happened_at"),
                        ),
                        known_at=_time(
                            raw_item,
                            ("known_at", "system_known_at", "as_known_at", "recorded_at"),
                        ),
                        links=links,
                        raw=raw_item,
                    )
                )
            chapter = StoryChapter(chapter_key, label_key, tuple(entries))
            chapters.append(chapter)
            all_entries.extend(entries)

        timeline_events: list[TimelineEvent] = []
        for entry in all_entries:
            if entry.event_time is not None:
                category = _event_category(entry.raw) if entry.raw is not None else None
                timeline_events.append(TimelineEvent(entry.event_time, category, entry))

        extra_events = _chapter_value(payload, ("events", "timeline"))
        for index, raw_value in enumerate(_sequence(extra_events), start=1):
            if isinstance(raw_value, Mapping):
                raw_item = raw_value
            else:
                text = _text(raw_value)
                raw_item = {"text": text} if text is not None else {}
            event_time = _time(
                raw_item,
                ("source_event_time", "event_time", "occurred_at", "happened_at"),
            )
            if event_time is None:
                continue
            title, summary = _entry_text(raw_item)
            source_ids = _source_ids(raw_item)
            links = _resolve_links(raw_item, source_refs)
            entry = StoryEntry(
                chapter_key="events",
                entry_key=_record_id(raw_item) or f"events-{index}",
                title=title,
                summary=summary,
                outcome=_outcome(raw_item),
                evidence_state=_explicit_evidence_state(
                    raw_item,
                    has_source_ids=bool(source_ids),
                    has_resolved_links=any(link.available for link in links),
                ),
                record_id=_record_id(raw_item),
                event_time=event_time,
                known_at=_time(
                    raw_item,
                    ("known_at", "system_known_at", "as_known_at", "recorded_at"),
                ),
                links=links,
                raw=raw_item,
            )
            timeline_events.append(TimelineEvent(event_time, _event_category(raw_item), entry))
        timeline_events.sort(key=lambda event: (event.event_time, event.entry.entry_key))
        return cls(
            model,
            mode=mode,
            root=root,
            chapters=tuple(chapters),
            timeline_events=tuple(timeline_events),
        )

    @classmethod
    def parse(
        cls, model: ManagerReadModel, *, mode: StoryMode | str = StoryMode.NARRATIVE
    ) -> ResearchStoryViewModel:
        """Alias used by page integrations that call parsed read models ``parse``."""

        return cls.from_read_model(model, mode=mode)

    @property
    def status(self) -> ReadModelStatus:
        return self.model.availability.status

    @property
    def entries(self) -> tuple[StoryEntry, ...]:
        return tuple(entry for chapter in self.chapters for entry in chapter.entries)

    def with_mode(self, mode: StoryMode | str) -> ResearchStoryViewModel:
        return ResearchStoryViewModel.from_read_model(self.model, mode=mode)

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "root": self.root.to_dict(),
            "chapters": [chapter.to_dict() for chapter in self.chapters],
            "timeline_events": [
                {
                    "event_time": event.event_time,
                    "category": event.category,
                    "entry_key": event.entry.entry_key,
                }
                for event in self.timeline_events
            ],
            "availability": self.model.availability.to_dict(),
        }

    def context_url(
        self,
        mode: StoryMode | str,
        *,
        base_path: str = "/?view=stories",
        query: Mapping[str, object] | str | None = None,
    ) -> str:
        """Build a stable mode link while preserving the story root and filters."""

        selected = StoryMode(mode)
        parsed = urlsplit(base_path)
        values: dict[str, str] = {
            key: value for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        }
        if isinstance(query, str):
            query_string = (
                urlsplit(query).query if "?" in query or "://" in query else query.lstrip("?")
            )
            values.update({key: value for key, value in parse_qsl(query_string, keep_blank_values=True)})
        elif query is not None:
            for key, value in query.items():
                if value is not None:
                    values[str(key)] = str(value)
        values["view"] = values.get("view", "stories")
        values["mode"] = selected.value
        root_values = {
            "campaign": self.root.campaign_id,
            "study": self.root.study_id,
            "strategy_family": self.root.strategy_family_id,
        }
        for key, value in root_values.items():
            if value:
                values[key] = value
        query_string = urlencode(sorted(values.items()))
        return urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path or "/", query_string, parsed.fragment)
        )

    def render(
        self,
        *,
        base_path: str = "/?view=stories",
        query: Mapping[str, object] | str | None = None,
        translator: Translator | None = None,
    ) -> str:
        """Render a mountable, accessible HTML fragment for the selected mode."""

        selected_translator = translator or Translator()
        fixture = _is_fixture(self.model, "stories")
        root_label = _root_label(self.root)
        heading = _display_text(
            root_label, "story.root_unavailable", translator=selected_translator, fixture=fixture
        )
        mode_links = "".join(
            (
                f'<a class="story-mode-link" data-story-mode="{mode.value}" '
                f'aria-current="{"page" if mode is self.mode else "false"}" '
                f'href="{escape(self.context_url(mode, base_path=base_path, query=query), quote=True)}">'
                f'{selected_translator.label("story.mode", mode.value)}</a>'
            )
            for mode in StoryMode
        )
        sections = {
            StoryMode.NARRATIVE: self._render_narrative(translator=selected_translator, fixture=fixture),
            StoryMode.EVIDENCE: self._render_evidence(translator=selected_translator, fixture=fixture),
            StoryMode.TIMELINE: self._render_timeline(translator=selected_translator, fixture=fixture),
        }
        return (
            f'<section class="research-story" data-integration-hook="research-story-view" '
            f'data-story-mode="{self.mode.value}" '
            f'data-story-root="{escape(root_label or "", quote=True)}">'
            f'<header class="research-story-header"><p class="eyebrow">'
            f'{escape(selected_translator.t("story.eyebrow"))}</p>'
            f'<h1 class="page-title" data-page-title tabindex="-1">{heading}</h1>'
            f'{_render_root_context(self.root, translator=selected_translator, fixture=fixture)}'
            f'<nav class="story-mode-nav" '
            f'aria-label="{escape(selected_translator.t("story.mode.aria"), quote=True)}">'
            f'{mode_links}</nav></header>'
            f"{render_status_block(_fixture_status_copy(self.model, selected_translator) if fixture else self.model, translator=selected_translator)}"
            f'<div class="research-story-content">{sections[self.mode]}</div>'
            f"</section>"
        )

    def _render_narrative(self, *, translator: Translator, fixture: bool) -> str:
        chapters = "".join(
            _render_narrative_chapter(chapter, translator=translator, fixture=fixture)
            for chapter in self.chapters
        )
        return f'<div class="story-narrative" data-reading-mode="narrative">{chapters}</div>'

    def _render_evidence(self, *, translator: Translator, fixture: bool) -> str:
        rows = "".join(
            _render_evidence_row(entry, translator=translator, fixture=fixture)
            for entry in self.entries
        )
        if not rows:
            return (
                '<div class="story-empty" data-evidence-state="missing">'
                f'{escape(translator.t("story.evidence.empty"))}</div>'
            )
        headers = "".join(
            f'<th scope="col">{escape(translator.t(f"story.evidence.{key}"))}</th>'
            for key in ("chapter_fact", "state", "record_id", "source_refs", "event_time", "known_at", "links")
        )
        return (
            '<div class="story-evidence" data-reading-mode="evidence">'
            f'<table><caption>{escape(translator.t("story.evidence.caption"))}</caption>'
            f'<thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div>'
        )

    def _render_timeline(self, *, translator: Translator, fixture: bool) -> str:
        if not self.timeline_events:
            return (
                '<div class="story-empty" data-timeline-state="missing">'
                f'{escape(translator.t("story.timeline.empty"))}</div>'
            )
        events = "".join(
            _render_timeline_event(event, translator=translator, fixture=fixture)
            for event in self.timeline_events
        )
        return (
            '<div class="story-timeline" data-reading-mode="timeline">'
            f'<p class="timeline-note">{escape(translator.t("story.timeline.note"))}</p>'
            f'<ol aria-label="{escape(translator.t("story.timeline.aria"), quote=True)}">'
            f'{events}</ol></div>'
        )


def _root_label(root: StoryRoot) -> str | None:
    for value in (
        root.campaign_label,
        root.study_label,
        root.strategy_family_label,
        root.campaign_id,
        root.study_id,
        root.strategy_family_id,
    ):
        if value:
            return value
    return None


def _is_fixture(model: ManagerReadModel, resource: str) -> bool:
    # Never translate owner prose merely because its ID, locator or text resembles
    # a fixture. The entire immutable envelope must match the shipped builder.
    if not (model.snapshot_token or "").startswith("fixture-") and model.data != {}:
        return False
    return any(model == build_fixture(state, resource=resource) for state in FixtureState)


def _fixture_status_copy(model: ManagerReadModel, translator: Translator) -> ManagerReadModel:
    def text(value: str | None) -> str | None:
        key = _l3_atlas_story_catalog.FIXTURE_KEYS.get(value or "")
        return translator.t(key) if key else value

    return replace(
        model,
        availability=replace(model.availability, reason=text(model.availability.reason)),
        errors=tuple(replace(error, message=text(error.message) or "") for error in model.errors),
    )


def _display_text(
    value: str | None,
    fallback_key: str,
    *,
    translator: Translator,
    fixture: bool,
) -> str:
    if value is None:
        return escape(translator.t(fallback_key))
    fixture_key = _l3_atlas_story_catalog.FIXTURE_KEYS.get(value) if fixture else None
    if fixture_key is not None:
        return escape(translator.t(fixture_key))
    return f'<span data-owner-text="true">{translator.source_text(value)}</span>'


def _render_root_context(
    root: StoryRoot, *, translator: Translator, fixture: bool
) -> str:
    values = (
        ("campaign", root.campaign_id, root.campaign_label),
        ("study", root.study_id, root.study_label),
        ("strategy_family", root.strategy_family_id, root.strategy_family_label),
    )
    items: list[str] = []
    for key, identifier, display in values:
        identifier_markup = (
            f'<span translate="no">{translator.source_text(identifier)}</span>'
            if identifier
            else escape(translator.t("story.missing"))
        )
        display_markup = (
            " · " + _display_text(display, "story.missing", translator=translator, fixture=fixture)
            if display and display != identifier
            else ""
        )
        items.append(
            f'<div class="story-root-item"><dt>{escape(translator.t(f"label.story.root.{key}"))}</dt>'
            f'<dd>{identifier_markup}{display_markup}</dd></div>'
        )
    return f'<dl class="story-root-context">{"".join(items)}</dl>'


def _render_outcome(outcome: StoryOutcome, *, translator: Translator) -> str:
    return (
        f'<span class="story-outcome outcome-{outcome.value}" data-outcome="{outcome.value}">'
        f'{translator.label("story.outcome", outcome.value)}</span>'
    )


def _render_evidence_state(state: str, *, translator: Translator) -> str:
    return (
        f'<span class="evidence-state evidence-{escape(state)}" '
        f'data-evidence-state="{escape(state)}">'
        f'{translator.label("story.evidence_state", state)}</span>'
    )


def _render_link_label(link: StoryLink, *, translator: Translator) -> str:
    if link.label is not None:
        label = f'<span data-owner-text="true">{translator.source_text(link.label)}</span>'
        kind = f'<span data-owner-text="true">{translator.source_text(link.kind)}</span>'
    elif link.label_key == "story.source_reference":
        label = translator.html(link.label_key, source_id=link.source_id or "")
        kind = translator.label("story.link_kind", link.kind)
    else:
        key = link.label_key or _link_label_key(link.kind)
        label = escape(translator.t(key, kind=link.kind))
        kind = translator.label("story.link_kind", link.kind)
    return f"{label} [{kind}]"


def _render_links(links: Sequence[StoryLink], *, translator: Translator) -> str:
    if not links:
        return f'<span class="source-missing">{escape(translator.t("story.source_missing"))}</span>'
    rendered: list[str] = []
    for link in links:
        label = _render_link_label(link, translator=translator)
        if link.target:
            rendered.append(
                f'<a class="source-link" data-link-kind="{escape(link.kind, quote=True)}" '
                f'href="{escape(link.target, quote=True)}">{label}</a>'
            )
        else:
            rendered.append(
                f'<span class="source-link-unconfirmed" data-link-kind="{escape(link.kind, quote=True)}">'
                f'{label} — {escape(translator.t("story.link.missing"))}</span>'
            )
    return '<span class="story-links">' + " · ".join(rendered) + "</span>"


def _render_temporal(entry: StoryEntry, *, translator: Translator) -> str:
    if entry.event_time and entry.known_at:
        key = "story.temporal.both"
    elif entry.event_time:
        key = "story.temporal.event_only"
    elif entry.known_at:
        key = "story.temporal.known_only"
    else:
        return escape(translator.t("story.temporal.none"))
    return translator.html(
        key,
        event_time=entry.event_time or "",
        known_at=entry.known_at or "",
    )


def _owner_or_catalog(
    value: str | None, key: str, *, translator: Translator, fixture: bool
) -> str:
    return _display_text(value, key, translator=translator, fixture=fixture)


def _render_narrative_chapter(
    chapter: StoryChapter, *, translator: Translator, fixture: bool
) -> str:
    if not chapter.entries:
        body = f'<p class="chapter-empty">{escape(translator.t("story.chapter.empty"))}</p>'
    else:
        entries: list[str] = []
        for entry in chapter.entries:
            entries.append(
                f'<article class="story-entry outcome-{entry.outcome.value}" data-entry-key="{escape(entry.entry_key, quote=True)}">'
                f'<div class="story-entry-heading"><h3>{_owner_or_catalog(entry.title, "story.entry.title_missing", translator=translator, fixture=fixture)}</h3>'
                f'{_render_outcome(entry.outcome, translator=translator)}</div>'
                f'<p>{_owner_or_catalog(entry.summary, "story.entry.summary_missing", translator=translator, fixture=fixture)}</p>'
                f'<p class="story-entry-meta"><span>{translator.html("story.record_id", record_id=entry.record_id or translator.t("story.missing"))}</span> '
                f'{_render_evidence_state(entry.evidence_state, translator=translator)}</p>'
                f'<p class="story-entry-temporal">{_render_temporal(entry, translator=translator)}</p>'
                f'<p class="story-entry-sources">{_render_links(entry.links, translator=translator)}</p></article>'
            )
        body = "".join(entries)
    return (
        f'<section class="story-chapter" data-chapter="{chapter.key}">'
        f'<h2>{escape(translator.t(chapter.label))}</h2>{body}</section>'
    )


def _render_evidence_row(
    entry: StoryEntry, *, translator: Translator, fixture: bool
) -> str:
    record_id = (
        f'<span translate="no">{translator.source_text(entry.record_id)}</span>'
        if entry.record_id
        else escape(translator.t("story.missing"))
    )
    event_time = (
        f'<time translate="no">{translator.source_text(entry.event_time)}</time>'
        if entry.event_time
        else escape(translator.t("story.missing"))
    )
    known_at = (
        f'<time translate="no">{translator.source_text(entry.known_at)}</time>'
        if entry.known_at
        else escape(translator.t("story.missing"))
    )
    source_links = _render_links(entry.links, translator=translator)
    title = _owner_or_catalog(
        entry.title, "story.entry.title_missing", translator=translator, fixture=fixture
    )
    return (
        f'<tr data-entry-key="{escape(entry.entry_key, quote=True)}" data-outcome="{entry.outcome.value}">'
        f'<th scope="row">{escape(translator.t(f"label.story.chapter.{entry.chapter_key}"))} / {title}<br>'
        f'{_render_outcome(entry.outcome, translator=translator)}</th>'
        f'<td>{_render_evidence_state(entry.evidence_state, translator=translator)}</td>'
        f'<td>{record_id}</td><td>{source_links}</td>'
        f'<td>{event_time}</td><td>{known_at}</td><td>{source_links}</td></tr>'
    )


def _render_timeline_event(
    event: TimelineEvent, *, translator: Translator, fixture: bool
) -> str:
    entry = event.entry
    category = (
        f'<span data-owner-text="true">{translator.source_text(event.category)}</span>'
        if event.category
        else escape(translator.t("story.timeline.default_category"))
    )
    return (
        f'<li class="timeline-event outcome-{entry.outcome.value}" data-event-time="{escape(event.event_time, quote=True)}" '
        f'data-event-category="{escape(event.category or "source_event", quote=True)}">'
        f'<time translate="no" datetime="{escape(event.event_time, quote=True)}">'
        f'{translator.source_text(event.event_time)}</time> '
        f'<span class="timeline-category">{category}</span> '
        f'<strong>{_owner_or_catalog(entry.title, "story.entry.title_missing", translator=translator, fixture=fixture)}</strong> '
        f'{_render_outcome(entry.outcome, translator=translator)}'
        f'<p>{_owner_or_catalog(entry.summary, "story.entry.summary_missing", translator=translator, fixture=fixture)}</p>'
        f'<p>{_render_links(entry.links, translator=translator)}</p></li>'
    )


def _event_category(item: Mapping[str, object]) -> str | None:
    return _first_text(item, ("event_category", "event_type", "category", "type", "kind"))


def render_research_story(
    model: ManagerReadModel,
    *,
    mode: StoryMode | str = StoryMode.NARRATIVE,
    base_path: str = "/?view=stories",
    query: Mapping[str, object] | str | None = None,
    translator: Translator | None = None,
) -> str:
    """Integration hook for ``app.py`` and future shells.

    T5 can mount this returned fragment at the existing
    ``data-integration-hook=research-story-view`` surface.  The shell only
    needs to pass its already-read ``ManagerReadModel``; it does not need to
    duplicate parsing, mode handling, source links, or status rendering.
    """

    return ResearchStoryViewModel.from_read_model(model, mode=mode).render(
        base_path=base_path, query=query, translator=translator
    )


# Explicit aliases make the integration seam discoverable without coupling the
# shared web package's __init__ export list to this page-local module.
render_research_story_view = render_research_story
research_story_hook = render_research_story


__all__ = [
    "EvidenceState",
    "ResearchStoryViewModel",
    "StoryChapter",
    "StoryEntry",
    "StoryLink",
    "StoryMode",
    "StoryOutcome",
    "StoryRoot",
    "TimelineEvent",
    "render_research_story",
    "render_research_story_view",
    "research_story_hook",
]
