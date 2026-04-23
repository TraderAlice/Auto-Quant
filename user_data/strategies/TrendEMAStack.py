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
        # Regime EMA 200. Shorter 100 (round 57) hurt trend-follower.
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        # ATR 21. Bracket 14/21/28 → 21 optimum on Sharpe (0.36 vs 0.34/0.35).
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=21)
        dataframe["atr_sma20"] = dataframe["atr"].rolling(20).mean()
        dataframe["vol_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Entry: crossover + slow-trend + macro + ATR + volume. RSI<70
        # (round 46) nudged pf up but cost Sharpe — Sharpe is primary metric.
        # Slower crossover: ema21 cross up ema50. Fewer/bigger trend-inception
        # signals than ema9/21. Using ema9>ema21 as an additional context
        # filter (short-term stack must also be bullish).
        ema21_cross_up_50 = (dataframe["ema21"] > dataframe["ema50"]) & (
            dataframe["ema21"].shift(1) <= dataframe["ema50"].shift(1)
        )
        short_stack_bull = dataframe["ema9"] > dataframe["ema21"]
        bull_regime = dataframe["close"] > dataframe["ema200"]
        atr_expanding = dataframe["atr"] > dataframe["atr_sma20"]
        vol_expansion = dataframe["volume"] > dataframe["vol_sma20"]
        dataframe.loc[
            ema21_cross_up_50
            & short_stack_bull
            & bull_regime
            & atr_expanding
            & vol_expansion,
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit on primary stack break: ema21 < ema50 (the slow crossover
        # used for entry reverses).
        dataframe.loc[
            dataframe["ema21"] < dataframe["ema50"], "exit_long"
        ] = 1
        return dataframe
