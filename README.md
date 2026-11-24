# Auto-Quant

> LLM-native autonomous quant research loop. Karpathy's
> [autoresearch](https://github.com/karpathy/autoresearch) pattern applied to
> FreqTrade strategies on a 5-pair crypto universe (BTC, ETH, SOL, BNB, AVAX)
> across 1h / 4h / 1d timeframes.

The idea: give an LLM agent a FreqTrade backtest harness and a single strategy
file. The agent modifies the strategy, runs a backtest, checks if the result
improved, keeps or discards, and repeats. Over many iterations the hope is to
observe which patterns the LLM actually finds useful on this asset pair. The
**loop lives in `program.md`** — not in any orchestrator — and is executed by
whatever LLM agent you point at the repo.

This is a prototype to validate whether Karpathy's autoresearch pattern
transfers to quant research. The success metric is "did the loop run and
produce an interpretable `results.tsv`", **not** "did we find a profitable
strategy". Nothing in this repo is a recommendation to trade real capital.

## A run in one picture

![Sharpe frontier — v0.1.0 run](sharpe-frontier.png)

One dot per backtest over 99 experiments on BTC/USDT + ETH/USDT @ 1h. Green
dots were kept by the agent, gray were discarded. The red line is the
running best of *kept only* — it plateaus at Sharpe 1.44, **not** at the
Sharpe-18 cluster on the right. Those high-Sharpe runs are gray because the
agent itself identified them as oracle-gaming (ROI-clipping that compressed
return variance without improving real return) and retroactively discarded
them. Full write-up in
[`versions/0.1.0/retrospective.md`](versions/0.1.0/retrospective.md).

## How it works

Four things that matter:

- **`config.json`** — minimal FreqTrade exchange/market config, fixed during
  runs. Configures Binance USDT-M perpetual futures (`trading_mode: "futures"`,
  `margin_mode: "isolated"`, 5 pairs with `:USDT` suffix), `1h` base timeframe,
  and dry-run wallet. The agent does not touch this.
- **`prepare.py`** — one-time data download from Binance via FreqTrade's Python
  API. Reads `DATA_TIMERANGE` from `run.py` and downloads `1h`, `4h`, and `1d`
  futures OHLCV plus `1h` `mark` and `funding_rate` for all configured pairs
  (supports `--erase`). The agent does not touch this.
- **`run.py`** — in-process **portfolio & multi-regime oracle** (v0.5.2) and
  single source of truth for bench constants (`BENCH_FEE`, `MAX_LEVERAGE`,
  `DATA_TIMERANGE`, `SPLIT_DATE`, editable at the top of `run.py` before a run).
  Discovers every `.py` under `user_data/strategies/` (skipping `_` files),
  runs FreqTrade's `Backtesting` on the training split (`uv run run.py`,
  `< SPLIT_DATE`: `bull_2021`, `winter_2022`, `recovery_23_25`, `full_5y`) or
  post-run OOS test split (`uv run run.py --oos`, `>= SPLIT_DATE`), enforces
  `MAX_LEVERAGE` (`1.0x`), reconstructs true daily **Mark-to-Market (MTM)**
  equity curves (realized PnL incl. funding + fee-inclusive EOD unrealized PnL
  of all open long/short positions at `1d` UTC closes), emits long/short +
  funding breakdowns (`sides:`), evaluates regime-calibrated + 3D kill-aware
  Pareto gates, and emits a cross-strategy **`PORTFOLIO_SUMMARY`** block
  combining all active slots (`portfolio_robust_sharpe`, `diversification_gain`,
  pairwise daily/tail correlations, and leave-one-out `marginal_robust_sharpe`
  `[ACCRETIVE]` / `[DILUTIVE]`). The agent does not touch this.
- **`user_data/strategies/`** — **the directory the agent owns**. Each `.py`
  is one strategy; up to 3 active at a time. Agent creates / evolves / forks
  / kills strategies here. Strategies evaluate on 1h base across the 5-pair
  portfolio (or declared `pair_basket`), and can opt into 4h/1d context AND/or
  cross-pair signals via FreqTrade's `@informative` decorator (see
  `_template.py.example` for the pattern). `run.py` reports per-pair metrics
  alongside the aggregate and combined portfolio rollup.

Plus:

- **`program.md`** — the autonomous-research instructions the human points the
  LLM agent at.
- **`results.tsv`** — 10-column event log. Schema:
  `commit | event | strategy_name | robust_sharpe | robust_sortino | cagr_pct | max_dd | alpha_pct | marginal_sharpe | note`.
  Events: `create | evolve | stable | fork | kill | portfolio`. Gitignored so it
  survives `git reset --hard` — past lessons stay available even when
  experimental commits get thrown away.
- **`analysis.ipynb`** — post-hoc read: per-strategy trajectories, cap
  utilization, event distribution, note word frequency.

*Version history*:
- **v0.1.0** ([archive](versions/0.1.0/)): single-file mutation. Anchored
  on one paradigm for all 99 rounds. Headline Sharpe 1.44 was mostly
  oracle gaming (true-edge 0.19). See [retrospective](versions/0.1.0/retrospective.md).
- **v0.2.0** ([archive](versions/0.2.0/)): multi-strategy (up to 3 slots).
  5 paradigms tested / 3 kept / 0 Goodhart attempts. Peak clean Sharpe
  0.67 (~3.5× better than v0.1.0's true-edge). See [retrospective](versions/0.2.0/retrospective.md).
- **v0.3.0** ([archive](versions/0.3.0/)): multi-strategy + multi-timeframe +
  multi-asset portfolio. Adds 4h + 1d informative data, expands universe to
  5 pairs (BTC/ETH/SOL/BNB/AVAX), and emits per-pair metrics. **First
  project-wide clean Sharpe > 1.0** (1.07 on BTCLeaderBreakX). Also: first
  fork event + isolation experiment. See [retrospective](versions/0.3.0/retrospective.md).
- **v0.4.0** ([archive](versions/0.4.0/)): regime extension to 2021-2025
  + dynamic position sizing. Real-edge clean Sharpe **1.122 / +232%** on
  5-year regime mix (strictly stronger than v0.3.0 on harder data). Surfaced
  the "Sharpe-as-single-oracle has a degeneracy boundary" finding and the
  cleanest sizing-vs-edge controlled experiment in the project.
  See [retrospective](versions/0.4.0/retrospective.md).
- **v0.4.1** ([archive](versions/0.4.1/)): four affordances bundled —
  `pair_basket` (strategy-declared portfolio), `test_timeranges` (multi-regime
  backtest with `robust_sharpe = min` as headline), per-timerange buy-and-hold
  benchmark, and multi-objective gates (`profit_floor`, `min_position_size`,
  `pareto_dominated_by`) flanking the headline metric. Direct response to
  v0.4.0's Sharpe-degeneracy finding. **First multi-strategy lineup with
  `robust_sharpe > 0` across all four declared regimes (bull/winter/recovery/
  full-5y) simultaneously**, but the run also surfaced an "early Pareto lock"
  pattern where the regime-robust frontier was set at round 9 by a single
  sizing ablation and never broken across the next 20 rounds. Five new
  cross-version findings + four reinforcements + two narrows of prior
  universal claims. See [retrospective](versions/0.4.1/retrospective.md).
- **v0.5.0** ([archive](versions/0.5.0/)): upgrades the oracle from isolated
  per-trade Sharpe to **true daily equity-curve portfolio analytics +
  cross-strategy `PORTFOLIO_SUMMARY`** (`daily_sharpe`, `daily_sortino`,
  `calmar`, `ulcer_index` / `martin_ratio`, OLS `alpha` / `beta` / `info_ratio`
  vs BaH, `time_in_market_pct`, `effective_pairs`, regime-calibrated return &
  exposure gates, 3D kill-aware Pareto check, pairwise daily & loss-day tail
  correlations, and leave-one-out `marginal_robust_sharpe`). Validated in a
  20-minute `omp` + `Muse Spark 1.3` sprint (13 rounds): **first 3-strategy
  lineup where 3/3 slots pass all gates on the 3D Pareto frontier**, achieving
  combined `portfolio_robust_sharpe = 0.974` (`1.163` R6 peak), 5y daily Sharpe
  **1.715** (vs 1.148 BaH) at `-2.84%` max DD, `+8.00%` annualized $\alpha$ at
  `beta = 0.001`, and negative loss-day tail correlations (`-0.19` to `-0.39`).
  See [retrospective](versions/0.5.0/retrospective.md).
- **v0.5.1** *(scaffold)*: upgrades `run.py` from close-day realized PnL to
  **true daily Mark-to-Market (MTM) equity curves** — valuing every open
  position at EOD UTC `1d` close prices (fee-inclusive, DCA/partial-exit aware)
  and reporting `mtm_dd` alongside `ft_realized_dd`. Eliminates the realized-only
  illusions around floating drawdown, near-zero `beta`, and artificial negative
  loss-day tail correlations on hold-and-pray strategies.
- **v0.5.2** *(scaffold)*: unlocks **1× unleveraged long/short trading** on
  Binance USDT-M perpetual futures (`trading_mode: "futures"`,
  `margin_mode: "isolated"`, real historical funding rates, `MAX_LEVERAGE = 1.0`
  enforced in `run.py`, plus `sides:` long/short/funding reporting) and
  centralizes bench constants (`BENCH_FEE`, `MAX_LEVERAGE`, `DATA_TIMERANGE`,
  `SPLIT_DATE`) at the top of `run.py`, with a minimal CLI: `uv run run.py`
  for the training split (`< SPLIT_DATE`) and `uv run run.py --oos` for clean
  post-run out-of-sample evaluation (`>= SPLIT_DATE`).

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- TA-Lib (the C library — installed separately from the Python binding)

## Install

```bash
# 1. Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install the TA-Lib C library
#    macOS:  brew install ta-lib
#    Linux:  see https://github.com/mrjbq7/ta-lib#dependencies
#    If native install is painful on your platform, the FreqTrade Docker
#    image ships with TA-Lib pre-built and works as an alternate runtime.

# 3. Install Python deps
uv sync

# 4. One-time data download (~a few minutes)
uv run prepare.py

# 5. Sanity check — with no strategies yet, run.py should report
#    "no strategies found" and exit. That's expected — the agent creates
#    1-3 starting strategies during setup before the first real backtest.
uv run run.py > run.log 2>&1; echo "exit=$?"
```

If step 5 prints `no strategies found...` and `exit=2`, you're ready. (An
actual backtest run only starts once the agent has created at least one
strategy file.)

## Running the agent

Open a **second** terminal (keep your editor/IDE in the first so the two
sessions don't fight over the working tree), `cd` into the repo, and start
your preferred LLM agent (Claude Code, Codex, Cursor agent, etc.). Then
prompt something like:

> Have a look at `program.md` and let's kick off a new experiment. Let's do
> the setup first.

The agent reads `program.md`, goes through setup, then enters the experiment
loop. It keeps iterating until you interrupt it or it runs out of context.

### Configuring bench parameters & running OOS evaluation (v0.5.2+)

Before starting a run, customize the 4 bench constants at the top of `run.py`
(immutable once the run begins; `prepare.py` imports `DATA_TIMERANGE` /
`SPLIT_DATE` from `run.py` directly):
- `BENCH_FEE`: per-side trading commission (default `0.001` = `0.10%`/side; e.g. `0.0005` for Binance taker or `0.002` for conservative slippage)
- `MAX_LEVERAGE`: leverage hard cap enforced by `run.py` (default `1.0`)
- `DATA_TIMERANGE`: full dataset window fetched by `uv run prepare.py` (default `"20210101-20261124"`)
- `SPLIT_DATE`: train/test cutoff date (default `"20260101"`)

After the agent finishes iterating on the training split (`uv run run.py`), evaluate the final lineup out-of-sample:

```bash
uv run run.py --oos
```

### Permissions

The loop only works if the agent can run commands without a human approving
each one — it will invoke `uv run run.py`, `git commit`, `git reset`, and
edit the strategy file hundreds of times. How you grant that depends on your
tooling:

- **Claude Code**: prefer a scoped allowlist via a project-level
  `.claude/settings.json`. See the
  [permissions docs](https://docs.claude.com/en/docs/claude-code/settings#permissions)
  for patterns like `Bash(uv run *)` and `Bash(git commit:*)`.
- **Other agents**: most have an equivalent — a config flag or settings file
  to mark specific commands or tools as pre-approved.

Read the docs and choose a permission posture you're comfortable with before
leaving a loop running unattended. The agent is pointed at a sandboxed
FreqTrade workspace and has no live-trading access (all `dry_run`), but it
does run arbitrary shell commands and write files inside this directory.

## Project structure

```
Auto-Quant/
├── README.md
├── pyproject.toml                     # uv-managed deps
├── .python-version                    # 3.11
├── config.json                        # FreqTrade config (read-only for agent)
├── prepare.py                         # data download (read-only for agent)
├── run.py                             # backtest + summary (read-only for agent)
├── program.md                         # agent instructions
├── analysis.ipynb                     # post-hoc analysis
├── user_data/
│   ├── strategies/
│   │   ├── _template.py.example       # skeleton the agent copies from
│   │   └── <agent-created files>.py   # up to 3 active at a time
│   ├── data/                          # gitignored — downloaded OHLCV
│   └── backtest_results/              # gitignored — FreqTrade outputs
├── versions/                          # frozen snapshots of past runs
└── results.tsv                        # gitignored — agent's event log
```

## Design notes

- **Agent owns one directory, not one file.** `user_data/strategies/` is its
  workspace; everything else is evaluation contract. Up to 3 strategies
  simultaneously, hard cap. Multi-strategy exists specifically to fight
  the single-paradigm anchoring that v0.1.0 exhibited.
- **No CLI indirection.** The agent only runs `uv run prepare.py` and
  `uv run run.py`. `run.py` uses FreqTrade's `Backtesting` class in-process,
  so startup is fast and errors surface as real Python stack traces.
- **`results.tsv` is a gitignored event log.** Each round, the agent appends
  rows (one per strategy touched, with event type: create/evolve/stable/fork/kill).
  It survives `git reset --hard` so past lessons stay available even when
  experimental commits get thrown away.
- **LLM decides keep/kill, not a scalar rule.** Sharpe on a finite window
  is noisy and gameable. Agent reads the full per-strategy summary blocks
  and decides inline which strategies to evolve, fork, or kill — the
  program.md rules force action but not which action.
- **Stagnation rule.** A strategy can't sit idle for more than 3 consecutive
  stable rounds — agent must evolve, fork, or kill it. With only 3 slots,
  dead weight is expensive.

## License

MIT.
