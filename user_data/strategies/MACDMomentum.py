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
        # MACD 19/39/12. Brackets: fast/slow 12/26 (0.32), 16/32 (0.52),
        # 19/39 (0.62) — 19/39 wins. Signal 9/12/15 → 12 (0.62 vs 0.60/0.55).
        macd = ta.MACD(dataframe, fastperiod=19, slowperiod=39, signalperiod=12)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]
        # Regime EMA 200. Shorter 100 (round 57) hurt — paradigm-specific:
        # MR benefits from regime reactivity, trend/momentum prefers stable
        # slow reference.
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_sma20"] = dataframe["atr"].rolling(20).mean()
        dataframe["vol_sma20"] = dataframe["volume"].rolling(20).mean()
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Entry: MACD cross up + MACD>0 + bull regime + ATR + volume.
        # close>ema50 (round 62) was redundant with existing filters.
        macd_cross_up = (dataframe["macd"] > dataframe["macdsignal"]) & (
            dataframe["macd"].shift(1) <= dataframe["macdsignal"].shift(1)
        )
        positive_macd = dataframe["macd"] > 0
        bull_regime = dataframe["close"] > dataframe["ema200"]
        atr_expanding = dataframe["atr"] > dataframe["atr_sma20"]
        vol_expansion = dataframe["volume"] > dataframe["vol_sma20"]
        # RSI<75. Bracket 70/75/80 → 75 optimum on Sharpe (0.67 vs 0.52/0.63).
        not_overbought = dataframe["rsi"] < 75
        dataframe.loc[
            macd_cross_up
            & positive_macd
            & bull_regime
            & atr_expanding
            & vol_expansion
            & not_overbought,
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit on MACD cross below signal (1-bar event). 2-bar confirmation
        # (round 63) delayed exits and cost Sharpe 0.62→0.52.
        dataframe.loc[
            (dataframe["macd"] < dataframe["macdsignal"])
            & (dataframe["macd"].shift(1) >= dataframe["macdsignal"].shift(1)),
            "exit_long",
        ] = 1
        return dataframe
