"""
ChannelADXTrend — 1d-regime + 4h-ADX/EMA20>50 + 1h EMA50 pullback-and-reclaim

Paradigm: trend-following
Hypothesis: r1 round-1 result was catastrophic (Sharpe -2.14, 4404 trades,
            WR 19%, profit -73%) — the EMA20 cross-back entry fires on
            every wiggle through a fast MA, and ADX>22 + 1d SMA100 alone
            don't filter the noise. r2 evolution: keep the regime + ADX
            scaffolding but (a) tighten ADX>25, (b) add a 4h EMA20>EMA50
            structural-trend gate, and (c) replace the noisy EMA20 cross
            with a slower "pullback to 1h EMA50 then reclaim" entry. This
            should cut trade frequency 5-10x and lift WR — the question is
            whether the surviving trades carry meaningful edge.
Parent: root (self-evolution; r1 commit 7a58a63 was the catastrophic baseline)
Created: 7a58a63 (r1)
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class ChannelADXTrend(IStrategy):
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
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma100"] = ta.SMA(dataframe, timeperiod=100)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Pullback-and-reclaim: prior bar touched/dipped through 1h EMA50;
        # current bar closes back above it. Combined with multi-TF trend
        # confirmation (1d SMA100 regime + 4h ADX>25 + 4h EMA20>EMA50).
        dataframe.loc[
            (dataframe["close"] > dataframe["sma100_1d"])
            & (dataframe["adx_4h"] > 25)
            & (dataframe["ema20_4h"] > dataframe["ema50_4h"])
            & (dataframe["close"] > dataframe["ema50"])
            & (dataframe["low"].shift(1) <= dataframe["ema50"].shift(1)),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["close"] < dataframe["ema50"], "exit_long"] = 1
        return dataframe
