"""
CrossPairMR — alt/BTC ratio mean-reversion gated by BTC bull regime

Paradigm: mean-reversion
Hypothesis: v0.3.0 Finding 5 explicitly flagged that cross-pair macro
            signals were "redundant in single-regime bull data" — BTC's
            move and alt's move co-incide in pure bull. v0.4.0's
            regime-mixed timerange (incl. 2022 winter, where BTC and alts
            diverged violently) is where cross-pair signals SHOULD start
            mattering. Hypothesis: when an alt's price-vs-BTC ratio drops
            2σ below its 48-hour mean WHILE BTC itself is in a structural
            bull regime (BTC > 50d SMA), that's relative weakness within
            macro strength — a setup classical pair-traders call "alt
            catch-up". Buy the alt; exit when ratio reverts above mean.
            BTC is excluded from this strategy (ratio with itself = 1).
            Replaces MeanRevRSIDip (killed r5 — RSI<28 was BNB-only edge,
            no cross-pair signal).
Parent: root (replaces killed MeanRevRSIDip — different paradigm flavor)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes (cross-pair on 1h + BTC 1d regime)
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class CrossPairMR(IStrategy):
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

    startup_candle_count: int = 250

    @informative("1h", "BTC/USDT")
    def populate_indicators_btc_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # close column is implicit; we reference btc_usdt_close_1h in the
        # main populate_indicators below.
        return dataframe

    @informative("1d", "BTC/USDT")
    def populate_indicators_btc_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # On the BTC pair itself the cross-pair gate is meaningless (ratio
        # is identically 1). Skip computing the ratio there to avoid
        # spurious signals.
        if metadata["pair"] == "BTC/USDT":
            dataframe["ratio_z"] = float("nan")
            dataframe["ratio_mean"] = float("nan")
            return dataframe

        ratio = dataframe["close"] / dataframe["btc_usdt_close_1h"]
        ratio_mean = ratio.rolling(48).mean()
        ratio_std = ratio.rolling(48).std()
        dataframe["ratio_mean"] = ratio_mean
        dataframe["ratio_z"] = (ratio - ratio_mean) / ratio_std
        dataframe["ratio_now"] = ratio
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if metadata["pair"] == "BTC/USDT":
            return dataframe
        # r6: rebound-start trigger. r5 entered while ratio was still
        # falling (DD -37%%, knives in 2022 alt cascades). Now require:
        # prior bar z < -2 (was deeply oversold) AND current bar z is
        # rising (z > z.shift(1)) — buy AFTER the bottom prints, not
        # while still falling. BTC bull regime gate retained.
        dataframe.loc[
            (dataframe["ratio_z"].shift(1) < -2.0)
            & (dataframe["ratio_z"] > dataframe["ratio_z"].shift(1))
            & (dataframe["btc_usdt_close_1h"] > dataframe["btc_usdt_sma50_1d"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if metadata["pair"] == "BTC/USDT":
            return dataframe
        # Exit when ratio reverts back above its rolling mean (z > 0).
        dataframe.loc[dataframe["ratio_z"] > 0, "exit_long"] = 1
        return dataframe
