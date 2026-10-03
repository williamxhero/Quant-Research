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
from dataclasses import dataclass
from enum import StrEnum
from html import escape
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..models import ManagerReadModel, ReadModelStatus, SourceReference
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
    label: str
    target: str | None
    source_id: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.target)

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "kind": self.kind,
            "label": self.label,
            "target": self.target,
            "source_id": self.source_id,
            "available": self.available,
        }


@dataclass(frozen=True, slots=True)
class StoryEntry:
    """One source-backed (or explicitly source-missing) story entry."""

    chapter_key: str
    entry_key: str
    title: str
    summary: str
    outcome: StoryOutcome
    evidence_state: str
    record_id: str | None
    event_time: str | None
    known_at: str | None
    links: tuple[StoryLink, ...]
    raw: Mapping[str, object] | None = None

    @property
    def temporal_boundary(self) -> str:
        """Describe explicit source/event versus system-known boundaries only."""

        if self.event_time and self.known_at:
            return f"Source event {self.event_time}; known at {self.known_at}."
        if self.event_time:
            return f"Source event {self.event_time}; known-at time unavailable."
        if self.known_at:
            return f"Known at {self.known_at}; source event time unavailable."
        return "Source event time and known-at time unavailable."

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
    category: str
    entry: StoryEntry


_CHAPTERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("intent", "Intent / purpose", ("intent", "purpose", "research_purpose")),
    (
        "initial_hypothesis",
        "Initial hypothesis",
        ("initial_hypothesis", "hypothesis"),
    ),
    (
        "research_design",
        "Research design",
        ("research_design", "design", "methodology"),
    ),
    ("attempts", "Attempts / runs", ("attempts", "runs", "trials")),
    (
        "evidence",
        "Evidence entry points",
        ("evidence", "evidence_entries", "evidence_entry_points"),
    ),
    ("conclusions", "Conclusions / decisions", ("conclusions", "decisions")),
    ("failures", "Failures / limitations", ("failures", "limitations")),
    ("follow_up", "Follow-up / evolution", ("follow_up", "followup", "evolution", "next_steps")),
)

_MODE_LABELS = {
    StoryMode.NARRATIVE: "Narrative",
    StoryMode.EVIDENCE: "Evidence",
    StoryMode.TIMELINE: "Timeline",
}
_OUTCOME_LABELS = {
    StoryOutcome.SUCCESS: "Success",
    StoryOutcome.FAILURE: "Failure",
    StoryOutcome.BLOCKED: "Blocked",
    StoryOutcome.NOT_EVALUATED: "Not evaluated",
    StoryOutcome.INCOMPARABLE: "Incomparable",
}
_EVIDENCE_LABELS = {
    EvidenceState.KNOWN.value: "Known",
    EvidenceState.DERIVED.value: "Derived",
    EvidenceState.INTERPRETED.value: "Interpreted",
    EvidenceState.MISSING.value: "Missing",
    EvidenceState.UNCONFIRMED.value: "Unconfirmed",
    EvidenceState.BLOCKED.value: "Blocked",
    EvidenceState.STALE.value: "Stale",
    EvidenceState.INCOMPARABLE.value: "Incomparable",
}
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


def _entry_text(item: Mapping[str, object]) -> tuple[str, str]:
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
    if title is None:
        title = "Record"
    if summary is None:
        summary = "Record available; no narrative text recorded."
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


def _link_from_mapping(value: Mapping[str, object], *, default_kind: str) -> StoryLink:
    target = _first_text(value, ("href", "url", "locator", "target", "uri"))
    label = _first_text(value, ("label", "title", "name", "kind", "id")) or default_kind.title()
    kind = _first_text(value, ("kind", "type")) or default_kind
    source_id = _first_text(value, ("source_id", "source_ref", "id"))
    return StoryLink(kind=kind, label=label, target=target, source_id=source_id)


def _explicit_links(item: Mapping[str, object]) -> tuple[StoryLink, ...]:
    links: list[StoryLink] = []
    raw_links = item.get("links")
    if isinstance(raw_links, Mapping):
        for key, value in raw_links.items():
            if isinstance(value, Mapping):
                links.append(_link_from_mapping(value, default_kind=str(key)))
            else:
                target = _text(value)
                links.append(StoryLink(str(key), str(key).replace("_", " ").title(), target))
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
            links.append(StoryLink(kind=kind, label=kind.title(), target=_text(value)))
    return tuple(links)


def _resolve_links(
    item: Mapping[str, object], source_refs: Mapping[str, SourceReference]
) -> tuple[StoryLink, ...]:
    source_ids = _source_ids(item)
    links: list[StoryLink] = []
    for source_id in source_ids:
        source = source_refs.get(source_id)
        if source is None:
            links.append(StoryLink("source", f"Source {source_id}", None, source_id))
        else:
            links.append(StoryLink(source.kind, source.source_id, source.locator, source.source_id))
    links.extend(_explicit_links(item))
    unique: list[StoryLink] = []
    seen: set[tuple[str, str, str | None, str | None]] = set()
    for link in links:
        marker = (link.kind, link.label, link.target, link.source_id)
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
        for chapter_key, label, aliases in _CHAPTERS:
            entries: list[StoryEntry] = []
            for index, raw_value in enumerate(_sequence(_chapter_value(payload, aliases)), start=1):
                if isinstance(raw_value, Mapping):
                    raw_item: Mapping[str, object] = raw_value
                else:
                    raw_item = {"text": _text(raw_value) or "Record available."}
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
            chapter = StoryChapter(chapter_key, label, tuple(entries))
            chapters.append(chapter)
            all_entries.extend(entries)

        timeline_events: list[TimelineEvent] = []
        for entry in all_entries:
            if entry.event_time is not None:
                category = _event_category(entry.raw) if entry.raw is not None else "Source event"
                timeline_events.append(TimelineEvent(entry.event_time, category, entry))

        extra_events = _chapter_value(payload, ("events", "timeline"))
        for index, raw_value in enumerate(_sequence(extra_events), start=1):
            if isinstance(raw_value, Mapping):
                raw_item = raw_value
            else:
                raw_item = {"text": _text(raw_value) or "Source event"}
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
            values.update({key: value for key, value in parse_qsl(query, keep_blank_values=True)})
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
        self, *, base_path: str = "/?view=stories", query: Mapping[str, object] | str | None = None
    ) -> str:
        """Render a mountable, accessible HTML fragment for the selected mode."""

        root_label = _root_label(self.root)
        mode_links = "".join(
            (
                f'<a class="story-mode-link" data-story-mode="{mode.value}" '
                f'aria-current="{"page" if mode is self.mode else "false"}" '
                f'href="{escape(self.context_url(mode, base_path=base_path, query=query), quote=True)}">'
                f"{escape(_MODE_LABELS[mode])}</a>"
            )
            for mode in StoryMode
        )
        sections = {
            StoryMode.NARRATIVE: self._render_narrative(),
            StoryMode.EVIDENCE: self._render_evidence(),
            StoryMode.TIMELINE: self._render_timeline(),
        }
        return (
            f'<section class="research-story" data-integration-hook="research-story-view" '
            f'data-story-mode="{self.mode.value}" data-story-root="{escape(root_label, quote=True)}">'
            f'<header class="research-story-header"><p class="eyebrow">Research Story</p>'
            f'<h1 class="page-title" data-page-title tabindex="-1">{escape(root_label)}</h1>{_render_root_context(self.root)}'
            f'<nav class="story-mode-nav" aria-label="Research Story reading mode">{mode_links}</nav></header>'
            f"{render_status_block(self.model)}"
            f'<div class="research-story-content">{sections[self.mode]}</div>'
            f"</section>"
        )

    def _render_narrative(self) -> str:
        chapters = "".join(_render_narrative_chapter(chapter) for chapter in self.chapters)
        return f'<div class="story-narrative" data-reading-mode="narrative">{chapters}</div>'

    def _render_evidence(self) -> str:
        rows = "".join(_render_evidence_row(entry) for entry in self.entries)
        if not rows:
            return (
                '<div class="story-empty" data-evidence-state="missing">'
                "No research facts or evidence entries are recorded. Missing / Unconfirmed."
                "</div>"
            )
        return (
            '<div class="story-evidence" data-reading-mode="evidence">'
            "<table><caption>Facts, evidence state, and provenance</caption>"
            '<thead><tr><th scope="col">Chapter / fact</th><th scope="col">Evidence state</th>'
            '<th scope="col">Record ID</th><th scope="col">Source refs</th>'
            '<th scope="col">Source event time</th><th scope="col">Known to system at</th>'
            '<th scope="col">Links</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div>"
        )

    def _render_timeline(self) -> str:
        if not self.timeline_events:
            return (
                '<div class="story-empty" data-timeline-state="missing">'
                "No source event times recorded; no phase transitions inferred."
                "</div>"
            )
        events = "".join(_render_timeline_event(event) for event in self.timeline_events)
        return (
            '<div class="story-timeline" data-reading-mode="timeline">'
            '<p class="timeline-note">Only explicit source event times are shown; GUI phase transitions are not inferred.</p>'
            f'<ol aria-label="Source event timeline">{events}</ol></div>'
        )


def _root_label(root: StoryRoot) -> str:
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
    return "Research Story (root unavailable)"


def _render_root_context(root: StoryRoot) -> str:
    values = (
        ("Campaign", root.campaign_id, root.campaign_label),
        ("Study", root.study_id, root.study_label),
        ("Strategy family", root.strategy_family_id, root.strategy_family_label),
    )
    items = "".join(
        f'<div class="story-root-item"><dt>{escape(label)}</dt><dd>'
        f"{escape(identifier or 'Missing / Unconfirmed')}"
        f"{f' · {escape(display)}' if display and display != identifier else ''}</dd></div>"
        for label, identifier, display in values
    )
    return f'<dl class="story-root-context">{items}</dl>'


def _render_outcome(outcome: StoryOutcome) -> str:
    return (
        f'<span class="story-outcome outcome-{outcome.value}" data-outcome="{outcome.value}">'
        f"{escape(_OUTCOME_LABELS[outcome])}</span>"
    )


def _render_evidence_state(state: str) -> str:
    label = _EVIDENCE_LABELS.get(state, state.replace("_", " ").title())
    return f'<span class="evidence-state evidence-{escape(state)}" data-evidence-state="{escape(state)}">{escape(label)}</span>'


def _render_links(links: Sequence[StoryLink]) -> str:
    if not links:
        return '<span class="source-missing">Missing / Unconfirmed source</span>'
    rendered: list[str] = []
    for link in links:
        label = f"{link.label} [{link.kind}]"
        if link.target:
            rendered.append(
                f'<a class="source-link" data-link-kind="{escape(link.kind, quote=True)}" '
                f'href="{escape(link.target, quote=True)}">{escape(label)}</a>'
            )
        else:
            rendered.append(
                f'<span class="source-link-unconfirmed" data-link-kind="{escape(link.kind, quote=True)}">'
                f"{escape(label)} — Missing / Unconfirmed</span>"
            )
    return '<span class="story-links">' + " · ".join(rendered) + "</span>"


def _render_narrative_chapter(chapter: StoryChapter) -> str:
    if not chapter.entries:
        body = '<p class="chapter-empty">No research material recorded for this chapter.</p>'
    else:
        entries: list[str] = []
        for entry in chapter.entries:
            record = escape(entry.record_id) if entry.record_id else "Missing / Unconfirmed"
            entries.append(
                f'<article class="story-entry outcome-{entry.outcome.value}" data-entry-key="{escape(entry.entry_key, quote=True)}">'
                f'<div class="story-entry-heading"><h3>{escape(entry.title)}</h3>{_render_outcome(entry.outcome)}'
                f"</div><p>{escape(entry.summary)}</p>"
                f'<p class="story-entry-meta"><span>Record ID: {record}</span> '
                f"{_render_evidence_state(entry.evidence_state)}</p>"
                f'<p class="story-entry-temporal">{escape(entry.temporal_boundary)}</p>'
                f'<p class="story-entry-sources">{_render_links(entry.links)}</p></article>'
            )
        body = "".join(entries)
    return (
        f'<section class="story-chapter" data-chapter="{chapter.key}">'
        f"<h2>{escape(chapter.label)}</h2>{body}</section>"
    )


def _render_evidence_row(entry: StoryEntry) -> str:
    record_id = escape(entry.record_id) if entry.record_id else "Missing / Unconfirmed"
    source_links = _render_links(entry.links)
    return (
        f'<tr data-entry-key="{escape(entry.entry_key, quote=True)}" data-outcome="{entry.outcome.value}">'
        f'<th scope="row">{escape(entry.chapter_key)} / {escape(entry.title)}<br>{_render_outcome(entry.outcome)}</th>'
        f"<td>{_render_evidence_state(entry.evidence_state)}</td>"
        f"<td>{record_id}</td><td>{source_links}</td>"
        f"<td>{escape(entry.event_time or 'Missing / Unconfirmed')}</td>"
        f"<td>{escape(entry.known_at or 'Missing / Unconfirmed')}</td><td>{source_links}</td></tr>"
    )


def _render_timeline_event(event: TimelineEvent) -> str:
    entry = event.entry
    return (
        f'<li class="timeline-event outcome-{entry.outcome.value}" data-event-time="{escape(event.event_time, quote=True)}" '
        f'data-event-category="{escape(event.category, quote=True)}">'
        f'<time datetime="{escape(event.event_time, quote=True)}">{escape(event.event_time)}</time> '
        f'<span class="timeline-category">{escape(event.category)}</span> '
        f"<strong>{escape(entry.title)}</strong> {_render_outcome(entry.outcome)}"
        f"<p>{escape(entry.summary)}</p><p>{_render_links(entry.links)}</p></li>"
    )


def _event_category(item: Mapping[str, object]) -> str:
    return (
        _first_text(item, ("event_category", "event_type", "category", "type", "kind"))
        or "Source event"
    )


def render_research_story(
    model: ManagerReadModel,
    *,
    mode: StoryMode | str = StoryMode.NARRATIVE,
    base_path: str = "/?view=stories",
    query: Mapping[str, object] | str | None = None,
) -> str:
    """Integration hook for ``app.py`` and future shells.

    T5 can mount this returned fragment at the existing
    ``data-integration-hook=research-story-view`` surface.  The shell only
    needs to pass its already-read ``ManagerReadModel``; it does not need to
    duplicate parsing, mode handling, source links, or status rendering.
    """

    return ResearchStoryViewModel.from_read_model(model, mode=mode).render(
        base_path=base_path, query=query
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
