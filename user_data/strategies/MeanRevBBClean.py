"""
MeanRevBBClean — BB-bounce mean-reversion gated by 1d EMA200 bull regime

Paradigm: mean-reversion
Hypothesis: Round 0 raw BB-bounce was -1.20 across all 5 pairs (catching falling
            knives in down-legs). v0.2.0 r2 found the fix: only mean-revert when
            1d close > EMA200 (bull regime). Apply it here on the broader 5-pair
            universe — expect the high-WR-but-pf<1 problem to flip to high-WR-
            and-pf>1 once we stop catching trend-down rejections.
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
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"].shift(1) < dataframe["bb_lower"].shift(1))
            & (dataframe["close"] > dataframe["bb_lower"])
            & (dataframe["rsi"] < 35)
            & (dataframe["close"] > dataframe["ema200_1d"]),  # 1d bull regime gate
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
