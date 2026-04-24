"""
BTCLeaderBreakX — fork of BTCLeaderBreak: tighter Donchian-15 + faster SMA20 exit

Paradigm: breakout
Hypothesis: BTCLeaderBreak hit 0.88 on Donchian-20 breaks + SMA50 exit. The
            Donchian-20 catches "established" breakouts but may miss earlier,
            higher-edge moves. Tighter Donchian-15 catches breaks 25% earlier;
            faster SMA20 exit closes faded breakouts before the SMA50 breach
            confirms. Risk: more chop entries, tighter exit may cut winners.
            This is a riskier variant testing whether earlier-and-faster
            outperforms BTCLeaderBreak's slower-and-stronger configuration.
Parent: BTCLeaderBreak
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class BTCLeaderBreakX(IStrategy):
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

    startup_candle_count: int = 200

    @informative("4h", "BTC/USDT")
    def populate_indicators_btc_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Donchian-10 (peak — established as local optimum at r27, confirmed by r28's regression at 7)
        dataframe["dc_high10"] = dataframe["high"].rolling(10).max()
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_ma20"] = dataframe["atr"].rolling(20).mean()
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Faster local-pair exit reference: SMA20 (was 50 in parent)
        dataframe["sma20"] = ta.SMA(dataframe, timeperiod=20)
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)  # kept for entry guard
        dataframe["vol_ma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        btc_break = (
            dataframe["btc_usdt_close_4h"] > dataframe["btc_usdt_dc_high10_4h"].shift(1)
        ) & (
            dataframe["btc_usdt_close_4h"].shift(1) <= dataframe["btc_usdt_dc_high10_4h"].shift(1)
        )
        dataframe.loc[
            btc_break
            & (dataframe["btc_usdt_atr_4h"] > dataframe["btc_usdt_atr_ma20_4h"])
            & (dataframe["close"] > dataframe["sma50"])              # entry guard kept on slower SMA
            & (dataframe["volume"] > dataframe["vol_ma20"] * 1.5),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Restore SMA50 exit to isolate whether it was the entry or the exit that hurt
        dataframe.loc[
            dataframe["close"] < dataframe["sma50"],
            "exit_long",
        ] = 1
        return dataframe
