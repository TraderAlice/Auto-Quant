"""
AltsBollBreak — Bollinger upper-band breakout on alts (SOL/AVAX/BNB), full + winter

Paradigm: volatility (breakout-flavored, but the trigger is a Bollinger
          band excursion rather than a Donchian high — distinct mechanism
          from v0.4.0's VolBreakoutSized)
Hypothesis: v0.4.0's per-pair Donchian breakout (VolBreakoutSized) hit
            Sharpe 1.122 on the full 5-pair universe with 4h EMA regime
            gate and SMA50 patient exit. The Bollinger upper-band variant
            is a structurally distinct volatility signal: it triggers on
            a price excursion of >2σ above a 20-bar mean, which fires on
            statistical breakouts rather than range-extreme breakouts. The
            two paradigms should have meaningfully different trade samples.
            Restricting to alts (SOL, AVAX, BNB) acts on the v0.4.0
            observation that breakouts have more juice on alts than on
            BTC majors, where Donchian breakouts on BTC were mediocre at
            best. The 4h ADX>25 filter cuts chop — Bollinger breakouts
            in flat regimes are noise. Equal-weight sizing keeps the edge
            question clean (v0.4.0 r7 separation: sizing is not edge).
Parent: root (paradigm-adjacent to v0.4.0 VolBreakoutSized but distinct
        signal mechanism + alts-only universe + ADX chop filter)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class AltsBollBreak(IStrategy):
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

    pair_basket = ["SOL/USDT", "AVAX/USDT", "BNB/USDT"]

    test_timeranges = [
        ("full_5y",     "20210101-20251231"),
        ("winter_2022", "20220101-20221231"),
    ]

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r1: Bollinger upper-band single-bar trigger replaced with Donchian-48
        # sustained-break (2 consecutive closes above 48-bar prior high). The
        # BB-single-bar version caught local tops that reverted (wr 32.7%).
        dataframe["donchian_high_48"] = dataframe["high"].rolling(48).max().shift(1)
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r1: 2-bar sustained break + 4h macro bull (ema50>ema200) replaces
        # ADX-only chop gate. The 4h macro filter is the load-bearing change —
        # ADX>25 fired in winter chop too, contributing to -2.33 winter sharpe.
        # r2: add 1d close > 1d EMA200 macro-regime gate on top of 4h ema
        # cross. r1 had winter -32% on 11 trades all losing — those were
        # entries during 2022 with 4h ema50>ema200 momentary upticks but
        # the 1d trend already broken down. The 1d filter cuts those
        # structurally.
        prior_close_above = dataframe["close"].shift(1) > dataframe["donchian_high_48"].shift(1)
        dataframe.loc[
            (dataframe["close"] > dataframe["donchian_high_48"])
            & prior_close_above
            & (dataframe["ema50_4h"] > dataframe["ema200_4h"])
            & (dataframe["close"] > dataframe["ema200_1d"])
            & (dataframe["volume"] > 1.3 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r1: Exit on 4h macro flip (ema50 < ema200) — patient ride-the-move.
        # Replaces the BB-mid exit which was too tight for sustained breakouts.
        dataframe.loc[dataframe["ema50_4h"] < dataframe["ema200_4h"], "exit_long"] = 1
        return dataframe
