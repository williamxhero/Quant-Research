# #408 RM-V1D.3: cross-cache deletion, delivery interruption and end-to-end replay

## Headline

The end-to-end recovery proof this ticket asks for is **implemented against a
real filesystem**, not against another in-memory `del`. A store with two scopes
is written to disk, its rebuildable projections are really deleted with
`Path.unlink` / `Path.rmdir`, its persisted records are really truncated and
really doctored, its append-only delivery journal is really torn mid-write, and
one test recovers the whole thing from a **fresh Python interpreter** that never
saw the objects that wrote it. All seven main acceptance criteria are covered by
passing tests.

**The A0-H02 real-asset slice stays `pending`.** #441 published no round-one
research asset in this repository and #442 confirmed there is no owner-authorized
`ResearchEnginePort` configuration; `A0-ROUND-1`, `A0-ROUND-2` and
`A0-FIXTURES-ORACLE` are all still `pending` in
`docs/research/a0/a0_delivery_index.json`, re-verified at the time of this
commit. There is no real frozen public research asset to delete and recover, so
the A0-H02 contract is proved on #437-*shaped* synthetic fixtures and the
real-asset half is reported as `pending`, exactly as #442 and #404 did. Nothing
here mocks a pass.

## Scope

Two files, standard library only, no new dependency, no service, no client, no
second fact authority:

| File | Role |
| --- | --- |
| `src/quantresearch_acceptance/research_recovery.py` | the recovery seam: a two-scope store on disk, a real delete, and a four-outcome recovery |
| `src/quantresearch_acceptance/_research_recovery_test.py` | 32 tests, all of which touch a real temporary directory |

Every fixture is synthetic and test-only, reusing #401's frozen `_declaration`
(`support-1`, `counter-1`, `experience-1`, `snapshot-2026-09-10`,
`genome-ema-crossback`) and #396's exposure event shapes, so the branch evidence
lines up with #396-#404 rather than forking a new fixture set. No real holdout
sample is read, transmitted or referenced.

## What is genuinely new, versus #396 / #398 / #401 / #404

This matters, because the ticket explicitly says a Hypothesis counterexample is
not a substitute for a real deletion/interruption proof.

| Prior evidence | What it actually did | What #408 adds |
| --- | --- | --- |
| `CTX::test_dropping_every_derived_projection_still_recovers_identity_and_content` | `del`s a Python object, rebuilds from a dict still held in memory | the record is a **file**; the writer object is gone; the rebuild reads bytes off disk |
| `PAG::test_a0_h02_the_same_context_is_recovered_after_the_projection_is_deleted` | same, one module | the Context, the Reporting projection and the Exposure journal are recovered **together**, through one seam, under one current authorization |
| `CUR::test_deleting_the_display_projection_loses_nothing` | same, one module | the display projection is a real file in a real directory that is really removed |
| `MTX::test_u6_rebuild_after_deletion_costs_no_run_llm_call_or_budget` (#404) | two records, in memory, one process | a real `projections/` directory deleted, then recovery in a **separate OS process** |
| `EXP::test_a_torn_tail_leaves_a_prepared_action_uncertain_not_unseen` (#396) | a real torn file — **the template for "real" here** — but for the Exposure module alone | the same torn-tail interruption is driven through the **full chain**, and the recovered Context, reporting boundary and replay coverage are all asserted alongside it |

The two things nobody had done before this ticket:

1. **A real process restart.** `test_u6_a_fresh_python_process_recovers_the_same_identity`
   spawns `sys.executable -c ...`, hands it only the store path and the current
   visibility request, and asserts its published readback is byte-identical to
   this process's. Nothing cached, imported or memoised in the writing
   interpreter is available to it.
2. **An observed, not asserted, "it never read the cache."**
   `test_ac1_the_recovery_never_opens_a_discardable_object` instruments
   `builtins.open` across the whole recovery and asserts no path under
   `projections/` was opened at all.

## The two scopes

Published as frozen tuples on the module, so the discardable list is a contract
rather than a comment.

| Scope | Objects | Rule |
| --- | --- | --- |
| **Discardable** (`<root>/projections/`) | `retrieval_cache.json`, `fts5_index.json`, `lineage_graph.json`, `display_projection.json` | may be deleted at any time; recovery must not notice; **never read by recovery** |
| **Preserved** (`<root>/preserved/`) | `paginated_context.json`, `reporting_projection.json`, `exposure.jsonl`, `manifest.json` | formal Workspace records, exact artifacts, frozen policy / template / manifest; a missing one is `facts_missing`, never something to paper over |

NetworkX is **absent** from this package by #401's decision (re-asserted by
`MTX::test_networkx_is_absent_rather_than_merely_unused`), so the ticket's
"NetworkX in-memory graph" item is represented by the same bounded adjacency
list the rest of the seam uses, and is in the discardable scope.

`exposure.jsonl` is deliberately **not** digested in the manifest: it is an
append-only journal that legitimately grows and that a real interruption
legitimately tears, so freezing a digest over it would turn #396's
`delivery_uncertain` recovery into a false corruption report. Its integrity is
#396's conservative loader instead — which is what `test_ac3_an_unreadable_journal_is_corruption_not_a_clean_slate`
pins down.

## Acceptance criteria, item by item

### 1. Delete the rebuildable projections, recover the same identity, content and reporting boundary

`test_ac1_deleting_every_projection_on_disk_still_recovers_identity_and_boundary`
recovers, deletes, and recovers again, asserting the **entire readback** is
equal before and after — not just the identity.

Observed, from a real run:

```
deleted:  ["projections/display_projection.json", "projections/fts5_index.json",
           "projections/lineage_graph.json", "projections/retrieval_cache.json",
           "projections/"]
status:                     "recovered"
context_identity  (before == after)    sha256:4c9deebf95974bd8b57f7a8da08655e85070fa3454c46996de1af6c2e2ad961c
projection_identity (before == after)  sha256:1caa87ca7720a3da8ba9c4475d88792a7d768a8daa2e8a5d9684be8858d3060c
read_objects:  ["exposure.jsonl", "manifest.json", "paginated_context.json",
                "reporting_projection.json"]
reporting_boundary: ["baseline_condition", "candidate_next_steps",
                     "comparison_condition", "conditional_conclusions",
                     "coverage_limitations", "current_candidate",
                     "current_genome", "evidence_gaps", "key_disagreements",
                     "must_not_claim", "reusable_assets"]
full readback identical before/after: True
```

Also: `test_ac1_the_recovery_never_opens_a_discardable_object` (the `open` audit),
`test_ac1_the_rebuild_seam_has_no_engine_to_spend_through` (the signature is
exactly `{root, visibility_request}` — there is no engine, no read model and no
retrieval callable to spend through), and
`test_ac1_the_discardable_scope_cannot_reach_a_formal_object`.

### 2. Missing facts / permission-restricted / corrupted content are three different safe outcomes

`RECOVERY_STATUSES == ("recovered", "facts_missing", "authorization_restricted",
"content_corrupted")`, pinned by
`test_ac2_the_three_unsafe_outcomes_are_distinct_and_enumerated`.

- `test_ac2_a_deleted_formal_record_is_facts_missing_not_a_rebuild` is
  parametrized over **all four** preserved objects. In every case the retrieval
  cache is still present on disk and still not consulted.
- `test_ac2_a_leftover_cache_cannot_fake_a_complete_rebuild` deletes the formal
  record, asserts the cache genuinely holds all three source ids, and asserts
  the outcome is still `facts_missing`.
- `test_ac2_a_truncated_record_is_content_corrupted_not_a_missing_fact` writes
  back the first half of the real bytes.
- `test_ac2_a_doctored_record_that_still_parses_is_content_corrupted` moves the
  knowledge cutoff in a record that is perfectly valid JSON.
- `test_ac2_a_restricted_reader_gets_a_third_outcome_that_leaks_nothing` makes
  the store both **unauthorized and incomplete**, and asserts the answer is
  `authorization_restricted` carrying no object name, no source id and neither
  identity anywhere in its serialised body.

### 3. Interruption records `delivery_uncertain`, never unseen, never blind-resent, never re-applied

- `test_ac3_a_real_torn_journal_leaves_the_context_uncertain_never_unseen` tears
  the journal mid-record on disk and asserts `torn_tail is True`,
  `context_exposure == "uncertain"`, `resend_allowed is False`,
  `reapplied_confirmed_side_effects is False` — **and** that the Context itself
  still recovers, because an interrupted delivery is not a corrupted store.
- `test_ac3_an_uncertain_delivery_needs_a_public_receipt_and_is_never_resent`
  proves the blind resend (an envelope with no receipt reference) is refused
  outright and the state stays `delivery_uncertain`; only a real public receipt
  moves it to `delivered`.
- `test_ac3_a_duplicate_receipt_event_re_applies_no_side_effect` appends the
  identical event again (readback unchanged) and then the same key with a
  *different* input (refused as a conflict, readback still unchanged).
- `test_ac3_an_uncertain_delivery_gains_no_independent_validation` asserts
  `grants_eligibility is False` on both the recovery readback and the usage
  history.
- `test_ac3_reconciliation_runs_before_any_re_delivery` asserts the published
  `stages` tuple is exactly
  `("reconcile_delivery", "check_current_authorization", "check_formal_facts",
  "check_record_integrity", "rebuild_from_formal_records",
  "redeliver_under_current_authorization")`, so "reconciliation first" is a
  checkable fact rather than a promise.

### 4. Historical replay uses the record of the time only; limited scope is explicit

`test_ac4_a_digest_without_a_body_replays_only_as_limited` runs after the
projections are deleted and asserts `reconstruction == "limited"`,
`declared_coverage == "limited"`, `payload_present is False`, and
`model_invocations == 0`. The recovery calls #396's `replay_exposure_delivery`
with **no** `load_envelope` — the honest position for a recovered store: the
body is not there, so nothing is re-fetched and no model is re-invoked to
manufacture the original request or answer.

`test_ac1_a_recovery_publishes_zero_run_model_and_budget_counts` asserts
`new_backtests == model_invocations == budget_reservations == 0` and
`used_fresh_retrieval is False`, `used_fixture_substitute is False`. These are
structurally true, not merely observed: the seam has no engine parameter.

### 5. Revocation cannot be bypassed by an old store; a correction moves the current brief only

- `test_ac5_revoked_authorization_cannot_be_bypassed_by_an_old_store` — the same
  store recovers for an authorized reader, is `authorization_restricted` for a
  revoked one, and still recovers identically afterwards (the refusal rewrote
  nothing).
- `test_ac5_a_correction_moves_the_current_store_and_not_the_old_one` writes
  **two real stores**, one cutoff apart, publishes an owner correction between
  them, and asserts: the old store's bytes on disk are unchanged, its readback
  is unchanged, the historical projection's `published_corrections` is `[]`, the
  current one carries `correction-408`, and the underlying Context identity is
  the same object in both.

### 6. U1-U6

Per the ticket's instruction not to duplicate: **U1-U5 are already satisfied by
real executed evidence in #399 / #401 / #404 and are cited, not re-run here.**
#404's table records the counters:

| Scenario | legitimate requests | wrongly blocked | runs reused | external calls | Owner |
| --- | --- | --- | --- | --- | --- |
| U1 renamed equivalent | 0 | **0** | 0 | 0 | #399, cited |
| U2 repaired data blocker | 1 | **0** | 0 | 4 | #399, cited |
| U3 new-sample revalidation | 1 | **0** | 0 | 4 | #399, cited |
| U4 single-component comparison | — | — | — | — | #404 `MTX::test_u4_…`, cited |
| U5 source correction | — | — | — | — | #401 `CUR::test_a0_u5_…`, cited |
| **U6 rebuild after deletion** | 1 | **0** | 0 | **0** | **this ticket, real execution** |

The gap #408 closes is U6's *real-execution* half. #404 proved it at contract
level in one process; here the actual commands run are:

```
$ python -m pytest src/quantresearch_acceptance/_research_recovery_test.py -q
32 passed
```

with, inside `test_u6_a_fresh_python_process_recovers_the_same_identity`, a real
subprocess:

```
sys.executable -c "<recover and print the readback>" <store root> <request path>
```

Expected: a `recovered` readback identical to this process's. Actual: identical,
`returncode == 0`.

- **wrongly-blocked legitimate research: 0 of 1** (the authorized recovery is
  never refused; the only refusals are the injected ones).
- **missing-required-counter-evidence count: 0** — the declaration's
  `conditional_conclusions` entry keeps its `required_counter_evidence` through
  the delete-and-recover cycle, which is what the recovered
  `reporting_boundary` shows.
- **run reuse: 0 runs re-executed. external calls: 0. budget reservations: 0**,
  in every branch, because the seam has no engine.
- No effectiveness or savings figure is claimed anywhere in this ticket. The
  safety and eligibility rules are unchanged: `grants_eligibility` is `False` on
  every readback.

### 7. Reporting shows owner facts only; canonical readback; V1 with no optional service

- `test_ac7_the_reporting_boundary_is_owner_facts_with_canonical_readback` —
  two recoveries produce byte-identical canonical JSON, and the boundary is the
  sorted owner-fact field list shown above.
- `test_ac7_the_recovery_needs_no_optional_service_and_no_private_source` parses
  the module's own AST, asserts every import root is in
  `sys.stdlib_module_names`, asserts none of `opa`, `mlflow`, `optuna`,
  `sqlalchemy`, `networkx`, `langgraph` appears — and then really recovers a
  store, here, with none of them running.
- Nothing reads a private database, an ORM object, a run directory or a
  production path. The store lives entirely under pytest's `tmp_path`
  (`test_a0_the_injected_records_stay_inside_the_test_scope` asserts the store
  root is under `tmp_path` and **not** under the repository).

## A0 reference acceptance slice

### A0-H02 — contract proved, real-asset half `pending`

| Half | Status | Evidence |
| --- | --- | --- |
| Contract: delete discardable projections in an isolated environment, recover the same identity / content boundary, read back the snapshot and template of the time, still check current authorization, zero new backtest / LLM / budget | **executed** | `test_a0_h02_the_contract_slice_runs_on_437_shaped_fixtures_only`, plus every AC1 and AC4 test above |
| Real: do the same over **#441/#442's frozen real public research assets** | **`pending`** | there are none — see below |

`test_a0_h02_the_real_asset_slice_is_pending_and_never_mocked` reads
`docs/research/a0/a0_delivery_index.json` and asserts `A0-ROUND-1`,
`A0-ROUND-2` and `A0-FIXTURES-ORACLE` are all `pending`, so this document cannot
drift away from the register. (`/docs` is git-ignored in this repository except
for the force-added `docs/evidence/issue-*.md` files, so the test skips on a
checkout that does not have it.)

Re-verified at the time of this commit, unchanged from what #442 and #404
recorded:

| Row | Status |
| --- | --- |
| `A0-B0-RULES` (#434) | `pending` |
| `A0-FIXTURES-ORACLE` (#437) | `pending` |
| `A0-ROUND-1` (#441) | `pending` — **the real assets this slice was to consume do not exist** |
| `A0-ROUND-2` (#442) | `pending` |
| `A0-ACCEPTANCE-INTEGRATION` (#439) | `observed; unchanged` at `61d2edcb7336407a2c94960a23992e59510e1c98` |

`docs/research/a0/a0_delivery_index.*` was **not modified**, for the same three
reasons #442 gave: `/docs` is git-ignored so an edit would not publish, the row
is owned by "Apex Research / pending owner", and there is no exact version to
backfill.

### A0-P02 — executed

`test_a0_p02_process_interruption_lost_receipt_and_duplicate_on_the_delivery_boundary`
drives all three on a real file at the A0 delivery boundary, in order:

1. **Process interruption** — a torn tail written mid-record; recovery reports
   `context_exposure == "uncertain"`.
2. **Lost receipt** — a `delivery_uncertain` event with `reason: receipt_lost`;
   reconciliation reports it as uncertain with `resend_allowed is False`.
3. **Duplicate event** — the identical event appended again; the readback is
   unchanged, so nothing already confirmed is re-applied.

And the digest-only record supports a `limited` replay at most. The model is
never resampled to fill history.

### Injection stays in test scope; E01/E02 signed off separately

Every correction, revocation and failure injection in this ticket happens under
pytest's `tmp_path`, on synthetic identities.
`test_a0_the_injected_records_stay_inside_the_test_scope` asserts it. **No real
research and no genuine holdout is touched.**

**A0-E01 and A0-E02 remain `not_run`**, unchanged by this ticket, for the reasons
#442 established. A well-executed negative case here is evidence for its own
negative case only; it does not offset the absence of connected E01/E02 evidence,
and nothing in this commit claims otherwise.

### Exact versions and evidence for #443

| Item | Value |
| --- | --- |
| B0 / B1 | **pending** — `A0-B0-RULES` and `A0-B1-DATA-RUN` are both `pending` in the register; no B0 rule set or B1 data run exists to cite |
| Code version | the branch commit SHAs, plus `RECOVERY_STORE_SCHEMA = quant-research.research-recovery-store.v1`, `RECOVERY_MANIFEST_SCHEMA = …-manifest.v1`, `RECOVERY_READBACK_SCHEMA = …-readback.v1` |
| Environment | Windows 11, CPython 3.13, no optional service running, no `.env`, no research-engine configuration |
| Owner evidence | #401's frozen declaration and #396's exposure shapes, reused unchanged; no new owner fact is invented |
| Deleted objects | `projections/display_projection.json`, `projections/fts5_index.json`, `projections/lineage_graph.json`, `projections/retrieval_cache.json`, then `projections/` itself |
| Public identity before / after | context `sha256:4c9deeb…d961c` → unchanged; projection `sha256:1caa87c…3060c` → unchanged; full readback equal |
| External calls / budget | `0` / `0` / `0` in every branch |

Prior valid evidence is reused by citation (U1-U5, the dependency invariants,
the injection invariants); nothing is re-paid for.

## Red / green confirmation

Each invariant was broken, observed to fail, and restored.

| Break | Result |
| --- | --- |
| give `recover_end_to_end` an `engine` parameter | `test_ac1_the_rebuild_seam_has_no_engine_to_spend_through` failed (1 failed, 31 passed) |
| let the facts check fall back to `projections/retrieval_cache.json` | 6 failed, 26 passed — all four `facts_missing` parametrizations plus `…leftover_cache_cannot_fake_a_complete_rebuild` and `…stay_inside_the_test_scope` |
| make a torn / unreadable journal read as a clean slate | 4 failed, 28 passed — `…torn_journal_leaves_the_context_uncertain_never_unseen`, `…unreadable_journal_is_corruption_not_a_clean_slate`, `…digest_without_a_body_replays_only_as_limited`, `test_a0_p02_…` |
| let the restricted answer publish the identity it refused | 2 failed, 30 passed — `…restricted_reader_gets_a_third_outcome_that_leaks_nothing`, `…revoked_authorization_cannot_be_bypassed_by_an_old_store` |
| drop the declared-name guard in `discard_projections` | `test_ac1_the_discardable_scope_cannot_reach_a_formal_object` failed (1 failed, 31 passed) |

Restored: `32 passed`.

## Test evidence

```
python -m pytest src/quantresearch_acceptance -q \
    --ignore=src/quantresearch_acceptance/_spec027_installed_test.py
```

| Run | Result |
| --- | --- |
| before (on `main` at `7725b8b`) | `2 failed, 349 passed` |
| after | `2 failed, 381 passed` |

The two failures are identical by name before and after, and are the pre-existing
ones recorded for #394-#404:

- `_a0_installed_test.py::test_a0_installed_tracer_is_not_source_preferred`
- `_installed_test.py::test_installed_wheel_has_no_source_checkout_precedence`

Both require the five wheels to be installed; they are not.
**+32 tests, zero regressions.**

```
python -m ruff check src/quantresearch_acceptance     # All checks passed!
python -m compileall -q src/quantresearch_acceptance  # clean
```

## What this ticket does not claim

- It does **not** claim A0-H02's real-asset requirement is met. It is `pending`,
  because #441/#442's real public research assets do not exist.
- It does **not** claim A0-E01 or A0-E02 changed. Both remain `not_run`.
- It does **not** claim a real model was invoked, a real backtest was run, or a
  budget was reserved. All three counters are `0`.
- It does **not** claim the offline layer substitutes for connected evidence.
- It does **not** report any efficiency or savings figure.
- It does **not** close #443's roll-up, and it did not wait on #443 or #431.

## Acceptance conclusion

All seven main acceptance criteria of #408 are implemented and covered by
passing tests that perform **real** filesystem deletion, real truncation, real
corruption, a real torn append-only journal and a real process restart —
distinct from, and additive to, the in-memory rebuild proofs of #397, #398,
#401 and #404. A0-P02 is **executed**. A0-H02's contract half is **executed**
and its real-asset half is **`pending`**, matching #442's and #404's honest
partial pattern. The overall A0 sign-off for this ticket is therefore
**PARTIAL**.
