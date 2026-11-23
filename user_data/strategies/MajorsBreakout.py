"""
MajorsBreakout — majors Donchian breakout with 4h trend gate (momentum paradigm).

Paradigm: breakout (trend-following / momentum)
Hypothesis: BTC/ETH 1h Donchian-48 breakouts confirmed by 4h EMA50 > EMA200 AND
            price above the 1d SMA20 (breakout WITH daily trend, not into daily
            resistance) capture regime-persistent momentum and cut bear-whipsaws;
            patient SMA75 exit suits breakout family. Orthogonal momentum leg.
Parent: root (v0.4.1 PerPairMR BTC+ETH branch lineage, standalone)
Created: round0
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class MajorsBreakout(IStrategy):
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

    startup_candle_count: int = 900

    pair_basket = ["BTC/USDT", "ETH/USDT"]


    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma20"] = ta.SMA(dataframe, timeperiod=20)
        return dataframe
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dc_window = 48
        dataframe["dc_high"] = dataframe["high"].rolling(dc_window, min_periods=dc_window).max()
        dataframe["sma75"] = ta.SMA(dataframe, timeperiod=75)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] > dataframe["dc_high"].shift(1))
            & (dataframe["ema50_4h"] > dataframe["ema200_4h"])
            & (dataframe["close"] > dataframe["sma20_1d"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["close"] < dataframe["sma75"]), "exit_long"] = 1
        return dataframe
