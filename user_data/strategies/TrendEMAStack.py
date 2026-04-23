"""
TrendEMAStack — Stacked-EMA trend follower

Paradigm: trend-following
Hypothesis: BTC/ETH 1h has persistent trends detectable by EMA stack alignment.
            When EMA9 > EMA21 > EMA50 AND close > EMA9, measurable upside
            momentum exists to capture. Exit when the stack order breaks or
            close falls below EMA21. v0.1.0 never tested trend-following
            so this fills an unexplored paradigm.
Parent: root
Created: pending-first-commit
Status: active
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy


class TrendEMAStack(IStrategy):
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
        dataframe["ema9"] = ta.EMA(dataframe, timeperiod=9)
        dataframe["ema21"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_sma20"] = dataframe["atr"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Entry layers: crossover event + slow-trend + macro regime + ATR
        # expansion. Green-candle confirmation (round 18) hurt — crossover
        # bars can close red intra-bar even on genuine signals.
        ema9_cross_up_21 = (dataframe["ema9"] > dataframe["ema21"]) & (
            dataframe["ema9"].shift(1) <= dataframe["ema21"].shift(1)
        )
        slow_trend_up = dataframe["ema21"] > dataframe["ema50"]
        bull_regime = dataframe["close"] > dataframe["ema200"]
        atr_expanding = dataframe["atr"] > dataframe["atr_sma20"]
        dataframe.loc[
            ema9_cross_up_21 & slow_trend_up & bull_regime & atr_expanding,
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit on stack break (ema9<ema21) OR ATR-based chandelier: close
        # drops more than 2*ATR below the 22-bar rolling high-close. The
        # chandelier catches sharp reversals that ema-cross would lag.
        chandelier_hit = dataframe["close"] < (
            dataframe["close"].rolling(22).max() - 2 * dataframe["atr"]
        )
        stack_break = dataframe["ema9"] < dataframe["ema21"]
        dataframe.loc[stack_break | chandelier_hit, "exit_long"] = 1
        return dataframe
