"""
prepare.py — READ-ONLY during runs. Part of the evaluation contract.

One-time (or when `autoquant.data_timerange` changes) setup: check env +
download OHLCV (and funding_rate / mark for futures) data from Binance across
all enabled timeframes (1h base + 4h + 1d informative) for the configured
pair whitelist and `data_timerange` in `config.json`.

Usage:
    uv run prepare.py
    uv run prepare.py --timerange 20210101-20261124
    uv run prepare.py --erase
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Env check — talib is hard to install on macOS ARM; give clear remediation.
# ---------------------------------------------------------------------------
try:
    import talib  # noqa: F401
except ImportError:
    print(
        "ERROR: TA-Lib is not installed.\n\n"
        "Two install paths (see README.md for full detail):\n"
        "  1. Native: `brew install ta-lib` then `uv sync`\n"
        "  2. Docker fallback: `docker compose run --rm freqtrade ...`\n",
        file=sys.stderr,
    )
    sys.exit(1)

from freqtrade.commands.data_commands import start_download_data  # noqa: E402

# ---------------------------------------------------------------------------
# Config-driven arena settings (edit config.json before starting a run).
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).parent.resolve()
USER_DATA = PROJECT_DIR / "user_data"
CONFIG = PROJECT_DIR / "config.json"
TIMEFRAMES = ["1h", "4h", "1d"]


def load_bench_settings() -> dict:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    aq = cfg.get("autoquant") or {}
    return {
        "exchange": cfg.get("exchange", {}).get("name", "binance"),
        "pairs": list(cfg.get("exchange", {}).get("pair_whitelist") or []),
        "trading_mode": cfg.get("trading_mode", "futures"),
        "data_timerange": str(aq.get("data_timerange") or cfg.get("timerange") or "20210101-20261124"),
        "split_date": str(aq.get("split_date") or "20260101"),
    }


def _pair_stem(pair: str) -> str:
    return pair.replace("/", "_").replace(":", "_")


def _ohlcv_path(data_dir: Path, pair: str, tf: str, trading_mode: str) -> Path:
    stem = _pair_stem(pair)
    if trading_mode == "futures":
        return data_dir / "futures" / f"{stem}-{tf}-futures.feather"
    return data_dir / f"{stem}-{tf}.feather"


def data_exists(settings: dict, timerange: str) -> bool:
    """Check every required feather covers [start, end] of `timerange`."""
    import pandas as pd

    data_dir = USER_DATA / "data"
    tr_start_str, tr_end_str = timerange.split("-", 1)
    required_start = pd.Timestamp(tr_start_str, tz="UTC")
    required_end = pd.Timestamp(tr_end_str, tz="UTC")
    trading_mode = settings["trading_mode"]

    for pair in settings["pairs"]:
        stem = _pair_stem(pair)
        required_paths: list[Path] = [
            _ohlcv_path(data_dir, pair, tf, trading_mode) for tf in TIMEFRAMES
        ]
        if trading_mode == "futures":
            required_paths.append(data_dir / "futures" / f"{stem}-1h-funding_rate.feather")
            required_paths.append(data_dir / "futures" / f"{stem}-1h-mark.feather")

        for path in required_paths:
            if not path.exists():
                return False
            try:
                df = pd.read_feather(path, columns=["date"])
            except Exception:
                return False
            if len(df) == 0:
                return False
            first = pd.Timestamp(df["date"].iloc[0])
            last = pd.Timestamp(df["date"].iloc[-1])
            first = first.tz_localize("UTC") if first.tzinfo is None else first.tz_convert("UTC")
            last = last.tz_localize("UTC") if last.tzinfo is None else last.tz_convert("UTC")
            # Grace window for listing offset / end-of-day alignment
            if first > required_start + pd.Timedelta(days=7):
                return False
            if last < required_end - pd.Timedelta(days=2):
                return False
    return True


def download(settings: dict, timerange: str, erase: bool = False) -> None:
    args = {
        "config": [str(CONFIG)],
        "user_data_dir": str(USER_DATA),
        "datadir": str(USER_DATA / "data"),
        "exchange": settings["exchange"],
        "pairs": settings["pairs"],
        "timeframes": TIMEFRAMES,
        "timerange": timerange,
        "dataformat_ohlcv": "feather",
        "dataformat_trades": "feather",
        "download_trades": False,
        "trading_mode": settings["trading_mode"],
        "prepend_data": True,
        "erase": erase,
        "include_inactive_pairs": False,
        "new_pairs_days": 30,
    }
    start_download_data(args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download OHLCV (+ funding/mark) data for Auto-Quant.")
    parser.add_argument(
        "--timerange",
        default=None,
        help="Override autoquant.data_timerange from config.json (YYYYMMDD-YYYYMMDD)",
    )
    parser.add_argument(
        "--erase",
        action="store_true",
        help="Erase existing feather files before downloading fresh data.",
    )
    cli = parser.parse_args()

    settings = load_bench_settings()
    timerange = cli.timerange or settings["data_timerange"]
    data_dir = USER_DATA / "data"

    if not cli.erase and data_exists(settings, timerange):
        print(
            f"Data already present at {data_dir} "
            f"({settings['trading_mode']}, {len(settings['pairs'])} pairs × {len(TIMEFRAMES)} TFs, "
            f"covers {timerange}, split_date={settings['split_date']})."
        )
        print("Ready.")
        return

    print(f"Exchange:     {settings['exchange']} ({settings['trading_mode']})")
    print(f"Pairs:        {settings['pairs']}")
    print(f"Timeframes:   {TIMEFRAMES}")
    print(f"Timerange:    {timerange}  (train/test split_date={settings['split_date']})")
    print(f"Dest:         {data_dir}")
    print()

    download(settings, timerange, erase=cli.erase)

    if not data_exists(settings, timerange):
        print(
            "ERROR: download appeared to succeed but expected files are missing or incomplete.\n"
            f"Check {data_dir}/",
            file=sys.stderr,
        )
        sys.exit(1)

    print()
    print("Ready.")


if __name__ == "__main__":
    main()
