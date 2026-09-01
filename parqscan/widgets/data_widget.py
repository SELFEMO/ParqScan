from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QItemSelectionModel, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressDialog,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from parqscan.config import ConfigManager
from parqscan.constants import DEFAULT_ROW_HEIGHT, IMAGE_ROW_HEIGHT, SEARCH_DEBOUNCE_MS, THUMBNAIL_SIZE
from parqscan.data.parquet_document import ParquetDocument
from parqscan.data.workers import GlobalSearchWorker, GlobalSortWorker, ImageExtractWorker
from parqscan.dialogs.cell_detail_dialog import RecordDetailDialog
from parqscan.dialogs.hex_dialog import HexDialog
from parqscan.i18n import Translator
from parqscan.models.parquet_table_model import ParquetTableModel
from parqscan.utils.binary import (
    contains_binary_type,
    embedded_binary_payload,
    embedded_file_name_hint,
    embedded_image_payload,
    to_base64,
)
from parqscan.utils.icons import make_icon
from parqscan.widgets.binary_delegate import BinaryCellDelegate
from parqscan.widgets.design_system import (
    CardFrame,
    HintToolButton,
    LoadingOverlay,
    PaginationBar,
    RoundedComboBox,
    RoundedMenu,
    RoundedTableView,
    SearchField,
    select_item,
    show_message,
)
from parqscan.widgets.image_popup import ImageHoverPreview


@dataclass
class SearchState:
    query: str = ""
    matches: list[tuple[int, int]] = field(default_factory=list)
    cursor: int = -1
    pending_coordinate: tuple[int, int] | None = None
    complete: bool = False

    def reset(self, query: str = "") -> None:
        # 中文：文件级与页内搜索必须维护彼此独立的结果、游标和待跳转坐标，否则切换范围时会复用错误状态。
        # English: File and page search must keep independent results, cursors, and pending coordinates, otherwise switching scope reuses invalid state.
        self.query = query
        self.matches.clear()
        self.cursor = -1
        self.pending_coordinate = None
        self.complete = False


@dataclass
class PageFilterState:
    column: int = -1
    operator: str = "contains"
    query: str = ""
    active: bool = False

    def clear(self) -> None:
        # 中文：筛选条件必须独立于搜索结果保存，搜索完成或分页重载才不会把用户已经应用的视图状态恢复为初始状态。
        # English: Filter criteria must be stored independently from search results so search completion or page reload cannot restore the user's applied view to its initial state.
        self.column = -1
        self.operator = "contains"
        self.query = ""
        self.active = False


class DataWidget(QWidget):
    coordinate_changed = Signal(int, int)
    loaded_rows_changed = Signal(int)

    def __init__(
        self,
        document: ParquetDocument,
        translator: Translator,
        config: ConfigManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DataPage")
        self.document = document
        self.translator = translator
        self.config = config
        self.model = ParquetTableModel(document, config.page_size(), self)
        self._threads: list[QThread] = []
        self._worker_contexts: dict[object, tuple[QProgressDialog, QThread, Callable[[object], None]]] = {}
        self._search_states = {"file": SearchState(), "page": SearchState()}
        self._page_filter_state = PageFilterState()
        self._search_generation = 0
        self._search_contexts: dict[object, tuple[int, str, bool, QThread]] = {}
        self._sort_column = -1
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._active_sort_worker: object | None = None
        self._restoring_columns = False
        self._page_error_shown = False
        self._shutting_down = False
        self._detail_dialogs: set[RecordDetailDialog] = set()

        self.header_eyebrow = QLabel()
        self.header_eyebrow.setObjectName("EyebrowLabel")
        self.header_title = QLabel()
        self.header_title.setObjectName("PageTitle")
        heading_layout = QVBoxLayout()
        heading_layout.setSpacing(3)
        heading_layout.addWidget(self.header_eyebrow)
        heading_layout.addWidget(self.header_title)

        self.search_scope_combo = RoundedComboBox()
        self.search_scope_combo.setMinimumWidth(132)
        self.search_field = SearchField()
        self.search_edit = self.search_field.editor
        self.search_previous_button = self._tool_button("left")
        self.search_next_button = self._tool_button("right")
        self.search_clear_button = self._tool_button("close")
        self.search_count_label = QLabel()
        self.search_count_label.setObjectName("Chip")

        search_card = CardFrame(object_name="ToolbarCard")
        search_layout = QHBoxLayout(search_card)
        search_layout.setContentsMargins(12, 10, 12, 10)
        search_layout.setSpacing(8)
        search_layout.addWidget(self.search_scope_combo)
        search_layout.addWidget(self.search_field, 1)
        search_layout.addWidget(self.search_previous_button)
        search_layout.addWidget(self.search_next_button)
        search_layout.addWidget(self.search_clear_button)
        search_layout.addWidget(self.search_count_label)

        self.filter_column_combo = RoundedComboBox()
        self.filter_column_combo.addItems(document.schema.names)
        self.filter_column_combo.setMinimumWidth(130)
        self.filter_operator_combo = RoundedComboBox()
        self.filter_operator_combo.setMinimumWidth(92)
        self.filter_value_edit = QLineEdit()
        self.filter_apply_button = QPushButton()
        self.filter_apply_button.setProperty("secondary", True)
        self.filter_clear_button = QPushButton()
        self.filter_clear_button.setProperty("ghost", True)
        self.sort_clear_button = QPushButton()
        self.sort_clear_button.setProperty("ghost", True)
        self.sort_clear_button.setEnabled(False)
        self.extract_images_button = QPushButton()
        self.extract_images_button.setProperty("primary", True)
        self.extract_images_button.setIcon(make_icon("image", "#FFFFFF"))

        filter_card = CardFrame(object_name="ToolbarCard")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(12, 10, 12, 10)
        filter_layout.setSpacing(8)
        filter_layout.addWidget(self.filter_column_combo)
        filter_layout.addWidget(self.filter_operator_combo)
        filter_layout.addWidget(self.filter_value_edit, 1)
        filter_layout.addWidget(self.filter_apply_button)
        filter_layout.addWidget(self.filter_clear_button)
        filter_layout.addWidget(self.sort_clear_button)
        filter_layout.addStretch(1)
        filter_layout.addWidget(self.extract_images_button)

        self.table_card = CardFrame(object_name="TableCard")
        table_layout = QVBoxLayout(self.table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(8)

        self.table = RoundedTableView()
        self.table.setObjectName("DataTable")
        self.table.setModel(self.model)
        self.table.setItemDelegate(BinaryCellDelegate(self.table))
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setShowGrid(False)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_corner = QWidget(self.table)
        self.scroll_corner.setObjectName("ScrollCorner")
        self.scroll_corner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # 中文：Qt 默认在双滚动条交叉处放置未样式化方块，显式角部控件可让该区域与表格背景连续。
        # English: Qt inserts an unstyled square where both scrollbars meet, so an explicit corner widget keeps that region continuous with the table surface.
        self.table.setCornerWidget(self.scroll_corner)
        self.table.horizontalHeader().setSectionsMovable(True)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().setSortIndicatorShown(False)
        self.table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.horizontalHeader().setMinimumSectionSize(78)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setMinimumHeight(42)
        self.table.verticalHeader().setDefaultSectionSize(DEFAULT_ROW_HEIGHT)
        self.table.verticalHeader().setMinimumSectionSize(DEFAULT_ROW_HEIGHT)
        self.table.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.viewport().setMouseTracking(True)
        self.table.viewport().installEventFilter(self)
        self.hover_preview = ImageHoverPreview(self.table, self.model)
        self._configure_table_columns()
        self._restore_column_order()

        table_layout.addWidget(self.table, 1)
        self.pagination = PaginationBar(translator, self.model.page_size)
        table_layout.addWidget(self.pagination)
        self.loading_overlay = LoadingOverlay(translator, self.table.viewport())
        self.loading_overlay.setGeometry(self.table.viewport().rect())

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(12)
        root.addLayout(heading_layout)
        root.addWidget(search_card)
        root.addWidget(filter_card)
        root.addWidget(self.table_card, 1)

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self.column_order_timer = QTimer(self)
        self.column_order_timer.setSingleShot(True)
        self.column_order_timer.setInterval(260)

        self.search_edit.textChanged.connect(lambda: self.search_timer.start())
        self.search_scope_combo.currentIndexChanged.connect(self._search_scope_changed)
        self.search_timer.timeout.connect(self._update_search)
        self.search_previous_button.clicked.connect(self.search_previous)
        self.search_next_button.clicked.connect(self.search_next)
        self.search_clear_button.clicked.connect(self.search_edit.clear)
        self.filter_apply_button.clicked.connect(self.apply_filter)
        self.filter_clear_button.clicked.connect(self.clear_filter)
        self.sort_clear_button.clicked.connect(self.clear_file_sort)
        self.extract_images_button.clicked.connect(self.extract_images)
        self.table.doubleClicked.connect(self.open_record_detail)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.selectionModel().currentChanged.connect(self._current_changed)
        self.table.selectionModel().selectionChanged.connect(self._refresh_image_hover)
        self.table.horizontalHeader().sectionClicked.connect(self._request_file_sort)
        self.table.horizontalHeader().sectionMoved.connect(self._column_moved)
        self.table.horizontalHeader().customContextMenuRequested.connect(self._show_header_menu)
        self.column_order_timer.timeout.connect(self._save_column_order)
        self.pagination.page_requested.connect(self.model.load_page)
        self.pagination.page_size_changed.connect(self._change_page_size)
        self.model.loaded_rows_changed.connect(self.loaded_rows_changed)
        self.model.search_matches_changed.connect(self._search_matches_changed)
        self.model.page_loading.connect(self._page_loading)
        self.model.page_progress.connect(self._page_progress)
        self.model.page_loaded.connect(self._page_loaded)
        self.model.page_load_failed.connect(self._page_load_failed)
        self.model.page_state_changed.connect(self._page_state_changed)
        self.model.image_cell_ready.connect(self._image_cell_ready)
        self.translator.language_changed.connect(self.retranslate)

        self.retranslate()
        self._page_state_changed(1, self.model.total_pages, self.model.page_size)
        QTimer.singleShot(0, lambda: self.model.load_page(0))

    def _tool_button(self, icon_name: str) -> HintToolButton:
        button = HintToolButton()
        button.setProperty("nav", True)
        button.setIcon(make_icon(icon_name))
        button.setFixedSize(32, 32)
        return button

    def _configure_table_columns(self) -> None:
        header = self.table.horizontalHeader()
        stretch_column: int | None = None
        text_tokens = ("text", "description", "content", "caption", "title", "summary")

        for column, field in enumerate(self.document.schema):
            name = field.name.casefold()
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            if contains_binary_type(field.type):
                width = THUMBNAIL_SIZE + 64
            elif any(token in name for token in text_tokens):
                width = 300
                if stretch_column is None:
                    stretch_column = column
            elif any(token in name for token in ("path", "url")):
                width = 240
            elif any(token in name for token in ("id", "year", "row", "col", "count", "num", "type")):
                width = 124
            else:
                width = 160
            self.table.setColumnWidth(column, width)

        # 中文：优先让正文类字段吸收窗口剩余宽度，避免少量列的数据表右侧出现大片空白；超宽 Schema 仍保留横向滚动。
        # English: A descriptive text field absorbs spare viewport width to avoid a large blank area on narrow schemas, while wide schemas still retain horizontal scrolling.
        if stretch_column is not None:
            header.setSectionResizeMode(stretch_column, QHeaderView.ResizeMode.Stretch)
        elif self.document.total_columns:
            header.setSectionResizeMode(self.document.total_columns - 1, QHeaderView.ResizeMode.Stretch)

    def _restore_column_order(self) -> None:
        # 中文：恢复的是表头视觉位置而不是模型字段索引，因此数据访问、导出和搜索仍保持稳定的 Schema 映射。
        # English: Only the header visual positions are restored, so data access, export, and search keep their stable schema-index mapping.
        order = self.config.column_order(list(self.document.schema.names))
        if order is None:
            return
        header = self.table.horizontalHeader()
        self._restoring_columns = True
        try:
            for target_visual, logical_index in enumerate(order):
                current_visual = header.visualIndex(logical_index)
                if current_visual != target_visual:
                    header.moveSection(current_visual, target_visual)
        finally:
            self._restoring_columns = False

    def _column_moved(self, _logical: int, _old_visual: int, _new_visual: int) -> None:
        if not self._restoring_columns:
            # 中文：拖动过程中会连续产生位置变化，延迟写入可避免每个像素移动都刷新配置文件。
            # English: Header dragging emits many position changes, so deferred persistence avoids rewriting the configuration for every pixel of movement.
            self.column_order_timer.start()

    def _save_column_order(self) -> None:
        header = self.table.horizontalHeader()
        logical_order = [header.logicalIndex(visual) for visual in range(header.count())]
        self.config.set_column_order(list(self.document.schema.names), logical_order)

    def reset_column_order(self) -> None:
        header = self.table.horizontalHeader()
        self._restoring_columns = True
        try:
            for target_visual in range(header.count()):
                current_visual = header.visualIndex(target_visual)
                if current_visual != target_visual:
                    header.moveSection(current_visual, target_visual)
        finally:
            self._restoring_columns = False
        self.config.clear_column_order(list(self.document.schema.names))

    def _show_header_menu(self, position) -> None:
        menu = RoundedMenu(self)
        reset_action = menu.addAction(self.translator.tr("data.reset_column_order"))
        selected = menu.exec(self.table.horizontalHeader().mapToGlobal(position))
        if selected == reset_action:
            self.reset_column_order()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.table.viewport() and event.type() == QEvent.Type.Resize:
            self.loading_overlay.setGeometry(self.table.viewport().rect())
        return super().eventFilter(watched, event)

    def _change_page_size(self, page_size: int) -> None:
        self.config.set("page_size", page_size)
        self.model.set_page_size(page_size)

    def _page_loading(self, page_number: int, total_pages: int) -> None:
        self._page_error_shown = False
        self.loading_overlay.start(page_number, total_pages)
        self.pagination.set_loading(True)
        # 中文：页面模型会在加载时丢弃旧页偏移，但筛选条件属于用户显式设置，必须保留到新页加载完成后再应用；这里只清除旧页搜索坐标。
        # English: The model drops old-page offsets while loading, but filter criteria are explicit user state and must be reapplied after the new page arrives; only stale page-search coordinates are cleared here.
        if self._selected_search_scope() == "page":
            state = self._search_states["page"]
            state.matches.clear()
            state.cursor = -1
            state.pending_coordinate = None
            state.complete = False
            self.model.clear_search()
            if state.query:
                self.search_count_label.setText(self.translator.tr("data.page_search_waiting"))

    def _page_progress(self, current: int, total: int) -> None:
        self.loading_overlay.update_progress(current, total)

    def _page_loaded(self, _page_number: int, _row_count: int) -> None:
        self.loading_overlay.finish()
        self.pagination.set_loading(False)
        self._restore_page_filter_after_load()
        self._resize_rows()
        # 中文：翻页后必须回到新页顶部，否则上一页的滚动位置会让用户误以为页码或加载结果错误。
        # English: A newly loaded page must start at the top, otherwise the prior scroll position makes the page number and loaded result appear inconsistent.
        self.table.scrollToTop()
        self.table.horizontalScrollBar().setValue(0)
        self.table.viewport().update()
        scope = self._selected_search_scope()
        generation = self._search_generation
        if scope == "page":
            state = self._search_states["page"]
            if state.query:
                QTimer.singleShot(
                    0,
                    lambda query=state.query, request=generation: self._refresh_page_search_after_load(
                        query, request
                    ),
                )
        else:
            state = self._search_states["file"]
            if state.pending_coordinate is not None:
                coordinate = state.pending_coordinate
                QTimer.singleShot(
                    0,
                    lambda current=coordinate, query=state.query, request=generation: self._select_pending_file_match(
                        current, query, request
                    ),
                )

    def _refresh_page_search_after_load(self, query: str, generation: int) -> None:
        if (
            generation != self._search_generation
            or self._selected_search_scope() != "page"
            or self.search_edit.text().strip() != query
        ):
            return
        self._run_page_search(query, auto_select=False)

    def _select_pending_file_match(
        self, coordinate: tuple[int, int], query: str, generation: int
    ) -> None:
        state = self._search_states["file"]
        if (
            generation != self._search_generation
            or self._selected_search_scope() != "file"
            or state.query != query
            or state.pending_coordinate != coordinate
        ):
            return
        self._select_source_coordinate(*coordinate)

    def _page_load_failed(self, message: str) -> None:
        self.loading_overlay.finish()
        self.pagination.set_loading(False)
        if not self._page_error_shown:
            self._page_error_shown = True
            show_message(self, self.translator.tr("common.error"), message, critical=True)

    def _page_state_changed(self, current_page: int, total_pages: int, page_size: int) -> None:
        self.pagination.set_state(current_page, total_pages, page_size, self.document.total_rows)

    def _resize_rows(self) -> None:
        # 中文：新页先使用紧凑文本行高；图片单元格真正进入可见区并完成缩略图解码后再单独增高，避免预扫描整页附件。
        # English: A new page starts with compact text rows, and only image cells that become visible and decode successfully expand their rows, avoiding a full-page attachment scan.
        for row in range(self.model.rowCount()):
            self.table.setRowHeight(row, DEFAULT_ROW_HEIGHT)

    def _image_cell_ready(self, row: int, _column: int) -> None:
        if row < 0 or row >= self.model.rowCount():
            return
        QTimer.singleShot(0, lambda current=row: self.table.setRowHeight(current, IMAGE_ROW_HEIGHT))

    def focus_search(self) -> None:
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def _current_changed(self, current, _previous) -> None:
        if not current.isValid() or current.data(ParquetTableModel.LoadingRole):
            return
        # 中文：单击任意单元格都会选中整行，状态栏仍保留实际点击列，既符合记录浏览习惯也不丢失字段定位信息。
        # English: Clicking any cell selects the whole record while the status bar keeps the actual clicked column, matching record browsing without losing field context.
        self.coordinate_changed.emit(self.model.source_row(current.row()) + 1, current.column() + 1)

    def _refresh_image_hover(self, *_args) -> None:
        self.hover_preview.refresh_from_cursor()

    def _selected_search_scope(self) -> str:
        scope = self.search_scope_combo.currentData()
        return str(scope) if scope in {"file", "page"} else "file"

    def _active_search_state(self) -> SearchState:
        return self._search_states[self._selected_search_scope()]

    def _search_scope_changed(self, _index: int) -> None:
        self.search_timer.stop()
        self._search_generation += 1
        self._cancel_search_workers()
        self._update_search_placeholder()
        # 中文：切换范围时立即重新激活对应搜索状态，避免文件结果和页内结果共用同一游标或高亮集合。
        # English: Switching scope immediately reactivates its own state so file and page results never share a cursor or highlight set.
        self._activate_search(auto_select=False)

    def _update_search(self) -> None:
        self._activate_search(auto_select=True)

    def _activate_search(self, auto_select: bool) -> None:
        query = self.search_edit.text().strip()
        scope = self._selected_search_scope()
        state = self._search_states[scope]
        self._search_generation += 1
        generation = self._search_generation
        self._cancel_search_workers()

        query_changed = state.query != query
        if query_changed:
            state.reset(query)
        elif scope == "page":
            # 中文：页内结果依赖当前页、过滤和可见顺序，即使查询文本不变也必须重新计算，不能复用上一页坐标。
            # English: Page results depend on the current page, filter, and visible order, so unchanged text must still be recalculated instead of reusing prior-page coordinates.
            state.reset(query)

        self.model.clear_search()
        if not query:
            state.reset()
            self._search_matches_changed(0)
            return

        if scope == "page":
            self._run_page_search(query, auto_select)
            return

        if state.complete and not query_changed:
            self._apply_active_search_results(auto_select=auto_select)
            return
        self._start_file_search(query, generation, auto_select)

    def _run_page_search(self, query: str, auto_select: bool) -> None:
        state = self._search_states["page"]
        state.query = query
        state.cursor = -1
        state.pending_coordinate = None
        if self.model.loading:
            state.matches.clear()
            state.complete = False
            self.search_previous_button.setEnabled(False)
            self.search_next_button.setEnabled(False)
            self.search_count_label.setText(self.translator.tr("data.page_search_waiting"))
            return

        # 中文：页内搜索只遍历当前模型的可见偏移，因此尊重当前页过滤，不会清除过滤或跳转到其他页面。
        # English: Page search scans only the model's visible offsets, so it respects the current-page filter and never clears it or navigates to another page.
        state.matches = self.model.find_page_matches(query)
        state.complete = True
        self._apply_active_search_results(auto_select=auto_select)

    def _start_file_search(self, query: str, generation: int, auto_select: bool) -> None:
        state = self._search_states["file"]
        state.query = query
        state.complete = False
        # 中文：文件级搜索在后台扫描全文件，并用请求代次而不是仅靠文本判断有效性，阻止同文本的过期线程覆盖页内搜索。
        # English: File search scans in the background and validates by request generation rather than text alone, preventing stale same-text workers from overwriting page search.
        worker = GlobalSearchWorker(self.document, query)
        thread = QThread(self)
        self._threads.append(thread)
        # 中文：是否在完成后定位首个结果属于发起搜索时的交互意图，必须随请求保存，避免异步完成后丢失该决定。
        # English: Whether completion should reveal the first result is interaction intent captured at request time, so it must travel with the asynchronous request.
        self._search_contexts[worker] = (generation, query, auto_select, thread)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(lambda current, total, active=worker: self._search_progress(active, current, total))
        worker.finished.connect(self._search_finished)
        worker.failed.connect(self._search_failed)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda current=thread: self._threads.remove(current) if current in self._threads else None)
        self.search_count_label.setText(self.translator.tr("data.searching", percent=0))
        thread.start()

    def _cancel_search_workers(self) -> None:
        for worker in list(self._search_contexts):
            worker.cancel()

    def _search_progress(self, worker: object, current: int, total: int) -> None:
        context = self._search_contexts.get(worker)
        if context is None:
            return
        generation, query, _auto_select, _thread = context
        state = self._search_states["file"]
        if (
            generation != self._search_generation
            or self._selected_search_scope() != "file"
            or state.query != query
        ):
            return
        percent = 0 if total <= 0 else min(100, round(current * 100 / total))
        self.search_count_label.setText(self.translator.tr("data.searching", percent=percent))

    def _search_finished(self, value: object) -> None:
        worker = self.sender()
        context = self._search_contexts.pop(worker, None)
        if context is None:
            return
        generation, query, auto_select, thread = context
        state = self._search_states["file"]
        if (
            generation == self._search_generation
            and self._selected_search_scope() == "file"
            and state.query == query
            and isinstance(value, list)
        ):
            state.matches = self.model.order_search_matches(list(value))
            state.complete = True
            state.cursor = -1
            state.pending_coordinate = None
            # 中文：没有当前页筛选时应立即把首个匹配显示在表格中；存在筛选时只定位当前可见匹配，避免搜索完成擅自改变用户视图。
            # English: Without a page filter the first match must be revealed immediately; with a filter only an already-visible match is selected so completion never changes the user's view.
            self._apply_active_search_results(auto_select=auto_select)
        thread.quit()

    def _search_failed(self, message: str) -> None:
        worker = self.sender()
        context = self._search_contexts.pop(worker, None)
        if context is None:
            return
        generation, query, _auto_select, thread = context
        state = self._search_states["file"]
        if (
            generation == self._search_generation
            and self._selected_search_scope() == "file"
            and state.query == query
        ):
            state.reset(query)
            self.model.clear_search()
            show_message(self, self.translator.tr("common.error"), message, critical=True)
        thread.quit()

    def _apply_active_search_results(self, auto_select: bool) -> None:
        state = self._active_search_state()
        self.model.set_search_results(state.query, state.matches)
        if not auto_select or not state.matches:
            self._search_matches_changed(len(state.matches))
            return

        if self._selected_search_scope() == "file":
            # 中文：优先选择当前表格中已经可见的匹配，既让搜索结果立即可见，也避免用户正在浏览含匹配页时被无意义地跳走。
            # English: Prefer a match already visible in the table so results appear immediately without needlessly moving the user away from a page that already contains one.
            if self._select_first_visible_file_match():
                return
            if self._page_filter_state.active:
                # 中文：当前页筛选有效时，文件搜索完成不能为显示结果而跨页；否则分页会改变筛选上下文并重现搜索与筛选冲突。
                # English: While a page filter is active, file-search completion cannot cross pages merely to reveal a result, because that would change filter context and recreate the conflict.
                self._search_matches_changed(len(state.matches))
                self.search_count_label.setText(
                    self.translator.tr("data.file_matches_hidden_by_filter", count=len(state.matches))
                )
                return

        state.cursor = -1
        self._select_search_match(1)

    def _select_first_visible_file_match(self) -> bool:
        state = self._search_states["file"]
        for cursor, (source_row, column) in enumerate(state.matches):
            if self.model.view_row_for_source(source_row) is None:
                continue
            # 中文：游标必须同步到全文件结果中的真实位置，后续“上一个/下一个”才能从当前显示结果继续，而不是重新从第一项开始。
            # English: The cursor must reflect the match's true position in the file-wide result set so previous/next continues from the displayed result instead of restarting.
            state.cursor = cursor
            state.pending_coordinate = None
            return self._select_source_coordinate(source_row, column)
        return False

    def _search_matches_changed(self, _count: int) -> None:
        scope = self._selected_search_scope()
        state = self._search_states[scope]
        count = len(state.matches)
        self.search_previous_button.setEnabled(count > 0)
        self.search_next_button.setEnabled(count > 0)
        if count and state.cursor >= 0:
            key = "data.file_match_position" if scope == "file" else "data.page_match_position"
            self.search_count_label.setText(
                self.translator.tr(key, current=state.cursor + 1, count=count)
            )
        else:
            key = "data.file_match_count" if scope == "file" else "data.page_match_count"
            self.search_count_label.setText(self.translator.tr(key, count=count))

    def _select_source_coordinate(self, source_row: int, column: int) -> bool:
        view_row = self.model.view_row_for_source(source_row)
        if view_row is None:
            state = self._active_search_state()
            state.pending_coordinate = None
            if self._selected_search_scope() == "file" and self._page_filter_state.active:
                # 中文：文件搜索与当前页筛选是正交状态；匹配被筛选隐藏时宁可提示用户，也不能静默清除筛选并恢复未筛选页面。
                # English: File search and page filtering are orthogonal state; when a match is hidden, the UI must inform the user rather than silently clearing the filter and restoring the unfiltered page.
                self.search_count_label.setText(
                    self.translator.tr("data.match_hidden_by_filter")
                )
            return False

        index = self.model.index(view_row, column)
        self._select_and_reveal_index(index)
        state = self._active_search_state()
        state.pending_coordinate = None
        self._search_matches_changed(len(state.matches))
        self._schedule_search_reveal(
            source_row,
            column,
            self._selected_search_scope(),
            state.query,
            self._search_generation,
        )
        return True

    def _select_and_reveal_index(self, index) -> None:
        if not index.isValid():
            return
        selection_model = self.table.selectionModel()
        if selection_model is not None:
            # 中文：仅设置 currentIndex 不保证整行真正进入选择模型；显式选择整行可让搜索定位在无焦点状态下仍有稳定的视觉反馈。
            # English: Setting only currentIndex does not guarantee that the row enters the selection model; explicitly selecting the row keeps search positioning visibly stable even while the search field owns focus.
            selection_model.setCurrentIndex(
                index, QItemSelectionModel.SelectionFlag.NoUpdate
            )
            selection_model.select(
                index,
                QItemSelectionModel.SelectionFlag.ClearAndSelect
                | QItemSelectionModel.SelectionFlag.Rows,
            )

        # 中文：先让 Qt 执行标准定位，再直接校正滚动条；后者可覆盖逐像素滚动和动态图片行高导致的同步 scrollTo 失效。
        # English: Qt performs its normal reveal first, then the scrollbars are corrected directly; the second step survives synchronous scrollTo being invalidated by per-pixel scrolling and dynamic image row heights.
        self.table.doItemsLayout()
        self.table.scrollTo(index, QTableView.ScrollHint.PositionAtCenter)
        viewport = self.table.viewport()
        row_top = self.table.rowViewportPosition(index.row())
        row_center = row_top + self.table.rowHeight(index.row()) // 2
        vertical_bar = self.table.verticalScrollBar()
        vertical_bar.setValue(
            vertical_bar.value() + row_center - viewport.height() // 2
        )

        header = self.table.horizontalHeader()
        column_left = header.sectionViewportPosition(index.column())
        column_width = header.sectionSize(index.column())
        column_right = column_left + column_width
        if column_left < 0 or column_right > viewport.width():
            horizontal_bar = self.table.horizontalScrollBar()
            horizontal_bar.setValue(
                horizontal_bar.value()
                + column_left
                - max(0, (viewport.width() - column_width) // 2)
            )
        viewport.update()

    def _schedule_search_reveal(
        self,
        source_row: int,
        column: int,
        scope: str,
        query: str,
        generation: int,
    ) -> None:
        # 中文：缩略图解码和行高更新会在后续事件循环发生，因此分阶段再次定位；每次都校验搜索代次，旧请求绝不会拉回当前视图。
        # English: Thumbnail decoding and row-height updates occur in later event-loop turns, so positioning is repeated in stages; every attempt validates the search generation so an old request can never pull the current view back.
        for delay in (0, 80, 240):
            QTimer.singleShot(
                delay,
                lambda row=source_row, col=column, active_scope=scope, active_query=query, request=generation: self._reveal_search_coordinate(
                    row, col, active_scope, active_query, request
                ),
            )

    def _reveal_search_coordinate(
        self,
        source_row: int,
        column: int,
        scope: str,
        query: str,
        generation: int,
    ) -> None:
        if (
            generation != self._search_generation
            or self._selected_search_scope() != scope
        ):
            return
        state = self._search_states[scope]
        if state.query != query or not state.matches:
            return
        if state.cursor < 0 or state.cursor >= len(state.matches):
            return
        if state.matches[state.cursor] != (source_row, column):
            return
        view_row = self.model.view_row_for_source(source_row)
        if view_row is None or self.model.loading:
            return
        self._select_and_reveal_index(self.model.index(view_row, column))

    def _select_search_match(self, direction: int) -> None:
        scope = self._selected_search_scope()
        state = self._search_states[scope]
        if not state.matches:
            return
        if state.cursor < 0:
            state.cursor = 0 if direction > 0 else len(state.matches) - 1
        else:
            state.cursor = (state.cursor + direction) % len(state.matches)
        source_row, column = state.matches[state.cursor]
        if scope == "file":
            target_page = self.model.page_index_for_source(source_row)
            if self.model.loading or target_page != self.model.page_index:
                state.pending_coordinate = (source_row, column)
                self.model.load_page(target_page)
                self._search_matches_changed(len(state.matches))
            else:
                self._select_source_coordinate(source_row, column)
        else:
            self._select_source_coordinate(source_row, column)

    def search_next(self) -> None:
        self._select_search_match(1)

    def search_previous(self) -> None:
        self._select_search_match(-1)

    def _request_file_sort(self, logical_column: int) -> None:
        if logical_column < 0 or logical_column >= self.model.columnCount():
            return
        if logical_column == self._sort_column:
            order = (
                Qt.SortOrder.DescendingOrder
                if self._sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            order = Qt.SortOrder.AscendingOrder
        self._sort_column = logical_column
        self._sort_order = order
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSortIndicator(logical_column, order)
        self.sort_clear_button.setEnabled(True)
        if self._active_sort_worker is not None:
            self._active_sort_worker.cancel()
        # 中文：表头点击启动的是全文件索引排序而非当前页排序，否则翻页后顺序会失去一致性。
        # English: A header click starts a whole-file index sort rather than a current-page sort, because page-only ordering would become inconsistent after navigation.
        worker = GlobalSortWorker(self.document, logical_column, order == Qt.SortOrder.DescendingOrder)
        self._active_sort_worker = worker
        self._start_worker(
            worker,
            self.translator.tr("progress.sorting_file"),
            lambda result, active_worker=worker: self._file_sort_finished(active_worker, result),
        )

    def _file_sort_finished(self, worker: object, result: object) -> None:
        if self._active_sort_worker is not worker:
            return
        self._active_sort_worker = None
        if not isinstance(result, tuple) or len(result) != 3:
            return
        column, descending, source_rows = result
        if column != self._sort_column or descending != (self._sort_order == Qt.SortOrder.DescendingOrder):
            return
        if isinstance(source_rows, list):
            self.model.set_row_order(source_rows)
            self._refresh_file_search_order()

    def clear_file_sort(self) -> None:
        if self._active_sort_worker is not None:
            self._active_sort_worker.cancel()
            self._active_sort_worker = None
        self._sort_column = -1
        self.table.horizontalHeader().setSortIndicatorShown(False)
        self.sort_clear_button.setEnabled(False)
        self.model.clear_row_order()
        self._refresh_file_search_order()

    def _refresh_file_search_order(self) -> None:
        state = self._search_states["file"]
        if not state.complete or not state.matches:
            return
        state.matches = self.model.order_search_matches(state.matches)
        state.cursor = -1
        state.pending_coordinate = None
        if self._selected_search_scope() == "file":
            self.model.set_search_results(state.query, state.matches)
            self._search_matches_changed(len(state.matches))

    def _apply_saved_page_filter(self) -> None:
        state = self._page_filter_state
        if not state.active or self.model.loading:
            return
        self.model.apply_filter(state.column, state.operator, state.query)

    def _restore_page_filter_after_load(self) -> None:
        if not self._page_filter_state.active:
            return
        # 中文：每次分页加载都会重建 Arrow 页面并清除模型偏移，因此必须从独立筛选状态重新应用，而不是依赖已经失效的旧偏移。
        # English: Every page load rebuilds the Arrow page and clears model offsets, so filtering must be reapplied from independent criteria instead of relying on stale offsets.
        self._apply_saved_page_filter()

    def apply_filter(self) -> None:
        query = self.filter_value_edit.text()
        if not query:
            self.clear_filter()
            return
        self._page_filter_state = PageFilterState(
            column=self.filter_column_combo.currentIndex(),
            operator=str(self.filter_operator_combo.currentData()),
            query=query,
            active=True,
        )
        self._apply_saved_page_filter()
        self._resize_rows()
        if self._selected_search_scope() == "page" and self.search_edit.text().strip():
            self._run_page_search(self.search_edit.text().strip(), auto_select=False)

    def clear_filter(self) -> None:
        self._page_filter_state.clear()
        self.filter_value_edit.clear()
        self.model.clear_filter()
        self._resize_rows()
        if self._selected_search_scope() == "page" and self.search_edit.text().strip():
            self._run_page_search(self.search_edit.text().strip(), auto_select=False)

    def open_record_detail(self, index) -> None:
        if not index.isValid() or index.data(ParquetTableModel.LoadingRole):
            return
        self.hover_preview.hide_preview()
        dialog = RecordDetailDialog(self.translator, self.model, index.row(), index.column())
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._detail_dialogs.add(dialog)
        dialog.finished.connect(lambda _result, active=dialog: self._detail_dialogs.discard(active))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _binary_index_for_row(self, row: int, preferred_column: int) -> object | None:
        preferred = self.model.index(row, preferred_column)
        if preferred.isValid() and preferred.data(ParquetTableModel.IsBinaryRole):
            data = preferred.data(ParquetTableModel.BinaryPayloadRole)
            if isinstance(data, bytes):
                return preferred
        for column in range(self.model.columnCount()):
            candidate = self.model.index(row, column)
            if not candidate.data(ParquetTableModel.IsBinaryRole):
                continue
            data = candidate.data(ParquetTableModel.BinaryPayloadRole)
            if isinstance(data, bytes):
                return candidate
        return None

    def show_context_menu(self, position) -> None:
        index = self.table.indexAt(position)
        if not index.isValid() or index.data(ParquetTableModel.LoadingRole):
            return
        self.table.setCurrentIndex(index)
        menu = RoundedMenu(self)
        open_detail = menu.addAction(self.translator.tr("context.open_detail"))
        menu.addSeparator()
        copy_cell = menu.addAction(self.translator.tr("context.copy_cell"))
        copy_row = menu.addAction(self.translator.tr("context.copy_row"))
        copy_column = menu.addAction(self.translator.tr("context.copy_page_column"))
        binary_index = self._binary_index_for_row(index.row(), index.column())
        view_raw = copy_base64 = export_binary = None
        if binary_index is not None:
            menu.addSeparator()
            view_raw = menu.addAction(self.translator.tr("context.view_raw_bytes"))
            copy_base64 = menu.addAction(self.translator.tr("context.copy_base64"))
            export_binary = menu.addAction(self.translator.tr("context.export_binary"))
        selected = menu.exec(self.table.viewport().mapToGlobal(position))
        clipboard = QGuiApplication.clipboard()
        if selected == open_detail:
            self.open_record_detail(index)
        elif selected == copy_cell:
            clipboard.setText(str(index.data(Qt.ItemDataRole.DisplayRole)))
        elif selected == copy_row:
            clipboard.setText(json.dumps(self.model.row_as_json(index.row()), ensure_ascii=False, indent=2))
        elif selected == copy_column:
            clipboard.setText(json.dumps(self.model.column_as_list(index.column()), ensure_ascii=False, indent=2))
        elif view_raw is not None and selected == view_raw:
            self.open_raw_bytes(binary_index)
        elif copy_base64 is not None and selected == copy_base64:
            data = binary_index.data(ParquetTableModel.BinaryPayloadRole) if binary_index is not None else None
            if isinstance(data, bytes):
                clipboard.setText(to_base64(data))
        elif export_binary is not None and selected == export_binary:
            self.export_binary_cell(binary_index)


    def open_raw_bytes(self, index) -> None:
        if not index.isValid() or not index.data(ParquetTableModel.IsBinaryRole):
            return
        data = index.data(ParquetTableModel.BinaryPayloadRole)
        if not isinstance(data, bytes):
            return
        label = self.translator.tr(
            "hex.cell_label",
            column=self.document.schema.names[index.column()],
            row=self.model.source_row(index.row()) + 1,
        )
        HexDialog(self.translator, data, label, self).exec()

    def export_binary_cell(self, index) -> None:
        raw_value = index.data(ParquetTableModel.RawValueRole)
        image = embedded_image_payload(raw_value)
        data = image.data if image is not None else embedded_binary_payload(raw_value)
        if data is None:
            return
        extension = image.image_format.extension if image is not None else "bin"
        source_row = self.model.source_row(index.row()) + 1
        suggested = embedded_file_name_hint(raw_value) or f"row_{source_row}.{extension}"
        if not Path(suggested).suffix:
            suggested = f"{suggested}.{extension}"
        target, _ = QFileDialog.getSaveFileName(self, self.translator.tr("context.export_binary"), suggested)
        if target:
            try:
                Path(target).write_bytes(data)
            except OSError as error:
                show_message(self, self.translator.tr("common.error"), str(error), critical=True)

    def extract_images(self) -> None:
        columns = [field.name for field in self.document.schema if contains_binary_type(field.type)]
        if not columns:
            show_message(self, self.translator.tr("common.information"), self.translator.tr("images.none_detected"))
            return
        column_name, accepted = select_item(
            self,
            self.translator.tr("images.select_column"),
            self.translator.tr("images.column"),
            columns,
            self.translator.tr("common.confirm"),
            self.translator.tr("common.cancel"),
        )
        if not accepted:
            return
        target = QFileDialog.getExistingDirectory(self, self.translator.tr("images.target_directory"))
        if not target:
            return
        worker = ImageExtractWorker(self.document, column_name, target)
        self._start_worker(
            worker,
            self.translator.tr("progress.extracting_images"),
            finished=lambda count: show_message(
                self,
                self.translator.tr("common.completed"),
                self.translator.tr("images.completed", count=count),
            ),
        )

    def _start_worker(self, worker, title: str, finished: Callable[[object], None]) -> None:
        thread = QThread(self)
        self._threads.append(thread)
        worker.moveToThread(thread)
        progress = QProgressDialog(title, self.translator.tr("common.cancel"), 0, self.document.total_rows, self)
        progress.setObjectName("TaskProgressDialog")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setAutoClose(False)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        self._worker_contexts[worker] = (progress, thread, finished)
        thread.started.connect(worker.run)
        progress.canceled.connect(worker.cancel, Qt.ConnectionType.DirectConnection)
        worker.progress.connect(self._worker_progress)
        worker.finished.connect(self._worker_finished)
        worker.failed.connect(self._worker_failed)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        thread.start()

    def _worker_progress(self, current: int, total: int) -> None:
        context = self._worker_contexts.get(self.sender())
        if context is None:
            return
        progress, _thread, _callback = context
        progress.setMaximum(max(total, 1))
        progress.setValue(current)

    def _worker_finished(self, value: object) -> None:
        worker = self.sender()
        context = self._worker_contexts.pop(worker, None)
        if context is None:
            return
        progress, thread, callback = context
        progress.close()
        callback(value)
        thread.quit()

    def _worker_failed(self, message: str) -> None:
        worker = self.sender()
        context = self._worker_contexts.pop(worker, None)
        if context is None:
            return
        progress, thread, _callback = context
        progress.close()
        if worker is self._active_sort_worker:
            self._active_sort_worker = None
        show_message(self, self.translator.tr("common.error"), message, critical=True)
        thread.quit()

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._search_generation += 1
        for dialog in tuple(self._detail_dialogs):
            dialog.close()
        self._detail_dialogs.clear()
        self.model.close()
        self._cancel_search_workers()
        for worker in list(self._worker_contexts):
            worker.cancel()
        for thread in list(self._threads):
            thread.quit()
            thread.wait(1000)
        self.document.close()

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)

    def _update_search_placeholder(self) -> None:
        key = "data.search_placeholder" if self._selected_search_scope() == "file" else "data.page_search_placeholder"
        self.search_edit.setPlaceholderText(self.translator.tr(key))

    def retranslate(self) -> None:
        self.header_eyebrow.setText(self.translator.tr("data.eyebrow"))
        self.header_title.setText(self.translator.tr("data.title"))
        current_scope = self._selected_search_scope()
        self.search_scope_combo.blockSignals(True)
        self.search_scope_combo.clear()
        self.search_scope_combo.addItem(self.translator.tr("data.search_scope_file"), "file")
        self.search_scope_combo.addItem(self.translator.tr("data.search_scope_page"), "page")
        scope_index = self.search_scope_combo.findData(current_scope)
        self.search_scope_combo.setCurrentIndex(max(0, scope_index))
        self.search_scope_combo.blockSignals(False)
        self._update_search_placeholder()
        self.search_previous_button.set_hint(self.translator.tr("common.previous"))
        self.search_next_button.set_hint(self.translator.tr("common.next"))
        self.search_clear_button.set_hint(self.translator.tr("common.clear"))
        self.filter_value_edit.setPlaceholderText(self.translator.tr("data.filter_value"))
        current_operator = self.filter_operator_combo.currentData()
        self.filter_operator_combo.clear()
        self.filter_operator_combo.addItem(self.translator.tr("data.contains"), "contains")
        self.filter_operator_combo.addItem(self.translator.tr("data.equals"), "equals")
        if current_operator is not None:
            index = self.filter_operator_combo.findData(current_operator)
            self.filter_operator_combo.setCurrentIndex(max(index, 0))
        self.filter_apply_button.setText(self.translator.tr("data.apply_filter"))
        self.filter_clear_button.setText(self.translator.tr("data.clear_filter"))
        self.sort_clear_button.setText(self.translator.tr("data.clear_file_sort"))
        self.extract_images_button.setText(self.translator.tr("data.extract_images"))
        self._search_matches_changed(len(self.model.search_matches))
