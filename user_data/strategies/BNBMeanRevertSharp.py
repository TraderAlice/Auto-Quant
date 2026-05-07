"""
BNBMeanRevertSharp — single-pair RSI mean-reversion on BNB across 4 regimes

Paradigm: mean-reversion
Hypothesis: v0.4.0 found that mean-reversion failed broadly on the 5-pair
            universe but was structurally BNB-skewed — both MR attempts
            (MeanRevRSIDip, CrossPairMR) showed BNB carrying most of the
            trade activity / non-zero edge with the other 4 pairs near zero.
            v0.4.0 lacked the affordance to act on this; it could only note
            it. v0.4.1's pair_basket lets us declare "MR is a BNB
            phenomenon" as a first-class design choice. Hypothesis: a tight
            RSI(14)<25 entry / RSI>55 exit on BNB alone, gated by a 1d
            EMA200 regime filter (skip catching knives in deep bear), will
            show clean mean-reversion edge across bull/winter/recovery
            without the noise of the other 4 pairs averaging the signal away.
            Equal-weight (no custom_stake_amount) — v0.4.0 r7 ablation
            already proved sizing carries no edge, so we test the pure
            signal here.
Parent: root (paradigm-inspired by v0.4.0 MeanRevRSIDip but structurally
        different: single-pair basket, regime gate, no sizing)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class BNBMeanRevertSharp(IStrategy):
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

    pair_basket = ["BNB/USDT"]

    test_timeranges = [
        ("bull_2021",      "20210101-20211231"),
        ("winter_2022",    "20220101-20221231"),
        ("recovery_23_25", "20230101-20251231"),
        ("full_5y",        "20210101-20251231"),
    ]

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r1: RSI<25 → RSI<30. Signal validated at <25 (all 4 regimes positive,
        # WR 68-81%) but trade count was too low (16/25/72/115). Loosening
        # threshold should triple trade count and lift per-regime profit
        # toward profit_floor (20%).
        dataframe.loc[
            (dataframe["rsi"] < 30)
            & (dataframe["close"] > dataframe["ema200_1d"] * 0.85),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["rsi"] > 55, "exit_long"] = 1
        return dataframe
