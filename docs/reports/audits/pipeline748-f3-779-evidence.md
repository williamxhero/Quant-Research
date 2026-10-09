# PIPELINE748 F3 (#779) Read-Only Acceptance Evidence

Status: **partial; real sidecar-blocked behavior and absolute zero-write criterion remain unproven**.

Observation date: 2026-10-09 (UTC). This report records the current integrated candidate and the evidence collected in isolated worktrees. No merge was performed.

## Frozen inputs and baseline

- QuantResearch / Manager GUI revision: `cde32879073811dd94f4a2f9bc631fe3e803480c` (`fix(manager-gui): defer conditional package API preflight`), isolated worktree `worktree-pipeline748-f3-779`.
- StrategyWorkspace revision: `e4e21afd594c7b9bd78910c27aab460babf7c9e8` (F1 merged owner implementation), isolated worktree `worktree-pipeline748-f3-779-sw`.
- Integrated launch used Python 3.12.13, Manager GUI 0.1.0 and StrategyWorkspace 0.2.0, both loaded from the uv isolated environment's `site-packages`; neither source checkout nor fixture provider supplied the live HTTP responses.
- Supported command shape was the F2 dual-source command: `uv run --no-project --isolated --python 3.12 --refresh-package quantresearch-manager-gui --refresh-package strategy-workspace --with "<manager-gui>[workspace]" --with "<strategy-workspace>" --default-index https://mirrors.aliyun.com/pypi/simple/ python -I -m manager_gui.web --provider workspace --workspace-root "<real workspace>" --port 0`.
- StrategyWorkspace baseline: focused tests `tests/test_s2_t2_price_limit_controls.py`, `tests/test_matched_r7_provenance.py`, and `tests/test_matched_r8_provenance.py`: **11 passed**. The full owner suite with its documented missing G0 oracle fixture excluded: **11 passed**. `ruff check .` and wheel/sdist build passed.
- QuantResearch baseline: Manager GUI complete package suite with the local StrategyWorkspace source and isolated declared test dependencies: **2032 passed**. Manager GUI Ruff, wheel/sdist build, and `compileall` passed.

## Real workspace observation

The real workspace path was used only as the `--workspace-root` for the documented read-only launch and was never initialized, migrated, checkpointed, cleaned, or otherwise intentionally mutated. No commands targeted its database or sidecars directly.

A full recursive inventory included hidden entries, directories, files, locks, and sidecar-name matches. Each file record includes relative path, object type, byte length, SHA-256, nanosecond mtime/ctime, before/after stat stability, and read errors. Detailed inventories and raw HTTP logs stay in local `.runtime/f3-779/` and are not committed because they contain private path and workspace metadata.

- Before scan: `2026-10-09T05:43:28.219399+00:00` through `05:43:33.621886+00:00`; **991 entries**: 753 files and 238 directories; **0 scan errors**, 0 unstable entries. The only lock-named entry was `locks/writer.lock`. No `-wal`, `-shm`, or `-journal` sidecar was present.
- Live run: `2026-10-09T05:53:26Z` through `05:56:27Z`. Health and all 17 routes returned HTTP 200. HTML responses contained no fixture/sample marker. The extra `/?view=atlas&workspace_retry=1` request also returned HTTP 200 and did not switch provider. The browser warning, manual retry, and auto-retry indicators were absent because no blocked sidecar state occurred.
- Final scan after successful integrated run: `2026-10-09T06:21:53.830785+00:00` through `06:21:58.176835+00:00`; again **991 entries**, 0 scan errors. Relative to the initial inventory: **0 added, 0 removed, 0 changed** across type, bytes, SHA-256, mtime, and ctime.

This proves that the sampled read-only invocation did not leave a persistent filesystem difference detectable by the full before/after inventories. It does **not** prove no transient create/delete or write-and-restore occurred. No OS-level file operation audit was enabled. The sidecar-blocked page path and recovery during a real sidecar window were not observed.

## Natural sidecar timeline

At every live-run sample before start, after start, after HTTP reads, at +10s intervals through +60s, and after process exit, the recursive sidecar-name scan found no `-wal`, `-shm`, or `-journal`. There is no real-workspace appearance/disappearance event to classify. The earlier 2026-10-09 observations quoted in issues #776/#779 were not reused as this run's evidence.

User-owned writer activity was not monitored or attributed during the live window. No statement is made about who caused any prior or concurrent workspace change. Empty WAL, non-empty uncheckpointed WAL, rollback journal, a sidecar appearing mid-read, and real-window recovery are **not observed in the real workspace**.

## Isolated public-API scenarios

Temporary workspace: `.runtime/f3-779/isolated-public-api-workspace`, outside the real workspace. It was created through `WorkspaceClient.init()` and populated only through `WorkspaceClient.publish_record()` with public artifact inputs. No database or sidecar bytes were directly edited.

- Three stable read-only client constructions and `list_records()` calls returned known data; full inventory before/after was identical: 6 entries, 0 additions/removals/changes, 0 scan errors.
- During concurrent public writes, natural `workspace.sqlite3-wal` and `workspace.sqlite3-shm` files appeared. Samples included a 32-byte WAL and later a 12,392-byte WAL; sizes alone are not treated as commit evidence.
- Across the polling window, 21 read attempts returned known snapshots and 15 returned the structured `workspace_unsafe_read` refusal. A read attempted during startup just before sidecar enumeration also refused. No fixture fallback occurred.
- The public writer ended with `OperationalError: attempt to write a readonly database`, consistent with the owner read view's Windows share-mode protection preventing a writer from changing the pinned database while the read handles are held. This limits throughput/concurrency and is not evidence that all attempts were writes by a user.
- After the writer exited, an explicit read-only client again returned **2 records** despite WAL/SHM filenames remaining present. The owner implementation verifies WAL contents against the main database and refuses unverifiable/pending state; this observed isolated sample alone does not exercise an uncheckpointed committed transaction.
- The isolation workload did not force empty SHM, a non-empty WAL with an unmerged committed transaction, a mid-read sidecar transition, or a browser-visible warning/retry/recovery sequence. These remain uncovered.

## Test and regression results

Focused GUI test command:

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src uv run --directory manager-gui --no-project --with pytest python -m pytest -q src/manager_gui/test_web.py src/manager_gui/test_interaction.py`

Result: **pass**.

Integrated complete Manager GUI suite:

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src uv run --no-project --isolated --python 3.12 --with pytest --with hypothesis --with "<manager-gui>[workspace]" --with "<strategy-workspace>" python -m pytest -q manager-gui`

Result: **2032 passed**.

Owner focused/full suite (with the repository's missing G0 oracle fixture excluded): **11 passed**. The unfiltered owner collection cannot run because the expected sibling `apex-research/tests/fixtures/g0` directory is absent in this checkout.

Exact root `uv run pytest -q` cannot collect because the environment lacks `strategy_workspace` and `apex_research` registry packages. With the owner-dependent GUI files and installed-package test excluded, root regression result was **1699 passed, 10 failed, 2 skipped**. The 10 failures are environment/evidence-dependent installed-wheel path and local docs/evidence fixtures absent from this worktree; this run did not create a clean, full root baseline and is not claimed as a passing full regression. Their IDs and output remain in the local command transcript; no tests were edited or skipped in committed code.

The exact GUI project command `uv run --directory manager-gui pytest -q` also fails dependency resolution because `strategy-workspace>=0.2.0` is a local source package, not present in the configured registry. The integrated local-source command above is the supported verification route.

## Evidence boundary and open acceptance items

| Claim | Evidence | Result |
| --- | --- | --- |
| F1/F2 integrated versions and interpreter are fixed | revisions, package metadata and Python 3.12.13 readback | observed |
| No fixture fallback during real no-sidecar reads | all 17 route responses lacked fixture markers | observed for this window |
| Persistent real-workspace filesystem state unchanged | recursive inventory with SHA-256 and ns mtime/ctime, before/after | observed; not an absolute no-write audit |
| Real sidecar-blocked GUI is actionable | no sidecar occurred during live window | not observed |
| Real recovery after sidecar disappearance | no real blocked interval occurred | not observed |
| Isolated WAL/SHM refusal and later owner recovery | concurrent public-API writer/read experiment | observed, with a public writer blocked by read handle |
| Empty sidecar, unmerged committed WAL, mid-read transition | not safely forced via the public API; no real occurrence | not observed |
| No transient write/create/delete/write-back on real root | no OS-level audit available/enabled | not proven |

This report is evidence for Hermes review, **not an unconditional F3 acceptance**. The live blocked-window criteria and absolute zero-write audit remain open. Do not manufacture real sidecar state, stop a user writer, or infer those conclusions from isolated tests.
