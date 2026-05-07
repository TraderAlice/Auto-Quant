"""
run.py — READ-ONLY. The oracle. Do not modify.

For each strategy in `user_data/strategies/`, runs FreqTrade's Backtesting
in-process across one or more timeranges and pair baskets, computes per-pair
metrics + portfolio aggregate + buy-and-hold benchmark + multi-objective
flags, and prints the result blocks to stdout.

v0.4.1 affordances exposed via per-strategy class attributes:

- `pair_basket`: list of pairs the strategy wants to trade. If unset, defaults
  to the full whitelist (BTC/ETH/SOL/BNB/AVAX). Strategy is only evaluated
  on its declared basket. This lets strategies opt into asset-specific
  universes (e.g., trend-only-on-alts, MR-only-on-BNB) instead of being
  forced through every pair in the whitelist.

- `test_timeranges`: list of `(label, "YYYYMMDD-YYYYMMDD")` tuples. If unset,
  defaults to a single backtest over the full v0.4.0 timerange. Each
  declared timerange produces its own `---` block in the output, plus the
  strategy gets a final summary block with `robust_sharpe` (= min sharpe
  across all declared timeranges).

Multi-objective oracle (new in v0.4.1):

- `profit_floor`: each timerange backtest's profit must clear a configurable
  floor (default 20% absolute) — flagged in summary.
- `min_position_size`: average stake fraction must be ≥ a configurable
  floor (default 5%). Catches the v0.4.0 "Sharpe-via-tiny-stakes" Pareto
  degeneracy.
- `pareto_dominated_by`: cross-checks the strategy's robust metrics against
  prior commits' KEEP / EVOLVE rows in `results.tsv` for Pareto dominance.

Buy-and-hold benchmark: each timerange's `---` block reports the
equal-weight buy-and-hold portfolio return + Sharpe + DD computed from
1d feathers, so the agent can compare strategy edge to "doing nothing".

Usage:
    uv run run.py > run.log 2>&1
    grep "^---\\|^strategy:\\|^sharpe:\\|^trade_count:" run.log  # compact scan
    awk '/^---$/,/^$/' run.log                                   # full blocks
"""

from __future__ import annotations

import importlib.util
import math
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from freqtrade.configuration import Configuration
from freqtrade.enums import RunMode
from freqtrade.optimize.backtesting import Backtesting

# ---------------------------------------------------------------------------
# Fixed constants. Do not modify.
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).parent.resolve()
USER_DATA = PROJECT_DIR / "user_data"
DATA_DIR = USER_DATA / "data"
STRATEGIES_DIR = USER_DATA / "strategies"
CONFIG = PROJECT_DIR / "config.json"

DEFAULT_TIMERANGE = "20210101-20251231"
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "AVAX/USDT"]
PAIRS_STR = ",".join(PAIRS)

# Multi-objective gates (v0.4.1)
PROFIT_FLOOR_PCT = 20.0   # each timerange must show at least +20% portfolio profit
MIN_POSITION_SIZE_PCT = 5.0  # avg trade stake / wallet must be ≥ 5%

# Annualization factor for daily Sharpe of crypto portfolios
DAILY_SHARPE_FACTOR = math.sqrt(365)


# ---------------------------------------------------------------------------
# Strategy module loading + class-attr introspection
# ---------------------------------------------------------------------------
def discover_strategies() -> list[str]:
    if not STRATEGIES_DIR.exists():
        return []
    names = []
    for path in sorted(STRATEGIES_DIR.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        names.append(path.stem)
    return names


def load_strategy_class(name: str):
    """Load the strategy class from its module file via importlib.

    We need this BEFORE invoking Backtesting so we can read class attributes
    (`pair_basket`, `test_timeranges`) and override the FreqTrade config
    per-strategy. FreqTrade's own StrategyResolver loads it again later;
    that's fine — Python caches the module.
    """
    path = STRATEGIES_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = getattr(module, name, None)
    if cls is None:
        raise AttributeError(
            f"file {path} does not define a class named {name} "
            "(class name must match filename stem)"
        )
    return cls


def get_strategy_overrides(name: str) -> tuple[list[str] | None, list[tuple[str, str]]]:
    """Return (pair_basket, test_timeranges) declared by the strategy class.

    Defaults: full whitelist + single full-timerange.
    """
    cls = load_strategy_class(name)
    pair_basket = getattr(cls, "pair_basket", None)
    test_timeranges = getattr(cls, "test_timeranges", None) or [("full", DEFAULT_TIMERANGE)]
    # Validate basket
    if pair_basket is not None:
        for p in pair_basket:
            if p not in PAIRS:
                raise ValueError(
                    f"{name}: pair_basket entry {p!r} not in whitelist {PAIRS}"
                )
    # Validate timeranges
    for label, tr in test_timeranges:
        if "-" not in tr or len(tr) < 11:
            raise ValueError(
                f"{name}: test_timerange {label!r} = {tr!r} is malformed; "
                'expected "YYYYMMDD-YYYYMMDD"'
            )
    return pair_basket, test_timeranges


# ---------------------------------------------------------------------------
# Backtest invocation with overrides
# ---------------------------------------------------------------------------
def run_backtest(
    strategy_name: str,
    timerange: str,
    pair_basket: list[str] | None,
) -> dict[str, Any]:
    args = {
        "config": [str(CONFIG)],
        "user_data_dir": str(USER_DATA),
        "datadir": str(DATA_DIR),
        "strategy": strategy_name,
        "strategy_path": str(STRATEGIES_DIR),
        "timerange": timerange,
        "export": "none",
        "exportfilename": None,
        "cache": "none",
    }
    config = Configuration(args, RunMode.BACKTEST).get_config()
    if pair_basket:
        config["exchange"]["pair_whitelist"] = list(pair_basket)
    bt = Backtesting(config)
    bt.start()
    return bt.results


# ---------------------------------------------------------------------------
# Metric extraction
# ---------------------------------------------------------------------------
def _get(d: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return float(d[k])
            except (TypeError, ValueError):
                continue
    return default


def _entry_metrics(entry: dict[str, Any]) -> dict[str, float]:
    return {
        "sharpe": _get(entry, "sharpe", "sharpe_ratio"),
        "sortino": _get(entry, "sortino", "sortino_ratio"),
        "calmar": _get(entry, "calmar", "calmar_ratio"),
        "total_profit_pct": _get(entry, "profit_total_pct"),
        "max_drawdown_pct": -abs(_get(entry, "max_drawdown_account")) * 100,
        "trade_count": int(_get(entry, "trades", "total_trades")),
        "win_rate_pct": _get(entry, "winrate") * 100,
        "profit_factor": _get(entry, "profit_factor"),
    }


def extract_metrics(
    results: dict[str, Any],
    strategy_name: str,
    pairs: list[str],
) -> dict[str, Any]:
    strat = results.get("strategy", {}).get(strategy_name, {}) or {}
    per_pair_list = strat.get("results_per_pair", []) or []
    aggregate: dict[str, float] = {}
    per_pair: dict[str, dict[str, float]] = {}
    for entry in per_pair_list:
        key = entry.get("key", "")
        m = _entry_metrics(entry)
        if key == "TOTAL":
            aggregate = m
        elif key:
            per_pair[key] = m
    if not aggregate:
        aggregate = _entry_metrics(strat)
    return {"aggregate": aggregate, "per_pair": per_pair, "pairs": pairs}


# ---------------------------------------------------------------------------
# Buy-and-hold benchmark — equal-weight portfolio over 1d feathers
# ---------------------------------------------------------------------------
def compute_bah_benchmark(
    timerange: str,
    pairs: list[str],
) -> dict[str, Any]:
    """Compute equal-weight buy-and-hold portfolio metrics over the timerange.

    Reads 1d feathers, slices to timerange, computes per-pair daily returns,
    averages across pairs (equal-weight portfolio), then derives Sharpe /
    profit / max-DD. Returns NaN-safe defaults on missing data.
    """
    start_str, end_str = timerange.split("-", 1)
    start = pd.Timestamp(start_str, tz="UTC")
    end = pd.Timestamp(end_str, tz="UTC")

    pair_returns: dict[str, pd.Series] = {}
    pair_summary: dict[str, dict[str, float]] = {}
    for pair in pairs:
        path = DATA_DIR / f"{pair.replace('/', '_')}-1d.feather"
        if not path.exists():
            continue
        df = pd.read_feather(path)
        # Normalise tz so comparisons work
        if df["date"].dt.tz is None:
            df["date"] = df["date"].dt.tz_localize("UTC")
        df = df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)
        if len(df) < 2:
            continue
        df["ret"] = df["close"].pct_change()
        pair_returns[pair] = df.set_index("date")["ret"]
        first, last = df["close"].iloc[0], df["close"].iloc[-1]
        cum = (1.0 + df["ret"].fillna(0.0)).cumprod()
        dd = float((cum / cum.cummax() - 1.0).min() * 100)
        pair_summary[pair] = {
            "profit_pct": float((last / first - 1.0) * 100),
            "dd_pct": dd,
        }

    if not pair_returns:
        return {
            "sharpe": 0.0,
            "profit_total_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "per_pair": {},
        }

    # Equal-weight portfolio: average daily returns across pairs
    rets_df = pd.concat(pair_returns.values(), axis=1).fillna(0.0)
    portfolio_daily = rets_df.mean(axis=1)
    if portfolio_daily.std() > 0:
        sharpe = float(portfolio_daily.mean() / portfolio_daily.std() * DAILY_SHARPE_FACTOR)
    else:
        sharpe = 0.0
    total_profit = float(((1.0 + portfolio_daily).prod() - 1.0) * 100)
    cum = (1.0 + portfolio_daily).cumprod()
    max_dd = float((cum / cum.cummax() - 1.0).min() * 100)

    return {
        "sharpe": sharpe,
        "profit_total_pct": total_profit,
        "max_drawdown_pct": max_dd,
        "per_pair": pair_summary,
    }


# ---------------------------------------------------------------------------
# Position-size estimation (avg stake fraction across trades)
# ---------------------------------------------------------------------------
def estimate_avg_position_size_pct(results: dict[str, Any], strategy_name: str) -> float:
    """Best-effort estimate of the average stake / wallet fraction.

    Reads the trade list from FreqTrade's results, computes mean
    stake_amount / starting_balance.
    """
    strat = results.get("strategy", {}).get(strategy_name, {}) or {}
    starting_balance = float(strat.get("starting_balance") or strat.get("dry_run_wallet") or 10000.0)
    trades = strat.get("trades") or strat.get("results") or []
    if not trades or starting_balance <= 0:
        return 0.0
    stakes = []
    for t in trades:
        s = t.get("stake_amount")
        if s is None:
            continue
        try:
            stakes.append(float(s))
        except (TypeError, ValueError):
            continue
    if not stakes:
        return 0.0
    return float(np.mean(stakes)) / starting_balance * 100.0


# ---------------------------------------------------------------------------
# Pareto dominance vs prior results.tsv entries
# ---------------------------------------------------------------------------
def load_prior_robust_metrics() -> list[dict[str, Any]]:
    """Read results.tsv and return prior commits' (commit, sharpe, max_dd) rows.

    We use sharpe (already robust_sharpe in v0.4.1 schema) and max_dd from
    the existing 5-column schema. profit isn't stored in tsv so dominance
    here is on (sharpe, max_dd) only — partial Pareto, still useful.
    """
    path = PROJECT_DIR / "results.tsv"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        df = pd.read_csv(path, sep="\t", dtype={"commit": str})
    except Exception:
        return []
    if df.empty:
        return []
    # Skip rows where sharpe / max_dd are dashes or NaN (kill events)
    df = df[df["sharpe"].astype(str).str.strip().ne("-")]
    df = df[df["max_dd"].astype(str).str.strip().ne("-")]
    for _, r in df.iterrows():
        try:
            rows.append({
                "commit": str(r["commit"]),
                "strategy": str(r.get("strategy_name", "")),
                "sharpe": float(r["sharpe"]),
                "max_dd": float(r["max_dd"]),  # already negative-pct
            })
        except (ValueError, KeyError):
            continue
    return rows


def check_pareto_dominance(robust_sharpe: float, max_dd: float) -> str | None:
    """Return commit:strategy of any prior row that dominates (sharpe ≥, dd ≥).

    `max_dd` is stored as a negative percent in tsv (e.g. -8.5 means -8.5%);
    "better dd" = closer to 0 = greater value (since less negative).
    Strict dominance: at least one inequality is strict.
    """
    prior = load_prior_robust_metrics()
    for row in prior:
        if row["sharpe"] >= robust_sharpe and row["max_dd"] >= max_dd:
            if row["sharpe"] > robust_sharpe or row["max_dd"] > max_dd:
                return f"{row['commit']}:{row['strategy']}"
    return None


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------
def get_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(PROJECT_DIR),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def print_block(
    strategy_name: str,
    commit: str,
    timerange_label: str,
    timerange: str,
    pairs: list[str],
    bundle: dict[str, Any],
    bah: dict[str, Any],
) -> None:
    agg = bundle["aggregate"]
    per_pair = bundle["per_pair"]
    print("---")
    print(f"strategy:         {strategy_name}")
    print(f"timerange_label:  {timerange_label}")
    print(f"timerange:        {timerange}")
    print(f"commit:           {commit}")
    print(f"basket:           {','.join(pairs)}")
    print(f"sharpe:           {agg['sharpe']:.4f}")
    print(f"sortino:          {agg['sortino']:.4f}")
    print(f"calmar:           {agg['calmar']:.4f}")
    print(f"total_profit_pct: {agg['total_profit_pct']:.4f}")
    print(f"max_drawdown_pct: {agg['max_drawdown_pct']:.4f}")
    print(f"trade_count:      {agg['trade_count']}")
    print(f"win_rate_pct:     {agg['win_rate_pct']:.4f}")
    print(f"profit_factor:    {agg['profit_factor']:.4f}")
    print(f"bah_sharpe:       {bah['sharpe']:.4f}")
    print(f"bah_profit_pct:   {bah['profit_total_pct']:.4f}")
    print(f"bah_dd_pct:       {bah['max_drawdown_pct']:.4f}")
    print("per_pair:")
    for pair in pairs:
        m = per_pair.get(pair)
        if m is None:
            print(f"  {pair}: (no data)")
            continue
        bah_p = bah["per_pair"].get(pair, {})
        bah_str = ""
        if bah_p:
            bah_str = f" (bah_profit={bah_p['profit_pct']:.1f} bah_dd={bah_p['dd_pct']:.1f})"
        print(
            f"  {pair}: sharpe={m['sharpe']:.4f} "
            f"trades={m['trade_count']} "
            f"profit_pct={m['total_profit_pct']:.2f} "
            f"dd_pct={m['max_drawdown_pct']:.2f} "
            f"wr={m['win_rate_pct']:.1f} "
            f"pf={m['profit_factor']:.2f}"
            f"{bah_str}"
        )


def print_strategy_summary(
    strategy_name: str,
    commit: str,
    per_timerange_metrics: list[dict[str, Any]],
    avg_position_pct: float,
) -> None:
    """Final per-strategy summary block. Headline = robust_sharpe = min over all
    declared timeranges. Includes multi-objective gate flags."""
    if not per_timerange_metrics:
        return
    sharpes = [m["aggregate"]["sharpe"] for m in per_timerange_metrics]
    profits = [m["aggregate"]["total_profit_pct"] for m in per_timerange_metrics]
    dds = [m["aggregate"]["max_drawdown_pct"] for m in per_timerange_metrics]

    robust_sharpe = min(sharpes) if sharpes else 0.0
    worst_profit = min(profits) if profits else 0.0
    worst_dd = min(dds) if dds else 0.0  # most negative

    profit_floor_pass = all(p >= PROFIT_FLOOR_PCT for p in profits)
    min_pos_pass = avg_position_pct >= MIN_POSITION_SIZE_PCT
    pareto_dom = check_pareto_dominance(robust_sharpe, worst_dd)

    print("---")
    print(f"strategy:         {strategy_name}")
    print(f"timerange_label:  SUMMARY")
    print(f"commit:           {commit}")
    print(f"robust_sharpe:    {robust_sharpe:.4f}   # min across declared timeranges")
    print(f"worst_profit_pct: {worst_profit:.4f}")
    print(f"worst_dd_pct:     {worst_dd:.4f}")
    print(f"avg_position_pct: {avg_position_pct:.4f}")
    print(f"profit_floor:     {'PASS' if profit_floor_pass else 'FAIL'}   "
          f"(threshold ≥ {PROFIT_FLOOR_PCT}% per timerange)")
    print(f"min_position_size: {'PASS' if min_pos_pass else 'FAIL'}   "
          f"(threshold ≥ {MIN_POSITION_SIZE_PCT}%)")
    if pareto_dom:
        print(f"pareto_dominated_by: {pareto_dom}")
    else:
        print(f"pareto_dominated_by: none (non-dominated)")


def print_error(
    strategy_name: str,
    commit: str,
    timerange_label: str,
    timerange: str,
    err: BaseException,
) -> None:
    print("---")
    print(f"strategy:         {strategy_name}")
    print(f"timerange_label:  {timerange_label}")
    print(f"timerange:        {timerange}")
    print(f"commit:           {commit}")
    print(f"status:           ERROR")
    print(f"error_type:       {type(err).__name__}")
    print(f"error_msg:        {err}")
    print("traceback:")
    print(traceback.format_exc())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    strategies = discover_strategies()
    if not strategies:
        print(
            f"ERROR: no strategies found in {STRATEGIES_DIR}.\n"
            "Create at least one `.py` file under user_data/strategies/ "
            "(see user_data/strategies/_template.py.example for the skeleton).",
            file=sys.stderr,
        )
        return 2

    commit = get_commit()
    print(f"Discovered {len(strategies)} strategies: {', '.join(strategies)}")
    print(f"Whitelist:   {PAIRS_STR}")
    print(f"Default TR:  {DEFAULT_TIMERANGE}")
    print()

    n_ok_total = 0
    n_err_total = 0

    for name in strategies:
        try:
            pair_basket, test_timeranges = get_strategy_overrides(name)
        except Exception as err:
            print_error(name, commit, "SETUP", "n/a", err)
            n_err_total += 1
            print()
            continue

        active_pairs = list(pair_basket) if pair_basket else list(PAIRS)
        per_timerange_metrics: list[dict[str, Any]] = []
        per_timerange_results: list[dict[str, Any]] = []

        for label, timerange in test_timeranges:
            try:
                results = run_backtest(name, timerange, pair_basket)
                bundle = extract_metrics(results, name, active_pairs)
                bah = compute_bah_benchmark(timerange, active_pairs)
                print_block(name, commit, label, timerange, active_pairs, bundle, bah)
                per_timerange_metrics.append(bundle)
                per_timerange_results.append(results)
                n_ok_total += 1
            except BaseException as err:
                print_error(name, commit, label, timerange, err)
                n_err_total += 1
            print()

        # Summary block: aggregate across timeranges
        if per_timerange_metrics:
            # Average position size estimate from the first successful backtest
            avg_pos = 0.0
            for r in per_timerange_results:
                est = estimate_avg_position_size_pct(r, name)
                if est > 0:
                    avg_pos = est
                    break
            print_strategy_summary(name, commit, per_timerange_metrics, avg_pos)
            print()

    print(f"Done: {n_ok_total} backtests succeeded, {n_err_total} failed.")
    return 0 if n_err_total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
