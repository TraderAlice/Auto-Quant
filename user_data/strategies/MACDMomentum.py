"""
MACDMomentum — MACD zero-line + signal-cross momentum

Paradigm: other (momentum oscillator)
Hypothesis: MACD captures trend acceleration distinct from EMA crossovers
            (trend-following) and BB bounces (mean-reversion). A cross of
            MACD above its signal line while MACD>0 indicates accelerating
            bullish momentum. Provides a complementary signal to the stack
            crossover in TrendEMAStack — MACD can trigger within an existing
            trend (re-accel), whereas stack cross only fires on alignment.
Parent: root
Created: pending-first-commit
Status: active

Replaces VolSqueezeBreak (killed round 27). VolSq achieved +0.17 Sharpe /
47-49 trades with clean pf 1.74 but thin sample size. Re-allocating slot
to test a fundamentally different signal family (momentum oscillator).
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy


class MACDMomentum(IStrategy):
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
        # Slower MACD (19/39/9) — round 30 faster 8/17/9 was noisier.
        # Testing the opposite direction from the 12/26/9 baseline.
        macd = ta.MACD(dataframe, fastperiod=19, slowperiod=39, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_sma20"] = dataframe["atr"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Entry: MACD cross up + MACD>0 + bull regime + ATR expanding.
        # Histogram-accelerating filter (round 29) was tautological.
        macd_cross_up = (dataframe["macd"] > dataframe["macdsignal"]) & (
            dataframe["macd"].shift(1) <= dataframe["macdsignal"].shift(1)
        )
        positive_macd = dataframe["macd"] > 0
        bull_regime = dataframe["close"] > dataframe["ema200"]
        atr_expanding = dataframe["atr"] > dataframe["atr_sma20"]
        dataframe.loc[
            macd_cross_up & positive_macd & bull_regime & atr_expanding,
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit on MACD cross below signal (momentum fading). Simpler than
        # stack-break analog — MACD crossover is the symmetric reverse signal.
        dataframe.loc[
            (dataframe["macd"] < dataframe["macdsignal"])
            & (dataframe["macd"].shift(1) >= dataframe["macdsignal"].shift(1)),
            "exit_long",
        ] = 1
        return dataframe
