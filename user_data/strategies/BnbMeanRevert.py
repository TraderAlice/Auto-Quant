"""
BnbMeanRevert — BNB-only RSI mean-reversion baseline (proven robust-positive family).

Paradigm: mean-reversion
Hypothesis: BNB/USDT 1h RSI(14) < 25 reverts toward RSI > 55 within ~10 days across
            all regimes; second leg buys shallow pullbacks (RSI < 35) only when
            price holds above the 1d SMA20 uptrend, adding recovery-regime trades
            where deep dislocations are rare while staying silent in winter.
            RSI-depth conviction sizing redistributes stake toward deeper dislocations.
Parent: root (v0.4.1 BNBMeanRevertSharp/BNBSizedConviction lineage, re-derived)
Created: round0
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class BnbMeanRevert(IStrategy):
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

    startup_candle_count: int = 500

    pair_basket = ["BNB/USDT"]

    def custom_stake_amount(
        self, pair: str, current_time, current_rate: float, proposed_stake: float,
        min_stake, max_stake: float, leverage: float, entry_tag: str, side: str,
        **kwargs,
    ) -> float:
        try:
            df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            rsi = float(df["rsi"].iloc[-1])
        except Exception:
            return proposed_stake
        # RSI-depth conviction: deeper oversold -> larger stake, clamp [0.5x, 2x]
        scale = min(2.0, max(0.5, 25.0 / max(rsi, 1.0)))
        return max(min_stake or 0.0, min(max_stake, proposed_stake * scale))

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["sma20"] = ta.SMA(dataframe, timeperiod=20)
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma20"] = ta.SMA(dataframe, timeperiod=20)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        deep = dataframe["rsi"] < 25
        shallow = (
            (dataframe["rsi"] < 30.0)
            & (dataframe["close"] > dataframe["sma20_1d"])
            & (dataframe["sma20_1d"] > dataframe["sma20_1d"].shift(24))
        )
        dataframe.loc[deep | shallow, "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[(dataframe["rsi"] > 55), "exit_long"] = 1
        return dataframe
