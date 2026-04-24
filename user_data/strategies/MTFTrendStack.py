"""
MTFTrendStack — multi-timeframe trend-following with 1d regime + 4h trend + 1h entry

Paradigm: trend-following
Hypothesis: v0.2.0's TrendEMAStack capped at Sharpe 0.36 on 1h-only because trend
            signals on 1h crypto see too much noise. Stacking a 1d EMA200 regime
            filter (only trade when above 200d) plus a 4h EMA9>EMA21 trend
            confirmation should let the 1h entry trigger fire only inside genuine
            multi-timeframe uptrends, lifting Sharpe and tightening DD.
Parent: root (paradigm-inspired by v0.2.0's TrendEMAStack but structurally different)
Created: pending — fill in after first commit
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class MTFTrendStack(IStrategy):
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

    # 1d EMA200 needs 200 daily bars warmup ≈ 4800 hourly bars
    startup_candle_count: int = 250

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Slower 4h EMA pair (13/34 vs prior 9/21) — clearer trend signal at 4h
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=13)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=34)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_ma20"] = dataframe["atr"].rolling(20).mean()
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema9"] = ta.EMA(dataframe, timeperiod=9)
        dataframe["ema21"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["sma50"] = ta.SMA(dataframe, timeperiod=50)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] > dataframe["ema200_1d"])      # 1d bull regime
            & (dataframe["ema_fast_4h"] > dataframe["ema_slow_4h"])   # 4h trend up (13/34)
            & (dataframe["atr_4h"] > dataframe["atr_ma20_4h"])  # 4h ATR expansion (conviction)
            & (dataframe["close"] > dataframe["ema9"])         # 1h pullback closed back above
            & (dataframe["close"].shift(1) < dataframe["ema9"].shift(1)),  # event-only (dropped redundant ema9>ema21 state)
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["ema9"] < dataframe["ema21"])           # 1h trend break (responsive exit — patient exit hurts trend per r36)
            | (dataframe["close"] < dataframe["ema200_1d"]),   # regime break
            "exit_long",
        ] = 1
        return dataframe
