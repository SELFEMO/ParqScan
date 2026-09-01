from __future__ import annotations

import os
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

import pyarrow as pa
import pyarrow.parquet as pq

from parqscan.constants import PAGE_READ_BATCH_ROWS
from parqscan.utils.binary import binary_leaf_paths, contains_binary_type

ProgressCallback = Callable[[int, int], None]
CancelCallback = Callable[[], bool]


@dataclass(frozen=True)
class ColumnMetadata:
    name: str
    logical_type: str
    physical_type: str
    nullable: bool
    compressed_size: int
    uncompressed_size: int
    binary_compressed_size: int
    storage_ratio: float
    compression: str
    is_binary: bool


@dataclass(frozen=True)
class ColumnStatistics:
    name: str
    min_value: str
    max_value: str
    null_count: str
    distinct_count: str


@dataclass(frozen=True)
class RowGroupMetadata:
    index: int
    row_count: int
    total_byte_size: int
    columns: tuple[ColumnStatistics, ...]


class ParquetDocument:
    def __init__(self, path: str) -> None:
        self.path = str(Path(path).expanduser().resolve())
        self.file = pq.ParquetFile(self.path)
        self.metadata = self.file.metadata
        self.schema = self.file.schema_arrow
        self.total_rows = self.metadata.num_rows
        self.total_columns = len(self.schema)
        self.file_size = os.path.getsize(self.path)
        self._row_group_offsets = self._build_row_group_offsets()
        self._column_metadata_cache: tuple[ColumnMetadata, ...] | None = None
        self._binary_leaf_paths = {
            field.name: binary_leaf_paths(field.type, (field.name,))
            for field in self.schema
        }

    @property
    def display_name(self) -> str:
        return Path(self.path).name

    def close(self) -> None:
        file = getattr(self, "file", None)
        if file is None:
            return
        closer = getattr(file, "close", None)
        if callable(closer):
            closer()
        self.file = None

    def _build_row_group_offsets(self) -> tuple[int, ...]:
        offsets: list[int] = []
        running = 0
        for group_index in range(self.metadata.num_row_groups):
            offsets.append(running)
            running += self.metadata.row_group(group_index).num_rows
        return tuple(offsets)

    def selected_schema(self, columns: list[str] | None = None) -> pa.Schema:
        if columns is None:
            return self.schema
        return pa.schema([self.schema.field(name) for name in columns])

    def _overlapping_groups(self, start_row: int, end_row: int) -> list[tuple[int, int, int]]:
        result: list[tuple[int, int, int]] = []
        for group_index, group_start in enumerate(self._row_group_offsets):
            group_rows = self.metadata.row_group(group_index).num_rows
            group_end = group_start + group_rows
            if group_end <= start_row:
                continue
            if group_start >= end_row:
                break
            result.append((group_index, group_start, group_rows))
        return result

    def read_rows(
        self,
        start_row: int,
        row_count: int,
        columns: list[str] | None = None,
        progress: ProgressCallback | None = None,
        is_cancelled: CancelCallback | None = None,
    ) -> pa.Table:
        """Read one logical page and report real row-group scan progress."""
        selected_schema = self.selected_schema(columns)
        if row_count <= 0 or start_row >= self.total_rows:
            if progress:
                progress(1, 1)
            return pa.Table.from_batches([], schema=selected_schema)

        start_row = max(0, start_row)
        end_row = min(self.total_rows, start_row + row_count)
        groups = self._overlapping_groups(start_row, end_row)
        total_work = max(
            1,
            sum(min(end_row, group_start + group_rows) - group_start for _, group_start, group_rows in groups),
        )
        completed_work = 0
        batches: list[pa.RecordBatch] = []
        if progress:
            progress(0, total_work)

        # 中文：分页是用户可理解的固定边界，但 Parquet 物理读取仍按行组进行；进度按实际扫描行组推进，避免进度条假装瞬间完成。
        # English: Pagination provides a clear logical boundary while Parquet still reads by row group; progress follows actual row-group scanning instead of pretending to finish instantly.
        for group_index, group_start, group_rows in groups:
            if is_cancelled and is_cancelled():
                break
            group_end = group_start + group_rows
            local_start = max(start_row, group_start) - group_start
            local_end = min(end_row, group_end) - group_start
            local_cursor = 0
            batch_size = min(max(PAGE_READ_BATCH_ROWS, row_count), max(group_rows, 1))
            for batch in self.file.iter_batches(
                batch_size=batch_size,
                row_groups=[group_index],
                columns=columns,
                use_threads=True,
            ):
                if is_cancelled and is_cancelled():
                    break
                batch_end = local_cursor + batch.num_rows
                slice_start = max(0, local_start - local_cursor)
                slice_end = min(batch.num_rows, local_end - local_cursor)
                if slice_end > slice_start:
                    batches.append(batch.slice(slice_start, slice_end - slice_start))
                local_cursor = batch_end
                completed_work += batch.num_rows
                if progress:
                    progress(min(completed_work, total_work), total_work)
                if local_cursor >= local_end:
                    break

        if is_cancelled and is_cancelled():
            return pa.Table.from_batches([], schema=selected_schema)
        if progress:
            progress(total_work, total_work)
        if not batches:
            return pa.Table.from_batches([], schema=selected_schema)
        return pa.Table.from_batches(batches, schema=selected_schema)

    def read_row_indices(
        self,
        source_rows: list[int],
        columns: list[str] | None = None,
        progress: ProgressCallback | None = None,
        is_cancelled: CancelCallback | None = None,
    ) -> pa.Table:
        """Read arbitrary source rows while preserving the caller's requested order."""
        selected_schema = self.selected_schema(columns)
        valid_rows = [row for row in source_rows if 0 <= row < self.total_rows]
        if not valid_rows:
            if progress:
                progress(1, 1)
            return pa.Table.from_batches([], schema=selected_schema)

        requests_by_group: dict[int, list[tuple[int, int]]] = {}
        for requested_position, source_row in enumerate(valid_rows):
            group_index = max(0, bisect_right(self._row_group_offsets, source_row) - 1)
            local_row = source_row - self._row_group_offsets[group_index]
            requests_by_group.setdefault(group_index, []).append((requested_position, local_row))

        selected_batches: list[pa.RecordBatch] = []
        requested_positions: list[int] = []
        completed = 0
        total = len(valid_rows)
        if progress:
            progress(0, total)

        # 中文：全文件排序后的页面通常由分散行组成；按行组一次扫描并在批次内抽取目标行，可避免为每一行重复解码同一个行组。
        # English: A globally sorted page usually contains scattered rows; scanning each row group once and taking target rows inside batches avoids decoding the same row group for every row.
        for group_index, requests in sorted(requests_by_group.items()):
            if is_cancelled and is_cancelled():
                break
            pending = sorted(requests, key=lambda item: item[1])
            request_cursor = 0
            batch_start = 0
            for batch in self.file.iter_batches(
                batch_size=max(PAGE_READ_BATCH_ROWS, 4096),
                row_groups=[group_index],
                columns=columns,
                use_threads=True,
            ):
                if is_cancelled and is_cancelled():
                    break
                batch_end = batch_start + batch.num_rows
                local_indices: list[int] = []
                positions: list[int] = []
                while request_cursor < len(pending) and pending[request_cursor][1] < batch_end:
                    requested_position, local_row = pending[request_cursor]
                    if local_row >= batch_start:
                        local_indices.append(local_row - batch_start)
                        positions.append(requested_position)
                    request_cursor += 1
                if local_indices:
                    selected_batches.append(batch.take(pa.array(local_indices, type=pa.int64())))
                    requested_positions.extend(positions)
                    completed += len(local_indices)
                    if progress:
                        progress(completed, total)
                batch_start = batch_end
                if request_cursor >= len(pending):
                    break

        if is_cancelled and is_cancelled():
            return pa.Table.from_batches([], schema=selected_schema)
        if not selected_batches:
            return pa.Table.from_batches([], schema=selected_schema)

        table = pa.Table.from_batches(selected_batches, schema=selected_schema)
        restore_order = sorted(range(len(requested_positions)), key=requested_positions.__getitem__)
        if progress:
            progress(total, total)
        return table.take(pa.array(restore_order, type=pa.int64()))

    def iter_batches_from(
        self,
        start_row: int,
        batch_size: int,
        columns: list[str] | None = None,
    ) -> Iterator[pa.RecordBatch]:
        parquet_file = self.file
        if parquet_file is None:
            return
        start_row = max(0, start_row)
        for group_index, group_start in enumerate(self._row_group_offsets):
            group_rows = self.metadata.row_group(group_index).num_rows
            group_end = group_start + group_rows
            if group_end <= start_row:
                continue
            local_start = max(0, start_row - group_start)
            local_cursor = 0
            for batch in parquet_file.iter_batches(
                batch_size=batch_size,
                row_groups=[group_index],
                columns=columns,
                use_threads=True,
            ):
                batch_end = local_cursor + batch.num_rows
                if batch_end <= local_start:
                    local_cursor = batch_end
                    continue
                if local_cursor < local_start:
                    batch = batch.slice(local_start - local_cursor)
                local_cursor = batch_end
                if batch.num_rows:
                    yield batch

    @staticmethod
    def _normalized_path(path: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        ignored = {"list", "key_value"}
        return tuple(part for part in path if part not in ignored)

    def _physical_path_is_binary(self, root_name: str, physical_path: str) -> bool:
        physical = self._normalized_path(tuple(physical_path.split(".")))
        for logical_path in self._binary_leaf_paths.get(root_name, ()):
            logical = self._normalized_path(logical_path)
            if physical == logical or physical[-len(logical) :] == logical:
                return True
        return False

    def column_metadata(self) -> list[ColumnMetadata]:
        if self._column_metadata_cache is not None:
            return list(self._column_metadata_cache)
        aggregates = {
            field.name: {
                "compressed": 0,
                "uncompressed": 0,
                "binary_compressed": 0,
                "physical": set(),
                "compression": set(),
            }
            for field in self.schema
        }
        for group_index in range(self.metadata.num_row_groups):
            row_group = self.metadata.row_group(group_index)
            for column_index in range(row_group.num_columns):
                column = row_group.column(column_index)
                physical_path = str(column.path_in_schema)
                root_name = physical_path.split(".", 1)[0]
                aggregate = aggregates.get(root_name)
                if aggregate is None:
                    continue
                compressed = int(column.total_compressed_size or 0)
                aggregate["compressed"] += compressed
                aggregate["uncompressed"] += int(column.total_uncompressed_size or 0)
                if self._physical_path_is_binary(root_name, physical_path):
                    aggregate["binary_compressed"] += compressed
                aggregate["physical"].add(str(column.physical_type))
                aggregate["compression"].add(str(column.compression))

        result: list[ColumnMetadata] = []
        for field in self.schema:
            aggregate = aggregates[field.name]
            compressed = int(aggregate["compressed"])
            result.append(
                ColumnMetadata(
                    name=field.name,
                    logical_type=str(field.type),
                    physical_type=", ".join(sorted(aggregate["physical"])) or "UNKNOWN",
                    nullable=field.nullable,
                    compressed_size=compressed,
                    uncompressed_size=int(aggregate["uncompressed"]),
                    binary_compressed_size=int(aggregate["binary_compressed"]),
                    storage_ratio=(compressed / self.file_size) if self.file_size else 0.0,
                    compression=", ".join(sorted(aggregate["compression"])) or "UNCOMPRESSED",
                    is_binary=contains_binary_type(field.type),
                )
            )
        self._column_metadata_cache = tuple(result)
        return list(self._column_metadata_cache)

    def compression_algorithms(self) -> list[str]:
        algorithms: set[str] = set()
        for column in self.column_metadata():
            algorithms.update(item.strip() for item in column.compression.split(",") if item.strip())
        return sorted(algorithms)

    def binary_compressed_size(self) -> int:
        return sum(column.binary_compressed_size for column in self.column_metadata())

    def row_group_metadata_at(self, group_index: int) -> RowGroupMetadata:
        row_group = self.metadata.row_group(group_index)
        columns: list[ColumnStatistics] = []
        for column_index in range(row_group.num_columns):
            column = row_group.column(column_index)
            statistics = column.statistics
            if statistics is None:
                minimum = maximum = null_count = distinct_count = "N/A"
            else:
                minimum = self._safe_stat_value(getattr(statistics, "min", None))
                maximum = self._safe_stat_value(getattr(statistics, "max", None))
                null_count = self._safe_stat_value(getattr(statistics, "null_count", None))
                distinct_count = self._safe_stat_value(getattr(statistics, "distinct_count", None))
            columns.append(
                ColumnStatistics(
                    name=str(column.path_in_schema),
                    min_value=minimum,
                    max_value=maximum,
                    null_count=null_count,
                    distinct_count=distinct_count,
                )
            )
        return RowGroupMetadata(
            index=group_index,
            row_count=row_group.num_rows,
            total_byte_size=row_group.total_byte_size,
            columns=tuple(columns),
        )

    @staticmethod
    def _safe_stat_value(value: Any) -> str:
        if value is None:
            return "N/A"
        if isinstance(value, bytes):
            preview = value[:32].hex(" ").upper()
            return preview + (" …" if len(value) > 32 else "")
        return str(value)
