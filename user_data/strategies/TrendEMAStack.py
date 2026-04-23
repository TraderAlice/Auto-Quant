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

    # Pair-specific EMA periods. ETH is higher-vol on 1h and whipsaws
    # with 9/21/50; slower 13/34/89 should reduce false crossovers there.
    # BTC keeps the validated 9/21/50.
    EMA_PERIODS = {
        "BTC/USDT": (9, 21, 50),
        "ETH/USDT": (13, 34, 89),
    }

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fast, mid, slow = self.EMA_PERIODS.get(metadata["pair"], (9, 21, 50))
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=fast)
        dataframe["ema_mid"] = ta.EMA(dataframe, timeperiod=mid)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=slow)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_sma20"] = dataframe["atr"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        fast_cross_up_mid = (dataframe["ema_fast"] > dataframe["ema_mid"]) & (
            dataframe["ema_fast"].shift(1) <= dataframe["ema_mid"].shift(1)
        )
        slow_trend_up = dataframe["ema_mid"] > dataframe["ema_slow"]
        bull_regime = dataframe["close"] > dataframe["ema200"]
        atr_expanding = dataframe["atr"] > dataframe["atr_sma20"]
        dataframe.loc[
            fast_cross_up_mid & slow_trend_up & bull_regime & atr_expanding,
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            dataframe["ema_fast"] < dataframe["ema_mid"], "exit_long"
        ] = 1
        return dataframe
