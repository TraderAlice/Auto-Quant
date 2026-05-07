# v0.4.0 — Retrospective

**Run**: 5-pair crypto portfolio (BTC/ETH/SOL/BNB/AVAX) on 1h base + 4h/1d informative, timerange **2021-01-01 → 2025-12-31** (regime-mixed: 2021 bull, 2022 winter, 2023-2025 recovery)
**Branch**: `autoresearch/may7` (preserved)
**Run-end commit**: `011eb08` (round 20, agent self-stopped at "Pareto end")
**Real-peak commit**: `d86392f` (round 11, Sharpe 1.122 / +232% / DD -20%)
**Total**: 20 rounds — 60 events — 6 creates, 29 evolves, 1 fork, 1 kill (explicit), 23 stables

---

## Headline — careful framing required

v0.4.0 has **two Sharpe peaks**, and reading just one is misleading.

- **Real peak (round 11)**: Sharpe **1.122** / profit **+232%** / DD -19.9% on 5-year regime-mixed data. **This is the number that matters.** Strictly stronger than v0.3.0's clean peak of 1.07 on bull-only data. The strategy (VolBreakoutSized) maintained meaningful portfolio exposure.

- **Pareto-end peak (round 20)**: Sharpe **1.339** / profit **+25%** / DD -4.3%. Same strategy, same trades, same win rate — only difference is `vol_target` parameter on the sizing function tightened from 0.025 to 0.003. Profit collapsed ~10× while Sharpe inflated. Agent self-flagged "degenerate territory" and stopped.

The trajectory v0.1.0 → v0.2.0 → v0.3.0 → v0.4.0 should be read as **0.19 → 0.67 → 1.07 → 1.12** (clean peaks at meaningful exposure). The 1.339 number is structurally clean (no oracle gaming in the v0.1.0 sense) but represents Sharpe-via-tiny-stakes territory, where a portfolio is barely participating.

**The most important v0.4.0 finding isn't a Sharpe number — it's the explicit Pareto-frontier mapping** that exposes Sharpe-as-single-oracle's degeneracy boundary.

---

## Final portfolio

| strategy | paradigm | real-peak Sharpe | profit | DD | status |
|---|---|---|---|---|---|
| **VolBreakoutSized** | per-pair breakout | **1.122** | +232% | -19.9% | LEADER |
| **BTCLeaderBreakV4** | cross-pair breakout | 0.79 | +170% | -12.8% | alive |
| **MomentumMTFConfluence** | momentum | 0.40 | +53% | -23.2% | alive (paradigm-cap evidence) |
| ~~MeanRevRSIDip~~ | mean-reversion | — | — | — | killed r5 |
| ~~CrossPairMR~~ | mean-reversion (cross-pair) | — | — | — | killed r7 |
| ~~ChannelADXTrend~~ | trend (no-sizing control) | — | — | — | killed r8 |
| ~~VolBreakoutEqual~~ | per-pair-breakout (sizing-isolation fork) | — | — | — | killed r10 |

**5 paradigms tested, 3 with positive edge, 2 declared exhausted.** Per-pair breakout dominated; cross-pair (the v0.3.0 winner) downgraded; momentum capped at structural ~0.4; mean-reversion didn't survive regime mix.

---

## Four-version comparison

| | v0.1.0 | v0.2.0 | v0.3.0 | v0.4.0 |
|---|---|---|---|---|
| Architecture | single-file | multi-strategy | + MTF + multi-asset | + regime mix + sizing |
| Rounds | 99 | 81 | 39 | 20 |
| Headline Sharpe | 1.44 (*) | 0.67 | 1.07 | 1.339 (**) |
| Real-edge Sharpe | **0.19** | 0.67 | 1.07 | **1.122** |
| Profit at real peak | +19% | +145% | +85% (3-yr) | **+232%** (5-yr) |
| Goodhart attempts | 3 (self-reversed) | 0 | 0 | 0 |
| Fork events | 0 | 0 | 1 (paradigm swap) | 1 (ablation) |
| Cross-version meta-findings | — | 5 | 5 | **6+** |
| Self-stop reason | context | context | context | **explicit Pareto-end recognition** |

(*) v0.1.0's 1.44 was `exit_profit_only` Goodhart in bull regime; agent's own sanity check at round 95 revealed true edge = 0.19.

(**) v0.4.0's 1.339 is structurally clean (no exit_profit_only, no ROI clipping) but is a Pareto-walk endpoint where profit fell to +25% — a different kind of "Sharpe inflation" via tiny stake sizing. The "real peak" 1.122 / +232% is the meaningful number.

---

## Phase-by-phase story

### Phase 1 — Setup with controlled-experiment design (r0)

Agent created 3 strategies — all using MTF, deliberately mixing sizing-aware and equal-weight to enable later attribution:

- **VolBreakoutSized**: per-pair Donchian breakout + vol-target sizing. Sharpe **1.085 baseline** — first round already above v0.3.0 peak.
- **ChannelADXTrend**: trend, equal-weight (deliberately). Agent's docstring: *"Equal-weight (no custom_stake_amount): this is the honest control case for whether sizing-aware strategies owe their survival to the sizing or to real edge."* Result: Sharpe **-2.14** (collapsed in 2022 winter). The control case worked exactly as designed.
- **MeanRevRSIDip**: mean-reversion + sizing. Sharpe **0.03** (barely positive — sizing kept it from collapse but couldn't push edge).

**Round 0 dispersion (-2.14 to +1.085) immediately validated v0.4.0's regime stress test**: equal-weight trend can't survive bear; sized breakout can.

### Phase 2 — Mean-reversion fails to find edge (r1-r5)

3 evolves of MeanRevRSIDip:
- r1 unchanged (deterministic stable)
- r3: -7% stoploss → BACKFIRED (-0.22). Agent: *"realized losses on RSI<28 dips that would have recovered — fundamental MR vs stoploss mismatch."*
- r4: revert stop + tighten regime → still -0.05.

Killed r5, replaced with CrossPairMR (alt/BTC ratio z-score). Two more evolves (r5-r7), still negative, BNB-only-skewed. Agent's verdict at r7:

> *"After 2 MR implementations × 4 total evolves with no aggregate positive, **MR paradigm exhausted on this 5-pair regime-mixed universe**."*

**Negative paradigm finding** with cross-strategy pattern preserved: both MR implementations were structurally BNB-skewed (other 4 pairs ~zero), suggesting MR alpha on this universe lives in BNB's specific behavior, not a generic asset-agnostic signal.

### Phase 3 — Sizing-vs-edge ablation experiment (r7) — the gold of this run

Agent **forked VolBreakoutSized → VolBreakoutEqual** as a deliberate ablation:
- Parent (sized): Sharpe 1.085 / profit 150% / DD -16% / Sortino 3.89
- Child (equal-weight): Sharpe 0.972 / profit **220%** / DD -20% / Calmar 11.81

Identical 1376 trades, same WR 35.1%. **Only sizing differs.**

Agent's verdict (worth quoting in full):

> *"VOL-TARGET CARRIES NO EDGE — it's pure risk control. The breakout signal itself has full edge across regime-mixed data. This DIRECTLY answers v0.4.0 program.md's named question: 'real edge or sizing artifact?' Answer: real edge. Major finding."*

This is **the cleanest controlled experiment in the project's history**. v0.4.0's central methodological question — "in regime-mixed data, can we tell sizing-as-risk-control from sizing-as-fake-edge?" — was answered cleanly by round 7.

The split between Sortino-better-on-Sized vs Calmar-better-on-Equal is itself a finding: vol-target sizing improves risk-adjusted return (Sortino) at the cost of total return (Calmar). Different objectives, different sizing optima.

### Phase 4 — Trend killed, cross-pair revisited (r8)

ChannelADXTrend evolved 4 times (r2-r4), eventually plateaued at +0.05 with persistent AVAX drag. Killed r8 to free slot.

Replacement: **BTCLeaderBreakV4** — a deliberate v0.3.0 paradigm reproduction (BTC 4h Donchian → all-pair trigger). Result:

> v0.3.0 BTCLeaderBreakX (3-yr bull): Sharpe **1.07**
> v0.4.0 BTCLeaderBreakV4 (5-yr regime mix): Sharpe **0.59 baseline**

**Cross-pair Sharpe drops ~45% under regime mix**, while per-pair Donchian (VolBreakoutSized) holds at 1.085. **v0.3.0's relative paradigm ordering reversed**. Agent's mechanism:

> *"BTC-leader signal triggers ALL pairs simultaneously → concentrated portfolio DD during BTC-leadership cycles. Per-pair Donchian staggers triggers naturally → DD diversifies."*

This is a **regime-mix-specific risk-distribution finding** that v0.3.0's data structurally couldn't surface. Cross-pair signals correlate the portfolio; per-pair signals diversify it.

### Phase 5 — Cross-version paradigm cap confirmed (r11)

Agent created **MomentumMTFConfluence** as v0.3.0 MACDMomentumMTF reproduction. Sharpe **0.40** baseline.

> v0.3.0 MACDMomentumMTF (3-yr bull, 5-pair): Sharpe **0.41**
> v0.4.0 MomentumMTFConfluence (5-yr regime mix, 5-pair): Sharpe **0.40**

**Two completely different timeranges, same 0.40 ceiling**. Agent:

> *"v0.3.0 retro speculated the cap was 'BTC/ETH-tuning that doesn't generalize' — v0.4.0 evidence: it's a PARADIGM-level cap, not universe-tuning. Cross-version cross-paradigm meta-finding."*

**Upgrades v0.3.0 retrospective speculation to confirmed paradigm-level structural cap.** Momentum on 1h crypto majors hits ~0.4 Sharpe regardless of regime.

(Round 16 attempted to break this cap by adding 4h ADX>22 filter; collapsed to Sharpe 0.14 — confirming filter-stack-overload is paradigm-agnostic, see Phase 6.)

### Phase 6 — v0.3.0 finding corrections + universalization (r13, r14, r16)

**r13: Patient-exit re-evaluation.** BTCLeaderBreakV4 exit SMA50 → SMA75: Sharpe 0.69 → **0.80** (+15%), profit 99% → 149% (+50%), DD -19.5% → **-11.6%** (-40%). All 5 pairs improved.

> *"v0.3.0's terminal SMA50 was bull-regime-conditional sub-optimum. In regime mix, more patience pays (skip 2022 whipsaws)."*

**v0.3.0's "SMA50 patient exit" sweet spot is corrected** — regime-mixed data prefers SMA75-100. r14 confirmed SMA100 is essentially equivalent to SMA75 (broad local optimum).

**r16: Filter-stack-overload generalized.** Adding ADX>22 to MomentumMTFConfluence's already-confluent stack collapsed Sharpe 0.40 → 0.14. Agent generalized:

> *"v0.3.0 Finding 4 ('volume helps when stack is light, hurts when heavy') generalizes to OTHER filter types — filter-stack-overload is paradigm-agnostic."*

**v0.3.0's volume-specific finding upgraded to a universal stack-size rule**: any additional filter on a heavy stack causes selection-bias degradation, regardless of filter type or paradigm.

### Phase 7 — Pareto frontier walk + voluntary stop (r17-r20)

Most distinctive sequence in the project so far. Starting from VolBreakoutSized at Sharpe 1.122 / profit +232% (vol_target 0.025), agent sequentially tightened vol_target:

| round | vol_target | Sharpe | profit | DD |
|---|---|---|---|---|
| r11 baseline | 0.025 | 1.122 | +232% | -19.9% |
| r17 | 0.020 | 1.155 | +188% | -19.2% |
| r18 | 0.015 | 1.193 | +140% | -17.5% |
| r19 | 0.010 | 1.267 | +95% | -13.4% |
| r19b | 0.005 | 1.327 | +44.5% | -7.0% |
| r20 (stop) | 0.003 | 1.339 | +25% | -4.3% |

**Sharpe monotonically up, profit monotonically down.** Identical entry/exit signals throughout — the only varying parameter was per-trade stake size.

Agent's r19 note flagged the diminishing returns:

> *"Profit 44.5%→25% (~4.5%/yr — degenerate territory)... Sharpe-via-tightening peak found near 0.005-0.003 boundary; gains are now noise."*

And at r20, voluntarily stopped:

> *"Sharpe 1.327→1.339 (+0.012, MARGINAL — curve has flattened)... Run stops here for retrospective review."*

This is **a NEW kind of self-aware behavior** — different from v0.1.0's retroactive Goodhart correction, different from v0.3.0's plateau-based context exhaustion. Agent recognized that **the metric (Sharpe) was monotonically improving via a mechanism (de-risking) that wasn't producing genuine improvement**, and stopped.

The Pareto curve itself is a research artifact: **a clean monotonic relationship between sizing risk and Sharpe** in a strategy whose underlying signal edge is independently confirmed (via the r7 ablation).

---

## Six structural cross-version findings

### 1. Vol-target sizing is risk-control, not edge
The r7 fork experiment cleanly proved this. Already strong in v0.4.0; the Pareto walk in r17-r20 makes it even stronger (sizing dial moves Sharpe-vs-profit curve, never adds genuine edge).

### 2. Per-pair > cross-pair Donchian in regime-mixed data
v0.3.0's relative ordering reversed. Mechanism: BTC-leader signals concentrate portfolio DD; per-pair signals diversify naturally.

### 3. Momentum paradigm has structural ~0.4 Sharpe cap
Confirmed across two regimes, two runs, completely different timeranges. v0.3.0 speculation → v0.4.0 confirmed structural finding. Upgrade to paradigm-level.

### 4. Patient-exit "SMA50 sweet spot" was bull-conditional; regime mix prefers SMA75-100
v0.3.0's specific value corrected. The patient-exit FAMILY direction was right; the specific lag value needed adjustment for regime mix.

### 5. Filter-stack-overload is paradigm-agnostic
v0.3.0's volume-specific rule generalizes to any filter on a heavy stack. ADX example in r16 confirmed.

### 6. Sharpe-as-single-oracle has a degeneracy boundary
**New v0.4.0 finding.** Tightening the risk-control dial (vol_target → 0) monotonically inflates Sharpe while collapsing profit. At the limit, the strategy degenerates to "trade tiny enough that Sharpe → ∞ but portfolio doesn't participate". Strictly clean (no Goodhart in v0.1.0 sense), but illustrates the limits of single-metric oracle design. **This finding directly motivates v0.5.0+ exploring multi-objective oracles or constrained Pareto-walk discipline.**

---

## Behavioral observations

**Self-stopping at Pareto degeneracy.** Agent's r19 ("degenerate territory") and r20 ("gains are now noise. Run stops here") are voluntary halts at a point where continued optimization would still nominally improve the metric. Distinct from prior runs — v0.1.0 stopped via Goodhart self-reversal (different mechanism), v0.3.0 stopped via context saturation (different reason). v0.4.0's stop is the most "researcher-like": the metric is still climbing but the mechanism is no longer interesting.

**Ablation fork as deliberate experimental design.** v0.3.0's first fork was a paradigm-swap try (different signal). v0.4.0's fork (r7) was an ablation experiment (same strategy, one parameter varied: presence/absence of `custom_stake_amount`). Cleaner experimental design; cleaner answer. Pattern worth naming and reusing in future versions.

**Cross-version retrospective citations as load-bearing reasoning.** Almost every meta-finding above is articulated in agent notes that explicitly cite v0.3.0 retrospective sections. Example r11: *"v0.3.0 retro speculated the cap was 'BTC/ETH-tuning that doesn't generalize' — v0.4.0 evidence: it's a PARADIGM-level cap, not universe-tuning."* The archived retrospectives are functioning as active reasoning substrate, not just historical record. Validates the `versions/` architecture as load-bearing.

**Zero classic Goodhart attempts.** Fourth consecutive run with no exit_profit_only, no ROI clipping, no Sharpe-up-while-profit-down without explicit Pareto-walk justification. The Pareto walk in r17-r20 IS Sharpe-up-profit-down but is structurally legitimate (real de-risking, agent labeled it).

---

## Limitations and known issues

**Bookkeeping drift on kill events.** Only 1 explicit kill row in `results.tsv`, but 4 strategies were actually killed (MeanRevRSIDip r5, CrossPairMR r7, ChannelADXTrend r8, VolBreakoutEqual r10). Agent used the "create note mentions killing X" pattern instead of separate kill rows. This breaks `analysis.ipynb`'s "alive set" derivation logic — the notebook will show all 6 ever-created strategies as alive at run-end, not just the 3 actually alive.

**Recommendation for v0.5.0:** either tighten `program.md` rule ("kill REQUIRES a separate event row even when paired with create"), or harden `analysis.ipynb` to handle the implicit-kill pattern via filesystem cross-check (`if strategy file no longer in user_data/strategies/, mark inactive`).

**Round 1 absent from tsv.** Rounds in `results.tsv` jump 0 → 2. Likely an agent oversight or a re-run that didn't get logged.

**Per-strategy trade counts vary widely.** Leader VolBreakoutSized has 1376 trades at real peak; Pareto-end version has same. Healthy sample. But killed strategies had varying counts (some <100, some 4000+) — Sharpe confidence intervals at small samples are wide.

**Two-peak ambiguity.** Most subtle communication problem in v0.4.0. The "headline Sharpe 1.339" is technically correct but misleading without context. Future external write-ups should consistently lead with the real peak (1.122 / +232%) and treat the Pareto-end as a sub-finding.

**Still no external benchmark.** Buy-and-hold over 2021-2025 5-pair was probably ~+200% with Sharpe ~1.0. v0.4.0 real peak (+232% / Sharpe 1.122) finally beats BaH meaningfully — but the comparison is not yet computed in `run.py`. Would be a small `run.py` upgrade (~30 lines) to inject BaH reference.

**Still single asset class.** Crypto majors only. Generalization to equity / commodity / fx untested.

---

## Recommended v0.5.0 directions

The user's reflection on optimization is post-archive (this section reflects my recommendations as of run-end). Several candidates with different value/cost profiles:

### A. External orchestrator for context-resetting (the deepest fix)
**Problem**: v0.4.0 stopped at 20 rounds vs v0.1.0/0.2.0/0.3.0's 99/81/39. Per-round information density is monotonically growing (per-pair × MTF × cross-paradigm × regime mix), saturating context. An external orchestrator — agent runs in fresh sessions per round, only relevant prior state passed in via `results.tsv` + current strategies — would remove this cap. Substantial but bounded engineering work.

### B. Multi-objective oracle (addresses Sharpe-degeneracy directly)
**Problem**: v0.4.0 surfaced that Sharpe alone has a degeneracy boundary. Adding profit-floor or DD-ceiling constraints to the oracle, or reporting a Pareto-curve summary instead of a single Sharpe, would give the agent more structured optimization targets. Direct response to the v0.4.0 finding.

### C. External benchmark injection (lowest cost, high value)
**Problem**: ~30 lines in `run.py` to compute and report buy-and-hold portfolio return + Sharpe alongside strategy metrics. Gives agent a permanent reference point. Already deferred from v0.3.0 → v0.4.0 → v0.5.0; should land soon.

### D. Cross-asset-class generalization
**Problem**: Universe stuck on crypto. Adding FX (EUR/USD, USD/JPY) or equity (SPY, QQQ) would test whether discoveries generalize across asset classes. Significant data-loader work; FreqTrade's stock support is weaker than crypto.

### E. Per-strategy timeframe selection
**Problem**: Strategies are forced to use 1h base. Some paradigms (very-short MR; long-term trend) may have natural base TFs other than 1h. Allowing per-strategy `timeframe` declaration extends the design space substantially.

### F. Bookkeeping hardening (low priority, low cost)
Address the kill-event drift via either program.md rule tightening or analysis.ipynb robustness. Should be addressed eventually but isn't blocking science.

**My ranking (by research-value-per-engineering-cost):** B → C → A → E → F → D. B addresses the most pressing v0.4.0-surfaced limitation; C is a cheap quality-of-life win that's been deferred too long; A removes the binding constraint on run depth.

---

## User reflections

*(blank — to be filled in by the human. My analysis emphasizes what I think stood out; the human's complement belongs here, including things I may have over-weighted, mis-framed, or missed entirely. Particularly relevant for v0.4.0: did I correctly characterize the two-peak distinction, or am I being too cautious about the 1.339?)*
