"""
BTCLeaderBreakV4 — BTC 4h Donchian-15 break triggers entries on all pairs

Paradigm: breakout (cross-pair leader→follower)
Hypothesis: v0.3.0's BTCLeaderBreakX hit 1.07 Sharpe on bull-only 2023-2025
            data using a BTC 4h Donchian-10 break as the trigger for trades
            on every pair, with local volume confirmation and SMA50 patient
            exit (Findings 1+2). v0.4.0's regime-mixed timerange should
            stress-test that paradigm — does the cross-pair leader signal
            survive 2022 winter where BTC's own breakouts went very wrong
            briefly? Direct test, not a copy: Donchian-15 (less aggressive
            than v0.3.0's terminal 10), 4h regime gate (BTC 4h EMA50 > 4h
            EMA200), local-pair volume confirmation, SMA50 exit, and
            vol-target sizing. If V4 reaches ≥0.9 Sharpe in regime mix,
            v0.3.0's leader paradigm is regime-robust. If it collapses
            (e.g. <0.5), the v0.3.0 result was a bull-regime artifact.
            Replaces ChannelADXTrend (killed r8 — trend paradigm capped at
            +0.05 on this universe; freeing slot for the more interesting
            cross-regime test).
Parent: root (paradigm-resurrection of v0.3.0 BTCLeaderBreakX with v0.4.0
        affordances; structurally distinct from VolBreakoutSized which
        uses per-pair Donchian-24, no cross-pair leader)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes (BTC 4h informative + 4h vol-target + 1h trade base)
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class BTCLeaderBreakV4(IStrategy):
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

    @informative("4h", "BTC/USDT")
    def populate_indicators_btc_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r11: Donchian-10 (revert from 8). r10 confirmed 10 IS the local
        # optimum across both bull-only (v0.3.0) AND regime-mixed (v0.4.0)
        # data. Cross-regime parameter robustness on this knob.
        dataframe["donchian_high_10"] = dataframe["high"].rolling(10).max().shift(1)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Local-pair 4h ATR for vol-target sizing.
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r14: SMA75→SMA100. r13 SMA50→75 was a +0.10 Sharpe win on V4.
        # Continue patient-exit trend further to find the local optimum.
        dataframe["sma100"] = ta.SMA(dataframe, timeperiod=100)
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # BTC 4h Donchian-15 break (leader signal — same on every pair),
        # AND BTC 4h EMA50>EMA200 (BTC structural bull, slow regime),
        # AND local-pair 1h volume confirmation (v0.3.0 Finding 1: local
        # volume on trade pair >> signal-source volume).
        dataframe.loc[
            (dataframe["btc_usdt_close_4h"] > dataframe["btc_usdt_donchian_high_10_4h"])
            & (dataframe["btc_usdt_ema50_4h"] > dataframe["btc_usdt_ema200_4h"])
            & (dataframe["volume"] > 1.3 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # SMA50 patient ride-the-move exit (v0.3.0 Finding 2 — breakouts
        # benefit from slow exits, not responsive ones).
        dataframe.loc[dataframe["close"] < dataframe["sma100"], "exit_long"] = 1
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
        # Vol-target on the trade pair's 4h ATR (NOT BTC's). Each pair
        # de-risks based on its own volatility — BTC and SOL get different
        # stakes for the same BTC-leader signal.
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df.empty or "atr_pct_4h" not in df.columns:
            return proposed_stake
        atr_pct = df["atr_pct_4h"].iloc[-1]
        if atr_pct != atr_pct or atr_pct <= 0:
            return proposed_stake
        # r18: vol_target 0.020→0.015 (mirror Vol's r17 step).
        vol_target = 0.015
        scale = min(1.0, vol_target / atr_pct)
        stake = proposed_stake * scale
        return max(min_stake or 0.0, min(max_stake, stake))
