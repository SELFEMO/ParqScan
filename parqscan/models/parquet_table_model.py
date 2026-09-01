from __future__ import annotations

import math
from collections import OrderedDict
from typing import Any

import pyarrow as pa
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QSize, QThreadPool, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPixmap

from parqscan.constants import IMAGE_HOVER_CACHE_LIMIT, PAGE_LOAD_THREADS, THUMBNAIL_CACHE_LIMIT, THUMBNAIL_SIZE
from parqscan.data.page_loader import PageLoadTask
from parqscan.data.parquet_document import ParquetDocument
from parqscan.utils.binary import (
    contains_binary_type,
    embedded_binary_candidate,
    embedded_binary_payload,
    embedded_file_name_hint,
    embedded_image_payload,
    format_size,
)
from parqscan.utils.qt_images import decode_image_bytes
from parqscan.utils.search import searchable_text
from parqscan.utils.serialization import display_text, json_safe


class ParquetTableModel(QAbstractTableModel):
    RawValueRole = Qt.ItemDataRole.UserRole + 1
    SourceRowRole = Qt.ItemDataRole.UserRole + 2
    IsBinaryRole = Qt.ItemDataRole.UserRole + 3
    IsImageRole = Qt.ItemDataRole.UserRole + 4
    LoadingRole = Qt.ItemDataRole.UserRole + 5
    BinaryPayloadRole = Qt.ItemDataRole.UserRole + 6
    SearchMatchRole = Qt.ItemDataRole.UserRole + 7

    loaded_rows_changed = Signal(int)
    search_matches_changed = Signal(int)
    page_loading = Signal(int, int)
    page_progress = Signal(int, int)
    page_loaded = Signal(int, int)
    page_load_failed = Signal(str)
    page_state_changed = Signal(int, int, int)
    image_cell_ready = Signal(int, int)

    def __init__(
        self,
        document: ParquetDocument,
        page_size: int,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.document = document
        self._page_size = max(1, page_size)
        self._page_index = 0
        self._requested_page_index = 0
        self._table: pa.Table | None = None
        self._page_source_rows: list[int] = []
        self._loading_source_rows: list[int] = []
        self._global_row_order: list[int] | None = None
        self._loading = False
        self._generation = 0
        self._tasks: dict[int, PageLoadTask] = {}
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(PAGE_LOAD_THREADS)
        self._filtered_offsets: list[int] | None = None
        self._ordered_offsets: list[int] | None = None
        self._search_text = ""
        self._search_matches: list[tuple[int, int]] = []
        self._search_match_set: set[tuple[int, int]] = set()
        self._pixmap_cache: OrderedDict[tuple[int, int, int], QPixmap] = OrderedDict()
        self._hover_cache: OrderedDict[tuple[int, int, int], QPixmap] = OrderedDict()
        self._invalid_image_cells: set[tuple[int, int]] = set()

    @property
    def page_size(self) -> int:
        return self._page_size

    @property
    def page_index(self) -> int:
        return self._page_index

    @property
    def page_number(self) -> int:
        return self._page_index + 1

    @property
    def total_pages(self) -> int:
        return max(1, math.ceil(self.document.total_rows / self._page_size))

    @property
    def loading(self) -> bool:
        return self._loading

    @property
    def loaded_rows(self) -> int:
        return self._table.num_rows if self._table is not None else 0

    @property
    def search_matches(self) -> tuple[tuple[int, int], ...]:
        return tuple(self._search_matches)

    def _expected_page_rows(self, page_index: int | None = None) -> int:
        index = self._requested_page_index if page_index is None else page_index
        start = index * self._page_size
        total = len(self._global_row_order) if self._global_row_order is not None else self.document.total_rows
        return max(0, min(self._page_size, total - start))

    def _source_rows_for_page(self, page_index: int) -> list[int]:
        start = page_index * self._page_size
        end = min(start + self._page_size, self.document.total_rows)
        if self._global_row_order is not None:
            return self._global_row_order[start:end]
        return list(range(start, end))

    def _base_offsets(self) -> list[int]:
        if self._table is None:
            return []
        return list(range(self._table.num_rows))

    def _active_offsets(self) -> list[int]:
        if self._ordered_offsets is not None:
            return self._ordered_offsets
        if self._filtered_offsets is not None:
            return self._filtered_offsets
        return self._base_offsets()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        if self._loading:
            return self._expected_page_rows()
        return len(self._active_offsets())

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.document.schema)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.document.schema.names[section]
        if section < 0 or section >= self.rowCount():
            return None
        if self._loading:
            return str(self.source_row(section) + 1)
        return str(self.source_row(section) + 1)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def _page_offset(self, view_row: int) -> int:
        offsets = self._active_offsets()
        return offsets[view_row]

    def source_row(self, view_row: int) -> int:
        if self._loading:
            if 0 <= view_row < len(self._loading_source_rows):
                return self._loading_source_rows[view_row]
            return self._requested_page_index * self._page_size + view_row
        offset = self._page_offset(view_row)
        if 0 <= offset < len(self._page_source_rows):
            return self._page_source_rows[offset]
        return self._page_index * self._page_size + offset

    def view_row_for_source(self, source_row: int) -> int | None:
        if self._loading or source_row not in self._page_source_rows:
            return None
        page_offset = self._page_source_rows.index(source_row)
        try:
            return self._active_offsets().index(page_offset)
        except ValueError:
            return None

    def page_index_for_source(self, source_row: int) -> int:
        if self._global_row_order is None:
            position = source_row
        else:
            try:
                position = self._global_row_order.index(source_row)
            except ValueError:
                position = source_row
        return max(0, min(position // self._page_size, self.total_pages - 1))

    def _raw_value(self, view_row: int, column: int) -> Any:
        if self._table is None or self._loading:
            return None
        offset = self._page_offset(view_row)
        return self._table.column(column)[offset].as_py()

    def _binary_display(self, value: Any) -> str:
        candidate = embedded_binary_candidate(value)
        if candidate is None:
            return "NULL"
        image = embedded_image_payload(value)
        prefix = f"IMAGE · {image.image_format.name}" if image is not None else "BLOB"
        size = len(image.data) if image is not None else len(candidate.data)
        hint = embedded_file_name_hint(value) or candidate.path_text
        return f"{prefix} · {format_size(size)}" + (f" · {hint}" if hint else "")

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= self.rowCount():
            return None
        field = self.document.schema.field(index.column())
        binary = contains_binary_type(field.type)

        if self._loading:
            if role == self.SourceRowRole:
                return self.source_row(index.row())
            if role == self.IsBinaryRole:
                return binary
            if role == self.LoadingRole:
                return True
            if role == Qt.ItemDataRole.DisplayRole:
                return ""
            return None

        value = self._raw_value(index.row(), index.column())
        if role == self.RawValueRole:
            return value
        if role == self.BinaryPayloadRole:
            return embedded_binary_payload(value) if binary else None
        if role == self.SourceRowRole:
            return self.source_row(index.row())
        if role == self.IsBinaryRole:
            return binary
        if role == self.LoadingRole:
            return False
        if role == self.IsImageRole:
            return binary and self.image_pixmap(index, THUMBNAIL_SIZE) is not None
        if role == self.SearchMatchRole:
            return (self.source_row(index.row()), index.column()) in self._search_match_set
        if role == Qt.ItemDataRole.DisplayRole:
            return self._binary_display(value) if binary else display_text(value, 260)
        if role == Qt.ItemDataRole.DecorationRole and binary:
            return self.image_pixmap(index, THUMBNAIL_SIZE)
        if role == Qt.ItemDataRole.ToolTipRole:
            # 中文：完整值由双击详情窗口承载，禁用平台原生长文本 Tooltip 可避免黑色方块遮挡表格和暴露未统一的系统样式。
            # English: Full values belong in the double-click detail dialog; disabling native long-text tooltips prevents opaque square panels from covering the table.
            return None
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.SizeHintRole and binary and self.image_pixmap(index, THUMBNAIL_SIZE) is not None:
            return QSize(THUMBNAIL_SIZE + 16, THUMBNAIL_SIZE + 16)
        if role == Qt.ItemDataRole.BackgroundRole and (self.source_row(index.row()), index.column()) in self._search_match_set:
            return QBrush(QColor(30, 144, 255, 70))
        return None

    def image_pixmap(self, index: QModelIndex, size: int) -> QPixmap | None:
        if not index.isValid() or self._loading or self._table is None:
            return None
        source_row = self.source_row(index.row())
        cell_key = (source_row, index.column())
        if cell_key in self._invalid_image_cells:
            return None
        cache_key = (source_row, index.column(), size)
        cache, limit, emit_ready = self._pixmap_store(size)
        cached = cache.get(cache_key)
        if cached is not None:
            cache.move_to_end(cache_key)
            return cached
        embedded = embedded_image_payload(self._raw_value(index.row(), index.column()))
        if embedded is None:
            return None
        image = decode_image_bytes(embedded.data, embedded.image_format, size)
        if image.isNull():
            self._invalid_image_cells.add(cell_key)
            return None

        # 中文：QPixmap 只能在 GUI 线程创建，后台任务仅返回 Arrow 数据，避免 GUI 对象跨线程产生未定义行为。
        # English: QPixmap must be created on the GUI thread, so workers return Arrow data only and never move GUI objects across threads.
        pixmap = QPixmap.fromImage(image)
        cache[cache_key] = pixmap
        while len(cache) > limit:
            cache.popitem(last=False)
        if emit_ready:
            self.image_cell_ready.emit(index.row(), index.column())
        return pixmap

    def _pixmap_store(self, size: int) -> tuple[OrderedDict[tuple[int, int, int], QPixmap], int, bool]:
        if size <= THUMBNAIL_SIZE:
            return self._pixmap_cache, THUMBNAIL_CACHE_LIMIT, True
        return self._hover_cache, IMAGE_HOVER_CACHE_LIMIT, False

    def load_page(self, page_index: int) -> None:
        page_index = max(0, min(page_index, self.total_pages - 1))
        # 中文：翻页时立即丢弃旧页并提升请求代次，确保内存始终只保留一个确定页面，过期线程结果也不能覆盖新页。
        # English: Changing pages drops the old page and advances the request generation so memory holds one deterministic page and stale workers cannot overwrite it.
        self._generation += 1
        for task in list(self._tasks.values()):
            task.cancel()
        self._thread_pool.clear()
        self.beginResetModel()
        self._requested_page_index = page_index
        self._loading_source_rows = self._source_rows_for_page(page_index)
        self._loading = True
        self._table = None
        self._page_source_rows = []
        self._clear_page_state()
        self.endResetModel()
        self.page_loading.emit(page_index + 1, self.total_pages)
        self.page_state_changed.emit(page_index + 1, self.total_pages, self._page_size)
        self.loaded_rows_changed.emit(0)

        start_row = page_index * self._page_size
        task = PageLoadTask(
            self._generation,
            self.document.path,
            page_index,
            start_row,
            self._expected_page_rows(page_index),
            self._loading_source_rows if self._global_row_order is not None else None,
        )
        task.signals.progress.connect(self._task_progress)
        task.signals.loaded.connect(self._task_loaded)
        task.signals.failed.connect(self._task_failed)
        task.signals.cancelled.connect(self._task_cancelled)
        self._tasks[self._generation] = task
        self._thread_pool.start(task)

    def set_page_size(self, page_size: int) -> None:
        page_size = max(1, page_size)
        if page_size == self._page_size:
            return
        # 中文：改变页大小后以当前页首行重新定位，避免用户因为设置调整被无故跳回文件开头。
        # English: Page-size changes are anchored to the current page's first row so a preference adjustment does not unexpectedly jump back to the file start.
        current_start = self._page_index * self._page_size
        self._page_size = page_size
        self.load_page(current_start // page_size)

    def _task_progress(self, generation: int, current: int, total: int) -> None:
        if generation == self._generation:
            self.page_progress.emit(current, total)

    def _task_loaded(self, generation: int, page_index: int, table: object) -> None:
        # 中文：先释放任务引用再检查代次，旧任务即使晚到也不会滞留在模型中。
        # English: The task reference is released before generation validation so a late stale result cannot remain retained by the model.
        self._tasks.pop(generation, None)
        if generation != self._generation or not isinstance(table, pa.Table):
            return
        self.beginResetModel()
        self._page_index = page_index
        self._requested_page_index = page_index
        self._table = table
        self._page_source_rows = list(self._loading_source_rows)
        self._loading_source_rows = []
        self._loading = False
        self._clear_page_state()
        self.endResetModel()
        self.loaded_rows_changed.emit(table.num_rows)
        self.page_loaded.emit(page_index + 1, table.num_rows)
        self.page_state_changed.emit(page_index + 1, self.total_pages, self._page_size)
        self._emit_search_highlight_changed()

    def _task_failed(self, generation: int, _page_index: int, message: str) -> None:
        # 中文：失败的旧任务只做资源清理，不弹出已经失去上下文的错误提示。
        # English: A failed stale task only releases resources and never shows an error that no longer matches the active page.
        self._tasks.pop(generation, None)
        if generation != self._generation:
            return
        self.beginResetModel()
        self._loading = False
        self._table = None
        self._page_source_rows = []
        self._loading_source_rows = []
        self._clear_page_state()
        self.endResetModel()
        self.page_load_failed.emit(message)

    def _task_cancelled(self, generation: int, _page_index: int) -> None:
        self._tasks.pop(generation, None)

    def _clear_page_state(self, clear_pixmaps: bool = True) -> None:
        self._filtered_offsets = None
        self._ordered_offsets = None
        if clear_pixmaps:
            self._pixmap_cache.clear()
            self._hover_cache.clear()
            self._invalid_image_cells.clear()

    def raw_value(self, row: int, column: int) -> Any:
        if row < 0 or row >= self.rowCount() or self._loading:
            return None
        return self._raw_value(row, column)

    def row_as_json(self, row: int) -> dict[str, Any]:
        return {
            name: json_safe(self.raw_value(row, column))
            for column, name in enumerate(self.document.schema.names)
        }

    def column_as_list(self, column: int) -> list[Any]:
        return [json_safe(self.raw_value(row, column)) for row in range(self.rowCount())]

    def _searchable_text_for_offset(self, offset: int, column: int) -> str:
        if self._table is None:
            return ""
        value = self._table.column(column)[offset].as_py()
        field = self.document.schema.field(column)
        return searchable_text(value, field.type)

    def find_page_matches(self, query: str) -> list[tuple[int, int]]:
        needle = query.strip().casefold()
        if not needle or self._table is None or self._loading:
            return []
        matches: list[tuple[int, int]] = []
        # 中文：页内搜索按当前可见偏移顺序生成原始行坐标，既尊重过滤结果，也让高亮和前后导航共用稳定坐标。
        # English: Page search emits source-row coordinates in current visible-offset order, respecting filters while giving highlighting and navigation one stable coordinate system.
        for offset in self._active_offsets():
            if offset < 0 or offset >= len(self._page_source_rows):
                continue
            source_row = self._page_source_rows[offset]
            for column in range(self.columnCount()):
                if needle in self._searchable_text_for_offset(offset, column).casefold():
                    matches.append((source_row, column))
        return matches

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if self._table is None or self._loading or column < 0 or column >= self.columnCount():
            return
        offsets = list(self._filtered_offsets) if self._filtered_offsets is not None else self._base_offsets()
        field_type = self.document.schema.field(column).type

        def sortable(offset: int) -> tuple[bool, Any]:
            value = self._table.column(column)[offset].as_py()
            if value is None:
                return True, ""
            if pa.types.is_integer(field_type) or pa.types.is_floating(field_type) or pa.types.is_decimal(field_type):
                return False, value
            if contains_binary_type(field_type):
                return False, embedded_binary_payload(value) or b""
            return False, display_text(value).casefold()

        offsets.sort(key=sortable, reverse=order == Qt.SortOrder.DescendingOrder)
        self.beginResetModel()
        self._ordered_offsets = offsets
        self.endResetModel()
        self._emit_search_highlight_changed()

    def apply_filter(self, column: int, operator: str, query: str) -> None:
        if self._table is None or self._loading:
            return
        query_folded = query.casefold()
        matches: list[int] = []
        for offset in self._base_offsets():
            text = self._searchable_text_for_offset(offset, column).casefold()
            accepted = text == query_folded if operator == "equals" else query_folded in text
            if accepted:
                matches.append(offset)
        self.beginResetModel()
        self._filtered_offsets = matches
        self._ordered_offsets = None
        self.endResetModel()
        self._emit_search_highlight_changed()

    def clear_filter(self) -> None:
        self.beginResetModel()
        self._filtered_offsets = None
        self._ordered_offsets = None
        self.endResetModel()
        self._emit_search_highlight_changed()

    def order_search_matches(self, matches: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if self._global_row_order is None:
            return sorted(matches, key=lambda coordinate: (coordinate[0], coordinate[1]))

        # 中文：文件级排序改变的是浏览顺序，搜索导航也必须按该顺序排列；只按匹配行分组可避免为全部行再建立一份位置字典。
        # English: File sorting changes browse order, so search navigation must follow it; grouping only matched rows avoids another full-row position dictionary.
        columns_by_row: dict[int, list[int]] = {}
        for source_row, column in matches:
            columns_by_row.setdefault(source_row, []).append(column)
        ordered: list[tuple[int, int]] = []
        for source_row in self._global_row_order:
            for column in sorted(columns_by_row.pop(source_row, [])):
                ordered.append((source_row, column))
        for source_row in sorted(columns_by_row):
            for column in sorted(columns_by_row[source_row]):
                ordered.append((source_row, column))
        return ordered

    def set_search_results(self, query: str, matches: list[tuple[int, int]]) -> None:
        self._search_text = query.strip()
        self._search_matches = list(matches)
        self._search_match_set = set(matches)
        self.search_matches_changed.emit(len(self._search_matches))
        self._emit_search_highlight_changed()

    def clear_search(self) -> None:
        self.set_search_results("", [])

    def _emit_search_highlight_changed(self) -> None:
        if self.rowCount() and self.columnCount() and not self._loading:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, self.columnCount() - 1),
                [Qt.ItemDataRole.BackgroundRole, self.SearchMatchRole],
            )

    def set_row_order(self, source_rows: list[int]) -> None:
        # 中文：排序结果只保存原始行号，不保存数据副本；后续每一页仍通过后台读取，保持分页内存边界。
        # English: Sorting stores only source-row indices rather than a data copy; every page is still loaded in the background, preserving the pagination memory boundary.
        self._global_row_order = list(source_rows)
        self.load_page(0)

    def clear_row_order(self) -> None:
        if self._global_row_order is None:
            return
        self._global_row_order = None
        self.load_page(0)

    @property
    def has_row_order(self) -> bool:
        return self._global_row_order is not None

    def close(self) -> None:
        self._generation += 1
        for task in list(self._tasks.values()):
            task.cancel()
        self._thread_pool.clear()
        self._tasks.clear()
        self._table = None
        self._page_source_rows = []
        self._loading_source_rows = []
        self._global_row_order = None
        self._pixmap_cache.clear()
        self._hover_cache.clear()
        self._invalid_image_cells.clear()
