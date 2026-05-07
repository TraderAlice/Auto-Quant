"""
BNBSizedConviction — fork of BNBMeanRevertSharp with RSI-depth conviction sizing

Paradigm: mean-reversion (sized variant)
Hypothesis: BNBMeanRevertSharp's signal at RSI<25 is the established local
            optimum (r1 found sharp signal decay at 25-30) and produces
            consistent positive Sharpe across all 4 regimes (bull 0.35,
            winter 0.23, recovery 0.08, full 0.13). The strategy's only
            structural weakness under v0.4.1 honesty bar is profit_floor
            FAIL — per-regime profits are 3-10%, well below the 20%
            threshold. v0.4.0 r7 ablation proved sizing isn't EDGE in
            its prior form (vol-targeting on breakouts), but here we
            test a different sizing thesis: CONVICTION-SCALED stakes
            based on signal depth. Deeper RSI implies stronger MR
            opportunity → bigger stake. Stake scale = clamp(25 / max(RSI,
            5), 0.5, 2.0). At RSI=25, scale=1.0 (baseline). At RSI=20,
            scale=1.25. At RSI=15, scale=1.67. At RSI=10, scale=2.0.
            Expected effect: same trade count and WR (signal unchanged),
            bigger position on deeper-conviction entries. Should lift
            per-regime profit while preserving the Sharpe shape.
Parent: BNBMeanRevertSharp (r9 fork — identical entry/exit, only sizing
        added)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class BNBSizedConviction(IStrategy):
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

    pair_basket = ["BNB/USDT"]

    test_timeranges = [
        ("bull_2021",      "20210101-20211231"),
        ("winter_2022",    "20220101-20221231"),
        ("recovery_23_25", "20230101-20251231"),
        ("full_5y",        "20210101-20251231"),
    ]

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] < 25)
            & (dataframe["close"] > dataframe["ema200_1d"] * 0.85),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["rsi"] > 55, "exit_long"] = 1
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
        # Conviction sizing: scale stake by RSI depth. Deeper RSI → bigger
        # stake. 25/RSI gives smooth scaling, clamped to [0.5x, 2.0x].
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df.empty or "rsi" not in df.columns:
            return proposed_stake
        rsi_now = df["rsi"].iloc[-1]
        if rsi_now != rsi_now or rsi_now <= 0:
            return proposed_stake
        scale = 25.0 / max(float(rsi_now), 5.0)
        scale = max(0.5, min(2.0, scale))
        stake = proposed_stake * scale
        return max(min_stake or 0.0, min(max_stake, stake))
