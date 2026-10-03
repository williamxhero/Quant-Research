# Manager GUI owner package

`manager-gui` is the independent QuantResearch workspace owner for the first
Manager GUI slice. It is a local, read-only contract package; it does not
implement Apex Research, Quant Runtime, Strategy Workspace, or Strategy
Reporting domain behavior.

## Package and commands

The package is a standalone Python 3.11 project with no production
dependencies. From this directory:

```console
# Run the fixture-backed contract smoke tests
uv run --group dev pytest

# Check the package source
uv run --group dev ruff check src

# Build the isolated wheel and source distribution
uv build

# Run the read-only fixture entry point
uv run manager-gui --fixture partial --pretty
# Equivalent without installation
python -m manager_gui --fixture api_unavailable
# Start the independently runnable local WebUI shell
uv run manager-gui-web --fixture partial --port 8765
# Equivalent without installation
python -m manager_gui.web --fixture partial
```

Open `http://127.0.0.1:8765/`. The shell is fixture-backed and read-only: it
serves the shared navigation, status/availability rendering, right Inspector,
and bottom raw JSON drawer while later pages are still placeholders. No write
or mutation route is exposed. Query state is stable and bookmarkable, for
example `/?view=evidence&fixture=partial&panel=events&q=campaign`.

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
- `q`: global search text (optional and currently display-only).

T3/T4 views should register or consume a `NavigationItem` and use its
`integration_hook`, call the public provider seam, and keep the same
`ManagerReadModel v0` envelope. They should not add page-specific mutation
endpoints, infer owner facts from private storage, or replace the shared
Inspector/event drawer.
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

No later slice is implemented here. The package remains independently
runnable with fixtures while those public seams are pending.
