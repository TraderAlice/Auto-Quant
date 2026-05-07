"""
MomentumMTFConfluence — multi-TF MACD momentum stack on regime-gated 1d uptrend

Paradigm: momentum
Hypothesis: v0.3.0's MACDMomentumMTF capped at 0.41 Sharpe on bull-only
            data — diagnosis was "v0.2.0's 0.67 was BTC/ETH-tuning that
            doesn't generalize". v0.4.0 question: does momentum survive
            regime mix at all, or does it collapse in 2022 winter where
            sustained uptrends are rare? Three-TF stack: 1d regime gate
            (close > 1d SMA50) defines tradeable universe; 4h MACD > MACD
            signal sets directional pulse; 1h close cross-up of 1h EMA20
            times the entry. Exit on 4h MACD < signal (regime-pulse break).
            Equal-weight (no sizing) — keeps this distinct from the two
            sized-breakout strategies. If MomentumMTFConfluence reaches
            ≥0.5 in regime mix, momentum paradigm is regime-survivable.
            If <0.2 it confirms v0.3.0's "momentum has BTC/ETH-bull
            ceiling" diagnosis transfers to mixed regimes too.
Parent: root (paradigm-resurrection of v0.3.0 MACDMomentumMTF, structurally
        leaner — single MACD trigger per TF, no MACD>0/RSI/ATR/strength stack)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes (1d regime + 4h MACD pulse + 1h entry)
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class MomentumMTFConfluence(IStrategy):
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
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        # r15: ADX strength gate — only enter when 4h trend has actual
        # directional movement, not just MACD-cross noise inside chop.
        # Tests if the structural 0.4 ceiling can be broken.
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 1d regime + 4h MACD bullish + 1h fresh close-cross-up of EMA20.
        dataframe.loc[
            (dataframe["close"] > dataframe["sma50_1d"])
            & (dataframe["macd_4h"] > dataframe["macdsignal_4h"])
            & (dataframe["adx_4h"] > 22)
            & (dataframe["close"] > dataframe["ema20"])
            & (dataframe["close"].shift(1) <= dataframe["ema20"].shift(1)),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit on 4h momentum break (MACD crosses below signal) — responsive
        # exit per v0.3.0 Finding 2 ("trend/momentum paradigms benefit from
        # responsive exits, not patient SMA-style").
        dataframe.loc[
            dataframe["macd_4h"] < dataframe["macdsignal_4h"],
            "exit_long",
        ] = 1
        return dataframe
