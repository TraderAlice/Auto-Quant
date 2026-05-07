"""
run.py — READ-ONLY. The oracle. Do not modify.

Discovers every `.py` file in `user_data/strategies/` (except those starting
with `_`), runs FreqTrade's Backtesting in-process for each, and prints one
`---` summary block per strategy to stdout. Each block contains the
portfolio aggregate metrics plus a per-pair breakdown (5 pairs as of v0.3.0).

The agent reads these blocks to decide keep/evolve/fork/kill actions on each
strategy. Per-pair metrics let the agent see which paradigms work on which
assets — previous versions (v0.1.0, v0.2.0) only exposed a single aggregate
number that hid asset-specific behaviour.

A single strategy's crash produces an error block for that strategy but
does NOT abort the others.

Usage:
    uv run run.py > run.log 2>&1
    grep "^---\\|^strategy:\\|^sharpe:\\|^trade_count:" run.log  # compact scan
    awk '/^---$/,/^$/' run.log                                   # full block incl per-pair
"""

from __future__ import annotations

import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

from freqtrade.configuration import Configuration
from freqtrade.enums import RunMode
from freqtrade.optimize.backtesting import Backtesting

# ---------------------------------------------------------------------------
# Fixed constants. Do not modify.
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).parent.resolve()
USER_DATA = PROJECT_DIR / "user_data"
STRATEGIES_DIR = USER_DATA / "strategies"
CONFIG = PROJECT_DIR / "config.json"
TIMERANGE = "20210101-20251231"
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "AVAX/USDT"]
PAIRS_STR = ",".join(PAIRS)


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


def discover_strategies() -> list[str]:
    """Return class names for every strategy file in strategies/, skipping
    files that start with `_` (reserved for templates, etc.)."""
    if not STRATEGIES_DIR.exists():
        return []
    names = []
    for path in sorted(STRATEGIES_DIR.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        # FreqTrade's StrategyResolver assumes class name == file stem
        names.append(path.stem)
    return names


def run_backtest(strategy_name: str) -> dict[str, Any]:
    args = {
        "config": [str(CONFIG)],
        "user_data_dir": str(USER_DATA),
        "datadir": str(USER_DATA / "data"),
        "strategy": strategy_name,
        "strategy_path": str(STRATEGIES_DIR),
        "timerange": TIMERANGE,
        "export": "none",
        "exportfilename": None,
        "cache": "none",
    }
    config = Configuration(args, RunMode.BACKTEST).get_config()
    bt = Backtesting(config)
    bt.start()
    return bt.results


def _get(d: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return float(d[k])
            except (TypeError, ValueError):
                continue
    return default


def _entry_metrics(entry: dict[str, Any]) -> dict[str, float]:
    """Extract canonical metrics from one results_per_pair entry (incl. TOTAL row).

    max_drawdown_account is a ratio 0..1 — convert to signed percent.
    profit_total_pct is already a percent (e.g., 12.34).
    winrate is a ratio — convert to percent.
    """
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


def extract_metrics(results: dict[str, Any], strategy_name: str) -> dict[str, Any]:
    """Return aggregate + per-pair metrics.

    FreqTrade stores results as:
        results["strategy"][<name>]["results_per_pair"] = [
            {key: "BTC/USDT", sharpe: ..., trades: ..., ...},
            {key: "ETH/USDT", ...},
            ...
            {key: "TOTAL", ...},  # last row is aggregate
        ]
    """
    strat = results.get("strategy", {}).get(strategy_name, {}) or {}
    per_pair_list = strat.get("results_per_pair", []) or []

    aggregate = {}
    per_pair: dict[str, dict[str, float]] = {}
    for entry in per_pair_list:
        key = entry.get("key", "")
        metrics = _entry_metrics(entry)
        if key == "TOTAL":
            aggregate = metrics
        elif key:
            per_pair[key] = metrics

    # Fallback: if results_per_pair wasn't populated (older freqtrade, edge case),
    # take top-level strat fields as aggregate.
    if not aggregate:
        aggregate = _entry_metrics(strat)

    return {"aggregate": aggregate, "per_pair": per_pair}


def print_summary(strategy_name: str, commit: str, bundle: dict[str, Any]) -> None:
    agg = bundle["aggregate"]
    per_pair = bundle["per_pair"]
    print("---")
    print(f"strategy:         {strategy_name}")
    print(f"commit:           {commit}")
    print(f"timerange:        {TIMERANGE}")
    print(f"sharpe:           {agg['sharpe']:.4f}")
    print(f"sortino:          {agg['sortino']:.4f}")
    print(f"calmar:           {agg['calmar']:.4f}")
    print(f"total_profit_pct: {agg['total_profit_pct']:.4f}")
    print(f"max_drawdown_pct: {agg['max_drawdown_pct']:.4f}")
    print(f"trade_count:      {agg['trade_count']}")
    print(f"win_rate_pct:     {agg['win_rate_pct']:.4f}")
    print(f"profit_factor:    {agg['profit_factor']:.4f}")
    print(f"pairs:            {PAIRS_STR}")
    print("per_pair:")
    for pair in PAIRS:  # preserve whitelist order
        m = per_pair.get(pair)
        if m is None:
            print(f"  {pair}: (no data)")
            continue
        print(
            f"  {pair}: sharpe={m['sharpe']:.4f} "
            f"trades={m['trade_count']} "
            f"profit_pct={m['total_profit_pct']:.2f} "
            f"dd_pct={m['max_drawdown_pct']:.2f} "
            f"wr={m['win_rate_pct']:.1f} "
            f"pf={m['profit_factor']:.2f}"
        )


def print_error(strategy_name: str, commit: str, err: BaseException) -> None:
    print("---")
    print(f"strategy:         {strategy_name}")
    print(f"commit:           {commit}")
    print(f"status:           ERROR")
    print(f"error_type:       {type(err).__name__}")
    print(f"error_msg:        {err}")
    print("traceback:")
    print(traceback.format_exc())


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
    print(f"Timerange: {TIMERANGE}  Pairs: {PAIRS_STR}")
    print()

    n_ok = 0
    n_err = 0
    for name in strategies:
        try:
            results = run_backtest(name)
            bundle = extract_metrics(results, name)
            print_summary(name, commit, bundle)
            n_ok += 1
        except BaseException as err:  # catch everything incl. SystemExit
            print_error(name, commit, err)
            n_err += 1
        print()  # blank line between strategy blocks

    print(f"Done: {n_ok} succeeded, {n_err} failed.")
    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
