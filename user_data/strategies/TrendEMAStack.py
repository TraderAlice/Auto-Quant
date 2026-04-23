"""
TrendEMAStack — Stacked-EMA trend follower

Paradigm: trend-following
Hypothesis: BTC/ETH 1h has persistent trends detectable by EMA stack alignment.
            When EMA9 > EMA21 > EMA50 AND close > EMA9, measurable upside
            momentum exists to capture. Exit when the stack order breaks or
            close falls below EMA21. v0.1.0 never tested trend-following
            so this fills an unexplored paradigm.
Parent: root
Created: pending-first-commit
Status: active
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy


class TrendEMAStack(IStrategy):
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

    startup_candle_count: int = 60

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema9"] = ta.EMA(dataframe, timeperiod=9)
        dataframe["ema21"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Entry = crossover event, not state — avoids re-entering every bar
        # while the stack holds. Fire when ema9 crosses above ema21, ema21
        # is already above ema50 (slow-trend filter), AND ADX>20 (trend
        # strength filter to skip chop).
        ema9_cross_up_21 = (dataframe["ema9"] > dataframe["ema21"]) & (
            dataframe["ema9"].shift(1) <= dataframe["ema21"].shift(1)
        )
        slow_trend_up = dataframe["ema21"] > dataframe["ema50"]
        strong_trend = dataframe["adx"] > 20
        dataframe.loc[
            ema9_cross_up_21 & slow_trend_up & strong_trend, "enter_long"
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        stack_broken = (dataframe["ema9"] < dataframe["ema21"]) | (
            dataframe["close"] < dataframe["ema21"]
        )
        dataframe.loc[stack_broken, "exit_long"] = 1
        return dataframe
