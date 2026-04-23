"""
VolSqueezeBreak — Volatility-squeeze breakout

Paradigm: volatility
Hypothesis: When normalized BB width is in the bottom 20% of its 100-bar
            rolling history, the market is in a compressed state. A close
            above the upper BB following that squeeze is a volatility-expansion
            signal worth capturing. Exit when price retraces to the middle band.
Parent: root
Created: pending-first-commit
Status: active
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy


class VolSqueezeBreak(IStrategy):
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

    startup_candle_count: int = 120

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_upper"] = bb["upperband"]
        dataframe["bb_middle"] = bb["middleband"]
        dataframe["bb_lower"] = bb["lowerband"]
        dataframe["bb_width"] = (
            dataframe["bb_upper"] - dataframe["bb_lower"]
        ) / dataframe["bb_middle"]
        dataframe["bb_width_q10"] = (
            dataframe["bb_width"].rolling(100).quantile(0.1)
        )
        dataframe["squeezed"] = dataframe["bb_width"] <= dataframe["bb_width_q10"]
        dataframe["vol_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Stricter breakout: require close > upper by 0.5% of price (not just
        # touch). Filters borderline breaks that mean-revert immediately.
        # Volume expansion filter retained.
        prior_squeezed = dataframe["squeezed"].shift(1).fillna(False).astype(bool)
        vol_expansion = dataframe["volume"] > dataframe["vol_sma20"]
        strong_break = dataframe["close"] > dataframe["bb_upper"] * 1.005
        dataframe.loc[
            prior_squeezed & strong_break & vol_expansion, "enter_long"
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit at middle band. Round-4 patient exit (bb_lower) widened DD to
        # -45%; round-8's stricter entry cut losers enough that a less
        # patient exit should now work better.
        dataframe.loc[dataframe["close"] < dataframe["bb_middle"], "exit_long"] = 1
        return dataframe
