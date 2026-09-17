# #398 Pagination, snapshot integrity and deterministic trimming evidence

## Scope

This evidence covers the QuantResearch acceptance seam for #398 (RM-V1C.2),
under the constraints in #398, parent SPEC #385, the R2 policy in #381
(RM-R2-3/4/6 and the shared implementation policy), and the contracts delivered
for #394, #395, #396 and #397. It adds
`quantresearch_acceptance.research_pagination`; it does not add a Pydantic
contract, an FTS5 or vector index, a second Context authority, a database
client, or a network dependency.

All records used here are synthetic, test-only identities, references and
digests. No real holdout sample is read, transmitted, or referenced. No
connected model was invoked. Nothing here claims that an A0 round, a real
provider delivery, a frozen B0, or an E02 real-model run has been executed.

## What existed, and the confirmed absence of Workspace infrastructure

#398's design revision says "复用 Workspace 公共分页/快照；FTS5 仅按需作为可重建
投影". A repository-wide search was run before any code was written:
`grep -ri workspace src/ apex-research/ docs/`, plus
`git log --all --grep='Workspace'`.

What that found, and nothing else:

- `fixtures.py` creates a temporary directory literally named `workspace` for
  SQLite isolation. It is a filesystem path, not a pagination or snapshot
  contract.
- `_spec027_installed_test.py` imports `strategy_workspace` and asserts
  `strategy_workspace.WorkspaceClient` exists. That is an *installed-wheel*
  cross-repo test; `python -c "import strategy_workspace"` fails with
  `ModuleNotFoundError` on this checkout, and that file is ignored in the test
  command below (it fails collection for the missing wheel, exactly as recorded
  for #394-#397).
- `migration.py` maps the legacy scope name `strategy-workspace` to
  `strategy_workspace`. A name, not an implementation.

So there is no Workspace pagination or snapshot primitive in this repository to
reuse. This is a **confirmed absence, not a new ambiguity**: #396's owner
established the same finding and built its own minimal event log rather than
inventing a Workspace, and #397 recorded that `src/` contains exactly one
package. This ticket follows that precedent and builds the minimal deterministic
pagination / snapshot / cursor primitives directly in the `research_*` family,
carrying Campaign / Iteration / Candidate / Genome identities as declared
references so a production Workspace can own storage later without this contract
changing.

`docs/research/a0/a0_delivery_index.md` was re-verified at the time of this
commit: `A0-B0-RULES`, `A0-FIXTURES-ORACLE`, `A0-ROUND-1`, `A0-ROUND-2` and
`A0-FINAL-EVIDENCE` remain `pending`.

## Sibling module rather than an in-place extension, and why

`research_context.py` is already 1382 lines and closes over one complete
concern: *given* a set of declared sources, freeze a bounded Context and
assemble its brief. #398's concern is the layer beneath it: *whether the store
actually handed those sources over*, under a cursor, a snapshot fence and a
budget. The two have different inputs (a declaration versus public page
evidence), different failure vocabularies, and different identities.

So `research_pagination.py` is a sibling in the same package, and it **extends
rather than replaces** #397:

- It calls `freeze_research_context` and keeps the resulting `ResearchContext`
  whole. There is no second declaration parser and no second brief assembler.
- It reads the required / optional split off #397's own `ManifestEntry.role`.
  It does not re-derive it.
- It reuses `_authorization_status`, `_bounded_int`, `_flag`,
  `ContextAssemblyFailure` from `research_context`, and `_token`, `_digest`,
  `_mapping`, `_list`, `_fields_subset`, `_SAFE_DIGEST`,
  `evaluate_visibility_request` from `research_visibility`. `RetrievalRefusal`
  subclasses `ContextAssemblyFailure`, which subclasses `AcceptanceFailure`, so
  the single sanitised domain error is unchanged.
- The paginated identity binds the #397 identity; it does not recompute it.

This also answers the explicit question in the ticket brief about #397's
five-state `CoverageState`. **Those five states were not modified.** #397's
contract is frozen and its tests pin it. Instead the finer pagination-specific
distinctions live in a new, separately versioned `RetrievalState` enum, and
`RETRIEVAL_STATE_CONTRACT` carries a *total* projection from each retrieval
state onto exactly one #397 coverage state. `effective_coverage_state` then
reports whichever of the two is worse under a fixed precedence, so the composed
coverage is never better than either input.

## Delivered contract

### The frozen state contract

`RETRIEVAL_STATE_CONTRACT_ID = "quant-research.research-retrieval-state"`,
`RETRIEVAL_STATE_CONTRACT_VERSION = "v1"`. Nine states, each with a category, a
deliverable flag and its #397 coverage projection:

| State | Category | Deliverable | Projects onto |
| --- | --- | --- | --- |
| `complete` | covered | yes | `complete` |
| `complete_empty` | covered | yes | `complete_empty` |
| `optional_scope_not_exhausted` | bounded | yes | `optional_not_exhausted` |
| `cursor_invalidated` | failure | no | `retrieval_failure` |
| `snapshot_contaminated` | failure | no | `retrieval_failure` |
| `index_unavailable` | failure | no | `retrieval_failure` |
| `retrieval_interrupted` | failure | no | `retrieval_failure` |
| `budget_exhausted` | failure | no | `required_incomplete` |
| `required_lineage_missing` | failure | no | `required_incomplete` |

`RETRIEVAL_STATE_CONTRACT_DIGEST` is the sha256 of that table, and it takes part
in every paginated Context identity: renaming, reordering or re-categorising a
state produces a different Context rather than a silent relabelling. The state
names are read off this table, never spelled from an example payload.

The precedence that picks a state is fixed and documented in `_state`:
structural distrust first (a broken cursor makes every later question
unanswerable), then the snapshot contract, then store availability, then the
budget, and only last can a state describe genuine absence.

### The retrieval plan and the page evidence

`freeze_paginated_research_context` takes one closed-field declaration:
`{"schema", "context", "retrieval": {"plan", "pages"}}`. The plan freezes
`retrieval_id`, `ordering_key`, `trimming_policy`, `policy_version`,
`page_size`, `page_budget`, `record_budget` and the opening cursor
(`cursor_id`, `snapshot_id`, `ordering_key`, `position`, `page_index`) *before*
anything is read. A plan whose `ordering_key` or `trimming_policy` contradicts
the #397 `query_scope` is refused outright, so there is exactly one declared
ordering and one declared trimming rule.

Each page is public evidence: `page_index`, `cursor_in`, `cursor_out`, `status`
(`ok` / `interrupted` / `index_unavailable`), `exhausted`, and records carrying
`source_id`, `sort_key` and `published_at`. Pages are replayed, never re-fetched.

### Order of operations, and why required-ness cannot move

1. The inner #397 Context is frozen. Its manifest roles are now immutable and
   part of a frozen identity.
2. `required_ids` / `optional_ids` are read off that manifest.
3. Only then are pages deduplicated, chained from the opening cursor, checked
   and trimmed.

There is no code path in which a page result can change what counts as required,
because by the time any page is examined the roles are already digested.

### Fail-closed checks

- **Cursor**: `cursor_snapshot_mismatch` (a cursor opened against another
  snapshot), `cursor_ordering_mismatch`, `cursor_cycle`, `unreachable_page` (a
  page whose `cursor_in` the opening cursor cannot reach — including the case
  where the opening cursor matches nothing at all), `conflicting_page_for_cursor`
  (one cursor, two different pages), `page_index_out_of_sequence`,
  `page_over_declared_size`, `record_ordering_violation` (a record that repeats
  or moves backwards in the frozen ordering). All → `cursor_invalidated`.
- **Snapshot**: any record with `published_at` after the frozen
  `knowledge_cutoff` → `snapshot_contaminated`. It is neither kept (which would
  break the snapshot contract) nor dropped (which would shrink the target sample
  without saying so).
- **Store**: `page_index_unavailable` → `index_unavailable`; `page_interrupted`
  → `retrieval_interrupted`.
- **Budget**: `record_budget_insufficient_for_required` or a truncated chain
  with required records still unseen → `budget_exhausted`.
- **Lineage**: an *explicitly exhausted* chain that never returned a required
  record → `required_lineage_missing` with detail
  `required_records_never_paged`.

Every detail token is drawn from the closed `_FAILURE_DETAILS` set and every
manifest reason from `_RECORD_REASONS`; a test asserts both across five
scenarios.

### "Not fully read" is never "does not exist"

`truncated` is true unless the chain ends on an `ok` page with
`exhausted: true`. A truncated chain with required records unseen reports
`budget_exhausted`, never `required_lineage_missing`. Genuine absence is
reachable only from an exhausted chain. For the same reason an empty `pages`
list is a `RetrievalRefusal`, not a `complete_empty` result: a database
returning no rows is not a cross-request snapshot contract, and `complete_empty`
must be earned by an explicit terminal page over an empty declared scope.

### Trimming

The pre-declared trimming policy is applied in one place. Required records are
admitted first and are never candidates for trimming. Optional records are then
admitted in the frozen ordering until `record_budget` is spent; the rest become
`trimmed` with reason `optional_trimmed_by_policy`, and the state becomes
`optional_scope_not_exhausted` with an explicit `optional_trimmed:<id>`
limitation. If the required records alone do not fit, the retrieval refuses
rather than trimming one of them or calling it optional. One level up, #397's
rule still holds unchanged: a conclusion travels with its required support,
counter-evidence and limitations as one unit.

### Identity

`_identity` digests the inner #397 identity (which already carries the snapshot,
query scope, ordering and trimming rule, policy and template version, purpose
and full inclusion / exclusion manifest), the whole retrieval plan, the state
contract digest, the canonical digest-sorted set of supplied pages, the chain
actually walked, and the complete retrieval outcome including the protected-side
entries. Reordering or repeating the same pages cannot change an identity; a
different plan, a different page, a different trimming result or a different
withheld set always does.

### Protected-side disclosure

`audit_readback()` is the owner view and carries the full retrieval manifest.
`readback()` is the consumer view: entries excluded with reason `not_authorized`
are removed entirely and replaced by one
`{"present": true, "reason": "not_authorized"}` marker — no ids, no counts — plus
a `protected_material_withheld` limitation. `deliver_paginated_research_brief`
returns only the consumer view, and only under a *current* #394/#395 gate
decision.

Three delivery outcomes stay distinct and none may impersonate another:

- `{"delivery": "blocked", "reason": "current_authorization_denied", "paginated_identity": null}` — no identity, no retrieval block, no brief.
- `{"delivery": "refused", "reason": "<retrieval state>"}` — identity and state disclosed, `brief: null`.
- `{"delivery": "delivered"}` — brief plus declared limitations.

### Reconstruction

`public_record()` emits the identity plus the canonical declaration echo (the
#397 declaration, the plan, and the frozen pages).
`reconstruct_paginated_research_context` replays it through exactly the same
assembly and refuses unless the rebuilt identity equals the recorded one. There
is no store to open, no index to consult and no "latest" result to re-select:
appending even one newer record to the frozen pages fails identity. A record
whose frozen pages are gone fails loudly rather than being patched with a fresh
query.

## Acceptance criteria mapping

| Criterion | Test evidence |
| --- | --- |
| Within the required scope, cursor / pagination / snapshot / budget / lineage failures are explicitly refused; never silently shrinks the sample, switches source, or downgrades a required item to optional | `test_a_cursor_from_another_snapshot_is_refused`, `test_an_unknown_opening_cursor_is_refused_not_answered_empty`, `test_an_out_of_sequence_page_invalidates_the_cursor`, `test_a_page_that_overflows_the_declared_page_size_is_refused`, `test_a_record_that_moves_backwards_in_the_frozen_ordering_is_refused`, `test_an_interrupted_page_is_refused_and_never_an_optional_miss`, `test_an_unavailable_index_is_refused_and_distinct_from_complete_empty`, `test_a_record_published_after_the_snapshot_is_contamination_not_a_miss`, `test_an_exhausted_page_budget_is_never_reported_as_an_absent_record`, `test_a_required_record_an_exhausted_chain_never_returned_is_missing_lineage`, `test_a_failure_is_never_reclassified_as_optional_after_the_fact`, `test_a_refusal_never_silently_shrinks_the_target_sample`, `test_an_undeclared_record_is_excluded_rather_than_smuggled_in` |
| `complete-empty`, `optional-scope-not-exhausted`, `index-unavailable` / `retrieval-interrupted` have versioned, distinguishable semantics; state names are frozen in the formal contract | `test_the_retrieval_state_contract_is_frozen_and_versioned`, `test_the_state_contract_digest_moves_when_a_state_name_moves`, `test_every_reported_reason_and_detail_comes_from_the_frozen_vocabulary`, `test_an_unavailable_index_is_refused_and_distinct_from_complete_empty`, `test_a_chain_that_never_says_it_is_exhausted_is_truncated_not_complete` |
| Identity is jointly determined by inclusion / exclusion and reasons, query scope / coverage, ordering / trimming policy and source snapshot; output is deterministic and leaks no protected-side information | `test_the_identity_binds_the_plan_the_pages_and_the_outcome`, `test_a_different_ordering_or_trimming_policy_is_a_different_context`, `test_a_plan_that_contradicts_the_declared_policy_is_refused_outright`, `test_protected_material_is_withheld_from_the_consumer_but_binds_the_identity`, `test_a_clean_context_does_not_claim_material_was_withheld`, `test_no_readback_ever_claims_the_whole_store_was_scanned`, `test_page_order_and_repetition_never_change_the_frozen_output` |
| Required complete but optional limited still yields a bounded context with limitations; missing required counter-evidence refuses | `test_required_complete_but_optional_trimmed_produces_a_bounded_context`, `test_trimming_never_drops_a_required_record_to_fit`, `test_a_missing_required_counter_example_still_refuses_a_one_sided_conclusion` |
| Hypothesis covers reordering / duplicate pages, invalid cursor, post-snapshot records, budget boundaries and input ordering; "not fully read" is never "does not exist" | `test_page_order_and_repetition_never_change_the_frozen_output` (30 examples), `test_a_conflicting_duplicate_page_is_always_refused` (30), `test_an_invalid_cursor_is_always_refused` (30), `test_a_post_snapshot_record_is_always_refused` (30), `test_budget_boundaries_never_turn_unread_into_absent` (40) |
| After deleting the full-text / graph / search projections the same Context is recovered from frozen public facts; genuinely missing facts fail explicitly | `test_a_paginated_context_is_rebuilt_from_its_public_record_alone`, `test_dropping_every_projection_recovers_the_same_identity_and_content`, `test_a_record_whose_frozen_pages_are_gone_fails_explicitly`, `test_history_cannot_be_patched_with_a_newer_retrieval_result`, `test_a_tampered_paginated_identity_is_refused`, `test_authorization_denial_and_retrieval_refusal_are_reported_separately` |

### A0 reference acceptance

The A0 fixture oracle (`A0-FIXTURES-ORACLE`, #434 / #437) and `A0-B0-RULES` are
still `pending` in `docs/research/a0/a0_delivery_index.json`, re-verified at the
time of this commit. Following the precedent set for #394-#397, the A0 slice
runs on synthetic, #437-shaped, explicitly test-only records. It asserts contract
shape on frozen stand-ins; it does not claim a frozen B0, a real A0 round, or a
real second-round model delivery. This slice does not wait on #441 / #442 / #443,
and the full real-research-history delete-and-rebuild remains #408's.

- **A0-C02** — `test_a0_c02_a_missing_protection_lineage_blocks_the_round`,
  `test_a0_c02_an_invalid_cursor_or_insufficient_budget_blocks_the_round`,
  `test_a0_c02_required_complete_optional_limited_is_honest_not_empty`,
  `test_a0_c02_a_failed_round_is_never_relabelled_complete_empty`. An A0 V0/V1
  round whose required support is never paged in blocks with
  `required_lineage_missing` and no brief; a cursor from another snapshot blocks
  with `cursor_invalidated`; a record budget too small for the required records
  blocks with `budget_exhausted` and detail
  `record_budget_insufficient_for_required`. When the required scope *is*
  complete and only the optional experience is limited, the result is a bounded
  Context whose conclusion still carries `a0-counter-v1` and
  `a0-limitation-cost`, with `optional_trimmed:a0-experience-v0` stated
  explicitly and `a0-real-round-executed` still in must-not-claim. No failure
  path produces `complete_empty`, and required-ness is never redefined after the
  fact — demoting an undelivered required source to the optional scope yields a
  different identity, so the refusal cannot be reissued under the original one.
- **A0-H02 (this ticket's slice)** —
  `test_a0_h02_the_same_context_is_recovered_after_the_projection_is_deleted`,
  `test_a0_h02_a_latest_reselection_cannot_impersonate_the_frozen_context`,
  `test_a0_h02_authorization_restriction_and_fact_absence_are_separate`. With
  the snapshot, manifest, ordering and template fixed, reordering the delivered
  pages and discarding every derived projection (rebuilding from the public
  record alone) reproduces the identical identity and audit readback. Appending
  a "latest" record to the frozen pages fails reconstruction. An authorization
  restriction returns `{"delivery": "blocked", "reason":
  "current_authorization_denied", "paginated_identity": null}`, while a genuine
  fact absence returns `{"delivery": "refused", "reason":
  "required_lineage_missing"}` naming the unseen required record — two honest,
  separate answers.
- **Frozen submission** —
  `test_a0_the_public_pagination_inputs_and_outputs_are_the_submitted_evidence`
  pins the public pagination inputs (`page_size` 2, `page_budget` 4,
  `record_budget` 3, the ordering key, the trimming policy, the snapshot id)
  against the expected outputs (`pages_read` 3, state
  `optional_scope_not_exhausted`, `trimmed` `["a0-experience-v0"]`, effective
  coverage `optional_not_exhausted`, and the identity). Expected and actual
  values are the test's own literals.
  `test_the_module_opens_no_store_and_makes_no_external_call` reads
  `research_pagination.py` back and asserts it contains no `socket`, `sqlite3`,
  `urllib`, `requests`, `http`, `subprocess` or `open(` — a zero-new-external-call
  record. No manual research content is mixed into this evidence.

## Test evidence

Command, run from `D:\WILL\STOCK\QuantResearch`:

```
python -m pytest src/quantresearch_acceptance -q \
  --ignore=src/quantresearch_acceptance/_spec027_installed_test.py
```

- Before (`main` at `7bb9c55`): **2 failed, 141 passed**.
- After: **2 failed, 187 passed** (+46, all in `_research_pagination_test.py`).

The two failures are identical before and after, by name:
`_installed_test.py::test_installed_wheel_has_no_source_checkout_precedence` and
`_a0_installed_test.py::test_a0_installed_tracer_is_not_source_preferred`. Both
require a no-source installed-wheel environment rather than a source checkout,
as recorded for #394-#397. `_spec027_installed_test.py` still fails collection on
this machine for the missing `strategy_workspace` / `apex_research` wheels, also
as recorded for those tickets; it is ignored in both the before and the after run
and is not counted as #398 evidence. There are no other deltas.

`python -m ruff check src/quantresearch_acceptance` passes, and
`python -m compileall -q src/quantresearch_acceptance` is clean.

Red/green was confirmed for the new logic rather than assumed. Each patch was
applied to `research_pagination.py`, `_research_pagination_test.py` was run, and
the patch reverted:

- `cursor_snapshot_mismatch` and `cursor_ordering_mismatch` dropped from the
  structural-distrust set (a stale cursor no longer fails closed): 3 fail
  (`test_a_cursor_from_another_snapshot_is_refused`,
  `test_an_invalid_cursor_is_always_refused`,
  `test_a0_c02_an_invalid_cursor_or_insufficient_budget_blocks_the_round`).
- The required-record budget check forced to always pass, so required records
  could be trimmed to fit: 3 fail
  (`test_trimming_never_drops_a_required_record_to_fit`,
  `test_budget_boundaries_never_turn_unread_into_absent`,
  `test_a0_c02_an_invalid_cursor_or_insufficient_budget_blocks_the_round`).
- The post-snapshot fence disabled, so contaminating records pass silently:
  2 fail (`test_a_record_published_after_the_snapshot_is_contamination_not_a_miss`,
  `test_a_post_snapshot_record_is_always_refused`).
- A truncated chain allowed to report `required_lineage_missing`, i.e. "not
  fully read" treated as "does not exist": 2 fail
  (`test_an_exhausted_page_budget_is_never_reported_as_an_absent_record`,
  `test_budget_boundaries_never_turn_unread_into_absent`).
- Supplied pages no longer canonically ordered before the identity is taken:
  2 fail (`test_page_order_and_repetition_never_change_the_frozen_output`,
  `test_a0_h02_the_same_context_is_recovered_after_the_projection_is_deleted`).

After restoring the module, all 46 pass again and the suite returns to
2 failed, 187 passed.

`hypothesis` remains the test-only dependency group declared for #395; no new
runtime dependency was added and `research_pagination` itself is standard
library only.

## Acceptance conclusion

The local #398 pagination, cursor-integrity, snapshot-fence, budget and
deterministic-trimming behaviour is verified on synthetic records, together with
the covered A0-C02 and A0-H02 slices. This is engineering and acceptance-seam
evidence only. It does not claim a connected E02 model run, real holdout access,
a frozen B0 sample, research qualification, or profitability.
