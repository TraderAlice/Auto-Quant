"""
CrossPairRatio — BTC/ETH ratio z-score mean-reversion (cross-pair statistical MR)

Paradigm: mean-reversion (cross-pair ratio)
Hypothesis: v0.4.0 had CrossPairMR (alt/BTC ratio z-score) which was
            killed at r7 with the verdict "MR paradigm exhausted on this
            5-pair regime-mixed universe" — but that test was on alt/BTC
            ratios where the alt side dominates noise and the MR signal
            is asymmetric. BTC/ETH is a different beast: two
            comparably-liquid majors with strong long-run cointegration
            but periodic decoupling (e.g., 2021 ETH outperformance,
            2022 BTC relative strength). Hypothesis: when BTC/ETH ratio
            stretches >2σ from a 200-bar rolling mean, it tends to
            revert within ~30 days. Trade BOTH pairs symmetrically: when
            ratio < -2σ → ETH cheap relative to BTC → enter long ETH;
            when ratio > +2σ → BTC cheap relative to ETH → enter long
            BTC. (We can only go long in spot — so the "expensive" leg
            stays unowned rather than being shorted.) Universe restricted
            to BTC+ETH only — adding alts dilutes the cointegration
            premise. test_timeranges spans bull/winter/full to make the
            cross-regime claim falsifiable.
Parent: root (paradigm-distinct from prior MR strategies which were
        single-pair RSI or single-pair BB; this is two-pair ratio
        z-score MR with symmetric long-only entries)
Created: pending — fill in after first commit
Status: active
Uses MTF: no (1h-only; ratio computed via informative_pairs cross-ref)
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class CrossPairRatio(IStrategy):
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

    pair_basket = ["BTC/USDT", "ETH/USDT"]

    test_timeranges = [
        ("bull_2021",   "20210101-20211231"),
        ("winter_2022", "20220101-20221231"),
        ("full_5y",     "20210101-20251231"),
    ]

    @informative("1h", "BTC/USDT")
    def populate_indicators_btc(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Pull BTC close into every pair's dataframe as `btc_usdt_close_1h`.
        return dataframe

    @informative("1h", "ETH/USDT")
    def populate_indicators_eth(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Pull ETH close into every pair's dataframe as `eth_usdt_close_1h`.
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Ratio = BTC/ETH price (always uses the cross-pulled columns so
        # the value is identical regardless of which pair we're processing).
        ratio = dataframe["btc_usdt_close_1h"] / dataframe["eth_usdt_close_1h"]
        ratio_mean = ratio.rolling(200).mean()
        ratio_std = ratio.rolling(200).std()
        dataframe["ratio_z"] = (ratio - ratio_mean) / ratio_std
        dataframe["ratio"] = ratio
        dataframe["ratio_mean"] = ratio_mean
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata.get("pair", "")
        if pair == "ETH/USDT":
            # Ratio < -2σ → BTC cheap relative to ETH … wait, ratio = BTC/ETH.
            # If ratio is LOW, BTC is relatively cheaper than usual vs ETH.
            # If ratio is HIGH, ETH is relatively cheaper than BTC.
            # We want to long the CHEAPER leg.
            # Ratio HIGH → ETH cheap → long ETH.
            dataframe.loc[dataframe["ratio_z"] > 2.0, "enter_long"] = 1
        elif pair == "BTC/USDT":
            # Ratio LOW → BTC cheap → long BTC.
            dataframe.loc[dataframe["ratio_z"] < -2.0, "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit when ratio crosses back through its rolling mean
        # (z-score crosses 0).
        pair = metadata.get("pair", "")
        if pair == "ETH/USDT":
            dataframe.loc[dataframe["ratio_z"] < 0, "exit_long"] = 1
        elif pair == "BTC/USDT":
            dataframe.loc[dataframe["ratio_z"] > 0, "exit_long"] = 1
        return dataframe
