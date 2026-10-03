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
```

The command emits one JSON `ManagerReadModel v0` envelope. Fixtures are
synthetic and do not stand in for a connected data gate.

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
page-specific envelope. T1 is the only implementation in this change.

| Slice | Owner | Dependency | Read-model contract |
| --- | --- | --- | --- |
| S1 / T1 base contract | `manager-gui` | none | defines v0 |
| S1 / T2 Atlas and Research Story | `manager-gui` | T1 plus approved public read seams | v0 |
| S2 Genome and conditions | `manager-gui` | T1; Apex public read seam | v0 |
| S3 Memory and failure knowledge | `manager-gui` | T1; Apex public read seam | v0 |
| S4 Evidence, lineage, comparison | `manager-gui` | T1; owner-published evidence/read seams | v0 |
| S5 Methodology, history, source documents | `manager-gui` | T1; document-index seam | v0 |
| S6 Search, portal, accessibility | `manager-gui` | T1 and S2–S5 read seams | v0 |

No later slice is implemented here. The package remains independently
runnable with fixtures while those public seams are pending.
