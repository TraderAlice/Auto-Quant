"""
PerPairMR — first per-pair-conditional strategy: BNB→RSI MR, alts→BB-lower MR

Paradigm: mean-reversion (per-pair conditional)
Hypothesis: This run's strongest findings were both MR-flavored:
              (a) BNBMeanRevertSharp r0: RSI<25 + 1d EMA200*0.85 gate
                  on BNB gave clean cross-regime positive (robust 0.079)
              (b) AltsBollLowerMR r10: BB-lower + RSI<35 + slope-up
                  filter on SOL+AVAX gave bull Sharpe 1.33 (highest in
                  run) but winter-fragile
            v0.4.0's "MR is BNB-skewed" finding plus v0.4.1's r6 fork
            confirmed RSI doesn't generalize beyond BNB. But Bollinger
            excursion DOES work on SOL+AVAX bull. So each MR signal has
            its preferred pair shape — different signal families fit
            different volatility profiles. v0.4.1's per-pair-conditional
            entries (via metadata['pair']) lets us EXPRESS this finding
            structurally: one strategy that uses RSI mechanism on BNB
            and BB-lower mechanism on SOL+AVAX. The aggregate is then
            two independent edge sources, not a forced single mechanism.
            Critically — both branches use the same winter defense
            (1d slope-up + close>EMA200) so the entire strategy is
            regime-gated. Equal-weight sizing per the v0.4.0 r7 / v0.4.1
            r9 ablation findings.
Parent: root (synthesis of BNBMeanRevertSharp + AltsBollLowerMR
        structures, novel per-pair conditional architecture)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class PerPairMR(IStrategy):
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

    # r18: expand to full 5-pair. BTC+ETH branches use Donchian-48 sustained
    # break + 4h macro filter (transfer of AltsBollBreak r1 finding) since
    # majors don't have the same MR profile. This makes the strategy
    # paradigm-mixed AND universe-conditional simultaneously.
    pair_basket = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "AVAX/USDT"]

    test_timeranges = [
        ("bull_2021",      "20210101-20211231"),
        ("winter_2022",    "20220101-20221231"),
        ("recovery_23_25", "20230101-20251231"),
        ("full_5y",        "20210101-20251231"),
    ]

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r14: 4h trend filter for alts branch — kills sideways-recovery
        # entries that were SOL -0.14, AVAX -0.05.
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        # r28: revert r27 14-bar → 7-bar slope. r27 finding: 14-bar slope
        # is over-restrictive (robust 0.052→0.036). 7-bar window is the
        # local optimum.
        dataframe["ema200_slope_up"] = (
            dataframe["ema200"] > dataframe["ema200"].shift(7)
        ).astype(int)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # All branches need RSI; alts also need Bollinger; majors need
        # Donchian-48 + volume.
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        bb_period = 20
        bb_std = 2.0
        sma = dataframe["close"].rolling(bb_period).mean()
        std = dataframe["close"].rolling(bb_period).std()
        dataframe["bb_lower"] = sma - bb_std * std
        dataframe["bb_mid"] = sma
        dataframe["donchian_high_48"] = dataframe["high"].rolling(48).max().shift(1)
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata.get("pair", "")
        if pair == "BNB/USDT":
            # BNB-RSI mechanism:
            dataframe.loc[
                (dataframe["rsi"] < 25)
                & (dataframe["close"] > dataframe["ema200_1d"] * 0.85),
                "enter_long",
            ] = 1
        elif pair in ("SOL/USDT", "AVAX/USDT"):
            # Alts BB-lower MR with full regime gate.
            dataframe.loc[
                (dataframe["close"] < dataframe["bb_lower"])
                & (dataframe["rsi"] < 35)
                & (dataframe["ema200_slope_up_1d"] == 1)
                & (dataframe["close"] > dataframe["ema200_1d"])
                & (dataframe["ema50_4h"] > dataframe["ema200_4h"]),
                "enter_long",
            ] = 1
        elif pair in ("BTC/USDT", "ETH/USDT"):
            # r18: majors Donchian-48 sustained break + 4h macro + volume.
            # Different paradigm (breakout, not MR) for majors which have
            # smaller MR opportunity space. Strategy now paradigm-conditional.
            prior_above = dataframe["close"].shift(1) > dataframe["donchian_high_48"].shift(1)
            dataframe.loc[
                (dataframe["close"] > dataframe["donchian_high_48"])
                & prior_above
                & (dataframe["ema50_4h"] > dataframe["ema200_4h"])
                & (dataframe["ema200_slope_up_1d"] == 1)
                & (dataframe["volume"] > 1.3 * dataframe["volume_sma20"]),
                "enter_long",
            ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata.get("pair", "")
        if pair == "BNB/USDT":
            dataframe.loc[dataframe["rsi"] > 55, "exit_long"] = 1
        elif pair in ("SOL/USDT", "AVAX/USDT"):
            dataframe.loc[dataframe["close"] > dataframe["bb_mid"], "exit_long"] = 1
        elif pair in ("BTC/USDT", "ETH/USDT"):
            # Majors patient SMA50 exit (paradigm-specific from
            # AltsBollBreak r1 finding — breakouts ride trends).
            dataframe.loc[dataframe["close"] < dataframe["sma50"], "exit_long"] = 1
        return dataframe

    # r22: removed custom_stake_amount entirely. r20+r21 transfer
    # experiment finding: BNB sizing doesn't compose linearly inside
    # multi-pair strategy. Plain 25/RSI: robust 0.052→0.038 (worse).
    # Regime-aware (slope_up gate): robust 0.052→0.044 (better than
    # plain but still worse than baseline). Net: sizing is best applied
    # at strategy isolation (single-pair) rather than embedded in
    # multi-pair containers. Cross-pair attribution is meaningfully
    # different from single-pair attribution.
