# v0.4.1 — Retrospective

**Run**: 5-pair crypto portfolio (BTC/ETH/SOL/BNB/AVAX) on 1h base + 4h/1d informative, timerange **2021-01-01 → 2025-12-31**, evaluated across 4 declared timeranges per round (bull_2021 / winter_2022 / recovery_23-25 / full_5y)
**Branch**: `autoresearch/may7-2026` (preserved)
**Run-end commit**: `ebe3254` (round 29, all 3 strategies marked "FINAL")
**Robust-peak (alive)**: `f53740b` (round 26, RegimeAdaptiveBNB robust_sharpe 0.0967)
**Robust-peak (ever)**: `021e120` (round 9, BNBSizedConviction robust_sharpe 0.0980, killed r22)
**Total**: 30 rounds — 98 events — 12 creates, 41 evolves, 1 fork, **9 kills (all explicit)**, 35 stables

---

## Headline — first regime-robust portfolio, but Pareto-locked early

v0.4.1 produced **the first multi-strategy lineup where every strategy is positive across all four declared timeranges simultaneously**. All 3 FINAL strategies clear robust_sharpe > 0:

| Strategy | robust_sharpe | binding_regime | full_5y profit | full_5y DD |
|---|---:|---|---:|---:|
| **RegimeAdaptiveBNB** | **0.0967** | recovery | +16.4% | -4.7% |
| **CrashRebound** | 0.0847 | winter | +55.7% | -11.3% |
| **PerPairMR** | 0.0520 | winter | +35.8% | -14.5% |

**These numbers are tiny — and that's the point**. `robust_sharpe = min(sharpe across 4 regimes)` is by construction harsher than v0.4.0's single-timerange Sharpe; comparing 0.097 to v0.4.0's 1.122 is comparing different metrics. The right reading: **first time the project has a portfolio that's positive in 2022 winter** (where BaH was -53% to -85%), AND in 2021 bull, AND in 2023-2025 recovery, AND on the full 5-year mix.

But there's a twist: **the robust_sharpe ceiling was set at round 9 and never broken**. BNBSizedConviction r9 hit robust 0.0980 via a single sizing ablation on the r0 baseline; the next 20 rounds of evolution + 7 new strategy creations failed to produce a strictly Pareto-dominating result. The agent killed BNBSized r22 to free a slot for paradigm experiments, and the v0.4.1 admissible Pareto frontier is just `{BNBMeanRevertSharp r0, BNBSizedConviction r9}` — both BNB-only RSI MR strategies, both killed during the run.

**The most important v0.4.1 finding isn't a Sharpe number — it's that the multi-objective gate setup successfully prevented Goodhart-style metric inflation while exposing a different failure mode: "early local optimum lock"**, where a strong baseline + a single sizing ablation can saturate the regime-robust frontier before complexity arrives.

---

## Final portfolio

| strategy | paradigm | basket | robust | full_5y sharpe | profit | DD | gates |
|---|---|---|---:|---:|---:|---:|---|
| **RegimeAdaptiveBNB** | BNB RSI-MR + composed sizing | [BNB] | **0.097** | 0.14 | +16.4% | -4.7% | floor F / pos P / dom 021e120 |
| **CrashRebound** | drawdown-rebound (counter-trend MR) | [SOL,AVAX,BNB] | 0.085 | 0.29 | +55.7% | -11.3% | floor F / pos P / dom 021e120 |
| **PerPairMR** | paradigm-conditional (RSI-MR / BB-MR / Donchian-break) | [5-pair] | 0.052 | 0.35 | +35.8% | -14.5% | floor F / pos P / dom edf1687 |

**8 paradigms tested, 3 with robust > 0, 6 declared exhausted or paradigm-capped.** Per-pair-conditional emerged as the architecturally novel structure of v0.4.1.

---

## Five-version comparison

| | v0.1.0 | v0.2.0 | v0.3.0 | v0.4.0 | v0.4.1 |
|---|---|---|---|---|---|
| Architecture | single-file | multi-strategy | + MTF + multi-asset | + regime mix + sizing | + pair_basket + multi-timerange + BaH + multi-objective gates |
| Rounds | 99 | 81 | 39 | 20 | **30** |
| Headline metric | Sharpe | Sharpe | Sharpe | Sharpe | **robust_sharpe** (min over 4 regimes) |
| Headline value | 1.44 / 0.19 (*) | 0.67 | 1.07 | 1.122 / 1.339 (**) | 0.097 / N/A (***) |
| Goodhart attempts | 3 (self-reversed) | 0 | 0 | 0 | 0 |
| Fork events | 0 | 0 | 1 (paradigm swap) | 1 (ablation) | 1 (ablation) |
| Explicit kills | 1 | 5 | 2 | 1 | **9** |
| Cross-version meta-findings | — | 5 | 5 | 6+ | **5 new + 4 reinforcements + 2 narrows** |
| Self-stop reason | retroactive Goodhart correction (r82) | context | context | explicit Pareto-end recognition | **explicit multi-strategy convergence ("FINAL" × 3)** |

(*) v0.1.0's 1.44 was `exit_profit_only` Goodhart; agent's r95 sanity check revealed true edge = 0.19.

(**) v0.4.0's 1.339 was Pareto-end via vol_target → 0.003. Real peak 1.122 / +232% at vol_target = 0.025.

(***) v0.4.1's 0.097 is robust_sharpe (min across 4 regimes) — incomparable to prior versions' single-timerange Sharpe. Single-timerange equivalents for FINAL strategies range 0.14-0.35 on full_5y; the 1.07-1.122 trajectory of v0.3.0/v0.4.0 does NOT continue here, and it's not supposed to (different oracle).

---

## Phase-by-phase story

### Phase 1 — Setup with 3 paradigm-diverse starters (r0)

Agent created 3 strategies with explicit paradigm diversity:

- **AltsBollBreak** (alts breakout): Sharpe -2.33 / DD -45% on winter — caught local tops that reverted, WR 32.7%
- **BNBMeanRevertSharp** (BNB-only RSI<25 MR): robust 0.0789 — **only r0 strategy with all 4 regimes positive**, but profit tiny (3-10% per regime) so profit_floor failed
- **TrendRegimeFiltered** (4h ema trend): bull 0.50 / winter -0.31 — the 1d regime gate did silence winter trades but residuals were bad (WR 26.7% in winter)

**Round 0 dispersion across 4 timeranges immediately validated the multi-timerange gate**: the BNB strategy's small-but-positive winter sharpe stood out as the only regime-robust signal. The setup is functionally identical to v0.4.0 (3 paradigm-diverse starters) but the affordance change made the BNB winter-positive structure visible and named-as-Pareto-relevant on round 0.

### Phase 2 — Two paradigms structurally fail under robust gate (r1-r6)

- **AltsBollBreak** (4 evolves r1-r4): tried Donchian-48-sustained, 1d position filter, hard stoploss, slope filter. Every defense traded bull profit for winter silencing. **Killed r5**: "this paradigm has structural winter exposure that cannot be patched without killing the edge".
- **TrendRegimeFiltered** (5 evolves r1-r5): tried 1.05 buffer, slope-up filter, patient SMA75 exit. All neutral or pessimizing. **Killed r6**: "consistently produced full_5y 0.38 / +415%, winter -0.31 — paradigm has structural winter exposure on full 5-pair".

Both kills logged as **explicit kill rows** — bookkeeping drift from v0.4.0 (implicit kill via subsequent create note) self-resolved without program.md change. Agent followed the implied protocol consistently across all 9 kills in the run.

Replacement at r5: **CrashRebound** (DD<-25% trigger + RSI<35 confirm — counter-trend MR family).

### Phase 3 — Cross-pair MR ablation answers the v0.4.0 BNB-skew question (r6-r7)

Agent forked **BNBMeanRevertSharp → BNBMeanRevertMulti** (drop pair_basket constraint, run identical RSI<25 logic on full 5-pair whitelist). Result by pair (r6):

> BNB +0.15 / AVAX +0.02 / BTC -0.14 / ETH -0.18 / SOL -0.09

**Killed r7** with verdict: *"BNB MR is BNB-specific; doesn't generalize. v0.4.0 'MR is BNB-skewed' suspicion is now CONFIRMED cross-pair finding."*

This is **the cleanest cross-pair ablation in the project** — pair_basket affordance + 1 fork round + 1 kill = definitive paradigm-localization answer that v0.4.0 could only suspect. The fork pattern is now stable across 2 versions with clean experimental design.

Replacement at r7: **MajorsBTCLeader** (deliberate v0.3.0 BTCLeaderBreakX paradigm reproduction).

### Phase 4 — v0.3.0 cross-pair-leader hero collapses under robust gate (r7-r9)

> v0.3.0 BTCLeaderBreakX (3-yr bull regime): Sharpe **1.07**
> v0.4.0 BTCLeaderBreakV4 (5-yr regime mix, single timerange): Sharpe **0.79** baseline
> v0.4.1 MajorsBTCLeader (5-yr regime mix, 4 timerange honesty bar): **robust -0.17** baseline

Agent diagnosed (r9 kill note): *"Cross-pair leader signal correlates portfolio DD in winter — exact mechanism v0.4.0 retro flagged. v0.3.0/v0.4.0 hero does NOT survive multi-timerange honesty bar."*

**v0.3.0's 1.07 hero now has cross-version evidence collapsing it progressively as the oracle gets harder**: 1.07 (one regime, one timerange) → 0.79 (mixed regimes, one timerange) → -0.17 robust (4 timerange honesty bar). Each version's stricter gate removes more of what was previously named "edge".

This is exactly what v0.4.1's design intended: **the affordance changes between versions are not just adding features, they are progressively stricter oracles, and the robust_sharpe gate's job is specifically to surface paradigm caps that single-Sharpe couldn't see**.

### Phase 5 — RSI-depth conviction sizing sets the run's Pareto ceiling (r9)

Agent **created BNBSizedConviction** (logged as create, conceptually a fork of BNBMeanRevertSharp) with single change: RSI-depth conviction sizing `scale = clamp(25/RSI, 0.5, 2.0)`.

> Parent BNBMeanRevertSharp r0: robust 0.0789, avg_position 19.98%, full_5y profit +10.8%
> Child BNBSizedConviction r9: robust 0.0980, avg_position 21.98%, full_5y profit +12.46%

**Identical 115 trades, identical WR 69.6%** — sizing redistribution alone lifted robust 24%. Agent's r9 verdict:

> *"Conviction sizing redistributes profit toward deeper-conviction regimes (recovery+full got the lift; bull/winter roughly flat). Sized weakly dominates parent."*

**This r9 result became the v0.4.1 robust_sharpe ceiling for the run.** The next 20 rounds of evolution + 7 new strategy creations did not produce a strategy strictly dominating BNBSized r9 on (robust_sharpe, max_dd). The agent killed BNBSized at r22 to free a slot for paradigm experiments — the mechanism survived in PerPairMR's BNB-RSI branch and in RegimeAdaptiveBNB's RSI-conviction layer, but the explicit Pareto-frontier point did not.

This is **the central finding-pattern of v0.4.1**: a single sizing ablation on the r0 baseline saturated the regime-robust local optimum, and complexity downstream extended the surface (paradigm coverage, basket diversity) without extending the frontier. **Early-Pareto-lock**.

### Phase 6 — paradigm-conditional strategy form emerges (r13-r18)

After PerPairMR's r13 creation as "first per-pair-conditional MR strategy" (BNB→RSI<25 / SOL+AVAX→BB-lower), the strategy iterated through:

- **r14: 4h trend gate added to alts branch** → winter -0.11 → **+0.05** (positive flip), recovery -0.10 → **+0.11** (positive flip), full doubled 0.14 → 0.30.

Agent named this **"second gold finding (volume filter was first)"** — both v0.4.1 in-run discoveries that operate as paradigm-agnostic edge filters.

- **r18: BTC+ETH Donchian-48 breakout branch added** → strategy now expresses **three different paradigms in one .py file**, routed by which pair triggered the entry. Pareto improvement: full_5y 0.30 → 0.35 / 387 → 519 trades / robust held 0.052.

**This is the architecturally novel strategy form of v0.4.1** — earlier versions forced one paradigm per file. PerPairMR's structure is enabled specifically by the v0.4.1 pair_basket affordance + per-pair conditional entry signals; expressing this in v0.3.0/v0.4.0 would have required either (a) 3 separate strategy files (eating slot capacity), or (b) running each paradigm on the wrong pairs (diluting signal).

### Phase 7 — sizing composition rules surface (r25-r28)

Agent **created RegimeAdaptiveBNB** at r25 with **regime-detected** stake sizing (bull 1.5x / neutral 1.0 / winter 0.5x) — first strategy in the project using regime classification as a sizing signal.

- r25: bull sharpe **0.358** (BEST BNB bull ever), winter **0.261** (BEST BNB winter ever), but recovery 0.075 (low) → robust dominated.
- r26: **composed regime × RSI-conviction sizing multiplicatively**. Recovery 0.075 → 0.097, robust 0.097 (Pareto-equal to BNBSized r9 at higher avg position 31% vs 22%).
- r27: pushed regime sizing 1.5x/0.5x → 2x/0.25x. Pareto MOVE not improvement (avg_position 31% → 40%, robust 0.097 → 0.089). **Third independent instance of the "single-knob sizing walk = Pareto move" cross-version meta-finding** (BNBSized r17 linear formula, v0.4.0 r17-r20 vol-target ladder, RegimeAdaptive r27 regime multiplier).

Then r28: **composition transferred to CrashRebound (DD-conviction × regime sizing) — robust 0.085 → -0.083 (catastrophic)**. Agent diagnosed:

> *"Regime and DD-signal are NEGATIVELY correlated (bull = small DDs = signal weak; winter = big DDs = signal strong). Composition INVERSE-amplifies."*

This produced **the most precise sizing rule in the project's history**:

> Sizing mechanisms compose multiplicatively when their underlying signals are independent OR positively correlated. Negatively correlated signals cause inverse-amplification.

r29: agent reverted r28 composition, declared all 3 strategies FINAL.

### Phase 8 — voluntary multi-strategy convergence (r29)

All 3 strategies stable at proven baselines after r28's composition experiment failed and was reverted:

- **CrashRebound**: r16 baseline (DD-conviction sizing only), robust 0.085
- **PerPairMR**: r19 baseline (paradigm-conditional, 5-pair), robust 0.052
- **RegimeAdaptiveBNB**: r26 baseline (composed sizing), robust 0.097

Agent's r29 notes: three explicit "FINAL" markers. Different stop mechanism from v0.4.0:

- **v0.4.0 stop**: one strategy walking off into Sharpe-via-tightening noise; agent named "degenerate territory"
- **v0.4.1 stop**: 3-strategy lineup reached joint stable optimum; agent named "FINAL" — converged not via metric saturation but via revertable-experiment exhaustion (no new mutation in the search space produced robust improvement)

Most "researcher-like" stop in the project so far.

---

## Findings — five new, four reinforcements, two narrows

### Five NEW v0.4.1 findings (not in any prior retrospective)

**1. Conviction-style sizing transfers paradigm-agnostically**

Two independent demonstrations: RSI-depth on BNB-MR (r9, +24% robust) and DD-depth on drawdown-rebound (r16, +37% robust). Same mechanism — scale stake by inverse of signal-depth — works across mean-reversion AND counter-trend MR. **Refines, doesn't contradict, v0.4.0 finding 1**: sizing isn't edge, but conviction-style sizing IS a paradigm-agnostic profit-redistribution mechanism. Where v0.4.0 said "vol-target sizing is risk control not edge", v0.4.1 says "...AND signal-conditional sizing is paradigm-agnostic redistribution".

**2. Sizing-composition rule (the most precise sizing rule across 5 versions)**

```
Compose multiplicatively when signals independent or positively correlated.
Avoid composition when signals negatively correlated (inverse-amplifies).
```

RegimeAdaptive r26 (regime × RSI = independent) succeeded; CrashRebound r28 (regime × DD = negatively correlated) crashed catastrophically. First explicit composition rule produced by the agent across 5 versions; precision goes beyond "yes/no transfer" to "transfer iff correlation structure is right".

**3. Signal-driven sizing > regime-driven sizing for MR (composition optimal)**

RegimeAdaptive r25 with regime-only sizing achieved per-strategy historic high in bull (0.358) and winter (0.236), but recovery languished at 0.075 because regime classification can't distinguish within-recovery pullbacks from neutral periods. RSI-depth sizing does. r26 composing both = best of both. Implies a hierarchy: **signal-driven sizing has higher resolution than regime-driven for paradigms with within-regime structure; regime-driven adds orthogonal context when signals are independent**.

**4. First paradigm-conditional strategy form**

PerPairMR final structure: BNB→RSI MR / SOL+AVAX→BB MR / BTC+ETH→Donchian breakout, all in one .py file routed by pair. **Architecturally novel** — earlier versions forced one paradigm per file. Enabled specifically by v0.4.1 pair_basket affordance + per-pair conditional entry signals. Expanded the project's strategy-design vocabulary; future versions could explicitly encourage this pattern via template.

**5. 4h trend gate as second gold filter (paradigm-agnostic)**

PerPairMR r14: 4h ema50>ema200 gate flipped winter -0.11 → +0.05 and recovery -0.10 → +0.11 simultaneously on the alts branch. Distinct from v0.2.0 volume filter — works for momentum, counter-trend, and breakout paradigms tested in v0.4.1. **Two gold filters now have explicit attribution**: volume (v0.2.0) for capitulation/MR family; 4h trend (v0.4.1) for cross-paradigm regime gating.

### Four cross-version REINFORCEMENTS

**1. Cross-pair-MR has structural paradigm cap (v0.4.0 + v0.4.1, two failures)**

v0.4.0 CrossPairMR (alt/BTC ratio MR) declared exhausted r7. v0.4.1 CrossPairRatio (BTC/ETH ratio z-score MR) declared exhausted r23 after 1 round. Different ratios, different timeranges, same result. **Two independent failures = paradigm cap, not version-specific issue**.

**2. Cross-pair-leader breakout collapses progressively as oracle hardens**

> v0.3.0 BTCLeaderBreakX (1 regime, 1 timerange): **1.07**
> v0.4.0 BTCLeaderBreakV4 (mixed regimes, 1 timerange): **0.79** baseline
> v0.4.1 MajorsBTCLeader (mixed regimes, 4 timeranges): **-0.17** robust

The v0.3.0 hero number was an oracle artifact, not a stable property. Each version of stricter oracle removed more of what was named edge. **Cross-version pattern**: stronger oracles surface paradigm caps that weaker ones can't see.

**3. Momentum 0.40 cap is INTRINSIC even with optimal filter stack**

v0.3.0 MACDMomentumMTF 0.41, v0.4.0 MomentumMTFConfluence 0.40, v0.4.1 MomentumGoldFilters 0.21 (with ALL gold filters stacked). Stacking degraded vs less-filtered v0.4.0 baseline. **The 0.40 momentum ceiling is structural, not a tuning artifact** — three independent attempts across regimes and filter configurations all bounded at the same value.

**4. Single-knob sizing walks produce Pareto move not improvement (3rd instance, 2 versions)**

BNBSized r17 (linear vs 25/RSI formula) + v0.4.0 r17-r20 (vol-target ladder) + RegimeAdaptive r27 (regime multiplier). Three independent instances, same outcome: sharpe drops slightly OR moves laterally, avg_position rises, DD widens. **Stable cross-version meta-finding**.

### Two cross-version NARROWS (v0.4.1 corrects/limits prior universal claims)

**1. Volume filter is paradigm-specific (narrows v0.2.0 universal claim)**

v0.2.0 declared volume filter "first universal gold filter when stack is light". v0.4.1 r24 evidence: volume filter HURTS momentum (continuations don't spike volume; bull sharpe 0.05 → 0.46 when removed) and HELPS capitulation/MR (CrashRebound r10 confirmed lift). **Narrows v0.2.0 finding from universal to family-specific: volume helps capitulation/MR; volume hurts continuation/momentum**.

**2. Patient-exit (SMA75-100) is breakout-family-specific (narrows v0.4.0)**

v0.4.0 r13 finding "regime-mix prefers SMA75-100 patient exit" was on a breakout strategy. v0.4.1 r14 tested transfer to CrashRebound (counter-trend MR family): SMA50→SMA100 backfired catastrophically (winter 0.06→-0.22, recovery 0.19→0.01). **Narrows v0.4.0 finding from "regime-mix prefers patience" to "breakout-family prefers patience; counter-trend MR family prefers tight exits"**.

**Cross-paradigm transferability rules now form a system:**

| Mechanism | Transfer rule |
|---|---|
| Conviction-style sizing (signal-depth scaling) | ✅ paradigm-agnostic |
| 4h trend gate | ✅ paradigm-agnostic (v0.4.1 finding) |
| Volume filter | ❌ paradigm-specific (capitulation/MR only) |
| Patient exit (SMA75-100) | ❌ paradigm-specific (breakout family only) |
| Multi-bar DD confirmation | ❌ misses inflection-point entries |
| Sizing composition | ✅ iff signals independent/positively-correlated |

---

## Behavioral observations

**Voluntary multi-strategy convergence stop.** All 3 strategies marked "FINAL" voluntarily in r29 notes. Different mechanism from v0.4.0's Pareto-end stop (one strategy walking off into single-metric noise) — here the agent recognized the joint 3-strategy lineup had stabilized at proven baselines after r28's composition experiment failed and was reverted. Most "researcher-like" stop in the project: experiment failed → revert → declare convergence on the multi-strategy portfolio rather than continue squeezing.

**Bookkeeping drift from v0.4.0 RESOLVED via behavior change.** v0.4.0 retrospective flagged the "implicit kill via subsequent create note" pattern (1 explicit kill row for 4 actual kills). v0.4.1 shows 9 explicit kill rows for 9 actual kills — agent followed the implied protocol consistently without any program.md tightening. Suggests **the retrospective itself functions as durable program guidance even though not in program.md**. Worth noting for future: archived retrospectives are load-bearing on agent behavior, not just historical record.

**Pareto-frontier-aware decision-making throughout.** `pareto_dominated_by` gate fired on all 3 FINAL strategies, with the dominators being early-run strategies (BNBMeanRevertSharp r0, BNBSizedConviction r9). Agent did NOT treat Pareto domination as automatic kill — it kept evolving the dominated strategies because they explored different paradigms with potential for future Pareto extension. **The gate worked as informational rather than imperative**, treated at the same level as profit_floor failure: a state to acknowledge in the note, not a kill criterion.

**Ablation-fork pattern continues.** r6 fork (BNBMeanRevertSharp → BNBMeanRevertMulti) was deliberate ablation — drop pair_basket constraint to test "is BNB MR pair-specific or generic?". Answer arrived in 1 round, child killed r7. Cleaner than v0.4.0's fork (also ablation but tested multi-round). The pattern named in v0.4.0 retro is now stable across 2 versions.

**Zero classic Goodhart attempts (5th run in a row).** No exit_profit_only toggles, no ROI clipping, no Sharpe-up-while-profit-down without explicit Pareto-walk justification. Multi-objective gates likely had structural deterrent effect: `pareto_dominated_by` automatically detects "sizing-walk Sharpe inflation" patterns by reading historical results.tsv rows. r17 BNBSized linear-formula attempt (Pareto move within the same strategy) was auto-flagged as dominated by r9 baseline.

**Minor bookkeeping inconsistency**: r9 BNBSizedConviction was conceptually a fork (note says "fork of BNB with RSI-depth conviction sizing") but logged as `create`, not `fork`. r6 was the only explicit fork event. Small inconsistency, doesn't affect findings — but the rule "fork events require explicit fork rows" could be tightened in a future version.

---

## Limitations and known issues

**`profit_floor` failed on all 3 FINAL strategies.** Threshold 20% per timerange — none clear winter_2022 (best: RegimeAdaptive +3.71%). Partly inherent (long-only spot in a -85% bear), partly calibration (20% / year on a low-position-size strategy is high). Gate did its job (informed agent of the floor), but no strategy achieved it. **v0.5.0 should consider lowering threshold OR making it timerange-conditional** (winter floor ≥ 0%, recovery floor ≥ 10%).

**All 3 FINAL strategies Pareto-dominated by early-run strategies.** Within-run Pareto frontier is `{BNBMeanRevertSharp r0, BNBSizedConviction r9}` — both BNB-only RSI MR, both KILLED during the run. The 22 subsequent rounds of evolution + 7 new creations did not produce strict Pareto dominance. **Suggests "early local optimum lock" pattern**: a strong baseline + a single sizing ablation can saturate the regime-robust frontier before complexity arrives. **Recommendation**: v0.5.0 might explicitly carry forward Pareto-frontier strategies across rounds rather than killing them for slot freeing — let the agent evolve next to the frontier.

**robust_sharpe absolute values are tiny (0.05-0.10).** Successful per the gate's criterion (positive across all 4 regimes), but not impressive in trading-deployment terms. Long-only spot crypto in 2022 has structurally low alpha — the strategies' near-zero positive winter sharpe is what the gate forces them to defend (BaH winter sharpe is consistently negative, -0.7 to -1.5). **The headline isn't a Sharpe number** — it's "first multi-strategy lineup with robust sharpe > 0 across all regimes simultaneously".

**Strategies underperform BaH on full_5y by 30-60×.** CrashRebound +55.7% / PerPairMR +35.8% / RegimeAdaptive +16.4% vs BaH +1740% to +3632% (5-pair equal-weight ~+2188%). The strategies trade absolute return for drawdown protection. **v0.4.1 strategies are not standalone trading strategies** — they're "drawdown-protected partial-exposure" research artifacts. Real-world use would be as winter-hedge allocation alongside BaH, not replacement.

**Long-only spot is the binding affordance constraint.** Winter alpha extraction is structurally capped because best behavior in a bear is "don't trade". **Adding shorting (perp futures) is the single most-impactful affordance unlock available**. Out of v0.4.1 scope but the obvious v0.5.0+ direction.

**pair_basket scope still narrow.** RegimeAdaptive uses 1 pair (BNB), CrashRebound uses 3. Only PerPairMR uses full 5. CrashRebound r18 attempted basket expansion to 5-pair, surfaced clean Pareto move (full sharpe +0.40 BUT winter dropped 0.085→0.013), reverted r19. **The robust_sharpe metric structurally penalizes basket expansion when added pairs aren't winter-positive** — basket selection becomes a regime-stability optimization rather than a diversification-for-return one.

---

## Recommended v0.5.0 directions

**Already addressed in v0.4.1** (from v0.4.0's candidate list):

- **B** (multi-objective oracle) — implemented as profit_floor + min_position_size + pareto_dominated_by
- **C** (external benchmark) — implemented as BaH per timerange in run.py
- **F** (bookkeeping) — resolved by behavior change alone (9/9 explicit kills logged)

**Remaining from v0.4.0 list:**

- **A** (external orchestrator): priority medium; v0.4.1 ran 30 rounds vs v0.4.0's 20, so context constraint less binding for now
- **D** (cross-asset-class): priority low — significant scope creep
- **E** (per-strategy timeframe): priority medium — folds naturally into G

**New v0.5.0 candidates surfaced by v0.4.1:**

**G — Sub-1h base timeframe (15m or 5m).** Capitulation-rebound, breakout-pullback, MR entry-timing all benefit from finer base TF. Cost: data 4-12×, backtest 3-5×. **Plausibly the biggest single robust_sharpe lift available without breaking spot constraint**. Independent of all other proposed changes.

**H — Hyperopt inner loop.** Hand off continuous-parameter search (RSI threshold, BB width, sizing scale params) to FreqTrade hyperopt; LLM agent constrains the space. Multiplies effective search depth. Risk: introduces new Goodhart surface — needs careful OOS split design and oracle-gate enforcement.

**I — Shorting via perp futures.** **BIGGEST single unlock available**. Converts winter from "sit out" to "extract alpha from negative drift". Plausible 2-5× robust_sharpe lift just from being able to act in bears. Cost: trading_mode change, funding-rate data, strategy short-side logic, oracle adjustment. Likely deserves its own version (not "one variable" if combined with other changes).

**J — Carry forward Pareto-frontier strategies across rounds.** v0.4.1 limitation: BNBSized r9 (Pareto-frontier) was killed at r22 for slot freeing. Future version could enforce "Pareto-frontier strategies are sticky — don't kill, set aside in archive slot". Lets agent evolve next to the frontier rather than reset to zero each time a new paradigm starts.

**My ranking:**

```
v0.5.0 = G (sub-hour) + H (hyperopt) bundled
        — independent affordances within long-only-spot framework
        — each ~1.5-2× robust_sharpe, both ROI-positive
        — E (per-strategy TF) folds naturally into G

v0.6.0 = I (shorting) standalone
        — transformative single-variable change
        — cleanest attribution if isolated
        — gives clean before/after vs G+H baseline

deferred: A, J, D, F-extensions (as needed)
```

Rationale for splitting G+H from I: G+H stay within v0.4.1's "spot crypto, robust_sharpe oracle" comparable framework, so v0.5.0 results read against v0.4.1 cleanly. I (shorting) changes the regime-extraction physics — winter sharpe ceiling moves structurally — and needs its own comparison baseline, ideally vs a long-only G+H result on the same data.

---

## User reflections

*(blank — to be filled in by the human. My analysis emphasizes what I think stood out. Particularly relevant for v0.4.1: did I correctly characterize the "early Pareto lock" framing? The "all 3 FINAL strategies are Pareto-dominated by killed early-run strategies" is the most subtle finding and I want to make sure the framing matches the user's read.)*
