# #443 A0-T09: the final rollup — recovery, generic regression, and the dual engineering/research sign-off

This is the capstone of the #444 single-line queue. It is **not a third test
implementation**. It builds one checkable index over work that eight other
tickets already did, verifies every claim in it against the current baseline,
and reports engineering, rule implementation, research findings and research
qualification as four separate conclusions that do not agree with each other.

Baseline: `db41a44f3b665472b7ad1dc7529a49734600330e` (`main`, clean).

---

## Headline

**Engineering: pass with declared gaps. Research: nothing was learned.**

19 of #431's 27 A0 scenarios pass with evidence of the type #431 requires for
them. The remaining 8 are reported as they actually are — one owner-reported
but unverifiable, two `not_run`, two `pending`, one cited-not-measured, and two
executed but missing one required evidence type each.

The A0 research question — *does adding a volume-contraction filter to a
ruleised first EMA Crossback provide incremental value?* — is **unanswered**,
in either direction.

And the single most important thing this rollup found:

> **The "#441 published no round-one assets" finding that #442, #404, #408 and
> #429 all carry is stale.** #441 closed on 2026-09-14 with a delivery receipt
> asserting a real connected V0/V1 round. Those four evidence documents were
> committed on 2026-09-17, three days later, and each repeated the absence.
> The narrow form they also stated ("#441 landed no commit in *this*
> repository") is correct; the broad form is not.

This is exactly the drift #443's step 1 exists to catch, and correcting it is
the capstone's job. The correction does **not** move A0-E01 to a pass — see
below. It moves it to a third, more honest status.

---

## 1. The A0-E01 drift, in full

### What #441 claims

From its closure receipt (`gh issue view 441 --comments`, verified at this
baseline):

| Field | Value |
| --- | --- |
| MarketHub deployment | `deploy_20260914_151903` |
| Dataset | `mhd-v1-6adc2341cda0e588835d3b2db6325ab68c42c8e5d2299012008211c7a561311b` |
| Coverage | `2015-01-05..2026-09-14`, `day_rows=6862`, `gap_rows=0` |
| Formal snapshot | `sha256:023bc95d8b3096669ce793cb8cb5c73095efb629a4e11df38a0144e9c1560716` |
| V0 run | `run_0b9549440d7dca28f0c0d573c293444a` |
| V1 run | `run_fdb00d3a48eff4a4b07d7e4d9ea44db4` |
| Engine | Nautilus `1.231.0`, both `completed`, `direct_markethub` |
| Orders / fills / positions | **0 / 0 / 0**, both runs |

### What is verifiable here: nothing

Re-checked at this baseline:

```
runtime/q441/evidence-index.md    -> absent
runtime/q441/a0-study-report.md   -> absent
docs/reports/q441-研究过程经验总结-2026-09-15.md -> absent
grep -rl "0b9549440d7dca28f0c0d573c293444a"  -> no match anywhere under D:/WILL/STOCK
git log --all --grep='#441'                  -> no commit in this repository
```

The only q441 traces on disk are in `.scratch/issue-444-single-line/` (a copy
of the issue comment text, git-ignored) and a `quant-runtime` worktree branch
`codex/unblock-q441-capability-contract`. Neither is the claimed evidence.

### So the status is neither `not_run` nor `executed`

`not_run` would ignore a real owner receipt. `executed` would claim something
this repository cannot check. This rollup therefore publishes a third status,
`owner_reported_unverifiable`, and **excludes it from the passed list either
way**. `test_e01_is_owner_reported_and_never_counted_as_executed_or_not_run`
and `test_the_e01_receipt_artifacts_are_absent_from_this_checkout` pin both
halves; the second fails if anyone later publishes the assets here, forcing the
status to be revisited rather than left stale.

### And even at face value, it asserts no finding

The receipt itself says: `comparison_present=false`, zero orders, zero fills
and zero positions in **both** V0 and V1, conclusion `inconclusive`, Apex
`accept` meaning only that a `run_count=2` count gate passed, and PIT/provider
lineage *not evaluated*.

Two runs that place no orders cannot separate a component's contribution from
its absence. Whatever else is true, no research finding follows from this.

---

## 2. The 27-scenario matrix

`must_assert` is quoted verbatim from #431's "Acceptance scenario catalogue
v1". The module restates these in English (every module in this package is
English-only); the verbatim text lives here so the restatement is always
checkable against the original.

Legend — **status**: `executed` (really run here), `cited` (owner-measured
elsewhere, not re-measured), `owner-reported` (asserted by an owner receipt,
unverifiable here), `not_run`, `pending`. **Type**: does the evidence that
exists match the evidence type #431 requires? **Pass** requires *both*
`executed` and a type match.

| # | Scenario | 必须断言的行为 | 默认证据类型 | Status | Type | Pass |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | A0-G01 | V0 改名/说明/来源封装不改变 Genome，原始出处和事件仍保留 | 公共合同、独立 golden | executed | ✗ | — |
| 2 | A0-G02 | V0->V1 只变缩量组件，身份改变，diff 准确列出变更/已验证未变范围 | 公共合同 | executed | ✓ | **✓** |
| 3 | A0-G03 | 未知类型/版本/歧义拒绝；无权/不兼容比较为 incomparable，不泄漏 | 正负矩阵 | executed | ✓ | **✓** |
| 4 | A0-G04 | Candidate/Genome/Package/request/event 分离，同内容稳定且不形成 hash 环 | 公共谱系 | executed | ✓ | **✓** |
| 5 | A0-X01 | 首次/再次回踩、阈值边界、无数据、失效/重置/冲突及订单轨迹符合独立预期 | 合成人工样例、独立 oracle | **pending** | ✗ | — |
| 6 | A0-X02 | 追加未来数据不改写过去已确认事件；发生/确认/下单时间分离 | 前缀性质与轨迹 | **pending** | ✗ | — |
| 7 | A0-L01 | 同动作重试幂等，同 key 不同输入拒绝，重提不能清除 tombstone | 公共状态机 | executed | ✓ | **✓** |
| 8 | A0-L02 | 默认拒绝/当前授权/历史重交付检查正确，旧权限不恢复访问 | 权限正负样例 | executed | ✓ | **✓** |
| 9 | A0-L03 | 同身份竞争/崩溃无半发布；保留 #419 本地 256 KiB p95≤250ms 单独实测 | 实际并发/性能 | **cited** | ✓ | — |
| 10 | A0-V01 | 门序短路，prepare 不等于 export，验证用途不能授权正式研究 | 门轨迹/真实沙箱 | executed | ✗ | — |
| 11 | A0-V02 | 精确 Package/验证绑定改变即拒绝；匹配有效证据复用不重复沙箱，撤销仍阻断 | 制品篡改、复用与发布证据 | executed | ✓ | **✓** |
| 12 | A0-M01 | Finding 有范围/证据类型/缺口；数据阻塞不等于策略无效 | 公共记录 | executed | ✓ | **✓** |
| 13 | A0-M02 | 同范围支持/反证保留，不同条件不强称冲突，单组件差异不声称因果 | 可比关系/简报 | executed | ✓ | **✓** |
| 14 | A0-M03 | 同 run 多摘要不膨胀独立性，跨 Campaign 不抹掉选择/检验家族 | 源谱系与选择历史 | executed | ✓ | **✓** |
| 15 | A0-P01 | 直接/派生保护在任何无权消费前阻断，理由/计数/日志不泄漏 | 人工保护记录 | executed | ✓ | **✓** |
| 16 | A0-P02 | Context 与最终 envelope/工具输入区别可追踪，uncertain 不变 unseen，不盲重发 | 交付/回执/中断轨迹 | executed | ✓ | **✓** |
| 17 | A0-C01 | 第二轮简报保留基线/反证/缺口/资产/建议前提和不能声称，字段有来源 | 冻结简报 | executed | ✓ | **✓** |
| 18 | A0-C02 | 必需闭包缺失拒绝，可选范围按预声明限界；不裁掉必需反证/故障伪空 | 分页/裁剪/覆盖矩阵 | executed | ✓ | **✓** |
| 19 | A0-R01 | 真正研究重复在新引擎 Context/付费预算/调用前停止；请求重试对账 | 调用/预算计数 | executed | ✓ | **✓** |
| 20 | A0-R02 | 同执行新统计协议可 attach，新样本合法复验不被 Genome 去重拦，修复 blocker 按新条件处理 | 三分支公开动作 | executed | ✓ | **✓** |
| 21 | A0-H01 | 纠正影响当前简报、不改旧知识快照；时效由原 owner 决定 | 双时间视图 | executed | ✓ | **✓** |
| 22 | A0-H02 | 清投影后按旧事实重建、当前权限仍检查，零新回测/LLM/预算 | 真实删除/恢复 | executed | ✓ | **✓** |
| 23 | **A0-E01** | 声明真实数据上的 V0/V1 正常研究贯通，结果方向不预设 | connected formal evidence | **owner-reported** | ✗ | — |
| 24 | **A0-E02** | 第二轮真实使用第一轮资产，实际模型请求/响应/Context/Exposure/决定相连 | 连通模型证据 | **not_run** | ✗ | — |
| 25 | **A0-E03** | installed/no-source 正负路径与双重放、报告只读、完整证据可核验 | 跨仓安装环境 | **not_run** | ✗ | — |
| 26 | A0-Q01 | 旧 selector/scope/fixed diff/新批次正确，不把 skip/blocked/not_run 当 pass | 验收器选择/执行记录 | executed | ✓ | **✓** |
| 27 | A0-Q02 | 独立预期能抓故意注入错误；复用已有非CPA小例检查通用性，无核心特判 | mutation/通用回归 | executed | ✓ | **✓** |

**19 pass / 27.** Full per-scenario evidence references, limitations and notes
are in `docs/research/a0/a0_acceptance_evidence_index.json`.

### The eight that do not pass, and exactly why

| Scenario | Why not | Gap |
| --- | --- | --- |
| A0-G01 | Contract invariance proven; the **独立 golden** half is a self-built #437-*shaped* fixture, not an owner-frozen oracle | G-437-ORACLE |
| A0-X01 | **No evidence at all.** No EMA-crossback reference strategy exists in `quant-runtime/src`, `apex-research/src` or `strategy-workspace/src` at this baseline | G-438-STRATEGY, G-437-ORACLE |
| A0-X02 | Same root cause: no strategy event trace to assert the prefix property over. #401's record-level no-hindsight proof is cited and explicitly **not** offered as a substitute | G-438-STRATEGY |
| A0-L03 | #419's concurrency/crash and 256 KiB p95 ≤ 250 ms are real but are the **owner's** measurement inside StrategyWorkspace. Cited, never re-measured. Deliberately excluded from the pass list | — (cited, by design) |
| A0-V01 | Gate order and prepare≠export proven against the contract; the **真实沙箱** half never ran | G-427-SANDBOX |
| A0-E01 | Owner-reported, unverifiable here, and inconclusive even as reported | G-441-ASSETS, G-435-PIT |
| A0-E02 | No owner-authorized `ResearchEnginePort` configuration exists | G-442-ENGINE |
| A0-E03 | No owner wheel is installed | G-429-WHEELS |

`test_every_unpassed_scenario_is_reachable_from_a_gap_or_is_cited` enforces
that every non-pass has somewhere to go next. It caught a real hole while being
written — A0-V01 had no gap entry — which is why G-427-SANDBOX exists.

---

## 3. E01 / E02 / E03 re-probed, not inherited

The ticket requires evidence **of the right type**, and forbids substituting a
fixture, a stub or a block. All three were re-probed at this baseline rather
than carried over from #442/#429.

| Probe | Result |
| --- | --- |
| `import apex_research` | `ModuleNotFoundError` |
| `import strategy_workspace` | `ModuleNotFoundError` |
| `import quant_runtime` | `ModuleNotFoundError` |
| `import strategy_reporting` | `ModuleNotFoundError` |
| `.env` / research-engine config in this repo | none |
| `class ResearchEnginePort` | still an unbound `Protocol` at `apex-research/src/apex_research/research_engine.py:642` |

So **A0-E02 is `not_run`** and **A0-E03 is `not_run`**, confirmed, not assumed.
`test_the_engine_and_wheel_absences_are_still_true_at_this_baseline` re-asserts
this on every run.

The two pre-existing suite failures are the honest signal of E03 and were not
silenced:

- `_a0_installed_test.py::test_a0_installed_tracer_is_not_source_preferred`
- `_installed_test.py::test_installed_wheel_has_no_source_checkout_precedence`

**A correctly expected block satisfies only its own negative case.** None of
the `not_run` reporting tests is offered as evidence that its criterion is met.

---

## 4. U1–U6

All six executed. Counters carried forward from #399/#401/#404/#408 by
citation, per the ticket's instruction not to re-run precisely-covered work.

| Scenario | A0 mapping | Status | Owner of the executed evidence |
| --- | --- | --- | --- |
| U1 equivalent failure, renamed | A0-R01, A0-M01 | executed | #399 |
| U2 repaired data blocker | A0-R02, A0-M01 | executed | #399 |
| U3 legitimate new-sample revalidation | A0-R02 | executed | #399 |
| U4 single-component comparison | A0-G02, A0-M02 | executed | #404 |
| U5 source correction | A0-H01 | executed | #401 |
| U6 rebuild after deleting the projection | A0-H02 | executed | #404 (contract) + #408 (real execution) |

### Counts — call / budget / reuse / wrongly-blocked

| Scenario | legitimate requests | wrongly blocked | runs reused | external calls |
| --- | --- | --- | --- | --- |
| U1 | 0 | **0** | 0 | 0 |
| U2 | 1 | **0** | 0 | 4 |
| U3 | 1 | **0** | 0 | 4 |
| U6 | 1 | **0** | 0 | **0** |

- **Wrongly-blocked legitimate research: 0**, denominator **3** (U2, U3, U6).
- **Missing-required-counter-evidence: 0.** The branch that *should* miss one
  is asserted to block, not to ship.
- **Duplicated already-confirmed side effects: 0.** #442's five R01/R02
  branches and #408's duplicate-receipt test each assert an unchanged readback.
- **Provider-facing calls: 0 in every branch**, because nobody authorized a
  provider.

No efficiency, yield, hit-rate or savings figure is reported anywhere. The one
"saving" the system claims — the duplicate branch reaching `(0,0,0,0)` — is
measured against the same fixture's non-duplicate branch reaching `(1,1,1,1)`
in the same test, which is a real executed baseline. Safety, eligibility and
budget rules are identical across every compared branch.

---

## 5. Step 4 — H02 verified: zero new backtest, LLM call or budget

Re-verified rather than restated:

- `MTX::test_u6_rebuild_after_deletion_costs_no_run_llm_call_or_budget` runs a
  real round `(1,1,1,1)`, deletes the objects, rebuilds, and a fresh recording
  engine ends at `(0,0,0,0)` with an empty trace.
- Structurally, not just observationally: `reconstruct_*` accept `{"record"}`
  and nothing else, and `recover_end_to_end`'s signature is exactly
  `{root, visibility_request}`. **The rebuild seam has no engine to spend
  through.**
- The old Context keeps its as-of knowledge and policy
  (`CUR::test_the_old_context_keeps_its_identity_and_policy_after_a_correction`);
  the new brief reflects the new correction
  (`CUR::test_a0_h01_a_correction_updates_the_current_brief_without_touching_the_old_one`).
- A limited payload yields **only** a declared limited replay coverage
  (`REC::test_ac4_a_digest_without_a_body_replays_only_as_limited`:
  `reconstruction == "limited"`, `payload_present is False`,
  `model_invocations == 0`). No model is re-invoked to manufacture a historical
  answer.

## Step 5 — Q02 verified: mutations are caught, and the core has no special case

- `SGF::test_a0_q02_an_independent_oracle_catches_identity_time_and_binding_mutations`
  detects all three declared mutation classes by recomputation.
- `SGF::test_a0_q02_no_production_module_branches_on_a_strategy_name` scans
  every production module's AST string constants against twelve strategy names
  — **zero offenders**. The existing non-CPA generic regression therefore
  exercises the same path any strategy would.
- `MTX::test_no_production_module_has_an_execution_seam_for_injected_text`:
  no `eval`/`exec`/`compile`/`__import__`, no process-spawning attribute call,
  and no `subprocess`/`os`/`socket`/`urllib`/`pickle` import across the
  research seam.

Per the ticket, **no new "Strategy B" research project was built** and the
existing regression was reused and cited, not rebuilt.

---

## 6. The four reports, kept separate

#431 requires engineering, rule implementation, research findings and research
qualification to be four independent conclusions. They are, and they disagree —
which is the point. `test_the_four_reports_are_separate_and_reach_different_conclusions`
pins all four.

### 6.1 Engineering acceptance — `pass_with_declared_gaps`

The acceptance seam was built correctly.

- Ten standard-library modules compose into a public contract with **no
  production dependency** (`[project]` declares no `dependencies` key at all),
  no Pydantic/BaseModel, no NetworkX/ORM, no OPA/MLflow/Optuna/LangGraph, no
  service and no second fact authority.
- Every claimed test resolves; every claimed commit SHA exists *and* carries
  the claimed subject; every claimed evidence document exists.
- Each ticket in the queue confirmed red/green for its own invariants, and this
  one does too (§9).
- 19/27 scenarios pass with type-matched evidence.
- The two known suite failures are declared, explained and not silenced.

**Not claimed:** that the installed/no-source environment was exercised; that
any real sandbox run or concurrency measurement happened here; that a strategy
behaviour oracle exists.

### 6.2 Rule-implementation correctness — `cannot_be_concluded`

**The A0 rule set was never delivered as an owner artifact.**

| Register row | Ticket | Ticket state | Row status at this baseline |
| --- | --- | --- | --- |
| `A0-B0-RULES` | #434 | **CLOSED** | `pending` |
| `A0-FIXTURES-ORACLE` | #437 | **CLOSED** | `pending` |
| `A0-REFERENCE-STRATEGY` | #438 | **CLOSED** | `pending` |
| `A0-ROUND-1` | #441 | **CLOSED** | `pending` |
| `A0-ROUND-2` | #442 | **CLOSED** | `pending` |
| `A0-B1-DATA-RUN` | #435 | **OPEN** | `pending` |
| `A0-ACCEPTANCE-INTEGRATION` | #439 | CLOSED | `observed; unchanged` |

Re-verified by reading `docs/research/a0/a0_delivery_index.json` at this
baseline. **GitHub `closed` ≠ delivered**: six closed tickets leave their
register row `pending`.

With no frozen rule file, no frozen oracle and no reference strategy,
rule-implementation correctness has nothing to be checked against. Neither B0
nor B1 is frozen. This is why A0-X01 and A0-X02 have **no evidence at all** —
the only two scenarios in the catalogue in that position.

### 6.3 Research findings — `no_research_finding`

**Nothing was learned. The A0 question is unanswered.**

- `v1_better_than_v0`: **unknown**.
- No profitability claim. No statistical-significance claim. No causal claim.
- The only round-one execution anyone claims is #441's, which reports
  `comparison_present=false` and zero orders/fills/positions in both variants.
- No second round happened at all: A0-E02 is `not_run`.

> Building correct fail-closed machinery is an **engineering** result. It is
> not a research result. "We proved the system refuses the right things in the
> right order" and "we ran real research and got results" are different claims,
> and only the first is true here.

### 6.4 Research qualification — `not_qualified`

A0 does not currently meet its own declared qualification bar.

- **Data readiness: `blocked`.** #435 is OPEN with
  `data_semantics:point_in_time` and `data_semantics:provider_lineage`
  unevaluated.
- B0/B1 not frozen (§6.2).
- The one claimed run is unverifiable from this repository.
- **No holdout was consumed.** **No undeclared profit or significance
  threshold** exists anywhere.
- **No lookahead / future-information leakage found.** Spot-checked: every
  fixture in this package is synthetic, test-only and lives under pytest's
  `tmp_path`; the no-hindsight properties are asserted *positively* by #401's
  dual-time tests and #404's U6 rebuild-cost test.

---

## 7. The #435 exception — recorded exactly as it happened

#435 (`[A0-T03]` data baseline) is **still OPEN and still blocked**. The queue
proceeded past it because of a real, explicit, user-made decision recorded in
its thread — not because the gap was repaired.

The user's recorded decision, verbatim in substance:

- Accept the currently available futures 1m dataset as the backtest baseline.
- Continue #444 using the data currently available.
- Defer further futures 1m source discovery, gap filling and the
  completeness-policy code change.
- **"The existing DATA_INCOMPLETE / missing_or_unknown_interval findings remain
  factual and are not reclassified as repaired or complete."**
- No new futures rows were imported by this decision.
- **"Do not close #435 as if its data gaps were repaired."**

The gap evidence remains authoritative and is restated here rather than
smoothed over: **225 day-gap rows across 33 dates** and **1,522
night-internal-gap rows across 454 sessions** in the audited futures dataset.

Critically: **that decision unblocked the QUEUE, not the PIT/lineage gate.**
The price-row point-in-time and provider-lineage gaps are a separate, still-open
blocker (G-435-PIT), documented across the #435 thread with read-only probes
that each ruled out a candidate substitute — health checks, dataset versions,
the export manifest, the provider capability catalogue and the financial PIT
endpoint. None of them proves price-row as-of semantics or per-row lineage.

`test_the_markethub_exception_is_recorded_as_accepted_not_repaired` keeps this
description from drifting.

---

## 8. Native relationship state — actually read back

The ticket forbids claiming native-tree/GraphQL verification that was not
performed. **It was performed.** A read-only GraphQL readback ran against every
issue in the A0 tree:

```
gh api graphql -f query='query { repository(owner:"williamxhero", name:"Quant-Research") {
  issue(number: N) { number state parent { number } subIssues(first:20) { nodes { number } } } } }'
```

| Issue | 431 | 432 | 433 | 434 | 435 | 436 | 437 | 438 | 439 | 440 | 441 | 442 | 443 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| native parent | null | null | null | null | null | null | null | null | null | null | null | null | null |
| native subIssues | — | — | — | — | — | — | — | — | — | — | — | — | — |

**Positive control**, so the empty result cannot be mistaken for a broken or
unsupported query:

```
#402 -> subIssues [405, 406, 409, 411]
#405 -> parent 402
```

The mechanism works and is used elsewhere in this repository (see
`runtime/strategy-genome-parent-readback-final.json`). The A0 edges were simply
never created.

| Item | Result |
| --- | --- |
| Readback performed | **yes** |
| Native parents found | **0** of 12 planned in #431's manifest |
| Native sub-issues found | **0** |
| Cycles | **0** — no native edge exists, so no native cycle can exist |
| Old relationships disturbed | **0** |
| Drift vs. issue-body plan | total: the body navigation and the native tree agree on nothing, which is the already-declared state, not new drift |
| Repair performed | **no** — not authorized to this session |
| State | **`pending-native-link`**, now confirmed by measurement rather than carried on trust |

No permission was expanded and no workflow was deployed. This rollup **does not
claim** the planned native edges exist.

---

## 9. Red / green confirmation of the consistency checker

The checker is the only genuinely new code here, so each of its invariants was
broken, observed to fail on the intended test, and restored.

| Mutation | Result |
| --- | --- |
| M1 rename a cited test | `1 failed` — `test_every_named_test_in_the_rollup_actually_exists` |
| M2 corrupt a cited commit SHA | `2 failed` — `…commit_exists_in_this_repository`, `…commit_subject_matches_the_real_commit` |
| M3 wrong commit subject (SHA still valid) | `1 failed` — `…commit_subject_matches_the_real_commit` |
| **M4 launder A0-E02 into a pass** | **`4 failed`** — `…three_e_scenarios_never_appear_in_the_passed_list`, `…e02_and_e03_are_not_run_and_say_why`, `…pass_count_is_nineteen_of_twenty_seven`, `…eight_unpassed_scenarios_each_have_a_declared_reason` |
| M5 claim the native tree was verified (`native_parents_found: 12`) | `1 failed` — `…native_relationship_state_is_pending_and_claims_no_verified_tree` |
| M6 drop a scenario from the catalogue | `5 failed` — including `…all_twenty_seven_scenarios_are_present_in_the_published_order` |
| M7 claim an evidence type the scenario never required | `1 failed` — `…satisfied_types_are_always_a_subset_of_required_types` |

Restored: **`39 passed`**.

M4 is the one that matters: the laundering this ticket would most be tempted
into is structurally impossible without four tests going red.

---

## 10. Deliverables

| Deliverable | Where |
| --- | --- |
| `a0_acceptance_evidence_index` (structured) | `docs/research/a0/a0_acceptance_evidence_index.json` — generated from the module, never hand-edited; `test_the_published_index_file_matches_the_module_exactly` fails if they drift |
| `a0_acceptance_evidence_index` (authoritative source) | `src/quantresearch_acceptance/research_a0_final_rollup.py` — tracked code, since `/docs` is git-ignored apart from force-added files |
| Layered acceptance output | `final_rollup_readback()["passed_/not_run_/pending_/cited_/owner_reported_/type_mismatched_scenario_ids"]` |
| Engineering report | `engineering_report()` + §6.1 |
| Research report | `research_findings_report()` + `research_qualification_report()` + §6.3–6.4 |
| Rule-implementation report | `rule_implementation_report()` + §6.2 |
| Native-relationship record | `NATIVE_RELATIONSHIP_READBACK` + §8 |
| Gap / remediation list | `GAPS` (9 items) + §11 |

Every result is pinned to `BASELINE_COMMIT`, and #431's exact catalogue version
is quoted in §2.

---

## 11. Gap / remediation list

Concrete, owned, and actionable by a human or a future session.

| Gap | Owner | Blocks | Remediation |
| --- | --- | --- | --- |
| **G-435-PIT** | MarketHub owner (yosef-server) | A0-E01 | Publish a price-row as-of/PIT contract and per-row provider lineage for `stock_daily_1d`. Health checks, dataset versions, the export manifest, the provider capability catalogue and the financial PIT endpoint were each probed and none substitutes. Until then `quant_runtime.a0_baseline` live preflight stays `blocked`. |
| **G-435-FUTURES** | user — **decision already made** | — | No action needed for the queue. The futures 1m dataset was explicitly accepted as the backtest baseline and further backfill deferred. The gap evidence stays authoritative; #435 stays open rather than being closed as repaired. |
| **G-442-ENGINE** | Apex Research owner | A0-E02 | Bind an implementation to the `ResearchEnginePort` Protocol and publish an owner-authorized engine reference plus a separate budget approval. `run_a0_round_two` already accepts one through `EngineAuthorization` with no contract change. **Do not** use the developer shell's general-purpose provider keys — they are not an owner authorization and spending was never approved. |
| **G-434-RULES** | #434 owner | A0-X01, A0-G01 | Publish the frozen rule file, parameters, V0/V1 delta and comparison protocol with an exact version and digest; backfill the `A0-B0-RULES` row. |
| **G-437-ORACLE** | #437 owner | A0-X01, A0-X02, A0-G01 | Publish versioned fixture inputs, expected traces and oracle notes with an exact digest. Until then every fixture here is #437-*shaped* and self-built. |
| **G-438-STRATEGY** | #438 owner | A0-X01, A0-X02 | Publish the ordinary reference strategy and its V0/V1 inputs. No `crossback` implementation was found in any checked-out repository. |
| **G-441-ASSETS** | #441 owner | A0-E01, A0-H02 | Publish `runtime/q441/*` and the named run/snapshot identities where a cross-repository consumer can read them; backfill `A0-ROUND-1`. Until then A0-E01 cannot move past `owner_reported_unverifiable` and A0-H02's real-asset half has nothing to delete and recover. |
| **G-427-SANDBOX** | #421/#427 owner | A0-V01 | Run the ordered gates and a prepare-vs-export attempt in a real sandbox and publish the gate trace. |
| **G-429-WHEELS** | release/packaging owner | A0-E03 | Build and install the four owner wheels, then run the two installed tests plus `_spec027_installed_test.py`. Those two failures are the honest signal of this gap and must not be silenced. |

---

## 12. Cited, never re-measured

Per the ticket's step 2, precisely-covered expensive work is reused by citation
rather than re-run:

| Source | What is cited | Why not re-measured |
| --- | --- | --- |
| #419 | concurrency/crash evidence; local 256 KiB p95 ≤ 250 ms | measurable only inside StrategyWorkspace, which this repository does not own and must not modify |
| #421 | independent behavioural conformance | same |
| #422 | Genome→Package export behaviour | same |
| #399/#401/#404 | U1–U5 counters | already executed against the current seam; #408's precedent |
| #408 | real deletion/interruption/restart | referenced by #429 and here, not reimplemented |

`SGF::test_the_owner_measured_evidence_is_cited_and_never_claimed_as_re_measured`
asserts the "NOT re-measured" wording survives in `CITED_OWNER_EVIDENCE`.
A0-L03 is deliberately excluded from the passed list for exactly this reason.

---

## 13. Test evidence

```
python -m pytest src/quantresearch_acceptance -q \
    --ignore=src/quantresearch_acceptance/_spec027_installed_test.py
```

| Run | Result |
| --- | --- |
| before (on `main` at `db41a44`) | `2 failed, 421 passed` |
| after | `2 failed, 460 passed` |

The two failures are identical by name before and after, and are the
pre-existing ones recorded for #394–#429:

- `_a0_installed_test.py::test_a0_installed_tracer_is_not_source_preferred`
- `_installed_test.py::test_installed_wheel_has_no_source_checkout_precedence`

Both require the owner wheels to be installed; they are not.
**+39 tests, zero regressions.**

```
python -m ruff check src/quantresearch_acceptance     # All checks passed!
python -m compileall -q src/quantresearch_acceptance  # clean
```

`_spec027_installed_test.py` is excluded because it imports four absent wheels;
it is a collection error, not a regression, and it was excluded identically
from the before-run.

---

## 14. Scope and owner boundary

Files added by this ticket:

- `src/quantresearch_acceptance/research_a0_final_rollup.py`
- `src/quantresearch_acceptance/_research_a0_final_rollup_test.py`
- `docs/research/a0/a0_acceptance_evidence_index.json`
- `docs/evidence/issue-443-a0-final-rollup.md`

Nothing else. No file under `quant-runtime/`, `apex-research/`,
`strategy-workspace/`, `strategy-reporting/`, `MarketHub/` or `QuoteMux/` was
modified — they were read only. `pyproject.toml` is unchanged. No acceptance
scope, selector, marker or ledger was changed. No product logic was added.

`docs/research/a0/a0_delivery_index.*` was **not modified**, for the same
reasons #442 and #408 gave: its pending rows are owned by "Apex Research /
pending owner", and there is still no exact version to backfill. The new
`a0_acceptance_evidence_index.json` is a *different* artifact, owned by this
ticket, and is the one #443 was asked to deliver.

---

## 15. What this rollup does not claim

- It does **not** claim A0 is signed off. Sign-off is **partial**.
- It does **not** claim A0-E01 happened. It claims an owner says it happened
  and that this repository cannot verify it.
- It does **not** claim A0-E01 did *not* happen either. `not_run` would be as
  inaccurate as `executed`.
- It does **not** claim a real model was invoked, a real wheel was installed, a
  real sandbox ran, or a real concurrency measurement was taken here.
- It does **not** claim the volume-contraction filter adds value — or that it
  does not.
- It does **not** claim #419/#421/#422's measurements as its own.
- It does **not** claim the native relationship tree was established.
- It does **not** report any efficiency, yield, hit-rate or savings figure.
- It does **not** retroactively gate #441, #442, T07 or T08, which are closed
  and did not wait on this ticket — exactly as #431's anti-loop policy requires.
- It does **not** wait on EPIC #431's own closure.

---

## Acceptance conclusion

| #443 criterion | Result |
| --- | --- |
| 1. E01/E02/E03 each have evidence of the right type; fixture/stub/blocked cannot substitute | **Reported honestly, none satisfied.** E01 `owner_reported_unverifiable`, E02 `not_run`, E03 `not_run`. All three have `satisfied_evidence_types == ()` and none can reach the passed list. |
| 2. Every required assertion has baseline-current checkable evidence; an expected-negative pass does not offset a real normal-path absence | **Met.** Every citation resolves against the current baseline; `passed` requires executed **and** type-matched, so a negative case counts only for itself. |
| 3. H01/H02/P01/P02/R01/R02 complete; zero wrongly-allowed access, zero missing required counter-evidence, zero duplicated confirmed side effects | **Met.** All six pass; the three counters are 0 with denominator 3. |
| 4. Independent oracle / mutation / existing non-CPA regression effective; general and performance/behaviour/cross-repo evidence not substituted by toy cases | **Met for mutation and genericity** (§5). **Cross-repo performance/behaviour is cited, not substituted** — A0-L03 is excluded from the pass list rather than counted. |
| 5. Unexecuted honestly `not_run`, environment-blocked stays `blocked`; no undeclared threshold; no lookahead leakage | **Met.** 2 `not_run`, 2 `pending`, 1 `owner_reported`, 1 `cited`; no threshold; no leakage found. |
| 6. Engineering / implementation / research findings / qualification reported separately; full index and native state auditable | **Met.** Four separate conclusions that disagree; index generated and drift-tested; native state measured. |

**Overall A0 sign-off: PARTIAL.**

Engineering acceptance is a pass with nine declared gaps. Rule-implementation
correctness cannot be concluded, because the rules were never frozen as owner
artifacts. Research completion is **not claimed at all**, and research
qualification is **not met**.

The #444 queue built a correct, fail-closed, dependency-free acceptance seam
across thirty-three tickets. It did not perform the research that seam exists
to govern.
