"""
VolBreakoutEqual — fork of VolBreakoutSized w/ vol-target sizing REMOVED

Paradigm: breakout
Hypothesis: VolBreakoutSized hit 1.085 Sharpe on r1 with all 5 pairs
            positive — using per-pair Donchian-24 + 4h EMA50>EMA200 regime
            + 1.3x volume + SMA30 patient exit + vol-target sizing. v0.4.0
            program.md raised the question: when sizing-aware strategies
            survive regime mix, is the edge real OR is the sizing the
            secret sauce? This fork removes ONLY the custom_stake_amount
            (defaults to equal-weight) — every entry/exit/regime knob
            otherwise identical to parent. Clean isolation experiment:
            if VolBreakoutEqual matches parent at ~1.0 Sharpe, vol-target
            wasn't doing real work; if it collapses (e.g. < 0.5), the
            sizing carries meaningful 2022-survival edge.
Parent: VolBreakoutSized (r6 baseline at 1.0853)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class VolBreakoutEqual(IStrategy):
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

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        # ATR retained on 4h since other indicators stay aligned with parent;
        # we just don't consume it for sizing.
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["donchian_high_24"] = dataframe["high"].rolling(24).max().shift(1)
        dataframe["sma30"] = ta.SMA(dataframe, timeperiod=30)
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] > dataframe["donchian_high_24"])
            & (dataframe["ema50_4h"] > dataframe["ema200_4h"])
            & (dataframe["volume"] > 1.3 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["close"] < dataframe["sma30"], "exit_long"] = 1
        return dataframe

    # NOTE: no custom_stake_amount → FreqTrade default equal-weight applies.
    # This is the entire point of the fork. Do not re-add.
