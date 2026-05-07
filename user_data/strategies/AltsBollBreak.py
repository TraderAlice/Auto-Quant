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
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        bb_period = 20
        bb_std = 2.0
        sma = dataframe["close"].rolling(bb_period).mean()
        std = dataframe["close"].rolling(bb_period).std()
        dataframe["bb_upper"] = sma + bb_std * std
        dataframe["bb_mid"] = sma
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Statistical breakout: close pierces upper Bollinger band, with
        # volume confirmation and a trending-not-chop 4h ADX gate.
        dataframe.loc[
            (dataframe["close"] > dataframe["bb_upper"])
            & (dataframe["adx_4h"] > 25)
            & (dataframe["volume"] > 1.3 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit on mean reversion to band midline (not the lower band — that
        # would let losers run too long).
        dataframe.loc[dataframe["close"] < dataframe["bb_mid"], "exit_long"] = 1
        return dataframe
