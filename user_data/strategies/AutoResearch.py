"""
AutoResearch — the single file the agent iterates on.

Baseline: plain RSI mean-reversion.
  - Enter long when RSI(14) < 30
  - Exit long when RSI(14) > 70
  - Hard stoploss at -10%, ROI table exits at any profit above 1%

The agent is free to change ANYTHING in this file — indicators, logic, attributes,
imports — as long as the class still exposes an IStrategy-compatible surface that
FreqTrade's Backtesting can load and run.
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy


class AutoResearch(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 0.01}
    stoploss = -0.08

    trailing_stop = False
    process_only_new_candles = True

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count: int = 200

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["bb_upper"], dataframe["bb_middle"], dataframe["bb_lower"] = ta.BBANDS(
            dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] > dataframe["ema200"])
            & (dataframe["rsi"] < 40)
            & (dataframe["close"] < dataframe["bb_lower"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] > 65) | (dataframe["close"] > dataframe["bb_middle"]),
            "exit_long",
        ] = 1
        return dataframe
