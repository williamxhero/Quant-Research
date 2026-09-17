# #399 Duplicate stop, run reuse and call-ordering evidence

## Scope

This evidence covers the QuantResearch acceptance seam for #399 (RM-V1C.3),
under the constraints in #399, parent SPEC #385, the R2 policy in #381
(RM-R2-2/4/5/7 and the shared implementation policy), and the contracts
delivered for #394, #395, #396, #397 and #398. It adds
`quantresearch_acceptance.research_decision`; it does not add a Pydantic
contract, a deduplication service, a LangGraph or parallel-agent loop, a second
statistical or eligibility authority, a database client, or a network
dependency. `research_decision` is standard library only.

All records used here are synthetic, test-only identities, references and
digests. No real holdout sample is read, transmitted, or referenced. No
connected model was invoked. **This ticket's evidence is contract- and
seam-level, not a real connected A0 round.** The real second-round connected
proof on actual research assets remains #442's job and is not substituted for
here by any offline stub.

## What existed, and the confirmed absence of Orchestrator infrastructure

#399's design revision says "把冻结研究简报接入既有 Orchestrator". A
repository-wide search was run before any code was written:
`grep -ri "orchestrator\|workspace" src/ apex-research/ docs/`.

What that found, and nothing else:

- `fixtures.py` creates a temporary directory literally named `workspace` for
  SQLite isolation. A filesystem path, not an orchestration contract.
- `_spec027_installed_test.py` imports `strategy_workspace` and asserts a
  `"ResearchOrchestrator"` symbol on an *installed wheel* of `apex_research`.
  That wheel is not installed on this checkout, and the file is ignored in the
  test command below, exactly as recorded for #394-#398.
- `migration.py` maps the legacy scope name `strategy-workspace` to
  `strategy_workspace`. A name, not an implementation.
- `apex-research/` is a separate git repository; its matches are commit
  messages in `.git/logs`, not code in this package.

So there is no Orchestrator, Workspace, invocation or budget-reservation
primitive in this repository to wire into. This is a **confirmed absence, not a
new ambiguity**: #396 established it, #398 re-confirmed it, and this ticket
re-verified it independently. Following that precedent, the minimal decision
layer and its engine seam are built directly in the `research_*` family,
carrying Campaign / Iteration / Package / Genome / Candidate identities as
declared references so a production Orchestrator can own execution later
without this contract changing.

`docs/research/a0/a0_delivery_index.md` and `.json` were re-verified at the time
of this commit: `A0-B0-RULES`, `A0-FIXTURES-ORACLE`, `A0-ROUND-1`, `A0-ROUND-2`
and `A0-FINAL-EVIDENCE` remain `pending`.

## The engine seam that was built, and why

`ResearchEngineSeam` is a `typing.Protocol` with **four** methods, not one:

```python
publish_context(record)            # publish a frozen Context to the engine
reserve_budget(budget_id, units)   # reserve external budget
execute_run(run_key, contract)     # execute the backtest / run
call_research_engine(request)      # invoke the existing consumer
```

They are separate because the acceptance criteria count them separately. "A
true duplicate spends nothing" is only a real assertion if the four spends can
each be observed at zero, and "same run, different protocol attaches rather than
re-backtests" is only expressible if executing a run is a different call from
invoking the engine. The test double `RecordingEngine` records each call on its
own list, so every count in this document is an exact list length rather than an
absence of exceptions. The gate additionally publishes its own `SpendCounters`
in the public decision record, and a Hypothesis invariant asserts the two agree.

## Three decisions, never one flag

| Decision | Key | What is deliberately *not* in the key |
| --- | --- | --- |
| Request idempotency | #396 `ExposureKey.action_key()` + frozen `input_digest` | `display_name` |
| Run reuse | `RunContract.run_key()`: Package, Genome, parameter digest, data snapshot id, data range, cost environment, execution environment, randomness contract | the statistical protocol; the run's `terminal_state` |
| Research duplication | question id, real failure direction, comparison target, evidence requirements, statistical protocol, **and** the whole run contract | `display_name`; the declared `intent` |

Two asymmetries carry most of the weight.

**A rename proves nothing.** `display_name` enters no key, so a re-titled
equivalent request recovers or duplicates under the original identity.

**A declared intent proves nothing.** `intent` enters no key either. Calling a
request a "replication" when its run contract, protocol and question are
identical to a completed judgment is still a duplicate; independence has to be
visible in the frozen inputs.

`terminal_state` is excluded from the run key on purpose: the same execution
input that failed and later succeeded is one run identity in two states, and
including the state would let an old failure hide a later success. Only
`completed` qualifies for reuse (`QUALIFYING_RUN_STATES`).

### The in-flight index

A conclusion belongs to the originating owner, so the gate never publishes a
judgment of its own — that would fabricate evidence. Without something else,
though, a second request under a *different* idempotency key would pay for the
identical question again. `DecisionLedger.in_flight_for(research_key)` closes
that: an authorised-but-unfinished research action leaves a public decision
record, and a later equivalent request stops with
`equivalent_research_already_in_flight`. This was found by the Hypothesis state
machine rather than by inspection.

## Ordering, and why the spends are unreachable

`DECISION_STEP_CONTRACT` freezes thirteen steps with a phase each
(`read` → `decide` → `publish` → `stop` → `gate` → `act`), and
`DECISION_STEP_CONTRACT_DIGEST` takes part in every decision identity, so a
renamed or reordered step is a different decision rather than a silent
relabelling.

1. `read_predecessor_policy`, `read_approved_sources`
2. `decide_request_idempotency`, `decide_run_reuse`, `decide_research_duplication`
3. `publish_decision_readback`
4. `stop_on_research_duplicate` — **returns**
5. `check_visibility`, `check_required_completeness`
6. `publish_engine_context`, `reserve_budget`, `execute_run`, `call_research_engine`

Nothing before step 4 touches the engine seam, and the duplicate path returns
from step 4. So on that path the engine is not merely unused — it is
unreachable. `_Trace.step` refuses a step that is not strictly later than the
last one, so the recorded trace can never be a reordering.

The visibility and completeness answers stay distinct, in the same way #398
keeps its three delivery outcomes distinct: only `{"delivery": "blocked"}` is an
authorization answer; a `refused` retrieval is a completeness answer and is
reported by the next step. A missing evidence chain is therefore never
mislabelled as a permission problem. A test drives a request that would fail
both and asserts the declared order decides which answer is given.

Reuse is not exempt from the gates: an attached or reused run still passes
`check_visibility` (the current #394/#395 authorization, currency and protection
decision) and `check_required_completeness` before anything is spent. No new
statistical or eligibility authority was added; every readback states
`grants_eligibility: false`.

## Data blockers

A prior judgment in `blocked_by_data` produces `blocked_prior_data_blocker` with
reasons `prior_data_blocker_unresolved` and `not_strategy_falsification`, and
zero spends. With an owner-permitted repair naming the recorded blocker it
becomes `new_research` with reasons
`blocker_repaired_under_owner_permitted_condition` and `new_condition:<token>`.
A repair the owner did not permit does not proceed; a repair naming a different
blocker is a `DecisionRefusal`. Every readback carries
`strategy_falsified: false` on all of these paths.

## Read-only access is structurally not a bypass

`inspect_decision_history(ledger, exposure, ...)` takes **no engine seam
parameter at all**, so a manual query, an MLflow dashboard or a future Optuna
study reading it has no path to a Context, a budget, a run or a call. It
returns `invokes_engine: false`, `reserves_budget: false`,
`publishes_context: false`, `bypasses_duplicate_gate: false` and
`scanned_full_history: false`. Twenty-five repeated inspections record no
decision and no spend.

## U1-U3

`U1`-`U6` come from #381's shared scenario table (`gh issue view 381`, the
"joint research-use scenarios" table). The three this ticket covers:

- **U1 等价失败方向换名再提** — the same question and the same *real failure
  reason*, re-proposed under a new name. Expected: recognised and not paid for
  again, and *not* blocked by natural-language similarity alone. Covered by
  keying on `failure_direction` + `comparison_target` + `evidence_requirements`
  + protocol + run contract, with `display_name` excluded.
- **U2 数据问题修复** — the old blocker is preserved, a governed retry with a
  new condition is allowed, and the old failure is never a permanent
  falsification. Covered by the `blocked_by_data` / `BlockerRepair` path above.
- **U3 同策略合法新样本复验** — not wrongly blocked by Genome-level dedup; only
  an exact input match reuses a run; independence still belongs to the
  statistical owner. Covered by the full-contract run key and
  `grants_eligibility: false` everywhere.

`test_a0_u1_u3_miscall_run_reuse_and_external_call_counts` runs all three and
asserts the recorded table exactly:

| Scenario | Legitimate requests | Wrongly blocked | Runs reused | External calls |
| --- | --- | --- | --- | --- |
| U1 (renamed equivalent) | 0 | 0 | 0 | 0 |
| U2 (repaired data blocker) | 1 | 0 | 0 | 4 |
| U3 (new-sample revalidation) | 1 | 0 | 0 | 4 |

The same test also pins the one case that *does* reuse an execution fact: the
same run with a new statistical protocol attaches, giving counts
`(contexts, budgets, runs, calls) = (1, 1, 0, 1)` — a new judgment with no
re-backtest.

## Acceptance criteria mapping

| Criterion | Test evidence |
| --- | --- |
| True-duplicate branch: after canonical decision readback, no engine Context, no external budget reservation, no run, no engine call | `test_a_true_duplicate_stops_before_context_budget_run_and_call` (four counters asserted separately, plus `SpendCounters.as_dict()`), `test_the_duplicate_branch_completes_the_canonical_readback_before_stopping`, `test_a_renamed_equivalent_request_is_still_a_duplicate`, `test_a_self_declared_replication_that_changes_nothing_is_still_a_duplicate`, `test_a_second_idempotency_key_cannot_buy_the_same_research_twice` |
| Non-duplicate branch calls the engine only after policy / visibility / completeness pass, in the declared order; manual read-only history is not a bypass | `test_a_new_question_calls_the_engine_only_after_the_gates_pass`, `test_a_blocked_visibility_gate_stops_before_any_spend`, `test_an_incomplete_required_scope_stops_before_any_spend`, `test_a_blocked_brief_stops_before_any_spend`, `test_the_visibility_gate_is_checked_before_completeness`, `test_manual_read_only_history_never_reaches_the_engine`, `test_read_only_history_repeated_never_accumulates_a_spend` |
| Same-action retry does not re-execute; same key + different semantics rejected; `delivery_uncertain` recovers conservatively per #396 | `test_a_retry_of_the_same_action_recovers_instead_of_re_executing`, `test_the_same_key_with_a_different_input_is_rejected`, `test_a_rename_alone_is_not_a_key_conflict`, `test_an_uncertain_delivery_is_reconciled_before_anything_is_resent`, `test_repeating_the_same_action_never_spends_twice` (30 examples) |
| Same run + different statistical protocol reuses execution facts but still produces a new judgment; a legitimate new sample is not blocked by a matching Genome | `test_a_new_statistical_protocol_attaches_to_the_run_and_still_judges_afresh`, `test_a_reused_run_does_not_by_itself_make_the_research_a_duplicate`, `test_a_legitimate_new_sample_is_not_blocked_by_a_matching_genome`, `test_the_run_key_excludes_the_statistical_protocol`, `test_a_genome_match_alone_is_not_a_run_match`, `test_a_different_randomness_contract_is_a_different_run`, `test_a_run_that_never_completed_is_not_reusable`, `test_a_protocol_change_never_changes_the_run_key` (40 examples) |
| After a data blocker is repaired, the owner-permitted new-condition / retry flow applies; a stale failure is never strategy falsification | `test_an_unrepaired_data_blocker_blocks_without_claiming_falsification`, `test_a_repaired_blocker_with_an_owner_permitted_condition_proceeds`, `test_a_repair_the_owner_did_not_permit_does_not_proceed`, `test_a_repair_that_names_another_blocker_is_refused` |
| Recovery / retry reuses frozen Context and events; across Campaigns the read results, test family and Exposure history are preserved; no new independent evidence | `test_a_decision_is_replayed_from_its_frozen_public_record`, `test_a_doctored_decision_record_fails_loudly`, `test_a_doctored_spend_counter_fails_loudly`, `test_a_reordered_call_trace_is_a_different_decision`, `test_recovery_reuses_the_frozen_context_identity_not_a_new_query`, `test_a_new_campaign_never_resets_the_test_family`, `test_prior_results_are_preserved_across_campaigns_rather_than_replaced`, `test_no_readback_ever_claims_eligibility_or_a_full_history_scan` |
| Hypothesis state machine + call-trace tests over every branch, plus recorded U1-U3 miscall / run-reuse / external-call counts | `TestResearchDecisionMachine` (25 examples x 12 steps, seven rules, two invariants), `test_no_rename_or_declared_intent_ever_unlocks_a_completed_duplicate` (40), `test_a_protocol_change_never_changes_the_run_key` (40), `test_every_distinct_execution_input_is_a_distinct_run` (40), `test_repeating_the_same_action_never_spends_twice` (30), `test_a0_u1_u3_miscall_run_reuse_and_external_call_counts` |

### A0 reference acceptance

`A0-B0-RULES` and `A0-FIXTURES-ORACLE` (#434 / #437) are still `pending` in
`docs/research/a0/a0_delivery_index.json`, re-verified at the time of this
commit. Following the precedent set for #394-#398, the A0 slice runs on
synthetic, #437-shaped, explicitly test-only records. It asserts contract shape
on frozen stand-ins; it does **not** claim a frozen B0, a real A0 round, or a
real second-round model delivery. It does not wait on #441 / #442 / #443.

- **A0-R01** — `test_a0_r01_retry_reconciles_conflict_rejects_and_duplicate_stops`.
  Four steps in one test: the first pass spends exactly `(1, 1, 1, 1)`; the same
  action retried reconciles against the record and the counts stay `(1, 1, 1, 1)`;
  the same key with a different parameter digest is `rejected_key_conflict` and
  the counts still stay `(1, 1, 1, 1)`; and a genuinely duplicate research
  question on a fresh ledger yields `stopped_duplicate` with
  `len(contexts) == 0`, `len(budgets) == 0`, `len(runs) == 0`, `len(calls) == 0`
  asserted individually, plus the full `SpendCounters.as_dict()` at zero.
- **A0-R02** — `test_a0_r02_attach_new_sample_and_blocker_recovery_stay_separate`.
  V1 with the same execution input and a new statistical protocol attaches
  (`attached_run` + `new_research`, `engine.runs == []`); a V1 legitimate
  new-sample revalidation carrying the *same* Genome id is `new_research` with
  counts `(1, 1, 1, 1)`; a repaired data blocker with an owner-permitted new
  condition proceeds with `strategy_falsified: false`. The readback's three
  dispositions are asserted as three separate fields, and the research family
  (`test-family-a0-crossback`) is asserted unchanged.
- **A0-P02 (call ordering)** —
  `test_a0_p02_call_ordering_uncertain_delivery_and_frozen_recovery`. The
  proceed trace equals every declared step but the duplicate stop, in order, and
  the engine's own trace is `[publish_context, reserve_budget, execute_run,
  call_research_engine]`. An action left `delivery_uncertain` in a real #396
  `ExposureLog` yields `reconcile_required` with `(0, 0, 0, 0)` and
  `resend_allowed: false`. Recovery replays only the frozen public record, with
  `used_latest_query: false`.
- **Frozen submission (B0 stand-in)** —
  `test_a0_the_public_decision_inputs_and_outputs_are_the_submitted_evidence`
  pins the public inputs (`package-a0`, `genome-ema-crossback`, data range
  `2020-01-01/2024-12-31`, `protocol-two-sided`, budget `10` units) against the
  expected outputs (`proceeded`, `new_request` / `new_run` / `new_research`,
  counters `1/1/1/1` and twelve trace steps). Expected values are the test's own
  literals.
  `test_the_module_opens_no_store_and_makes_no_external_call` reads
  `research_decision.py` back and asserts it contains no `socket`, `sqlite3`,
  `urllib`, `requests`, `subprocess` or `open(` — a zero-new-external-call
  record. No manual research content is mixed into this evidence.

## Test evidence

Command, run from `D:\WILL\STOCK\QuantResearch`:

```
python -m pytest src/quantresearch_acceptance -q \
  --ignore=src/quantresearch_acceptance/_spec027_installed_test.py
```

- Before (`main` at `99dfb07`): **2 failed, 187 passed**.
- After: **2 failed, 243 passed** (+56, all in `_research_decision_test.py`).

The two failures are identical before and after, by name:
`_installed_test.py::test_installed_wheel_has_no_source_checkout_precedence` and
`_a0_installed_test.py::test_a0_installed_tracer_is_not_source_preferred`. Both
require a no-source installed-wheel environment rather than a source checkout,
as recorded for #394-#398. `_spec027_installed_test.py` still fails collection on
this machine for the missing `strategy_workspace` / `apex_research` wheels, also
as recorded for those tickets; it is ignored in both the before and the after
run and is not counted as #399 evidence. There are no other deltas.

`python -m ruff check src/quantresearch_acceptance` passes, and
`python -m compileall -q src/quantresearch_acceptance` is clean.

Red/green was confirmed for the new logic rather than assumed. Each patch was
applied to `research_decision.py` alone, `_research_decision_test.py` was run,
and the patch reverted (the restored file was diffed byte-for-byte against the
pre-break copy):

- The duplicate branch no longer stops (`if research_disposition != "new_research"`
  forced false): **15 fail**, including
  `test_a_true_duplicate_stops_before_context_budget_run_and_call`,
  `test_a0_r01_retry_reconciles_conflict_rejects_and_duplicate_stops`,
  `test_a0_u1_u3_miscall_run_reuse_and_external_call_counts` and
  `TestResearchDecisionMachine`.
- The attach case collapsed into a plain reuse (the protocol comparison in
  `_decide_run_reuse` forced false), i.e. run reuse and research duplication no
  longer independent: **3 fail**
  (`test_a_new_statistical_protocol_attaches_to_the_run_and_still_judges_afresh`,
  `test_a0_r02_attach_new_sample_and_blocker_recovery_stay_separate`,
  `test_a0_u1_u3_miscall_run_reuse_and_external_call_counts`).
- Same key with a different input accepted as a recovery (the input-digest
  comparison forced true): **2 fail**
  (`test_the_same_key_with_a_different_input_is_rejected`,
  `test_a0_r01_retry_reconciles_conflict_rejects_and_duplicate_stops`).
- `display_name` and `intent` added to the research key, so a rename or a
  self-declared replication manufactures novelty: **9 fail**, including
  `test_a_renamed_equivalent_request_is_still_a_duplicate`,
  `test_a_self_declared_replication_that_changes_nothing_is_still_a_duplicate`
  and `test_no_rename_or_declared_intent_ever_unlocks_a_completed_duplicate`.
- The required-completeness gate disabled, so an incomplete required scope
  reaches the engine: **2 fail**
  (`test_an_incomplete_required_scope_stops_before_any_spend`,
  `test_a_blocked_brief_stops_before_any_spend`).

After restoring the module, all 56 pass again and the suite returns to
2 failed, 243 passed.

The in-flight duplicate hole described above was found by
`TestResearchDecisionMachine`'s `a_research_key_is_never_paid_for_twice`
invariant failing on a two-step sequence, not by inspection; it was fixed and is
now covered by `test_a_second_idempotency_key_cannot_buy_the_same_research_twice`.

`hypothesis` remains the test-only dependency group declared for #395; no new
runtime dependency was added.

## Acceptance conclusion

The local #399 request-idempotency, run-reuse, research-duplication, call-order
and recovery behaviour is verified on synthetic records, together with the
covered A0-R01, A0-R02 and A0-P02 slices and the recorded U1-U3 counts. This is
engineering and acceptance-seam evidence only. It does not claim a connected E02
model run, a real A0 second round, real holdout access, a frozen B0 sample,
research qualification, or profitability.
