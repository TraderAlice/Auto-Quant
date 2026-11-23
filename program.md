# Auto-Quant v0.5.0 — True Portfolio Optimization + Cross-Regime Risk Decomposition

This is an autonomous quantitative research loop where the LLM evolves a
**multi-strategy crypto spot portfolio** (up to 3 active strategies) that can:
- combine signals across **multiple timeframes** (`1h` base + `4h` + `1d`)
- reference **multiple assets** (5-pair universe: BTC, ETH, SOL, BNB, AVAX)
- declare their **own asset basket** (`pair_basket`)
- evaluate automatically across **4 canonical market regimes** (`bull_2021`,
  `winter_2022`, `recovery_23_25`, `full_5y`)
- use **dynamic position sizing** via `custom_stake_amount`
- optimize both **single-strategy risk quality** AND **combined cross-strategy
  portfolio synergy** (`PORTFOLIO_SUMMARY`)

## What changed in v0.5.0 (and why)

Prior versions (v0.1.0 → v0.4.1) evaluated up to 3 strategies completely in
isolation and relied on FreqTrade's per-trade `sharpe` formula (which divided
daily mean return by *per-trade* standard deviation, making it incomparable to
daily Buy-and-Hold Sharpe and punishing upside breakouts). v0.4.1 also surfaced
two structural bottlenecks: a flat `+20%` winter profit floor that was
physically unreachable in a `-75%` spot-only bear market, and "early Pareto
lock" where a killed single-pair strategy permanently dominated later paradigms
on 2D `(sharpe, max_dd)`.

**v0.5.0 upgrades the oracle (`run.py`) along three axes:**

1. **True Daily Equity-Curve Portfolio Analytics (per strategy & regime)**
   - **`daily_sharpe` & `daily_sortino`**: annualized ($\sqrt{365}$) from the
     reconstructed daily equity curve — directly apples-to-apples with
     `bah_sharpe`, with `daily_sortino` avoiding unfair penalties on upside
     breakout volatility.
   - **Tail & Underwater Pain**: `cagr_pct`, `calmar`, `ulcer_index`,
     `martin_ratio` ($\text{CAGR} / \text{UlcerIndex}$), and `max_dd_days`
     (longest underwater streak).
   - **Benchmark OLS Decomposition vs Equal-Weight BaH**: `alpha_ann_pct`
     (annualized Jensen's $\alpha$), `beta` (passive market exposure), and
     `info_ratio`. Separates real timing/selection alpha from "holding 10%
     passive crypto beta".
   - **Capital Utilization & Breadth**: `avg_pos_pct`, `time_in_market_pct`
     (exact merged interval fraction with $\ge 1$ open trade), `capital_util_pct`,
     and `effective_pairs` ($1 / \sum w_i^2$ inverse HHI of per-pair $|\text{PnL}|$).

2. **Calibrated Multi-Objective Gates (per strategy `SUMMARY`)**
   - **`regime_return_gate`**: regime-conditional return bar:
     - Bull / Recovery windows (`bah_profit_pct >= 0`, < 4y): `profit >= +10%`
     - Full 5y window (`>= 4y`): `profit >= +20%`
     - Bear / Winter windows (`bah_profit_pct < 0`, e.g. `winter_2022`): capital
       preservation `profit >= -2.0%` AND strictly beating `bah_profit_pct`
   - **`exposure_gate`**: `worst_avg_pos_pct >= 5.0%` across ALL traded regimes
     AND `full_time_in_market_pct >= 2.0%` (blocks both tiny-stake Sharpe
     gaming and 2-trades-in-5-years cash-sitting).
   - **`pareto_dominated_by` (3D + Kill-Aware)**: checks 3D dominance on
     `(robust_sharpe, full_cagr_pct, worst_dd_pct)` and distinguishes live
     dominators from archived/killed strategies (`none_active`).

3. **Cross-Strategy `PORTFOLIO_SUMMARY` (Portfolio Manager Layer)**
   - Combines all active strategies ($1..3$ slots) into an equal-weight
     daily-rebalanced portfolio (`PORTFOLIO_EQ`) across all common regimes:
   - **`portfolio_robust_sharpe`** & **`portfolio_robust_sortino`**: worst-regime
     daily Sharpe / Sortino of the combined lineup (**co-headline metric!**).
   - **`diversification_gain`**: `portfolio_robust_sharpe - mean(individual robust_sharpe)`
     — directly rewards combining low-correlation paradigms.
   - **Correlation Diagnostics & `diversification_gate`**: `pairwise_daily_corr`
     and `pairwise_tail_corr` (correlation on loss days), gated at
     `max_pairwise_corr < 0.60`.
   - **Leave-One-Out Marginal Contribution**: `marginal_robust_sharpe` and
     `marginal_full_sharpe` per strategy (`[ACCRETIVE]` vs `[DILUTIVE]`). A
     modest standalone strategy that hedges winter drawdowns for the rest of
     the portfolio shows up immediately as `[ACCRETIVE]`.

---

## Setup

To set up a new experiment:

1. **Agree on (or create) a run branch**: e.g. `git checkout -b autoresearch/<tag>`
   if not already on an experiment branch.
2. **Read the in-scope files**:
   - `README.md` — project history
   - `config.json` — fixed FreqTrade config (`5` pairs, `1h` base, `0.1%` fee). Do not modify.
   - `prepare.py` — data check/download. Do not modify.
   - `run.py` — the v0.5.0 portfolio & multi-regime oracle. Do not modify.
   - `user_data/strategies/_template.py.example` — strategy skeleton.
   - `versions/0.4.1/retrospective.md` — key findings from prior runs.
3. **Verify data exists**: Check that all 15 feather files exist under
   `user_data/data/` (`{BTC,ETH,SOL,BNB,AVAX}_USDT-{1h,4h,1d}.feather`).
4. **Initialize `results.tsv`** (if it doesn't already exist) with the 10-column
   tab-separated header:
   ```
   commit	event	strategy_name	robust_sharpe	robust_sortino	cagr_pct	max_dd	alpha_pct	marginal_sharpe	note
   ```
   Do NOT commit `results.tsv` — it is gitignored so history survives `git reset`.
5. **Create 2–3 starting strategies** under `user_data/strategies/<YourName>.py`:
   - Class name MUST match filename stem.
   - Fill all 6 docstring metadata fields (`Paradigm`, `Hypothesis`, `Parent`,
     `Created`, `Status`, `Uses MTF`).
   - **Each starter MUST target a genuinely orthogonal paradigm** (e.g.
     mean-reversion + MTF trend/breakout + volatility/regime-rebound) so
     `PORTFOLIO_SUMMARY` starts with low `pairwise_daily_corr` and positive
     `diversification_gain`.
   - Leave `test_timeranges` unset (so all strategies inherit the 4 canonical
     regimes `bull_2021`, `winter_2022`, `recovery_23_25`, `full_5y` and align
     in `PORTFOLIO_SUMMARY`).
6. **Confirm and go** (if running interactively with a human; if launched in
   autonomous/non-interactive mode, proceed directly into the experiment loop
   without pausing!).

---

## Experimentation Rules

### What you CAN do
- Create, modify (`evolve`), copy (`fork`), or delete (`git rm`, `kill`)
  strategy `.py` files under `user_data/strategies/` (not prefixed with `_`).

### What you CANNOT do
- Modify `prepare.py`, `run.py`, `config.json`, or `_template.py.example`.
- Add new Python dependencies or call `freqtrade` CLI directly — always run
  `uv run run.py`.
- Exceed **3 active strategies** at any time.
- Request timeframes other than `1h`, `4h`, `1d` or pairs outside the 5-pair
  whitelist (`BTC/USDT`, `ETH/USDT`, `SOL/USDT`, `BNB/USDT`, `AVAX/USDT`).

### Affordances Recap

1. **Multi-timeframe & Cross-Asset (`@informative`)**:
   - `@informative("4h")` / `@informative("1d")` merges look-ahead-safe
     columns (`rsi_4h`, `ema200_1d`).
   - `@informative("1h", "BTC/USDT")` merges cross-pair columns
     (`btc_usdt_rsi_1h`). Remember to set `startup_candle_count` high enough
     for slow higher-TF indicators.
2. **Dynamic Position Sizing (`custom_stake_amount`)**:
   - Scale `proposed_stake` within `[min_stake, max_stake]` for volatility
     targeting, conviction weighting, or regime sizing.
   - Lesson from v0.4.1: multiplicative sizing composition works when signals
     are independent/positively correlated, and inverse-amplifies when
     negatively correlated!
3. **Strategy-Declared Basket (`pair_basket`)**:
   - Optional subset of the 5 pairs (e.g. `pair_basket = ["BNB/USDT"]` or
     alts-only). You can also build per-pair-conditional paradigms inside one
     strategy using `metadata["pair"]`.

### Hard Lifecycle Rules

1. **Hard cap — max 3 active strategies** in `user_data/strategies/`.
2. **Stagnation gate — max 3 consecutive `stable` rounds**: if a strategy sits
   `stable` for 3 consecutive rounds, round 4 MUST `evolve`, `fork`, or `kill` it.
3. **Every round touches $\ge 1$ strategy.**

---

## Reading `run.py` v0.5.0 Output

Quick scan of strategy summaries + portfolio rollup:
```bash
awk '/timerange_label: *(SUMMARY|PORTFOLIO_SUMMARY)/,/^$/' run.log
```
Full blocks (including per-regime `bull_2021` / `winter_2022` / `recovery_23_25` / `full_5y`):
```bash
awk '/^---$/,/^$/' run.log
```

### Key metrics to watch

- **Portfolio Level (`PORTFOLIO_SUMMARY`) — Primary Optimization Target:**
  - `portfolio_robust_sharpe` & `portfolio_robust_sortino`: push BOTH up!
  - `diversification_gain`: positive means your strategies genuinely complement
    each other across regimes.
  - `pairwise_daily_corr` & `pairwise_tail_corr`: keep `max_corr < 0.60`
    (`diversification_gate: PASS`). High tail correlation means two strategies
    bleed on the exact same days.
  - `marginal_contributions`: check whether each slot is `[ACCRETIVE]` or
    `[DILUTIVE]` on `marginal_robust_sharpe` and `marginal_full_sharpe`.
- **Strategy Level (`SUMMARY`):**
  - `robust_sharpe` & `robust_sortino` (worst-regime daily Sharpe/Sortino).
  - `full_cagr_pct`, `full_calmar`, `full_martin_ratio` (CAGR / Ulcer Index).
  - `full_alpha_ann_pct` & `beta`: verify positive $\alpha$ rather than disguised
    low-$\beta$ passive exposure.
  - Gates: `regime_return_gate`, `exposure_gate`, `pareto_dominated_by`.

---

## Logging to `results.tsv`

After each round, append:
1. **One row per active/killed strategy** (`create | evolve | stable | fork | kill`)
2. **One `portfolio` row** (`event = portfolio`, `strategy_name = PORTFOLIO_EQ`)
   recording the combined lineup's metrics (`robust_sharpe = portfolio_robust_sharpe`,
   `robust_sortino = portfolio_robust_sortino`, `cagr_pct = portfolio_full_cagr_pct`,
   `max_dd = portfolio_worst_dd_pct`, `alpha_pct = portfolio_alpha_ann_pct`,
   `marginal_sharpe = diversification_gain`).

10 tab-separated columns:
```
commit	event	strategy_name	robust_sharpe	robust_sortino	cagr_pct	max_dd	alpha_pct	marginal_sharpe	note
```
For `kill` rows, use `-` for numeric columns and explain *why* it was killed in
`note`. Always write rich, analytical notes citing regime dispersion, $\alpha/\beta$,
gate status, and portfolio correlation/marginal impact.

---

## The Experiment Loop

1. **Inspect state**: read tail of `results.tsv`, check active strategies,
   stagnation counts, gates, and which slot is `[DILUTIVE]` or bottlenecking
   `portfolio_robust_sharpe`.
2. **Formulate a sharp hypothesis** and choose this round's action (`create`,
   `evolve`, `fork`, `kill`, or combination within the 3-slot cap).
3. **Edit strategy code** under `user_data/strategies/`.
4. **Commit**: `git commit -am "<concise round summary>"`
5. **Run oracle**: `uv run run.py > run.log 2>&1`
6. **Inspect results**: check for `status: ERROR` first; read per-regime blocks,
   `SUMMARY`, and `PORTFOLIO_SUMMARY`.
7. **Append rows to `results.tsv`** (all strategies + `PORTFOLIO_EQ` row).
8. **Keep or rollback**: if an evolution degraded both standalone `robust_sharpe`
   AND `portfolio_robust_sharpe` (and wasn't an informative stepping stone),
   revert that change (`git checkout HEAD~1 -- user_data/strategies/<File>.py`
   or `git reset --hard HEAD~1` if the whole round regressed — `results.tsv`
   stays intact because it is gitignored!).
9. **Repeat continuously** without stopping to ask the human!

### Keep vs. Kill Criteria (v0.5.0)

Keep / evolve a strategy when:
1. It is **`[ACCRETIVE]`** to `portfolio_robust_sharpe` (or `marginal_full_sharpe`
   with positive `robust_sharpe`), AND `diversification_gate` passes (`corr < 0.60`).
2. `robust_sharpe > 0` across all 4 regimes (or rapidly trending toward `> 0`
   within 1–2 evolutions) with strong `robust_sortino` and `martin_ratio`.
3. `regime_return_gate` and `exposure_gate` PASS (or you have a concrete next
   evolution aimed at clearing the failing gate).
4. Positive annualized $\alpha$ (`full_alpha_ann_pct > 0`).

Kill / replace a strategy when:
- `robust_sharpe < 0` persistently after targeted fixes (structural winter bleed).
- Strongly correlated (`corr >= 0.60`) with a superior active strategy AND
  `[DILUTIVE]` on marginal portfolio Sharpe.
- Dominated on 3D `(robust_sharpe, cagr_pct, max_dd)` by an active strategy in
  the same paradigm.
- Stagnant for 3 rounds with no untested mechanism left.

### Goodhart Watch

Never use `exit_profit_only=True`, micro-ROI clipping (`minimal_roi` < 1% to
compress return variance), or sub-5% stake shrinking. Watch `alpha_ann_pct`,
`cagr_pct`, `exposure_gate`, and `regime_return_gate` alongside Sharpe: real
improvements lift risk-adjusted return AND economic return/portfolio synergy
together.
