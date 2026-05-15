import polars as pl
from typing import List, Union


def get_weights_ffd(d: float, threshold: float) -> List[float]:
    """
    计算分数差分的权重系数(出处为AFML)

    Args:
        d: 差分阶数
        threshold: 权重阈值，当权重小于此值时停止计算

    Returns:
        权重列表
    """
    w = [1.0]
    k = 1.0
    while True:
        w_ = -w[-1] / k * (d - k + 1.0)
        if abs(w_) < threshold:
            break
        w.append(w_)
        k += 1.0
    return list(reversed(w))


def frac_diff(series: pl.Series, d: float, threshold: float = 1e-5) -> pl.Series:
    """
    对时间序列进行分数差分，使用polars原生功能

    Args:
        series: 输入的时间序列
        d: 差分阶数
        threshold: 权重阈值，当权重小于此值时停止计算

    Returns:
        分数差分后的时间序列
    """
    # 获取权重
    weights = get_weights_ffd(d, threshold)
    n_weights = len(weights)

    # 创建临时DataFrame用于计算
    df = pl.DataFrame({series.name: series})

    # 使用shift和表达式计算分数差分
    expr_list = []
    for i, w in enumerate(weights):
        expr_list.append(pl.col(series.name).shift(i) * w)

    result_df = df.with_columns(pl.sum_horizontal(expr_list).alias(f"frac_diff_{d}"))

    # 前n_weights-1个值设为null
    result_df = result_df.with_columns(
        pl.col(f"frac_diff_{d}").fill_null(None).alias(f"frac_diff_{d}")
    )

    return result_df[f"frac_diff_{d}"]


def frac_diff_expr(
    expr: pl.Expr, d: float, threshold: float = 1e-5, name: str = None
) -> pl.Expr:
    """
    创建分数差分的表达式，用于LazyFrame计算

    Args:
        expr: 输入列的表达式
        d: 差分阶数
        threshold: 权重阈值，当权重小于此值时停止计算
        name: 列名，用于生成结果列名

    Returns:
        分数差分表达式
    """
    # 获取权重
    weights = get_weights_ffd(d, threshold)

    # 使用shift和表达式创建分数差分表达式
    expr_list = []
    for i, w in enumerate(weights):
        expr_list.append(expr.shift(i) * w)

    # 生成结果列名
    result_name = f"frac_diff_{d}"
    if name:
        result_name = f"frac_diff_{d}_{name}"

    return pl.sum_horizontal(expr_list).alias(result_name)


def frac_diff_exprs(cols: List[str], d: float, threshold: float = 1e-5) -> pl.Expr:
    """
    创建分数差分的表达式，用于LazyFrame计算

    Args:
        expr: 输入列的表达式
        d: 差分阶数
        threshold: 权重阈值，当权重小于此值时停止计算
        name: 列名，用于生成结果列名

    Returns:
        分数差分表达式
    """
    # 获取权重
    weights = get_weights_ffd(d, threshold)
    return (
        pl.col(cols)
        .rolling_sum(window_size=len(weights), weights=weights)
        .name.suffix(f"_frac_diff_{d}")
    )

    # # 使用shift和表达式创建分数差分表达式
    # expr_list = []
    # for i, w in enumerate(weights):
    #     expr_list.append(expr.shift(i) * w)

    # # 生成结果列名
    # result_name = f"frac_diff_{d}"
    # if name:
    #     result_name = f"frac_diff_{d}_{name}"

    # return pl.sum_horizontal(expr_list).alias(result_name)


def frac_diff_df(
    df: Union[pl.DataFrame, pl.LazyFrame],
    columns: List[str],
    d: list[float],
    threshold: float = 1e-5,
) -> pl.LazyFrame:
    """
    对DataFrame或LazyFrame中的多个列进行分数差分

    Args:
        df: 输入的DataFrame或LazyFrame
        columns: 需要进行分数差分的列名列表
        d: 差分阶数
        threshold: 权重阈值，当权重小于此值时停止计算

    Returns:
        包含原始列和分数差分列的DataFrame或LazyFrame
    """
    # 检查输入是DataFrame还是LazyFrame
    is_lazy = isinstance(df, pl.LazyFrame)

    # 如果是DataFrame，转换为LazyFrame进行处理
    if not is_lazy:
        lf = df.lazy()
    else:
        lf = df

    # 创建所有分数差分列的表达式
    expr_list = [frac_diff_exprs(cols=columns, d=dv, threshold=threshold) for dv in d]

    # 一次性添加所有列，提高性能
    lf = lf.with_columns(expr_list)

    # 根据输入类型返回相应的结果
    return lf
