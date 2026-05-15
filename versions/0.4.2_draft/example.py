# pythonscript

# %% initialize
from enhanced_ccxt_processor import TimeStampUnit
from enhanced_ccxt_processor import CCXTEngineerEnhanced
from datetime import datetime
import asyncio

learn_rate = 1e-3
batch_size = 32
train_start_date = datetime(2021, 1, 1, 0, 0, 0)
train_end_date = datetime(2022, 1, 1, 0, 0, 0)
pairs = ["BTC/USDT", "ETH/USDT"]
periods = [TimeStampUnit.Min1, TimeStampUnit.Hour1, TimeStampUnit.Day1]


# %% random shit
async def gather_data():
    exchanger = CCXTEngineerEnhanced(
        notebook=True, num_worker=5, backup=True, cache_dir="datasets"
    )
    datasets = await exchanger.data_fetch_ohlvc(
        start=train_start_date,
        end=train_end_date,
        pair_list=pairs,
        periods=periods,
    )


# %%
asyncio.run(gather_data())

# %% how to use
# label data...
import polars
import polars.config
from frac_diff import frac_diff

polars.Config.set_tbl_cols(-1).set_tbl_width_chars(-1)

pairs = ["BTC/USDT"]
periods = [TimeStampUnit.Sec1]
exp_index = (periods[0], pairs[0])
exchanger = CCXTEngineerEnhanced(notebook=True, backup=True)
df = exchanger.retrieve_download_cache_ohlcv(ts=periods, pairs=pairs)[exp_index]
print(df.collect_schema())
df = exchanger.reaxis(df, axis="volume", part_range=128)
df.collect().describe()

n_endo_indicate_col_set = {
    "group_id",
    "first_ts",
    "last_ts",
    "part_error",
    "period_duration",
    "period_duration_sec",
    "open",
    "close",
    "high",
    "low",
    "volume",
}

fraced = frac_diff_cols = (
    frac_diff(
        df,
        ["open", "high", "low", "close"],
        d=[
            *[i / 10.0 for i in range(1, 15)],
        ],
    )
    .with_columns(
        [
            (pl.col(gcol) - pl.col(lcol).shift(-i)).alias(
                f"{gcol}-{lcol}_diff_tier_{i}"
            )
            for gcol in ["high", "close", "open"]
            for lcol in ["low", "open", "close"]
            if gcol != lcol
            for i in range(2, 9)
        ],
    )
    .collect()
)

fraced.describe()

# %% and more data shit...
from math import pi


to_be_cleaned_fraced_data = fraced.lazy()
to_be_cleaned_fraced_data = to_be_cleaned_fraced_data.select(
    [
        "volume",
        "part_error",
        "period_duration_sec",
        "group_id",
        pl.selectors.contains("diff"),
    ]
)
(
    mean,
    std,
) = (
    to_be_cleaned_fraced_data.mean(),
    to_be_cleaned_fraced_data.std(),
)
normalized_data = (
    to_be_cleaned_fraced_data.with_columns(
        [
            *[
                ((pl.col(col) - pl.col(col).mean()) / pl.col(col).std()).alias(col)
                for col in to_be_cleaned_fraced_data.columns
                if col
                not in ["part_error", "period_duration_sec", "volume", "group_id"]
            ],
        ]
    )
    .with_columns(
        *[
            pl.col(col).arctan() / pi + 0.5
            for col in to_be_cleaned_fraced_data.columns
            if col != "group_id"
        ],
    )
    .with_columns(
        exchange_rate=(pl.col("part_error") / (pl.col("period_duration_sec") + 1)),
        group_id=pl.col("group_id").cast(pl.Int64),
    )
    .rename(
        {
            "part_error": "part-error",
            "period_duration_sec": "period-duration-sec",
            "volume": "volume",
            "exchange_rate": "exchange-rate",
            "group_id": "group-id",
        }
    )
    .collect()
)
normalized_data.describe()

# %% figure out whether the data follows gaussian dist
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly_resampler import register_plotly_resampler

register_plotly_resampler()
draw_df = normalized_data

# features = ["open", "high", "low", "close", "volume", "exchange_rate", "duration"]
cols = draw_df.columns
features = {str(name).split("_")[0] for name in cols}

# 创建子图
fig = make_subplots(
    rows=len(features), cols=1, shared_xaxes=True, vertical_spacing=0.02
)

for i, feature in enumerate(features):
    # 获取原始数据和对应的分数阶微分列
    grouped_columns = [col for col in cols if feature in col]

    # if feature in cols:
    #     # 添加原始数据曲线
    #     fig.add_trace(
    #         go.Scattergl(
    #             x=fraced["first_ts"],
    #             y=draw_df[feature],
    #             mode="lines",
    #             name=f"Original {feature}",
    #             line=dict(color="blue"),
    #             # legendgroup=f"group_{i}",
    #             hovertext=f"{feature}",
    #         ),
    #         row=i + 1,
    #         col=1,
    #     )

    # 添加分数阶微分后的数据曲线
    for col in grouped_columns:
        fig.add_trace(
            go.Scattergl(
                x=fraced["first_ts"],
                y=draw_df[col],
                mode="lines",
                name=col,
                line=dict(dash="dot"),
                # legendgroup=f"group_{i}",
                showlegend=True,
                hovertext=f"{col}",
                # make legend has auto fit width
            ),
            row=i + 1,
            col=1,
        )

    # 设置每个子图的标题和Y轴标签
    fig.update_yaxes(title_text="Value", row=i + 1, col=1)
    fig.update_xaxes(title_text="", row=i + 1, col=1)
    fig.update_xaxes(matches="x")

# 设置整体标题和布局
fig.update_layout(
    height=2000,
    width=1400,
    title_text="Original vs Fractional Differences (Interactive View)",
    showlegend=True,
    # make legend has auto fit width
    legend=dict(
        traceorder="normal",
    ),
)

# 显示图表
fig.show()
