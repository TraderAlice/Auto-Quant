"""
MeanRevBBClean — pure 1h Bollinger-bounce mean-reversion (single-TF baseline)

Paradigm: mean-reversion
Hypothesis: Pure 1h BB-lower bounce was v0.2.0's MeanRevBB strongest config
            (Sharpe 0.52). Re-running the paradigm without MTF on the new 5-pair
            universe lets us see per-pair MR behaviour as a clean signal — does
            the BB-bounce edge transfer to SOL/BNB/AVAX, or is it BTC/ETH only?
            This serves as a single-TF control against the two MTF strategies.
Parent: root (paradigm-inspired by v0.2.0's MeanRevBB)
Created: pending — fill in after first commit
Status: active
Uses MTF: no
"""

from pandas import DataFrame
import talib.abstract as ta
import qtpylib.indicators as qtpylib  # noqa: F401

from freqtrade.strategy import IStrategy


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

    startup_candle_count: int = 50

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Bollinger Bands via talib (period=20, 2 stddev)
        upperband, middleband, lowerband = ta.BBANDS(
            dataframe["close"], timeperiod=20, nbdevup=2.0, nbdevdn=2.0, matype=0
        )
        dataframe["bb_upper"] = upperband
        dataframe["bb_middle"] = middleband
        dataframe["bb_lower"] = lowerband
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Bounce event: prior bar closed below lower band, current bar closed back above it
        dataframe.loc[
            (dataframe["close"].shift(1) < dataframe["bb_lower"].shift(1))
            & (dataframe["close"] > dataframe["bb_lower"])
            & (dataframe["rsi"] < 35),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit on revert to mid-band OR overbought
        dataframe.loc[
            (dataframe["close"] > dataframe["bb_middle"])
            | (dataframe["rsi"] > 65),
            "exit_long",
        ] = 1
        return dataframe
