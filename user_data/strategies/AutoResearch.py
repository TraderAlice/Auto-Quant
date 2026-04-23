"""
AutoResearch — the single file the agent iterates on.
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy


class AutoResearch(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 0.008}
    stoploss = -0.08

    trailing_stop = False
    trailing_stop_positive = 0.000
    trailing_stop_positive_offset = 0.000
    trailing_only_offset_is_reached = False
    process_only_new_candles = True

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = True

    startup_candle_count: int = 200

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=21)
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        bands = ta.BBANDS(dataframe, timeperiod=24, nbdevup=2.3, nbdevdn=2.3)
        dataframe["bb_upper"] = bands["upperband"]
        dataframe["bb_middle"] = bands["middleband"]
        dataframe["bb_lower"] = bands["lowerband"]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        condition = (dataframe["close"] > dataframe["ema200"])
        condition &= dataframe["rsi"] < 40
        condition &= (dataframe["close"] < dataframe["bb_lower"] * 0.998)

        dataframe.loc[condition, "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_condition = ((dataframe["rsi"] > 60) & (dataframe["close"] > dataframe["bb_middle"] * 1.000))
        dataframe.loc[exit_condition, "exit_long"] = 1
        return dataframe
