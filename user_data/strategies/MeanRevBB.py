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
    # No hard stop. v0.1.0 aha#1 + round-3 here both confirmed: at 1h on
    # BTC/ETH, stops cut recoverable bounces. Regime filter (close>EMA200)
    # already bounds downside exposure.
    stoploss = -0.99

    trailing_stop = False
    process_only_new_candles = True

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count: int = 210

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_lower"] = bb["lowerband"]
        dataframe["bb_middle"] = bb["middleband"]
        dataframe["bb_upper"] = bb["upperband"]
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Regime filter: only bounce-bounce in bullish regime to avoid catching
        # knives during downtrends. Close below lower BB AND close above EMA200.
        dataframe.loc[
            (dataframe["close"] < dataframe["bb_lower"])
            & (dataframe["close"] > dataframe["ema200"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit at upper band, not middle. Round-3 analysis: wr 66% with pf<1
        # means winners too small. Extending exit target trades wr for bigger
        # winners; regime filter keeps us in a context where overshoot is plausible.
        dataframe.loc[dataframe["close"] >= dataframe["bb_upper"], "exit_long"] = 1
        return dataframe
