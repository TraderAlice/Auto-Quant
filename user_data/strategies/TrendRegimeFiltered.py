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
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r4: 4h SMA75 used for patient-exit trigger. v0.4.0 r13 found
        # regime-mixed data prefers SMA75-100 over SMA50 (the
        # bull-conditional sweet spot). Translating to 1h timeframe by
        # building a 4h-equivalent SMA75 = 300-bar SMA on 1h.
        dataframe["sma75_4h_eq"] = dataframe["close"].rolling(300).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r3: revert r1+r2 layered defenses (1.05× buffer and slope-up
        # filter both ineffective). Back to r0 baseline: 4h ema cross +
        # 1d close > EMA200. Per v0.4.0 ChannelADXTrend's experience and
        # r1+r2 here, the right move next is probably patient EXIT
        # (v0.4.0 r13: SMA50→SMA75 lifted regime-mix sharpe 0.69→0.80)
        # not stricter entries. r4 will try that if needed.
        dataframe.loc[
            (dataframe["ema20_4h"] > dataframe["ema50_4h"])
            & (dataframe["close"] > dataframe["ema200_1d"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r4: switch from symmetric 4h ema cross exit to patient SMA75-eq
        # exit (300-bar SMA on 1h ≈ SMA75 on 4h). Per v0.4.0 r13: regime-
        # mixed data prefers patient exits — they cut whipsaws that fast
        # MA-cross exits suffer in winter.
        dataframe.loc[dataframe["close"] < dataframe["sma75_4h_eq"], "exit_long"] = 1
        return dataframe
