"""
MeanRevBBClean — shallow BB touch + volume expansion + 1d bull regime

Paradigm: mean-reversion
Hypothesis: r1 added 1d EMA200 regime gate but pf dropped (0.76→0.62) — deep
            "close-below-then-bounce-above" entry catches violent rejections,
            not soft pullbacks. v0.2.0 r67 finding: "shallow BB touches ARE the
            edge" — i.e. wick penetrates band but close stays above (test of
            support, not break of support). Add volume-expansion confirmation
            (v0.2.0's universal lesson — works across all 3 paradigms there).
Parent: root (paradigm-inspired by v0.2.0's MeanRevBB)
Created: ba0dd4a
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class MeanRevBBClean(IStrategy):
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

    # 1d EMA200 needs ~200 daily bars warmup
    startup_candle_count: int = 250

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        upperband, middleband, lowerband = ta.BBANDS(
            dataframe["close"], timeperiod=20, nbdevup=2.0, nbdevdn=2.0, matype=0
        )
        dataframe["bb_upper"] = upperband
        dataframe["bb_middle"] = middleband
        dataframe["bb_lower"] = lowerband
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["vol_ma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            # Shallow touch: wick penetrated lower band, body stayed above
            (dataframe["low"] <= dataframe["bb_lower"])
            & (dataframe["close"] > dataframe["bb_lower"])
            & (dataframe["rsi"] < 35)
            & (dataframe["volume"] > dataframe["vol_ma20"] * 1.2)  # volume expansion
            & (dataframe["close"] > dataframe["ema200_1d"]),       # 1d bull regime
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] > dataframe["bb_middle"])
            | (dataframe["rsi"] > 65),
            "exit_long",
        ] = 1
        return dataframe
