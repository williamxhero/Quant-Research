"""Server-side rendering for the fixture-backed Manager GUI shell."""

# The HTML document is intentionally readable as a single template; its markup
# lines are longer than the Python package's normal line-length budget.
# ruff: noqa: E501

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from html import escape, unescape
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..fixtures import FixtureState, build_fixture
from ..models import Availability, Derivation, ManagerReadModel, ReadModelError, ReadModelStatus
from ..provider import ManagerDataProvider
from ..reader import (
    ProjectionMode,
    ReaderProjection,
    project_reader_model,
    render_mode_switch,
    render_reader_contract,
    render_sample_banner,
)
from ..reader.mode import reader_contract_payload
from .assets import CSS, render_js
from .atlas import render_atlas_reading, render_atlas_view
from .comparison import (
    COMPARISON_RESOURCE,
    ComparisonFixtureState,
    build_genome_comparison_fixture,
)
from .comparison_reader import (
    project_comparison_reader,
    render_comparison_reader,
)
from .conditions import (
    CONDITIONS_RESOURCE,
    ConditionFixtureState,
    build_conditions_fixture,
    render_genome_conditions_view,
)
from .documents import (
    DOCUMENTS_RESOURCE,
    ApprovedDirectoryBoundary,
    build_source_documents_fixture,
)
from .evidence import EVIDENCE_RESOURCE, render_evidence_view
from .evidence_comparison import (
    EVIDENCE_COMPARISON_RESOURCE,
    render_evidence_comparison_view,
)
from .evidence_lineage_reader import (
    ReaderTraceMode,
    build_evidence_lineage_reader_fixture,
    project_evidence_lineage_reader,
    render_evidence_lineage_reader,
    render_lineage_reader,
)
from .evidence_trace import render_evidence_trace
from .failure_grouping import FAILURE_GROUPING_RESOURCE, render_failure_grouping_view
from .failure_patterns import (
    FAILURE_PATTERNS_RESOURCE,
    render_failure_patterns_view,
    render_memory_failure_view,
)
from .genome import (
    GENOME_RESOURCE,
    GenomeFixtureState,
    build_genome_fixture,
    render_genome_view,
)
from .history import HISTORY_SCOPES, build_history_fixture
from .history_documents_reader import (
    project_history_reader,
    project_source_documents_reader,
    render_history_reader,
    render_source_documents_reader,
)
from .i18n import DEFAULT_LOCALE, Locale, Translator, resolve_locale, with_lang
from .interaction import (
    export_json as render_current_view_export_json,
)
from .interaction import (
    opaque_copy_button,
    render_export_control,
)
from .lineage import LINEAGE_RESOURCE, render_lineage_view
from .memory import render_memory_view
from .memory_failure_reader import (
    project_failure_reader,
    project_memory_reader,
    render_failure_patterns_reader,
    render_failure_reader,
    render_memory_reader,
)
from .methodology import (
    MethodologyFixtureState,
    build_methodology_fixture,
)
from .methodology_reader import (
    project_methodology_reader,
    render_methodology_reader,
)
from .navigation import (
    NAVIGATION,
    NavigationItem,
    ViewId,
    navigation_description,
    navigation_item,
    navigation_label,
)
from .plain_result import render_plain_result
from .portal import REPORT_SOURCE_RESOURCE
from .portal_reader import project_portal_reader, render_portal_reader
from .reader_shell import annotate_reader_mount, reader_route
from .reader_surface import ReaderPage
from .research_story import StoryMode, render_research_story
from .resource_reading import RESOURCES, render_resource_reading
from .s4_fixtures import S4_FIXTURE_STATES, S4_RESOURCES, build_s4_fixture
from .s6_fixtures import S6_RESOURCES, build_s6_fixture
from .search import SEARCH_RESOURCE
from .search_reader import project_search_reader, render_search_reader
from .source_support import (
    deferred_raw_markup,
    demand_link,
    demand_pagination,
    demand_window,
    support_scope,
)
from .status import render_status_block
from .strategy_reader import project_strategy_reader, render_strategy_reader

_INTERNAL_HREF = re.compile(r'''(?P<prefix>href=["'])(?P<url>/\?[^"']*)(?P<suffix>["'])''')


def _without_query_keys(url: str, keys: set[str]) -> str:
    """Remove UI-only query keys while retaining every other pair and order."""

    parts = urlsplit(url)
    pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in keys
    ]
    return urlunsplit(parts._replace(query=urlencode(pairs)))


@dataclass(frozen=True, slots=True)
class WebRequestState:
    """The URL state shared by server rendering and future page modules.

    ``mode`` is the global Reader mode.  Research Story's historical
    ``narrative|evidence|timeline`` selector remains available as ``story_mode``
    so old v0 links continue to render without taking over the Reader URL key.
    """

    view: ViewId
    fixture: FixtureState
    query: str
    panel: str | None
    mode: ProjectionMode = ProjectionMode.READER
    story_mode: StoryMode = StoryMode.NARRATIVE
    context: tuple[tuple[str, str], ...] = ()
    lang: Locale | None = None
    default_locale: Locale = DEFAULT_LOCALE
    workspace_retry_requested: bool = False

    @property
    def locale(self) -> Locale:
        """Return the explicit locale, or the app's configured default."""

        return self.lang or self.default_locale

    def context_value(self, key: str) -> str | None:
        """Return the first value for an opaque context key."""

        return next((value for context_key, value in self.context if context_key == key), None)

    @property
    def scope(self) -> str | None:
        return self.context_value("scope")

    @property
    def root(self) -> str | None:
        return self.context_value("root")

    @property
    def filters(self) -> tuple[str, ...]:
        return tuple(value for key, value in self.context if key == "filter")

    @property
    def snapshot_token(self) -> str | None:
        return self.context_value("snapshot_token") or self.context_value("snapshot")

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        default_fixture: FixtureState,
        default_locale: Locale | str = DEFAULT_LOCALE,
    ) -> WebRequestState:
        resolved_default_locale = resolve_locale(default_locale)
        if resolved_default_locale is None:
            raise ValueError(f"unsupported default locale: {default_locale!r}")
        parsed = urlsplit(url)
        pairs = parse_qsl(parsed.query, keep_blank_values=True)

        def first(key: str, default: str = "") -> str:
            return next((value for pair_key, value in pairs if pair_key == key), default)

        raw_view = first("view", ViewId.ATLAS.value)
        raw_fixture = first("fixture", default_fixture.value)
        raw_panel = first("panel")
        raw_mode = first("mode", ProjectionMode.READER.value)
        raw_story_mode = first("story_mode", raw_mode)
        lang = resolve_locale(first("lang") or None)
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
            mode = ProjectionMode(raw_mode)
        except ValueError:
            mode = ProjectionMode.READER
        try:
            story_mode = StoryMode(raw_story_mode)
        except ValueError:
            story_mode = StoryMode.NARRATIVE
        return cls(
            view=view,
            fixture=fixture,
            query=first("q").strip(),
            panel=panel,
            mode=mode,
            story_mode=story_mode,
            context=tuple(
                (key, value)
                for key, value in pairs
                if key not in {"view", "fixture", "panel", "q", "mode", "lang", "workspace_retry"}
            ),
            lang=lang,
            default_locale=resolved_default_locale,
            workspace_retry_requested=first("workspace_retry") == "1",
        )

    def query_pairs(self, *, view: ViewId | None = None) -> tuple[tuple[str, str], ...]:
        """Canonical shared links/forms retain page-local opaque context."""

        pairs = list(self.context)
        pairs.extend((("view", (view or self.view).value), ("fixture", self.fixture.value)))
        if self.query:
            pairs.append(("q", self.query))
        if self.panel:
            pairs.append(("panel", self.panel))
        if self.lang is not None:
            pairs.append(("lang", self.lang.value))
        pairs.append(("mode", self.mode.value))
        return tuple(sorted(pairs))

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
        if resource in S6_RESOURCES:
            return build_s6_fixture(resource, self.fixture)
        if resource in S4_RESOURCES:
            return build_s4_fixture(resource, self.fixture)
        if self.fixture in S4_FIXTURE_STATES:
            # S4-only selector values: other routes keep the shared generic envelope.
            return build_fixture(self.fixture, resource=resource)
        if resource == GENOME_RESOURCE:
            return build_genome_fixture(self._genome_fixture_state())
        if resource == CONDITIONS_RESOURCE:
            return build_conditions_fixture(self._conditions_fixture_state())
        if resource == COMPARISON_RESOURCE:
            return build_genome_comparison_fixture(self._comparison_fixture_state())
        if resource == EVIDENCE_RESOURCE:
            return build_evidence_lineage_reader_fixture(self.fixture.value)
        if resource == "methodology":
            return self._methodology()
        if resource == "history":
            return self._history()
        if resource == DOCUMENTS_RESOURCE:
            return self._documents()
        return build_fixture(self.fixture, resource=resource)

    def _genome_fixture_state(self) -> GenomeFixtureState:
        return GenomeFixtureState(self.fixture.value)

    def _conditions_fixture_state(self) -> ConditionFixtureState:
        return ConditionFixtureState(self.fixture.value)

    def _comparison_fixture_state(self) -> ComparisonFixtureState:
        if self.fixture is FixtureState.EMPTY:
            return ComparisonFixtureState.MISSING
        return ComparisonFixtureState(self.fixture.value)

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


def _legacy_reader_compat(markup: str) -> str:
    """Keep pre-R4 semantic hooks available without adding a second page heading."""

    def _heading(match: re.Match[str]) -> str:
        return f'<span{match.group(1)} hidden>{match.group(2)}</span>'

    # The visible page owns support anchors. Discard hidden compatibility
    # entries rather than leave their coordinated references pointing nowhere.
    markup = re.sub(
        r'<a\b[^>]*data-source-support="[^"]*"[^>]*>(.*?)</a>',
        r'<span>\1</span>', markup, flags=re.DOTALL,
    )
    # Match the HTML ``id`` attribute itself, not the ``id`` suffix in
    # data-record-id/data-source-id attributes.
    markup = re.sub(r'(?<![-\w])id="([^"]+)"', r'id="legacy-\1"', markup)
    markup = re.sub(
        r'\b(aria-labelledby|aria-describedby)="([^"]+)"',
        lambda match: f'{match.group(1)}="{" ".join("legacy-" + token for token in match.group(2).split())}"',
        markup,
    )
    markup = re.sub(r'href="#([^"]+)"', r'href="#legacy-\1"', markup)
    return '<div class="reader-legacy-compat" hidden>' + re.sub(
        r'<h1(\b[^>]*)>(.*?)</h1>',
        _heading,
        markup,
        flags=re.DOTALL,
    ) + '</div>'


@dataclass(frozen=True, slots=True)
class _PlainResultPage:
    markup: str


class ManagerGUIApp:
    """Read-only shell renderer with an injectable public provider seam."""

    def __init__(
        self,
        provider: ManagerDataProvider | None = None,
        *,
        default_fixture: FixtureState | str = FixtureState.PARTIAL,
        default_locale: Locale | str = DEFAULT_LOCALE,
        approved_directories: tuple[str, ...] = (),
    ) -> None:
        self._provider = provider
        self._default_fixture = FixtureState(default_fixture)
        resolved_locale = resolve_locale(default_locale)
        if resolved_locale is None:
            raise ValueError(f"unsupported default locale: {default_locale!r}")
        self._default_locale = resolved_locale
        self._approved_directories = tuple(approved_directories)

    @property
    def default_fixture(self) -> FixtureState:
        """Fixture selected when a URL omits ``fixture``."""

        return self._default_fixture

    @property
    def default_locale(self) -> Locale:
        """Locale selected when a URL omits or invalidates ``lang``."""

        return self._default_locale

    def request_state(self, url: str = "/") -> WebRequestState:
        """Parse stable query state without consulting owner storage."""

        return WebRequestState.from_url(
            url,
            default_fixture=self._default_fixture,
            default_locale=self._default_locale,
        )

    def read_model(self, state: WebRequestState) -> ManagerReadModel:
        """Read through the public seam; this method intentionally has no writes."""

        if state.workspace_retry_requested:
            restart = getattr(self._provider, "_restart_retry_cycle", None)
            if restart is not None:
                restart()
        provider = self._provider or _FixtureReadProvider(
            self._default_fixture_for_state(state), self._scope_for_state(state)
        )
        resource = self._resource_for_view(state.view)
        tokens = tuple(value for key, value in state.context if key in {"snapshot_token", "snapshot"})
        if self._provider is not None and (
            any(not token.strip() for token in tokens) or len(set(tokens)) > 1
        ):
            reason = "Blank or conflicting application read-view tokens."
        else:
            try:
                model = provider.read(resource, snapshot_token=state.snapshot_token)
            except Exception as exc:
                if self._provider is not None and getattr(exc, "code", None) == "workspace_unsafe_read":
                    from ..workspace import unavailable_workspace_model

                    return unavailable_workspace_model(
                        ReadModelError(exc.code, str(exc), details=getattr(exc, "details", None)),
                        snapshot_token=state.snapshot_token,
                    )
                if self._provider is None or resource not in RESOURCES:
                    raise
                return ManagerReadModel(
                    data={},
                    source_refs=(),
                    as_of=None,
                    snapshot_token=state.snapshot_token,
                    derivation=Derivation("direct"),
                    availability=Availability(
                        ReadModelStatus.API_UNAVAILABLE,
                        False,
                        "Public resource read failed; absence is not confirmed.",
                    ),
                    errors=(
                        ReadModelError(
                            "provider_read_failed",
                            str(exc) or type(exc).__name__,
                            details={
                                "exception_type": type(exc).__name__,
                                "owner_code": str(exc.code) if hasattr(exc, "code") else None,
                            },
                        ),
                    ),
                )
            unsafe = next((e for e in model.errors if e.code == "workspace_unsafe_read"), None)
            if self._provider is not None and unsafe is not None:
                from ..workspace import unavailable_workspace_model

                return unavailable_workspace_model(unsafe, snapshot_token=state.snapshot_token)
            if (
                self._provider is None
                or state.snapshot_token is None
                or model.snapshot_token == state.snapshot_token
            ):
                return model
            reason = "The provider cannot honor the requested application read view."
        requested = state.snapshot_token
        return ManagerReadModel(
            {}, (), None, requested if requested and requested.strip() else None,
            Derivation("direct"), Availability(ReadModelStatus.STALE, False, reason),
            (ReadModelError("snapshot_drift", reason),),
        )

    def reader_projection(self, url: str = "/") -> ReaderProjection:
        """Project the current public v0 read into the UI-only Reader contract."""

        state = self.request_state(url)
        return self._project_reader_model(state, self.read_model(state))

    def _project_reader_model(
        self, state: WebRequestState, model: ManagerReadModel
    ) -> ReaderProjection:
        if state.view in {ViewId.COMPARISON, ViewId.EVIDENCE_COMPARISON}:
            return project_comparison_reader(
                model,
                sample=self._provider is None,
                sample_state=state.fixture.value,
            )
        if state.view in {ViewId.STRATEGIES, ViewId.CONDITIONS}:
            return project_strategy_reader(
                model,
                resource=self._resource_for_view(state.view),
                sample=self._provider is None,
                sample_state=state.fixture.value,
            )
        if state.view is ViewId.MEMORY:
            return project_memory_reader(
                model,
                sample=self._provider is None,
                sample_state=state.fixture.value,
            )
        if state.view in {ViewId.MEMORY_FAILURES, ViewId.FAILURE_PATTERNS}:
            return project_failure_reader(
                model,
                sample=self._provider is None,
                sample_state=state.fixture.value,
            )
        if state.view in {ViewId.EVIDENCE, ViewId.LINEAGE}:
            return project_evidence_lineage_reader(
                model,
                sample=self._provider is None,
                sample_state=state.fixture.value,
            )
        if state.view is ViewId.METHODOLOGY:
            return project_methodology_reader(
                model,
                sample=self._provider is None,
                sample_state=state.fixture.value,
            )
        if state.view is ViewId.HISTORY:
            return project_history_reader(
                model,
                sample=self._provider is None,
                sample_state=state.fixture.value,
            )
        if state.view is ViewId.SOURCE_DOCUMENTS:
            return project_source_documents_reader(
                model,
                sample=self._provider is None,
                sample_state=state.fixture.value,
            )
        if state.view is ViewId.SEARCH:
            context = dict(state.context)
            return project_search_reader(
                model,
                query=state.query,
                record_type=context.get("record_type") or context.get("type"),
                source=context.get("source"),
                sample=self._provider is None,
                sample_state=state.fixture.value,
            )
        if state.view is ViewId.PORTAL:
            return project_portal_reader(
                model,
                sample=self._provider is None,
                sample_state=state.fixture.value,
            )
        return project_reader_model(
            model,
            resource=self._resource_for_view(state.view),
            sample=self._provider is None,
            sample_state=state.fixture.value,
        )

    @staticmethod
    def _resource_for_view(view: ViewId) -> str:
        if view is ViewId.STRATEGIES:
            return GENOME_RESOURCE
        if view is ViewId.CONDITIONS:
            return CONDITIONS_RESOURCE
        if view is ViewId.COMPARISON:
            return COMPARISON_RESOURCE
        if view is ViewId.EVIDENCE:
            return EVIDENCE_RESOURCE
        if view is ViewId.LINEAGE:
            return LINEAGE_RESOURCE
        if view is ViewId.EVIDENCE_COMPARISON:
            return EVIDENCE_COMPARISON_RESOURCE
        if view is ViewId.FAILURE_GROUPING:
            return FAILURE_GROUPING_RESOURCE
        if view is ViewId.MEMORY_FAILURES:
            return "memory"
        if view is ViewId.FAILURE_PATTERNS:
            return FAILURE_PATTERNS_RESOURCE
        if view is ViewId.SOURCE_DOCUMENTS:
            return DOCUMENTS_RESOURCE
        if view is ViewId.SEARCH:
            return SEARCH_RESOURCE
        if view is ViewId.PORTAL:
            return REPORT_SOURCE_RESOURCE
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
        normalized_url = with_lang(_without_query_keys(url, {"workspace_retry"}), state.lang)
        model = self.read_model(state)
        if self._provider is not None and model.snapshot_token and state.snapshot_token is None:
            parts = urlsplit(normalized_url)
            pairs = parse_qsl(parts.query, keep_blank_values=True)
            pairs.append(("snapshot_token", model.snapshot_token))
            normalized_url = urlunsplit(parts._replace(query=urlencode(pairs)))
            state = replace(state, context=(*state.context, ("snapshot_token", model.snapshot_token)))
        projection = self._project_reader_model(state, model)
        deferred = len(projection.raw_source.raw_bytes) > 1_000_000
        item = navigation_item(state.view)
        route = reader_route(state.view)
        translator = Translator(state.locale)
        if state.context_value("ui_raw") == "1":
            text = projection.raw_source.raw_bytes.decode("utf-8")
            window = demand_window(normalized_url, total=(len(text) + 99999) // 100000)
            chunk = text[window.start * 100000:window.stop * 100000]
            return (
                '<section class="demand-raw">'
                f'<pre class="raw-json" translate="no">{escape(chunk)}</pre>'
                + demand_pagination(normalized_url, window, translator)
                + '</section>'
            )
        with support_scope(
            model, normalized_url, translator, sample=projection.sample_data is not None,
            active=deferred or state.mode is not ProjectionMode.READER or state.view is not ViewId.ATLAS,
            deferred=deferred,
        ) as support:
            unsafe = next((e for e in model.errors if e.code == "workspace_unsafe_read"), None)
            rendered = (
                self._render_workspace_warning(unsafe, normalized_url, translator)
                if unsafe is not None else self._render_page(
                    state, model, normalized_url, translator=translator, reader_projection=projection
                )
            )
            plain_reading = isinstance(rendered, _PlainResultPage)
            page = rendered.markup if isinstance(rendered, _PlainResultPage) else rendered
            if page is not None:
                resource = self._resource_for_view(state.view)
                if self._provider is not None and resource in RESOURCES and unsafe is None:
                    page = render_resource_reading(
                        model, resource=resource, view=state.view.value,
                        title=navigation_label(state.view, translator),
                        page=page, translator=translator,
                    )
                if deferred and state.mode is not ProjectionMode.READER:
                    page += "".join(
                        f'<p>{support.reference(ref.source_id)}</p>' for ref in model.source_refs
                    )
                selected = state.context_value("ui_support")
                if selected is not None:
                    try:
                        index = int(selected)
                    except ValueError:
                        index = 0
                    return support.render(page, selected_index=index) or (
                        '<section class="source-support">'
                        f'<p role="status">{escape(translator.t("client.load_unavailable"))}</p>'
                        f'{render_status_block(model, translator=translator)}</section>'
                    )
                page += support.render(page)
        if page is not None:
            page = annotate_reader_mount(
                page,
                route=route,
                mode=state.mode,
                availability=projection.availability.status.value,
            )
        page = self._localize_internal_links(page, state.lang)
        return self._render_document(
            state,
            model,
            item,
            page,
            translator=translator,
            raw_url=normalized_url,
            reader_projection=projection,
            plain_reading=plain_reading,
        )

    @staticmethod
    def _render_workspace_warning(error, url, translator) -> str:
        details = error.details or {}
        attempts = details.get("retry_attempts", 0)
        limit = details.get("retry_limit", 5)
        delay = details.get("next_delay_seconds")
        auto_url = _without_query_keys(url, {"workspace_retry", "ui_raw", "ui_support", "ui_reader"})
        manual_base = _without_query_keys(auto_url, {"workspace_autoload"})
        manual_url = manual_base + ("&" if urlsplit(manual_base).query else "?") + "workspace_retry=1"
        cancelled = ("workspace_autoload", "0") in parse_qsl(urlsplit(url).query)
        pending = delay is not None and not details.get("stopped", True) and not cancelled
        schedule = translator.t(
            "workspace.wait" if pending else "workspace.stopped",
            attempts=attempts, limit=limit, seconds=delay,
        )
        if cancelled:
            schedule = translator.t("workspace.cancelled")
        timer = (
            f' data-workspace-retry-url="{escape(auto_url, quote=True)}"'
            f' data-workspace-retry-seconds="{delay}"' if pending else ""
        )
        return (
            f'<section class="workspace-read-warning" role="alert"{timer}>'
            f'<h1 class="page-title" data-page-title tabindex="-1">{escape(translator.t("workspace.unsafe"))}</h1>'
            f'<p data-workspace-retry-status>{escape(schedule)}</p>'
            f'<a href="{escape(manual_url, quote=True)}" data-workspace-retry-manual>'
            f'{escape(translator.t("workspace.manual"))}</a> '
            f'<button type="button" data-workspace-retry-cancel>'
            f'{escape(translator.t("workspace.cancel"))}</button>'
            f'<details><summary>{escape(error.code)}</summary>'
            f'<pre translate="no">{escape(error.message)}</pre></details></section>'
        )

    def render_reader_json(self, url: str) -> str:
        state = self.request_state(url)
        projection = self._project_reader_model(state, self.read_model(state))
        return json.dumps(
            reader_contract_payload(projection, state.mode),
            ensure_ascii=False, allow_nan=False, sort_keys=True,
        )

    def render_json(self, url: str = "/") -> str:
        """Return the current envelope for a future client-side integration."""

        state = self.request_state(url)
        return self.read_model(state).to_json(indent=2)

    def render_export(self, url: str = "/") -> str:
        """Return a pure current-view export payload for a read-only GET route."""

        state = self.request_state(url)
        model = self.read_model(state)
        # Export data stays language-neutral and excludes presentation-only mode.
        export_context = _without_query_keys(with_lang(url, None), {"mode", "workspace_retry"})
        return render_current_view_export_json(
            model,
            view=state.view.value,
            query_context=export_context,
        )

    @staticmethod
    def _localize_internal_links(markup: str | None, locale: Locale | None) -> str | None:
        """Apply explicit language state to owner-provided local links only."""

        if markup is None:
            return None

        def replace_link(match: re.Match[str]) -> str:
            raw_url = unescape(match.group("url"))
            localized = with_lang(raw_url, locale)
            return (
                f'{match.group("prefix")}{escape(localized, quote=True)}'
                f'{match.group("suffix")}'
            )

        return _INTERNAL_HREF.sub(replace_link, markup)

    def _render_page(
        self,
        state: WebRequestState,
        model: ManagerReadModel,
        url: str,
        *,
        translator: Translator,
        reader_projection: ReaderProjection,
    ) -> str | _PlainResultPage | None:
        """Mount a page hook while leaving all shell chrome in this app."""

        cached = _CachedReadProvider(model)
        if state.mode is ProjectionMode.RAW:
            raw = deferred_raw_markup()
            if raw is not None:
                item = navigation_item(state.view)
                return (
                    f'<section data-integration-hook="{escape(item.integration_hook, quote=True)}">'
                    f'<h1 data-page-title tabindex="-1">{escape(navigation_label(state.view, translator))}</h1>'
                    f'{render_status_block(model, translator=translator)}{raw}</section>'
                )
        if state.view is ViewId.ATLAS:
            if state.mode is ProjectionMode.READER:
                return render_atlas_reading(
                    model, query_context=url, translator=translator,
                    sample=reader_projection.sample_data is not None,
                ) + _legacy_reader_compat(render_atlas_view(
                    cached, query_context=url, snapshot_token=model.snapshot_token,
                    translator=translator, reader_projection=reader_projection,
                ))
            return render_atlas_view(
                cached,
                query_context=url,
                snapshot_token=model.snapshot_token,
                translator=translator,
                reader_projection=reader_projection,
                include_reader_surface=state.mode is ProjectionMode.READER,
            )
        if state.view is ViewId.STORIES:
            legacy_markup = render_research_story(
                model,
                mode=state.story_mode,
                base_path=url,
                query=url,
                translator=translator,
                reader_projection=reader_projection,
                include_reader_surface=state.mode is ProjectionMode.READER,
            )
            if state.mode is ProjectionMode.READER:
                plain_markup = render_plain_result(
                    model, view="stories", query_context=url, translator=translator,
                    sample=reader_projection.sample_data is not None,
                )
                if plain_markup is not None:
                    return _PlainResultPage(plain_markup + _legacy_reader_compat(legacy_markup))
            return legacy_markup
        if state.view is ViewId.STRATEGIES:
            if state.mode is ProjectionMode.READER:
                return render_strategy_reader(
                    model,
                    query_context=url,
                    translator=translator,
                    page=ReaderPage.GENOME,
                    projection=reader_projection,
                )
            return render_genome_view(
                cached,
                query_context=url,
                snapshot_token=model.snapshot_token,
                genome_id=dict(state.context).get("genome_id"),
                translator=translator,
            )
        if state.view is ViewId.CONDITIONS:
            if state.mode is ProjectionMode.READER:
                return render_strategy_reader(
                    model,
                    query_context=url,
                    translator=translator,
                    page=ReaderPage.CONDITIONS,
                    projection=reader_projection,
                )
            return render_genome_conditions_view(
                cached,
                query_context=url,
                snapshot_token=model.snapshot_token,
                genome_id=dict(state.context).get("genome_id"),
                translator=translator,
            )
        if state.view is ViewId.COMPARISON:
            return render_comparison_reader(
                model,
                query_context=url,
                translator=translator,
                projection=reader_projection,
                mode=state.mode,
            )
        if state.view is ViewId.MEMORY:
            if state.mode is ProjectionMode.READER:
                return render_memory_reader(
                    model,
                    query_context=url,
                    translator=translator,
                    projection=reader_projection,
                )
            return render_memory_view(
                cached,
                query_context=url,
                snapshot_token=model.snapshot_token,
                memory_id=dict(state.context).get("memory_id"),
                translator=translator,
            )
        if state.view is ViewId.MEMORY_FAILURES:
            if state.mode is ProjectionMode.READER:
                return render_failure_reader(
                    model,
                    query_context=url,
                    translator=translator,
                    projection=reader_projection,
                )
            return render_memory_failure_view(
                cached,
                query_context=url,
                snapshot_token=model.snapshot_token,
                failure_id=dict(state.context).get("failure_id") or dict(state.context).get("memory_id"),
                translator=translator,
            )
        if state.view is ViewId.FAILURE_PATTERNS:
            if state.mode is ProjectionMode.READER:
                return render_failure_patterns_reader(
                    model,
                    query_context=url,
                    translator=translator,
                    projection=reader_projection,
                )
            return render_failure_patterns_view(
                cached,
                query_context=url,
                snapshot_token=model.snapshot_token,
                translator=translator,
            )
        if state.view is ViewId.EVIDENCE:
            if state.mode is ProjectionMode.READER:
                reader_markup = render_evidence_lineage_reader(
                    model,
                    projection=reader_projection,
                    query_context=url,
                    mode=ReaderTraceMode.READER,
                    translator=translator,
                    page=ReaderPage.EVIDENCE,
                )
                legacy_markup = render_evidence_view(
                    cached,
                    query_context=url,
                    snapshot_token=model.snapshot_token,
                    translator=translator,
                ) + render_evidence_trace(model, query_context=url, translator=translator)
                plain_markup = render_plain_result(
                    model, view="evidence", query_context=url, translator=translator,
                    sample=reader_projection.sample_data is not None,
                )
                if plain_markup is not None:
                    return _PlainResultPage(plain_markup + _legacy_reader_compat(legacy_markup))
                return reader_markup + _legacy_reader_compat(legacy_markup)
            if state.mode is ProjectionMode.RAW:
                return render_evidence_lineage_reader(
                    model,
                    projection=reader_projection,
                    query_context=url,
                    mode=ReaderTraceMode.RAW,
                    translator=translator,
                )
            # The trace reuses the already-read envelope: still exactly one provider read.
            return render_evidence_view(
                cached,
                query_context=url,
                snapshot_token=model.snapshot_token,
                translator=translator,
            ) + render_evidence_trace(model, query_context=url, translator=translator)
        if state.view is ViewId.LINEAGE:
            if state.mode is not ProjectionMode.READER:
                return render_lineage_view(
                    cached,
                    query_context=url,
                    snapshot_token=model.snapshot_token,
                    record_id=dict(state.context).get("record_id"),
                    translator=translator,
                )
            reader_markup = render_lineage_reader(
                model,
                projection=reader_projection,
                query_context=url,
                translator=translator,
            )
            if state.snapshot_token and state.snapshot_token != model.snapshot_token:
                reader_markup += _legacy_reader_compat(render_lineage_view(
                    cached, query_context=url, snapshot_token=model.snapshot_token,
                    record_id=dict(state.context).get("record_id"), translator=translator,
                ))
            return reader_markup
        if state.view is ViewId.EVIDENCE_COMPARISON:
            if state.mode in {ProjectionMode.READER, ProjectionMode.EXPERT, ProjectionMode.RAW}:
                reader_markup = render_comparison_reader(
                    model,
                    query_context=url,
                    translator=translator,
                    projection=reader_projection,
                    mode=state.mode,
                    integration_hook="evidence-comparison-view",
                )
                return reader_markup + _legacy_reader_compat(
                    render_evidence_comparison_view(
                        cached,
                        query_context=url,
                        snapshot_token=model.snapshot_token,
                        translator=translator,
                    )
                )
            return render_evidence_comparison_view(
                cached,
                query_context=url,
                snapshot_token=model.snapshot_token,
                translator=translator,
            )
        if state.view is ViewId.FAILURE_GROUPING:
            return render_failure_grouping_view(
                cached,
                query_context=url,
                snapshot_token=model.snapshot_token,
                translator=translator,
                reader_projection=reader_projection,
                include_reader_surface=state.mode is ProjectionMode.READER,
            )
        if state.view is ViewId.METHODOLOGY:
            return render_methodology_reader(
                model,
                query_context=url,
                translator=translator,
                projection=reader_projection,
                mode=state.mode,
            )
        if state.view is ViewId.HISTORY:
            return render_history_reader(
                model,
                scope=self._scope_for_state(state),
                query_context=url,
                translator=translator,
                projection=reader_projection,
                mode=state.mode,
            )
        if state.view is ViewId.SOURCE_DOCUMENTS:
            return render_source_documents_reader(
                model,
                scope=self._scope_for_state(state),
                approved_directories=self._approved_directories,
                boundary=ApprovedDirectoryBoundary(self._approved_directories),
                query_context=url,
                translator=translator,
                projection=reader_projection,
                mode=state.mode,
            )
        if state.view is ViewId.SEARCH:
            context = dict(state.context)
            return render_search_reader(
                model,
                query=state.query,
                record_type=context.get("record_type") or context.get("type"),
                source_filter=context.get("source"),
                query_context=url,
                projection=reader_projection,
                mode=state.mode,
                translator=translator,
            )
        if state.view is ViewId.PORTAL:
            return render_portal_reader(
                model,
                base_path=url,
                query_context=url,
                projection=reader_projection,
                mode=state.mode,
                translator=translator,
            )
        return None

    @staticmethod
    def _render_source_refs(model: ManagerReadModel, translator: Translator) -> str:
        if not model.source_refs:
            return (
                f'<div class="inspector-item"><dt>{escape(translator.t("shell.sources"))}'
                f'</dt><dd>{escape(translator.t("shell.none_recorded"))}</dd></div>'
            )
        refs = []
        for source in model.source_refs:
            refs.append(
                f'<div class="inspector-item"><dt>{escape(source.owner)} · '
                f"{escape(source.kind)}</dt><dd>"
                f'<span data-opaque-ref="{escape(source.source_id, quote=True)}">'
                f"{escape(source.locator)}</span>"
                f"{opaque_copy_button(source.source_id, translator=translator)}"
                f"</dd></div>"
            )
        return "".join(refs)

    @staticmethod
    def _render_context_refs(state: WebRequestState, translator: Translator) -> str:
        """Expose copy affordances without interpreting opaque query values."""

        candidates = tuple(
            (key, value)
            for key, value in state.context
            if key == "snapshot_token" or key == "opaque_ref" or key.endswith("_id")
        )
        opaque_label = translator.t("shell.opaque_reference")
        return "".join(
            f'<div class="inspector-item"><dt>{escape(key)} · {escape(opaque_label)}</dt><dd>'
            f'<span data-opaque-ref="{escape(value, quote=True)}">{escape(value)}</span>'
            f"{opaque_copy_button(value, translator=translator)}</dd></div>"
            for key, value in candidates
        )

    @staticmethod
    def _render_document(
        state: WebRequestState,
        model: ManagerReadModel,
        item: NavigationItem,
        page: str | None,
        *,
        translator: Translator,
        raw_url: str,
        reader_projection: ReaderProjection,
        plain_reading: bool,
    ) -> str:
        deferred = len(reader_projection.raw_source.raw_bytes) > 1_000_000
        query = urlsplit(raw_url).query
        raw_endpoint = "/api/read-model?" + query
        raw_url_paged = demand_link(raw_url, ui_raw=1, ui_page=None)
        raw_json = (
            '<section class="demand-raw">'
            f'<a href="{escape(raw_url_paged, quote=True)}" data-demand-open>'
            f'{escape(translator.t("shell.view_raw_json"))}</a>'
            f'<a href="{escape(raw_endpoint, quote=True)}" target="_blank" rel="noopener">'
            f'{escape(translator.t("reader.raw_source"))}</a></section>'
            if deferred else
            f'<pre class="raw-json" aria-label="{escape(translator.t("shell.raw_json_aria"), quote=True)}">'
            f'{escape(model.to_json(indent=2))}</pre>'
        )
        label = navigation_label(item.view_id, translator)
        description = navigation_description(item.view_id, translator)
        raw_mode = next(
            (value for key, value in parse_qsl(urlsplit(raw_url).query, keep_blank_values=True) if key == "mode"),
            None,
        )
        legacy_story_modes = {story_mode.value for story_mode in StoryMode}
        search_mode = raw_mode if raw_mode in legacy_story_modes else state.mode.value
        raw_view_selected = state.mode is ProjectionMode.RAW
        reader_plain_shell = plain_reading or (
            state.mode is ProjectionMode.READER and state.view is ViewId.ATLAS
        )
        inspector_hidden = " hidden" if state.panel == "events" or raw_view_selected else ""
        workspace_note = (
            translator.t("plain.result.sample" if reader_projection.sample_data else "plain.result.scope")
            if reader_plain_shell else translator.t(
                "shell.workspace_snapshot" if reader_projection.sample_data else "shell.owner_workspace_snapshot",
                snapshot=model.snapshot_token or translator.t("shell.snapshot_missing")
            )
        )
        drawer_hidden = "" if state.panel == "events" or raw_view_selected else " hidden"
        snapshot = model.snapshot_token or translator.t("shell.snapshot_missing")
        as_of = model.as_of or translator.t("shell.unavailable")
        query_value = escape(state.query, quote=True)
        state_value = escape(state.fixture.value, quote=True)
        # Build GET controls from the original pair list so repeated opaque query
        # parameters are not silently collapsed by the state model.
        raw_pairs = parse_qsl(urlsplit(raw_url).query, keep_blank_values=True)
        context_hidden = "".join(
            f'<input type="hidden" name="{escape(key, quote=True)}" value="{escape(value, quote=True)}">'
            for key, value in raw_pairs
            if key not in {"q", "view", "fixture", "lang", "panel", "mode"}
        )
        lang_hidden = (
            f'<input type="hidden" name="lang" value="{escape(state.lang.value, quote=True)}">'
            if state.lang is not None
            else ""
        )
        panel_hidden = (
            f'<input type="hidden" name="panel" value="{escape(state.panel, quote=True)}">'
            if state.panel
            else ""
        )
        mode_hidden = (
            f'<input type="hidden" name="mode" value="{escape(search_mode, quote=True)}">'
        )
        if page is None:
            page_markup = f"""
      <p class="eyebrow">{escape(translator.t("shell.shared_shell"))}</p>
      <h1 class="page-title" data-page-title tabindex="-1">{escape(label)}</h1>
      <p class="page-intro">{escape(description)} {escape(translator.t("shell.page_intro"))}</p>
      <p class="context-line"><span><strong>{escape(translator.t("shell.view"))}</strong> {escape(state.view.value)}</span>
        <span><strong>{escape(translator.t("shell.fixture"))}</strong> {escape(state.fixture.value)}</span>
        <span><strong>{escape(translator.t("shell.observed"))}</strong> {escape(as_of)}</span></p>
      {render_status_block(model, translator=translator)}
      <section class="hook-surface" data-integration-hook="{escape(item.integration_hook)}">
        <h2>{escape(translator.t("shell.integration_ready"))}</h2>
        <p>{escape(translator.t("shell.placeholder_intro", schema="ManagerReadModel v0"))}</p>
        <span class="hook-label">{escape(translator.t("shell.hook", hook=item.integration_hook))}</span>
      </section>"""
        else:
            page_markup = page
        export_context = _without_query_keys(with_lang(raw_url, None), {"mode"})
        export_control = render_export_control(
            export_context,
            translator=translator,
            view=state.view.value,
            snapshot_token=model.snapshot_token,
            model=None if deferred else model,
        )
        navigation = (
            f'<nav class="nav-strip" aria-label="{escape(translator.t("nav.aria"), quote=True)}">'
            f'{ManagerGUIApp._render_navigation_static(state, raw_url, translator)}</nav>'
        )
        if state.mode is ProjectionMode.READER:
            navigation = (
                f'<div><nav class="nav-strip reading-navigation" aria-label="{escape(translator.t("nav.reading.aria"), quote=True)}">'
                f'{ManagerGUIApp._render_navigation_static(state, raw_url, translator, reading_tasks=True)}</nav>'
                f'<details class="professional-navigation" hidden aria-hidden="true"><summary>{escape(translator.t("nav.professional"))}</summary>'
                f'{navigation}</details></div>'
            )
        language_switcher = ManagerGUIApp._render_language_switcher(state, raw_url, translator)
        mode_context_url = ManagerGUIApp._reader_mode_context_url(state, raw_url)
        reader_mode_switch = render_mode_switch(
            mode_context_url,
            locale=state.locale.value,
            aria_label=translator.t("shell.reader_mode_aria"),
            labels={
                mode.value: translator.t(f"reader.mode.{mode.value}")
                for mode in ProjectionMode
            },
            current_attribute="true",
        )
        reader_contract = render_reader_contract(
            reader_projection, state.mode,
            deferred_url=demand_link(raw_url, ui_reader=1) if deferred else None,
        )
        sample_banner = render_sample_banner(
            reader_projection,
            locale=state.locale.value,
            text=translator.t("plain.result.sample" if plain_reading else "reader.sample.banner.fixed"),
        )
        snapshot_markup = (
            f'<span data-opaque-ref="{escape(snapshot, quote=True)}">{escape(snapshot)}</span>'
            f"{opaque_copy_button(model.snapshot_token, translator=translator)}"
            if model.snapshot_token
            else escape(snapshot)
        )
        snapshot_hidden = (
            ' hidden aria-hidden="true"'
            if state.mode is ProjectionMode.READER and state.view is ViewId.ATLAS
            else ''
        )
        return f"""<!doctype html>
<html lang="{state.locale.html_lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#18343a">
  <title>{escape(translator.t("shell.title", view=label))}</title>
  <style>{CSS}</style>
</head>
<body>
<a class="skip-link" href="#main-content">{escape(translator.t("shell.skip_to_workspace"))}</a>
<div class="app-shell">
  <header class="topbar">
    <a class="brand" href="{escape(ManagerGUIApp._static_link(state, raw_url), quote=True)}" aria-label="{escape(translator.t("shell.brand_home"), quote=True)}">
      <span class="brand-mark" aria-hidden="true">M</span><span class="brand-name" translate="no">{escape(translator.t("shell.brand"))}</span>
    </a>
    <div class="topbar-meta">
      <span class="workspace-note">{escape(workspace_note)}</span>
      <span class="read-only-badge" aria-label="{escape(translator.t("shell.read_only_aria"), quote=True)}">{escape(translator.t("shell.read_only"))}</span>
      {language_switcher}
      {reader_mode_switch}
    </div>
    <form class="search-form" role="search" action="/" method="get" aria-label="{escape(translator.t("shell.global_search"), quote=True)}">
      <label class="sr-only" for="global-search">{escape(translator.t("shell.global_search"))}</label>
      <input class="search-input" id="global-search" name="q" value="{query_value}"
        placeholder="{escape(translator.t("shell.search_placeholder"), quote=True)}" autocomplete="off">
      <input type="hidden" name="view" value="{escape(state.view.value, quote=True)}">
      <input type="hidden" name="fixture" value="{state_value}">{lang_hidden}{context_hidden}{panel_hidden}{mode_hidden}
    </form>
  </header>
  {navigation}
  <div class="workspace">
    <main id="main-content" class="main-column" tabindex="-1">
      {sample_banner}
      {page_markup}
      <div class="panel-actions" aria-label="{escape(translator.t("shell.shared_panels"), quote=True)}">
        <button class="panel-button" type="button" data-panel-target="inspector" aria-controls="inspector" aria-expanded="{str(not inspector_hidden).lower()}">{escape(translator.t("shell.open_inspector"))}</button>
        <button class="panel-button" type="button" data-panel-target="events" aria-controls="event-drawer" aria-expanded="{str(state.panel == 'events').lower()}">{escape(translator.t("shell.open_events"))}</button>
        {export_control}
      </div>
      <p id="copy-status" class="copy-status" role="status" aria-live="polite"></p>
    </main>
    <aside class="inspector" id="inspector" tabindex="-1"{inspector_hidden} aria-labelledby="inspector-title">
      <div class="panel-heading"><h2 id="inspector-title">{escape(translator.t("shell.inspector"))}</h2><span class="panel-kicker">{escape(translator.t("shell.read_context"))}</span></div>
      <dl class="inspector-list">
        <div class="inspector-item"><dt>{escape(translator.t("shell.read_model"))}</dt><dd>manager-read-model.v0</dd></div>
        <div class="inspector-item"><dt>{escape(translator.t("shell.status"))}</dt><dd>{escape(model.availability.status.value)}</dd></div>
        <div class="inspector-item"{snapshot_hidden}><dt>{escape(translator.t("shell.snapshot"))}</dt><dd>{snapshot_markup}</dd></div>
        <div class="inspector-item"><dt>{escape(translator.t("shell.observed_at"))}</dt><dd>{escape(as_of)}</dd></div>
        {ManagerGUIApp._render_context_refs(state, translator)}
        {ManagerGUIApp._render_source_refs(model, translator)}
      </dl>
      <div class="panel-actions"><button class="panel-button" type="button" data-panel-target="events" aria-controls="event-drawer" aria-expanded="{str(state.panel == 'events').lower()}">{escape(translator.t("shell.view_raw_json"))}</button></div>
    </aside>
  </div>
  <aside class="event-drawer" id="event-drawer" tabindex="-1"{drawer_hidden} aria-labelledby="event-title">
    <div class="panel-heading"><h2 id="event-title">{escape(translator.t("shell.events_raw_json"))}</h2><button class="panel-button drawer-close" type="button" data-close-panels aria-label="{escape(translator.t("shell.close_panels"), quote=True)}">{escape(translator.t("shell.close"))}</button></div>
    {raw_json}
  </aside>
</div>
{render_js(translator=translator)}
{reader_contract}
</body>
</html>"""

    @staticmethod
    def _reader_mode_context_url(state: WebRequestState, raw_url: str) -> str:
        """Keep the legacy Story selector while adding a Reader mode link."""

        if state.view is not ViewId.STORIES:
            return raw_url
        pairs = parse_qsl(urlsplit(raw_url).query, keep_blank_values=True)
        if not any(key == "mode" and value in {item.value for item in StoryMode} for key, value in pairs):
            return raw_url
        retained = [(key, value) for key, value in pairs if key != "mode"]
        if not any(key == "story_mode" for key, _ in retained):
            retained.append(("story_mode", state.story_mode.value))
        return urlunsplit(urlsplit(raw_url)._replace(query=urlencode(retained)))

    @staticmethod
    def _render_language_switcher(
        state: WebRequestState, raw_url: str, translator: Translator
    ) -> str:
        """Render a no-JavaScript switcher while preserving the raw query state."""

        aria_label = translator.t("shell.language")
        labels = {
            Locale.ZH_CN: translator.t("shell.language_zh"),
            Locale.EN: translator.t("shell.language_en"),
        }
        choices: list[str] = []
        for locale in (Locale.ZH_CN, Locale.EN):
            label = labels[locale]
            if locale is state.locale:
                choices.append(
                    f'<span lang="{locale.html_lang}" aria-current="true">'
                    f"{escape(label)}</span>"
                )
                continue
            href = with_lang(raw_url, locale)
            choices.append(
                f'<a lang="{locale.html_lang}" hreflang="{locale.html_lang}" '
                f'href="{escape(href, quote=True)}">{escape(label)}</a>'
            )
        return (
            f'<nav class="language-switcher" aria-label="{escape(aria_label, quote=True)}" '
            'data-language-switcher>'
            + '<span class="language-switcher-label" aria-hidden="true">·</span>'.join(choices)
            + "</nav>"
        )

    @staticmethod
    def _static_link(state: WebRequestState, raw_url: str) -> str:
        normalized_url = with_lang(raw_url, state.lang)
        pairs = parse_qsl(urlsplit(normalized_url).query, keep_blank_values=True)
        pairs = [(key, value) for key, value in pairs if key not in {"view", "fixture"}]
        pairs.extend((("view", ViewId.ATLAS.value), ("fixture", state.fixture.value)))
        return "/?" + urlencode(pairs)

    @staticmethod
    def _render_navigation_static(
        state: WebRequestState, raw_url: str, translator: Translator, *, reading_tasks: bool = False
    ) -> str:
        normalized_url = with_lang(raw_url, state.lang)
        raw_pairs = parse_qsl(urlsplit(normalized_url).query, keep_blank_values=True)
        context = [
            (key, value)
            for key, value in raw_pairs
            if key not in {"view", "fixture"}
        ]
        links = []
        task_views = (
            ViewId.ATLAS, ViewId.STORIES, ViewId.STRATEGIES,
            ViewId.MEMORY, ViewId.METHODOLOGY, ViewId.PORTAL,
        )
        for item in NAVIGATION:
            if reading_tasks and item.view_id not in task_views:
                continue
            current = item.view_id is state.view
            href_values = [("view", item.view_id.value), ("fixture", state.fixture.value), *context]
            href = "/?" + urlencode(href_values)
            if reading_tasks:
                label = translator.t(f"nav.reading.{item.view_id.value}")
                links.append(
                    f'<a class="reading-task-link" href="{escape(href, quote=True)}" '
                    f'aria-current="{"true" if current else "false"}">{escape(label)}</a>'
                )
                continue
            label = navigation_label(item.view_id, translator)
            description = navigation_description(item.view_id, translator)
            links.append(
                f'<a class="nav-link" data-nav-link href="{escape(href, quote=True)}" '
                f'aria-current="{"page" if current else "false"}" '
                f'aria-label="{escape(label, quote=True)}" '
                f'title="{escape(description, quote=True)}">'
                f'<span class="nav-short" aria-hidden="true">{escape(item.short_label)}</span>'
                f'<span class="nav-label">{escape(label)}</span></a>'
            )
        return "".join(links)


__all__ = ["ManagerGUIApp", "WebRequestState"]
