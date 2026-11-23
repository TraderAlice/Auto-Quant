"""
AltsCrashRebound — alts drawdown-rebound (counter-trend MR) on high-beta alts.

Paradigm: volatility (capitulation rebound / counter-trend mean-reversion)
Hypothesis: SOL/AVAX/BNB 30-day drawdowns beyond -25% confirmed by RSI(14) < 35
            rebound within ~2-4 weeks; tight exits (RSI > 55 or SMA20 reclaim)
            suit counter-trend family (v0.4.1 narrow: patient exits backfire here).
            DD-depth conviction sizing scales with dislocation depth.
Parent: root (v0.4.1 CrashRebound lineage, re-derived)
Created: round0
Status: active
Uses MTF: no
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy


class AltsCrashRebound(IStrategy):
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

    startup_candle_count: int = 800

    pair_basket = ["SOL/USDT", "AVAX/USDT", "BNB/USDT"]

    def custom_stake_amount(
        self, pair: str, current_time, current_rate: float, proposed_stake: float,
        min_stake, max_stake: float, leverage: float, entry_tag: str, side: str,
        **kwargs,
    ) -> float:
        try:
            df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            dd = float(df["dd_pct"].iloc[-1])
        except Exception:
            return proposed_stake
        # DD-depth conviction: deeper drawdown -> larger stake, clamp [0.5x, 2x]
        depth = min(50.0, max(0.0, -dd))
        scale = min(2.0, max(0.5, depth / 25.0))
        return max(min_stake or 0.0, min(max_stake, proposed_stake * scale))

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["sma20"] = ta.SMA(dataframe, timeperiod=20)
        lookback = 720  # ~30d on 1h
        roll_max = dataframe["close"].rolling(lookback, min_periods=lookback).max()
        dataframe["dd_pct"] = (dataframe["close"] / roll_max - 1.0) * 100.0
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["dd_pct"] < -25.0) & (dataframe["rsi"] < 35.0),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] > 55.0) | (dataframe["close"] > dataframe["sma20"]),
            "exit_long",
        ] = 1
        return dataframe
