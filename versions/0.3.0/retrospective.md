# v0.3.0 — Retrospective

**Run**: 5-pair crypto portfolio (BTC/USDT + ETH/USDT + SOL/USDT + BNB/USDT + AVAX/USDT) on 1h base + 4h/1d informative, timerange 2023-01-01 → 2025-12-31
**Branch**: `autoresearch/apr24` (preserved)
**Peak commit**: `8d007d1` (round 39 final state)
**Total rounds**: 39 — 120 events — 5 creates, 46 evolves, 1 fork, 3 kills, 65 stables

---

## Headline

**v0.3.0 produced the project's first clean-edge Sharpe above 1.0**: BTCLeaderBreakX, a cross-pair breakout strategy, reached **Sharpe 1.07 / DD -8.8% / all 5 pairs positive** — a +60% improvement over v0.2.0's clean peak (0.67) in less than half the rounds. The strategy uses both of v0.3.0's new affordances (cross-pair signal via BTC 4h Donchian + 5-pair portfolio) in a configuration that literally could not have been built in v0.1.0 or v0.2.0.

Beyond the headline number, v0.3.0 produced **more structural findings per round** than any prior version — partly because per-pair reporting + cross-paradigm + cross-TF comparison together create N-dimensional comparison surfaces that single-paradigm or single-pair setups don't have.

And: **zero Goodhart attempts in 39 rounds** — third run in a row. The multi-axis comparison substrate + prior-retrospective awareness continues to work as a defense.

---

## Final portfolio

| strategy | paradigm | peak Sharpe | DD | v0.3.0-specific affordance used |
|---|---|---|---|---|
| **BTCLeaderBreakX** | cross-pair breakout | **1.07** | -8.8% | cross-pair (BTC 4h) + MTF |
| **MTFTrendStack** | trend-following | 0.74 | -12.5% | MTF confluence (1d + 4h + 1h) |
| **VolBBSqueeze** | volatility | 0.70 | -9.4% | MTF (4h squeeze + 1h entry) |
| ~~BTCLeaderBreak~~ | cross-pair (parent) | 0.88 | | killed r15 (fork dominated) |
| ~~MACDMomentumMTF~~ | momentum | 0.41 | | killed r13 (plateau) |
| ~~MeanRevBBClean~~ | mean-reversion | -0.24 | | killed r6 |

**5 paradigms tested, 3 with positive edge.** Mean-reversion (familiar from v0.1.0/v0.2.0 as positive-edge) did NOT survive in the 5-pair universe — its v0.2.0 recipes didn't transfer. Momentum (v0.2.0's winner) plateaued at a lower ceiling than v0.2.0's 0.67. Breakout (failed in v0.2.0 as TrendDonchian) SUCCEEDED here when combined with cross-pair signal — the leading strategy of the run.

---

## Three-version comparison

| | v0.1.0 | v0.2.0 | v0.3.0 |
|---|---|---|---|
| Architecture | single-file mutation | multi-strategy (cap 3) | multi-strategy + MTF + multi-asset |
| Rounds | 99 | 81 | 39 |
| Events | 99 | 209 | 120 |
| Headline Sharpe | 1.44 (*) | 0.67 | **1.07** |
| "True edge" Sharpe | **0.19** | 0.67 | 1.07 |
| Goodhart attempts | 3 (self-reversed) | 0 | 0 |
| Fork events | 0 | 0 | 1 |
| Kill events | 0 | 3 | 3 |
| Paradigms tested | 1 | 5 | 5 |
| Paradigms with clean positive edge | 1 | 3 | 3 |
| Structural cross-paradigm findings | 0 | 2 | 6+ |
| Per-asset findings possible | No | No (aggregated only) | **Yes** |

(*) v0.1.0's 1.44 came from `exit_profit_only` in a bull regime. Agent's own sanity check at round 95 revealed true-edge Sharpe = 0.19. See v0.1.0 retrospective.

**Read the "true edge" row, not the headline row.** v0.3.0's 1.07 is strictly the strongest result the project has ever produced with zero oracle gaming.

---

## Phase-by-phase story

### Phase 1 — Setup (r0)

Agent created 3 strategies, all using MTF:
- **MTFTrendStack**: 1d EMA200 regime + 4h EMA trend + 1h pullback entry. Started at **Sharpe 0.74 on round 0** (already above v0.2.0's peak).
- **BTCLeaderBreak**: BTC 4h Donchian breakout triggering entries on ALL pairs — first cross-pair strategy in project history.
- **MeanRevBBClean**: pure 1h BB bounce, deliberately as null baseline to test whether v0.2.0's MR recipes transfer.

Per-pair reporting IMMEDIATELY produced unexpected structure: MTFTrendStack Sharpe distributed 0.42 (SOL) to -0.17 (BTC). **v0.2.0's "trend caps at 0.40" was BTC/ETH-universe artifact; trend actually works strongly on SOL/AVAX.**

### Phase 2 — MeanRev failure cascade (r1–r5)

Three evolutions of MeanRevBBClean, applying v0.2.0 lessons sequentially:
- r1: +1d regime gate → pf WORSE (filter cuts valid bounces)
- r2: shallow-touch + volume → Sharpe -0.95 → -0.25 (lessons transfer)
- r3: +BTC 1d cross-pair gate → no change (regime redundancy finding)

Critical r3 diagnosis:

> *"In this 2023-25 bull period, BTC daily strength and per-pair daily strength are co-incident — adding the BTC 1d gate is redundant with each pair's own 1d EMA200 gate. **To get cross-pair differentiation we'd need either (a) finer TF (4h BTC trend diverges more from 1d) or (b) a regime-mix sample.**"*

This finding directly motivates v0.4.0: **regime diversity is the binding constraint for cross-pair signals to matter**.

### Phase 3 — MACDMomentumMTF: v0.2.0 reinterpretation (r6–r13)

r6: MeanRev killed (plateau at -0.24), MACDMomentumMTF created — **testing whether v0.2.0's MACD winner reproduces in the 5-pair universe**.

Result: peak Sharpe 0.41, below v0.2.0's 0.67 despite identical MACD 12/26/9 + MACD>0 + regime + ATR + RSI stack. Three optimization attempts (MA20 strength gate, faster MACD periods, faster EMA periods) all failed. Agent's kill note at r13:

> *"v0.2.0's 0.67 may have come from BTC/ETH-only-tuning that doesn't generalize."*

**This reinterprets v0.2.0's headline peak**: momentum paradigm isn't 0.67-capable in general; it was 0.67-capable on the specific 2-pair universe v0.2.0 ran on. Paradigm quality claims need asset-basis caveats.

See `versions/0.2.0/errata.md` (to be added) for the formal correction.

### Phase 4 — First fork in project history (r13–r15)

r13 simultaneously: kill MACDMomentumMTF + fork BTCLeaderBreak → BTCLeaderBreakX. Fork changed TWO things at once (Donchian 20→15, exit SMA50→SMA20). Result: Sharpe 0.88 → **0.54** (significantly worse).

r14: agent isolated by reverting ONE of the two changes (exit back to SMA50, kept Donchian-15). Result: **0.54 → 0.93** (+72%).

> *"Of the two changes, the SMA20 exit was the entire culprit — Donchian-15 entry alone is actually SUPERIOR to Donchian-20. Two-variable fork + one-at-a-time-rollback isolated the cause cleanly."*

This is **textbook controlled experimental method** executed autonomously. v0.1.0/v0.2.0 showed isolation via revert-one-parameter-at-a-time; v0.3.0 extended this to revert-one-of-two-changes-in-a-fork. The pattern is compound: **fork to preserve known-good, test risky compound change, isolate via selective revert**.

r15: kill parent BTCLeaderBreak (dominated by fork on every metric), create VolBBSqueeze (5th paradigm). Full strategy rotation complete.

### Phase 5 — Peak push to 1.07 (r18–r34)

BTCLeaderBreakX pushed from 0.93 to 1.07 via sequential bracket optimization:
- r18: local-volume threshold 1.2x → 1.5x (tighter conviction) — accepted
- r21-22: BTC ATR threshold 1.0→1.2 — reverted
- r26: drop redundant ema9>ema21 state check — kept (simpler is better reflex)
- r27-29: Donchian 15 → 13 → 10 — **each tightening improved** (final 1.07 at Donchian-10)
- r34-35: local-vol 1.5 → 1.7x → reverted (1.5 is sweet spot)

**First clean-edge Sharpe > 1.0 in project history** at r28-29, locked in at r34-35 peak 1.07.

### Phase 6 — VolBBSqueeze development + plateau validation (r16–r39)

VolBBSqueeze created r15 at Sharpe 0.21 evolved to peak 0.70:
- r16: SMA50 exit (mirrors BTCLeaderBreakX finding) → 0.21 → 0.70
- r23: squeeze threshold q25→q33 (looser) — kept
- r24-25: cross-pair BTC-squeeze confirmation → failed + reverted
- r33, r39: BB period bracket tests → default 20 confirmed best

---

## Five structural cross-paradigm findings

### Finding 1: Cross-pair volume asymmetry (Local >> Signal-source)

For strategies where signal-pair ≠ trade-pair (like BTCLeaderBreakX), volume confirmation on the **trade pair** vastly outperforms volume on the **signal-source pair**. Agent's mechanism:

> *"Local volume = 'the local market is participating'; signal-source volume = 'the macro driver is active' but says nothing about whether THIS pair will follow."*

This finding is IMPOSSIBLE to produce without both cross-pair affordance AND per-pair reporting. It's the most v0.3.0-specific insight in the run.

### Finding 2: "Ride the move" vs "manage the trend" — exit semantics asymmetry

Patient exit (slow SMA crossover) helps:
- Breakout paradigm (BTCLeaderBreakX SMA50 exit)
- Volatility paradigm (VolBBSqueeze SMA50 exit)

But hurts:
- Trend-following paradigm (MTFTrendStack prefers responsive EMA-cross exit)

Agent's mechanism:

> *"'Ride the move' paradigms benefit from patience (the move IS the alpha); trend-following alpha lives in responsive position management (exit when trend is breaking)."*

This is a **paradigm-theory statement, not a parameter rule**. Different paradigm families have different alpha sources, therefore different exit semantics.

### Finding 3: Default parameters are best (with one exception)

Default indicator parameters are local optima on 1h crypto for:
- Trend (EMA 9/21)
- Momentum (MACD 12/26/9)
- Volatility (BB 20)

**Exception: Breakout (Donchian tightening from 20 → 10 IMPROVED results).**

Theory: "channel-break" indicators reward tighter channels because break events become higher-signal. "Smoothing" indicators (EMA, MACD) become noisier when accelerated. Different information extraction mechanisms → different parameter sensitivities.

### Finding 4: Volume filter generalization is stack-size-dependent

v0.2.0 claimed volume filter was universally helpful across paradigms. v0.3.0 refines: volume filter helps when filter stack is LIGHT (few other conditions); when stacked on top of regime + ATR + TF + RSI filters, adding volume causes selection-bias on already-rare entries, DEGRADING results.

Observed across 3 strategies (MTFTrendStack, MACDMomentumMTF, VolBBSqueeze): all three showed "universal volume helper" claim collapse when applied to multi-filter stacks.

### Finding 5: Cross-pair macro gate is regime-dependent

BTC 1d EMA200 as macro strength filter on MeanRevBBClean had ZERO effect in this run. Agent's diagnosis:

> *"In this 2023-25 bull period, BTC daily strength and per-pair daily strength are co-incident."*

Implication: **for cross-pair macro signals to matter, the regime sample needs divergent periods** (e.g., 2022 winter where BTC, ETH, SOL, alts diverged violently). Single-regime data compresses the cross-pair signal to uselessness.

This is a **direct v0.4.0 pointer**: expand timerange to include 2021-2022 to test regime-mixed cross-pair utility.

---

## v0.3.0 reinterprets v0.2.0

Two specific corrections worth noting on v0.2.0's retrospective:

1. **v0.2.0 MACDMomentum Sharpe 0.67 should be read as "on BTC/ETH"**, not as paradigm-robust. v0.3.0's 5-pair test shows the same stack topping at 0.41. v0.2.0's retrospective characterized momentum as the leading paradigm; v0.3.0's evidence suggests it was the leader on that particular universe.

2. **v0.2.0's "volume filter is universal across paradigms" finding is narrower than stated.** It's universal-when-filter-stack-is-light, not universal-period.

An `errata.md` addition to `versions/0.2.0/` would be appropriate. Not part of this archive PR (archives are immutable by convention) — recommend a separate PR that adds `errata.md` with cross-reference to this retrospective's Finding 4.

---

## Agent behavior observations

**Fork discipline** — The project's first fork happened in v0.3.0, and it was used correctly: applied to a KNOWN-GOOD strategy (BTCLeaderBreak at 0.88) that agent wanted to test a risky compound change on. Fork immediately resulted in degradation (0.88 → 0.54), which agent recovered via isolation experiment rather than abandoning (r14). Parent was killed only after fork proved strictly dominant. This is the canonical fork-then-replace-parent pattern.

**Zero Goodhart** — Third consecutive run with no Sharpe-up-while-profit-down signature. Agent's sanity-check reflexes continue to hold. New in v0.3.0: per-pair reporting adds another dimension where gaming would show (a Goodhart move typically has same-direction jumps on ALL 5 pairs, flagging non-edge mechanism).

**Explicit v0.2.0 retrospective citation** — Agent consistently cited specific v0.2.0 findings ("v0.2.0 r2 lesson", "v0.2.0 r67 recipe", "v0.2.0's 0.67 ceiling") during reasoning. The archived retrospectives are being used as LOAD-BEARING context. This validates the versions/ architecture — it's not just historical, it's active reasoning substrate.

**Stopped at r39 (not 80-100)** — Per-round information density in v0.3.0 is higher than v0.2.0 (per-pair × MTF × cross-paradigm comparison surfaces). Agent likely hit context saturation. A future orchestrator (external, resetting context per round — "route B" from earlier design work) would remove this cap. Noted for v0.5.0+ roadmap.

---

## Limitations carried forward

- **Single regime** (2023-2025 bull). v0.3.0 found that cross-pair macro gates don't help in single-regime data — this is now the BINDING limitation for v0.4.0 to address.
- **No benchmark** (buy-and-hold still not in oracle). Sharpe 1.07 is good in absolute terms but we don't have a BaH comparison on this 5-pair universe. v0.4.0 candidate.
- **Small per-pair trade counts** (40-70 per pair / 3 years on the leader). Sharpe CI wide at these samples.
- **Stopped early** — 39 rounds vs v0.2.0's 81. External orchestrator would allow deeper exploration.

---

## Recommended v0.4.0 direction

Given the findings above, v0.4.0 should do exactly ONE thing: **expand the timerange to include 2021-2022** (regime diversity). Concrete rationale:

1. Finding 5 explicitly flagged cross-pair macro utility as regime-blocked
2. All three alive strategies are unvalidated in bear/crash regimes (2022 winter)
3. Benchmark (BaH) becomes meaningful only over regime-mixed periods (BaH in pure bull = +500%, BaH including 2022 = ~+100%, closer to our strategies' clean edge)
4. Testing strategy robustness across regimes is the classical "out-of-sample" risk check — currently absent

What NOT to add in v0.4.0 (defer to v0.5.0+):
- More pairs (current 5 is working, don't add dimensions)
- Per-pair customization (complex, wait for regime-diverse baseline first)
- Shorting / pairs trading (changes backtest semantics)
- External orchestrator for context reset (infrastructure work, separate track)

v0.4.0's retrospective should specifically re-test Finding 5 (cross-pair macro gate) in regime-mixed data. If the finding holds across regimes, it's a null result; if it flips (BTC 1d becomes useful when regimes diverge), that's a major v0.3.0 → v0.4.0 insight.

---

## User reflections

*(blank — to be filled in by the human. My analysis emphasizes what I think stood out; the human's complement belongs here, including things I may have over-weighted, wrongly framed, or missed entirely.)*
