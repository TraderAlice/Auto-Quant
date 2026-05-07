"""
ChannelADXTrend — 1d-regime + 4h-ADX-gated trend, 1h EMA20 cross-back entry

Paradigm: trend-following
Hypothesis: v0.3.0's MTFTrendStack reached 0.74 with a 1d EMA200 regime + 4h
            EMA9>EMA21 trend + 1h pullback entry, but EMA-cross signals are
            inherently lagging (the trend is half-over by the time EMA9
            crosses EMA21). Try a structurally different trend gate: 4h ADX
            (Wilder's directional-movement strength) which fires on trend
            EXISTENCE rather than trend INFLECTION, plus a 1d SMA100 (not
            EMA200) for a less-lagged regime filter that should re-engage
            faster after bear→bull regime transitions (relevant in 2022→2023).
            Entry on a 1h EMA20 cross-back from below — a "buy the first
            higher low" pattern. Equal-weight (no custom_stake_amount): this
            is the honest control case for whether sizing-aware strategies
            owe their survival to the sizing or to real edge.
Parent: root (paradigm-inspired by v0.2.0/v0.3.0 trend work but structurally
        different: ADX gate not EMA cross, SMA100 1d not EMA200 1d, EMA20
        cross-back entry not pullback-touch)
Created: pending — fill in after first commit
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
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma100"] = ta.SMA(dataframe, timeperiod=100)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] > dataframe["sma100_1d"])
            & (dataframe["adx_4h"] > 22)
            & (dataframe["close"] > dataframe["ema20"])
            & (dataframe["close"].shift(1) < dataframe["ema20"].shift(1)),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] < dataframe["ema20"])
            & (dataframe["close"].shift(1) > dataframe["ema20"].shift(1)),
            "exit_long",
        ] = 1
        return dataframe
