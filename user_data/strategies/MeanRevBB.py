"""
MeanRevBB — Bollinger lower-band bounce

Paradigm: mean-reversion
Hypothesis: BTC/ETH 1h bars that close below the lower Bollinger Band
            (20-period, sigma=2.0) tend to mean-revert back to the middle band
            within ~10-20 bars. No exit_profit_only trick — we want to measure
            the raw BB bounce edge cleanly.
Parent: root
Created: pending-first-commit
Status: active
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy


class MeanRevBB(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 100}
    # No stop. Confirmed across multiple rounds: any stop tight enough to
    # reduce DD (-5%, -15%) realizes recoverable losses and actually makes
    # DD worse or leaves it flat while cutting profit.
    stoploss = -0.99

    trailing_stop = False
    process_only_new_candles = True

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count: int = 210

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # BB period 15, sigma 2.0. Brackets confirmed: period 20/15/10 →
        # 15 wins; sigma 2.5/2.0/1.8 → 2.0 wins.
        bb = ta.BBANDS(dataframe, timeperiod=15, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_lower"] = bb["lowerband"]
        dataframe["bb_middle"] = bb["middleband"]
        dataframe["bb_upper"] = bb["upperband"]
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["vol_sma20"] = dataframe["volume"].rolling(20).mean()
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_sma20"] = dataframe["atr"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Confirmed reversal + regime + volume. ATR expansion (round 41)
        # hurt — MR signals often come from low-vol exhaustion bars, and
        # filtering for expanding ATR removes the best setups. ATR is
        # paradigm-specific: helps trend/momentum, hurts mean-reversion.
        prev_below_lower = dataframe["close"].shift(1) < dataframe["bb_lower"].shift(1)
        now_above_lower = dataframe["close"] > dataframe["bb_lower"]
        bull_regime = dataframe["close"] > dataframe["ema200"]
        vol_expansion = dataframe["volume"] > dataframe["vol_sma20"]
        dataframe.loc[
            prev_below_lower & now_above_lower & bull_regime & vol_expansion,
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit at upper band + RSI>65 (was >70). Earlier exit locks in more
        # trades. Trade-off: smaller avg winner but potentially more winners.
        dataframe.loc[
            (dataframe["close"] >= dataframe["bb_upper"])
            & (dataframe["rsi"] > 65),
            "exit_long",
        ] = 1
        return dataframe
