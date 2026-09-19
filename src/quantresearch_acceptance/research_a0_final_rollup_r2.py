"""R2 correction of the A0 final acceptance rollup (#443 / research_a0_final_rollup.py).

Not a rewrite. #443's rollup at :data:`research_a0_final_rollup.BASELINE_COMMIT`
is left untouched as an accurate historical record of that baseline -- it was
correct when it was published. This module publishes a second, later,
equally checkable snapshot after real work landed that changes three of its
conclusions:

1. **A0-E01, A0-E02 and A0-E03 all moved from unproven to genuinely executed**,
   with real evidence: a real six-window V0/V1 backtest against live
   MarketHub data (williamxhero/Quant-Research#469, #470), a real
   owner-authorized model round through yosef-server's CPA proxy, and a real
   isolated-wheel installed-environment run. Each is checked here by a real
   test in :mod:`_a0_r2_real_evidence_test`, not asserted.

2. **#443's own G-438-STRATEGY finding was a false negative.** It searched
   ``quant-runtime/src``, ``apex-research/src`` and ``strategy-workspace/src``
   for a "crossback" implementation and correctly found nothing -- because the
   real implementation lives at
   ``strategy-workspace/strategies/equity/a0-ema-crossback/``, a sibling of
   ``src/``, not under it. The rule file, parameters, variants, oracle
   fixtures and reference strategy were all already real and owner-approved
   (2026-09-14) at #443's own baseline; the rollup's search path missed them.
   This module names that correction explicitly rather than quietly using the
   corrected facts.

3. **A0-X01 and A0-X02 also moved to executed/passed**, once the T04
   independent oracle (which had only ever been statically reviewed, per its
   own ``review_record.json``) was actually run against the real, current
   strategy for the first time (williamxhero/Quant-Research#471). The
   oracle's own exact volume-boundary operands and append sequence were
   replayed verbatim, not self-chosen values.

Standard library only. No dependency, no client, no service, no product
logic -- the real work already happened elsewhere and left real files; this
module only reads and reports.
"""

from __future__ import annotations

from dataclasses import replace

from . import research_a0_final_rollup as _r1
from .research_a0_final_rollup import GapItem, ScenarioRecord

A0_ROLLUP_R2_SCHEMA = "quantresearch.research.a0_final_rollup_r2/v1"
# This repo only: apex-research/strategy-workspace commits are cited as text,
# not CommitRef, since only this repo's history is git-cat-file-checkable here.
R2_BASELINE_COMMIT = "49ee869"
SUPERSEDES = _r1.BASELINE_COMMIT

_EV = "_a0_r2_real_evidence_test"

G438_CORRECTION_NOTE = (
    "#443's G-438-STRATEGY gap searched quant-runtime/src, apex-research/src and "
    "strategy-workspace/src and correctly found nothing there. The real implementation "
    "lives at strategy-workspace/strategies/equity/a0-ema-crossback/ -- a sibling of "
    "src/, not a subdirectory of it. It existed at #443's own baseline (commit "
    "c4c401b, 2026-09-13, before #443 was even written) with a real Nautilus adapter, "
    "a real state-machine core and passing domain tests. #443's finding was a false "
    "negative caused by an incomplete search path, not a missing artifact. Re-verified "
    "directly in this module's evidence test."
)

# ---------------------------------------------------------------------------
# Scenario corrections.
# ---------------------------------------------------------------------------

_E01_R2 = ScenarioRecord(
    scenario_id="A0-E01",
    must_assert=_r1.scenario("A0-E01").must_assert,
    required_evidence_types=("connected_formal",),
    satisfied_evidence_types=("connected_formal",),
    owner_issue="#441 (real study: williamxhero/Quant-Research#469, #470)",
    status="executed",
    evidence_class="proven_in_this_repo",
    evidence=_r1._refs(
        _EV,
        "test_a0_e01_real_round1_study_shows_a_real_v0_v1_divergence",
        "test_a0_e01_volume_filter_diagnostic_was_independently_spot_checked",
    ),
    limitations=(
        "the formal SPEC-013 DeflatedSharpeService statistical layer does not run "
        "end to end yet: NautilusReturnArtifactReader requires a Workspace owner "
        "record of schema quant-research.result.v4, quant_runtime's `run` CLI emits "
        "quant-research.result.v2. Plain descriptive statistics (mean/std/annualized "
        "Sharpe) are reported instead, clearly labelled as a fallback, not the "
        "verified assessment. See T03-METHOD-001 in apex-research's gap list.",
        "PIT/provider lineage remains a recorded owner policy waiver (T03-DATA-001), "
        "not empirical proof; this was never a gate on A0-E01 specifically.",
    ),
    note=(
        "Six real connected quant-runtime formal runs (development/validation/holdout "
        "x V0/V1), read_method=direct_markethub in all six, executed 2026-09-18 "
        "against live MarketHub data using the strategy-workspace package fixed in "
        "#469/#470. V0 places 70 real round-trip trades across the three windows; V1 "
        "places zero in every window, independently spot-checked by replaying the "
        "real bars directly through the state machine outside the Nautilus engine -- "
        "every real pivot-confirmation event carried volume above its trailing "
        "baseline, never below the required 75% contraction threshold. This "
        "supersedes #441's unverifiable receipt (see E01_DRIFT_NOTE on the R1 "
        "rollup) with real, in-repo-checkable evidence."
    ),
)

_E02_R2 = ScenarioRecord(
    scenario_id="A0-E02",
    must_assert=_r1.scenario("A0-E02").must_assert,
    required_evidence_types=("connected_model",),
    satisfied_evidence_types=("connected_model",),
    owner_issue="#442",
    status="executed",
    evidence_class="proven_in_this_repo",
    evidence=_r1._refs(_EV, "test_a0_e02_real_round2_outcome_is_a_delivered_connected_stop"),
    limitations=(
        "the model's decision was 'stop', not 'continue' or 'add_evidence' -- a "
        "genuine terminal outcome, not a partial one. A future round could still "
        "exercise the continue/add_evidence branches for real; they remain "
        "evidenced only by the offline regression layer (see #442's own tests).",
    ),
    note=(
        "run_a0_round_two executed for real through GovernedRoundTwoEngine with a "
        "real, owner-authorized EngineAuthorization (engine_ref="
        "'yosef-server-cpa/deepseek-v4-1-flash', transport=real_process, no "
        "credential in the record, driver in "
        "src/quantresearch_acceptance/_a0_round2_real_driver.py). The model reviewed "
        "the real A0-E01 finding above, cited only the approved source, requested no "
        "new run/budget/strategy, and proposed 'stop'. delivery_state=delivered, "
        "delivery_layer=real_connected, proves_model_use=True -- the first genuinely "
        "connected A0-E02 evidence this project has produced."
    ),
)

_E03_R2 = ScenarioRecord(
    scenario_id="A0-E03",
    must_assert=_r1.scenario("A0-E03").must_assert,
    required_evidence_types=("installed_cross_repo",),
    satisfied_evidence_types=("installed_cross_repo",),
    owner_issue="#428/#429",
    status="executed",
    evidence_class="proven_in_this_repo",
    evidence=_r1._refs(_EV, "test_a0_e03_real_installed_environment_run_passed_all_twelve"),
    limitations=(
        "the wheels installed for this run are ad-hoc local build artifacts for "
        "verification, not a published/tagged release -- see the evidence file's own "
        "scope_boundary.",
        "the source-checkout suite's 2 pre-existing failures "
        "(_a0_installed_test.py::test_a0_installed_tracer_is_not_source_preferred, "
        "_installed_test.py::test_installed_wheel_has_no_source_checkout_precedence) "
        "are unchanged and still correctly fail from this checkout -- that fact and "
        "this scenario's pass are not in tension: one proves the source checkout "
        "still lacks wheels (true), the other proves a real installed environment "
        "was built and exercised elsewhere (also true).",
    ),
    note=(
        "Real wheels built for all five owner packages and installed into a fresh, "
        "isolated venv with no source checkout on sys.path, run from a directory "
        "containing none of the five repositories. _spec027_installed_test.py (the "
        "five-wheel golden tracer that could not even collect from source) and both "
        "source-precedence guards passed for real: 12/12, 0 failed. The first time "
        "this project has executed A0-E03's required condition rather than only "
        "documented its absence."
    ),
)

_X01_R2 = replace(
    _r1.scenario("A0-X01"),
    status="executed",
    satisfied_evidence_types=("independent_golden",),
    evidence_class="proven_in_this_repo",
    evidence=_r1._refs(
        _EV, "test_a0_x01_x02_independent_oracle_replay_passed_for_real"
    ),
    limitations=(
        G438_CORRECTION_NOTE,
        "the replay covers the T04 oracle's FX-X01 input_sequence and its explicit "
        "fixture_operands volume-boundary values (74/75/76 against a five-prior-bar "
        "mean of 100); it does not separately re-derive every one of X01's twelve "
        "named subprobes as an individually cited assertion.",
    ),
    note=(
        "Corrected from #443's baseline and from this rollup's own earlier R2 draft: "
        "the T04 oracle (fixture_inputs.json / expected_traces.json) was actually "
        "executed against the real, current core.py for the first time "
        "(williamxhero/Quant-Research#471), not just statically reviewed. The "
        "oracle's own volume-boundary values (74/75/76) are exactly the boundary "
        "#470's off-by-one fix corrects; the real replay is the independent "
        "confirmation that the fix is right, not an internal self-check."
    ),
)

_X02_R2 = replace(
    _r1.scenario("A0-X02"),
    status="executed",
    satisfied_evidence_types=("trace_prefix_property",),
    evidence_class="proven_in_this_repo",
    evidence=_r1._refs(
        _EV, "test_a0_x01_x02_independent_oracle_replay_passed_for_real"
    ),
    limitations=(
        G438_CORRECTION_NOTE,
        "the replay uses the oracle's own append_sequence (close=102 then "
        "close=98) verbatim rather than an arbitrary future bar.",
    ),
    note=(
        "Corrected: the T04 oracle's FX-X02 append_sequence was replayed for real. "
        "The original entry decision's trace and record are unchanged after the "
        "future bars are appended; a genuine new, later-dated exit decision is "
        "correctly produced (close 98 < slow EMA), confirmed as a legitimate new "
        "event rather than a backfill of the confirmed past -- the actual prefix "
        "property this scenario requires."
    ),
)

_R2_OVERRIDES: dict[str, ScenarioRecord] = {
    "A0-E01": _E01_R2,
    "A0-E02": _E02_R2,
    "A0-E03": _E03_R2,
    "A0-X01": _X01_R2,
    "A0-X02": _X02_R2,
}

A0_SCENARIOS_R2: tuple[ScenarioRecord, ...] = tuple(
    _R2_OVERRIDES.get(record.scenario_id, record) for record in _r1.A0_SCENARIOS
)

# ---------------------------------------------------------------------------
# Gap corrections.
# ---------------------------------------------------------------------------

_RESOLVED_R2_GAP_IDS = frozenset(
    {
        "G-434-RULES",
        "G-437-ORACLE",
        "G-438-STRATEGY",
        "G-441-ASSETS",
        "G-442-ENGINE",
        "G-429-WHEELS",
    }
)

# G-438-REPLAY-R2 (the narrower "artifacts are real, replay unexecuted" gap this
# rollup drafted first) is itself now resolved: williamxhero/Quant-Research#471
# ran the real replay for both A0-X01 and A0-X02. G-434-RULES/G-437-ORACLE/the
# original G-438-STRATEGY were already resolved (see G438_CORRECTION_NOTE), so
# none of the three "rule/oracle/strategy" gaps carry forward into GAPS_R2.

GAPS_R2: tuple[GapItem, ...] = tuple(
    gap for gap in _r1.GAPS if gap.gap_id not in _RESOLVED_R2_GAP_IDS
)

# ---------------------------------------------------------------------------
# Derived views (same rules as #443's rollup, over the R2 tuples).
# ---------------------------------------------------------------------------


def passed_scenario_ids_r2() -> tuple[str, ...]:
    return tuple(record.scenario_id for record in A0_SCENARIOS_R2 if record.passed)


def scenario_r2(scenario_id: str) -> ScenarioRecord:
    for record in A0_SCENARIOS_R2:
        if record.scenario_id == scenario_id:
            return record
    raise KeyError(scenario_id)


def type_mismatched_scenario_ids_r2() -> tuple[str, ...]:
    return tuple(
        record.scenario_id
        for record in A0_SCENARIOS_R2
        if record.status == "executed" and not record.evidence_type_matches
    )


# ---------------------------------------------------------------------------
# The four reports, corrected.
# ---------------------------------------------------------------------------


def engineering_report_r2() -> dict[str, object]:
    base = _r1.engineering_report()
    base["scenarios_passed"] = len(passed_scenario_ids_r2())
    base["scenarios_total"] = len(A0_SCENARIOS_R2)
    base["summary"] = (
        base["summary"]
        + " R2: A0-E01/E02/E03 now have real, checkable, connected evidence "
        "(see research_a0_final_rollup_r2)."
    )
    return base


def rule_implementation_report_r2() -> dict[str, object]:
    return {
        "conclusion": "concluded_pass",
        "summary": (
            "Corrected from #443's 'cannot_be_concluded': A0-B0-RULES (#434), "
            "A0-FIXTURES-ORACLE (#437) and A0-REFERENCE-STRATEGY (#438) are all real, "
            "committed, owner-approved artifacts (rule_binding a0-r2, owner approval "
            "2026-09-14). #443's claim that no reference strategy exists in any "
            "checked-out repository was a false negative caused by searching only "
            "*/src/ paths; the real implementation lives at "
            "strategy-workspace/strategies/equity/a0-ema-crossback/. The "
            "T04-independent oracle (fixture_inputs.json / expected_traces.json) was "
            "then actually executed against that real, current strategy for the "
            "first time (williamxhero/Quant-Research#471) -- A0-X01's shape trace "
            "and exact volume-boundary operands (74/75/76) and A0-X02's "
            "prefix-property append sequence both matched the independently-authored "
            "oracle. Rule implementation correctness can now be concluded: pass."
        ),
        "b0_frozen": "artifacts_real_formal_b0_sign_off_not_separately_declared",
        "b1_frozen": True,
        "scenarios_without_any_evidence": (),
        "scenarios_pending_independent_replay": (),
        "blocking_gaps": (),
        "correction": G438_CORRECTION_NOTE,
        "not_claimed": (
            "that a formal B0 governance sign-off was declared by an owner in this rollup "
            "(the constituent artifacts are real and owner-approved individually; no single "
            "explicit 'B0 is frozen' declaration was made here)",
            "that every one of A0-X01's twelve named subprobes was individually re-derived "
            "as its own cited assertion, beyond the shape trace and volume-boundary operands "
            "the replay covers",
        ),
    }


def research_findings_report_r2() -> dict[str, object]:
    return {
        "conclusion": "real_finding_published",
        "a0_question": _r1.research_findings_report()["a0_question"],
        "answer": (
            "As specified in a0-r2 (volume contraction checked at the pivot-"
            "confirmation bar, 75% of the trailing 5-bar mean), the filter does not "
            "merely fail to add value -- it eliminates the entire strategy. V1 placed "
            "zero trades across the full declared 2015-2026 universe and date range, "
            "in all three windows. V0 alone placed 70 real round-trip trades with a "
            "near-zero annualized Sharpe (0.012 / -0.030 / -0.054 across the three "
            "windows) and a 28.6% win rate."
        ),
        "v1_better_than_v0": "v1_is_non_viable_zero_trades_under_this_exact_specification",
        "profitability_claimed": False,
        "statistical_significance_claimed": False,
        "causal_claim": False,
        "formal_statistical_layer": (
            "SPEC-013's DeflatedSharpeService was attempted for real against the "
            "real, artifact-verified portfolio_returns series (1813 real "
            "observations for V0's development window alone) and found a genuine "
            "result-schema v2/v4 gap between quant_runtime and apex-research, "
            "documented rather than routed around (see A0-E01's limitations)."
        ),
        "caveat": (
            "This is a real, complete result for the exact a0-r2 rule specification, "
            "not a general claim about volume-contraction filters. It may reflect a "
            "structural mismatch between checking contraction at a breakout bar "
            "(where volume expansion is the more common real pattern, confirmed by "
            "direct inspection of every real pivot-confirmation event) and an "
            "earlier-bar pre-breakout confirmation use -- reinterpreting the rule "
            "would be a new, separately-approved a0-r3 revision, not something this "
            "rollup is authorized to do."
        ),
        "engineering_success_is_not_research_success": _r1.research_findings_report()[
            "engineering_success_is_not_research_success"
        ],
        "not_claimed": (
            "that a general volume-contraction filter has no value in any strategy",
            "that this result is statistically significant (the formal DSR layer "
            "does not run end to end yet; see formal_statistical_layer above)",
        ),
    }


def research_qualification_report_r2() -> dict[str, object]:
    return {
        "conclusion": "qualified_with_declared_boundaries",
        "summary": (
            "Corrected from #443's 'not_qualified': #435's data-readiness gate is "
            "resolved (normal_research_authorized=true, T03-EXEC-001 resolved with "
            "live readback), the rule/oracle/strategy baseline is real (see "
            "rule_implementation_report_r2), a real round-one study ran and produced "
            "a finding, and a real round-two model review was delivered. PIT/"
            "provider-lineage remains a recorded owner policy waiver rather than "
            "empirical proof, and the formal SPEC-013 statistical layer is not yet "
            "wired end to end -- both are declared boundaries, not silent gaps."
        ),
        "data_readiness": "ready",
        "data_readiness_detail": (
            "#435 CLOSED 2026-09-18: T03-EXEC-001 resolved with a live "
            "health->resolve->manifest->preflight readback; "
            "a0_data_readiness.json.normal_research_authorized=true. T03-DATA-001 "
            "(PIT/provider lineage) remains waived_by_policy, an explicit owner "
            "decision, not an empirical result; T03-DATA-003 (futures 1m gaps) "
            "remains an accepted baseline, unchanged."
        ),
        "b0_b1_frozen": True,
        "holdout_consumed": True,
        "holdout_consumed_detail": (
            "the holdout window (2023-01-01..2026-06-30) was run for real as part "
            "of A0-E01's six-window study, using parameters frozen on 2026-09-14, "
            "before any of these runs -- consumed once, at the end, without tuning "
            "on its result, which is the protocol-correct use of a holdout rather "
            "than a violation of it."
        ),
        "lookahead_or_future_information_leak_found": False,
        "lookahead_check_detail": _r1.research_qualification_report()[
            "lookahead_check_detail"
        ],
        "undeclared_profit_or_significance_threshold": False,
        "blocking_gaps": ("G-427-SANDBOX",),
        "not_blocking_this_conclusion": (
            "G-435-PIT (policy-waived, not a qualification gate per the owner's "
            "recorded decision)",
            "G-435-FUTURES (accepted baseline, user decision already recorded)",
            "G-431-NATIVE (native GitHub relationship edges; tracking only)",
        ),
    }


def final_rollup_readback_r2() -> dict[str, object]:
    """The R2 correction as one deterministic public record."""

    return {
        "schema": A0_ROLLUP_R2_SCHEMA,
        "supersedes": SUPERSEDES,
        "baseline": R2_BASELINE_COMMIT,
        "corrections_summary": (
            "A0-E01, A0-E02, A0-E03, A0-X01 and A0-X02 all moved from unproven to "
            "executed/passed with real evidence (24/27, up from 19/27). #443's own "
            "G-438-STRATEGY false negative is named and corrected."
        ),
        "scenarios": [record.as_dict() for record in A0_SCENARIOS_R2],
        "gaps": [gap.as_dict() for gap in GAPS_R2],
        "passed_scenario_ids": list(passed_scenario_ids_r2()),
        "type_mismatched_scenario_ids": list(type_mismatched_scenario_ids_r2()),
        "engineering_report": engineering_report_r2(),
        "rule_implementation_report": rule_implementation_report_r2(),
        "research_findings_report": research_findings_report_r2(),
        "research_qualification_report": research_qualification_report_r2(),
        "sign_off": "qualified_with_declared_boundaries",
        "sign_off_reason": (
            "24 of 27 scenarios pass with evidence of the required type (up from "
            "19/27 at #443's baseline). A0-E01, A0-E02, A0-E03, A0-X01 and A0-X02 -- "
            "the five scenarios most damaging to launder or most consequential to "
            "leave undone -- all now carry real, connected, in-repo-checkable "
            "evidence rather than a claim. Only A0-L03 (cited owner evidence, by "
            "design) and A0-G01/A0-V01 (executed but type-mismatched, unchanged from "
            "#443) remain unpassed. Research: a real finding is published (the "
            "volume-contraction filter as specified eliminates the strategy). "
            "Research qualification: qualified, with the PIT/lineage policy waiver "
            "and the pending formal-statistics-layer "
            "compatibility gap both declared rather than hidden."
        ),
    }
