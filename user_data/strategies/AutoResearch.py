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

    minimal_roi = {"0": 100}
    stoploss = -0.99

    trailing_stop = False
    process_only_new_candles = True

    use_exit_signal = True
    exit_profit_only = True
    ignore_roi_if_entry_signal = False

    startup_candle_count: int = 30

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["rsi"] < 21, "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["rsi"] > 62, "exit_long"] = 1
        return dataframe
