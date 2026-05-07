"""
VolBreakoutSized — per-pair Donchian-24 break w/ 4h regime + vol-target sizing

Paradigm: breakout
Hypothesis: v0.3.0's BTCLeaderBreakX hit 1.07 via cross-pair Donchian on BTC
            triggering trades on every pair — but its single-regime success
            doesn't tell us whether breakouts as a paradigm survive 2022 bear.
            Try a per-pair Donchian-24 (24-bar = 1 day at 1h) WITHOUT the
            BTC-leader cross-pair lever, gated by a 4h slow trend regime
            (4h EMA50 > 4h EMA200 — engages/disengages on weeks-long regime
            shifts), with vol-target sizing (4h ATR/close → scale stake to
            target ~2.5% ATR per trade). The vol-target is the v0.4.0 honesty
            mechanism: in 2022 winter ATRs balloon, so this strategy
            structurally trades smaller — letting us distinguish breakout
            edge from regime exposure cleanly. Patient SMA30 exit transfers
            v0.3.0 Finding 2 (breakouts benefit from "ride the move" exits).
Parent: root (paradigm-inspired by v0.3.0 BTCLeaderBreakX but structurally
        different: per-pair Donchian not BTC-cross-pair, 4h EMA regime not
        portfolio-diversification, vol-target sizing not equal-weight)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class VolBreakoutSized(IStrategy):
    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False

    minimal_roi = {"0": 100}
    # r13 reverts r12's stoploss=-0.10 → -0.99. r12 found stoploss had
    # near-zero aggregate effect (Sharpe 1.122→1.100, slight drag) —
    # SMA50 patient exit already cuts bad trades at ~the right point.
    # Stoploss adds no value on this configuration, small drag.
    stoploss = -0.99
    trailing_stop = False
    process_only_new_candles = True
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count: int = 250

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Per-pair Donchian-24 prior-bar high (exclude current bar to avoid
        # self-reference at break detection)
        dataframe["donchian_high_24"] = dataframe["high"].rolling(24).max().shift(1)
        # r14: SMA50→SMA75 (mirrors V4's r13 win — patient-exit trend has
        # more gas than v0.3.0's terminal SMA50 in regime-mixed data).
        dataframe["sma75"] = ta.SMA(dataframe, timeperiod=75)
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r6: revert volume threshold 1.4x → 1.3x. r5 bump cost 0.09 Sharpe
        # (1.085→0.998), the -28 filtered trades were net positive. 1.3x
        # is the local optimum — clean isolation, single-knob revert.
        dataframe.loc[
            (dataframe["close"] > dataframe["donchian_high_24"])
            & (dataframe["ema50_4h"] > dataframe["ema200_4h"])
            & (dataframe["volume"] > 1.3 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Patient ride-the-move exit (v0.3.0 Finding 2: breakouts benefit
        # from slow-SMA exits, not responsive ones)
        dataframe.loc[dataframe["close"] < dataframe["sma75"], "exit_long"] = 1
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
        # Vol-target sizing: scale stake so position-level ATR exposure
        # tracks ~2.5% per 4h bar. In low-vol bull, scale is capped at 1.0
        # (don't OVER-size when vol is unusually low). In high-vol bear,
        # ATR% balloons → smaller stake → bear-regime de-risking.
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df.empty or "atr_pct_4h" not in df.columns:
            return proposed_stake
        atr_pct = df["atr_pct_4h"].iloc[-1]
        if atr_pct != atr_pct or atr_pct <= 0:
            return proposed_stake
        vol_target = 0.025
        scale = min(1.0, vol_target / atr_pct)
        stake = proposed_stake * scale
        return max(min_stake or 0.0, min(max_stake, stake))
