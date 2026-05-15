import json
import math
import os
import polars as pl
from polars_ta.wq.preprocess import cs_mad
from scipy.stats import norm


non_endo_indicate_col_set = {
    "group_id",
    "first_ts",
    "last_ts",
    "part_error",
    "period_duration",
    "open",
    "close",
    "high",
    "low",
    "volume",
}


def construct_indicator_normalizer_params_path(
    pair: str, split_col: str, split_vol: int
):
    path = f"datasets/indicators/normalizer_params"
    os.makedirs(path, exist_ok=True)
    return f"{path}/{pair.replace('/', '_').lower()}-{split_col}-{split_vol}.json"


class GaussianScaler:
    def __init__(
        self,
        pair: str,
        split_col: str,
        split_vol: int,
        state_dict: dict[str, dict[str, float]] | None | pl.LazyFrame = None,  # type:ignore
    ):
        if state_dict.__class__ is pl.LazyFrame:
            stats_df: pl.DataFrame = (
                state_dict.collect(engine="streaming")  # type:ignore
                .describe()
                .drop(["statistic", *non_endo_indicate_col_set])
            )
            state_dict = {
                "means": stats_df.row(2, named=True),
                "stds": stats_df.row(3, named=True),
            }
            del stats_df

        if state_dict.__class__ is dict:
            with open(
                construct_indicator_normalizer_params_path(pair, split_col, split_vol),
                "w",
            ) as f:
                json.dump(state_dict, f, indent=2)

        with open(
            construct_indicator_normalizer_params_path(pair, split_col, split_vol)
        ) as f:
            params = json.load(f)
        self.mean_map: dict[str, float] = params["means"]
        self.std_map: dict[str, float] = params["stds"]

    def __create_expr(self, col: str) -> pl.Expr:
        """生成包含CDF转换的表达式链"""
        return cs_mad(  # celling掉奇异值
            (pl.col(col) - self.mean_map[col]) / self.std_map[col]
        ).map_batches(
            norm.cdf,
            return_dtype=pl.Float32,
        )

    def process_stream(self, preserve: bool = False) -> list[pl.Expr]:
        # 生成所有列的表达式
        return [
            self.__create_expr(col).alias(f"{col}_normalized" if preserve else f"{col}")
            for col in self.mean_map.keys()
        ]

    def apply_to_df(
        self, df: pl.DataFrame | pl.LazyFrame, preserve: bool = False
    ) -> pl.DataFrame | pl.LazyFrame:
        return df.with_columns(self.process_stream())
