"""
MeanRevBBClean — shallow BB touch + vol-expansion + 1d local bull + cross-pair BTC strength

Paradigm: mean-reversion
Hypothesis: r2 fixed 4 of 5 pairs but ETH still has pf 0.42. Theory: alt
            mean-reversion (and even ETH which behaves like an alt vs BTC)
            requires BTC itself to be strong; otherwise the "bounce" is a
            short-lived bull-trap inside a broader BTC weakness episode.
            Add cross-pair gate: BTC daily close > BTC daily EMA200. This is
            the v0.3.0-native cross-pair affordance — couldn't be expressed
            in v0.1.0 or v0.2.0.
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

    @informative("1d", "BTC/USDT")
    def populate_indicators_btc_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # BTC daily EMA200 — used as cross-pair "macro strength" gate.
        # On the BTC pair this is redundant with the local ema200_1d (same data),
        # but the gate condition stays consistent so it doesn't break BTC.
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
            & (dataframe["close"] > dataframe["ema200_1d"])        # local 1d bull
            & (dataframe["btc_usdt_close_1d"] > dataframe["btc_usdt_ema200_1d"]),  # BTC macro strength
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
