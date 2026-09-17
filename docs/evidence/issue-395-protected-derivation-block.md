# #395 Protected result and derived-material delivery block evidence

## Scope

This evidence covers the QuantResearch acceptance seam for #395 (RM-V1B.2), under
the constraints in #395, parent SPEC #384, the R2 policy in #381 (RM-R2-3/6/7 and
the shared implementation policy), and the gate delivered for #394. It extends
`quantresearch_acceptance.research_visibility`; it does not add a second
authorization system, a Pydantic contract, or a network dependency.

All records used here are synthetic, test-only identities and payloads. No real
holdout sample is read, transmitted, or referenced. Nothing here claims that a
connected research run, a real model delivery, or an A0 round has been executed.

## Delivered contract

- `VisibilityRequest` gains an optional, frozen `closure_budget` (default
  `DEFAULT_PROTECTION_CLOSURE_BUDGET` = 64, maximum
  `MAX_PROTECTION_CLOSURE_BUDGET` = 4096). It is part of the request identity, so
  the declared traversal bound is auditable rather than implicit.
- `_protection_closure` walks the declared derivation graph of each material with
  a bounded, deterministic explicit-stack DFS. Duplicate edges are canonicalised
  before traversal, so repeated edges and repeated nodes cannot change a decision
  or consume budget. Protection propagates along every declared hop, so a
  multi-hop chain cannot launder a protected source by republishing a derived
  record. The walk is implemented with the standard library only; NetworkX stays
  an Apex-internal concern per the shared policy.
- Closure defects fail closed and are reported as stable safe codes:
  `closure_incomplete` (an unresolvable or incomplete transitive endpoint),
  `closure_budget_exhausted` (the declared bound was reached), and
  `closure_not_acyclic` (a back edge in a lineage that must be a DAG). The first
  two join the incompleteness family: strict mode is `restricted`, audit mode is
  `unknown`, and neither is ever deliverable. A missing source is never rewritten
  as an optional one in order to release delivery.
- `MaterialVisibilityDecision.closure_digest` is a canonical digest of the closure
  membership. It is stable across display-name, campaign, and dataset-version
  renames and across duplicate edges and nodes.
- `GateDecision.safety_audit` reports how post-assembly additions were handled.
  At `final_envelope` and `tool_return`, material the declared Context does not
  carry is re-checked and given an explicit `clear` / `unknown` / `blocked`
  status, so a blocked addition is neither silently dropped nor silently
  delivered. At other stages the status is `not_applicable`. The field carries a
  stage, a scope, and a status only; it carries no identifiers, counts, reasons,
  or lineage.
- A non-deliverable `GateDecision.as_dict()` omits `materials` entirely and
  reports `delivery: "blocked"`. A non-delivered `GuardedDelivery.as_dict()`
  omits `payload_count` and `material_ids` and reports a `delivery_status` of
  `restricted` or `unavailable`. Detailed per-material facts remain reachable
  only on the in-process decision object, at the trusted policy/audit boundary.
- `guard_visibility_delivery` catches loader exceptions and reports the
  sanitised `unavailable` state. Source text, provider debug state, and the
  exception chain do not cross the public delivery boundary.
- Protected, unknown, and unavailable states remain distinct from `allowed`.
  None of them is repackaged as strict out-of-sample eligibility, and
  reachability alone never grants eligibility.

## Acceptance criteria mapping

| Criterion | Test evidence |
| --- | --- |
| Filtering completes before any consumer read; new names, Campaign, data version and multi-hop derivation do not lift protection | `test_a0_p01_derived_artifacts_are_blocked_before_any_consumer_read` (24 cases), `test_multi_hop_derivation_cannot_launder_a_protected_source`, `test_renaming_a_multi_hop_chain_does_not_lift_protection`, `test_property_every_hop_of_a_chain_keeps_the_tail_protected`, `test_property_renaming_never_lifts_protection` |
| No leakage through normal results, errors, logs, exclusion counts/reasons, debug output or derivation hints | `test_restricted_output_cannot_reveal_material_ids_counts_or_lineage`, `test_loader_failure_has_a_safe_public_result`, `test_denied_decision_wire_contract_contains_only_stable_safe_fields`, and the zero-read / no-repr assertions in the A0-P01 matrix |
| Protected / unknown / unavailable states are never repackaged as out-of-sample eligible | `test_missing_metadata_is_restricted_in_strict_and_unknown_in_audit`, `test_exhausted_traversal_budget_is_refused_not_downgraded_to_optional`, `test_a_missing_closure_endpoint_is_never_read_as_unprotected` |
| Hypothesis covers duplicate edges/nodes, multi-hop chains, renaming, missing endpoints and budget boundaries; incomplete lineage is never treated as unprotected | `test_property_duplicate_edges_and_nodes_do_not_change_a_decision`, `test_property_every_hop_of_a_chain_keeps_the_tail_protected`, `test_property_renaming_never_lifts_protection`, `test_property_a_missing_closure_endpoint_is_never_deliverable`, `test_property_the_traversal_budget_boundary_fails_closed` |
| Context may be deliverable while envelope / tool-return additions are blocked pre-delivery with a safety-audit status | `test_envelope_additions_are_blocked_and_get_a_safety_audit_status`, `test_tool_return_additions_are_audited_and_earlier_stages_are_not` |
| Revoked current authorization cannot redeliver via old Context, cache or historical policy; the restricted state does not mutate the original Context identity | `test_revoked_current_access_blocks_historical_redelivery_without_rewriting_context`, `test_a_restricted_delivery_does_not_mutate_the_submitted_context` |

### A0 reference acceptance

- **A0-P01** — covered on test-only records. A synthetic A0 protected result is
  turned into a derived parameter suggestion, component rationale, report summary
  and chart projection, and into a multi-hop derivation chain. Every derived form
  is blocked before any consumer read at `initial_read`, `ranking`, `embedding`,
  `summary`, `research_model` and `final_envelope`; the loader is asserted never
  to be called. Renaming the display name, Campaign and dataset version does not
  lift protection. Normal output, counts, reasons and the error path are asserted
  not to carry the protected identifiers, universe or record type.
- **A0-C02** — covered for the protection-closure slice. A missing required
  derivation source and an insufficient traversal budget both refuse; neither is
  downgraded to an optional item in order to release delivery. A Context draft
  that passes does not carry new envelope or tool-return content: those additions
  are re-checked and produce an explicit blocked safety-audit status.
- Baseline, public operations and consumer-side read counts are recorded below.
  The real holdout is not used in CI, and these synthetic samples are not
  presented as real research evidence.
- The upstream A0 artifacts are still `pending` in
  `docs/research/a0/a0_delivery_index.md` (`A0-B0-RULES` for #434,
  `A0-FIXTURES-ORACLE` for #437). No frozen B0 sample was available, so the
  connected part of the #431 evidence remains **pending** and is not claimed
  here. This ticket's fragment acceptance does not wait on #441/#442/#443 or the
  EPIC.

## Verification

Baseline commit for this work: `b033bd3aad431e015ef14479ebd9fdde8f0b09c3`
(branch `codex/444-a0-t04`, even with `origin/main` at the time of branching).

Commands run from the QuantResearch worktree:

```text
python -m pytest src/quantresearch_acceptance/_research_visibility_test.py -q
58 passed

python -m pytest src/quantresearch_acceptance -q \
    --ignore=src/quantresearch_acceptance/_spec027_installed_test.py
2 failed, 64 passed

python -m ruff check src/quantresearch_acceptance
All checks passed!

python -m compileall -q src/quantresearch_acceptance
success

git diff --check
success
```

The two failures (`_installed_test.py::test_installed_wheel_has_no_source_checkout_precedence`
and `_a0_installed_test.py::test_a0_installed_tracer_is_not_source_preferred`) are
pre-existing on the baseline commit: they reproduce identically with this change
stashed, because they require a no-source installed-wheel environment rather than
a source checkout. `_spec027_installed_test.py` still fails collection on this
machine for the missing external owner wheels, as recorded for #394. Neither
condition is counted as #395 evidence.

Red/green was confirmed for the new logic rather than assumed. With the closure
recursion and the budget check disabled, six tests fail
(`test_multi_hop_derivation_cannot_launder_a_protected_source`,
`test_exhausted_traversal_budget_is_refused_not_downgraded_to_optional`,
`test_a_missing_closure_endpoint_is_never_read_as_unprotected`,
`test_a_cyclic_derivation_graph_fails_closed_in_every_mode`,
`test_property_every_hop_of_a_chain_keeps_the_tail_protected`,
`test_property_the_traversal_budget_boundary_fails_closed`). With the
envelope-addition safety audit disabled, two further tests fail
(`test_envelope_additions_are_blocked_and_get_a_safety_audit_status`,
`test_tool_return_additions_are_audited_and_earlier_stages_are_not`). Both
patches were reverted and the full 58 pass again.

`hypothesis` is declared as a test-only dependency group in `pyproject.toml`; it
is not a runtime dependency and the gate itself remains standard library only.

## Acceptance conclusion

The local #395 delivery-block behaviour is verified for the covered A0-P01 and
A0-C02 slices on synthetic records. This is engineering and acceptance-seam
evidence only. It does not claim a connected E02 model run, real holdout access,
research qualification, or profitability.
