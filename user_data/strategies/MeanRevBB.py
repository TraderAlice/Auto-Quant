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

from datetime import datetime

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.persistence import Trade
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
        bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_lower"] = bb["lowerband"]
        dataframe["bb_middle"] = bb["middleband"]
        dataframe["bb_upper"] = bb["upperband"]
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Confirmed-reversal entry: prior close<lower, now>lower, in bull regime
        # (close>EMA200). RSI<30 confluence (round 21) over-filters. Weekday
        # filter (round 17) not meaningful on BTC/ETH 1h.
        prev_below_lower = dataframe["close"].shift(1) < dataframe["bb_lower"].shift(1)
        now_above_lower = dataframe["close"] > dataframe["bb_lower"]
        bull_regime = dataframe["close"] > dataframe["ema200"]
        dataframe.loc[
            prev_below_lower & now_above_lower & bull_regime, "enter_long"
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit only when price hits upper band AND RSI>70 — wait for genuine
        # overbought confirmation. Regime-break exit (round 15) cut DD but
        # also cut profit equally by realizing recoverable losses.
        dataframe.loc[
            (dataframe["close"] >= dataframe["bb_upper"])
            & (dataframe["rsi"] > 70),
            "exit_long",
        ] = 1
        return dataframe

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> str | None:
        # Stale-loser exit: trade held >96 bars (4 days) AND still losing >5%.
        # Targets truly stuck positions without cutting normal recoveries.
        age_hours = (current_time - trade.open_date_utc).total_seconds() / 3600
        if age_hours > 96 and current_profit < -0.05:
            return "stale_loser"
        return None
