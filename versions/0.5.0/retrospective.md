# v0.5.0 — Retrospective

**Run**: 5-pair crypto portfolio (`BTC/ETH/SOL/BNB/AVAX`) on `1h` base + `4h`/`1d` informative across 4 canonical regimes (`bull_2021` / `winter_2022` / `recovery_23_25` / `full_5y`)
**Agent & Harness**: `omp` (Oh My Pi v19.1.0) + `opencode-go/muse-spark-1.3-contributor` (`thinking=high`, 20-minute wall-clock sprint)
**Branch / Tag**: `autoresearch/nov22-v0.5.0-muse` / `v0.5.0`
**Converged Commit**: `53b6840` (Round 12)
**Portfolio Robust Peak Commit**: `f816be0` (Round 6, `portfolio_robust_sharpe = 1.1626`, `sortino = 2.0004`, `diversification_gain = +0.7896`)

---

## Headline — First 3/3 All-Gate-Passing Portfolio & Market-Neutral Alpha

v0.5.0 upgraded the evaluation oracle (`run.py`) from isolated per-trade strategy Sharpe to **true daily equity-curve portfolio analytics + cross-strategy `PORTFOLIO_SUMMARY`**. Over a 20-minute autonomous run (13 rounds R0–R12), `Muse Spark 1.3` produced **the first 3-strategy lineup in project history where every active slot passes all multi-objective gates simultaneously, sits on the non-dominated 3D Pareto frontier, and contributes positively (`[ACCRETIVE]`) to the combined portfolio**:

| Regime | `PORTFOLIO_EQ` Daily Sharpe | Sortino | Return | Max DD | Martin Ratio | Equal-Weight BaH |
|---|---:|---:|---:|---:|---:|---|
| **`bull_2021`** | **2.8267** | 8.0100 | +20.07% | -2.10% | 31.68 | Sharpe 3.28 / +1741.8% |
| **`winter_2022`** *(binding)* | **0.9741** | 1.6485 | **+3.46%** | **-1.70%** | 4.92 | Sharpe -1.43 / **-79.0%** |
| **`recovery_23_25`** | **1.4238** | 3.1597 | +18.27% | -2.84% | 4.49 | Sharpe 1.16 / +357.9% |
| **`full_5y`** | **1.7146** | **3.9555** | **+46.92%** (CAGR 7.99%) | **-2.84%** | **7.42** | Sharpe **1.15** / DD -82.1% |

Key portfolio properties at `53b6840`:
- **Outperforms 5-year Buy-and-Hold on risk-adjusted return by +49%** (`1.7146` vs `1.1482` daily Sharpe) while compressing max drawdown from `-82.14%` to **`-2.84%`** (`Calmar = 2.81`, `Martin Ratio = 7.42`).
- **Pure $\alpha$, zero passive $\beta$**: OLS benchmark regression yields **`+8.00%` annualized $\alpha$** at **`beta = 0.0011`**.
- **Strictly negative tail correlation on loss days**: pairwise daily correlations are `+0.019`, `+0.075`, `-0.002` (`diversification_gate: PASS`), while drawdown-day tail correlations are **`-0.194`, `-0.307`, `-0.390`** — lifting `portfolio_robust_sharpe` by **`+0.3807`** above the average component (`0.9741` vs `0.5934`).

---

## Final 3-Slot Lineup (`53b6840`)

| Strategy | Paradigm & Basket | `robust_sharpe` | `robust_sortino` | `full_cagr` | `worst_dd` | Marginal (`robust` / `full`) | Gates & Frontier |
|---|---|---:|---:|---:|---:|---|---|
| **AltBbMeanRevert** | Alts BB-lower MR + 4h/1d trend gates + RSI sizing (`SOL, AVAX, BNB`, eff `2.74/3`) | 0.6054 | 0.9095 | 8.75% | -5.48% | `+0.1622` / `+0.4708` `[ACCRETIVE]` | PASS / PASS / 3D Frontier |
| **BnbMeanRevert** | BNB RSI<25 MR + RSI sizing + **1d-regime-conditional exit** (`BNB`, eff `1.00/1`) | **0.6441** | 1.0717 | 5.62% | **-4.03%** | **`+0.1805`** / `+0.2353` `[ACCRETIVE]` | PASS / PASS / 3D Frontier |
| **MajorsBreakout** | Majors Donchian-48 breakout + 4h EMA & 1d SMA20 confluence (`BTC, ETH`, eff `1.89/2`) | 0.5307 | **1.2355** | **9.05%** | -6.47% | `+0.1415` / `+0.0886` `[ACCRETIVE]` | PASS / PASS / 3D Frontier |

---

## Phase-by-Phase Evolution Trajectory

1. **R0 → R1 (`5a52f97` → `ff6476b`) — Portfolio marginal attribution catches falling-knife drag immediately**:
   - `AltsCrashRebound` bled `-42%` in `winter_2022` (`marginal_robust_sharpe = -2.36 [DILUTIVE]`), dragging `PORTFOLIO_EQ` to `-1.44`. Killed in R1 and replaced with `AltBbMeanRevert`.
2. **R2 → R3 (`30e6db1` → `255df36`) — Daily trend gate + deeper RSI threshold flip portfolio strongly positive**:
   - Adding `close > sma20_1d` (R2) and tightening `RSI < 30` (R3) on `AltBbMeanRevert` flipped it from `[DILUTIVE]` to `[ACCRETIVE]`, propelling `portfolio_robust_sharpe` from `-0.53 → +0.50 → +1.08` (`diversification_gain = +0.61`).
3. **R4 → R7 (`8fd86a2` → `7211f70`) — Portfolio marginal Sharpe prevents premature slot destruction + clean ablation**:
   - Testing a shallow-pullback leg on `BnbMeanRevert` hurt standalone recovery (`-0.02` robust), but `PORTFOLIO_SUMMARY` showed `+0.41` marginal robust Sharpe from winter hedging (`portfolio_robust_sharpe` peaked at **`1.1626`** in R6 after `MajorsBreakout` added `1d SMA20` confluence). R7 ablation cleanly reverted the shallow leg back to pure `RSI < 25`.
4. **R9 → R11 (`8b541a7` → `d7cdf99`) — Regime-conditional exit resolves the counter-trend exit trade-off**:
   - R9 proved unconditional slow exits (`RSI > 65`) destroy MR (`robust 0.38 → -0.06`, rolled back in R10).
   - R11 synthesized the run's breakthrough: **hold for `RSI > 65` when `close > sma20_1d` (uptrend), exit fast at `RSI > 55` otherwise**. On the exact same 80 trades, recovery jumped `+4.78% → +10.35%` (clearing `regime_return_gate`), winter held `+6.96%`, and standalone `robust_sharpe` jumped **`0.3808 → 0.6441`**.
5. **R11 → R12 (`68e9759` → `53b6840`) — Rejecting Pareto-negative sizing inflation**:
   - Breakout-strength sizing on `MajorsBreakout` lifted CAGR (`9.05% → 16.22%`) at the expense of DD (`-6.47% → -11.29%`) and `robust_sharpe` (`0.53 → 0.48`). Reverted in R12, sealing the 3/3 gate-passing 3D Pareto lineup.
