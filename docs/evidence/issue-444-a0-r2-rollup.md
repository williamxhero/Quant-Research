# A0 final acceptance rollup — R2 correction (2026-09-19)

This corrects three things in [#443's rollup](issue-443-a0-final-rollup.md)
(baseline `db41a44`, 2026-09-17). It does not replace that document — #443
was an accurate record of its own baseline. This is a second, later,
equally checkable snapshot, published by
`src/quantresearch_acceptance/research_a0_final_rollup_r2.py` and backed by
real tests in `_a0_r2_real_evidence_test.py` and
`_research_a0_final_rollup_r2_test.py`.

> **Same-day update**: this document originally left A0-X01/X02 unpassed,
> pending a real independent-oracle replay (`G-438-REPLAY-R2`). That replay
> was run for real a few hours later
> ([#471](https://github.com/williamxhero/Quant-Research/issues/471)) and
> both scenarios passed. The sections below are updated in place rather than
> left stale; `a0_acceptance_evidence_index_r2.json` reflects the final
> **24/27** count, not the intermediate 22/27.

## What changed

**A0-E01, A0-E02 and A0-E03 — the three scenarios most damaging to launder —
all moved from unproven to genuinely executed**, each with real, connected,
in-repo-checkable evidence:

| Scenario | #443 (2026-09-17) | R2 (2026-09-19) | Real evidence |
| --- | --- | --- | --- |
| A0-E01 | `owner_reported_unverifiable` | `executed` / passed | Six real connected `quant-runtime` formal runs (development/validation/holdout × V0/V1) against live MarketHub data. V0 places 70 real round-trip trades; V1 places zero in every window — independently spot-checked by replaying the real bars through the state machine outside the Nautilus engine (every real pivot-confirmation event carried volume *above* its baseline, never below the 75% contraction threshold). |
| A0-E02 | `not_run` | `executed` / passed | A real, owner-authorized `run_a0_round_two` through yosef-server's CPA proxy (deepseek-v4-1-flash). `delivery_state=delivered`, `delivery_layer=real_connected`, `proves_model_use=true`. The model reviewed the real A0-E01 finding and proposed `stop`. |
| A0-E03 | `not_run` | `executed` / passed | Real wheels built for all five owner packages, installed into a fresh isolated venv with no source checkout on `sys.path`. `_spec027_installed_test.py` (previously uncollectable) and both source-precedence guards passed for real: 12/12. |
| A0-X01 | `pending` | `executed` / passed | The T04 independent oracle (`fixture_inputs.json`/`expected_traces.json`, previously only statically reviewed) replayed for real against the current strategy: shape trace matches, and the oracle's own volume-boundary operands (74/75/76 against a five-prior-bar mean of 100) match exactly — see [#471](https://github.com/williamxhero/Quant-Research/issues/471). |
| A0-X02 | `pending` | `executed` / passed | Same replay, using the oracle's own future-bar append sequence (close=102 then 98) verbatim: the confirmed entry decision is unchanged, and a genuine new, later-dated exit decision is correctly distinguished from a backfill. |

Pass count: **24 / 27**, up from 19/27.

## A self-correction: G-438-STRATEGY was a false negative

#443's gap list stated: *"No 'crossback' implementation was found in any
checked-out repository"*, searching `quant-runtime/src`, `apex-research/src`
and `strategy-workspace/src`. The real implementation lives at
`strategy-workspace/strategies/equity/a0-ema-crossback/` — a **sibling** of
`src/`, not a subdirectory of it. It existed at commit `c4c401b`
(2026-09-13), *before* #443 was even written, with a real Nautilus adapter,
a real state-machine core, and passing domain tests.

The rule file, parameters, variants and oracle fixtures were likewise
already real and owner-approved (2026-09-14) — #443's own delivery-index
citations for `a0-rules`/`a0-parameters`/`a0-variants` already showed
`frozen-default-approved` with real commits, which its own gap-list text
(`G-434-RULES`, `G-437-ORACLE`: "never delivered as an owner artifact")
contradicted. This rollup corrects that inconsistency rather than quietly
using the corrected facts.

**Same-day follow-up**: the narrower gap this correction left behind
(`G-438-REPLAY-R2` — artifacts real, independent-oracle replay unexecuted)
was itself resolved a few hours later. [#471](https://github.com/williamxhero/Quant-Research/issues/471)
ran the T04 oracle's own `fixture_inputs.json`/`expected_traces.json` for
real against the current strategy, using the oracle's own volume-boundary
values and append sequence rather than self-chosen numbers. A0-X01 and
A0-X02 both passed; `G-438-REPLAY-R2` no longer appears in `GAPS_R2`.

## Two more code bugs found and fixed while producing this evidence

Neither was previously known. Both are merged, tested red-before/green-after:

- **Missing exit logic + multi-instrument state sharing**
  ([#469](https://github.com/williamxhero/Quant-Research/issues/469),
  [StrategyWorkspace#1](https://github.com/williamxhero/StrategyWorkspace/pull/1)):
  the reference strategy never emitted a sell order (positions opened and
  never closed), and one `A0EmaCrossbackCore` instance was shared across
  every subscribed instrument, cross-contaminating multi-symbol backtests.
- **Volume-contraction baseline off-by-one**
  ([#470](https://github.com/williamxhero/Quant-Research/issues/470),
  [StrategyWorkspace#2](https://github.com/williamxhero/StrategyWorkspace/pull/2)):
  the current bar was folded into its own baseline, contradicting
  `a0_parameters.json`'s explicit "current bar is excluded from its own
  baseline" rule. Confirmed real (not cosmetic) via a differential test, but
  did not change the real 70-trade sample's outcome — none of the real
  trades were near the true/buggy threshold boundary.

## The four reports, corrected

- **Engineering**: unchanged conclusion (`pass_with_declared_gaps`), updated
  scenario count (24/27).
- **Rule implementation**: `cannot_be_concluded` → `concluded_pass`. The
  rule/oracle/strategy baseline is real, and the independent-oracle replay
  for A0-X01/X02 has now been run and matched.
- **Research findings**: `no_research_finding` → `real_finding_published`.
  As specified in a0-r2, the volume-contraction filter does not merely fail
  to add value — it eliminates the entire strategy (V1: 0 trades across
  2015–2026; V0 alone: 70 trades, near-zero Sharpe, 28.6% win rate). The
  formal SPEC-013 statistical layer was attempted for real and found a
  genuine `quant-research.result.v2` vs `v4` schema gap, documented rather
  than routed around.
- **Research qualification**: `not_qualified` → `qualified_with_declared_boundaries`.
  Data readiness is real (#435 closed, `normal_research_authorized=true`),
  B0/B1 artifacts are real, a real round-one study and a real round-two
  model review both landed. PIT/provider-lineage remains a recorded owner
  policy waiver, not empirical proof — declared, not hidden.

## What this still does not claim

- That a formal B0 governance sign-off was declared by an owner in this
  rollup (the constituent artifacts are real and owner-approved
  individually; no single explicit "B0 is frozen" declaration was made
  here), or that every one of A0-X01's twelve named subprobes was
  individually re-derived beyond the shape trace and volume-boundary
  operands the replay covers.
- That the volume-contraction result generalizes beyond this exact a0-r2
  rule specification, or that it is statistically significant (the formal
  DSR layer is not wired end to end).
- That G-427-SANDBOX (real concurrency/sandbox proof) or G-431-NATIVE
  (native GitHub parent/sub-issue edges) are resolved — both remain open,
  unchanged from #443.

## Sign-off

`qualified_with_declared_boundaries` — a genuine, positive shift from
#443's `partial`, with every remaining boundary named rather than smoothed
over. See `docs/research/a0/a0_acceptance_evidence_index_r2.json` for the
full machine-readable record.
