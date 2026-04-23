"""
TrendDonchian — Donchian-channel breakout trend follower

Paradigm: breakout
Hypothesis: On BTC/ETH 1h, a close above the 20-bar rolling high (Donchian
            upper band) is a cleaner trend-continuation signal than EMA9/21
            crossover. Classic turtle-style breakout with modern filters:
            macro regime, ATR expansion, and volume expansion. Exit on close
            below 10-bar low (Turtle-style asymmetric: long entry 20-bar,
            exit 10-bar).
Parent: root
Created: pending-first-commit
Status: active

Replaces TrendEMAStack (killed round 49). TrendEMA achieved +0.34 Sharpe /
131 trades / pf 1.78 / Calmar 8.7 — solid but lowest Sharpe in portfolio.
Testing whether breakout signal is the better trend-follower on this data.
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy


class TrendDonchian(IStrategy):
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

    startup_candle_count: int = 210

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Donchian channels (shifted by 1 to exclude current bar from lookback).
        dataframe["dc_upper"] = dataframe["high"].rolling(20).max().shift(1)
        dataframe["dc_lower"] = dataframe["low"].rolling(10).min().shift(1)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_sma20"] = dataframe["atr"].rolling(20).mean()
        dataframe["vol_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Entry: close breaks above 20-bar rolling high + macro regime +
        # ATR expansion + volume expansion. Same filter stack validated
        # across MACDMomentum and TrendEMA.
        breakout = dataframe["close"] > dataframe["dc_upper"]
        bull_regime = dataframe["close"] > dataframe["ema200"]
        atr_expanding = dataframe["atr"] > dataframe["atr_sma20"]
        vol_expansion = dataframe["volume"] > dataframe["vol_sma20"]
        dataframe.loc[
            breakout & bull_regime & atr_expanding & vol_expansion,
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit on close below 10-bar low. Turtle asymmetric: use a shorter
        # lookback for exits to catch reversals faster than entries trigger.
        dataframe.loc[
            dataframe["close"] < dataframe["dc_lower"], "exit_long"
        ] = 1
        return dataframe
