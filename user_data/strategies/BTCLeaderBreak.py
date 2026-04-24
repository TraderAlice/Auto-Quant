"""
BTCLeaderBreak — cross-pair breakout: BTC strength on 4h drives entries on all pairs

Paradigm: breakout
Hypothesis: BTC tends to lead the broader crypto market on 4h+ timeframes. When
            BTC breaks above its recent 4h high (Donchian-20), the alts often
            follow within the next few 1h bars. Enter long on any pair when
            (a) BTC has just broken its 4h-20 high AND (b) the local pair is
            above its own 1h-50 SMA (trend-not-falling guard). v0.2.0's pure-1h
            Donchian breakout (TrendDonchian) drowned in false signals; gating
            on BTC at a higher TF should filter to higher-conviction breakouts.
Parent: root (loosely inspired by v0.2.0's killed TrendDonchian, restructured cross-pair + higher TF)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class BTCLeaderBreak(IStrategy):
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
        # Donchian-20 high on 4h BTC (excluding the current bar via shift in entry)
        dataframe["dc_high20"] = dataframe["high"].rolling(20).max()
        # ATR-expansion gate: only count BTC breaks that come with vol-expansion conviction
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_ma20"] = dataframe["atr"].rolling(20).mean()
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["vol_ma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # BTC just broke its 4h-20 Donchian high (event: this bar's BTC close exceeds
        # the prior bar's high20). Use shift(1) to compare against the strictly-prior
        # rolled max so the breakout bar itself doesn't self-include.
        btc_break = (
            dataframe["btc_usdt_close_4h"] > dataframe["btc_usdt_dc_high20_4h"].shift(1)
        ) & (
            dataframe["btc_usdt_close_4h"].shift(1) <= dataframe["btc_usdt_dc_high20_4h"].shift(1)
        )
        dataframe.loc[
            btc_break
            & (dataframe["btc_usdt_atr_4h"] > dataframe["btc_usdt_atr_ma20_4h"])  # BTC vol-expansion conviction
            & (dataframe["close"] > dataframe["sma50"])                            # local pair not in down-trend
            & (dataframe["volume"] > dataframe["vol_ma20"] * 1.2),                 # local pair volume confirmation
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit when local pair drops below its 50-SMA — trend-follow exit
        dataframe.loc[
            dataframe["close"] < dataframe["sma50"],
            "exit_long",
        ] = 1
        return dataframe
