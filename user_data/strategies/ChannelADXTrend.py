"""
ChannelADXTrend — 1d-regime + 4h-ADX/EMA20>50 + 1h EMA50 pullback-and-reclaim

Paradigm: trend-following
Hypothesis: r1 was catastrophic (Sharpe -2.14, 4404 trades). r2 added
            slower entry + 4h trend gate, cut trades to 1352 and Sharpe
            to -0.37 — but WR still 18%, meaning the entry pattern was
            wrong-side (pullback-and-reclaim catches stop-runs in trends,
            not buyable dips). r3 pivots: continuation-style entry (close
            breaks 5-bar high while above 1h EMA50, gated by full MTF
            trend stack). Trend-following alpha lives in entering WITH
            momentum, not against it. If r3 doesn't lift WR meaningfully
            (target >35%) the trend paradigm should be killed and the
            slot recycled.
Parent: root (self-evolution; r1 commit 7a58a63 was the catastrophic baseline)
Created: 7a58a63 (r1)
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class ChannelADXTrend(IStrategy):
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

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma100"] = ta.SMA(dataframe, timeperiod=100)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r3 pivot: continuation-style entry (NOT pullback). r2 found
        # WR stuck at 18% with pullback-reclaim — in trending markets
        # brief EMA50 touches are stop-runs, not buy zones. Now: enter on
        # 5-bar high break while above EMA50, with full MTF trend gating.
        dataframe["high_5"] = dataframe["high"].rolling(5).max().shift(1)
        dataframe.loc[
            (dataframe["close"] > dataframe["sma100_1d"])
            & (dataframe["adx_4h"] > 25)
            & (dataframe["ema20_4h"] > dataframe["ema50_4h"])
            & (dataframe["close"] > dataframe["ema50"])
            & (dataframe["close"] > dataframe["high_5"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["close"] < dataframe["ema50"], "exit_long"] = 1
        return dataframe
