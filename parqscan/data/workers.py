from __future__ import annotations

from pathlib import Path

import pyarrow as pa
from PySide6.QtCore import QObject, Signal, Slot

from parqscan.constants import EXPORT_BATCH_ROWS
from parqscan.data.export_service import EXPORT_HANDLERS, export_parquet_fragment
from parqscan.data.parquet_document import ParquetDocument
from parqscan.utils.binary import (
    contains_binary_type,
    embedded_binary_payload,
    embedded_file_name_hint,
    embedded_image_payload,
)
from parqscan.utils.search import searchable_text
from parqscan.utils.serialization import display_text


class CancellableWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._cancelled = False

    @Slot()
    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled


class ExportWorker(CancellableWorker):
    def __init__(self, document: ParquetDocument, target: str, export_kind: str) -> None:
        super().__init__()
        self.document = document
        self.target = target
        self.export_kind = export_kind

    @Slot()
    def run(self) -> None:
        try:
            EXPORT_HANDLERS[self.export_kind](self.document, self.target, self.progress.emit, self.is_cancelled)
            self.finished.emit(self.target if not self.is_cancelled() else None)
        except Exception as error:
            self.failed.emit(str(error))


class FragmentExportWorker(CancellableWorker):
    def __init__(
        self,
        document: ParquetDocument,
        target: str,
        start_row: int,
        end_row: int,
        columns: list[str],
    ) -> None:
        super().__init__()
        self.document = document
        self.target = target
        self.start_row = start_row
        self.end_row = end_row
        self.columns = columns

    @Slot()
    def run(self) -> None:
        try:
            export_parquet_fragment(
                self.document,
                self.target,
                self.start_row,
                self.end_row,
                self.columns,
                self.progress.emit,
                self.is_cancelled,
            )
            self.finished.emit(self.target if not self.is_cancelled() else None)
        except Exception as error:
            self.failed.emit(str(error))


class ImageExtractWorker(CancellableWorker):
    def __init__(self, document: ParquetDocument, column_name: str, target_directory: str) -> None:
        super().__init__()
        self.document = document
        self.column_name = column_name
        self.target_directory = target_directory

    @Slot()
    def run(self) -> None:
        exported = 0
        processed = 0
        try:
            target = Path(self.target_directory)
            target.mkdir(parents=True, exist_ok=True)
            for batch in self.document.iter_batches_from(0, EXPORT_BATCH_ROWS, columns=[self.column_name]):
                if self.is_cancelled():
                    break
                for value in batch.column(0):
                    if self.is_cancelled():
                        break
                    raw_value = value.as_py() if hasattr(value, "as_py") else value
                    image = embedded_image_payload(raw_value)
                    if image is not None:
                        row_number = processed + 1
                        name_hint = embedded_file_name_hint(raw_value)
                        output = target / (name_hint or f"row_{row_number}.{image.image_format.extension}")
                        if not output.suffix:
                            output = output.with_suffix(f".{image.image_format.extension}")
                        if output.exists():
                            output = target / f"row_{row_number}_{output.name}"
                        output.write_bytes(image.data)
                        exported += 1
                    processed += 1
                self.progress.emit(processed, self.document.total_rows)
            self.finished.emit(exported)
        except Exception as error:
            self.failed.emit(str(error))


class GlobalSearchWorker(CancellableWorker):
    def __init__(self, document: ParquetDocument, query: str) -> None:
        super().__init__()
        self.document = document
        self.query = query.strip().casefold()

    @Slot()
    def run(self) -> None:
        matches: list[tuple[int, int]] = []
        processed = 0
        try:
            if not self.query:
                self.finished.emit(matches)
                return
            # 中文：搜索按批次扫描整个文件并只保存坐标，避免为了全局搜索把完整 Parquet 数据常驻内存。
            # English: Search scans the whole file in batches and retains only coordinates, avoiding a full in-memory copy of the Parquet data.
            for batch in self.document.iter_batches_from(0, EXPORT_BATCH_ROWS):
                if self.is_cancelled():
                    break
                for local_row in range(batch.num_rows):
                    if self.is_cancelled():
                        break
                    source_row = processed + local_row
                    for column in range(batch.num_columns):
                        value = batch.column(column)[local_row].as_py()
                        field_type = self.document.schema.field(column).type
                        if self.query in searchable_text(value, field_type).casefold():
                            matches.append((source_row, column))
                processed += batch.num_rows
                self.progress.emit(processed, self.document.total_rows)
            self.finished.emit(matches if not self.is_cancelled() else None)
        except Exception as error:
            self.failed.emit(str(error))


class GlobalSortWorker(CancellableWorker):
    def __init__(self, document: ParquetDocument, column: int, descending: bool) -> None:
        super().__init__()
        self.document = document
        self.column = column
        self.descending = descending

    @staticmethod
    def _sortable_value(value: object, field_type: object) -> object:
        if contains_binary_type(field_type):
            return embedded_binary_payload(value) or b""
        if (
            pa.types.is_boolean(field_type)
            or pa.types.is_integer(field_type)
            or pa.types.is_floating(field_type)
            or pa.types.is_decimal(field_type)
            or pa.types.is_date(field_type)
            or pa.types.is_time(field_type)
            or pa.types.is_timestamp(field_type)
            or pa.types.is_duration(field_type)
        ):
            return value
        if pa.types.is_string(field_type) or pa.types.is_large_string(field_type):
            return str(value).casefold()
        return display_text(value).casefold()

    @Slot()
    def run(self) -> None:
        processed = 0
        non_null: list[tuple[object, int]] = []
        null_rows: list[int] = []
        try:
            field = self.document.schema.field(self.column)
            column_name = field.name
            # 中文：文件级排序只扫描目标列并建立原始行号索引，随后分页按索引读取，既保证跨页顺序又不复制整张表。
            # English: File-level sorting scans only the target column and builds a source-row index; pages then read by that index, preserving cross-page order without copying the full table.
            for batch in self.document.iter_batches_from(0, EXPORT_BATCH_ROWS, columns=[column_name]):
                if self.is_cancelled():
                    break
                array = batch.column(0)
                for local_row in range(batch.num_rows):
                    if self.is_cancelled():
                        break
                    source_row = processed + local_row
                    value = array[local_row].as_py()
                    if value is None:
                        null_rows.append(source_row)
                    else:
                        non_null.append((self._sortable_value(value, field.type), source_row))
                processed += batch.num_rows
                self.progress.emit(processed, self.document.total_rows)
            if self.is_cancelled():
                self.finished.emit(None)
                return
            non_null.sort(key=lambda item: item[0], reverse=self.descending)
            row_order = [source_row for _value, source_row in non_null]
            row_order.extend(null_rows)
            self.finished.emit((self.column, self.descending, row_order))
        except Exception as error:
            self.failed.emit(str(error))
