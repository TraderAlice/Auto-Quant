# Auto-Quant v0.4.1 — strategy-declared portfolio + cross-regime testing

This is an experiment to have the LLM do its own quantitative research across
**multiple parallel strategies** that can:
- combine signals across **multiple timeframes** (1h base + 4h + 1d)
- reference **multiple assets** (5-pair universe with cross-asset signal references)
- declare their **own basket** of pairs to trade (subset of the whitelist)
- declare **their own test timeranges** for cross-regime evaluation
- use **dynamic position sizing** via `custom_stake_amount`
- compare against a **buy-and-hold benchmark** computed for the same period

Decision metric (v0.4.1): `robust_sharpe = min(sharpe across declared timeranges)`,
flanked by `profit_floor`, `min_position_size`, and `pareto_dominated_by` gates.

The progression so far:
- v0.2.0 added multi-strategy → resisted single-paradigm anchoring
- v0.3.0 added MTF + multi-asset + per-pair reporting → hit clean Sharpe 1.07
- v0.4.0 extended timerange to include 2022 winter + opened sizing affordance
  → real-edge clean Sharpe 1.122 / +232% on 5-year regime mix; surfaced the
  Sharpe-as-single-oracle degeneracy boundary
- **v0.4.1** addresses the v0.4.0 surfacing directly:
  - **Portfolio basket** (`pair_basket`): strategies declare which pairs to
    trade, no longer forced through all 5
  - **Multi-timerange** (`test_timeranges`): each strategy backtested across
    multiple regime segments in one round, with `robust_sharpe` = worst-case
    timerange Sharpe as the headline
  - **Multi-objective oracle**: profit-floor, min-position-size, and
    Pareto-dominance gates flank the Sharpe number — directly counters the
    v0.4.0 "tighten vol_target until Sharpe → ∞ but profit → 0" degeneracy
  - **Buy-and-hold benchmark**: per-timerange BaH portfolio Sharpe + return
    + DD, computed from 1d feathers and reported alongside strategy metrics

The v0.4.1 honesty bar (more demanding than v0.4.0):
- A strategy is "real" only if `robust_sharpe` is good across ALL its declared
  timeranges, AND `profit_floor` PASS, AND `min_position_size` PASS, AND it
  isn't `pareto_dominated_by` a prior keep
- Headline Sharpe by itself is no longer enough — the gates must clear

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `may1`).
   The branch `autoresearch/<tag>` must not already exist.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from current `master`.
3. **Read the in-scope files**. The repo is small. Read these files for full context:
   - `README.md` — repository context
   - `config.json` — fixed FreqTrade config (pairs, timeframe, fees). Do not modify.
   - `prepare.py` — data download. Do not modify.
   - `run.py` — the batch backtest oracle. Do not modify.
   - `user_data/strategies/_template.py.example` — skeleton for new strategies.
     **Note:** the folder may also contain `__pycache__`; ignore it.
   - `versions/<v>/retrospective.md` — prior runs' findings. All three
     are valuable as design context:
     - v0.1.0: single-paradigm anchoring + 3 Goodhart exploits agent
       self-reversed
     - v0.2.0: multi-strategy resolution of anchoring; 5 paradigms / 3 kept
     - v0.3.0: MTF + portfolio + per-pair → Sharpe 1.07 clean; first fork +
       isolation experiment; **explicitly flagged single-regime data as
       blocking** several findings (cross-pair macro gates, bear robustness)
       — exactly what v0.4.0 addresses.
4. **Verify data exists**: Check that all fifteen data files exist under
   `user_data/data/` — 5 pairs × 3 timeframes:
   - `BTC_USDT-{1h,4h,1d}.feather`
   - `ETH_USDT-{1h,4h,1d}.feather`
   - `SOL_USDT-{1h,4h,1d}.feather`
   - `BNB_USDT-{1h,4h,1d}.feather`
   - `AVAX_USDT-{1h,4h,1d}.feather`

   If any are missing, tell the user to run `uv run prepare.py`.
5. **Initialize results.tsv**: Create `results.tsv` with just the header row:
   ```
   commit	event	strategy_name	sharpe	max_dd	note
   ```
   Tab-separated. Do not commit this file — it's gitignored on purpose.
6. **Create 1-3 starting strategies.** This is the most important setup step.
   - Each strategy goes in its own file: `user_data/strategies/<YourName>.py`
   - Class name MUST match filename stem (FreqTrade requirement)
   - Each strategy's docstring MUST fill all 6 metadata fields
     (Paradigm, Hypothesis, Parent, Created, Status, Uses MTF)
   - **Each strategy MUST target a different paradigm.** Don't create 3
     mean-reversion variants as a "safe start" — that defeats the whole point
     of v0.2.0+. Pick from: mean-reversion, trend-following, volatility,
     breakout, other. At least 2 different categories.
   - **Strongly encouraged**: at least one of the starting strategies should
     use the multi-timeframe affordance (see "Multi-timeframe" section below).
     Otherwise v0.3.0 doesn't exercise the new capability and we'll have
     learned nothing new vs v0.2.0. This is encouragement not mandate — if
     you have strong reasoning to make all 3 single-TF, write that reasoning
     in the notes.
   - Keep each strategy minimal initially. You'll iterate in the loop.
7. **Confirm and go**: Confirm setup looks good with the user.

Once you get confirmation, kick off the experimentation.

## Experimentation

Each round runs a backtest on ALL active strategies on a **fixed timerange**
(`20210101-20251231`, 5 years including the 2022 bear regime) across the
**5-pair portfolio** (BTC, ETH, SOL, BNB, AVAX) at 1h base. `run.py` emits
one `---` summary block per strategy, containing both portfolio-aggregate
metrics AND per-pair breakdown.

**Backtest time note (v0.4.0)**: 5 years × 5 pairs × 3 timeframes ≈ 1.7×
slower than v0.3.0. Each round of 3 strategies takes roughly 5-8 minutes.
Plan iterations accordingly — about 8-12 rounds per hour.

### What you CAN do

- Modify any file under `user_data/strategies/` (that isn't prefixed `_`)
- Create a new strategy file
- Delete a strategy file (via `git rm`)
- Copy an existing strategy to create a variant (fork)

### What you CANNOT do

- Modify `prepare.py`, `run.py`, or `config.json`. These are the evaluation
  contract.
- `uv add` new dependencies. Use what's already in `pyproject.toml`.
- Call the `freqtrade` CLI directly. The only way to run backtests is via
  `uv run run.py`.
- Modify the timerange, pair list, or `_template.py.example`.
- Have more than 3 active strategies at any time (see hard cap below).
- Request timeframes other than `1h`, `4h`, `1d` OR pairs other than the
  5 in the whitelist in `@informative` decorators. Anything else will crash
  the backtest with a missing-data error.

### Multi-timeframe + cross-asset affordance (new in v0.3.0)

Data is pre-downloaded for **three timeframes × five pairs = 15 combinations**:

| Timeframe | Pairs |
|---|---|
| 1h (base) | BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, AVAX/USDT |
| 4h | BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, AVAX/USDT |
| 1d | BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, AVAX/USDT |

Strategies are always evaluated on the 1h base across ALL five pairs in one
backtest run. You cannot change the base TF or pair list. But you can pull
additional context along TWO axes via FreqTrade's `@informative` decorator:
higher-TF data from the same pair, and same-TF data from different pairs.

**Basic higher-timeframe usage** (most common):

```python
from freqtrade.strategy import IStrategy, informative

class YourStrategy(IStrategy):
    timeframe = "1h"

    @informative("4h")
    def populate_indicators_4h(self, dataframe, metadata):
        dataframe["rsi"] = ta.RSI(dataframe, 14)
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe, metadata):
        dataframe["ema200"] = ta.EMA(dataframe, 200)
        return dataframe

    def populate_indicators(self, dataframe, metadata):
        # Merged columns are auto-available: rsi_4h, ema200_1d
        dataframe["rsi"] = ta.RSI(dataframe, 14)
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        # MTF confluence: 1h oversold + 4h not overbought + 1d bull regime
        dataframe.loc[
            (dataframe["rsi"] < 20)
            & (dataframe["rsi_4h"] < 60)
            & (dataframe["close"] > dataframe["ema200_1d"]),
            "enter_long",
        ] = 1
        return dataframe
```

**Cross-pair usage** (reference another asset's data):

```python
@informative("1h", "BTC/USDT")
def populate_btc_1h(self, dataframe, metadata):
    dataframe["close_ma"] = ta.SMA(dataframe, 50)
    return dataframe

# In populate_indicators on, say, ETH — you now have `btc_usdt_close_ma_1h`
# Column naming: `{base}_{quote}_{col}_{tf}`, lowercase, underscore-separated.
```

**Cross-pair asymmetry** — important subtlety: `@informative('1h', 'ETH/USDT')`
always pulls ETH data regardless of which pair the strategy is currently
processing. When processing BTC, that gives you BTC main + ETH context
(useful). When processing ETH itself, you get ETH's data alongside itself
(redundant). For truly symmetric cross-pair strategies (e.g., BTC/ETH ratio
that means something on BOTH pairs), use `informative_pairs()` with a
`metadata['pair']`-conditional branch inside `populate_indicators`.

**Key properties** (FreqTrade handles these for you):
- Column naming: `rsi` in a `@informative('4h')` method → `rsi_4h` in 1h dataframe.
  For cross-pair: `rsi` in `@informative('1h', 'BTC/USDT')` → `btc_usdt_rsi_1h`.
- Look-ahead safe: FreqTrade shifts merged data by 1 period so current 1h bar
  never sees future higher-TF bars.
- Forward-filled: at any 1h bar, the merged `rsi_4h` value is the last
  fully-closed 4h bar's RSI.

**When to use higher TFs:**
- Regime filters (`close > ema200_1d` for bull regime)
- Trend confirmation (`ema9_4h > ema21_4h`)
- Volatility context (`atr_4h` for relative-vol positioning)

**When to use cross-pair:**
- Relative value / ratio plays (`close / btc_usdt_close_1h`)
- Leader/follower dynamics (BTC often leads ETH/altcoins on 4h)
- Diversification checks ("only enter if BTC isn't crashing")

**When NOT to use either:**
- If the paradigm doesn't have an intuitive MTF/cross-pair analog, don't force it.
  v0.2.0's MeanRevBB was pure 1h single-pair and hit 0.52 Sharpe.

**`startup_candle_count`** — bump up for slow indicators on higher TFs. EMA200
on 1d needs 200 daily bars = 4800 hourly bars of warmup. Starting at 250-300
is usually safe for most MTF configurations.

### Dynamic position sizing (new in v0.4.0)

By default each trade is sized at `wallet * tradable_balance_ratio /
max_open_trades` — equal-weight across the 5-pair universe. v0.4.0 unlocks
**dynamic per-trade sizing** via FreqTrade's `custom_stake_amount` method:

```python
def custom_stake_amount(self, pair, current_time, current_rate,
                        proposed_stake, min_stake, max_stake,
                        leverage, entry_tag, side, **kwargs) -> float:
    # Return a number within [min_stake, max_stake].
    # `proposed_stake` is the equal-weight default.
    df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
    atr_pct = df["atr"].iloc[-1] / df["close"].iloc[-1]
    vol_target = 0.02
    scale = min(1.0, vol_target / max(atr_pct, 1e-6))
    return max(min_stake or 0.0, min(max_stake, proposed_stake * scale))
```

**When to use it**:
- Vol-targeting (smaller positions on more volatile pairs/regimes)
- Signal-strength weighting (bigger position when entry signal is stronger)
- Regime-conditional sizing (smaller in bear, normal in bull). With v0.4.0's
  regime-mixed timerange, this is especially relevant — equal-weight in 2022
  winter is often a research liability.

**When NOT to use it**:
- If your paradigm doesn't have a natural sizing logic, default equal-weight
  is fine. Forcing sizing into a strategy that doesn't need it adds noise.
- v0.3.0's MTFTrendStack and BTCLeaderBreakX both used equal-weight default
  and reached Sharpe > 0.7.

**Honesty consideration**: in v0.4.0's regime-mixed data, sizing-aware
strategies are likely to look better than equal-weight equivalents because
they can de-risk in 2022. That doesn't mean sizing is "the secret sauce" —
it means equal-weight in regime mix is structurally exposed. When comparing,
distinguish "this strategy has real edge" from "this strategy survives
regime mix BECAUSE it sizes down in bear".

### Per-pair reporting (still as in v0.3.0)

`run.py` output now includes a `per_pair:` section after the aggregate
metrics. Example:

```
---
strategy:         YourStrategy
sharpe:           0.45         # aggregate across all 5 pairs
...
pairs:            BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,AVAX/USDT
per_pair:
  BTC/USDT: sharpe=0.62 trades=45 profit_pct=18.5 dd_pct=-3.2 wr=58.0 pf=1.72
  ETH/USDT: sharpe=0.38 trades=50 profit_pct=12.1 dd_pct=-5.1 wr=52.0 pf=1.35
  SOL/USDT: sharpe=0.12 trades=35 profit_pct=5.3 dd_pct=-8.1 wr=48.6 pf=1.08
  BNB/USDT: sharpe=0.71 trades=40 profit_pct=22.0 dd_pct=-2.9 wr=62.5 pf=1.93
  AVAX/USDT: sharpe=-0.05 trades=30 profit_pct=-2.8 dd_pct=-7.4 wr=46.7 pf=0.92
```

**Use per-pair metrics aggressively** — they're the main new information
surface. Things to look for:
- **Does the strategy work on ALL pairs or just some?** A paradigm that's
  great on BTC but negative on SOL/AVAX is either (a) BTC-specific
  (interesting, worth understanding why) or (b) noise (worth killing).
- **Are DDs asymmetric?** Some pairs may carry most of the portfolio DD.
- **Trade count balance**: if one pair has 200 trades and another has 3,
  that's a sample-size problem you should note.
- **Cross-pair correlations in edge**: BTC+BNB doing well while ETH+SOL+AVAX
  flat tells you something about what kind of regime the strategy exploits.

In your `results.tsv` notes, when a result varies substantially across pairs,
**call it out explicitly** — e.g., "Sharpe 0.45 aggregate but SOL=-0.10 and
BNB=+0.80; signal is BNB-heavy, trade count 40 not enough". These are the
observations that make the run's knowledge output per-asset-profile-shaped
(the original project goal).

### Strategy-declared portfolio basket (new in v0.4.1)

By default a strategy is evaluated on ALL 5 pairs in the whitelist. This
forces every paradigm through every asset, which is sometimes wrong:
trend may shine on alts but not on BTC, MR may be BNB-skewed, etc. v0.4.1
lets a strategy declare its trade universe via a class attribute:

```python
class YourStrategy(IStrategy):
    timeframe = "1h"
    pair_basket = ["SOL/USDT", "BNB/USDT", "AVAX/USDT"]   # alts only
    ...
```

The strategy is then only evaluated on its declared basket, both for
trade execution and for per-pair reporting. The aggregate metrics
(`sharpe`, `profit_total_pct`, etc.) are over the basket, not the full
whitelist.

**When to declare a basket:**
- The paradigm clearly fits some assets better than others (per-pair report
  shows wide dispersion across the 5 pairs)
- v0.4.0 surfaced patterns like "MR is BNB-skewed" or "trend has AVAX drag" —
  basket declaration lets you act on those findings as a first-class
  design choice, not a post-hoc note

**When NOT to declare a basket:**
- The paradigm is universal (e.g., a regime filter that should apply to all
  major crypto)
- You haven't yet seen evidence of asset-specific fit — start with full
  basket, observe per-pair dispersion, then prune if warranted

The basket survives across timeranges within a strategy (you can't
declare different baskets per timerange — that would be two separate
strategies).

### Multi-timerange testing (new in v0.4.1)

A strategy can declare a list of timeranges to test across. Each declared
timerange runs as its own backtest; results are emitted as separate
`---` blocks; a final SUMMARY block reports `robust_sharpe = min over
declared timeranges`.

```python
class YourStrategy(IStrategy):
    test_timeranges = [
        ("bull_2021",      "20210101-20211231"),  # 2021 bull regime
        ("winter_2022",    "20220101-20221231"),  # 2022 winter (BTC -75%)
        ("recovery_23_25", "20230101-20251231"),  # 2023-25 recovery
        ("full_5y",        "20210101-20251231"),  # full window
    ]
```

If unset, defaults to a single backtest over `20210101-20251231` (full).

**Why use multi-timerange:**
- Cross-regime robustness: a strategy that gets Sharpe 1.5 on bull but -0.5
  on winter is NOT a Sharpe 1.0 strategy; it's an over-fit one. Multi-timerange
  surfaces this immediately.
- Out-of-sample validation: declare `("train_21_24", "20210101-20241231")`
  and `("test_25", "20250101-20251231")` to get a clean OOS check.
- Mechanism understanding: which regime carries the edge? which kills it?
  The per-timerange dispersion is a research output in itself.

**`robust_sharpe`** is the headline metric for a strategy in v0.4.1 —
it's the worst-timerange Sharpe across all declared ranges. Use this
when judging keep/kill — single-timerange Sharpe can hide regime
overfit.

**Trade-off**: backtest time scales linearly with number of timeranges.
4 declared timeranges = 4× backtest time per round. Choose meaningfully —
you don't need 8 timeranges. 2-4 is usually plenty.

### Buy-and-hold benchmark (new in v0.4.1)

Each timerange's `---` block now reports:

```
bah_sharpe:       0.93
bah_profit_pct:   187.3
bah_dd_pct:       -65.2
```

These are the equal-weight buy-and-hold portfolio metrics over the same
pairs and timerange. Compare your strategy directly:
- If `sharpe < bah_sharpe` AND `profit < bah_profit`, your strategy is
  strictly worse than doing nothing — kill it
- If your strategy beats BaH on Sharpe but not profit, you're trading
  return for risk-adjustment (might be intentional)
- If your strategy beats BaH on both, you have real alpha

In `results.tsv` notes, **always cite BaH for context** — e.g., "Sharpe 1.12
beats BaH 0.93 on full timerange; profit 232% beats BaH 187%". Without
the BaH reference, the agent can over-celebrate strategies that just track
the market.

### Multi-objective gates (new in v0.4.1)

In addition to `robust_sharpe`, the per-strategy SUMMARY block reports
three pass/fail gates:

```
profit_floor:        PASS  (threshold ≥ 20% per timerange)
min_position_size:   PASS  (threshold ≥ 5%)
pareto_dominated_by: none (non-dominated)
```

- **profit_floor**: each declared timerange must clear ≥20% portfolio profit.
  Catches "Sharpe-via-tightening-stake" Pareto degeneracy from v0.4.0.
- **min_position_size**: average trade stake / wallet must be ≥5%. Same
  defense — prevents sizing → 0 from inflating Sharpe.
- **pareto_dominated_by**: the SUMMARY's robust_sharpe + worst-DD pair
  is checked against all prior commits' rows in `results.tsv`. If any
  prior strategy has `sharpe ≥ yours` AND `dd ≥ yours` (less negative),
  this row is marked dominated. A dominated current strategy is a kill
  candidate — there's no reason to keep it when a prior is strictly better.

**A FAIL gate isn't an automatic kill** — agent decides. But it's a strong
signal that the headline number is misleading. When deciding keep/kill,
weigh gates as inputs alongside the metrics.

### Hard rules on strategy lifecycle

**Rule 1: Hard cap — 3 active strategies.**
At any moment, `user_data/strategies/` must contain at most 3 non-underscore
`.py` files. To add a 4th, you must first `git rm` one of the existing.

**Rule 2: Stagnation gate — 3 stable rounds.**
Each round, every strategy gets one of these events logged in `results.tsv`:
- `create` — you added it this round
- `evolve` — you modified it this round
- `stable` — it existed, got measured, but you didn't touch it
- `fork` — you copied it to create a derivative (logged on the child, with
  `parent→child` in the strategy_name field)
- `kill` — you removed it this round

**If a strategy has accumulated 3 consecutive `stable` events with no `evolve`
or `fork`, the next round it MUST receive one of: `evolve`, `fork`, or `kill`.**
Cannot sit idle for a 4th stable round. You decide which treatment. This rule
exists because the cap is 3 — we can't afford a slot sitting still.

**Rule 3: Every round must touch at least one strategy.**
A round where all events are `stable` is not an experiment — it's wasted time.
At minimum, evolve one strategy per round. (Exception: the very first backtest
round right after setup, where you log `create` events for what you built.)

**Rule 4: Paradigm diversity at setup.**
See setup step 6 above. First 1-3 strategies must target different paradigms.
After that, you're free to create same-paradigm variants (e.g. two
mean-reversion approaches with different signals) — but sparingly. Diversity
is more valuable than depth in this run.

## Output format

Once `run.py` finishes, stdout has one `---` block **per (strategy, timerange)
combination**, plus a final SUMMARY block per strategy. If a strategy declares
4 timeranges, you get 4 backtest blocks + 1 SUMMARY = 5 blocks for that
strategy.

Per-timerange block:

```
---
strategy:         YourStrategy
timerange_label:  bull_2021
timerange:        20210101-20211231
commit:           abc1234
basket:           BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,AVAX/USDT
sharpe:           1.2300
sortino:          2.1500
calmar:           1.8900
total_profit_pct: 67.5
max_drawdown_pct: -7.4
trade_count:      201
win_rate_pct:     58.0
profit_factor:    1.85
bah_sharpe:       1.45
bah_profit_pct:   132.1
bah_dd_pct:       -22.3
per_pair:
  BTC/USDT: sharpe=0.62 trades=45 profit_pct=18.5 dd_pct=-3.2 wr=58.0 pf=1.72 (bah_profit=98.3 bah_dd=-15.1)
  ...
```

Per-strategy SUMMARY block:

```
---
strategy:         YourStrategy
timerange_label:  SUMMARY
commit:           abc1234
robust_sharpe:    0.6500   # min across declared timeranges
worst_profit_pct: 22.4
worst_dd_pct:     -28.1
avg_position_pct: 18.7
profit_floor:     PASS    (threshold ≥ 20% per timerange)
min_position_size: PASS   (threshold ≥ 5%)
pareto_dominated_by: none (non-dominated)
```

**`robust_sharpe`** is the headline metric for v0.4.1 keep/kill decisions —
it's the worst-timerange Sharpe. Single-timerange Sharpe is no longer
sufficient; cross-regime robustness must clear too.

If a strategy crashes on any timerange, that timerange's block looks like:
```
---
strategy:         SomeBrokenStrategy
commit:           abc1234
status:           ERROR
error_type:       NameError
error_msg:        name 'foo' is not defined
traceback:
  ...
```

Extract all strategies' metrics at once:
```bash
grep "^---\|^strategy:\|^sharpe:\|^trade_count:\|^max_drawdown_pct:" run.log
```

Full per-strategy block:
```bash
awk '/^---$/,/^$/' run.log
```

## Logging results

After each round, append one row to `results.tsv` **per strategy touched**.
Tab-separated, 6 columns:

```
commit	event	strategy_name	sharpe	max_dd	note
```

Rules:
- `commit` is the short git hash of the round's commit
- `event` is one of `create | evolve | stable | fork | kill`
- For `fork`, `strategy_name` uses `parent→child` format (e.g. `MeanRevRSI→MRVolGate`)
- For `kill`, leave `sharpe` and `max_dd` as `-` (dash). The strategy is gone.
- `note` is your reasoning in free text. This is load-bearing — when you
  later decide keep vs kill, you re-read these notes. Be specific:
  - Bad: `"tried MACD, didn't work"`
  - Good: `"replaced RSI entry with MACD cross-up. wr 68→51, sharpe 0.82→0.31. MACD crossovers on 1h crypto trigger inside ongoing drops, catching knives. Discarding paradigm."`
- Every strategy that exists this round gets a row, even if `stable`. This
  is how the stagnation counter stays visible.

**Do NOT commit `results.tsv`.** It is gitignored on purpose — the log
survives `git reset --hard`, which is essential so you don't forget what
you've already tried.

## The experiment loop

The experiment runs on the dedicated branch (e.g. `autoresearch/may1`).

LOOP FOREVER:

1. **Look at state**: read `results.tsv` (tail ~30 rows), note the current
   active strategies and their stagnation counters (how many consecutive
   `stable` events each has).

2. **Decide this round's action.** Your toolkit per round:
   - `evolve <strategy>`: modify an existing strategy file
   - `create <name>`: add a new strategy (if cap has room)
   - `fork <parent>→<child>`: cp a strategy file to a new name, then modify
     the child
   - `kill <strategy>`: `git rm` the file
   - You can combine: e.g. "kill A and create B in the same commit" (make room
     for something new), or "fork A→A' and evolve B" (two strategies touched)

3. **Respect the rules.** In particular:
   - Cap: max 3 active strategies after this round's changes
   - Stagnation: any strategy with 3 prior consecutive `stable` events must
     be evolved, forked, or killed THIS round
   - Every round touches ≥ 1 strategy

4. **Make the code changes.** Write/modify files under `user_data/strategies/`.

5. **`git commit -am "<short summary of this round>"`**

6. **Run the backtest**: `uv run run.py > run.log 2>&1`

7. **Read the summary**: `awk '/^---$/,/^$/' run.log` (shows all blocks) or
   `grep "^---\|^strategy:\|^sharpe:\|^trade_count:" run.log` (compact).

8. **Check for crashes**: a strategy with `status: ERROR` needs to be fixed
   (if the error is trivial — syntax, typo) OR killed (if the hypothesis is
   broken). Don't leave ERROR strategies around.

9. **Log to results.tsv**: one row per strategy that existed this round. Fill
   in the event, metrics (or `-` for kills), and your reasoning note.

10. **Decide keep vs rollback.**
    - Common case: per-strategy decisions happen inline (you either evolved
      to something better, or the change was bad and you git-reset only that
      strategy's commit). The whole round doesn't have one "keep/discard"
      decision — individual strategies do.
    - If the whole round was a mistake (broke everything, wrong direction),
      `git reset --hard HEAD~1` to undo all changes.
    - If some strategies improved and others didn't: keep the commit, log
      `stable` for the unchanged ones, log `evolve` or `kill` etc. for the
      changed ones.

11. **Loop.**

### Deciding keep vs kill on a strategy (updated for v0.4.1)

A strategy deserves to stay if (in priority order):
1. **`robust_sharpe` is meaningfully positive** (> 0.3 as a soft bar) AND
   the worst-timerange numbers aren't catastrophic
2. **All multi-objective gates PASS**: profit_floor, min_position_size,
   pareto_dominated_by = none
3. **Beats BaH** at least on Sharpe across the declared timeranges (or has
   a clear non-Sharpe edge: e.g., much lower DD with comparable profit)
4. Its paradigm/basket is distinct from other active strategies
5. Recent evolutions have moved it in the right direction

A strategy deserves to die if:
- `robust_sharpe` is below 0 (worst regime is genuinely bad — not a
  recoverable strategy)
- A gate FAILs (especially `pareto_dominated_by` — there's a strict prior
  better than this one)
- Sharpe is below BaH on every declared timerange (you're losing to
  doing nothing)
- Stable for 3 rounds with no improvement and no new ideas
- Paradigm/basket overlaps strongly with a better-performing active strategy

**The v0.4.1 honesty bar:** a strategy that hits Sharpe 1.5 on `bull_2021` but
-0.5 on `winter_2022` has `robust_sharpe = -0.5` — that's NOT a Sharpe-1.5
strategy. Keep/kill decisions weight robust_sharpe, not best-case.

**Always log your reasoning.** These notes become the retrospective —
future you (and the meta-analysis layer) will read them to extract what this
run actually learned. Cite BaH for context: "Sharpe 1.12 beats BaH 0.93;
robust_sharpe 0.85 (winter_2022 is the floor, still positive)" is a useful
note. "Sharpe 1.12" alone is not.

### Goodhart watch

From v0.1.0 we learned the agent can inadvertently game the metric:
- `exit_profit_only=True` → 100% win rate by never realizing losses
  (regime-dependent, breaks in bear markets)
- Tight `minimal_roi` clipping → tiny uniform returns → low stddev → huge
  Sharpe (profit goes DOWN even as Sharpe goes UP)

**v0.2.0 added zero new Goodhart exploits over 81 rounds — try to keep that streak.**

If you find a Sharpe jump that comes with a profit drop or a DD collapse to
~0, that's a gaming signal, not real edge. Log it, document the mechanism,
then either kill the strategy or explicitly note "this is an oracle artifact,
not edge" in the description.

Multi-strategy helps here: if strategy A's Sharpe jumps while B and C stay
flat on the same data, A's jump is more likely a real discovery. If ALL
three strategies' Sharpe jumped on the same commit — you probably modified
something shared, or the oracle itself has a hole.

**Timeout**: each full round (3 strategies × backtest) should take under 3
minutes. If a single run exceeds 10 minutes, kill it and treat it as a
failure (revert the commit, skip the round).

### NEVER STOP

Once the experiment loop has begun (after initial setup), do NOT pause to
ask the human if you should continue. Do NOT ask "should I keep going?" or
"is this a good stopping point?". The human may be asleep, or away from
the computer, and expects you to continue working *indefinitely* until
manually stopped.

If you run out of ideas:
- **Re-read `versions/0.1.0/retrospective.md` and `versions/0.2.0/retrospective.md`**
  — v0.1.0 listed directions it never tried (multi-timeframe was one!);
  v0.2.0 attempted 5 paradigms and identified specific plateau ceilings per paradigm
- Apply multi-timeframe to a stagnant strategy (if not using MTF yet) —
  that's literally the new affordance of v0.3.0
- Look at your stagnant strategies — can you fork them with a bolder change?
- Try combining winners from different paradigms (e.g. a volatility-gated
  version of a winning mean-reversion strategy)
- Try completely new indicator families you haven't touched
- Check v0.2.0's comparative findings (volume-filter universal, ATR
  paradigm-specific, regime-window paradigm-specific, ADX-lag universal) —
  see if any transfer to your current strategies in ways v0.2.0 never tested
  (e.g., 4h volume expansion instead of 1h)

The loop runs until the human interrupts you, period.

As an example use case, a user might leave you running while they sleep.
Each round of 3-strategy backtests takes ~2-3 minutes, so you can run several
dozen per hour. The user then wakes up to a rich multi-strategy research
trace ready for meta-analysis.
