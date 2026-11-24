"""
run.py — READ-ONLY during runs. The v0.5.2 Portfolio & Multi-Regime Oracle
(Daily MTM + 1x Futures Long/Short + Configurable Train/Test Split).

Bench constants (`BENCH_FEE`, `MAX_LEVERAGE`, `DATA_TIMERANGE`, `SPLIT_DATE`)
are defined at the top of this file (human-editable before starting a run;
immutable during the run). `prepare.py` reads `DATA_TIMERANGE` / `SPLIT_DATE`
from here as the single source of truth.

For each strategy in `user_data/strategies/`, runs FreqTrade's Backtesting
in-process across the active split's timeranges and pair baskets, enforces the
configured `MAX_LEVERAGE` ceiling (default 1.0x — unleveraged long/short),
reconstructs true daily Mark-to-Market (MTM) portfolio equity curves (realized
PnL incl. funding + end-of-day unrealized PnL of all open long/short positions
valued at 1d UTC closes, fee-inclusive), and emits:

1. Per-(strategy, timerange) blocks with:
   - True daily MTM equity-curve metrics: `daily_sharpe`, `daily_sortino`,
     `cagr_pct`, `calmar`, `ulcer_index`, `martin_ratio`, `max_drawdown_pct`
     (`mtm_dd` vs `ft_realized_dd`), `max_dd_days`, plus legacy `ft_sharpe`
   - Benchmark decomposition vs equal-weight Buy-and-Hold (`bah_*`):
     `alpha_ann_pct`, `beta`, `info_ratio`
   - Long / short decomposition (`sides`: long/short trade counts, profit %,
     net `funding_fees`, and `max_lev`)
   - Capital utilization & breadth (`avg_pos_pct`, `time_in_market_pct`,
     `capital_util_pct`, `effective_pairs`) + per-pair breakdown

2. Per-strategy `SUMMARY` block across regimes (`robust_sharpe`,
   `robust_sortino`, calibrated multi-objective gates, 3D kill-aware Pareto)

3. Cross-strategy `PORTFOLIO_SUMMARY` block (`PORTFOLIO_EQ` equal-weight
   daily-MTM rollup, correlations, leave-one-out marginal contributions)

Usage:
    uv run run.py > run.log 2>&1    # Train split (< SPLIT_DATE, default for agent)
    uv run run.py --oos             # Out-of-sample test split (>= SPLIT_DATE, human only)
    awk '/^---$/,/^$/' run.log
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from freqtrade.configuration import Configuration
from freqtrade.enums import RunMode
from freqtrade.optimize.backtesting import Backtesting

# ---------------------------------------------------------------------------
# Bench constants — edit before starting a run; READ-ONLY during runs.
# Single source of truth (prepare.py imports DATA_TIMERANGE / SPLIT_DATE).
# ---------------------------------------------------------------------------
BENCH_FEE: float = 0.001                   # per-side trading commission (0.001 = 0.10%/side)
MAX_LEVERAGE: float = 1.0                  # hard leverage ceiling (1.0x = unleveraged long/short)
DATA_TIMERANGE: str = "20210101-20261124"  # full downloaded dataset range
SPLIT_DATE: str = "20260101"               # train (< SPLIT_DATE) vs OOS test (>= SPLIT_DATE)

# ---------------------------------------------------------------------------
# Paths & exchange wiring (loaded from config.json)
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).parent.resolve()
USER_DATA = PROJECT_DIR / "user_data"
DATA_DIR = USER_DATA / "data"
STRATEGIES_DIR = USER_DATA / "strategies"
CONFIG = PROJECT_DIR / "config.json"


def _load_exchange_wiring() -> tuple[list[str], str]:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    pairs = list(cfg.get("exchange", {}).get("pair_whitelist") or [])
    trading_mode = str(cfg.get("trading_mode", "futures"))
    return pairs, trading_mode


PAIRS, TRADING_MODE = _load_exchange_wiring()
PAIRS_STR = ",".join(PAIRS)

# Historical regime templates intersected with the configured train window
_REGIME_TEMPLATES: list[tuple[str, str, str]] = [
    ("bull_2021", "20210101", "20211231"),
    ("winter_2022", "20220101", "20221231"),
    ("recovery_23_25", "20230101", "20251231"),
    ("post_2025", "20260101", "20991231"),
]


def _fmt_ymd(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y%m%d")


def build_split_timeranges(
    split: str = "train",
    data_timerange: str | None = None,
    split_date: str | None = None,
) -> list[tuple[str, str]]:
    """Build evaluation (label, timerange) list from bench constants and split."""
    dtr = data_timerange or DATA_TIMERANGE
    sdate = split_date or SPLIT_DATE
    d_start_str, d_end_str = dtr.split("-", 1)
    d_start = pd.Timestamp(d_start_str, tz="UTC").normalize()
    d_end = pd.Timestamp(d_end_str, tz="UTC").normalize()
    sp = pd.Timestamp(sdate, tz="UTC").normalize()

    if split == "test":
        if sp > d_end:
            raise ValueError(
                f"SPLIT_DATE ({sdate}) is after DATA_TIMERANGE end ({d_end_str}); "
                "update DATA_TIMERANGE / SPLIT_DATE at the top of run.py."
            )
        return [("oos_test", f"{_fmt_ymd(max(d_start, sp))}-{_fmt_ymd(d_end)}")]

    # Train split: [d_start, min(d_end, split_date - 1 day)]
    train_end = min(d_end, sp - pd.Timedelta(days=1))
    if train_end < d_start + pd.Timedelta(days=30):
        raise ValueError(
            f"Train window [{_fmt_ymd(d_start)}..{_fmt_ymd(train_end)}] is too short; "
            "check DATA_TIMERANGE and SPLIT_DATE at the top of run.py."
        )

    out: list[tuple[str, str]] = []
    for lbl, r_s, r_e in _REGIME_TEMPLATES:
        rs = max(d_start, pd.Timestamp(r_s, tz="UTC").normalize())
        re = min(train_end, pd.Timestamp(r_e, tz="UTC").normalize())
        if (re - rs).days >= 60:
            out.append((lbl, f"{_fmt_ymd(rs)}-{_fmt_ymd(re)}"))

    full_tr = f"{_fmt_ymd(d_start)}-{_fmt_ymd(train_end)}"
    full_label = "full_5y" if full_tr == "20210101-20251231" else "full_train"
    if not out or out[-1][1] != full_tr:
        out.append((full_label, full_tr))
    return out


CANONICAL_TIMERANGES: list[tuple[str, str]] = build_split_timeranges("train")
DEFAULT_TIMERANGE = CANONICAL_TIMERANGES[-1][1]

# Multi-objective gates (v0.5.0 calibrated)
BULL_PROFIT_FLOOR_PCT = 10.0       # bull/recovery (BaH >= 0) minimum profit %
FULL_PROFIT_FLOOR_PCT = 20.0       # multi-year full window (>= 4y) minimum profit %
BEAR_PRESERVATION_FLOOR_PCT = -2.0 # bear window (BaH < 0) capital preservation floor %
MIN_POSITION_SIZE_PCT = 5.0        # worst-regime avg trade stake / wallet >= 5%
MIN_TIME_IN_MARKET_PCT = 2.0       # full-window time with >= 1 open trade >= 2%
MAX_PAIRWISE_CORR = 0.60           # cross-strategy daily return correlation ceiling

DAILY_SHARPE_FACTOR = math.sqrt(365.0)


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


def get_strategy_overrides(
    name: str,
    default_timeranges: list[tuple[str, str]] | None = None,
    force_timeranges: bool = False,
) -> tuple[list[str] | None, list[tuple[str, str]]]:
    """Return (pair_basket, test_timeranges) declared by the strategy class.

    Defaults to full configured whitelist + active split timeranges so
    cross-strategy portfolio rollups align automatically. When running `--oos`
    or `--timerange`, `force_timeranges=True` overrides any class attribute.
    """
    cls = load_strategy_class(name)
    pair_basket = getattr(cls, "pair_basket", None)
    base_trs = list(default_timeranges) if default_timeranges else list(CANONICAL_TIMERANGES)
    test_timeranges = base_trs if force_timeranges else (getattr(cls, "test_timeranges", None) or base_trs)
    if pair_basket is not None:
        for p in pair_basket:
            if p not in PAIRS:
                hint = (
                    f" (futures mode requires ':USDT' suffix, e.g. '{p}:USDT')"
                    if TRADING_MODE == "futures" and f"{p}:USDT" in PAIRS
                    else ""
                )
                raise ValueError(
                    f"{name}: pair_basket entry {p!r} not in whitelist {PAIRS}{hint}"
                )
    for label, tr in test_timeranges:
        if "-" not in tr or len(tr) < 11:
            raise ValueError(
                f"{name}: test_timerange {label!r} = {tr!r} is malformed; "
                'expected "YYYYMMDD-YYYYMMDD"'
            )
    return pair_basket, test_timeranges


from freqtrade.resolvers import ExchangeResolver

_SHARED_EXCHANGE = None


def _get_shared_exchange(config: dict[str, Any]):
    global _SHARED_EXCHANGE
    if _SHARED_EXCHANGE is None:
        _SHARED_EXCHANGE = ExchangeResolver.load_exchange(config, load_leverage_tiers=True)
    return _SHARED_EXCHANGE


# ---------------------------------------------------------------------------
# Backtest invocation
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
    config["fee"] = BENCH_FEE
    exchange = _get_shared_exchange(config)
    if pair_basket:
        config["exchange"]["pair_whitelist"] = list(pair_basket)
    bt = Backtesting(config, exchange=exchange)
    bt.start()
    return bt.results


# ---------------------------------------------------------------------------
# Time Grid & Equity Curve Portfolio Analytics
# ---------------------------------------------------------------------------
def _timerange_bounds(timerange: str) -> tuple[pd.Timestamp, pd.Timestamp, pd.DatetimeIndex]:
    start_str, end_str = timerange.split("-", 1)
    start = pd.Timestamp(start_str, tz="UTC").normalize()
    end = pd.Timestamp(end_str, tz="UTC").normalize()
    days = pd.date_range(start=start, end=end, freq="1D", tz="UTC")
    return start, end, days


def compute_curve_metrics(daily_ret: pd.Series) -> dict[str, float]:
    """Compute comprehensive portfolio metrics from a daily return series."""
    r = daily_ret.fillna(0.0).astype(float)
    n_days = len(r)
    if n_days < 2:
        return {
            "daily_sharpe": 0.0,
            "daily_sortino": 0.0,
            "total_profit_pct": 0.0,
            "cagr_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "max_dd_days": 0.0,
            "calmar": 0.0,
            "ulcer_index": 0.0,
            "martin_ratio": 0.0,
            "ann_vol_pct": 0.0,
        }

    mean_r = float(r.mean())
    std_r = float(r.std(ddof=1))
    daily_sharpe = (mean_r / std_r * DAILY_SHARPE_FACTOR) if std_r > 1e-12 else 0.0

    downside_sq = np.minimum(r.to_numpy(), 0.0) ** 2
    downside_dev = float(np.sqrt(np.mean(downside_sq)))
    if downside_dev > 1e-12:
        daily_sortino = mean_r / downside_dev * DAILY_SHARPE_FACTOR
    elif mean_r > 0:
        daily_sortino = daily_sharpe * 2.0
    else:
        daily_sortino = 0.0

    equity = (1.0 + r).cumprod()
    # Prepend 1.0 so drawdowns from initial capital on day 1 are captured
    eq_with_start = pd.concat(
        [pd.Series([1.0], index=[r.index[0] - pd.Timedelta(days=1)]), equity]
    )
    running_max = eq_with_start.cummax()
    dd_series = (eq_with_start / running_max - 1.0) * 100.0  # negative pct
    dd_days_only = dd_series.iloc[1:]

    total_mult = float(equity.iloc[-1])
    total_profit_pct = (total_mult - 1.0) * 100.0
    years = max(n_days / 365.0, 1.0 / 365.0)
    cagr_pct = ((max(total_mult, 1e-9) ** (1.0 / years)) - 1.0) * 100.0

    max_dd_pct = float(dd_days_only.min())  # <= 0.0
    ulcer_index = float(np.sqrt(np.mean(dd_days_only.to_numpy() ** 2)))

    # Longest underwater streak (days strictly below previous peak by > 1e-6%)
    underwater = (dd_days_only < -1e-6).to_numpy()
    max_streak = 0
    cur_streak = 0
    for uw in underwater:
        if uw:
            cur_streak += 1
            if cur_streak > max_streak:
                max_streak = cur_streak
        else:
            cur_streak = 0

    calmar = (cagr_pct / abs(max_dd_pct)) if abs(max_dd_pct) > 1e-6 else 0.0
    martin_ratio = (cagr_pct / ulcer_index) if ulcer_index > 1e-6 else 0.0
    ann_vol_pct = std_r * DAILY_SHARPE_FACTOR * 100.0

    return {
        "daily_sharpe": daily_sharpe,
        "daily_sortino": daily_sortino,
        "total_profit_pct": total_profit_pct,
        "cagr_pct": cagr_pct,
        "max_drawdown_pct": max_dd_pct,
        "max_dd_days": float(max_streak),
        "calmar": calmar,
        "ulcer_index": ulcer_index,
        "martin_ratio": martin_ratio,
        "ann_vol_pct": ann_vol_pct,
    }


def compute_benchmark_decomposition(
    strat_ret: pd.Series,
    bah_ret: pd.Series,
) -> dict[str, float]:
    """OLS Alpha/Beta decomposition + Information Ratio vs equal-weight BaH."""
    df = pd.concat([strat_ret.rename("s"), bah_ret.rename("b")], axis=1).fillna(0.0)
    if len(df) < 2:
        return {"alpha_ann_pct": 0.0, "beta": 0.0, "info_ratio": 0.0}

    s = df["s"].to_numpy(dtype=float)
    b = df["b"].to_numpy(dtype=float)
    var_b = float(np.var(b, ddof=1))
    if var_b > 1e-12:
        cov_sb = float(np.cov(s, b, ddof=1)[0, 1])
        beta = cov_sb / var_b
    else:
        beta = 0.0

    alpha_daily = float(np.mean(s) - beta * np.mean(b))
    alpha_ann_pct = (math.expm1(alpha_daily * 365.0)) * 100.0 if alpha_daily > -0.5 else -100.0

    active = s - b
    active_std = float(np.std(active, ddof=1))
    info_ratio = (
        float(np.mean(active)) / active_std * DAILY_SHARPE_FACTOR
        if active_std > 1e-12
        else 0.0
    )
    return {
        "alpha_ann_pct": alpha_ann_pct,
        "beta": beta,
        "info_ratio": info_ratio,
    }


# ---------------------------------------------------------------------------
# Cached 1d OHLCV closes (UTC EOD close for each day)
# ---------------------------------------------------------------------------
_DAILY_CLOSE_CACHE: dict[str, pd.Series | None] = {}


def _daily_close_path(pair: str) -> Path:
    stem = pair.replace("/", "_").replace(":", "_")
    if TRADING_MODE == "futures":
        fut = DATA_DIR / "futures" / f"{stem}-1d-futures.feather"
        if fut.exists():
            return fut
    return DATA_DIR / f"{stem}-1d.feather"


def _load_daily_close(pair: str) -> pd.Series | None:
    """Load UTC end-of-day close series indexed by normalized UTC day."""
    if pair in _DAILY_CLOSE_CACHE:
        return _DAILY_CLOSE_CACHE[pair]
    path = _daily_close_path(pair)
    if not path.exists():
        _DAILY_CLOSE_CACHE[pair] = None
        return None
    df = pd.read_feather(path, columns=["date", "close"])
    if df.empty:
        _DAILY_CLOSE_CACHE[pair] = None
        return None
    dates = pd.to_datetime(df["date"])
    if dates.dt.tz is None:
        dates = dates.dt.tz_localize("UTC")
    else:
        dates = dates.dt.tz_convert("UTC")
    df = df.assign(day=dates.dt.normalize()).drop_duplicates("day").sort_values("day")
    series = df.set_index("day")["close"].astype(float)
    _DAILY_CLOSE_CACHE[pair] = series
    return series


def _aligned_daily_close(pair: str, days: pd.DatetimeIndex) -> np.ndarray | None:
    """Return float ndarray of EOD close prices aligned to `days` (ffill/bfill safe)."""
    series = _load_daily_close(pair)
    if series is None or series.empty:
        return None
    # Reindex over union so leading days before window start can ffill cleanly
    aligned = series.reindex(days.union(series.index)).sort_index().ffill().bfill().reindex(days)
    if aligned.isna().any():
        return None
    return aligned.to_numpy(dtype=float)


# ---------------------------------------------------------------------------
# Buy-and-hold benchmark — equal-weight portfolio over 1d feathers
# ---------------------------------------------------------------------------
def compute_bah_benchmark(
    timerange: str,
    pairs: list[str],
) -> dict[str, Any]:
    start, end, days = _timerange_bounds(timerange)
    pair_returns: dict[str, pd.Series] = {}
    pair_summary: dict[str, dict[str, float]] = {}

    for pair in pairs:
        close_s = _load_daily_close(pair)
        if close_s is None:
            continue
        sub = close_s[(close_s.index >= start) & (close_s.index <= end)]
        if len(sub) < 2:
            continue
        ret = sub.pct_change().fillna(0.0)
        aligned_ret = ret.reindex(days, fill_value=0.0)
        pair_returns[pair] = aligned_ret

        first, last = float(sub.iloc[0]), float(sub.iloc[-1])
        cum = (1.0 + aligned_ret).cumprod()
        dd = float((cum / cum.cummax() - 1.0).min() * 100.0)
        pair_summary[pair] = {
            "profit_pct": (last / first - 1.0) * 100.0,
            "dd_pct": dd,
        }

    if not pair_returns:
        zero_series = pd.Series(0.0, index=days)
        return {
            "daily_ret": zero_series,
            "sharpe": 0.0,
            "sortino": 0.0,
            "profit_total_pct": 0.0,
            "cagr_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "per_pair": {},
        }

    rets_df = pd.concat(pair_returns.values(), axis=1).fillna(0.0)
    portfolio_daily = rets_df.mean(axis=1).reindex(days, fill_value=0.0)
    curve = compute_curve_metrics(portfolio_daily)

    return {
        "daily_ret": portfolio_daily,
        "sharpe": curve["daily_sharpe"],
        "sortino": curve["daily_sortino"],
        "profit_total_pct": curve["total_profit_pct"],
        "cagr_pct": curve["cagr_pct"],
        "max_drawdown_pct": curve["max_drawdown_pct"],
        "per_pair": pair_summary,
    }


# ---------------------------------------------------------------------------
# Strategy Metric Extraction (Daily Curve + Utilization + Per-Pair HHI)
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
        "ft_sharpe": _get(entry, "sharpe", "sharpe_ratio"),
        "ft_sortino": _get(entry, "sortino", "sortino_ratio"),
        "ft_calmar": _get(entry, "calmar", "calmar_ratio"),
        "total_profit_pct": _get(entry, "profit_total_pct"),
        "profit_total_abs": _get(entry, "profit_total_abs"),
        "max_drawdown_pct": -abs(_get(entry, "max_drawdown_account")) * 100.0,
        "trade_count": int(_get(entry, "trades", "total_trades")),
        "win_rate_pct": _get(entry, "winrate") * 100.0,
        "profit_factor": _get(entry, "profit_factor"),
    }


def _to_utc_ts(val: Any) -> pd.Timestamp | None:
    if val is None:
        return None
    try:
        ts = pd.Timestamp(val)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts
    except Exception:
        return None


def _add_trade_unrealized_mtm(
    trade: dict[str, Any],
    start: pd.Timestamp,
    i0: int,
    i1: int,
    close_arr: np.ndarray,
    unrealized_arr: np.ndarray,
) -> None:
    """Add fee-inclusive EOD mark-to-market unrealized PnL for an open trade on days [i0, i1).

    Matches FreqTrade's `LocalTrade.calculate_profit(rate)` mark-to-liquidation
    convention (open fee sunk at entry + estimated close fee at EOD close).
    Handles both standard single-entry trades (vectorized) and multi-order
    position-adjusted (DCA / partial-exit) trades via `trade["orders"]`.
    """
    is_short = bool(trade.get("is_short", False))
    fee_open = _get(trade, "fee_open", default=0.0)
    fee_close = _get(trade, "fee_close", default=0.0)
    orders = trade.get("orders")

    # Multi-order trade (position adjustments / partial exits): replay fills by day
    if isinstance(orders, list) and len(orders) > 2:
        parsed_orders: list[tuple[int, bool, float, float]] = []
        for o in orders:
            ts_ms = o.get("order_filled_timestamp")
            if ts_ms is None:
                continue
            try:
                f_day = pd.Timestamp(int(ts_ms), unit="ms", tz="UTC").normalize()
            except Exception:
                continue
            f_idx = int((f_day - start).days)
            amt = _get(o, "amount", default=0.0)
            price = _get(o, "safe_price", "average", "price", default=0.0)
            if amt <= 0.0 or price <= 0.0:
                continue
            is_entry = bool(o.get("ft_is_entry", True))
            parsed_orders.append((f_idx, is_entry, amt, price))

        if parsed_orders:
            parsed_orders.sort(key=lambda x: x[0])
            qty = 0.0
            cash_delta = 0.0
            o_ptr = 0
            n_ord = len(parsed_orders)
            for k in range(i0, i1):
                while o_ptr < n_ord and parsed_orders[o_ptr][0] <= k:
                    _, is_entry, amt, price = parsed_orders[o_ptr]
                    if not is_short:
                        if is_entry:
                            qty += amt
                            cash_delta -= amt * price * (1.0 + fee_open)
                        else:
                            qty -= amt
                            cash_delta += amt * price * (1.0 - fee_close)
                    else:
                        if is_entry:
                            qty += amt
                            cash_delta += amt * price * (1.0 - fee_open)
                        else:
                            qty -= amt
                            cash_delta -= amt * price * (1.0 + fee_close)
                    o_ptr += 1

                if qty > 1e-12:
                    p_d = close_arr[k]
                    if not is_short:
                        unrealized_arr[k] += cash_delta + qty * p_d * (1.0 - fee_close)
                    else:
                        unrealized_arr[k] += cash_delta - qty * p_d * (1.0 + fee_close)
                else:
                    unrealized_arr[k] += cash_delta
            return

    # Standard single-entry trade (fast vectorized path)
    open_rate = _get(trade, "open_rate", default=0.0)
    qty = _get(trade, "amount", default=0.0)
    if qty <= 0.0:
        stake = _get(trade, "stake_amount", default=0.0)
        qty = (stake / open_rate) if (stake > 0.0 and open_rate > 0.0) else 0.0
    if qty <= 0.0 or open_rate <= 0.0:
        return

    prices = close_arr[i0:i1]
    if not is_short:
        open_val = qty * open_rate * (1.0 + fee_open)
        unrealized_arr[i0:i1] += qty * prices * (1.0 - fee_close) - open_val
    else:
        open_val = qty * open_rate * (1.0 - fee_open)
        unrealized_arr[i0:i1] += open_val - qty * prices * (1.0 + fee_close)


def extract_strategy_bundle(
    results: dict[str, Any],
    strategy_name: str,
    timerange: str,
    pairs: list[str],
    bah: dict[str, Any],
) -> dict[str, Any]:
    start, end, days = _timerange_bounds(timerange)
    n_days = len(days)
    win_end_inclusive = end + pd.Timedelta(days=1)
    total_win_secs = max(1.0, (win_end_inclusive - start).total_seconds())

    strat = results.get("strategy", {}).get(strategy_name, {}) or {}
    starting_balance = float(
        strat.get("starting_balance") or strat.get("dry_run_wallet") or 10000.0
    )
    if starting_balance <= 0:
        starting_balance = 10000.0

    # Per-pair & legacy FreqTrade stats
    per_pair_list = strat.get("results_per_pair", []) or []
    ft_agg: dict[str, float] = {}
    per_pair: dict[str, dict[str, float]] = {}
    for entry in per_pair_list:
        key = entry.get("key", "")
        m = _entry_metrics(entry)
        if key == "TOTAL":
            ft_agg = m
        elif key:
            per_pair[key] = m
    if not ft_agg:
        ft_agg = _entry_metrics(strat)

    # Reconstruct true daily Mark-to-Market equity curve & utilization from trade records
    trades = strat.get("trades") or []
    realized_daily = np.zeros(n_days, dtype=float)
    unrealized_daily = np.zeros(n_days, dtype=float)
    pair_close_cache: dict[str, np.ndarray | None] = {}
    stakes: list[float] = []
    deployed_dollar_secs = 0.0
    intervals: list[tuple[float, float]] = []

    win_start_epoch = start.timestamp()
    win_end_epoch = win_end_inclusive.timestamp()

    long_trades = 0
    short_trades = 0
    long_profit_abs = 0.0
    short_profit_abs = 0.0
    funding_fees_abs = 0.0
    max_leverage_seen = 1.0

    for t in trades:
        lev = _get(t, "leverage", default=1.0)
        if lev > max_leverage_seen:
            max_leverage_seen = lev
        if lev > MAX_LEVERAGE + 1e-6:
            raise ValueError(
                f"{strategy_name}: trade leverage {lev:.2f}x exceeds bench "
                f"MAX_LEVERAGE={MAX_LEVERAGE:.2f}x (locked in run.py)"
            )

        p_abs = _get(t, "profit_abs", default=0.0)
        funding_fees_abs += _get(t, "funding_fees", default=0.0)
        if bool(t.get("is_short", False)):
            short_trades += 1
            short_profit_abs += p_abs
        else:
            long_trades += 1
            long_profit_abs += p_abs

        stake = _get(t, "stake_amount", default=0.0)
        if stake > 0:
            stakes.append(stake)

        open_ts = _to_utc_ts(t.get("open_date"))
        close_ts = _to_utc_ts(t.get("close_date"))

        c_idx: int | None = None
        if close_ts is not None:
            c_idx = int((close_ts.normalize() - start).days)
            if 0 <= c_idx < n_days:
                realized_daily[c_idx] += p_abs
            elif c_idx < 0:
                realized_daily[0] += p_abs
            # Note: if c_idx >= n_days (closed after window end), leave realized
            # out of this window and mark the open position through EOD of `end`.

        # Mark open position at EOD UTC close on every day `d` with open_day <= d < close_day
        if open_ts is not None and n_days > 0:
            o_idx = int((open_ts.normalize() - start).days)
            end_open_idx = c_idx if c_idx is not None else n_days
            i0 = max(0, o_idx)
            i1 = min(n_days, end_open_idx)
            if i1 > i0:
                pair = str(t.get("pair") or "")
                if pair:
                    if pair not in pair_close_cache:
                        pair_close_cache[pair] = _aligned_daily_close(pair, days)
                    close_arr = pair_close_cache[pair]
                    if close_arr is not None:
                        _add_trade_unrealized_mtm(
                            t, start, i0, i1, close_arr, unrealized_daily
                        )

        if open_ts is not None and close_ts is not None:
            o_ep = max(win_start_epoch, open_ts.timestamp())
            c_ep = min(win_end_epoch, close_ts.timestamp())
            if c_ep > o_ep:
                dur = c_ep - o_ep
                deployed_dollar_secs += stake * dur
                intervals.append((o_ep, c_ep))

    # Merge overlapping intervals for exact time-in-market %
    merged_secs = 0.0
    if intervals:
        intervals.sort(key=lambda x: x[0])
        cur_s, cur_e = intervals[0]
        for s_ep, e_ep in intervals[1:]:
            if s_ep <= cur_e:
                cur_e = max(cur_e, e_ep)
            else:
                merged_secs += cur_e - cur_s
                cur_s, cur_e = s_ep, e_ep
        merged_secs += cur_e - cur_s

    time_in_market_pct = (merged_secs / total_win_secs) * 100.0
    capital_util_pct = (deployed_dollar_secs / (starting_balance * total_win_secs)) * 100.0
    avg_pos_pct = (float(np.mean(stakes)) / starting_balance * 100.0) if stakes else 0.0

    # Telescoping daily MTM return series: (1 + r).prod() == final_equity / starting_balance
    equity_vals = starting_balance + np.cumsum(realized_daily) + unrealized_daily
    equity = pd.Series(equity_vals, index=days).clip(lower=1e-6)
    prev_eq = pd.Series(
        [starting_balance] + equity.iloc[:-1].tolist(),
        index=days,
    ).clip(lower=1e-6)
    daily_ret = (equity - prev_eq) / prev_eq

    curve = compute_curve_metrics(daily_ret)
    decomp = compute_benchmark_decomposition(daily_ret, bah["daily_ret"])

    # Effective number of contributing pairs (1 / HHI over |PnL_pair|)
    abs_pnls = [abs(per_pair[p]["profit_total_abs"]) for p in pairs if p in per_pair]
    sum_abs_pnl = sum(abs_pnls)
    if sum_abs_pnl > 1e-9:
        weights = [x / sum_abs_pnl for x in abs_pnls if x > 0]
        effective_pairs = 1.0 / sum(w * w for w in weights)
    else:
        trade_counts = [per_pair[p]["trade_count"] for p in pairs if p in per_pair]
        sum_tc = sum(trade_counts)
        if sum_tc > 0:
            weights = [c / sum_tc for c in trade_counts if c > 0]
            effective_pairs = 1.0 / sum(w * w for w in weights)
        else:
            effective_pairs = 0.0

    effective_max_dd = min(ft_agg["max_drawdown_pct"], curve["max_drawdown_pct"])
    effective_calmar = (
        curve["cagr_pct"] / abs(effective_max_dd) if abs(effective_max_dd) > 1e-6 else 0.0
    )

    aggregate = {
        "daily_sharpe": curve["daily_sharpe"],
        "daily_sortino": curve["daily_sortino"],
        "ft_sharpe": ft_agg["ft_sharpe"],
        "cagr_pct": curve["cagr_pct"],
        "calmar": effective_calmar,
        "ulcer_index": curve["ulcer_index"],
        "martin_ratio": curve["martin_ratio"],
        "total_profit_pct": ft_agg["total_profit_pct"],
        "max_drawdown_pct": effective_max_dd,
        "mtm_drawdown_pct": curve["max_drawdown_pct"],
        "ft_drawdown_pct": ft_agg["max_drawdown_pct"],
        "max_dd_days": curve["max_dd_days"],
        "trade_count": ft_agg["trade_count"],
        "long_trades": long_trades,
        "short_trades": short_trades,
        "long_profit_pct": (long_profit_abs / starting_balance) * 100.0,
        "short_profit_pct": (short_profit_abs / starting_balance) * 100.0,
        "funding_fees_abs": funding_fees_abs,
        "max_leverage": max_leverage_seen,
        "win_rate_pct": ft_agg["win_rate_pct"],
        "profit_factor": ft_agg["profit_factor"],
        "alpha_ann_pct": decomp["alpha_ann_pct"],
        "beta": decomp["beta"],
        "info_ratio": decomp["info_ratio"],
        "avg_pos_pct": avg_pos_pct,
        "time_in_market_pct": time_in_market_pct,
        "capital_util_pct": capital_util_pct,
        "effective_pairs": effective_pairs,
    }

    return {
        "timerange_label": "",
        "timerange": timerange,
        "days_count": len(days),
        "daily_ret": daily_ret,
        "bah": bah,
        "aggregate": aggregate,
        "per_pair": per_pair,
        "pairs": pairs,
    }


# ---------------------------------------------------------------------------
# Pareto dominance vs prior results.tsv entries (3D + kill-aware)
# ---------------------------------------------------------------------------
def load_prior_strategy_rows() -> tuple[list[dict[str, Any]], set[str]]:
    """Read results.tsv (supports both 6-col v0.4.1 and 10-col v0.5.0 schemas).

    Returns (rows, killed_strategy_names). Skips PORTFOLIO rollup rows.
    """
    path = PROJECT_DIR / "results.tsv"
    if not path.exists():
        return [], set()
    try:
        df = pd.read_csv(path, sep="\t", dtype={"commit": str})
    except Exception:
        return [], set()
    if df.empty:
        return [], set()

    killed: set[str] = set()
    rows: list[dict[str, Any]] = []
    sharpe_col = "robust_sharpe" if "robust_sharpe" in df.columns else "sharpe"

    for _, r in df.iterrows():
        ev = str(r.get("event", "")).strip().lower()
        sname = str(r.get("strategy_name", "")).strip()
        if "->" in sname:
            sname = sname.split("->")[-1].strip()
        elif "→" in sname:
            sname = sname.split("→")[-1].strip()

        if ev == "portfolio" or sname == "PORTFOLIO_EQ":
            continue
        if ev == "kill":
            killed.add(sname)
            continue
        if ev == "create":
            killed.discard(sname)

        sh_str = str(r.get(sharpe_col, "-")).strip()
        dd_str = str(r.get("max_dd", "-")).strip()
        if sh_str in ("-", "", "nan") or dd_str in ("-", "", "nan"):
            continue
        try:
            sh_val = float(sh_str)
            dd_val = float(dd_str)
            cagr_raw = str(r.get("cagr_pct", "-")).strip()
            cagr_val = float(cagr_raw) if cagr_raw not in ("-", "", "nan") else None
            rows.append({
                "commit": str(r.get("commit", "")),
                "strategy": sname,
                "robust_sharpe": sh_val,
                "cagr_pct": cagr_val,
                "max_dd": dd_val,
            })
        except ValueError:
            continue

    return rows, killed


def check_pareto_dominance(
    strategy_name: str,
    robust_sharpe: float,
    full_cagr_pct: float,
    worst_dd: float,
) -> tuple[str | None, str | None]:
    """Return (active_dominator, archived_dominator) on 3D (robust_sharpe, cagr_pct, worst_dd).

    Separates live/active strategy history from killed strategies so an early
    killed single-pair baseline no longer causes permanent 'ghost lock'.
    """
    rows, killed = load_prior_strategy_rows()
    active_dom: str | None = None
    archived_dom: str | None = None

    for row in rows:
        # Compare on 3D when cagr_pct is available, else 2D fallback
        sh_ge = row["robust_sharpe"] >= robust_sharpe - 1e-6
        dd_ge = row["max_dd"] >= worst_dd - 1e-6
        if row["cagr_pct"] is not None:
            cagr_ge = row["cagr_pct"] >= full_cagr_pct - 1e-6
            strict = (
                row["robust_sharpe"] > robust_sharpe + 1e-4
                or row["cagr_pct"] > full_cagr_pct + 1e-3
                or row["max_dd"] > worst_dd + 1e-3
            )
            dominates = sh_ge and dd_ge and cagr_ge and strict
        else:
            strict = (
                row["robust_sharpe"] > robust_sharpe + 1e-4
                or row["max_dd"] > worst_dd + 1e-3
            )
            dominates = sh_ge and dd_ge and strict

        if dominates:
            tag = f"{row['commit']}:{row['strategy']}"
            if row["strategy"] in killed and row["strategy"] != strategy_name:
                if archived_dom is None:
                    archived_dom = tag
            else:
                if active_dom is None:
                    active_dom = tag

    return active_dom, archived_dom


# ---------------------------------------------------------------------------
# Cross-Strategy Portfolio Rollup (PORTFOLIO_SUMMARY)
# ---------------------------------------------------------------------------
def evaluate_cross_strategy_portfolio(
    strategy_bundles: dict[str, list[dict[str, Any]]],
    commit: str,
) -> None:
    """Combine all active strategies into an equal-weight portfolio across common regimes."""
    strat_names = list(strategy_bundles.keys())
    if not strat_names:
        return

    # Find common (label, timerange) pairs in declaration order of first strategy
    first_trs = [(b["timerange_label"], b["timerange"]) for b in strategy_bundles[strat_names[0]]]
    common_trs: list[tuple[str, str]] = []
    for key in first_trs:
        if all(
            any((b["timerange_label"], b["timerange"]) == key for b in strategy_bundles[s])
            for s in strat_names
        ):
            common_trs.append(key)

    if not common_trs:
        print("---")
        print("portfolio:        PORTFOLIO_EQ")
        print(f"commit:           {commit}")
        print("note:             No common timeranges across active strategies; align test_timeranges.")
        return

    # Lookup map: (strategy, label, tr) -> bundle
    lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for s in strat_names:
        for b in strategy_bundles[s]:
            lookup[(s, b["timerange_label"], b["timerange"])] = b

    port_regime_stats: list[dict[str, Any]] = []
    full_ret_matrix: pd.DataFrame | None = None

    for label, tr in common_trs:
        rets_df = pd.concat(
            [lookup[(s, label, tr)]["daily_ret"].rename(s) for s in strat_names],
            axis=1,
        ).fillna(0.0)
        port_ret = rets_df.mean(axis=1)

        # Union of baskets for portfolio-level BaH benchmark
        union_pairs: list[str] = []
        for p in PAIRS:
            if any(p in lookup[(s, label, tr)]["pairs"] for s in strat_names):
                union_pairs.append(p)
        bah = compute_bah_benchmark(tr, union_pairs or PAIRS)

        curve = compute_curve_metrics(port_ret)
        decomp = compute_benchmark_decomposition(port_ret, bah["daily_ret"])
        port_regime_stats.append({
            "label": label,
            "timerange": tr,
            "rets_df": rets_df,
            "curve": curve,
            "decomp": decomp,
            "bah": bah,
        })
        if full_ret_matrix is None or len(rets_df) > len(full_ret_matrix):
            full_ret_matrix = rets_df

    port_sharpes = [x["curve"]["daily_sharpe"] for x in port_regime_stats]
    port_sortinos = [x["curve"]["daily_sortino"] for x in port_regime_stats]
    port_dds = [x["curve"]["max_drawdown_pct"] for x in port_regime_stats]

    port_robust_sharpe = min(port_sharpes)
    port_robust_sortino = min(port_sortinos)
    port_worst_dd = min(port_dds)

    # Longest window serves as full-cycle reference
    longest = max(port_regime_stats, key=lambda x: len(x["rets_df"]))
    full_cagr = longest["curve"]["cagr_pct"]
    full_calmar = longest["curve"]["calmar"]
    full_martin = longest["curve"]["martin_ratio"]
    full_sharpe = longest["curve"]["daily_sharpe"]
    full_alpha = longest["decomp"]["alpha_ann_pct"]
    full_beta = longest["decomp"]["beta"]
    full_ir = longest["decomp"]["info_ratio"]

    # Individual robust_sharpe over common regimes for diversification gain
    indiv_robust = []
    for s in strat_names:
        s_sh = [lookup[(s, l, t)]["aggregate"]["daily_sharpe"] for l, t in common_trs]
        indiv_robust.append(min(s_sh))
    mean_indiv_robust = float(np.mean(indiv_robust)) if indiv_robust else 0.0
    div_gain = port_robust_sharpe - mean_indiv_robust

    # Pairwise correlation & tail (drawdown-day) correlation
    max_corr = -1.0
    corr_pairs_str: list[str] = []
    tail_pairs_str: list[str] = []
    if len(strat_names) >= 2 and full_ret_matrix is not None:
        corr_mat = full_ret_matrix.corr().fillna(0.0)
        for i in range(len(strat_names)):
            for j in range(i + 1, len(strat_names)):
                s1, s2 = strat_names[i], strat_names[j]
                c = float(corr_mat.loc[s1, s2])
                max_corr = max(max_corr, c)
                corr_pairs_str.append(f"{s1}~{s2}={c:+.3f}")

                # Tail correlation on days where either strategy loses money
                sub = full_ret_matrix[[s1, s2]]
                tail = sub[(sub[s1] < 0) | (sub[s2] < 0)]
                tc = float(tail[s1].corr(tail[s2])) if len(tail) >= 5 else 0.0
                if math.isnan(tc):
                    tc = 0.0
                tail_pairs_str.append(f"{s1}~{s2}={tc:+.3f}")

    div_gate_pass = (len(strat_names) == 1) or (max_corr < MAX_PAIRWISE_CORR)

    # Leave-one-out Marginal Portfolio Contribution per strategy
    marginals: dict[str, dict[str, float]] = {}
    if len(strat_names) >= 2:
        for s in strat_names:
            others = [o for o in strat_names if o != s]
            loo_sharpes = []
            loo_full_sharpe = 0.0
            for x in port_regime_stats:
                loo_ret = x["rets_df"][others].mean(axis=1)
                loo_c = compute_curve_metrics(loo_ret)
                loo_sharpes.append(loo_c["daily_sharpe"])
                if x is longest:
                    loo_full_sharpe = loo_c["daily_sharpe"]
            loo_robust = min(loo_sharpes)
            marginals[s] = {
                "marginal_robust_sharpe": port_robust_sharpe - loo_robust,
                "marginal_full_sharpe": full_sharpe - loo_full_sharpe,
            }
    else:
        s0 = strat_names[0]
        marginals[s0] = {
            "marginal_robust_sharpe": port_robust_sharpe,
            "marginal_full_sharpe": full_sharpe,
        }

    print("---")
    print("portfolio:                 PORTFOLIO_EQ")
    print("timerange_label:           PORTFOLIO_SUMMARY")
    print(f"commit:                    {commit}")
    print(f"active_strategies ({len(strat_names)}):     {','.join(strat_names)}")
    print(f"portfolio_robust_sharpe:   {port_robust_sharpe:.4f}   # min equal-weight daily Sharpe across regimes")
    print(f"portfolio_robust_sortino:  {port_robust_sortino:.4f}")
    print(f"diversification_gain:      {div_gain:+.4f}   # portfolio_robust_sharpe - mean(strategy robust_sharpe)")
    print(f"portfolio_full_sharpe:     {full_sharpe:.4f}   (window={longest['label']})")
    print(f"portfolio_full_cagr_pct:   {full_cagr:.4f}")
    print(f"portfolio_worst_dd_pct:    {port_worst_dd:.4f}")
    print(f"portfolio_calmar:          {full_calmar:.4f}")
    print(f"portfolio_martin_ratio:    {full_martin:.4f}")
    print(f"portfolio_alpha_ann_pct:   {full_alpha:+.4f}")
    print(f"portfolio_beta:            {full_beta:.4f}")
    print(f"portfolio_info_ratio:      {full_ir:.4f}")
    if len(strat_names) >= 2:
        print(f"pairwise_daily_corr:       {', '.join(corr_pairs_str)}")
        print(f"pairwise_tail_corr:        {', '.join(tail_pairs_str)}")
        print(
            f"diversification_gate:      {'PASS' if div_gate_pass else 'FAIL'}   "
            f"(max_corr={max_corr:+.3f}, threshold < {MAX_PAIRWISE_CORR:.2f})"
        )
    else:
        print("pairwise_daily_corr:       n/a (single active strategy)")
        print("diversification_gate:      SINGLE_SLOT (add orthogonal paradigms to unlock diversification)")

    print("per_regime_portfolio:")
    for x in port_regime_stats:
        c = x["curve"]
        b = x["bah"]
        print(
            f"  {x['label']} ({x['timerange']}): "
            f"daily_sharpe={c['daily_sharpe']:.4f} "
            f"sortino={c['daily_sortino']:.4f} "
            f"profit_pct={c['total_profit_pct']:+.2f} "
            f"dd_pct={c['max_drawdown_pct']:.2f} "
            f"martin={c['martin_ratio']:.2f} "
            f"(bah_sharpe={b['sharpe']:.2f} bah_profit={b['profit_total_pct']:+.1f}%)"
        )

    print("marginal_contributions:")
    for s in strat_names:
        m = marginals[s]
        verdict = "ACCRETIVE" if m["marginal_robust_sharpe"] >= -1e-4 else "DILUTIVE"
        print(
            f"  {s}: marginal_robust_sharpe={m['marginal_robust_sharpe']:+.4f} "
            f"marginal_full_sharpe={m['marginal_full_sharpe']:+.4f} "
            f"[{verdict}]"
        )


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
    print(f"strategy:           {strategy_name}")
    print(f"timerange_label:    {timerange_label}")
    print(f"timerange:          {timerange}")
    print(f"commit:             {commit}")
    print(f"basket:             {','.join(pairs)}")
    print(f"daily_sharpe:       {agg['daily_sharpe']:.4f}   (ft_sharpe={agg['ft_sharpe']:.4f})")
    print(f"daily_sortino:      {agg['daily_sortino']:.4f}")
    print(f"cagr_pct:           {agg['cagr_pct']:.4f}")
    print(f"total_profit_pct:   {agg['total_profit_pct']:.4f}")
    print(
        f"max_drawdown_pct:   {agg['max_drawdown_pct']:.4f}   "
        f"(mtm_dd={agg['mtm_drawdown_pct']:.2f}%, ft_realized_dd={agg['ft_drawdown_pct']:.2f}%, "
        f"max_dd_days={int(agg['max_dd_days'])}d)"
    )
    print(f"calmar:             {agg['calmar']:.4f}")
    print(f"ulcer_index:        {agg['ulcer_index']:.4f}")
    print(f"martin_ratio:       {agg['martin_ratio']:.4f}")
    print(f"alpha_ann_pct:      {agg['alpha_ann_pct']:+.4f}")
    print(f"beta:               {agg['beta']:.4f}")
    print(f"info_ratio:         {agg['info_ratio']:.4f}")
    print(f"trade_count:        {agg['trade_count']}")
    print(
        f"sides:              long={agg['long_trades']} ({agg['long_profit_pct']:+.2f}%) "
        f"short={agg['short_trades']} ({agg['short_profit_pct']:+.2f}%) "
        f"funding={agg['funding_fees_abs']:+.2f} USDT (max_lev={agg['max_leverage']:.2f}x)"
    )
    print(f"win_rate_pct:       {agg['win_rate_pct']:.2f}")
    print(f"profit_factor:      {agg['profit_factor']:.4f}")
    print(
        f"exposure:           avg_pos={agg['avg_pos_pct']:.2f}% "
        f"time_in_mkt={agg['time_in_market_pct']:.2f}% "
        f"cap_util={agg['capital_util_pct']:.2f}% "
        f"eff_pairs={agg['effective_pairs']:.2f}/{len(pairs)}"
    )
    print(
        f"bah_benchmark:      bah_sharpe={bah['sharpe']:.4f} "
        f"bah_profit_pct={bah['profit_total_pct']:+.2f} "
        f"bah_dd_pct={bah['max_drawdown_pct']:.2f}"
    )
    print("per_pair:")
    for pair in pairs:
        m = per_pair.get(pair)
        if m is None:
            print(f"  {pair}: (no data)")
            continue
        bah_p = bah["per_pair"].get(pair, {})
        bah_str = ""
        if bah_p:
            bah_str = f" (bah_profit={bah_p['profit_pct']:+.1f}% bah_dd={bah_p['dd_pct']:.1f}%)"
        print(
            f"  {pair}: ft_sharpe={m['ft_sharpe']:.3f} "
            f"trades={m['trade_count']} "
            f"profit_pct={m['total_profit_pct']:+.2f} "
            f"dd_pct={m['max_drawdown_pct']:.2f} "
            f"wr={m['win_rate_pct']:.1f} "
            f"pf={m['profit_factor']:.2f}"
            f"{bah_str}"
        )


def _check_regime_return_gate(per_timerange_metrics: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for b in per_timerange_metrics:
        lbl = b["timerange_label"]
        prof = b["aggregate"]["total_profit_pct"]
        bah_prof = b["bah"]["profit_total_pct"]
        days_n = b["days_count"]
        if bah_prof < 0.0:
            # Bear regime: capital preservation + outperform negative BaH
            if prof < BEAR_PRESERVATION_FLOOR_PCT or prof <= bah_prof:
                reasons.append(f"{lbl}: {prof:+.1f}% < {BEAR_PRESERVATION_FLOOR_PCT:+.1f}% bear floor")
        else:
            floor = FULL_PROFIT_FLOOR_PCT if days_n >= 1400 else BULL_PROFIT_FLOOR_PCT
            if prof < floor:
                reasons.append(f"{lbl}: {prof:+.1f}% < +{floor:.0f}% floor")
    return len(reasons) == 0, reasons


def print_strategy_summary(
    strategy_name: str,
    commit: str,
    per_timerange_metrics: list[dict[str, Any]],
) -> None:
    if not per_timerange_metrics:
        return

    d_sharpes = [m["aggregate"]["daily_sharpe"] for m in per_timerange_metrics]
    d_sortinos = [m["aggregate"]["daily_sortino"] for m in per_timerange_metrics]
    profits = [m["aggregate"]["total_profit_pct"] for m in per_timerange_metrics]
    dds = [m["aggregate"]["max_drawdown_pct"] for m in per_timerange_metrics]
    pos_sizes = [
        m["aggregate"]["avg_pos_pct"]
        for m in per_timerange_metrics
        if m["aggregate"]["trade_count"] > 0
    ]

    longest = max(per_timerange_metrics, key=lambda m: m["days_count"])
    full_agg = longest["aggregate"]

    robust_sharpe = min(d_sharpes)
    robust_sortino = min(d_sortinos)
    worst_profit = min(profits)
    worst_dd = min(dds)
    worst_pos = min(pos_sizes) if pos_sizes else 0.0

    ret_gate_pass, ret_reasons = _check_regime_return_gate(per_timerange_metrics)
    exp_gate_pass = (
        worst_pos >= MIN_POSITION_SIZE_PCT
        and full_agg["time_in_market_pct"] >= MIN_TIME_IN_MARKET_PCT
    )
    active_dom, archived_dom = check_pareto_dominance(
        strategy_name,
        robust_sharpe,
        full_agg["cagr_pct"],
        worst_dd,
    )

    print("---")
    print(f"strategy:             {strategy_name}")
    print("timerange_label:      SUMMARY")
    print(f"commit:               {commit}")
    print(f"robust_sharpe:        {robust_sharpe:.4f}   # min daily_sharpe across declared regimes")
    print(f"robust_sortino:       {robust_sortino:.4f}   # min daily_sortino across declared regimes")
    print(f"full_cagr_pct:        {full_agg['cagr_pct']:.4f}   (window={longest['timerange_label']})")
    print(f"full_calmar:          {full_agg['calmar']:.4f}")
    print(f"full_martin_ratio:    {full_agg['martin_ratio']:.4f}")
    print(f"full_alpha_ann_pct:   {full_agg['alpha_ann_pct']:+.4f}   (beta={full_agg['beta']:.3f}, IR={full_agg['info_ratio']:.3f})")
    print(f"worst_profit_pct:     {worst_profit:.4f}")
    print(f"worst_dd_pct:         {worst_dd:.4f}")
    print(
        f"utilization:          worst_avg_pos={worst_pos:.2f}% "
        f"full_time_in_mkt={full_agg['time_in_market_pct']:.2f}% "
        f"eff_pairs={full_agg['effective_pairs']:.2f}/{len(longest['pairs'])}"
    )
    if ret_gate_pass:
        print("regime_return_gate:   PASS   (bull/rec >= +10%, full >= +20%, bear >= -2%)")
    else:
        print(f"regime_return_gate:   FAIL   ({'; '.join(ret_reasons)})")
    print(
        f"exposure_gate:        {'PASS' if exp_gate_pass else 'FAIL'}   "
        f"(avg_pos >= {MIN_POSITION_SIZE_PCT}%, time_in_mkt >= {MIN_TIME_IN_MARKET_PCT}%)"
    )
    if active_dom:
        print(f"pareto_dominated_by:  {active_dom} (active 3D dominator on sharpe/cagr/dd)")
    elif archived_dom:
        print(f"pareto_dominated_by:  none_active (archived_ref={archived_dom})")
    else:
        print("pareto_dominated_by:  none (3D Pareto frontier)")


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
    print("status:           ERROR")
    print(f"error_type:       {type(err).__name__}")
    print(f"error_msg:        {err}")
    print("traceback:")
    print(traceback.format_exc())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-Quant v0.5.2 Portfolio & Multi-Regime Oracle.")
    parser.add_argument(
        "--oos",
        action="store_true",
        help="Evaluate on the out-of-sample test split (>= SPLIT_DATE). Default: train split.",
    )
    cli = parser.parse_args()
    split = "test" if cli.oos else "train"
    eval_timeranges = build_split_timeranges(split=split)
    force_trs = split == "test"

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
    print(
        f"Bench:       mode={TRADING_MODE} max_lev={MAX_LEVERAGE:.1f}x fee={BENCH_FEE*100:.3f}%/side "
        f"data={DATA_TIMERANGE} split_date={SPLIT_DATE}"
    )
    print(f"Split:       {split.upper()}{' (OOS)' if split == 'test' else ' (IS)'}")
    print(f"Whitelist:   {PAIRS_STR}")
    print(f"Eval TRs:    {', '.join(f'{lbl}({tr})' for lbl, tr in eval_timeranges)}")
    print()

    n_ok_total = 0
    n_err_total = 0
    all_strategy_bundles: dict[str, list[dict[str, Any]]] = {}

    for name in strategies:
        try:
            pair_basket, test_timeranges = get_strategy_overrides(
                name,
                default_timeranges=eval_timeranges,
                force_timeranges=force_trs,
            )
        except Exception as err:
            print_error(name, commit, "SETUP", "n/a", err)
            n_err_total += 1
            print()
            continue

        active_pairs = list(pair_basket) if pair_basket else list(PAIRS)
        per_timerange_metrics: list[dict[str, Any]] = []

        for label, timerange in test_timeranges:
            try:
                results = run_backtest(name, timerange, pair_basket)
                bah = compute_bah_benchmark(timerange, active_pairs)
                bundle = extract_strategy_bundle(results, name, timerange, active_pairs, bah)
                bundle["timerange_label"] = label
                print_block(name, commit, label, timerange, active_pairs, bundle, bah)
                per_timerange_metrics.append(bundle)
                n_ok_total += 1
            except BaseException as err:
                print_error(name, commit, label, timerange, err)
                n_err_total += 1
            print()

        if per_timerange_metrics:
            print_strategy_summary(name, commit, per_timerange_metrics)
            print()
            if len(per_timerange_metrics) == len(test_timeranges):
                all_strategy_bundles[name] = per_timerange_metrics

    if all_strategy_bundles:
        evaluate_cross_strategy_portfolio(all_strategy_bundles, commit)
        print()

    print(f"Done: {n_ok_total} backtests succeeded, {n_err_total} failed.")
    return 0 if n_err_total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
