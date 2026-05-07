"""
MajorsBTCLeader — BTC 4h Donchian-24 leader signal triggers all-pair entries

Paradigm: breakout (cross-pair leader)
Hypothesis: v0.3.0's BTCLeaderBreakX hit Sharpe 1.07 on a single bull-only
            timerange via cross-pair Donchian — BTC's 4h Donchian-24 high
            broken triggered entries on ALL pairs (BTC leadership thesis).
            v0.4.0's BTCLeaderBreakV4 reproduced this on regime-mixed
            data and got 0.79 / +170% / DD-12.8% on full timerange — but
            that result is still single-timerange. The v0.4.1 honesty
            bar requires the leader signal to clear under worst-regime
            evaluation. Hypothesis: the cross-pair leader paradigm
            survives bull and full but degrades in winter (BTC leadership
            during bear means correlated drawdowns; v0.4.0 noted "BTC-
            leader signal triggers ALL pairs simultaneously → concentrated
            portfolio DD"). Test the hypothesis by declaring 3 timeranges
            and evaluating across regimes. Per v0.4.0 r13 finding,
            patient SMA75 exit lifts regime-mixed Sharpe — using it here.
            Full 5-pair basket (the leader signal premise REQUIRES the
            full universe to express its diversifying-or-concentrating
            risk profile).
Parent: root (paradigm-relative to v0.3.0 BTCLeaderBreakX / v0.4.0
        BTCLeaderBreakV4 but with v0.4.1 multi-timerange honesty test)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class MajorsBTCLeader(IStrategy):
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

    startup_candle_count: int = 300

    # Default full whitelist — leader signal premise requires it.

    test_timeranges = [
        ("bull_2021",   "20210101-20211231"),
        ("winter_2022", "20220101-20221231"),
        ("full_5y",     "20210101-20251231"),
    ]

    @informative("4h", "BTC/USDT")
    def populate_indicators_btc_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # BTC 4h Donchian-24 prior-bar high. Excludes current bar to avoid
        # current-bar self-reference. When BTC's 4h close pierces this
        # high, all pairs in the basket get the entry trigger.
        dataframe["donchian_high_24"] = dataframe["high"].rolling(24).max().shift(1)
        return dataframe

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 4h macro filter on the trading pair itself — avoid fading a pair
        # that's mid-collapse even if BTC is breaking out.
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Patient SMA75 exit (300-bar 1h ≈ SMA75-on-4h) — v0.4.0 r13 finding
        # that regime-mixed prefers patient over fast.
        dataframe["sma75_4h_eq"] = dataframe["close"].rolling(300).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # r8: drop same-pair 4h ema filter (too restrictive — r7 only 17
        # bull trades / WR 23.5% / 76 full_5y trades; v0.4.0 reproductions
        # had hundreds). Pure BTC-leader trigger now: BTC's 4h close pierces
        # its 4h Donchian-24 prior high → all pairs in basket get entry.
        dataframe.loc[
            dataframe["close"].notna()  # keep alignment, no extra filter
            & (dataframe["close"] > dataframe["btc_usdt_donchian_high_24_4h"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["close"] < dataframe["sma75_4h_eq"], "exit_long"] = 1
        return dataframe
