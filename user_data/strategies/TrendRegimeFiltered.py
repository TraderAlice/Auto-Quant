"""
TrendRegimeFiltered — 4h MA-cross trend gated by 1d EMA200 regime, 5-pair × 3 regimes

Paradigm: trend-following
Hypothesis: v0.4.0's ChannelADXTrend died in 2022 winter (-2.14 baseline,
            equal-weight on full 5-pair). The mechanism was clear: trend-
            following has no defense against bear regimes when it doesn't
            structurally avoid them. v0.4.0 had no clean way to test
            regime-conditional trend because there was a single timerange.
            v0.4.1's test_timeranges lets us split bull / winter /
            recovery and ASK the regime question explicitly.
            The hypothesis: a 4h EMA20-crosses-EMA50 trend trigger gated
            by a 1d close > EMA200 macro-regime filter should fire mostly
            in 2021 bull and 2023+ recovery, and structurally MUTE in
            2022 winter (when 1d EMA200 sits above price for most of the
            year). If the regime filter works, winter Sharpe should be
            ≈0 (few trades) rather than -2.14. If it fails, the filter
            isn't tight enough.
            Full 5-pair basket: trend should be paradigm-universal across
            crypto majors, unlike MR which was BNB-specific. No custom
            sizing — equal-weight keeps the regime-filter mechanism
            cleanly attributable.
Parent: root (paradigm-relative to v0.4.0 ChannelADXTrend but with
        explicit 1d regime gate and tested across regime splits)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class TrendRegimeFiltered(IStrategy):
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

    startup_candle_count: int = 250

    test_timeranges = [
        ("bull_2021",   "20210101-20211231"),
        ("winter_2022", "20220101-20221231"),
        ("full_5y",     "20210101-20251231"),
    ]

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        # r2: 7d slope of EMA200 (today's vs 7-bar-prior). Slope > 0 → regime
        # is structurally improving, not just briefly poking above EMA200.
        dataframe["ema200_slope_up"] = (
            dataframe["ema200"] > dataframe["ema200"].shift(7)
        ).astype(int)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r2: keep 1.05× buffer + ADD 1d EMA200 slope-up. r1's buffer alone
        # was roughly neutral (full 0.38→0.34, winter -0.31→-0.39); the
        # missing piece is regime-direction. ema200_1d can be FALLING but
        # price still 5% above it (e.g., bull tail before winter break).
        # Slope-up gates entries to regimes where the 1d trend is still
        # structurally improving.
        dataframe.loc[
            (dataframe["ema20_4h"] > dataframe["ema50_4h"])
            & (dataframe["close"] > dataframe["ema200_1d"] * 1.05)
            & (dataframe["ema200_slope_up_1d"] == 1),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Symmetric exit: 4h trend rolls over (regardless of 1d filter —
        # once in, exit on the trigger that put us in).
        dataframe.loc[dataframe["ema20_4h"] < dataframe["ema50_4h"], "exit_long"] = 1
        return dataframe
