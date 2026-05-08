"""
CrashRebound — buy alts after a -25% drawdown from rolling 30d high

Paradigm: other (counter-trend / drawdown-rebound)
Hypothesis: AltsBollBreak's r0-r4 trajectory established that breakout
            paradigms on alts have structural winter fragility — every
            defense (1d position filter, stoploss, slope filter) cut bull
            profit while only partially silencing winter. The opposite
            structural exposure is interesting: a counter-trend strategy
            that ENTERS on drawdowns. Crashes happen in every regime
            (bull pullbacks, winter capitulations, recovery shakeouts);
            the rebound size varies but the directional edge is generally
            positive on liquid majors. Trigger: 1h close < 30d-rolling-max
            × 0.75 (i.e., 25% off 30-day peak) AND 1h RSI(14) < 35
            (oversold confirmation — don't catch knives mid-fall, wait
            for a stretch). Exit: 1h close > 1h SMA50 (mean-reversion
            target, halfway-back-to-prior-trend). Universe: alts only
            (SOL, AVAX, BNB) — alts have larger drawdowns than majors,
            and the v0.4.0 surfacing was that BTC/ETH have less
            mean-reverting structure. test_timeranges spans bull/winter/
            recovery/full to make the cross-regime claim falsifiable.
            Equal-weight sizing.
Parent: root (replaces AltsBollBreak which was killed at r5 after 5
        rounds of failed winter defenses)
Created: pending — fill in after first commit
Status: active
Uses MTF: no (1h-only on entry/exit; 30d max needs 720 bars warmup)
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class CrashRebound(IStrategy):
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

    # 30d at 1h = 720 bars warmup
    startup_candle_count: int = 760

    # r19: revert r18 expansion. r18 finding: full-5pair lifted full_5y
    # Sharpe 0.29→0.40 and bull 0.85→1.07 / recovery 0.19→0.33, BUT
    # winter regressed 0.085→0.013 (BTC/ETH winter drawdown-bounces are
    # weaker than alts'). Net robust 0.085→0.013 — a clean Pareto move
    # where best-case lifted but worst-case dropped. Drawdown-rebound
    # paradigm DOES generalize to majors in directional regimes but
    # NOT under v0.4.1 robust-sharpe honesty bar. Reverting to 3-pair
    # alts+BNB basket which holds robust 0.085.
    pair_basket = ["SOL/USDT", "AVAX/USDT", "BNB/USDT"]

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
        # 30-day rolling high (720 1h bars). Drawdown trigger uses prior bar
        # to avoid current-bar self-reference.
        dataframe["high_30d"] = dataframe["high"].rolling(720).max().shift(1)
        dataframe["drawdown_pct"] = (
            dataframe["close"] / dataframe["high_30d"] - 1.0
        )
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        # r15: revert r14 SMA100 → SMA50. Patient exit BACKFIRED on this
        # paradigm — drawdown-rebounds revert quickly; letting the bounce
        # ride past SMA50 to SMA100 turns winners into losers. v0.4.0 r13
        # patient-exit finding is paradigm-specific to BREAKOUTS, not
        # counter-trend MR. Cross-version finding.
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r24: revert r23 multi-bar DD confirmation. r23 finding: 3-bar
        # sustained-DD drops the inflection-point entries (bounces start
        # WITHIN the 3-bar window) — robust 0.085→0.0095. Single-bar
        # DD<-20% trigger IS the local optimum; capitulation signals
        # don't need post-confirmation when paired with RSI<35 already.
        dataframe.loc[
            (dataframe["drawdown_pct"] < -0.20)
            & (dataframe["rsi"] < 35)
            & (dataframe["ema200_slope_up_1d"] == 1)
            & (dataframe["volume"] > 1.3 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r15: revert r14 SMA100 → SMA50.
        dataframe.loc[dataframe["close"] > dataframe["sma50"], "exit_long"] = 1
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
        # r28: COMPOSE DD-conviction × regime-detection sizing (transfer
        # from RegimeAdaptiveBNB r26 finding that composition works
        # multiplicatively without degrading either mechanism). Regime
        # uses the same indicators as RegimeAdaptive: 1d slope_up +
        # close vs EMA200 with 1.10/0.90 thresholds.
        # bull regime → 1.5x boost; winter → 0.5x cut; neutral → 1.0
        # composed × DD-conviction (abs(dd)/0.20 clamped 0.5-2.0)
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df.empty or "drawdown_pct" not in df.columns:
            return proposed_stake
        dd = df["drawdown_pct"].iloc[-1]
        if dd != dd or dd >= 0:
            return proposed_stake
        dd_scale = abs(float(dd)) / 0.20
        dd_scale = max(0.5, min(2.0, dd_scale))

        # Regime detection inline (CrashRebound doesn't store a `regime`
        # column; compute on the fly from existing 1d EMA200 + slope_up).
        if "ema200_slope_up_1d" in df.columns and "ema200_1d" in df.columns:
            slope_up = df["ema200_slope_up_1d"].iloc[-1]
            close_now = df["close"].iloc[-1]
            ema200_1d_now = df["ema200_1d"].iloc[-1]
            if (
                slope_up == 1
                and close_now == close_now
                and ema200_1d_now == ema200_1d_now
                and close_now > ema200_1d_now * 1.10
            ):
                regime_scale = 1.5
            elif (
                slope_up == 0
                and close_now == close_now
                and ema200_1d_now == ema200_1d_now
                and close_now < ema200_1d_now * 0.90
            ):
                regime_scale = 0.5
            else:
                regime_scale = 1.0
        else:
            regime_scale = 1.0

        scale = dd_scale * regime_scale
        scale = max(0.25, min(3.0, scale))
        stake = proposed_stake * scale
        return max(min_stake or 0.0, min(max_stake, stake))
