"""
AltBbMeanRevert — alts Bollinger-lower mean-reversion with 4h trend gate.

Paradigm: mean-reversion (band-touch)
Hypothesis: SOL/AVAX/BNB touches of the 1h BB(20,2) lower band that also hold
            RSI(14) < 40 AND sit above the 4h EMA50 > EMA200 uptrend revert to
            the basis within days; the 4h gate (v0.4.1 gold filter) silences
            entries in structural downtrends where band-touches cascade. Tight
            RSI > 55 exit suits counter-trend family. RSI-depth conviction sizing
            (30/RSI in [0.5,2]) redistributes stake toward deeper dislocations.
Parent: AltsCrashRebound (slot replacement; signal paradigm swap DD-trigger -> BB-touch + trend gate)
Created: round1
Status: active
Uses MTF: yes
"""

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy, informative


class AltBbMeanRevert(IStrategy):
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

    startup_candle_count: int = 900

    pair_basket = ["SOL/USDT", "AVAX/USDT", "BNB/USDT"]

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
        scale = min(2.0, max(0.5, 30.0 / max(rsi, 1.0)))
        return max(min_stake or 0.0, min(max_stake, proposed_stake * scale))

    @informative("4h")
    def populate_indicators_4h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        return dataframe

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma20"] = ta.SMA(dataframe, timeperiod=20)
        return dataframe



    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe["bb_lower"] = bb["lowerband"]
        dataframe["bb_mid"] = bb["middleband"]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] < dataframe["bb_lower"])
            & (dataframe["rsi"] < 30.0)
            & (dataframe["ema50_4h"] > dataframe["ema200_4h"])
            & (dataframe["close"] > dataframe["sma20_1d"]),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] > 55.0) | (dataframe["close"] > dataframe["bb_mid"]),
            "exit_long",
        ] = 1
        return dataframe
