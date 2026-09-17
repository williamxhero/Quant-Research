# #397 Frozen reconstructable bounded research Context and brief evidence

## Scope

This evidence covers the QuantResearch acceptance seam for #397 (RM-V1C.1),
under the constraints in #397, parent SPEC #385, the R2 policy in #381
(RM-R2-3/4/6/7 and the shared implementation policy), and the contracts
delivered for #394, #395 and #396. It adds
`quantresearch_acceptance.research_context`; it does not add a Pydantic
contract, an LLM summarisation layer, a second Context authority, a vector
store, or a network dependency.

All records used here are synthetic, test-only identities, references and
digests. No real holdout sample is read, transmitted, or referenced. No
connected model was invoked. Nothing here claims that an A0 round, a real
provider delivery, a frozen B0, or an E02 real-model run has been executed.

## What existed, and what was extended

The ticket asks to extend an existing frozen bounded context rather than build a
new high-level memory object. A repository-wide search was run before any code
was written: `bounded_context`, `BoundedContext`, `frozen_context`,
`FrozenContext`, `context_identity`, `inclusion_manifest` and `snapshot_id`
across the whole checkout, plus a case-insensitive text search for
"bounded context".

What that found:

- **A specification, not an implementation.**
  `artifacts/research-memory-v1/spec-c.md` (the SPEC-C body behind #385) and
  `README.md` both describe a bounded research context. `spec-c.md` states the
  Implementation Decisions this module realises almost line for line: identity
  over source snapshot, query policy/version, inclusion and exclusion manifests,
  ranking/cut policy, visibility policy, statement/template version and purpose;
  complete-empty as a distinct result from index failure; rebuild from immutable
  public records with discardable caches.
- **A live identity seam with no producer.**
  `research_exposure.ExposureEvent.context_identity` is a `sha256:` digest that
  every exposure event already binds, and `ExposureLog.context_exposure`,
  `usage_history` and `replay_exposure_delivery` all key off it. Until now that
  digest was supplied by the caller: #396 referenced a Context object that this
  repository could not produce or rebuild.
- **No parallel Context store anywhere.** #392 and #393 are closed, but
  `git log --all --grep='#392'` / `--grep='#393'` return no commits in this
  repository; their comparability-relation and source-dependency contracts are
  owned elsewhere, and this module consumes owner-published facts by reference
  rather than re-deriving them. `src/` contains exactly one package,
  `quantresearch_acceptance`.

So the extension is: the Context that #396 already references by identity is now
*derived* from a public declaration in the same package family, reusing the same
primitives. It is the same public contract, not a second one. The digest
`freeze_research_context` produces is accepted verbatim by
`ExposureLog.append` as `context_identity`, which
`test_the_context_identity_is_the_one_an_exposure_event_references` checks by
appending a real `context_prepared` event and reading
`context_exposure(...) == "prepared"` back.

## Reused versus newly built

- **Reused.** The #394/#395 visibility gate (`evaluate_visibility_request`,
  `GateDecision.materials`) is the only authorization check, both for admitting
  a source into the Context and, separately, for `deliver_research_brief` under
  *current* authority. The package's token / digest / field-subset validation
  primitives (`_token`, `_tokens`, `_digest`, `_mapping`, `_list`,
  `_fields_subset`, `_SAFE_DIGEST`) are reused unchanged, so no brief field can
  carry free text. `AcceptanceFailure` remains the single sanitised domain error;
  `ContextAssemblyFailure` subclasses it. The bounded explicit-stack DFS with
  canonically ordered edges mirrors `research_visibility._protection_closure`.
- **Newly built.** The declaration, manifest, coverage and brief objects
  themselves. Frozen dataclasses, `Literal` status enums, standard library only,
  no new runtime dependency. Campaign / Iteration / Candidate / Genome / Package
  / Run identities are carried as declared references, so a production Workspace
  or Orchestrator can own storage without this contract changing.

## Delivered contract

- `freeze_research_context(declaration)` parses a single closed-field
  declaration: `mode`, `purpose`, `query_scope` (campaign, iteration, question,
  ordering rule, trimming rule), `snapshot` (snapshot id, knowledge cutoff,
  corrections version), `policy` (policy id/version, template id/version),
  `budget` (`discussion_budget`, `closure_budget`), `required_closure`,
  `optional_scope` (+ `exhausted`), `sources`, `owner_facts`, `evidence_gaps`,
  `candidate_next_steps`, `conclusions`, `genome_compare` and an optional
  `visibility_request`. Everything is declared before any source is resolved.
- **Identity.** `_identity` digests the mode, purpose, query scope (ordering and
  trimming included), snapshot, policy and template version, budget, optional
  exhaustion, every declared source identity (id, type, content digest,
  provenance ref, publication time, derivation edges) and the complete
  inclusion/exclusion manifest. The declared closure *roots* are deliberately
  not in the digest: the manifest already records, per source, whether it was
  required or optional and whether it was included, so naming a closure by its
  roots and naming it by every transitive member is one Context.
- **Manifest.** Every source the Context ever saw gets one entry: `included`
  with reason `declared_and_approved`, or `excluded` with a reason from a closed
  set — `not_approved`, `not_applicable`, `not_authorized`, `retrieval_failure`,
  `published_after_snapshot`, `outside_declared_scope`. The order of the checks
  matters and is asserted: a retrieval failure is decided before the softer
  reasons, so it can never be relabelled.
- **Closure.** The required-evidence closure is walked as an explicit-stack DFS
  over deduplicated, sorted derivation edges, bounded by the frozen
  `closure_budget`. An exhausted budget, an undeclared hop or an excluded member
  is a *missing* closure, never an empty one.
- **Coverage.** Five distinct states with fixed precedence: `retrieval_failure`,
  `required_incomplete`, `complete_empty`, `optional_not_exhausted`, `complete`.
  `ContextCoverage.as_dict` always reports `declared_scope_only: true` and
  `scanned_full_history: false`, and lists the missing required ids, the
  uncovered optional ids and the retrieval failures separately.
- **Brief.** `BRIEF_FIELDS` is fixed and no field is ever omitted: current
  Candidate, current Genome, baseline condition, comparison condition,
  conditional conclusions, key disagreements, evidence gaps, reusable assets,
  candidate next steps, must-not-claim, coverage limitations. A field is either
  `{"state": "present", ... , "provenance": [...]}` or
  `{"state": "unknown", ...}`. An owner fact with an empty provenance list is
  refused outright, and every value is a safe token, so a sentence cannot be
  smuggled into a field.
- **Assembly units.** A conclusion is delivered only when its required support,
  required counter-evidence and limitations are *all* in the included closure.
  `_assemble_units` fits units to the discussion budget by dropping optional
  units in reverse canonical order; if the required units still do not fit the
  brief becomes `blocked` with
  `discussion_budget_insufficient_for_required_units` and the readback states
  `pagination_owner: "issue-398"`. A non-optional unit whose counter-evidence is
  unavailable blocks with `required_counter_evidence_unavailable`. Under no path
  is a conclusion emitted with its counter-evidence or limitations stripped.
- **Single-component comparison.** `genome_compare` is consumed as published:
  semantic path, change category, verified-unchanged scope, and per-dimension
  alignment for cost, data and execution. Any dimension that is not `aligned`
  (including `unknown`) puts `comparison_gap:<dimension>` at the *head* of the
  evidence gaps with precondition `align:<dimension>`, adds
  `comparability_limited:<dimension>` to the coverage limitations, and adds
  `causal_improvement` to must-not-claim. Every `verified_unchanged:<scope>` and
  the `changed_component:<semantic path>` are carried through verbatim.
- **Suggestions only.** Every next step is emitted with
  `status: "suggestion_pending_approval"`, its provenance, and non-empty
  execution preconditions (an empty precondition list is refused). The brief
  readback asserts `creates_tasks: false`, `reserves_budget: false`,
  `invokes_engine: false` and `grants_eligibility: false`.
- **Historical versus current.** In `historical_reconstruction` mode a source
  published after the snapshot's knowledge cutoff is excluded with
  `published_after_snapshot`; in `current_research` mode the same source is
  included. The two Contexts have different identities.
- **Reconstruction.** `public_record()` emits the canonical declaration echo plus
  the identity; `reconstruct_research_context` replays it through exactly the
  same assembly and refuses unless the rebuilt identity equals the recorded one.
  There is no cached brief, no graph projection and no second authority to
  consult, so deleting every derived projection is a no-op for recovery.
- **Delivery.** `deliver_research_brief` re-checks *current* authorization
  through the #394/#395 gate. A denied reader gets
  `{"delivery": "blocked", "reason": "current_authorization_denied",
  "context_identity": null}` — no brief, no manifest, no identity — and the
  frozen Context is unchanged.

## Acceptance criteria mapping

| Criterion | Test evidence |
| --- | --- |
| Identity includes source snapshot, query scope, policy/template version, purpose, source identity and inclusion/exclusion basis; only approved and applicable sources are included | `test_the_identity_binds_snapshot_scope_policy_purpose_sources_and_manifest`, `test_only_approved_and_applicable_sources_are_included`, `test_a_different_manifest_cannot_share_an_identity`, `test_an_unauthorized_source_is_excluded_by_the_reused_gate` |
| `unknown`, declared-scope complete-but-empty, optional scope not exhausted and retrieval failure are all distinct; full history is never claimed | `test_the_five_coverage_states_are_distinguishable`, `test_a_retrieval_failure_is_never_downgraded_to_an_optional_miss`, `test_an_empty_declared_scope_is_not_a_retrieval_failure`, `test_no_readback_ever_claims_that_full_history_was_scanned`, `test_an_exhausted_closure_budget_is_incomplete_not_empty` |
| The structured brief is reconstructable from public records alone; no parallel Context or independent authority store | `test_a_context_is_reconstructable_from_its_public_record_alone`, `test_dropping_every_derived_projection_still_recovers_identity_and_content`, `test_a_tampered_record_cannot_reproduce_its_identity`, `test_the_context_identity_is_the_one_an_exposure_event_references` |
| Every brief field has provenance or `unknown`; gaps and suggestions carry preconditions; no unauthorized task and no causal/eligibility conclusion | `test_the_brief_carries_every_fixed_field_with_provenance_or_unknown`, `test_an_absent_owner_fact_is_unknown_and_never_invented`, `test_an_owner_fact_without_provenance_is_refused`, `test_a_gap_carries_its_preconditions`, `test_a_next_step_without_preconditions_is_refused`, `test_next_steps_stay_suggestions_and_never_create_a_task`, `test_the_brief_cannot_carry_free_text` |
| Single-component cases preserve known-unchanged items and comparison limitations; a required counter-example that will not fit never yields a one-sided conclusion | `test_a_misaligned_single_component_comparison_reports_the_gap_first`, `test_an_unknown_alignment_is_a_gap_and_not_an_alignment`, `test_a_fully_aligned_comparison_does_not_add_a_causal_claim_or_a_gap`, `test_genome_compare_is_consumed_and_never_recomputed`, `test_a_conclusion_ships_with_its_support_counter_evidence_and_limitations`, `test_a_conclusion_whose_counter_evidence_is_unavailable_is_not_delivered`, `test_a_tight_budget_drops_optional_units_before_required_ones`, `test_a_small_budget_blocks_a_required_unit_instead_of_dropping_its_evidence`, `test_an_optional_unit_missing_its_evidence_is_dropped_not_degraded` |
| Hypothesis covers input ordering, allowed-equivalent representations and post-hoc nested-input changes; graph traversal order does not change the canonical output | `test_input_ordering_never_changes_the_frozen_output`, `test_allowed_equivalent_representations_freeze_to_the_same_context`, `test_changing_a_nested_input_after_freezing_never_changes_the_output`, `test_graph_traversal_order_never_changes_the_canonical_output` (25 examples each) |
| Deleting the graph / search cache recovers the original identity and content; a new correction does not mix into an old Context; current authorization can still restrict delivery | `test_dropping_every_derived_projection_still_recovers_identity_and_content`, `test_a_correction_published_after_the_snapshot_never_joins_a_historical_context`, `test_current_authorization_still_blocks_delivery_of_an_old_context` |

### A0 reference acceptance

The A0 fixture oracle (`A0-FIXTURES-ORACLE`, #434 / #437) and `A0-B0-RULES` are
still `pending` in `docs/research/a0/a0_delivery_index.json`, re-verified at the
time of this commit. Following the precedent set for #394-#396, the A0 slice
runs on synthetic, #437-shaped, explicitly test-only records. It asserts contract
shape on frozen stand-ins; it does not claim a frozen B0, a real A0 round, or a
real second-round model delivery.

- **A0-C01** — `test_a0_c01_second_round_brief_has_every_field_with_provenance_or_unknown`.
  A second-round brief built from A0 V0/V1-shaped frozen samples carries the
  baseline (`a0-v0`) and comparison condition, the supporting and
  counter-evidence of its conclusion as one unit, the method gap
  (`comparison_gap:cost` ahead of the owner's `a0-gap-cost-model`), the reusable
  Package and Run assets, a next step with provenance and preconditions
  (`align:cost`, `approval:owner`) at `suggestion_pending_approval`, and the
  must-not-claim list. Every field reports `present` with provenance or
  `unknown`. `creates_tasks` and `invokes_engine` are both false.
- **A0-M02 (this ticket's slice)** —
  `test_a0_m02_unaligned_cost_keeps_limitations_and_refuses_a_causal_claim` and
  `test_a0_m02_a_tight_budget_never_buys_room_by_dropping_counter_evidence`. A
  single-component Genome difference with cost *not* aligned keeps
  `comparability_limited:cost`, both `verified_unchanged:` scopes and
  `changed_component:genome:sizing/turnover-cap`, adds `causal_improvement` to
  must-not-claim, and still ships the required counter-evidence. Squeezing the
  discussion budget blocks the brief instead of buying room by dropping that
  counter-evidence, and the comparability limitation survives the refusal. Only
  owner-published Genome compare data is consumed.
- **Frozen submission** —
  `test_a0_the_frozen_result_survives_reordering_and_losing_every_projection`
  pins the exact Context identity and readback, then shows that reordering the
  inputs and discarding every derived projection (rebuilding from the public
  record alone) reproduces both unchanged. The Context and template versions are
  carried in the readback (`policy.template_id`,
  `policy.template_version`, `snapshot.*`), and the public input, expected and
  actual values are the test's own literals.

This ticket does not wait on #441 / #442 / #443. Constructing a brief
successfully is **not** a substitute for an actual second-round delivery, which
remains #442's to validate.

## Test evidence

Command, run from `D:\WILL\STOCK\QuantResearch`:

```
python -m pytest src/quantresearch_acceptance -q \
  --ignore=src/quantresearch_acceptance/_spec027_installed_test.py
```

- Before (`main` at `cd9632b`): **2 failed, 98 passed**.
- After: **2 failed, 141 passed** (+43, all in `_research_context_test.py`).

The two failures are identical before and after, by name:
`_installed_test.py::test_installed_wheel_has_no_source_checkout_precedence` and
`_a0_installed_test.py::test_a0_installed_tracer_is_not_source_preferred`. Both
require a no-source installed-wheel environment rather than a source checkout,
as recorded for #394, #395 and #396. `_spec027_installed_test.py` still fails
collection on this machine for the missing `apex_research` wheel, also as
recorded for those tickets; it is ignored in both the before and the after run
and is not counted as #397 evidence. There are no other deltas.

`python -m ruff check src/quantresearch_acceptance` passes, and
`python -m compileall -q src/quantresearch_acceptance` is clean.

Red/green was confirmed for the new logic rather than assumed. Each patch was
applied to `research_context.py`, the suite run, and the patch reverted:

- Required units trimmed to fit the budget by discarding their counter-evidence
  and limitations: 2 fail
  (`test_a_small_budget_blocks_a_required_unit_instead_of_dropping_its_evidence`,
  `test_a0_m02_a_tight_budget_never_buys_room_by_dropping_counter_evidence`).
- Declared sources no longer canonically sorted: 2 fail
  (`test_input_ordering_never_changes_the_frozen_output`,
  `test_a0_the_frozen_result_survives_reordering_and_losing_every_projection`).
- Derivation edges no longer canonically ordered before the walk: 1 fails
  (`test_graph_traversal_order_never_changes_the_canonical_output`).
- Retrieval failure relabelled as `not_applicable`: 2 fail
  (`test_the_five_coverage_states_are_distinguishable`,
  `test_a_retrieval_failure_is_never_downgraded_to_an_optional_miss`).
- A conclusion with unavailable counter-evidence admitted anyway: 1 fails
  (`test_a_conclusion_whose_counter_evidence_is_unavailable_is_not_delivered`).

After restoring the module, all 43 pass again and the suite returns to
2 failed, 141 passed.

`hypothesis` remains the test-only dependency group declared for #395; no new
runtime dependency was added and `research_context` itself is standard library
only.

## Acceptance conclusion

The local #397 bounded-Context freezing, brief assembly, coverage-state and
reconstruction behaviour is verified on synthetic records, together with the
covered A0-C01 and A0-M02 slices. This is engineering and acceptance-seam
evidence only. It does not claim a connected E02 model run, real holdout access,
a frozen B0 sample, research qualification, or profitability.
