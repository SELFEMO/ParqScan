from __future__ import annotations

import re
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
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

MAX_GLOBAL_SEARCH_MATCHES = 50_000
_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_extract_output_path(target_dir: Path, name_hint: str | None, row_number: int, ext: str) -> Path:
    base_target = target_dir.resolve()
    raw_name = Path(name_hint).name if name_hint else ""
    cleaned = _UNSAFE_FILENAME_RE.sub("_", raw_name).strip().strip(".")
    if not cleaned or cleaned in {".", ".."}:
        cleaned = f"row_{row_number}.{ext}"
    output = (base_target / cleaned)
    if not output.suffix:
        output = output.with_suffix(f".{ext}")
    if output.exists():
        output = base_target / f"row_{row_number}_{output.name}"
    resolved = output.resolve()
    if not resolved.is_relative_to(base_target):
        raise ValueError(f"Unsafe image output path: {output}")
    return resolved


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
    def __init__(self, document: ParquetDocument | str, target: str, export_kind: str) -> None:
        super().__init__()
        self.path = document.path if isinstance(document, ParquetDocument) else str(document)
        self.target = target
        self.export_kind = export_kind

    @Slot()
    def run(self) -> None:
        doc: ParquetDocument | None = None
        try:
            doc = ParquetDocument(self.path)
            EXPORT_HANDLERS[self.export_kind](doc, self.target, self.progress.emit, self.is_cancelled)
            self.finished.emit(self.target if not self.is_cancelled() else None)
        except Exception as error:
            if not self.is_cancelled():
                self.failed.emit(str(error))
        finally:
            if doc is not None:
                doc.close()


class FragmentExportWorker(CancellableWorker):
    def __init__(
        self,
        document: ParquetDocument | str,
        target: str,
        start_row: int,
        end_row: int,
        columns: list[str],
    ) -> None:
        super().__init__()
        self.path = document.path if isinstance(document, ParquetDocument) else str(document)
        self.target = target
        self.start_row = start_row
        self.end_row = end_row
        self.columns = columns

    @Slot()
    def run(self) -> None:
        doc: ParquetDocument | None = None
        try:
            doc = ParquetDocument(self.path)
            export_parquet_fragment(
                doc,
                self.target,
                self.start_row,
                self.end_row,
                self.columns,
                self.progress.emit,
                self.is_cancelled,
            )
            self.finished.emit(self.target if not self.is_cancelled() else None)
        except Exception as error:
            if not self.is_cancelled():
                self.failed.emit(str(error))
        finally:
            if doc is not None:
                doc.close()


class ImageExtractWorker(CancellableWorker):
    def __init__(self, document: ParquetDocument | str, column_name: str, target_directory: str) -> None:
        super().__init__()
        self.path = document.path if isinstance(document, ParquetDocument) else str(document)
        self.column_name = column_name
        self.target_directory = target_directory

    @Slot()
    def run(self) -> None:
        exported = 0
        processed = 0
        doc: ParquetDocument | None = None
        try:
            doc = ParquetDocument(self.path)
            target = Path(self.target_directory)
            target.mkdir(parents=True, exist_ok=True)
            last_percent = -1
            for batch in doc.iter_batches_from(0, EXPORT_BATCH_ROWS, columns=[self.column_name]):
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
                        output = safe_extract_output_path(target, name_hint, row_number, image.image_format.extension)
                        output.write_bytes(image.data)
                        exported += 1
                    processed += 1
                percent = 100 if doc.total_rows <= 0 else min(100, (processed * 100) // doc.total_rows)
                if percent != last_percent or processed >= doc.total_rows:
                    last_percent = percent
                    self.progress.emit(processed, doc.total_rows)
            self.finished.emit(exported if not self.is_cancelled() else None)
        except Exception as error:
            if not self.is_cancelled():
                self.failed.emit(str(error))
        finally:
            if doc is not None:
                doc.close()


class GlobalSearchWorker(CancellableWorker):
    def __init__(self, document: ParquetDocument | str, query: str) -> None:
        super().__init__()
        self.path = document.path if isinstance(document, ParquetDocument) else str(document)
        self.query = query.strip().casefold()

    @Slot()
    def run(self) -> None:
        matches: list[tuple[int, int]] = []
        processed = 0
        doc: ParquetDocument | None = None
        try:
            if not self.query:
                self.finished.emit(matches)
                return
            doc = ParquetDocument(self.path)
            last_percent = -1
            # 中文：搜索按批次扫描整个文件并限制最大命中数，同时对纯字符串列走 Arrow 向量化预筛。
            # English: Search scans the file in batches with a match cap and vectorized Arrow pre-filtering for string columns.
            for batch in doc.iter_batches_from(0, EXPORT_BATCH_ROWS):
                if self.is_cancelled() or len(matches) >= MAX_GLOBAL_SEARCH_MATCHES:
                    break
                for column in range(batch.num_columns):
                    if self.is_cancelled() or len(matches) >= MAX_GLOBAL_SEARCH_MATCHES:
                        break
                    field_type = doc.schema.field(column).type
                    col_array = batch.column(column)
                    if pa.types.is_string(field_type) or pa.types.is_large_string(field_type):
                        mask = pc.match_substring(col_array, self.query, ignore_case=True)
                        indices = pc.indices_nonzero(mask).to_pylist()
                        for local_row in indices:
                            matches.append((processed + local_row, column))
                            if len(matches) >= MAX_GLOBAL_SEARCH_MATCHES:
                                break
                    else:
                        values = col_array.to_pylist()
                        for local_row, value in enumerate(values):
                            if self.is_cancelled():
                                break
                            if value is not None and self.query in searchable_text(value, field_type).casefold():
                                matches.append((processed + local_row, column))
                                if len(matches) >= MAX_GLOBAL_SEARCH_MATCHES:
                                    break
                processed += batch.num_rows
                percent = 100 if doc.total_rows <= 0 else min(100, (processed * 100) // doc.total_rows)
                if percent != last_percent or processed >= doc.total_rows:
                    last_percent = percent
                    self.progress.emit(processed, doc.total_rows)
            if not self.is_cancelled():
                matches.sort(key=lambda item: (item[0], item[1]))
            self.finished.emit(matches if not self.is_cancelled() else None)
        except Exception as error:
            if not self.is_cancelled():
                self.failed.emit(str(error))
        finally:
            if doc is not None:
                doc.close()


class GlobalSortWorker(CancellableWorker):
    def __init__(self, document: ParquetDocument | str, column: int, descending: bool) -> None:
        super().__init__()
        self.path = document.path if isinstance(document, ParquetDocument) else str(document)
        self.column = column
        self.descending = descending

    @staticmethod
    def _supports_arrow_sort(field_type: object) -> bool:
        return (
            pa.types.is_boolean(field_type)
            or pa.types.is_integer(field_type)
            or pa.types.is_floating(field_type)
            or pa.types.is_decimal(field_type)
            or pa.types.is_date(field_type)
            or pa.types.is_time(field_type)
            or pa.types.is_timestamp(field_type)
            or pa.types.is_duration(field_type)
            or pa.types.is_string(field_type)
            or pa.types.is_large_string(field_type)
            or pa.types.is_binary(field_type)
            or pa.types.is_large_binary(field_type)
        )

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
        doc: ParquetDocument | None = None
        try:
            doc = ParquetDocument(self.path)
            field = doc.schema.field(self.column)
            column_name = field.name
            if self._supports_arrow_sort(field.type):
                chunks: list[pa.Array] = []
                for batch in doc.iter_batches_from(0, EXPORT_BATCH_ROWS, columns=[column_name]):
                    if self.is_cancelled():
                        self.finished.emit(None)
                        return
                    chunks.append(batch.column(0))
                    processed += batch.num_rows
                    self.progress.emit(processed, doc.total_rows)
                if self.is_cancelled():
                    self.finished.emit(None)
                    return
                if not chunks:
                    self.finished.emit((self.column, self.descending, []))
                    return
                combined = pa.chunked_array(chunks)
                order = "descending" if self.descending else "ascending"
                indices = pc.sort_indices(combined, sort_keys=[("", order)], null_placement="at_end")
                self.finished.emit((self.column, self.descending, indices.to_pylist()))
                return

            non_null: list[tuple[object, int]] = []
            null_rows: list[int] = []
            for batch in doc.iter_batches_from(0, EXPORT_BATCH_ROWS, columns=[column_name]):
                if self.is_cancelled():
                    break
                values = batch.column(0).to_pylist()
                for local_row, value in enumerate(values):
                    if self.is_cancelled():
                        break
                    source_row = processed + local_row
                    if value is None:
                        null_rows.append(source_row)
                    else:
                        non_null.append((self._sortable_value(value, field.type), source_row))
                processed += batch.num_rows
                self.progress.emit(processed, doc.total_rows)
            if self.is_cancelled():
                self.finished.emit(None)
                return
            non_null.sort(key=lambda item: item[0], reverse=self.descending)
            row_order = [source_row for _value, source_row in non_null]
            row_order.extend(null_rows)
            self.finished.emit((self.column, self.descending, row_order))
        except Exception as error:
            if not self.is_cancelled():
                self.failed.emit(str(error))
        finally:
            if doc is not None:
                doc.close()
