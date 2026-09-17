# #396 Research Exposure lifecycle and actual-usage linkage evidence

## Scope

This evidence covers the QuantResearch acceptance seam for #396 (RM-V1B.3), under
the constraints in #396, parent SPEC #384, the R2 policy in #381 (RM-R2-2/5/6/7
and the shared implementation policy), and the gates delivered for #394 and #395.
It adds `quantresearch_acceptance.research_exposure`; it does not add a Pydantic
contract, a workflow framework, a second authorization system, or a network
dependency.

All records used here are synthetic, test-only identities, references and
digests. No real holdout sample is read, transmitted, or referenced. No connected
model was invoked. Nothing here claims that an A0 round, a real provider
delivery, or an E02 real-model run has been executed.

## Reused versus newly built

- **Reused.** The #394/#395 visibility gate (`evaluate_visibility_request`,
  `VisibilityRequest`, `GateDecision.safety_audit`) is the only admission check
  for research material added to a final envelope or a tool turn; the exposure
  log calls it rather than re-deciding. The package's existing token/digest/field
  validation primitives and canonical `sha256:` digest are reused unchanged, so
  the exposure record cannot carry free text. Persistence reuses the existing
  append-only JSONL sink shape from `local.py::JsonlEventSink` (`ExposureLog`
  takes any `Callable[[dict], None]` sink), and `AcceptanceFailure` remains the
  single sanitised domain error.
- **Newly built.** This repository's acceptance package has no Workspace,
  Orchestrator, or invocation objects to extend — a package-wide search for
  `Workspace`, `append_event`, `Orchestrator`, `invocation`, `Campaign` and
  `Candidate` under `src/` found no such infrastructure. The exposure log is
  therefore the minimal append-only event log the ticket needs: frozen
  dataclasses, `Literal` status enums, standard library only, no new runtime
  dependency. Campaign / Iteration / consumer / action / invocation /
  research-family identities are carried as declared references, so a production
  Workspace can own the storage without this contract changing.

## Delivered contract

- `ExposureKey` (Campaign, Iteration, consumer, action, idempotency key) yields a
  canonical `action_key`. Each event additionally binds a `research_action_id`, a
  Context identity digest, the originating `research_family` (family id, test
  family, prior result ids), the frozen `policy` triple, and an `invocation_id`.
- Four event types — `context_prepared`, `envelope_delivered`,
  `delivery_uncertain`, `completion_linked` — map to the four states `prepared`,
  `delivered`, `delivery_uncertain`, `completed`. Only the transitions in
  `_ALLOWED_TRANSITIONS` are accepted. Uncertainty resolves forwards only;
  `delivered` never returns to `delivery_uncertain`, and no event ever returns an
  action towards "unseen".
- `DeliveryBinding` records the delivered envelope separately from the Context
  draft: `envelope_digest`, an optional approved-store `envelope_content_ref`, the
  `provider_request_id`, `template_version`, `tool_input_version`, `receipt_ref`,
  `response_ref`, and the material ids added after Context assembly. A tool turn
  is its own exposure action under the same `research_action_id`, so a later
  delivery links to the same research action instead of overwriting the draft.
- Material in `added_material_ids` must be cleared by the #394/#395 gate in the
  same append: the request must be deliverable, its safety audit must be `clear`
  or `not_applicable`, and every added id must appear among the gated materials.
  A blocked, unknown, ungated, or partially gated addition raises and the action
  keeps its previous state. The gate's `request_identity` is stored as
  `gate_identity`.
- `replay_coverage` is declared explicitly and validated: `full` is refused
  unless an approved-store reference exists, and `none` is refused when one does.
  A digest is an identity, never a body.
- Idempotency is per `(action_key, event_type)` over a canonical `input_digest`.
  The same key with the same frozen input returns the existing event — a
  duplicate callback never re-confirms a delivery. The same key with a different
  input is refused, never merged. A different idempotency key is a new action, so
  a fresh research intent is not misread as a retry.
- Binding immutability: every later event on an action must repeat the same
  Context identity, research family and policy, and two actions sharing a
  `research_action_id` must agree on Context identity and family.
- Recovery is conservative. A persistence failure on an event that reports an
  external fact leaves the action in `delivery_uncertain` with reason
  `persistence_failure` (marked `persisted: false`) and raises
  `ExposurePersistenceFailure`; it never downgrades an action that is already
  delivered. `ExposureLog.load` drops a torn trailing record, and an action left
  at `prepared` by that torn tail is promoted to `delivery_uncertain` with reason
  `process_interrupted` — a failed local write proves nothing about the external
  consumer. `readback` always reports `resend_allowed: false`.
- `context_exposure` spans Campaigns and Iterations, so a new Campaign, a rename,
  or a new task never returns an exposed or uncertain Context to `unseen`.
  `usage_history` publishes source-and-usage relations (Candidate ids, selection
  decision ids, test family, Context identity) and always reports
  `grants_eligibility: false`: multiplicity, independence and qualification stay
  with the originating statistical owner.
- `replay_exposure_delivery` checks **current** authorization through the same
  gate before any historical content is handed back. A currently unauthorized
  party gets `reconstruction: "denied"`, no payload, no Context identity, and the
  loader is never called; the stored events and the Context identity are
  unchanged. When the approved store does not hold the envelope, only
  `reconstruction: "limited"` is declared — the model is never re-invoked to
  manufacture the missing evidence.
- The event schema is a closed field set, so credentials, secrets, or unrelated
  private raw text cannot be attached; every string field is a safe token or a
  `sha256:` digest.

## Acceptance criteria mapping

| Criterion | Test evidence |
| --- | --- |
| Events link Campaign/Iteration, consumer/action, Context, policy, invocation and the originating research family; all four states have canonical readback | `test_all_four_states_have_canonical_readback_with_full_linkage`, `test_readback_of_an_unknown_action_is_empty_not_an_error`, `test_independent_invocation_counts_are_reported_per_action` |
| Envelope differing from Context is fully traceable; tool turns, responses and downstream usage have explicit references | `test_envelope_additions_are_traceable_with_versions_and_references`, `test_a_tool_turn_delivery_links_to_the_same_research_action`, `test_added_material_blocked_by_the_visibility_gate_is_never_recorded_as_delivered`, `test_added_material_without_a_visibility_request_is_refused`, `test_an_ungated_addition_cannot_ride_along_with_a_gated_one` |
| Uncertain delivery is conservative, does not assume non-exposure, does not blindly resend; changing Campaign does not restore unseen | `test_uncertain_delivery_never_claims_non_exposure_and_forbids_blind_resend`, `test_reconciling_an_uncertain_delivery_requires_a_real_receipt`, `test_a_new_campaign_does_not_restore_unseen_for_an_exposed_context`, `test_a_confirmed_delivery_cannot_be_returned_to_uncertain`, `test_an_out_of_order_event_is_refused` |
| Same key and same input recovers the existing event; a different input is refused; a new intent is not a retry | `test_the_same_key_and_the_same_input_recovers_the_existing_event`, `test_the_same_key_with_a_different_input_is_refused_not_merged`, `test_a_new_research_intent_is_not_treated_as_a_retry_of_an_old_request`, `test_an_action_binding_cannot_drift_between_events`, `test_one_research_action_cannot_carry_two_context_identities` |
| Hypothesis state machine over prepare / send / lost receipt / duplicate callback / retry / cross-Campaign; real interruption and persistence failure keep public readback | `TestExposureLifecycle` (`ExposureLifecycleMachine`, 40 examples x 20 steps, rules `prepare`, `send`, `lose_receipt`, `duplicate_callback`, `retry_with_a_different_input`, `complete`; invariants `exposure_never_regresses`, `each_event_type_is_recorded_at_most_once_per_action`), `test_a_torn_tail_leaves_a_prepared_action_uncertain_not_unseen`, `test_a_clean_reload_preserves_every_public_fact`, `test_a_persistence_failure_leaves_the_exposure_uncertain`, `test_a_persistence_failure_never_downgrades_an_already_delivered_action` |
| Replay coverage is stated explicitly, a hash is not a body, and records never leak secrets or protected content | `test_replay_coverage_cannot_be_full_without_a_stored_envelope`, `test_a_missing_payload_yields_only_a_limited_reconstruction`, `test_full_coverage_replays_from_the_approved_store_only`, `test_the_event_record_cannot_carry_secrets_or_free_text`, `test_the_persisted_log_never_contains_protected_body_text` |
| A currently unauthorized party cannot re-receive original content; old events and Context identity are unchanged | `test_a_currently_unauthorized_party_cannot_replay_historical_content`, `test_usage_history_publishes_relations_without_granting_eligibility`, `test_usage_history_is_not_cleared_by_a_later_campaign` |

### A0 reference acceptance

- **A0-P02** — covered on synthetic, #437-shaped controlled-delivery fixtures by
  `test_a0_p02_second_round_envelope_differs_from_context_and_loses_its_receipt`.
  A second-round envelope carries material the Context draft never held; that
  addition passes the #394/#395 gate first, and the delivery records its own
  provider request id, template and tool-input versions, receipt and response
  references. A following tool turn loses its receipt and becomes
  `delivery_uncertain`; a reload from the append-only file keeps it uncertain and
  keeps the Context `exposed` rather than `unseen`. With no stored payload, the
  replay declares `limited` only.
- **A0-M03 / A0-R01 (this ticket's slice)** — covered by
  `test_a0_m03_downstream_stop_decision_links_context_exposure_and_test_family`
  and `test_a0_r01_same_key_retry_reconciles_and_a_different_input_is_refused`,
  with `test_usage_history_is_not_cleared_by_a_later_campaign`. A downstream stop
  decision and its Candidate link back to the Context, the exposure and the test
  family; a same-key retry reconciles to the existing event while a differing
  input is refused; usage history survives a new Campaign and an already
  confirmed delivery is not confirmed twice.
- **Frozen B0, event taxonomy, public commands, state trajectories, independent
  invocation counts.** No frozen B0 sample exists: `A0-B0-RULES` (#434) and
  `A0-FIXTURES-ORACLE` (#437) are still `pending` in
  `docs/research/a0/a0_delivery_index.md`, so the connected part of the #431
  evidence remains **pending** and is not claimed here. The test event-type
  taxonomy is the four types above; the public commands are
  `ExposureLog.append`, `.state`, `.readback`, `.research_action_readback`,
  `.context_exposure`, `.usage_history`, `.export`, `.load`, and
  `replay_exposure_delivery`. State trajectories are read back verbatim from
  `readback()["state_trajectory"]`, and independent invocation counts from
  `readback()["invocation_count"]`.
- **Stand-ins versus real failures.** `DeliveryUncertainty.transport` separates
  `offline_stand_in` from `real_process`, and the A0-P02 test asserts the
  stand-in tool turn is labelled `offline_stand_in`. The torn-tail and
  persistence-failure tests are labelled `real_process`: they exercise a real
  truncated append-only file and a real failing sink, not a simulated transport.
- **E02 remains pending.** Real model evidence is produced later by #442. No
  stand-in success in this ticket is offered as evidence that E02 has run. This
  ticket's fragment acceptance does not wait on #441/#442/#443 or the EPIC.

## Verification

Baseline commit for this work: `641a0869b867944bd05bc87b6afc3366889bee1d`
(`main`, after #395 merged as PR #447).

Commands run from the QuantResearch worktree, before and after the change:

```text
# before (baseline 641a086)
python -m pytest src/quantresearch_acceptance -q \
    --ignore=src/quantresearch_acceptance/_spec027_installed_test.py
2 failed, 64 passed

# after
python -m pytest src/quantresearch_acceptance/_research_exposure_test.py -q
34 passed

python -m pytest src/quantresearch_acceptance -q \
    --ignore=src/quantresearch_acceptance/_spec027_installed_test.py
2 failed, 98 passed

python -m ruff check src/quantresearch_acceptance
All checks passed!

python -m compileall -q src/quantresearch_acceptance
success

git diff --check
success
```

The failure set is unchanged: the same two tests
(`_installed_test.py::test_installed_wheel_has_no_source_checkout_precedence`
and `_a0_installed_test.py::test_a0_installed_tracer_is_not_source_preferred`)
fail before and after, because they require a no-source installed-wheel
environment rather than a source checkout. `_spec027_installed_test.py` still
fails collection on this machine for the missing `apex_research` wheel, as
recorded for #394 and #395; it is ignored in both the before and the after run
and is not counted as #396 evidence. The delta is 64 -> 98 passed, 0 -> 0 new
failures.

Red/green was confirmed for the new logic rather than assumed. Each patch was
applied, the suite run, and the patch reverted:

- Transition ordering disabled: 3 fail
  (`test_a_confirmed_delivery_cannot_be_returned_to_uncertain`,
  `test_an_out_of_order_event_is_refused`, `TestExposureLifecycle::runTest`).
- Both visibility-gate checks disabled: 1 fails
  (`test_added_material_blocked_by_the_visibility_gate_is_never_recorded_as_delivered`).
  Disabling only the deliverability check leaves the suite green because the
  safety-audit check still refuses that request; both arms of the #394/#395
  reuse had to be removed to turn it red.
- Idempotency conflict rewritten to silently merge: 3 fail
  (`test_the_same_key_with_a_different_input_is_refused_not_merged`,
  `test_a0_r01_same_key_retry_reconciles_and_a_different_input_is_refused`,
  `TestExposureLifecycle::runTest`).
- Persistence-failure uncertainty marker disabled: 1 fails
  (`test_a_persistence_failure_leaves_the_exposure_uncertain`).
- Torn-tail promotion disabled: 1 further fails
  (`test_a_torn_tail_leaves_a_prepared_action_uncertain_not_unseen`).

After restoring the module, all 34 pass again.

`hypothesis` remains the test-only dependency group declared for #395; no new
runtime dependency was added and the exposure log itself is standard library
only.

## Acceptance conclusion

The local #396 exposure-lifecycle and usage-linkage behaviour is verified for the
covered A0-P02 and A0-M03 / A0-R01 slices on synthetic records. This is
engineering and acceptance-seam evidence only. It does not claim a connected E02
model run, real holdout access, a frozen B0 sample, research qualification, or
profitability.
