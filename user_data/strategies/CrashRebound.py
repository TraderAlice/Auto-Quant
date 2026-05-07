"""
CrashRebound — buy alts after a -25% drawdown from rolling 30d high

Paradigm: other (counter-trend / drawdown-rebound)
Hypothesis: AltsBollBreak's r0-r4 trajectory established that breakout
            paradigms on alts have structural winter fragility — every
            defense (1d position filter, stoploss, slope filter) cut bull
            profit while only partially silencing winter. The opposite
            structural exposure is interesting: a counter-trend strategy
            that ENTERS on drawdowns. Crashes happen in every regime
            (bull pullbacks, winter capitulations, recovery shakeouts);
            the rebound size varies but the directional edge is generally
            positive on liquid majors. Trigger: 1h close < 30d-rolling-max
            × 0.75 (i.e., 25% off 30-day peak) AND 1h RSI(14) < 35
            (oversold confirmation — don't catch knives mid-fall, wait
            for a stretch). Exit: 1h close > 1h SMA50 (mean-reversion
            target, halfway-back-to-prior-trend). Universe: alts only
            (SOL, AVAX, BNB) — alts have larger drawdowns than majors,
            and the v0.4.0 surfacing was that BTC/ETH have less
            mean-reverting structure. test_timeranges spans bull/winter/
            recovery/full to make the cross-regime claim falsifiable.
            Equal-weight sizing.
Parent: root (replaces AltsBollBreak which was killed at r5 after 5
        rounds of failed winter defenses)
Created: pending — fill in after first commit
Status: active
Uses MTF: no (1h-only on entry/exit; 30d max needs 720 bars warmup)
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class CrashRebound(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 100}
    stoploss = -0.99
    trailing_stop = False
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # 30d at 1h = 720 bars warmup
    startup_candle_count: int = 760

    pair_basket = ["SOL/USDT", "AVAX/USDT", "BNB/USDT"]

    test_timeranges = [
        ("bull_2021",      "20210101-20211231"),
        ("winter_2022",    "20220101-20221231"),
        ("recovery_23_25", "20230101-20251231"),
        ("full_5y",        "20210101-20251231"),
    ]

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["ema200_slope_up"] = (
            dataframe["ema200"] > dataframe["ema200"].shift(7)
        ).astype(int)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 30-day rolling high (720 1h bars). Drawdown trigger uses prior bar
        # to avoid current-bar self-reference.
        dataframe["high_30d"] = dataframe["high"].rolling(720).max().shift(1)
        dataframe["drawdown_pct"] = (
            dataframe["close"] / dataframe["high_30d"] - 1.0
        )
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        # r14: SMA100 for patient exit (replaces SMA50 — v0.4.0 r13 found
        # regime-mix prefers patient exits, transferring here from
        # CrashRebound r10 baseline).
        dataframe["sma100"] = ta.SMA(dataframe, timeperiod=100)
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r10: ADD volume confirmation (volume > 1.3 * SMA20). Real
        # capitulation bounces have volume; low-volume pseudo-bounces
        # within sideways drift are likely false positives. Targets
        # winter (which still has 33 trades netting near-zero) and
        # recovery noise.
        dataframe.loc[
            (dataframe["drawdown_pct"] < -0.20)
            & (dataframe["rsi"] < 35)
            & (dataframe["ema200_slope_up_1d"] == 1)
            & (dataframe["volume"] > 1.3 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r14: SMA50 → SMA100 patient exit. v0.4.0 r13: regime-mix prefers
        # patient over fast. Strategy WR is 70% — winners > losers, so
        # extending winner runtime usually helps slightly.
        dataframe.loc[dataframe["close"] > dataframe["sma100"], "exit_long"] = 1
        return dataframe
