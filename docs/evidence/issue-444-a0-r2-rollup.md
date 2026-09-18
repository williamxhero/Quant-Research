# A0 final acceptance rollup — R2 correction (2026-09-19)

This corrects three things in [#443's rollup](issue-443-a0-final-rollup.md)
(baseline `db41a44`, 2026-09-17). It does not replace that document — #443
was an accurate record of its own baseline. This is a second, later,
equally checkable snapshot, published by
`src/quantresearch_acceptance/research_a0_final_rollup_r2.py` and backed by
real tests in `_a0_r2_real_evidence_test.py` and
`_research_a0_final_rollup_r2_test.py`.

## What changed

**A0-E01, A0-E02 and A0-E03 — the three scenarios most damaging to launder —
all moved from unproven to genuinely executed**, each with real, connected,
in-repo-checkable evidence:

| Scenario | #443 (2026-09-17) | R2 (2026-09-19) | Real evidence |
| --- | --- | --- | --- |
| A0-E01 | `owner_reported_unverifiable` | `executed` / passed | Six real connected `quant-runtime` formal runs (development/validation/holdout × V0/V1) against live MarketHub data. V0 places 70 real round-trip trades; V1 places zero in every window — independently spot-checked by replaying the real bars through the state machine outside the Nautilus engine (every real pivot-confirmation event carried volume *above* its baseline, never below the 75% contraction threshold). |
| A0-E02 | `not_run` | `executed` / passed | A real, owner-authorized `run_a0_round_two` through yosef-server's CPA proxy (deepseek-v4-1-flash). `delivery_state=delivered`, `delivery_layer=real_connected`, `proves_model_use=true`. The model reviewed the real A0-E01 finding and proposed `stop`. |
| A0-E03 | `not_run` | `executed` / passed | Real wheels built for all five owner packages, installed into a fresh isolated venv with no source checkout on `sys.path`. `_spec027_installed_test.py` (previously uncollectable) and both source-precedence guards passed for real: 12/12. |

Pass count: **22 / 27**, up from 19/27.

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

**What this does not mean**: A0-X01 and A0-X02 still do not pass. The
original blocker ("nothing exists to test against") is resolved, but the
specific T04-independent-oracle replay these two scenarios require has not
been run against the real (post-#469/#470-fix) strategy in this rollup.
Manufacturing a pass here without that replay would be exactly the
laundering this rollup family exists to prevent. `G-438-REPLAY-R2` replaces
`G-434-RULES`/`G-437-ORACLE`/`G-438-STRATEGY` with this narrower, real
remaining task.

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
  scenario count (22/27).
- **Rule implementation**: `cannot_be_concluded` → `artifacts_real_replay_pending`.
  The rule/oracle/strategy baseline is real; what remains is the independent
  replay for A0-X01/X02 specifically.
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

- That A0-X01/X02 pass, or that a formal B0 governance sign-off was declared
  by an owner in this rollup.
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
