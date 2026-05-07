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
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r6: ADD 1d EMA200 slope-up filter (winter defense). r5 baseline
        # had bull 0.82/+31% but winter -0.84/-21.8% on 145 trades — winter
        # bounces too small to outpace continuation drops. Slope-up gates
        # entries to regimes where the 1d trend is structurally improving;
        # should silence most of 2022 winter while preserving the bull/
        # recovery edge.
        dataframe.loc[
            (dataframe["drawdown_pct"] < -0.25)
            & (dataframe["rsi"] < 35)
            & (dataframe["ema200_slope_up_1d"] == 1),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Mean-reversion target: above 1h SMA50 = halfway back to prior trend.
        dataframe.loc[dataframe["close"] > dataframe["sma50"], "exit_long"] = 1
        return dataframe
