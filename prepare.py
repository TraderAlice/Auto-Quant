"""
prepare.py — READ-ONLY. Part of the evaluation contract, do not modify.

One-time setup: check env + download BTC/USDT and ETH/USDT OHLCV data from
Binance across all enabled timeframes (1h base + 4h + 1d informative).

The multi-timeframe data is what lets strategies use FreqTrade's @informative
decorator to reference higher-TF context from inside a 1h base strategy.

Usage:
    uv run prepare.py
"""

from __future__ import annotations

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
# Fixed constants — these define the evaluation arena. Do not modify.
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).parent.resolve()
USER_DATA = PROJECT_DIR / "user_data"
CONFIG = PROJECT_DIR / "config.json"

EXCHANGE = "binance"
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "AVAX/USDT"]
TIMEFRAMES = ["1h", "4h", "1d"]
# v0.4.0: extended from 2023-2025 (bull only) to 2021-2025 to include
# the 2022 winter regime. Cross-pair macro signals + bear-regime
# resilience were both blocked by single-regime data in v0.3.0.
TIMERANGE = "20210101-20251231"


def data_exists() -> bool:
    # Check (a) every (pair, timeframe) feather file exists AND (b) it covers
    # the configured TIMERANGE from the start. v0.4.0 extended timerange
    # backward, so we can no longer just check file presence — files from
    # the v0.3.0 era cover only 2023+ and need prepending.
    import pandas as pd

    data_dir = USER_DATA / "data"
    tr_start_str = TIMERANGE.split("-")[0]  # e.g. "20210101"
    required_start = pd.Timestamp(tr_start_str, tz="UTC")

    for pair in PAIRS:
        pair_name = pair.replace("/", "_")
        for tf in TIMEFRAMES:
            path = data_dir / f"{pair_name}-{tf}.feather"
            if not path.exists():
                return False
            try:
                df = pd.read_feather(path, columns=["date"])
            except Exception:
                return False
            if len(df) == 0:
                return False
            first = pd.Timestamp(df["date"].iloc[0])
            if first.tzinfo is None:
                first = first.tz_localize("UTC")
            # Allow a tiny grace window — file's first bar may be a few
            # candles after exact TIMERANGE start due to exchange listing
            # times. If the file starts more than 7 days late, it doesn't
            # cover the required window.
            if first > required_start + pd.Timedelta(days=7):
                return False
    return True


def download() -> None:
    args = {
        "config": [str(CONFIG)],
        "user_data_dir": str(USER_DATA),
        "datadir": str(USER_DATA / "data"),
        "exchange": EXCHANGE,
        "pairs": PAIRS,
        "timeframes": TIMEFRAMES,
        "timerange": TIMERANGE,
        "dataformat_ohlcv": "feather",
        "dataformat_trades": "feather",
        "download_trades": False,
        "trading_mode": "spot",
        # prepend_data=True so v0.4.0 can extend existing 2023-2025 files
        # backward to 2021-01-01 without re-downloading the bull regime.
        "prepend_data": True,
        "erase": False,
        "include_inactive_pairs": False,
        "new_pairs_days": 30,
    }
    start_download_data(args)


def main() -> None:
    data_dir = USER_DATA / "data"
    if data_exists():
        print(f"Data already present at {data_dir} ({len(PAIRS)} pairs × {len(TIMEFRAMES)} timeframes).")
        print("Ready.")
        return

    print(f"Exchange:   {EXCHANGE}")
    print(f"Pairs:      {PAIRS}")
    print(f"Timeframes: {TIMEFRAMES}")
    print(f"Timerange:  {TIMERANGE}")
    print(f"Dest:       {data_dir}")
    print()

    download()

    if not data_exists():
        print(
            "ERROR: download appeared to succeed but expected files are missing.\n"
            f"Check {data_dir}/",
            file=sys.stderr,
        )
        sys.exit(1)

    print()
    print("Ready.")


if __name__ == "__main__":
    main()
