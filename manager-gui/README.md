# Manager GUI owner package

`manager-gui` is the independent QuantResearch workspace owner for the first
Manager GUI slice. It is a local, read-only contract package; it does not
implement Apex Research, Quant Runtime, Strategy Workspace, or Strategy
Reporting domain behavior.

## Package and commands

The package is a standalone Python 3.11 project with no production
dependencies. From the QuantResearch repository root, run:

```console
# Focused S1 test suite and full package regression suite
uv run --directory manager-gui pytest -q

# Lint the package (the source tree is intentionally dependency-free)
uv run --directory manager-gui ruff check .

# Build the isolated wheel and source distribution
uv build --directory manager-gui

# Temporary type check (keeps mypy out of production dependencies)
uv run --directory manager-gui --with mypy mypy --python-version 3.11 src

# Full S5 verification helpers
uv run --directory manager-gui pytest -q
uv run --directory manager-gui ruff check .
python -m compileall -q manager-gui/src
uv run --directory manager-gui python -m manager_gui --fixture complete --pretty

# Start the integrated, fixture-backed WebUI shell
uv run --directory manager-gui manager-gui-web --fixture complete --port 8765
# Equivalent module invocation
uv run --directory manager-gui python -m manager_gui.web --fixture complete --port 8765
```

Open `http://127.0.0.1:8765/`. The shared shell mounts Atlas, Research Story,
Genome, Genome Conditions, Genome Comparison, Memory, Memory Failures,
Failure Patterns, Methodology, History, and Source Documents:

- `/?view=atlas&fixture=complete` renders the Atlas hook;
- `/?view=stories&fixture=complete&mode=evidence` renders the Story hook;
- `/?view=strategies&fixture=complete&genome_id=genome-fixture-1` renders the Genome hook;
- `/?view=strategy-conditions&fixture=complete&genome_id=genome-fixture-1` renders condition evidence;
- `/?view=strategy-genome-comparison&fixture=complete&left_genome_id=genome-left&right_genome_id=genome-right` renders comparison;
- `/?view=methodology&fixture=complete&scope=A0` renders the versioned method archive;
- `/?view=history&fixture=complete&scope=S3` renders source-recorded history;
- `/?view=source-documents&fixture=complete&scope=CPA` renders the approved document index;
- `/?view=memory&fixture=complete&memory_id=memory-fixture-1` mounts the S3-T1 Memory catalog/detail hook;
- `/?view=memory-failures&fixture=complete&failure_id=memory-fixture-1` mounts the Memory failure/lineage projection;
- `/?view=failure-patterns&fixture=complete&pattern_id=pattern-fixture-1` mounts ordinary failures and explicitly Derived patterns.

The fixture-backed path is read-only and preserves `fixture`, `scope`, `panel`, `q`,
`snapshot_token`, Atlas/Memory/failure filters, story root identifiers, `record_id`,
`document_id`, and `mode` in stable links. The shared top bar, navigation, read-only badge, status
block, Inspector, and raw JSON drawer remain owned by the shell. Methodology links
its explicit document and record references to Source Documents and History; History
links source artifacts, records, and documents; Source Documents links record
citations and reverse citations in both directions. No write or mutation route is
exposed: `POST` requests return `405 Allow: GET, HEAD`.

The command emits one JSON `ManagerReadModel v0` envelope when using the
contract entry point. Fixtures are synthetic and do not stand in for a
connected data gate.

## ManagerReadModel v0

The envelope is defined in `src/manager_gui/models.py` and contains exactly the
following public fields in addition to its schema identifier:

- `data`: JSON-compatible value from the requested read;
- `source_refs`: stable, public source pointers;
- `as_of`: source observation time, or `null` when unavailable;
- `snapshot_token`: opaque source snapshot identity, or `null`;
- `derivation`: direct/derived/interpreted rule and named inputs;
- `availability`: completeness, status, reason, and retryability;
- `errors`: explicit non-silent limitations or failures.

The machine-readable schemas are exported as
`MANAGER_READ_MODEL_JSON_SCHEMA`, `SOURCE_REFERENCE_JSON_SCHEMA`,
`AVAILABILITY_JSON_SCHEMA`, and `ERROR_JSON_SCHEMA`. The only status values are
`known`, `derived`, `interpreted`, `missing`, `blocked`, `stale`,
`incomparable`, `integrity_failure`, and `api_unavailable`.

## Shared WebUI contract

Shared WebUI code lives under `src/manager_gui/web/`; no Atlas or Research Story
owner behavior is implemented here. `navigation.py` owns URL-stable view IDs
and integration hooks. `status.py` owns reusable rendering for all nine
read-model statuses plus `ready`, `loading`, `empty`, `partial`, and `error`
operational states. `app.py` consumes only `ManagerDataProvider.read` and
renders the shell around the unchanged v0 envelope.

The stable URL query keys are:

- `view`: `atlas`, `stories`, `strategies`, `memory`, `memory-failures`,
  `failure-patterns`, `evidence`, `methodology`, `history`, `source-documents`, or `search`;
- `fixture`: one of the deterministic shell fixture states;
- `scope`: `A0`, `S3`, `CPA`, or `V1.x` on History and Source Documents;
- `panel`: `inspector` or `events` (optional);
- `q`: global search text (optional and currently display-only);
- `mode`: `narrative`, `evidence`, or `timeline` on the Stories route;
- `page` and `page_size`: bounded presentation pagination for already-read entries;
- `record_type`, `state`, `date`, `source`, and `availability` on Atlas;
- `genome_id` on Genome and condition evidence; `left_genome_id` and
  `right_genome_id` on Genome comparison;
- `family`, `stage`, `outcome`, `failure_category`, `subject`, and `campaign` on
  Memory/failure filters; `memory_id`, `failure_id`, and `pattern_id` on detail views;
- `record_id`, `document_id`, `campaign`, `study`, and `strategy_family` are opaque
  object/root context retained by detail and mode links.

All page hooks register or consume a `NavigationItem`, use the public provider seam,
and keep the same `ManagerReadModel v0` envelope. The shell passes a cached copy of
the envelope to hooks that accept a provider, so an integrated route performs one
owner read. The current public hook contract is:

- `manager_gui.web.atlas.render_atlas_view(provider, filters=..., query_context=..., snapshot_token=...)`
  mounts `data-integration-hook="atlas-view"`;
- `manager_gui.web.research_story.render_research_story(model, mode=..., base_path=..., query=...)`
  mounts `data-integration-hook="research-story-view"`;
- `manager_gui.web.methodology.render_methodology_view(provider_or_model, snapshot_token=..., query_context=...)`
  mounts `data-integration-hook="methodology-view"`;
- `manager_gui.web.history.render_history_view(provider_or_model, scope=..., base_path=..., query=..., snapshot_token=...)`
  mounts `data-integration-hook="history-view"`;
- `manager_gui.web.documents.render_source_documents_view(provider_or_model, scope=..., boundary=..., base_path=..., query=..., snapshot_token=...)`
  mounts `data-integration-hook="source-documents-view"`;
- `manager_gui.web.memory.render_memory_view(provider, filters=..., query_context=..., memory_id=..., snapshot_token=...)`
  mounts `data-integration-hook="memory-view"`;
- `manager_gui.web.failure_patterns.render_memory_failure_view(provider_or_model, filters=..., query_context=..., failure_id=..., pattern_id=..., snapshot_token=...)`
  mounts the shared `data-integration-hook="failure-patterns-view"` for formal Memory failure/lineage;
- `manager_gui.web.failure_patterns.render_failure_patterns_view(provider_or_model, filters=..., query_context=..., failure_id=..., pattern_id=..., snapshot_token=...)`
  mounts the same hook for ordinary failures and explicitly Derived patterns.

The S3 routes keep Formal Research Memory, ordinary failure records, and Derived
patterns visibly separate. A missing or zero-entry Memory scope is rendered as
missing/not recorded; blocked, stale, integrity-failure, and API-unavailable
states never get relabeled as empty. Lineage is six-dimensional (campaign,
candidate, run, evidence, artifact, and source document); each absent or blocked
edge remains visibly `Missing / Unconfirmed`. Explicit fixture IDs link Memory to
failure/Derived views and onward to campaign, run, evidence, and source-document
locators. No similarity or LLM promotion, private-storage fallback, dereference,
or mutation endpoint is used. S3 integrated tests cover complete, zero-entry,
empty, partial, blocked, stale, integrity-failure, API-unavailable, missing-lineage,
context-preserving links, and one-read provider audits.

### S3 route integration / exit evidence for #628

The S3 read-only loop is:
`Research Memory → Memory failure/lineage or ordinary failure → explicit Derived
pattern → campaign/run/evidence/source document (or Missing)`. The route hooks
consume the existing `ManagerReadModel v0` envelope and cached shell read, so each
integrated route performs exactly one public provider read. This note records the
S3-T3 exit evidence; it does not close issue #628 and does not implement S4 or S6.

### S2 Genome route integration / exit evidence for #626

The S2-T3 shell mounts the existing read-only page hooks without replacing the
shared document chrome or introducing a second envelope:

- `/?view=strategies&fixture=complete&genome_id=genome-fixture-1` mounts
  `manager_gui.web.genome.render_genome_view` at
  `data-integration-hook="strategy-genome-view"`;
- `/?view=strategy-conditions&fixture=complete&genome_id=genome-fixture-1`
  mounts `manager_gui.web.conditions.render_genome_conditions_view` at
  `data-integration-hook="strategy-genome-conditions-view"`;
- `/?view=strategy-genome-comparison&fixture=complete&left_genome_id=genome-left&right_genome_id=genome-right`
  mounts `manager_gui.web.comparison.render_genome_comparison_view` at
  `data-integration-hook="strategy-genome-comparison-view"`.

The stable Genome query key is `genome_id`; comparison uses
`left_genome_id` and `right_genome_id`. Genome detail links retain fixture,
panel, query, snapshot token, and comparison context when linking to condition
evidence and comparison. Condition evidence links back to Genome and comparison;
comparison links back to both Genome identities and left-side condition evidence.
Published source and lineage locators remain explicit source links, and the
shared Inspector/raw JSON drawer retains the complete `ManagerReadModel v0`
envelope including source refs, as-of, snapshot, derivation, availability, and
errors. No page hook reads private storage or exposes a mutation operation.

S2 integrated fixtures cover complete, empty, partial, blocked, stale,
incomparable, integrity-failure, and API-unavailable routes. Empty Genome and
condition scopes render missing/not-recorded semantics; partial records remain
partial; blocked, stale, incomparable, integrity-failure, and API-unavailable
states remain distinct. The provider audit verifies one `read` call per mounted
resource and no publish/propose/retry/delete/retire/revalidate/create/update/
write method. These checks are the S2 exit evidence for #626; the issue remains
open until the release owner closes it.

S3's Memory and failure modules are mounted through the shared read-only shell.
S4 can consume the stable Memory/failure source, lineage, condition, and comparison
hooks through the same v0 read seam; S3-T3 does not implement an S4 evidence portal.
S6 can compose these hooks for future
search, portal, and accessibility work without changing the route keys or
introducing page-specific envelopes.

Methodology is the canonical methodology-record surface: usage, results, validity
evidence, limitations, failure cases, versions, and superseded state are separate
fields. History admits only explicit source-event times and categories. Source
Documents is an interpreted-document index: document metadata, plans, reports,
retrospectives, future ideas, external sources, and raw evidence never become
canonical facts merely because they are indexed. Each page has explicit boundary
copy and stable links to the related view.

The app remains responsible for the document chrome, top bar, navigation,
read-only badge, shared status/operational-state rendering, Inspector, raw JSON
drawer, and URL state. Page hooks must not add mutation endpoints, infer owner
facts from private storage, or replace the shared Inspector/event drawer.

### S1 exit evidence / integration note for #618

The S1 fixture path is a single read-only loop:
`Atlas object → Research Story mode → explicit source reference`. The `complete`
fixture supplies a campaign, study, strategy family, lifecycle records, story
chapters, and a source locator; `empty`, `partial`, `blocked`, `stale`,
`incomparable`, `integrity_failure`, and `api_unavailable` remain distinct
fixture states on both integrated routes. The integration tests verify the
route markers, stable query/root/filter/mode context, source links, shell chrome,
`/api/read-model`, `/health`, and `405` responses to mutation attempts. The
provider audit verifies that the fixture adapter exposes only `read`; no S1 code
opens SQLite/private storage or calls publish, retry, delete, retire, or
revalidation operations. This note is evidence for issue #618 and does not
close the issue or implement S2–S6.

### S6-T3 common interaction contract / S6-T4 integration hand-off

S6-T3 owns the shared interaction behavior; it deliberately does **not** mount
Search or Strategy Reporting Portal page hooks. The shell continues to render the
Search navigation item as an integration placeholder until S6-T4 mounts the
approved read seams.

- `web/status.py` is the one state vocabulary for all mounted pages. Use
  `render_status_block(model)` for source provenance and
  `render_operational_state(...)` for loading/empty/partial/error presentation.
  `render_common_state(...)` dispatches both forms. Every rendered state keeps
  the machine status and includes stable English plus Chinese accessibility
  labels; blocked, stale, incomparable, integrity-failure, and API-unavailable
  are never relabeled as empty.
- `web/interaction.py` owns pure `opaque_copy_button`, stable `export_url`,
  `current_view_export`, `export_json`, `render_export_control`, and
  `render_alternative_view` helpers. The shell embeds the already-read envelope
  and URL context in the current document; the browser creates a local JSON Blob;
  the UI does not issue a second read and never writes a ledger. `/api/export`
  is a compatibility GET/HEAD read route for external smoke clients only.
- Copy controls carry opaque source IDs and snapshot tokens without
  dereferencing them. Filter reset links use `clear_filters_link` so fixture,
  panel, query, snapshot, presentation mode, and unrelated opaque context stay
  intact. `presentation=graph|table` is reserved for the graph/table hook.
- `web/failure_lineage.py` exposes both a graph hook and a semantic table
  alternative under `data-alternative-view="failure-lineage"`.
  The table is the default keyboard/screen-reader path; page owners may replace
  only the graph panel.
- The server has no mutation routes. `POST`, `PUT`, `PATCH`, and `DELETE`
  receive `405 Allow: GET, HEAD`; providers expose only `read`.

S6-T4 may now, and only now:

1. map `ViewId.SEARCH` to `ManagerDataProvider.read("search", snapshot_token=...)`
   and call `render_search_view` with the cached envelope, preserving `q`, type,
   source, page, panel, snapshot, and opaque query context;
2. add the Portal view ID/route and map it to
   `read("report_source", snapshot_token=...)`, calling `render_portal_view`
   with the same cached envelope; keep source publication and generated artifact
   separate and do not add rebuild/run/publish controls;
3. retain the shared document chrome, status renderer, copy/export controls,
   inspector/raw JSON drawer, URL/query state, one-read provider audit, and
   `405` mutation behavior; add route fixtures for Search and Portal rather than
   changing this T3 interaction contract.

## Read-only boundary

`ManagerDataProvider` in `src/manager_gui/provider.py` exposes one operation:
`read(resource, snapshot_token=...)`. It intentionally has no publish,
propose, retry, delete, retire, revalidation, create, update, or write method.
All source adapters must return the envelope and preserve provenance. No
provider may read private SQLite/storage or use CLI stdout as an internal API.

`src/manager_gui/fixtures.py` supplies deterministic `empty`, `partial`,
`blocked`, `stale`, `incomparable`, `integrity_failure`, and
`api_unavailable` states. The empty state is represented as `missing`; partial
state remains `known` with `complete: false` and an explicit missing-record
error. This prevents “not recorded” from becoming “did not happen”.

## Public seam decisions

The declarations in `src/manager_gui/seams.py` are decisions for later slices,
not implementations of other owners:

| Seam | Owner | Decision in T1 | Until available |
| --- | --- | --- | --- |
| Package catalog | `strategy-workspace` | Consume a versioned public `WorkspaceClient` package-catalog record via `list_records(record_type="package_catalog")` and `get_record`. | Report `api_unavailable`; never read the private `packages` table, SQLite, or scrape CLI output. |
| Historical-document index | `manager-gui` adapter | Use an explicit configured index with stable `document_id`, type, revision, source ref, and relations. | Do not scan arbitrary paths or treat filenames as identity; document interpretation stays `interpreted`. |

These are public-read seams only. T1 does not add an owner API, a database
adapter, a page, a mutation, a retry, or a fallback.

## S5 directory and document boundary

`SourceDocumentsViewModel` consumes an explicit approved document index through
`ManagerDataProvider.read("source_documents")`. It uses stable `document_id`, type,
version, source locator, update time, forward citations, and reverse citations. It
never treats a filename as identity, scans a directory, opens a document, reads
SQLite, or dereferences a private path. URI/fixture locators are renderable public
references. A local `file:` or Windows path is renderable only when it is beneath
an explicitly configured `ApprovedDirectoryBoundary` (for example,
`ManagerGUIApp(..., approved_directories=("D:/approved-documents",))`); otherwise
its locator is withheld and the page reports `boundary-blocked`.

The index keeps `missing`, `version-conflict`, `not-indexed`, `api-unavailable`,
and `boundary-blocked` distinct. A version conflict retains all versions and never
silently chooses the newest one. History and Methodology can link into the Source
Documents route, but a link does not imply that a document interpretation is a
canonical owner fact.

### S5 exit evidence / integration note for #629

The S5 read-only loop is:
`Methodology record → explicit document/record refs → Source Documents ↔ History
record/event → source artifact/document`. Integrated routes preserve the shared
shell, source refs, `as_of`, snapshot token, status/error envelope, raw JSON, and
opaque query context. Deterministic scope fixtures cover `A0`, `S3`, `CPA`, and
`V1.x`; shell fixtures exercise missing, partial, blocked, stale, incomparable,
integrity-failure, and API-unavailable states. Tests verify source-event-only
history, canonical-fact versus document-interpretation boundaries, document and
record navigation, bounded pagination, provider read-only shape, and approved
directory blocking. This evidence does not close issue #629 from the worktree and
does not implement S2, S3, S4, or S6 search/portal behavior.
## Planned Manager GUI S1–S6 ownership

All later slices consume `ManagerReadModel v0`; they do not introduce a second
page-specific envelope. S2–S4 and S6 remain consumers or future owners outside
this ticket; S5 is integrated here through the public document-index seam.

| Slice | Owner | Dependency | Read-model contract |
| --- | --- | --- | --- |
| S1 / T1 base contract | `manager-gui` | none | defines v0 |
| S1 / T2 shared WebUI shell | `manager-gui` | T1 | shared shell, statuses, navigation, inspector, raw JSON |
| S1 / T3 Atlas and Research Story | `manager-gui` | T1/T2 plus approved public read seams | v0 |
| S2 Genome and conditions | `manager-gui` | T1; Apex public read seam | v0 |
| S3 Memory and failure knowledge | `manager-gui` | T1; Apex public read seam | v0 |
| S4 Evidence, lineage, comparison | `manager-gui` | T1; owner-published evidence/read seams | v0 |
| S5 Methodology, history, source documents | `manager-gui` | T1; document-index seam | v0, integrated in S5-T3 |
| S6 Search, portal, accessibility | `manager-gui` | T1 and S2–S5 read seams | v0 |

### S2–S6 consumption contract
`ManagerDataProvider.read(resource, snapshot_token=...)` boundary. A page may add
its own exported renderer and URL-stable `NavigationItem`, but it must:

1. preserve `source_refs`, `as_of`, `snapshot_token`, `derivation`,
   `availability`, and `errors` without guessing missing owner facts;
2. use the shared status renderer and distinguish empty, partial, blocked, stale,
   incomparable, integrity-failure, and API-unavailable states;
3. keep the shared shell's Inspector, raw JSON drawer, read-only badge, and
   query-context behavior rather than introducing a page-specific envelope;
4. expose only approved public reads, with no SQLite/private-storage fallback,
   CLI stdout scraping, mutation method, retry, publish, delete, retire, or
   revalidation call; and
5. keep page-specific facts in the owning slice and publish a stable hook for
   S6 search/portal/accessibility consumption.

S2 consumes Genome/condition reads, S3 consumes Memory/failure reads, S4 consumes
Evidence/lineage/comparison reads, S5 consumes Methodology/History/document-index
reads, and S6 composes those read seams for search and Portal integration. S5-T3
publishes the integration hook and contract; it does not implement S2, S3, S4, or
S6 search/portal behavior.
