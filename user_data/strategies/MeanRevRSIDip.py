"""
MeanRevRSIDip — RSI dip-buy w/ daily regime gate AND vol-conditional sizing

Paradigm: mean-reversion
Hypothesis: v0.3.0's MeanRevBBClean failed in the bull-only 5-pair universe
            (-0.24 Sharpe, killed r6) — its v0.2.0 recipes did not transfer.
            v0.4.0's regime-mixed timerange (2021-2025 incl. 2022 winter) is
            structurally HOSTILE to mean-reversion: catching knives in 2022
            is exactly how MR strategies blow up. Hypothesis: a soft 1d
            regime gate (close > 1d SMA50 — not the strict EMA200) plus a
            vol-conditional stake (smaller stake on high-4h-ATR pairs/bars)
            should let MR survive 2022 by sizing down WHEN the dip-buy is
            riskiest, instead of refusing to trade. This tests whether
            dynamic sizing can rescue a paradigm that pure equal-weight
            kills in regime mix.
Parent: root (paradigm-inspired by v0.2.0 MeanRevRSI / v0.3.0 MeanRevBBClean,
        but distinct: SMA50-not-EMA200 regime, vol-conditional sizing is the
        primary new mechanism)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class MeanRevRSIDip(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 100}
    # r3 added stoploss=-0.07; r4 reverts to -0.99 — stop realized losses
    # on dips that would have recovered (Sharpe 0.03→-0.22). MR entries
    # are structurally meant to be temporarily underwater; stops fight
    # the paradigm. Defense against bear is now structural via stricter
    # regime gate (SMA100 1d), not stoploss.
    stoploss = -0.99
    trailing_stop = False
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count: int = 250

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r4: SMA50 → SMA100 — stricter regime gate to STRUCTURALLY exclude
        # 2022-style bear conditions from the dip-buy universe instead of
        # sizing through them.
        dataframe["sma100"] = ta.SMA(dataframe, timeperiod=100)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] < 28)
            & (dataframe["close"] > dataframe["sma100_1d"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["rsi"] > 65, "exit_long"] = 1
        return dataframe

    def custom_stake_amount(
        self,
        pair: str,
        current_time,
        current_rate: float,
        proposed_stake: float,
        min_stake,
        max_stake: float,
        leverage: float,
        entry_tag: str,
        side: str,
        **kwargs,
    ) -> float:
        # Vol-conditional sizing: if 4h ATR% is high (> 3.5%) we're in a
        # high-vol regime — likely 2022 winter or alt-crash. Halve the stake.
        # Below 2% we're in calm-bull territory — full size. Linear in between.
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df.empty or "atr_pct_4h" not in df.columns:
            return proposed_stake
        atr_pct = df["atr_pct_4h"].iloc[-1]
        if atr_pct != atr_pct:  # NaN guard during warmup
            return proposed_stake
        lo, hi = 0.02, 0.035
        if atr_pct <= lo:
            scale = 1.0
        elif atr_pct >= hi:
            scale = 0.5
        else:
            scale = 1.0 - 0.5 * (atr_pct - lo) / (hi - lo)
        stake = proposed_stake * scale
        return max(min_stake or 0.0, min(max_stake, stake))
