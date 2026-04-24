"""
VolBBSqueeze — 4h Bollinger-Band squeeze breakout, 1h entry on confirmation

Paradigm: volatility
Hypothesis: v0.2.0's VolSqueezeBreak was killed at Sharpe 0.17 — agent noted
            squeeze paradigm needs lower frequency than 1h. v0.3.0 affordance:
            move squeeze detection to 4h, then enter on 1h once break confirms.
            BB squeeze = 4h BB-width in bottom quartile of last 50 4h bars.
            Break = 4h close > 4h upper band after squeeze. Direction is
            implicitly long (we don't short on this universe). 1d EMA200
            regime gate to avoid bear-market squeeze releases that fail.
Parent: root (paradigm-inspired by v0.2.0's killed VolSqueezeBreak, restructured to MTF)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class VolBBSqueeze(IStrategy):
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

    # 4h indicators with 50-bar window need ~250 hourly bars warmup; 1d EMA200 dominates
    startup_candle_count: int = 250

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        upper, middle, lower = ta.BBANDS(
            dataframe["close"], timeperiod=20, nbdevup=2.0, nbdevdn=2.0, matype=0
        )
        dataframe["bb_upper"] = upper
        dataframe["bb_middle"] = middle
        dataframe["bb_lower"] = lower
        # BB width relative to its own 50-bar history — squeeze when width is in bottom quartile
        dataframe["bb_width"] = (upper - lower) / middle
        # q33 squeeze threshold (peak via r23 / r32 — tighter q20 hurts compounding, looser q50 over-trades)
        dataframe["bb_width_q33"] = dataframe["bb_width"].rolling(50).quantile(0.33)
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        squeeze_then_break = (
            (dataframe["bb_width_4h"].shift(1) <= dataframe["bb_width_q33_4h"].shift(1))  # was squeezed
            & (dataframe["close_4h"] > dataframe["bb_upper_4h"])                          # now breaking upper band
        )
        dataframe.loc[
            squeeze_then_break
            & (dataframe["close"] > dataframe["ema200_1d"]),  # 1d bull regime
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            dataframe["close"] < dataframe["sma50"],  # 1h trend break — patient exit
            "exit_long",
        ] = 1
        return dataframe
