"""
MomentumGoldFilters — 4h MACD momentum with EVERY gold filter discovered this run

Paradigm: trend-following / momentum (gold-filter stacked)
Hypothesis: v0.4.0 found momentum capped at ~0.40 Sharpe across two
            different runs / regimes (MACDMomentumMTF v0.3.0 = 0.41,
            MomentumMTFConfluence v0.4.0 = 0.40). v0.4.0 retro flagged
            this as a paradigm-level structural cap. v0.4.1 has surfaced
            multiple "gold" entry filters that lifted strategies' robust
            sharpe materially:
              - 1d EMA200 slope-up filter (CrashRebound r6: -0.84 → +0.024)
              - Volume>1.3*SMA20 confirm (CrashRebound r10: 0.003 → 0.062)
              - 4h ema50>ema200 macro gate (PerPairMR r14: -0.11 → +0.052)
              - close > 1d EMA200 instant-position gate (multiple)
              - Per-pair conditional (PerPairMR r13)
            This strategy stacks ALL of them on a 4h MACD bullish-cross
            entry signal, with patient SMA50 exit (transferred from
            v0.4.0 r13 — found paradigm-specific to BREAKOUTS but
            momentum is similar paradigm-family). Tests: does the v0.4.0
            momentum cap hold even when entry is optimally filtered?
            If yes, the cap is intrinsic to momentum-on-1h-crypto-majors.
            If no, the cap was filter-stack-dependent.
            Universe: full 5-pair (momentum should be paradigm-universal).
Parent: root (paradigm-relative to v0.4.0 MomentumMTFConfluence but
        with v0.4.1 gold-filter stack)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class MomentumGoldFilters(IStrategy):
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

    startup_candle_count: int = 300

    test_timeranges = [
        ("bull_2021",   "20210101-20211231"),
        ("winter_2022", "20220101-20221231"),
        ("full_5y",     "20210101-20251231"),
    ]

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macd_signal"] = macd["macdsignal"]
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["ema200_slope_up"] = (
            dataframe["ema200"] > dataframe["ema200"].shift(7)
        ).astype(int)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 4h MACD bullish: MACD line crosses above signal AND > 0 (genuine
        # bullish momentum, not just "less bearish"). All gold filters
        # stacked: 1d slope-up + 1d close>EMA200 + 4h ema50>ema200 +
        # volume confirm.
        macd_bullish_cross = (
            (dataframe["macd_4h"] > dataframe["macd_signal_4h"])
            & (dataframe["macd_4h"].shift(1) <= dataframe["macd_signal_4h"].shift(1))
            & (dataframe["macd_4h"] > 0)
        )
        # r24: remove volume filter. r23 baseline (with volume) gave
        # full_5y 0.21 — BELOW v0.4.0's momentum cap of 0.40. Volume
        # filter cuts ~half of momentum entries (momentum often fires
        # without volume spike). Test: does removing volume restore
        # to v0.4.0-comparable Sharpe? If yes, filter-stack-overload
        # confirmed volume-specific. If no, the cap is intrinsic.
        dataframe.loc[
            macd_bullish_cross
            & (dataframe["ema50_4h"] > dataframe["ema200_4h"])
            & (dataframe["close"] > dataframe["ema200_1d"])
            & (dataframe["ema200_slope_up_1d"] == 1),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Patient exit on 1h close < 1h SMA50.
        dataframe.loc[dataframe["close"] < dataframe["sma50"], "exit_long"] = 1
        return dataframe
