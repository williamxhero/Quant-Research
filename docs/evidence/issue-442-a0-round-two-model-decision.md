# #442 A0 second round: memory use, controlled model decision, reuse/stop

## Headline: A0-E02 is `not_run`

**No owner-authorized `ResearchEnginePort` configuration exists for this
repository, so no real model request or response was made. A0-E02 is `not_run`.**

This is the ticket's own explicitly permitted outcome
("未具备授权/连通时 E02 是 blocked/not_run"), and it is reported here as the
result, not worked around. Nothing in this commit creates an API key, copies a
credential, reaches a paid provider, or presents a recorded, stubbed or
harness-driven response as real research use.

Every other acceptance criterion of #442 was implemented and tested in the
**offline regression** layer, which is reported separately from the (empty)
**real connected** layer and never substituted for it.

## Scope

This evidence covers the QuantResearch acceptance seam for #442 (A0-T08), under
#442, parent #440, EPIC #431, and the contracts delivered for #394, #395, #396,
#397, #398, #399 and #401. It adds
`quantresearch_acceptance.research_a0_round2`, which composes those six modules
for exactly one scenario: the A0 second round. It adds no dependency, no
network client, no database client, no LangGraph or agent loop, and no second
statistical authority. The module is standard library only.

All records used here are synthetic, test-only identities, references and
digests, shaped as #437-style fixtures. No real holdout sample is read,
transmitted or referenced.

## The independent connectivity check, and what it found

This was settled **before** any code was written, because it determines how much
of the ticket is "wire together and mark `not_run`" versus "wire together and
call".

What was searched, in this repository and (read-only) in the adjacent
`apex-research/` checkout:

- `ResearchEnginePort`, `research_engine_port`, `ORCHESTRATOR`,
  `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `api_key`.

What was found, and nothing else:

- `README.md:43` mentions `ResearchEnginePort` as a documented extension point.
  A doc sentence, not an implementation.
- `_spec027_installed_test.py:60` asserts a `ResearchEnginePort` attribute on an
  **installed wheel** of `apex_research`. That wheel is **not installed** on this
  checkout (`import apex_research` fails with `ModuleNotFoundError`), which is
  exactly why that file is excluded from the test command, as recorded for
  #394-#401.
- In the adjacent `apex-research/` repository (a separate project, read only,
  not modified): `research_engine.py:642` defines
  `class ResearchEnginePort(Protocol)` — a **seam**, with no bound
  implementation. The only generic adapter,
  `adapters/research_engine.py::RunnerBackedResearchEngine`, requires a
  `GovernedExternalResearchRunner` plus a `GovernedActionRequest` and a
  `RunnerPolicy`. No such runner endpoint is configured anywhere.
- Every `api_key` / `base_url` hit in that repository is a **redaction list** or
  a data-source URL (`memory.py:783`, `governance.py:2090`,
  `empirical.py:1692`, `adapters/qrafti.py:523`), not a model client.
- There is no `.env`, no secrets file, and no research-engine configuration in
  this repository.

So there is no connectable, owner-authorized model path. This is a **confirmed
absence**, consistent with what #396, #398 and #399 each recorded independently.

### On the machine's environment variables

Unrelated, general-purpose provider keys exist in the developer's shell
environment. They were **not** used, not read, not copied, and are not an
authorization for this round: they are not an owner-published
`ResearchEnginePort` configuration, and using them would have meant spending
money on a paid external API, which neither #442 nor the planning issue
authorizes. This is recorded here so that their existence cannot later be
mistaken for an authorization that was overlooked.

## The state of this ticket's declared inputs

`docs/research/a0/a0_delivery_index.md` and `.json` were re-verified at the time
of this commit. Still `pending`:

| Row | Status | Consequence for #442 |
| --- | --- | --- |
| `A0-B0-RULES` (#434) | `pending` | allowed-action / stop policy is a fixture, not an owner artifact |
| `A0-FIXTURES-ORACLE` (#437) | `pending` | fixtures are #437-*shaped*, built in this repo |
| `A0-ROUND-1` (#441) | `pending` | **the first-round public assets this ticket was to consume do not exist** |
| `A0-ROUND-2` (this ticket) | `pending` | the owner row stays pending; see below |

`git log --all --grep='#441'` returns nothing: #441 landed no commit in this
repository. Its baseline / results / counter-evidence / gaps are therefore
represented by the frozen synthetic A0 fixtures already established by #399
(`a0-support-v1`, `a0-counter-v1`, `genome-ema-crossback`,
`test-family-a0-crossback`), reused here unchanged so the two tickets' branch
evidence lines up. **No round-one conclusion is invented**, and none is
presented as real.

### `docs/research/a0/a0_delivery_index.*` was not modified

Deliberately, for three reasons, and consistent with #394-#401 which also left
it alone:

1. `/docs/` is git-ignored in this repository; only the explicitly force-added
   `docs/evidence/issue-*.md` files are tracked. An index edit would not be
   published by this commit at all.
2. The `A0-ROUND-2` row is owned by "Apex Research / pending owner", not by
   QuantResearch. Backfilling a row this repository does not own would be a
   cross-owner write.
3. There is no exact round-two version to backfill: with E02 `not_run`, the row's
   "run identity" and "output digest" remain genuinely `pending`. Writing this
   commit's SHA there would imply a connected round that did not happen.

The exact versions this ticket *did* produce are the commit SHAs of this branch
plus `ROUND2_RECORD_SCHEMA` / `ROUND2_READBACK_SCHEMA`, recorded here.

## What was built

`research_a0_round2.py`, composing the six accepted modules:

| Piece | Role |
| --- | --- |
| `EngineAuthorization` | reads whether an owner-authorized real engine exists; refuses any declaration carrying a credential field |
| `unauthorized_engine()` | the documented default for this repository |
| `GovernedRoundTwoEngine` | #399's four-method seam, with only `call_research_engine` gated on authorization |
| `ModelDelivery` | `delivered` / `blocked` / `not_run`, with the invariants below |
| `review_model_response()` | structural review: source, step, assumption, boundary, and the three forbidden asks |
| `RoundTwoFreeze` | the frozen round: cutoff, purpose, consumer, closure, template/model/parameter/tool versions, budget, allowed actions, authorization |
| `run_a0_round_two()` | the end-to-end round, returning `RoundTwoOutcome` |

### The invariants that carry the ticket

1. **`delivered` is unreachable without an authorized real engine.**
   `ModelDelivery.build` refuses it. `EngineAuthorization.parse` refuses
   `state="authorized"` unless there is *both* a public `engine_ref` *and*
   `transport="real_process"`, so an offline stand-in — or a successful
   connectivity probe — can never describe itself as authorized.
2. **A non-delivered round carries no response.** `blocked` and `not_run`
   refuse an `invocation_id`, a `response_ref` or a raw response outright.
   There is nothing for a later reader to mistake for a model answer.
3. **Delivered is not cognized.** `proves_model_use` is the single place that
   claim is made, and it requires `state == "delivered"` *and*
   `layer == "real_connected"`.
4. **The layers never merge.** `evidence_layers` reports `real_connected` and
   `offline_regression` separately, and the offline layer carries
   `substitutes_for_connected: False` explicitly.
5. **A credential can never travel in a declaration.** `CREDENTIAL_FIELDS` is
   checked on the *field name*; the value is never read, logged or echoed.
6. **The response is judged on structure, not wording.** Two responses with the
   same structure and different prose review identically
   (`test_the_review_judges_structure_not_wording`).

### Where protection is enforced

#399 already gates the Context before the first unit of spend. This module adds
the two stages #399 did not own:

- **`final_envelope`** — checked *before* any model read; a restricted addition
  stops the round with `final_envelope_gate:restricted` and the gate's
  `safety_audit["status"] == "blocked"`, so the addition is neither silently
  dropped nor silently delivered.
- **`tool_return`** — checked on the callback path; a non-`allowed` status
  prevents Candidate admission.

Exposure records `context_prepared` as soon as the Context really was assembled
(true whether or not anyone read it) and `envelope_delivered` **only** on a real
delivery. A retry finds the record already present and appends nothing, so
reconciliation never re-prepares. An `delivery_uncertain` state is reconciled by
#399 (`reconcile_required`, zero spend) and is asserted still
`delivery_uncertain` afterwards — never washed back to "unseen", never resent.

## Acceptance criteria mapping

| #442 criterion | Status | Test evidence |
| --- | --- | --- |
| **A0-E02** real authorized model request/response | **`not_run`, honestly reported** | `test_a0_e02_reports_not_run_and_never_claims_model_use`, `test_a0_e02_a_not_run_round_creates_no_candidate`, `test_a0_e02_a_blocked_or_not_run_delivery_cannot_carry_a_response`, `test_a0_e02_an_unauthorized_engine_can_never_produce_a_delivered_state`, `test_a0_e02_a_connectivity_probe_is_not_an_authorization`, `test_a0_e02_the_engine_call_is_attempted_but_never_made`, `test_a0_e02_an_authorization_declaration_may_never_carry_a_credential` |
| **A0-C01/M02/M03** sources, counter-evidence, gaps, test family | pass | `test_a0_c01_required_counter_evidence_missing_blocks_the_round`, `test_a0_m03_the_test_family_is_preserved_on_the_readback`, `test_a_response_citing_an_unapproved_source_is_refused_not_patched`, `test_a_response_proposing_an_unpermitted_step_is_refused`, `test_an_unsourced_conclusion_never_becomes_a_verified_one` |
| **A0-P01/P02** direct/derived protection, final-input check, uncertain delivery, no leakage | pass | `test_a0_p01_a_blocked_final_envelope_stops_before_the_model_read`, `test_a0_p01_the_visibility_gate_stops_the_round_before_any_spend`, `test_a0_p02_an_uncertain_delivery_is_reconciled_and_never_resent`, `test_a0_p02_the_public_record_carries_a_digest_not_the_payload` |
| **A0-R01/R02** retry, duplicate stop, run reuse, legitimate new research — separate branches, zero-side-effect assertions | pass | `test_a0_r01_retry_conflict_and_duplicate_stop_each_have_their_own_branch` (branches 1-3), `test_a0_r02_attach_and_legitimate_new_sample_stay_separate_branches` (branches 4-5), `test_a0_r02_usage_history_survives_a_new_campaign`, `test_a0_r02_a_new_campaign_with_new_research_keeps_both_histories` |
| Model output may only continue / add evidence / stop; no unauthorized new strategy, budget or run; a wrong output is refused | pass | `test_a_response_may_only_continue_add_evidence_or_stop`, `test_a_response_that_asks_for_a_new_run_budget_or_strategy_is_refused`, `test_a_response_without_declared_boundaries_is_refused`, `test_a_declaration_may_not_allow_an_action_outside_the_policy`, `test_harness_only_a_refused_response_never_yields_a_candidate` |
| Connected vs offline layers reported separately; not failed on wording; not claimed complete without a real call | pass | `test_the_two_evidence_layers_are_reported_separately`, `test_the_review_judges_structure_not_wording`, `test_the_round_opens_no_store_and_reaches_no_provider` |
| T08 does not depend on #404/#408/#429/T09 | pass by construction | nothing in this module imports or waits on those tickets |

### The five R01/R02 branches, with their side-effect counts

`RecordingEngine` counts `(contexts, budgets, runs, calls)` separately, so a
branch is proved with four zeros rather than one "nothing happened". The fourth
counter is the provider-facing one.

| Branch | Decision outcome | `(ctx, budget, run, call)` | Note |
| --- | --- | --- | --- |
| 1. same action retried | `recovered_existing` | `(1, 1, 1, 0)` unchanged | reconciles, does not re-execute |
| 2. same key, different input | `rejected_key_conflict` | `(1, 1, 1, 0)` unchanged | rejected outright |
| 3. truly equivalent research | `stopped_duplicate` | `(0, 0, 0, 0)` | **zero new expensive actions** |
| 4. same execution, new protocol | `attached_run` / `new_research` | `runs == []` | attach only |
| 5. legitimate new sample | `new_research` | `(1, 1, 1, 0)` | not caught by Genome dedup |

In every branch the fourth counter is `0`: the provider was never reached,
because nobody authorized it. `engine_counts` reports this separately as
`{"attempted_calls": 1, "real_calls": 0, "not_run": 1}` — "we would have asked"
and "a model saw it" are kept apart.

A cross-Campaign check is included: a second Campaign asking the *same* question
stops as `stopped_duplicate` precisely **because** the first Campaign's usage
history was not cleared, and a second Campaign asking genuinely new research
keeps both entries in the family readback.

## The Candidate

**No Candidate was created**, and the recorded reason is
`model_delivery_not_run`. A Candidate is only admitted when the delivery
genuinely proves model use *and* the structured review returns `continue` or
`add_evidence` *and* the tool-return gate allowed. With E02 `not_run`, the first
condition fails, so admission never runs. A stop decision is recorded as a
successful round with `no_candidate_reason == "model_proposed_stop"`, per the
ticket ("有依据停止也是成功结果").

## The harness-only tests, and what they are not

Four tests named `test_harness_only_*` drive the authorized branch with a local
harness so the code path stays exercised rather than dead. **They are not A0-E02
evidence**, and the test file says so in a block comment at that point. The
harness declares its own engine reference, reaches no provider and spends
nothing. A0-E02 remains `not_run`; the `test_a0_e02_*` tests above are its
evidence.

## Red/green confirmation

Each invariant was broken, observed to fail, and restored:

| Break | Result |
| --- | --- |
| `delivered` no longer requires an authorized engine | `test_a0_e02_an_unauthorized_engine_can_never_produce_a_delivered_state` failed (1 failed, 34 passed) |
| a `not_run` delivery may carry a response | `test_a0_e02_a_blocked_or_not_run_delivery_cannot_carry_a_response` failed (1 failed, 34 passed) |
| the final-envelope gate no longer stops the round | `test_a0_p01_a_blocked_final_envelope_stops_before_the_model_read` failed (1 failed, 34 passed) |
| the review accepts an unauthorized new run | `test_a_response_that_asks_for_a_new_run_budget_or_strategy_is_refused` and `test_harness_only_a_refused_response_never_yields_a_candidate` failed (2 failed, 33 passed) |

Restored: `35 passed`.

## Test evidence

```
python -m pytest src/quantresearch_acceptance -q \
    --ignore=src/quantresearch_acceptance/_spec027_installed_test.py
```

| Run | Result |
| --- | --- |
| before (this file's tests excluded) | `2 failed, 292 passed` |
| after | `2 failed, 327 passed` |

The two failures are identical by name before and after, and are the
pre-existing ones recorded for #394-#401:

- `_a0_installed_test.py::test_a0_installed_tracer_is_not_source_preferred`
- `_installed_test.py::test_installed_wheel_has_no_source_checkout_precedence`

Both require the five wheels to be installed; they are not. **+35 tests, zero
regressions.**

```
python -m ruff check src/quantresearch_acceptance     # All checks passed!
python -m compileall -q src/quantresearch_acceptance  # clean
```

## What this ticket does not claim

- It does **not** claim a real model was invoked. It was not.
- It does **not** claim the round-one public assets of #441 exist. They do not;
  `A0-ROUND-1` is still `pending`.
- It does **not** claim the offline branch substitutes for required connected
  evidence. The layered report says so explicitly.
- It does **not** claim owner approval of the allowed-action / stop policy;
  `A0-B0-RULES` (#434) is still `pending`, so that policy is a fixture.
- A real connected A0 second round still needs an owner-authorized
  `ResearchEnginePort` configuration and a separate budget approval. When one
  exists, `run_a0_round_two` takes it through `EngineAuthorization` without any
  contract change.

## Acceptance conclusion

Every #442 criterion except A0-E02 is implemented and covered by passing tests
with separate public branch evidence and explicit zero-side-effect assertions.
**A0-E02 is `not_run`**, for the confirmed absence of any owner-authorized
research-engine configuration, and the module is built so that this status can
never be presented as a delivery.
