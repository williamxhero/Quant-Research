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

# Compile and smoke-test the package without a server dependency
python -m compileall -q manager-gui/src
uv run --directory manager-gui python -m manager_gui --fixture complete --pretty

# Start the integrated, fixture-backed WebUI shell
uv run --directory manager-gui manager-gui-web --fixture complete --port 8765
# Equivalent module invocation
uv run --directory manager-gui python -m manager_gui.web --fixture complete --port 8765
```

Open `http://127.0.0.1:8765/`. S1 mounts Atlas and Research Story into the
shared shell: `/?view=atlas&fixture=complete` renders the Atlas hook and
`/?view=stories&fixture=complete&mode=evidence` renders the Story hook. The
fixture-backed path is read-only and preserves `fixture`, `panel`, `q`, Atlas
filters, story root identifiers, `record_id`, and `mode` in stable links. The
shared top bar, navigation, read-only badge, status block, Inspector, and raw
JSON drawer remain owned by the shell. Atlas object links include a stable
Research Story link; story entries retain explicit source references and show
`Missing / Unconfirmed` when one is not available. No write or mutation route
is exposed: `POST` requests return `405 Allow: GET, HEAD`.

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

- `view`: `atlas`, `stories`, `strategies`, `memory`, `evidence`, `methodology`,
  `history`, or `search`;
- `fixture`: one of the deterministic fixture states;
- `panel`: `inspector` or `events` (optional);
- `q`: global search text (optional and currently display-only);
- `mode`: `narrative`, `evidence`, or `timeline` on the Stories route;
- `record_type`, `state`, `date`, `source`, and `availability` on Atlas;
- `record_id`, `campaign`, `study`, and `strategy_family` are opaque object/root
  context retained by detail and mode links.

T3/T4 views register or consume a `NavigationItem`, use the public provider seam,
and keep the same `ManagerReadModel v0` envelope. S1-T5 mounts the exported
hooks without moving shell ownership into a page module:

- `manager_gui.web.atlas.render_atlas_view(provider, filters=..., query_context=..., snapshot_token=...)`
  reads the Atlas resource and returns a fragment at `data-integration-hook="atlas-view"`.
  The app passes a cached copy of the shell's envelope so the hook does not perform a
  second provider read.
- `manager_gui.web.research_story.render_research_story(model, mode=..., base_path=..., query=...)`
  consumes the already-read Stories envelope and mounts at
  `data-integration-hook="research-story-view"`. `mode` is `narrative`, `evidence`,
  or `timeline`; the shell parses invalid modes as the safe narrative default.
- `manager_gui.web.ATLAS_INTEGRATION_HOOK`, `render_atlas_view`, `StoryMode`,
  `render_research_story`, and `render_research_story_view` are exported from the
  `manager_gui.web` package for the public integration seam.

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

## Planned Manager GUI S1–S6 ownership

All later slices consume `ManagerReadModel v0`; they do not introduce a second
page-specific envelope. T2 implements the shared shell only; domain pages remain
placeholders until their owning slices.

| Slice | Owner | Dependency | Read-model contract |
| --- | --- | --- | --- |
| S1 / T1 base contract | `manager-gui` | none | defines v0 |
| S1 / T2 shared WebUI shell | `manager-gui` | T1 | shared shell, statuses, navigation, inspector, raw JSON |
| S1 / T3 Atlas and Research Story | `manager-gui` | T1/T2 plus approved public read seams | v0 |
| S2 Genome and conditions | `manager-gui` | T1; Apex public read seam | v0 |
| S3 Memory and failure knowledge | `manager-gui` | T1; Apex public read seam | v0 |
| S4 Evidence, lineage, comparison | `manager-gui` | T1; owner-published evidence/read seams | v0 |
| S5 Methodology, history, source documents | `manager-gui` | T1; document-index seam | v0 |
| S6 Search, portal, accessibility | `manager-gui` | T1 and S2–S5 read seams | v0 |

No later slice is implemented here. The package remains independently runnable
with fixtures while those public seams are pending.

### S2–S6 consumption contract

Every later slice consumes the same `ManagerReadModel v0` envelope and the same
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
reads, and S6 composes those read seams for search and Portal integration. None
of these contracts is implemented or simulated by S1-T5.
