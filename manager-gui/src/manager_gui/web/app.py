"""Server-side rendering for the fixture-backed Manager GUI shell."""

# The HTML document is intentionally readable as a single template; its markup
# lines are longer than the Python package's normal line-length budget.
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass, replace
from html import escape
from urllib.parse import parse_qs, urlencode, urlsplit

from ..fixtures import FixtureState, build_fixture
from ..models import Availability, ManagerReadModel, ReadModelError, ReadModelStatus
from ..provider import ManagerDataProvider
from .assets import CSS, JS
from .atlas import render_atlas_view
from .documents import (
    DOCUMENTS_RESOURCE,
    ApprovedDirectoryBoundary,
    build_source_documents_fixture,
    render_source_documents_view,
)
from .history import HISTORY_SCOPES, build_history_fixture, render_history_view
from .methodology import (
    MethodologyFixtureState,
    build_methodology_fixture,
    render_methodology_view,
)
from .navigation import NAVIGATION, NavigationItem, ViewId, navigation_item
from .research_story import StoryMode, render_research_story
from .status import render_status_block


@dataclass(frozen=True, slots=True)
class WebRequestState:
    """The URL state shared by server rendering and future page modules."""

    view: ViewId
    fixture: FixtureState
    query: str
    panel: str | None
    mode: StoryMode = StoryMode.NARRATIVE
    context: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_url(cls, url: str, *, default_fixture: FixtureState) -> WebRequestState:
        parsed = urlsplit(url)
        values = parse_qs(parsed.query, keep_blank_values=True)
        raw_view = values.get("view", [ViewId.ATLAS.value])[0]
        raw_fixture = values.get("fixture", [default_fixture.value])[0]
        raw_panel = values.get("panel", [""])[0]
        raw_mode = values.get("mode", [StoryMode.NARRATIVE.value])[0]
        try:
            view = ViewId(raw_view)
        except ValueError:
            view = ViewId.ATLAS
        try:
            fixture = FixtureState(raw_fixture)
        except ValueError:
            fixture = default_fixture
        panel = raw_panel if raw_panel in {"inspector", "events"} else None
        try:
            mode = StoryMode(raw_mode)
        except ValueError:
            mode = StoryMode.NARRATIVE
        return cls(
            view=view,
            fixture=fixture,
            query=values.get("q", [""])[0].strip(),
            panel=panel,
            mode=mode,
            context=tuple(sorted(
                (key, entries[0]) for key, entries in values.items()
                if key not in {"view", "fixture", "panel", "q", "mode"}
            )),
        )

    def query_pairs(self, *, view: ViewId | None = None) -> tuple[tuple[str, str], ...]:
        """Canonical shared links/forms retain page-local opaque context."""

        values = dict(self.context)
        values.update(view=(view or self.view).value, fixture=self.fixture.value)
        if self.query:
            values["q"] = self.query
        if self.panel:
            values["panel"] = self.panel
        destination = view or self.view
        if destination is ViewId.STORIES:
            values["mode"] = self.mode.value
        return tuple(sorted(values.items()))

    def url(self, *, view: ViewId | None = None) -> str:
        return "/?" + urlencode(self.query_pairs(view=view))


@dataclass(frozen=True, slots=True)
class _FixtureReadProvider:
    """Route the shared fixture selector to each S5 public read seam."""

    fixture: FixtureState
    scope: str

    def read(
        self,
        resource: str = "atlas",
        *,
        snapshot_token: str | None = None,
    ) -> ManagerReadModel:
        del snapshot_token
        if resource == "methodology":
            return self._methodology()
        if resource == "history":
            return self._history()
        if resource == DOCUMENTS_RESOURCE:
            return self._documents()
        return build_fixture(self.fixture, resource=resource)

    def _methodology(self) -> ManagerReadModel:
        selected = self.fixture
        if selected in {
            FixtureState.EMPTY,
            FixtureState.COMPLETE,
            FixtureState.PARTIAL,
            FixtureState.STALE,
        }:
            state = MethodologyFixtureState(selected.value)
            return build_methodology_fixture(state)
        if selected is FixtureState.API_UNAVAILABLE:
            return build_methodology_fixture(MethodologyFixtureState.NOT_INDEXED)
        return build_fixture(selected, resource="methodology")

    def _history(self) -> ManagerReadModel:
        if self.fixture is FixtureState.COMPLETE:
            return build_history_fixture(self.scope)
        if self.fixture is FixtureState.PARTIAL:
            model = build_history_fixture(self.scope)
            return replace(
                model,
                availability=Availability(
                    status=ReadModelStatus.KNOWN,
                    complete=False,
                    reason="Only part of the source-event history is in scope.",
                ),
                errors=(
                    ReadModelError(
                        code="history_scope_partial",
                        message="Some source-event categories are outside the indexed scope.",
                        source_ref=model.source_refs[0].source_id if model.source_refs else None,
                    ),
                ),
            )
        return build_fixture(self.fixture, resource="history")

    def _documents(self) -> ManagerReadModel:
        if self.fixture is FixtureState.COMPLETE:
            return build_source_documents_fixture(self.scope)
        return build_fixture(self.fixture, resource=DOCUMENTS_RESOURCE)


@dataclass(frozen=True, slots=True)
class _CachedReadProvider:
    """Adapt the already-read envelope to a page hook without a second read."""

    model: ManagerReadModel

    def read(
        self,
        resource: str = "atlas",
        *,
        snapshot_token: str | None = None,
    ) -> ManagerReadModel:
        del resource, snapshot_token
        return self.model


class ManagerGUIApp:
    """Read-only shell renderer with an injectable public provider seam."""

    def __init__(
        self,
        provider: ManagerDataProvider | None = None,
        *,
        default_fixture: FixtureState | str = FixtureState.PARTIAL,
        approved_directories: tuple[str, ...] = (),
    ) -> None:
        self._provider = provider
        self._default_fixture = FixtureState(default_fixture)
        self._approved_directories = tuple(approved_directories)

    @property
    def default_fixture(self) -> FixtureState:
        """Fixture selected when a URL omits ``fixture``."""

        return self._default_fixture

    def request_state(self, url: str = "/") -> WebRequestState:
        """Parse stable query state without consulting owner storage."""

        return WebRequestState.from_url(url, default_fixture=self._default_fixture)

    def read_model(self, state: WebRequestState) -> ManagerReadModel:
        """Read through the public seam; this method intentionally has no writes."""

        provider = self._provider or _FixtureReadProvider(
            self._default_fixture_for_state(state), self._scope_for_state(state)
        )
        resource = self._resource_for_view(state.view)
        return provider.read(resource, snapshot_token=dict(state.context).get("snapshot_token"))

    @staticmethod
    def _resource_for_view(view: ViewId) -> str:
        if view is ViewId.SOURCE_DOCUMENTS:
            return DOCUMENTS_RESOURCE
        return view.value

    def _default_fixture_for_state(self, state: WebRequestState) -> FixtureState:
        """Use the URL fixture while keeping S5 scopes as page-local context."""

        return state.fixture

    @staticmethod
    def _scope_for_state(state: WebRequestState) -> str:
        requested = dict(state.context).get("scope")
        return requested if requested in HISTORY_SCOPES else "A0"

    def render(self, url: str = "/") -> str:
        """Render a complete HTML document for the shell route."""

        state = self.request_state(url)
        model = self.read_model(state)
        item = navigation_item(state.view)
        page = self._render_page(state, model, url)
        return self._render_document(state, model, item, page)

    def render_json(self, url: str = "/") -> str:
        """Return the current envelope for a future client-side integration."""

        state = self.request_state(url)
        return self.read_model(state).to_json(indent=2)

    def _render_page(self, state: WebRequestState, model: ManagerReadModel, url: str) -> str | None:
        """Mount a page hook while leaving all shell chrome in this app."""

        cached = _CachedReadProvider(model)
        if state.view is ViewId.ATLAS:
            return render_atlas_view(
                cached,
                query_context=url,
                snapshot_token=model.snapshot_token,
            )
        if state.view is ViewId.STORIES:
            return render_research_story(
                model,
                mode=state.mode,
                base_path=url,
                query=url,
            )
        if state.view is ViewId.METHODOLOGY:
            return render_methodology_view(
                cached,
                snapshot_token=model.snapshot_token,
                query_context=url,
            )
        if state.view is ViewId.HISTORY:
            return render_history_view(
                model,
                scope=self._scope_for_state(state),
                base_path=url,
                query=url,
            )
        if state.view is ViewId.SOURCE_DOCUMENTS:
            return render_source_documents_view(
                model,
                scope=self._scope_for_state(state),
                boundary=ApprovedDirectoryBoundary(self._approved_directories),
                base_path=url,
                query=url,
            )
        return None

    @staticmethod
    def _render_source_refs(model: ManagerReadModel) -> str:
        if not model.source_refs:
            return '<div class="inspector-item"><dt>Sources</dt><dd>None recorded</dd></div>'
        refs = []
        for source in model.source_refs:
            refs.append(
                f'<div class="inspector-item"><dt>{escape(source.owner)} · '
                f"{escape(source.kind)}</dt><dd>{escape(source.locator)}</dd></div>"
            )
        return "".join(refs)

    @staticmethod
    def _render_document(
        state: WebRequestState,
        model: ManagerReadModel,
        item: NavigationItem,
        page: str | None,
    ) -> str:
        raw_json = escape(model.to_json(indent=2))
        inspector_hidden = " hidden" if state.panel == "events" else ""
        drawer_hidden = "" if state.panel == "events" else " hidden"
        snapshot = model.snapshot_token or "No snapshot token"
        as_of = model.as_of or "Unavailable"
        query_value = escape(state.query, quote=True)
        state_value = escape(state.fixture.value, quote=True)
        panel_text = "Events & raw JSON"
        if page is None:
            page_markup = f"""
      <p class="eyebrow">Shared shell · fixture-backed</p>
      <h1 class="page-title" data-page-title tabindex="-1">{escape(item.label)}</h1>
      <p class="page-intro">{escape(item.description)} This slice provides orientation and provenance only;
        domain pages attach through the public read-model hook.</p>
      <p class="context-line"><span><strong>View</strong> {escape(state.view.value)}</span>
        <span><strong>Fixture</strong> {escape(state.fixture.value)}</span>
        <span><strong>Observed</strong> {escape(as_of)}</span></p>
      {render_status_block(model)}
      <section class="hook-surface" data-integration-hook="{escape(item.integration_hook)}">
        <h2>Integration point ready</h2>
        <p>This placeholder deliberately does not infer owner facts. A future view can consume the
          same <code>ManagerReadModel v0</code> envelope and keep this shell, inspector, and event drawer.</p>
        <span class="hook-label">hook: {escape(item.integration_hook)}</span>
      </section>"""
        else:
            page_markup = page
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#18343a">
  <title>{escape(item.label)} · Manager GUI</title>
  <style>{CSS}</style>
</head>
<body>
<a class="skip-link" href="#main-content">Skip to workspace</a>
<div class="app-shell">
  <header class="topbar">
    <a class="brand" href="{escape(ManagerGUIApp._static_link(state), quote=True)}" aria-label="Manager GUI home">
      <span class="brand-mark" aria-hidden="true">M</span><span class="brand-name">MANAGER GUI</span>
    </a>
    <div class="topbar-meta">
      <span class="workspace-note">Fixture workspace · snapshot {escape(snapshot)}</span>
      <span class="read-only-badge" aria-label="Read only; mutations are disabled">READ ONLY</span>
    </div>
    <form class="search-form" role="search" action="/" method="get">
      <label class="sr-only" for="global-search">Global search</label>
      <input class="search-input" id="global-search" name="q" value="{query_value}"
        placeholder="Search read models…" autocomplete="off">
      <input type="hidden" name="view" value="{escape(state.view.value, quote=True)}">
      <input type="hidden" name="fixture" value="{state_value}">
    </form>
  </header>
  <nav class="nav-strip" aria-label="Manager GUI sections">{ManagerGUIApp._render_navigation_static(state)}</nav>
  <div class="workspace">
    <main id="main-content" class="main-column" tabindex="-1">
      {page_markup}
      <div class="panel-actions" aria-label="Shared panels">
        <button class="panel-button" type="button" data-panel-target="inspector">Open inspector</button>
        <button class="panel-button" type="button" data-panel-target="events">Open {panel_text.lower()}</button>
      </div>
    </main>
    <aside class="inspector" id="inspector" tabindex="-1"{inspector_hidden} aria-labelledby="inspector-title">
      <div class="panel-heading"><h2 id="inspector-title">Inspector</h2><span class="panel-kicker">read context</span></div>
      <dl class="inspector-list">
        <div class="inspector-item"><dt>Read model</dt><dd>manager-read-model.v0</dd></div>
        <div class="inspector-item"><dt>Status</dt><dd>{escape(model.availability.status.value)}</dd></div>
        <div class="inspector-item"><dt>Snapshot</dt><dd>{escape(snapshot)}</dd></div>
        <div class="inspector-item"><dt>Observed at</dt><dd>{escape(as_of)}</dd></div>
        {ManagerGUIApp._render_source_refs(model)}
      </dl>
      <div class="panel-actions"><button class="panel-button" type="button" data-panel-target="events">View raw JSON</button></div>
    </aside>
  </div>
  <aside class="event-drawer" id="event-drawer" tabindex="-1"{drawer_hidden} aria-labelledby="event-title">
    <div class="panel-heading"><h2 id="event-title">{panel_text}</h2><button class="panel-button drawer-close" type="button" data-close-panels>Close</button></div>
    <pre class="raw-json" aria-label="Raw ManagerReadModel v0 JSON">{raw_json}</pre>
  </aside>
</div>
<script>{JS}</script>
</body>
</html>"""

    @staticmethod
    def _static_link(state: WebRequestState) -> str:
        return state.url(view=ViewId.ATLAS)

    @staticmethod
    def _render_navigation_static(state: WebRequestState) -> str:
        context = [
            (key, value)
            for key, value in state.query_pairs()
            if key not in {"view", "fixture"}
        ]
        links = []
        for item in NAVIGATION:
            current = item.view_id is state.view
            href_values = [("view", item.view_id.value), ("fixture", state.fixture.value), *context]
            href = "/?" + urlencode(href_values)
            links.append(
                f'<a class="nav-link" data-nav-link href="{escape(href, quote=True)}" '
                f'aria-current="{"page" if current else "false"}" '
                f'title="{escape(item.description, quote=True)}">'
                f'<span class="nav-short" aria-hidden="true">{escape(item.short_label)}</span>'
                f'<span class="nav-label">{escape(item.label)}</span></a>'
            )
        return "".join(links)


__all__ = ["ManagerGUIApp", "WebRequestState"]
