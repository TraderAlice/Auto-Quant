"""
MajorsBreakout — majors Donchian breakout with 4h trend gate (momentum paradigm).

Paradigm: breakout (trend-following / momentum)
Hypothesis: BTC/ETH 1h Donchian-48-channel breakouts confirmed by 4h EMA50 >
            EMA200 trend gate capture regime-persistent momentum; patient SMA75
            exit suits breakout family (v0.4.1 narrow). Orthogonal to MR pair —
            should diversify portfolio correlation and hedge MR winter dynamics.
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

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dc_window = 48
        dataframe["dc_high"] = dataframe["high"].rolling(dc_window, min_periods=dc_window).max()
        dataframe["sma75"] = ta.SMA(dataframe, timeperiod=75)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] > dataframe["dc_high"].shift(1))
            & (dataframe["ema50_4h"] > dataframe["ema200_4h"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["close"] < dataframe["sma75"]), "exit_long"] = 1
        return dataframe
