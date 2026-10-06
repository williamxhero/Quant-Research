# Reader R6 v1 Exit Evidence

Branch: `claude/spec-699-reader-r6`

## Scope

The global Reader registry contains exactly these 17 mounted routes, in navigation
order: Atlas, Research Story, Strategies, Strategy Conditions, Strategy Genome
Comparison, Memory, Memory Failures, Failure Patterns, Evidence, Lineage,
Evidence Object Comparison, Derived Failure Grouping, Methodology, History,
Source Documents, Search, and Portal.

The automated Reader matrix exercises 17 routes × 11 fixture states × 3 modes
(Reader, Expert, Raw) × 2 locales. It checks the v0 envelope and raw bytes are
unchanged across modes/locales, sample and owner provenance stay separate, all
claims have source references and typed derivation, and gaps are not emitted as
success/failure.

## Checks run on 2026-10-07

| Check | Result |
| --- | --- |
| Focused Reader, S6, interaction, and lineage pytest | PASS |
| Full `uv run --directory manager-gui pytest -q` | PASS |
| Full `uv run --directory manager-gui ruff check .` | PASS |
| `python -m compileall -q manager-gui/src` | PASS |
| `uv build --directory manager-gui` | PASS |
| Installed wheel zh-CN/en smoke | PASS |
| Live HTTP 17-route HTML/API/export smoke | PASS |
| Live HTTP mutation boundary (`POST`, `PUT`, `PATCH`, `DELETE`) | PASS — `405 Allow: GET, HEAD` |
| Full mypy command from the README | BLOCKED by 125 pre-existing type errors in dossier and older Reader modules |

The mypy result is recorded rather than hidden: it was not caused by the R6
files changed in this branch, and no type-check suppression was added. The
focused runtime, lint, build, wheel, and HTTP checks above remain reproducible
from the repository root.

## Boundary evidence

- `/api/read-model` and `/api/export` are byte-stable across `lang` values.
- The embedded Reader contract is UI-only and does not alter the v0 API or export
  payload.
- Fixture pages show the sample-data banner; an owner provider does not.
- Owner text, machine values, source references, as-of values, and snapshots are
  escaped and preserved verbatim.
- No Runtime/run/rebuild/revalidation or private SQLite/storage path is used by
  the web shell.
- All mounted routes are GET/HEAD-only; mutation methods return
  `405 Allow: GET, HEAD`.

The companion `READER_GUIDE.md` contains the mode/truth-state guide, known
limitations, and the manual accessibility checklist for keyboard, screen-reader,
CJK, zoom, graph/table, focus, and responsive-layout review.
