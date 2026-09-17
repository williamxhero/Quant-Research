# #401 Source correction, formal currency and the read-only Reporting projection

## Scope

This evidence covers the QuantResearch acceptance seam for #401 (RM-V1D.1),
under the constraints in #401, parent SPEC #386, the R2 policy in #381
(RM-R2-4/6/7 and the shared implementation policy), and the contracts delivered
for #394, #395, #396, #397, #398 and #399. It adds
`quantresearch_acceptance.research_currency`; it does not add a Pydantic
contract, a statistics or reporting computation layer, a second eligibility
authority, a database client, a network dependency, or NetworkX.
`research_currency` is standard library only.

All records used here are synthetic, test-only identities, references and
digests. No real holdout sample is read, transmitted or referenced. No connected
model was invoked, no backtest was run, and **nothing was deployed or uploaded
to MLflow**. This ticket's evidence is contract- and seam-level, not a real
connected A0 round. The real first and second connected rounds remain #441 and
#442's job; comprehensive replay over real research material remains #408's.
This ticket did not wait on #441 / #442 / #443.

`docs/research/a0/a0_delivery_index.md` and `.json` were re-verified at the time
of this commit: `A0-B0-RULES`, `A0-FIXTURES-ORACLE`, `A0-REFERENCE-STRATEGY`,
`A0-B1-DATA-RUN`, `A0-ROUND-1`, `A0-ROUND-2` and `A0-FINAL-EVIDENCE` remain
`pending`.

## NetworkX was deliberately not added

#401's R2 says "NetworkX 仅从完整有界公共谱系计算潜在影响". A repository-wide
search was run before any code was written (`grep -ri networkx` over `*.py`,
`*.toml`, `*.txt`, `*.cfg`): **zero matches**. NetworkX is not a dependency of
this package and is used nowhere in it.

#381's shared implementation policy scopes it precisely: "NetworkX 仅在 Apex 内部
复用有界图算法" — Apex-internal, not this acceptance package. The two equivalent
graph problems already solved here were solved without it:

- `research_visibility._protection_closure` (#395) — bounded explicit-stack DFS
  over canonically ordered derivation edges, with a traversal budget.
- `research_context._required_closure` (#397) — the same shape for the required
  evidence closure.

`research_currency.assess_correction_impact` follows that precedent exactly: a
bounded explicit-stack DFS over the *reversed* public edges, with a frozen
`impact_budget`, canonical ordering and an explicit `budget_exhausted` code. The
assessment publishes `"traversal": "bounded_explicit_stack_dfs"` so the choice is
recorded in the public record rather than only in a commit message.

This is a deliberate consistency choice, not an oversight. #401's own R2 also
says "不新增 ... 统计或报告计算层"; adding a graph library to walk four nodes
would add a production dependency with no capability the existing pattern lacks,
and #381 requires a new dependency to carry maintenance, adoption, licence,
Python-range and lock/upgrade evidence. `test_the_module_opens_no_store_and_makes_no_external_call`
asserts there is no `networkx` import and no `networkx.` call in the module.

## The correction / currency read-model seam that was built

The real read model is owned upstream (#392, closed outside this repo; its
published comparability facts are consumed by reference — `git log --all
--grep='#392'` returns nothing here, exactly as #397 and #399 recorded). So the
seam is a `typing.Protocol`, matching #399's `ResearchEngineSeam` pattern:

```python
class SourceCurrencyReadModel(Protocol):
    def lineage(self) -> Mapping[str, object]: ...        # complete bounded public graph
    def corrections(self) -> Sequence[Mapping[str, object]]: ...   # append-only
    def currency_facts(self) -> Sequence[Mapping[str, object]]: ...  # append-only
```

Three methods, not one, because they answer three different questions that must
never be conflated: the graph says what *could* be affected, a correction says
what the owner changed and when the system learned it, and a currency fact says
what the owner formally believes about one statement.

`read_source_currency(model)` consumes the seam **once** and freezes the result
into a `SourceCurrencyView`. Nothing downstream calls the seam again, so a
projection is reproducible from public facts without the upstream service.
`test_the_read_model_seam_is_consumed_once_and_then_frozen` asserts the recorded
call list is exactly `["lineage", "corrections", "currency_facts"]` before and
after a full readback.

## Two times, never one

Every correction and every currency fact carries `applicable_at` (when the fact
applies to the world) and `system_known_at` (when this system learned it).
`SourceCurrencyView.as_of(cutoff)` filters on `system_known_at` **alone**. The
fixtures make the two impossible to confuse: the test correction is published at
`2026-09-20` and applies to `2019-01-01`, while the old Context's knowledge
cutoff is `2026-09-10`. A filter on applicability time would let it through; the
filter on system-known time does not.

`SourceCurrencyView` is a frozen dataclass and `append_correction` returns a
*new* view, so a correction published today has no path into a Context frozen
yesterday.

## The currency state contract

`CURRENCY_STATE_CONTRACT` freezes `current`, `revalidation_due`, `stale`,
`superseded`, `invalidated` and `unknown` with a version, and
`CURRENCY_STATE_CONTRACT_DIGEST` takes part in every projection identity, so a
renamed or reordered state is a different projection rather than a silent
relabelling. The only derived bit is `usable_as_current_evidence`
(`current` / `revalidation_due` true, everything else false) — a *display* rule
over the owner's own state, never a judgment about the research. A statement the
owner published no fact about is `unknown` with provenance `["unknown"]`; it is
never quietly `current`.

`refresh_formal_currency` keeps the basis in the request rather than inferring it
from a payload. `owner_evidence` and `owner_decision` refresh (and only with an
`owner_evidence_ref`); `summary`, `explanation` and `discovery_only_review`
return `refreshed: false` with reason `<basis>_is_not_owner_evidence` and report
the owner's existing state back unchanged.

## Impact, and the three states it can have

| Situation | State |
| --- | --- |
| Reachable over known edges, conditions intersect | `potentially_affected` |
| Owner's precise conditions are disjoint from the statement's | `not_affected` |
| Unknown dependency edge, undeclared node, unknown conditions, incomplete graph, exhausted budget, target off-graph | `needs_review` |

`needs_review` is sticky downstream, `not_affected` stops propagation on that
path (a descendant reachable another way is still reached by that path), and
`invalidated` is not in the enum at all. `not_affected` is only ever *claimed*
on a graph that is declared complete, has no dangling edges, whose correction
target is in it, and whose walk finished inside budget — otherwise every
`not_affected` is downgraded to `needs_review`. `as_dict()` publishes
`invalidates_downstream: false`, `blanket_invalidation: false` and
`refreshes_formal_currency: false`.

## Reporting shows, it does not compute

`ReportingProjection.readback()` carries the #397 brief verbatim, the owner's
published `genome_compare` verbatim, the owner's currency statuses, the visible
corrections and #396's envelope linkage. `REPORTING_GUARANTEES` is carried into
every readback with `recomputes_metrics`, `recomputes_independence`,
`recomputes_conflicts`, `recomputes_eligibility`, `recomputes_genome_diff`,
`traverses_private_graph`, `refreshes_formal_currency`, `grants_eligibility`,
`invalidates_downstream` and `scanned_full_history` all false, and
`mlflow_deployment: "none"`.

`_sourced()` guarantees every gap, candidate step and coverage limitation keeps
an owner provenance or the explicit token `unknown` — never neither.

The exposure link must name the projected Context's own identity (a projection
cannot pair one Context's brief with another delivery's envelope), and it
republishes #396's `replay_coverage` rule: `full` requires a stored envelope
reference, and the public view always states `digest_is_not_content: true` with
`full_content_available` derived from the coverage rather than from the digest.

`deliver_reporting_projection` re-evaluates the #394/#395 gate on **every**
delivery. A denied reader gets a fixed five-field refusal with no identity, no
counts and no per-source reasons, and the projection it was refused for is
unchanged afterwards.

## Acceptance criteria mapping

| Criterion | Test evidence |
| --- | --- |
| 1. Potential impact located along the public lineage; uncertainty is `needs_review`; never a blanket invalidation | `test_a_correction_locates_multi_hop_potential_impact_over_the_public_lineage`, `test_an_unknown_dependency_is_needs_review_and_never_invalidates_downstream`, `test_needs_review_travels_downstream_but_stays_needs_review`, `test_precise_owner_conditions_narrow_the_affected_scope`, `test_a_statement_with_unknown_conditions_is_needs_review_not_excluded`, `test_an_incomplete_graph_downgrades_not_affected_rather_than_asserting_it`, `test_an_edge_to_an_undeclared_node_is_graph_incomplete_and_needs_review`, `test_an_exhausted_impact_budget_is_needs_review_not_a_clean_answer`, `test_a_cyclic_public_lineage_terminates_without_inventing_an_invalidation`, `test_a_correction_target_outside_the_public_lineage_is_needs_review`, `test_the_impact_walk_is_the_declared_graph_not_the_declaration_order` |
| 2. Only owner evidence / decision refreshes formal currency; old Finding / Context keep identity and policy | `test_only_owner_evidence_or_decision_refreshes_formal_currency`, `test_a_new_summary_or_explanation_never_refreshes_formal_currency`, `test_an_owner_decision_without_evidence_does_not_refresh`, `test_the_currency_state_contract_is_frozen_and_versioned`, `test_an_impact_assessment_never_refreshes_currency`, `test_the_old_context_keeps_its_identity_and_policy_after_a_correction` |
| 3. A new brief uses currently-known status; old snapshots take no hindsight; system-known time independently verifiable | `test_a_correction_published_later_is_invisible_to_an_older_cutoff`, `test_an_old_snapshot_projection_shows_no_hindsight_and_a_new_one_does`, `test_the_system_known_time_is_published_and_independently_verifiable`, `test_a_projection_cannot_cite_a_correction_its_cutoff_cannot_see`, `test_a_known_invalidated_conclusion_is_not_presented_as_current_evidence`, `test_the_latest_owner_fact_wins_by_system_known_time` |
| 4. A currently-unauthorized party cannot re-read via an old policy or cache; the refusal mutates nothing and leaks nothing | `test_a_currently_unauthorized_reader_cannot_re_read_via_the_old_policy`, `test_a_restricted_response_leaks_no_counts_reasons_or_identifiers`, `test_a_restricted_response_does_not_rewrite_the_original_objects`, `test_revoking_access_after_a_delivery_blocks_the_next_one` |
| 5. Reporting recomputes nothing and traverses no private graph; every gap / suggestion carries an owner source or `unknown` | `test_reporting_shows_only_already_published_material`, `test_reporting_never_recomputes_metrics_independence_conflicts_or_a_genome_diff`, `test_every_gap_and_candidate_step_carries_an_owner_source_or_unknown`, `test_a_digest_is_never_presented_as_the_delivered_content`, `test_full_replay_coverage_cannot_be_declared_without_a_stored_envelope`, `test_the_exposure_link_must_name_the_projected_context`, `test_the_projection_surfaces_the_real_context_envelope_and_replay_linkage`, `test_the_module_opens_no_store_and_makes_no_external_call` |
| 6. Hypothesis over multi-hop impact, unknown dependency, time cutoffs and correction appends; state recoverable after deleting the projection | `test_impact_is_always_one_of_three_states_and_never_an_invalidation` (60 examples), `test_appending_a_correction_never_changes_an_older_knowledge_cutoff` (60), `test_a_non_owner_basis_never_moves_a_published_state` (60), `test_a_projection_always_rebuilds_from_its_public_record` (40), `test_a_projection_is_rebuilt_from_its_public_record_alone`, `test_deleting_the_display_projection_loses_nothing`, `test_a_doctored_projection_record_fails_loudly` |
| 7. U5 and limited replay coverage pass through public readback, with no new LLM / backtest call, and no MLflow | `test_a0_u5_and_limited_replay_coverage_pass_through_public_readback_only`, `test_the_module_opens_no_store_and_makes_no_external_call`, `test_a_digest_is_never_presented_as_the_delivered_content` |

### What U5 turned out to mean

`U1`-`U6` come from #381's "Testing Decisions and joint research-use scenarios"
table (`gh issue view 381`). The table row is:

> **U5 来源纠正** — 新简报使用当前纠正/时效，旧 Context 保持当时身份与内容。

That is: *source correction*. A new brief uses the current correction and
currency state; the old Context keeps the identity and the content it had at the
time. (`U4` is the single-component comparison row, and `U6` is the
delete-the-projection-and-rebuild row, which this ticket's reconstruction tests
also exercise.)
`test_a0_u5_and_limited_replay_coverage_pass_through_public_readback_only` runs
it end to end: one Context identity, two knowledge cutoffs, identical published
brief, no corrections visible at the old cutoff, `correction-1` visible at the
new one, `support-1` going from `unknown` to `revalidation_due`, replay coverage
stated as `limited`, `mlflow_deployment: "none"`, and the whole readback
reproduced from the public record alone.

### A0 reference acceptance

Following the precedent set for #394-#399, the A0 slice runs on synthetic,
#437-shaped, explicitly test-only records. It asserts contract shape on frozen
stand-ins; it does **not** claim a frozen B0, a real A0 round, or a real
second-round model delivery.

- **A0-H01** — `test_a0_h01_a_correction_updates_the_current_brief_without_touching_the_old_one`.
  A correction is appended inside an isolated, test-only view. The historical
  projection at cutoff `2026-09-10` shows `published_corrections: []` and all
  three statements `unknown`; the current projection at `2026-09-30` shows
  `correction-1` and `support-1: revalidation_due`, with
  `potentially_affected == ["counter-1", "data-1", "support-1"]` and
  `invalidates_downstream: false`. The Context frozen before the correction is
  asserted identical by identity *and* by full readback, before and after. A
  `summary` refresh of the same statement returns `refreshed: false` and
  `grants_eligibility: false`.
- **A0-C01 / A0-L02 (projection slice)** —
  `test_a0_c01_l02_reporting_source_is_published_only_and_revocation_blocks_redelivery`.
  The delivered source contains only the published baseline (`baseline-v0`), the
  published comparison (`comparison-v0-vs-v1`), the required counter-evidence
  (`counter-1`), the published disagreements and reusable assets, the sourced
  gaps and candidate steps, and the permitted envelope with
  `replay_coverage: limited` / `full_content_available: false` /
  `envelope_content_ref: None`. Revoking current access then blocks re-delivery
  with `current_authorization_denied`, and the projection readback is asserted
  byte-identical before and after the refusal.
- **Frozen submission (B0 stand-in, per #431)** — the public inputs are the
  test's own literals: Context snapshot `snapshot-2026-09-10` / cutoff
  `2026-09-10T00:00:00Z`, template `quant-research.research-brief.v1` at
  template version `v1`, policy `research-policy` `v2`, currency state contract
  `quant-research.research-currency-state` `v1`, correction `correction-1`
  (`applicable_at 2019-01-01T00:00:00Z`, `system_known_at 2026-09-20T00:00:00Z`),
  current cutoff `2026-09-30T00:00:00Z`. Expected outputs are the literals
  asserted in the A0 tests above; actual outputs are what the assertions compare.
  Before- and after-correction references are the two projections in
  `test_an_old_snapshot_projection_shows_no_hindsight_and_a_new_one_does`, and
  the read-only reconstruction evidence is
  `test_deleting_the_display_projection_loses_nothing`.
- **Manual correction does not touch real research facts** —
  `test_a0_a_manual_test_correction_does_not_touch_real_research_facts`
  constructs the with-correction and the without-correction views separately and
  asserts neither can reach the other, and that the published brief is the same
  in both. Whether a real owner correction exists or not therefore does not
  change which branches this suite covers.

## Test evidence

Command, run from `D:\WILL\STOCK\QuantResearch`:

```
python -m pytest src/quantresearch_acceptance -q \
  --ignore=src/quantresearch_acceptance/_spec027_installed_test.py
```

- Before (`main` at `d084077`): **2 failed, 243 passed**.
- After: **2 failed, 292 passed** (+49, all in `_research_currency_test.py`).

The two failures are identical before and after, by name:
`_installed_test.py::test_installed_wheel_has_no_source_checkout_precedence` and
`_a0_installed_test.py::test_a0_installed_tracer_is_not_source_preferred`. Both
require a no-source installed-wheel environment rather than a source checkout,
as recorded for #394-#399. `_spec027_installed_test.py` still fails collection on
this machine for the missing `strategy_workspace` / `apex_research` wheels, also
as recorded for those tickets; it is ignored in both the before and the after run
and is not counted as #401 evidence. There are no other deltas.

`python -m ruff check src/quantresearch_acceptance` passes, and
`python -m compileall -q src/quantresearch_acceptance` is clean.

Red/green was confirmed for the new logic rather than assumed. Each patch was
applied to `research_currency.py` alone, `_research_currency_test.py` was run,
and the module was restored (the restored file was diffed byte-for-byte against
the pre-break copy; the diff was empty):

- An unknown dependency edge no longer produces `needs_review`: **2 fail**
  (`test_an_unknown_dependency_is_needs_review_and_never_invalidates_downstream`,
  `test_needs_review_travels_downstream_but_stays_needs_review`).
- `as_of` stops filtering on `system_known_at`, i.e. hindsight backfills an old
  snapshot: **6 fail**, including
  `test_a_correction_published_later_is_invisible_to_an_older_cutoff`,
  `test_a_projection_cannot_cite_a_correction_its_cutoff_cannot_see`,
  `test_appending_a_correction_never_changes_an_older_knowledge_cutoff` and
  `test_a0_h01_a_correction_updates_the_current_brief_without_touching_the_old_one`.
- `recomputes_genome_diff` flipped to true: **1 fail**
  (`test_reporting_never_recomputes_metrics_independence_conflicts_or_a_genome_diff`).
- The restricted response carries the projection identity: **4 fail**, including
  `test_a_restricted_response_leaks_no_counts_reasons_or_identifiers` and
  `test_a0_c01_l02_reporting_source_is_published_only_and_revocation_blocks_redelivery`.
- A `summary` basis refreshes formal currency: **3 fail**
  (`test_a_new_summary_or_explanation_never_refreshes_formal_currency`,
  `test_a_non_owner_basis_never_moves_a_published_state`,
  `test_a0_h01_a_correction_updates_the_current_brief_without_touching_the_old_one`).
- The incomplete-graph downgrade removed, so `not_affected` is asserted on a
  graph that is not provably complete: **4 fail**
  (`test_an_incomplete_graph_downgrades_not_affected_rather_than_asserting_it`,
  `test_an_exhausted_impact_budget_is_needs_review_not_a_clean_answer`,
  `test_a_correction_target_outside_the_public_lineage_is_needs_review`,
  `test_impact_is_always_one_of_three_states_and_never_an_invalidation`).

After restoring the module, all 49 pass again and the suite returns to
2 failed, 292 passed.

Two design defects were found by running the tests rather than by inspection and
were fixed before the commit: the correction's own target was being narrowed out
by its own precise conditions (it is corrected by construction, so the conditions
narrow its *dependents*), and a correction target outside the public graph left
the rest of the graph asserted as `not_affected` when nothing was known about
where that target sits.

`hypothesis` remains the test-only dependency group declared for #395; no new
runtime dependency was added.

## Acceptance conclusion

The local #401 correction / currency read-model consumption, bounded public
lineage impact assessment, historical-versus-current separation, current
authorization on re-delivery and read-only Reporting projection behaviour is
verified on synthetic records, together with the covered A0-H01 and A0-C01 /
A0-L02 slices and the U5 scenario. This is engineering and acceptance-seam
evidence only. It does not claim a connected E01/E02 round, real holdout access,
a frozen B0 sample, research qualification, an MLflow deployment, or
profitability.
