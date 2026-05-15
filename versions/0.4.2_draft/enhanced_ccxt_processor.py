from __future__ import annotations

import asyncio
from cmath import polar
import enum
import math
import os
import shutil
from datetime import datetime
from typing import Any, List, Literal, Tuple

import ccxt
import ccxt.async_support
import numpy as np
import polars as pl
from torch import Tensor
import torch.utils
import torch.utils.data
from tqdm.asyncio import tqdm as tqdm_as
from tqdm.notebook import tqdm as tqdm_nb
from polars.ml.torch import PolarsDataset
from gaussian_normalizer import GaussianScaler


class TimeStampUnit(enum.Enum):
    Sec1 = ("1s", 1)
    Min1 = ("1m", 60)
    Hour1 = ("1h", 60 * 60)
    Day1 = ("1d", 60 * 60 * 24)

    def suffix(self) -> str:
        return self.name[1]


class RoundRobinWorkerPool:
    def __init__(self, creator, worker: int):
        self.pool = [creator() for _ in range(worker)]
        self.workers = worker
        self.idx = 0

    def get(self) -> ccxt.async_support.Exchange:
        idx = self.idx
        self.idx = (self.idx + 1) % self.workers
        return self.pool[idx]

    async def closeall(self):
        for w in self.pool:
            await w.close()


class CCXTEngineerEnhanced:
    def __init__(
        self,
        exchanger=lambda: ccxt.async_support.binance(),
        num_worker: int = 8,
        wait_interval=10,
        max_concurrent: int = 20,
        req_per_sec: int = 10,
        shards_per_type: int = 5,
        cache_dir="datasets",
        backup=False,
        notebook=False,
    ):
        self.exchanger_creator = exchanger
        self.num_worker = num_worker
        self.wait_interval = wait_interval
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.req_interval = 1.0 / req_per_sec
        self.shards_per_type = shards_per_type
        self.tqdm_bar_idx = 0
        self.cache_dir = cache_dir
        self.download_sem = 0
        self.backup = backup
        if notebook:
            self.tqdm = tqdm_nb
        else:
            self.tqdm = tqdm_as

    async def _fetch(
        self,
        worker: ccxt.async_support.Exchange,
        ktype: str,
        pair: str,
        after: int,
        limit=None,
    ) -> List[List[Any]]:
        async with self.semaphore:
            await asyncio.sleep(self.req_interval)
            future = worker.fetch_ohlcv(
                symbol=pair, timeframe=ktype, since=after, limit=limit
            )
            return await future  # type:ignore

    def _generate_shards(
        self, start_time: datetime, end_time: datetime
    ) -> Tuple[List[Tuple[int, int]], int]:
        total_span = int((end_time - start_time).total_seconds() * 1000)
        shard_span = total_span // self.shards_per_type
        shards = [
            (
                int(start_time.timestamp() * 1000) + i * shard_span,
                min(
                    int(start_time.timestamp() * 1000) + (i + 1) * shard_span,
                    int(end_time.timestamp() * 1000),
                ),
            )
            for i in range(self.shards_per_type)
        ]
        return (shards, total_span)

    def take_tqdm_position(self) -> int:
        idx = self.tqdm_bar_idx
        self.tqdm_bar_idx += 1
        return idx

    async def _work(
        self,
        workers: RoundRobinWorkerPool,
        pair: str,
        period_ktype: TimeStampUnit,
        shard: Tuple[int, int],
        buffer,
    ):
        start_ts, end_ts = shard
        current_ts = start_ts

        with self.tqdm(
            range(end_ts - start_ts),
            desc=f"{pair}-{period_ktype.name}:{start_ts}->{end_ts}",
            position=self.take_tqdm_position(),
        ) as pbar:
            while current_ts < end_ts:
                try:
                    data = await self._fetch(
                        workers.get(),
                        ktype=period_ktype.value[0],
                        pair=pair,
                        after=current_ts,
                    )
                    if not data:
                        continue

                    valid_data = [
                        row for row in data if start_ts <= int(row[0]) <= end_ts
                    ]
                    if not valid_data:
                        break

                    lts = int(valid_data[-1][0])
                    pbar.update(lts - current_ts)
                    buffer.extend(valid_data)
                    current_ts = lts
                except Exception as e:
                    print(f"\n重试分片 {period_ktype}@{current_ts}: {str(e)}\n")
            pbar.close()
        self.download_sem -= 1

    async def recover_data_fetch(
        self,
        start: datetime,
        end: datetime,
        pair_list=["BTC/USDT"],
        periods=[TimeStampUnit.Min1],
    ):
        rec = self.retrieve_download_cache_ohlcv(periods, pair_list, savemem=True)
        remain: list[tuple[str, TimeStampUnit, datetime]] = []

        for (period, pair), df in rec.items():
            (_, secs) = period.value
            df: pl.LazyFrame = df
            last: datetime = (
                df.select(pl.col("ts").max()).collect(engine="streaming").item(0, 0)
            )
            del df
            if last is None:
                remain.append((pair, period, start))
            elif (end - last).total_seconds() >= int(secs):
                remain.append((pair, period, last))

        if len(remain) == 0:
            print("no download process need to be recover!")
            return

        data_buffers = {
            (pair, period): [[] for slice in range(self.shards_per_type)]
            for pair, period, _ in remain
        }

        raw_schema = {
            "ts": pl.Datetime("ms"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
        }
        actual_schema = {
            "ts": pl.Datetime("ms"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "pair": pl.String,
        }

        async def _auto_save(self):
            while self.download_sem > 0:
                await asyncio.sleep(60)
                await _save_all(self)

        async def _save_all(self, sort=False):
            for pair, period, _ in remain:
                path = f"{self.cache_dir}/cache/download/{period.name}"
                df = pl.DataFrame(schema=raw_schema)
                for shard in data_buffers[(pair, period)]:
                    df = df.vstack(
                        pl.DataFrame(
                            shard,
                            schema=raw_schema,
                            orient="row",
                        )
                    )
                    # check if folder exists
                    os.makedirs(path, exist_ok=True)

              [118;1:3u      file = f"{path}/{pair.replace('/', '_').lower()}_raw.parquet"
                    print(f"\n新保存{df.height}条数据到{file}\n")

                    if os.path.exists(file):
                        df = pl.concat([pl.read_parquet(file), df]).unique("ts")
                        if sort:
                            df = df.sort(by="ts")
                        df.write_parquet(file)
                    else:
                        df = df.unique("ts")
                        if sort:
                            df = df.sort("ts")
                        df.write_parquet(file)
                    shard.clear()

        tasks = []
        workers = RoundRobinWorkerPool(self.exchanger_creator, self.num_worker)
        for pair, period, begin in remain:
            shards, _ = self._generate_shards(begin, end)
            for shard_idx, shard in enumerate(shards):  # 使用enumerate获取索引
                # 获取对应的缓冲区位置
                buffer = data_buffers[(pair, period)][shard_idx]
                # 创建任务并添加到列表
                task = self._work(workers, pair, period, shard, buffer)
                tasks.append(task)
                self.download_sem += 1
        if self.backup:
            tasks.append(_auto_save(self))
        await asyncio.gather(*tasks)
        await workers.closeall()
        print("download completed!")
        await _save_all(self, sort=True)

    async def data_fetch_ohlvc(
        self,
        start: datetime,
        end: datetime,
        pair_list=["BTC/USDT"],
        periods=[TimeStampUnit.Min1],
    ) -> dict[tuple[TimeStampUnit, str], pl.LazyFrame]:
        data_buffers = {
            period: {
                pair: [[] for slice in range(self.shards_per_type)]
                for pair in pair_list
            }
            for period in periods
        }
        raw_schema = {
            "ts": pl.Datetime("ms"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
        }
        actual_schema = {
            "ts": pl.Datetime("ms"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "pair": pl.String,
        }

        async def _auto_save(self):
            while self.download_sem > 0:
                await asyncio.sleep(60)
                await _save_all(self)

        async def _save_all(self, sort=False):
            for period in periods:
                path = f"{self.cache_dir}/cache/download/{period.name}"
                for pair in pair_list:
                    pair: str = pair
                    df = pl.DataFrame(schema=raw_schema)
                    for shard in range(self.shards_per_type):
                        df = df.vstack(
                            pl.DataFrame(
                                data_buffers[period][pair][shard],
                                schema=raw_schema,
                                orient="row",
                            )
                        )
                    # check if folder exists
                    os.makedirs(path, exist_ok=True)

                    file = f"{path}/{pair.replace('/', '_').lower()}_raw.parquet"
                    print(f"\n新保存{df.height}条数据到{file}\n")

                    if os.path.exists(file):
                        df = pl.concat([pl.read_parquet(file), df]).unique("ts")
                        if sort:
                            df = df.sort(by="ts")
                        df.write_parquet(file)
                    else:
                        df = df.unique("ts")
                        if sort:
                            df = df.sort("ts")
                        df.write_parquet(file)

                    for shard in data_buffers[period][pair]:
                        shard.clear()

        tasks = []
        workers = RoundRobinWorkerPool(self.exchanger_creator, self.num_worker)
        for period in periods:
            for pair in pair_list:
                shards, _ = self._generate_shards(start, end)
                for shard_idx, shard in enumerate(shards):  # 使用enumerate获取索引
                    # 获取对应的缓冲区位置
                    buffer = data_buffers[period][pair][shard_idx]
                    # 创建任务并添加到列表
                    task = self._work(workers, pair, period, shard, buffer)
                    tasks.append(task)
                    self.download_sem += 1
        if self.backup:
            tasks.append(_auto_save(self))
        await asyncio.gather(*tasks)
        await workers.closeall()
        print("download completed!")
        await _save_all(self, sort=True)

        datasets = {
            (period, pair): pl.scan_parquet(
                f"{self.cache_dir}/cache/download/{period.name}/{pair.replace('/', '_').lower()}_raw.parquet",
                schema=actual_schema,
            )
            for period in periods
            for pair in pair_list
        }
        return datasets

    def take_pairs_with_unit_only(
        self, df_s: dict[tuple[TimeStampUnit, str], pl.LazyFrame], unit: TimeStampUnit
    ) -> dict[str, pl.LazyFrame]:
        dfs = {}
        for (period, pair), df in df_s.items():
            if period == unit:
                dfs[pair] = df
        return dfs

    def retrieve_download_cache_ohlcv(
        self,
        ts: list[TimeStampUnit],
        pairs: list[str],
        savemem=False,
        uniquelize_inplace=False,
        sort=False,
    ) -> dict[tuple[TimeStampUnit, str], pl.LazyFrame]:
        outer_schema = {
            "ts": pl.Datetime("ms"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
        }
        datasets = {}
        for period in ts:
            for pair in pairs:
                path = f"{self.cache_dir}/cache/download/{period.name}/{pair.replace('/', '_').lower()}_raw.parquet"
                df = pl.scan_parquet(
                    path,
                    schema=outer_schema,
                    low_memory=savemem,
                )
                dirty = False
                if uniquelize_inplace:
                    df = df.unique("ts")
                    dirty = True
                if sort:
                    df = df.sort("ts")
                    dirty = True
                if dirty:
                    df.collect(engine="streaming").write_parquet(path)
                    df = pl.scan_parquet(path, schema=outer_schema, low_memory=savemem)
                datasets[(period, pair)] = df

        return datasets

    def retrieve_indicated_cache_ohlcv(
        self, ts: list[TimeStampUnit], pairs: list[str], savemem=False
    ) -> dict[tuple[TimeStampUnit, str], pl.LazyFrame]:
        datasets = {
            (period, pair): pl.scan_parquet(
                f"{self.cache_dir}/cache/indicated/{period.name}/{pair.replace('/', '_').lower()}.parquet",
                low_memory=savemem,
            )
            for period in ts
            for pair in pairs
        }
        return datasets

    def add_technical_indicators_to_ohlcv_v2(
        self,
        df_s: dict[str, pl.LazyFrame],
        axises_indicators: dict[str, list[tuple[str, int, list[pl.Expr]]]],
        agg_func: dict[tuple[str, str, int], list[pl.Expr]] = {},
    ) -> list[tuple[str, str, int, pl.LazyFrame]]:
        ret = []
        for pair, mappers in axises_indicators.items():
            df_outer = df_s[pair]
            for axis_col, axis_split, indicator in mappers:
                df_inner = self.reaxis(
                    df_outer,
                    axis_col,
                    axis_split,
                    agg_func.get((pair, axis_col, axis_split), []),
                )
                ret.append(
                    (
                        pair,
                        axis_col,
                        axis_split,
                        df_inner.with_columns(indicator).fill_nan(0).drop_nulls(),
                    )
                )

        return ret

    def extract_normalizer_from_v2_dataframes(
        self, df_s: list[tuple[str, str, int, pl.LazyFrame]]
    ) -> list[tuple[str, str, int, pl.LazyFrame, GaussianScaler]]:
        return [
            (
                pair,
                axis_col,
                axis_split,
                df,
                GaussianScaler(pair, axis_col, axis_split, df),
            )
            for pair, axis_col, axis_split, df in df_s
        ]

    def retrieve_normalizer_from_v2_dataframes(
        self, df_s: list[tuple[str, str, int, pl.LazyFrame]]
    ) -> list[tuple[str, str, int, pl.LazyFrame, GaussianScaler]]:
        return [
            (
                pair,
                axis_col,
                axis_split,
                df,
                GaussianScaler(pair, axis_col, axis_split),
            )
            for pair, axis_col, axis_split, df in df_s
        ]

    def add_technical_indicators_to_ohlcv(
        self,
        df_s: dict[tuple[TimeStampUnit, str], pl.LazyFrame],
        tech_indicator_list: dict[tuple[TimeStampUnit, str], list[pl.Expr]]
        | list[pl.Expr] = [],
        extra_indicators: list[pl.Expr] = [],
        stream=False,
        use_gpu=False,
    ) -> dict[tuple[TimeStampUnit, str], pl.LazyFrame]:
        datasets = {}
        cache_path = f"{self.cache_dir}/cache/indicated"
        if tech_indicator_list is list:
            for (period, pair), df in df_s.items():
                df = (
                    df.unique("ts")
                    .sort("ts")
                    .with_columns(tech_indicator_list)
                    .with_columns(extra_indicators)
                )
                if self.backup:
                    os.makedirs(f"{cache_path}/{period.name}", exist_ok=True)
                    file_name = f"{cache_path}/{period.name}/{pair.replace('/', '_').lower()}.parquet"
                    df.collect(
                        streaming=stream, engine="gpu" if use_gpu else "cpu"
                    ).write_parquet(file_name)
                    df = pl.scan_parquet(file_name)
                datasets[(period, pair)] = df
            print("Succesfully add technical indicators")
        elif tech_indicator_list is dict:
            for (period, pair), df in df_s.items():
                df = (
                    df.unique("ts")
                    .sort("ts")
                    .with_columns(tech_indicator_list[(period, pair)])
                    .with_columns(extra_indicators)
                )
                if self.backup:
                    os.makedirs(f"{cache_path}/{period.name}", exist_ok=True)
                    file_name = f"{cache_path}/{period.name}/{pair.replace('/', '_').lower()}.parquet"
                    df.collect(
                        streaming=stream, engine="gpu" if use_gpu else "cpu"
                    ).write_parquet(file_name)
                    df = pl.scan_parquet(file_name)
                datasets[(period, pair)] = df
                print(f"Succesfully add technical indicators for ({period},{pair})")
        return datasets

    def construct_and_save_predict_dataset_v2(
        self,
        df_s: list[pl.LazyFrame],
        index_col: str = "group_id",
        rolling_window: int = 12,
        size_limit: int | None = None,
    ) -> list[PolarsDataset]:
        ds = []
        for df in df_s:
            schema = df.collect_schema()
            label_len = (
                schema.len() - 1
            )  # self predicted endo variable series, expect groupid, all is endo variable
            feature_count = label_len
            df = df.head(size_limit + rolling_window) if size_limit is not None else df
            dataset = (
                (
                    df.select(
                        [
                            pl.col(index_col),
                            ##
                            pl.concat_list(
                                pl.exclude(index_col).cast(dtype=pl.Float32)
                            ).alias("unioned_x"),
                            ##
                            pl.concat_list(pl.exclude(index_col).cast(dtype=pl.Float32))
                            .shift(-1)
                            .list.to_array(feature_count)
                            .alias("grouped_y"),
                        ]
                    )
                    .drop_nulls()
                    .filter(pl.col("unioned_x").list.len() == feature_count)
                    .rolling(index_column=index_col, period=f"{rolling_window}i")
                    .agg(
                        [
                            pl.col("unioned_x")
                            .head(rolling_window)
                            .flatten()
                            .alias("grouped_x"),
                            pl.col("grouped_y").last().alias("grouped_y"),
                        ]
                    )
                    .filter(
                        pl.col("grouped_x").list.len() == rolling_window * feature_count
                    )
                    .with_columns(
                        pl.col("grouped_x")
                        .list.to_array(rolling_window * feature_count)
                        .alias("grouped_x")
                    )
                )
                .collect(engine="streaming")
                .to_torch(
                    return_type="dataset", label="grouped_y", features="grouped_x"
                )
            )
            ds.append(dataset)
        return ds

    def construct_and_save_predict_dataset_ohlcv_v1(
        self,
        df_s: dict[tuple[TimeStampUnit, str], pl.LazyFrame],
        rolling_windows: dict[TimeStampUnit, int] = {TimeStampUnit.Sec1: 120},
        labels: list[str] = [f"ROCP_{i:03d}" for i in (1, 3, 5, 10, 20, 60, 120)],
        ts_col: str = "ts",
        take_head: int | None = None,
        offset: int = 0,
        hint: bool = False,
    ) -> dict[tuple[TimeStampUnit, str], PredictorNormalizedDatasetV1]:
        ds = {}
        for (period, pair), df in df_s.items():
            schema = df.collect_schema()
            rolling_window = rolling_windows[period]
            label_len = len(labels)
            feature_count = schema.len() - 1 - label_len  # additional -1 for ts col
            if offset != 0:
                df = df.slice(offset=offset)
            if take_head is not None:
                df = df.head(take_head + 2 * rolling_window)
            dataset = (
                df.drop_nulls()
                .select(
                    [
                        pl.col(ts_col),
                        pl.concat_list(
                            pl.exclude(
                                [
                                    *labels,
                                    "ts",
                                ]
                            ).cast(dtype=pl.Float32)
                        )
                        .list.to_array(feature_count)
                        .alias("unioned_x"),
                        pl.concat_list(pl.col(labels).cast(dtype=pl.Float32))
                        .list.to_array(label_len)
                        .alias("unioned_y"),
                    ]
                )
                .rolling(index_column=ts_col, period=f"{rolling_window}s")
                .agg(
                    [
                        pl.col("unioned_x").head(rolling_window).alias("grouped_x"),
                        pl.col("unioned_y").head(1).alias("grouped_y"),
                    ]
                )
                .slice(rolling_window)
                .select(
                    [
                        pl.col("grouped_x").list.to_array(rolling_window),
                        pl.col("grouped_y").list.to_array(1),
                    ]
                )
                .collect(engine="streaming")
            )
            if hint:
                print(dataset.head(5))
            ds[(period, pair)] = PredictorNormalizedDatasetV1(
                dataset.to_torch(
                    "dataset",
                    label="grouped_y",
                    features="grouped_x",
                )
            )
        return ds

    def drop_cache(self, nonexist_okay=True):
        shutil.rmtree(f"{self.cache_dir}/cache", ignore_errors=nonexist_okay)

    def reaxis(
        self,
        df: pl.LazyFrame,
        axis: str,
        part_range: float,
        group_agg_func: list[pl.Expr] = [],
    ) -> pl.LazyFrame:
        """
        按照指定轴重新切片金融数据

        参数:
        df: 包含OHLCV数据的DataFrame
        axis: 重新采样的轴，如"volume"
        part_key: 每个间隔的大小，如50000（表示每50000单位volume为一个间隔）
        tolerance: 严格容忍误差，表示为百分比（0-1之间）

        返回:
        按指定轴重新采样后的LazyFrame，包含切片内样本的累计信息
        """

        return (
            df.with_columns(
                # 计算累积轴值
                pl.col(axis).cum_sum().alias(f"cum_{axis}")
            )
            .with_columns(
                # 计算理想的划分点
                (pl.col(f"cum_{axis}") / part_range).floor().alias("group_id")
            )
            .group_by("group_id")
            .agg(
                [
                    # 保留第一个时间戳作为组的时间戳
                    pl.col("ts").first().alias("first_ts"),
                    pl.col("ts").last().alias("last_ts"),
                    # 保留第一个价格作为开盘价
                    pl.col("open").first().alias("open"),
                    # 记录区间内的极值
                    pl.col("high").max().alias("high"),
                    pl.col("low").min().alias("low"),
                    # 最后一个价格作为收盘价
                    pl.col("close").last().alias("close"),
                    # 计算累积成交量
                    pl.col("volume").sum().alias("volume"),
                    # 计算区间内实际累积的轴值（用于验证是否满足tolerance要求）
                    pl.col(axis).sum().alias("actual_part"),
                    *group_agg_func,
                ]
            )
            .with_columns(
                ((pl.col("actual_part") - part_range).abs() / part_range).alias(
                    "part_error"
                ),
                (pl.col("last_ts") - pl.col("first_ts")).alias("period_duration"),
            )
            .with_columns(
                [
                    pl.col("period_duration")
                    .dt.total_seconds()
                    .alias("period_duration_sec"),
                    pl.col("group_id").cast(pl.UInt64),
                ]
            )
            .drop(["actual_part"])
            .sort("group_id")
        )


class PredictorNormalizedDatasetV1(torch.utils.data.Dataset):
    def __init__(self, original_data):
        self.data = original_data  # 假设原始数据已加载为Tensor或可索引对象

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        # 假设每个样本返回 (feature, label)，feature形状为[120,40]，label形状为[1,7]
        feature, label = self.data[idx]

        # 特征归一化（逐列处理）
        mean = torch.mean(feature, dim=0, keepdim=True)  # 保持维度以支持广播
        std = torch.std(feature, dim=0, keepdim=True, unbiased=False)  # 使用总体标准差
        epsilon = 1e-8
        normalized_feature: Tensor = (feature - mean) / (std + epsilon)  # 防止除零

        # 标签二值化（保留符号并处理零值）
        processed_label = torch.sign(label)
        processed_label = torch.where(
            processed_label == 0, torch.ones_like(processed_label) * -1, processed_label
        )

        return normalized_feature.reshape(
            [1, normalized_feature.shape.numel()]
        ), processed_label
