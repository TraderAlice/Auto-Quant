"""
BNBMeanRevertMulti — RSI<25 MR strategy on full 5-pair (fork of BNBMeanRevertSharp)

Paradigm: mean-reversion
Hypothesis: BNBMeanRevertSharp's r0 baseline showed RSI<25 + 1d EMA200
            regime filter produces consistently positive Sharpe across
            all 4 regimes when restricted to BNB. v0.4.0 finding was that
            "MR alpha lives in BNB" but it never tested whether the same
            signal mechanism (RSI<25 + 1d regime gate) on the FULL
            universe could find BNB-like behavior on other pairs that
            v0.4.0's broader basket configurations never isolated. This
            fork drops `pair_basket` to use the default full whitelist
            (BTC/ETH/SOL/BNB/AVAX). The aggregate is now 5-pair-averaged,
            so dilution is the expected risk: if BTC/ETH/SOL/AVAX have
            zero MR edge, the aggregate Sharpe should drop meaningfully.
            But per_pair output is now informative: it tells us pair by
            pair whether RSI<25 captures a real signal beyond BNB. This
            is a controlled cross-pair experiment that v0.4.0 could not
            run as cleanly.
Parent: BNBMeanRevertSharp (forked at r6; identical entry/exit logic,
        only `pair_basket` removed and test_timeranges adjusted)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class BNBMeanRevertMulti(IStrategy):
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

    # NO pair_basket → defaults to full 5-pair whitelist

    # Lighter timerange slate than parent (parent already runs 4 ranges on
    # BNB; here we run 5 pairs × 2 ranges to keep total backtest cost
    # reasonable while still covering bull and winter).
    test_timeranges = [
        ("full_5y",     "20210101-20251231"),
        ("winter_2022", "20220101-20221231"),
    ]

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Identical mechanism to BNBMeanRevertSharp r2: RSI<25 + price not
        # catastrophically below 1d trend. Universe expansion is the only
        # change.
        dataframe.loc[
            (dataframe["rsi"] < 25)
            & (dataframe["close"] > dataframe["ema200_1d"] * 0.85),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["rsi"] > 55, "exit_long"] = 1
        return dataframe
