"""
RegimeAdaptiveBNB — BNB MR with regime-DETECTED stake scaling

Paradigm: mean-reversion (regime-conditional sizing)
Hypothesis: BNBSizedConviction r9 proved RSI-depth conviction sizing
            lifted robust marginally (0.079→0.098). r20-r21 fork
            experiments showed BNB sizing doesn't compose linearly
            inside multi-pair containers. The remaining sizing question
            is structural: does REGIME-CONDITIONAL sizing (large in
            favorable regimes, small in unfavorable) outperform
            SIGNAL-CONDITIONAL sizing (large at deep RSI)? v0.4.0 r7
            ablation found vol-target sizing was risk-control not edge,
            but it never tested regime-detected sizing — it relied on
            ATR (proxy for vol) which inversely correlates with regime
            but isn't regime-direct.
            This strategy uses 1d EMA200 slope+magnitude to classify
            regime in real-time (no peek-ahead): bull (slope_up AND
            close > EMA200*1.10), winter (slope_down AND close <
            EMA200*0.90), neutral (everything else). Then scales stake:
            - bull: 1.5x (lean into favorable regime)
            - neutral: 1.0x (baseline)
            - winter: 0.5x (de-risk)
            Same RSI<25 entry as BNBSized. Tests: does regime-detected
            sizing lift robust > BNBSized's 0.098?
Parent: root (regime-detection-conditional-sizing variant of BNB MR;
        distinct from BNBSized's RSI-depth-conditional sizing)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class RegimeAdaptiveBNB(IStrategy):
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
        dataframe["ema200_slope_up"] = (
            dataframe["ema200"] > dataframe["ema200"].shift(7)
        ).astype(int)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        # Regime classification: 2 (bull) | 1 (neutral) | 0 (winter)
        is_bull = (
            (dataframe["ema200_slope_up_1d"] == 1)
            & (dataframe["close"] > dataframe["ema200_1d"] * 1.10)
        )
        is_winter = (
            (dataframe["ema200_slope_up_1d"] == 0)
            & (dataframe["close"] < dataframe["ema200_1d"] * 0.90)
        )
        dataframe["regime"] = 1
        dataframe.loc[is_bull, "regime"] = 2
        dataframe.loc[is_winter, "regime"] = 0
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Same RSI<25 entry as BNBSized (proven local optimum).
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
        # Regime-detected sizing: bull 1.5x / neutral 1.0x / winter 0.5x.
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df.empty or "regime" not in df.columns:
            return proposed_stake
        regime = df["regime"].iloc[-1]
        if regime != regime:
            return proposed_stake
        if regime == 2:
            scale = 1.5
        elif regime == 0:
            scale = 0.5
        else:
            scale = 1.0
        stake = proposed_stake * scale
        return max(min_stake or 0.0, min(max_stake, stake))
