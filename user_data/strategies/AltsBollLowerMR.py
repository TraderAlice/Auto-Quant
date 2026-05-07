"""
AltsBollLowerMR — Bollinger lower-band reversion on SOL+AVAX with slope-up filter

Paradigm: mean-reversion (statistical, on alts)
Hypothesis: BNBMeanRevertMulti's r6 fork experiment proved that the
            RSI<25 mechanism doesn't generalize beyond BNB (BTC/ETH/SOL
            all negative). But that was a single signal family — RSI
            extreme. Statistical MR via Bollinger lower-band excursion
            is a different signal family: it triggers when price moves
            >2σ below a 20-bar mean, which is a relative-volatility
            measure rather than a momentum-oscillator measure. SOL and
            AVAX have higher absolute volatility than BNB and therefore
            larger BB excursions; their MR opportunity space is
            distinct from BNB's RSI space. Pairing this with the slope-up
            filter that worked for CrashRebound should give a winter-safe
            MR mechanism on alts. Excludes BNB (already covered by
            BNBSizedConviction). Equal-weight sizing — the v0.4.0 r7 +
            v0.4.1 r9 cumulative findings: sizing isn't edge in itself,
            so test the pure signal first; r11+ can fork sized variant
            if signal is real.
Parent: root (paradigm-relative to BNBMeanRevertSharp but distinct
        signal family — Bollinger excursion vs RSI extreme — and
        distinct universe — SOL+AVAX vs BNB)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class AltsBollLowerMR(IStrategy):
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

    pair_basket = ["SOL/USDT", "AVAX/USDT"]

    test_timeranges = [
        ("bull_2021",   "20210101-20211231"),
        ("winter_2022", "20220101-20221231"),
        ("full_5y",     "20210101-20251231"),
    ]

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["ema200_slope_up"] = (
            dataframe["ema200"] > dataframe["ema200"].shift(7)
        ).astype(int)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        bb_period = 20
        bb_std = 2.0
        sma = dataframe["close"].rolling(bb_period).mean()
        std = dataframe["close"].rolling(bb_period).std()
        dataframe["bb_lower"] = sma - bb_std * std
        dataframe["bb_mid"] = sma
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        # r11: volume SMA20 — transfer CrashRebound r10 finding (volume
        # filter lifted CrashRebound robust_sharpe 0.003→0.062). Real
        # capitulation rebounds need volume; chop-driven BB excursions
        # don't.
        dataframe["volume_sma20"] = dataframe["volume"].rolling(20).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r12: r11 volume filter didn't transfer (winter still -0.47).
        # ADD close > 1d EMA200 as second regime gate. Double-gate:
        # slope-up (trajectory) AND price-above (instant position). The
        # bear-market rallies during winter that triggered slope-up
        # briefly DON'T satisfy close > EMA200 — that's the structural
        # tighten.
        dataframe.loc[
            (dataframe["close"] < dataframe["bb_lower"])
            & (dataframe["rsi"] < 35)
            & (dataframe["ema200_slope_up_1d"] == 1)
            & (dataframe["close"] > dataframe["ema200_1d"])
            & (dataframe["volume"] > 1.3 * dataframe["volume_sma20"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Mean reversion target: above BB midline (50% reversion).
        dataframe.loc[dataframe["close"] > dataframe["bb_mid"], "exit_long"] = 1
        return dataframe
