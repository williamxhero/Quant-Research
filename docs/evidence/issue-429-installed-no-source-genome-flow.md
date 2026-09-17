# #429 SG-V1D: installed/no-source cross-repository Strategy Genome flow

## Headline

The Strategy Genome **product** is not in this repository. It lives in
`williamxhero/StrategyWorkspace` (confirmed via `gh repo list williamxhero`, and
checked out read-only under `strategy-workspace/` and `.worktrees/` as the
wheel-buildable package `strategy_workspace`), with `QuantRuntime` and
`StrategyReporting` alongside it. Per this repository's ownership boundary —
read across projects, write only through the project that owns the files — **no
file outside `src/quantresearch_acceptance/` and `docs/evidence/` was touched**,
and nothing under `strategy-workspace/` or `.worktrees/` was modified.

What this ticket delivers, therefore, is the **acceptance layer**: the Genome
flow's public contract — stage order, identity algebra, verification binding,
fail-closed consumption, replay discipline and compatibility table — stated as
executable code over #437-shaped synthetic fixtures, exactly as #394–#408 did
for the Research Memory family. 40 new tests, all passing.

Three things are explicitly **not** claimed:

1. **The installed-wheel half is `not_run`.** Re-verified at commit time:
   `python -c "import strategy_workspace"` → `ModuleNotFoundError`, and
   `python -c "import apex_research"` → `ModuleNotFoundError`. The pre-existing
   `_spec027_installed_test.py` and `_a0_installed_test.py::test_a0_installed_tracer_is_not_source_preferred`
   fail here for exactly that honest reason, unchanged by this ticket.
2. **#419 and #422 are cited, never re-measured.** #419's real concurrency/crash
   evidence and the 256 KiB p95 ≤ 250 ms local get/contract-validate/compare
   target, and #422's independent behavioural conformance, can only be measured
   inside StrategyWorkspace. They are recorded in
   `research_genome_flow.CITED_OWNER_EVIDENCE` with the words "NOT re-measured"
   / "NOT re-run" in the citation text itself, and a test asserts that wording
   survives.
3. **A0-E01 and A0-E02 remain `pending`.** #441 landed no commit in this
   repository and #442 confirmed no owner-authorized `ResearchEnginePort`
   configuration exists; `docs/research/a0/a0_delivery_index.json` is still
   `pending`. No synthetic fixture is offered in their place.

## Scope

| File | Role |
| --- | --- |
| `src/quantresearch_acceptance/research_genome_flow.py` | the Genome-flow contract seam: stages, identity, content-addressed store, verification ledger, consumption gate, compatibility table, replay, rollup |
| `src/quantresearch_acceptance/_research_genome_flow_test.py` | 40 tests |

Standard library only. The module's imports are asserted to be a subset of
`{__future__, hashlib, json, collections, dataclasses, typing}` plus this
package's own `core`, so there is **no new dependency**, no Pydantic/BaseModel,
no NetworkX/ORM, no OPA/MLflow/Optuna and no graph or vector service. Hypothesis
stays dev-only (unused here). `pyproject.toml` is unchanged.

## The seven ticket acceptance criteria

Each maps to one `SG-ACnn` item in `GENOME_ACCEPTANCE_ITEMS`, whose evidence
references are resolved against the real test functions by
`test_every_matrix_evidence_reference_resolves_to_a_real_test`.

| Item | Criterion | Evidence class | Key tests |
| --- | --- | --- | --- |
| SG-AC01 | full public golden flow preserves every identity and source relation, using the existing IR not a second DSL | **[proven-in-this-repo]** | `test_the_golden_flow_runs_every_stage_in_order_and_keeps_six_identities`, `test_preparation_is_not_export_and_the_stage_graph_has_no_cycle`, `test_the_candidate_ir_is_stored_verbatim_and_no_second_dsl_appears`, `test_the_three_gates_run_in_their_fixed_order_before_preparation`, `test_identical_payloads_of_different_kinds_never_share_an_identity` |
| SG-AC02 | installed/no-source positive+negative compatibility, equal/different/incomparable, rejection/tombstone/current-permission, no private read | **[proven-in-this-repo]** for contract shape; **[pending-real-asset]** for the wheel half | `test_every_compatibility_case_keeps_its_documented_behaviour`, `test_an_unsupported_major_has_no_adapter_and_no_silent_fallback`, `test_the_genome_seam_imports_no_owner_wheel_and_no_private_storage` |
| SG-AC03 | preparation-only cannot run formally; exact valid verification is reused; changed/stale bindings cannot complete export | **[proven-in-this-repo]** | `test_a_prepared_package_cannot_enter_the_formal_path`, `test_a_sandbox_only_grant_cannot_enter_the_ordinary_formal_path`, `test_an_exact_repeat_reuses_verification_and_runs_no_new_sandbox_work`, `test_any_binding_change_revalidates_instead_of_reusing`, `test_a_stale_binding_cannot_complete_a_formal_consumption`, `test_the_four_qualification_flags_are_independent` |
| SG-AC04 | identity/idempotency: same-content stability, distinct attempt provenance, same-key/different-input rejection, no hash hijack, no tombstone bypass, no cycles | **[proven-in-this-repo]** | `test_a_second_attempt_keeps_the_genome_identity_and_adds_its_provenance`, `test_different_bytes_can_never_take_over_an_existing_identity`, `test_the_same_identity_with_a_different_reference_set_is_rejected`, `test_a_new_attempt_cannot_clear_a_tombstone`, `test_content_addressing_admits_no_self_reference_and_no_cycle`, `test_a_rejected_record_is_terminal_and_distinct_from_a_tombstone` |
| SG-AC05 | U1–U6 and retry / run-reuse / new-research branches; a matching Genome alone never blocks replication | **[proven-in-this-repo]**, referencing #399/#401/#404/#408 | `test_the_u1_u6_scenarios_are_referenced_from_the_research_memory_evidence`, `test_a_matching_genome_alone_neither_blocks_nor_establishes_equivalence`, plus `_research_decision_test`'s four named U-scenario tests |
| SG-AC06 | historical/current views, current authorization, delivery coverage and zero-call replay after cache deletion | **[proven-in-this-repo]**, referencing #408 | `test_replay_rebuilds_frozen_identities_with_zero_run_call_and_budget`, `test_an_unavailable_payload_replays_as_limited_and_is_never_substituted`, `test_a_doctored_public_fact_fails_loudly_during_replay`, `test_historical_readability_is_not_eligibility_is_not_redelivery`, `test_a_mismatched_identity_is_refused_and_leaks_nothing`, `test_a_record_whose_major_is_not_current_cannot_run_formally` |
| SG-AC07 | exact commands, dependency locks, owner boundaries and executed/not_run status published; conformance/performance/concurrency/end-to-end kept separate | **[proven-in-this-repo]** + **[cited-from-closed-StrategyWorkspace-ticket]** for #419/#422 | `test_the_owner_measured_evidence_is_cited_and_never_claimed_as_re_measured`, `test_the_seam_adds_no_dependency_and_needs_no_optional_service`, `test_the_rollup_never_counts_a_not_run_item_as_passed` |

### Preparation is not export — the non-circularity argument

The ticket's "no circular publish-before-verify requirement" is not asserted in
prose here; it is a property of `STAGE_PREREQUISITES`:

```
"package_preparation":     ("semantic_gate",)
"independent_conformance": ("package_preparation",)     # <- and nothing downstream
"owner_publication":       ("independent_conformance",)
"formal_package_export":   ("owner_publication",)
```

`stage_cycles()` walks the graph and returns `()`. The test additionally asserts
every prerequisite appears *earlier* in `GOLDEN_STAGES` than its dependent, so
the ordering and the dependency graph cannot drift apart.

### Why the identity algebra holds

`identity_of(kind, content)` digests `{"kind": ..., "content": ...}` and prefixes
the result with the kind. Digesting the kind is load-bearing: without it, a
Package identity could be re-labelled a Genome identity by rewriting its prefix
and would still reproduce. The test asserts both the six identities **and** the
six digests are distinct — that second assertion is what caught a weaker earlier
version of the test during the red/green pass below.

Provenance lives strictly outside the digest, which is why a second attempt over
the same canonical content keeps one Genome identity and accumulates two
provenances.

## The A0 reference-acceptance slice

| Item | Status | Evidence class | Notes |
| --- | --- | --- | --- |
| **A0-G04/V02** | `executed` | **[proven-in-this-repo]** | `test_a0_g04_v02_the_a0_flow_keeps_its_identities_and_refuses_the_bad_inputs` — six distinct identities survive; permitted reuse leaves `sandbox_invocations` unchanged; preparation-only / mismatched-identity / revoked inputs each produce their **own distinct refusal**. #437-shaped synthetic fixtures, test-only. |
| **A0-E01** | `not_run` | **[pending-real-asset]** | #441 published no round-one asset in this repository; `a0_delivery_index.json` still `pending`. `test_a0_e01_e02_report_not_run_and_are_never_substituted` proves the status is *reported honestly* — it is **not** evidence the criterion is met. |
| **A0-E02** | `not_run` | **[pending-real-asset]** | #442 confirmed no owner-authorized `ResearchEnginePort` configuration exists. Unchanged by this ticket; never mocked. |
| **A0-E03/H02** | `executed` (contract half) | **[proven-in-this-repo]**, referencing #408 | Per the ticket's explicit instruction, #408's `research_recovery` is **referenced, not reimplemented**: `test_a0_e03_h02_references_408_rather_than_reimplementing_recovery` asserts `recover_end_to_end` is still live *and* that `research_genome_flow.py` contains no duplicate of it. The installed/no-source environment half stays `not_run` (no wheel here). |
| **A0-Q02** | `executed` | **[proven-in-this-repo]** | `test_a0_q02_an_independent_oracle_catches_identity_time_and_binding_mutations` detects all three declared mutation classes by recomputation: (a) a doctored declared identity fails replay, (b) a provenance timestamp change does not move the identity and is not lost, (c) a single changed binding field is `binding_stale`. `test_a0_q02_no_production_module_branches_on_a_strategy_name` scans every production module's AST string constants for strategy names (cpa, doub, momentum, reversal, breakout, pairs, meanrev, turtle, macd, rsi, grid, martingale) — **zero offenders**, so the generic framework has no per-strategy route and A0's small non-CPA regression exercises the same path any strategy would. |

#419's concurrency/performance and #422's independent conformance are kept as
**separate cited claims** and are never merged into any of the above.

Per the ticket, this work did **not** wait on #441, #443 or EPIC #431. #427 and
#428 closed without waiting on #441 either; that is already resolved and is
recorded in `CITED_OWNER_EVIDENCE["#427/#428"]`.

## The fail-closed consumption table

`consume_for_formal_run` checks in a fixed order so a refusal reason is
deterministic, and publishes **three separate booleans** —
`historically_readable`, `execution_eligible`, `redelivery_permitted` — because
the ticket requires those be distinguished rather than collapsed.

| Refusal | Trigger |
| --- | --- |
| `facts_missing` | the identity is not in the store (and `historically_readable` is `False`) |
| `identity_mismatch` | the identity is not a Package kind, or does not reproduce from its own content |
| `tombstoned` / `rejected` | two distinct terminal states, neither reversible |
| `authorization_revoked` | the reader's authorization is not current |
| `unknown_major` | the record's major is not the current major |
| `sandbox_only_grant` | a sandbox grant cannot enter the ordinary formal path |
| `not_formally_consumable` | `prepared` / `registered` content — preparation is not export |
| `binding_stale` | no evidence exists for the exact declared binding |
| `not_conformant` | evidence exists and says the behaviour did not conform |

A refused outcome publishes no content, no count and no lineage — only the
identity the caller already named, and `None` when that identity does not exist.

## Red / green verification

Eight invariants were each broken in `research_genome_flow.py`, the suite run,
and the file restored. Every one went red on the intended test, and the suite is
green again afterwards.

| # | Mutation | Test that went red |
| --- | --- | --- |
| R1 | `independent_conformance` made to depend on `owner_publication` | `test_preparation_is_not_export_and_the_stage_graph_has_no_cycle` (+ rollup) |
| R2 | kind removed from the identity digest | `test_identical_payloads_of_different_kinds_never_share_an_identity` |
| R3 | `prepared`/`registered` added to `FORMALLY_CONSUMABLE` | `test_a_prepared_package_cannot_enter_the_formal_path`, `test_a0_g04_v02_...` |
| R4 | tombstone cleared by a new attempt | `test_a_new_attempt_cannot_clear_a_tombstone` |
| R5 | verification cache keyed without the binding | `test_a_non_conformant_result_is_never_admitted_and_never_reclassified`, `test_a0_g04_v02_...` (+ binding tests) |
| R6 | forward/self reference allowed | `test_content_addressing_admits_no_self_reference_and_no_cycle` |
| R7 | `research_qualified` derived from `published` | `test_the_four_qualification_flags_are_independent` |
| R8 | `not_run` items counted in `passed_item_ids` | `test_the_rollup_never_counts_a_not_run_item_as_passed` |

R2 initially stayed **green**, which exposed a genuinely weak assertion: the
original test only compared the prefixed identity strings, which differ whatever
the digest does. The test was strengthened to compare the digests as well, and
R2 then went red as it should. This is recorded rather than quietly fixed.

## Exact commands and results

Environment: Windows 11, CPython 3.13, `D:\WILL\STOCK\QuantResearch`, branch
`codex/issue-429-sg-e2e-proof` off `main` at `3906f47`.

```
python -c "import strategy_workspace"   -> ModuleNotFoundError: No module named 'strategy_workspace'
python -c "import apex_research"        -> ModuleNotFoundError: No module named 'apex_research'
```

```
python -m pytest src/quantresearch_acceptance -q --ignore=src/quantresearch_acceptance/_spec027_installed_test.py
```

| | Before | After |
| --- | --- | --- |
| passed | 381 | **421** (+40) |
| failed | 2 | **2** (identical, by name) |

The two failures, unchanged and pre-existing:

- `_a0_installed_test.py::test_a0_installed_tracer_is_not_source_preferred`
- `_installed_test.py::test_installed_wheel_has_no_source_checkout_precedence`

Both assert `"site-packages" in __file__`, which is false when the package is
run from the source checkout rather than an installed wheel. They are the
correct, honest signal that this environment has no installed wheel.

```
python -m ruff check src/quantresearch_acceptance     -> All checks passed!
python -m compileall -q src/quantresearch_acceptance  -> exit 0
python -m pytest src/quantresearch_acceptance/_research_genome_flow_test.py -q -> 40 passed
```

`_spec027_installed_test.py` is excluded because it imports four wheels that are
absent from this environment; it is a collection error, not a regression, and it
was excluded from the before-run identically.

## What is genuinely not satisfied

| Requirement | Status | Why |
| --- | --- | --- |
| Installed/no-source positive+negative commands executed **against the real wheels** | `not_run` | `strategy_workspace` / `apex_research` are not installed in this Python environment. The contract shape is proved; the wheel run is not, and is not claimed. |
| A0-E01 real V0/V1 research round on real data | `pending` | #441 produced no asset in this repository. |
| A0-E02 second-round authorized model/request/response records | `pending` | #442 confirmed no owner-authorized engine configuration. |
| #419 concurrency/crash + 256 KiB p95 ≤ 250 ms; #422 independent conformance | cited | Measuring these requires StrategyWorkspace's code, which this repository does not own and must not modify. Cited as owner evidence, explicitly labelled as not re-derived. |

No profit or significance threshold applies; this is engineering acceptance
only. Skipped, blocked and `not_run` items are counted nowhere as passed —
`genome_matrix_readback()["not_run_item_ids"]` and `["passed_item_ids"]` are
asserted disjoint.

## Owner boundary confirmation

Files added by this ticket:

- `src/quantresearch_acceptance/research_genome_flow.py`
- `src/quantresearch_acceptance/_research_genome_flow_test.py`
- `docs/evidence/issue-429-installed-no-source-genome-flow.md`

Nothing else. `strategy-workspace/`, `.worktrees/`, `pyproject.toml` and every
other project's source are untouched.
