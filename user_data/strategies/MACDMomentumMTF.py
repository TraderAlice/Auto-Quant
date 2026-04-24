"""
MACDMomentumMTF — MACD cross-up momentum + 1d regime + 4h ATR + RSI 75 ceiling

Paradigm: momentum
Hypothesis: v0.2.0's MACDMomentum was the clean-edge leader at Sharpe 0.67 on
            BTC+ETH 1h (no MTF, no cross-pair). v0.3.0 evidence so far says
            ATR-expansion is universal for directional paradigms and 1d regime
            filter is generally helpful. Building a momentum strategy that bakes
            those in from round 0 plus adds the 4h ATR-expansion via @informative
            should at minimum match v0.2.0's 0.67 ceiling and ideally exceed it.
            Also bakes in v0.2.0's "RSI 75 = BTC/ETH 1h overbought ceiling"
            finding as both an entry filter and an exit signal.
Parent: root (paradigm-inspired by v0.2.0's MACDMomentum, MTF/ATR baked in)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class MACDMomentumMTF(IStrategy):
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

    startup_candle_count: int = 250  # 1d EMA200 warmup

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_ma20"] = dataframe["atr"].rolling(20).mean()
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macd_signal"] = macd["macdsignal"]
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["macd"] > dataframe["macd_signal"])                       # MACD above signal
            & (dataframe["macd"].shift(1) <= dataframe["macd_signal"].shift(1))  # cross-up event
            & (dataframe["macd"] > 0)                                            # MACD in positive territory
            & (dataframe["close"] > dataframe["ema200_1d"])                      # 1d bull regime
            & (dataframe["atr_4h"] > dataframe["atr_ma20_4h"])                   # 4h ATR expansion
            & (dataframe["rsi"] < 75),                                           # not yet overbought
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["macd"] < dataframe["macd_signal"])  # MACD cross-down
            | (dataframe["rsi"] > 75),                      # v0.2.0 BTC/ETH 1h overbought line
            "exit_long",
        ] = 1
        return dataframe
