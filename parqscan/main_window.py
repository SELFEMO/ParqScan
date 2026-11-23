from __future__ import annotations

import os
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import psutil
from PySide6.QtCore import QByteArray, QSize, QTimer, Qt
from PySide6.QtGui import QAction, QActionGroup, QDragEnterEvent, QDropEvent, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
)

from parqscan.config import ConfigManager
from parqscan.constants import APP_NAME, MEMORY_STATUS_INTERVAL_MS
from parqscan.data.parquet_document import ParquetDocument
from parqscan.data.task_runner import BackgroundTaskRunner
from parqscan.data.workers import ExportWorker, FragmentExportWorker
from parqscan.dialogs.range_export_dialog import RangeExportDialog
from parqscan.i18n import Translator
from parqscan.release import release_name
from parqscan.themes import ThemeManager
from parqscan.update.controller import UpdateCheckResult, UpdateController
from parqscan.utils.binary import format_size
from parqscan.utils.icons import make_icon
from parqscan.widgets.design_system import ChoiceOption, EmptyState, RoundedComboBox, RoundedMenu, show_choice, show_message
from parqscan.widgets.document_widget import DocumentWidget


@dataclass
class DocumentContext:
    document: ParquetDocument
    widget: DocumentWidget
    list_item: QListWidgetItem
    opened_order: int


class MainWindow(QMainWindow):
    def __init__(
        self,
        config: ConfigManager,
        translator: Translator,
        theme_manager: ThemeManager,
        app_icon: QIcon,
        update_controller: UpdateController | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.translator = translator
        self.theme_manager = theme_manager
        self.app_icon = app_icon
        self.update_controller = update_controller
        self.contexts: list[DocumentContext] = []
        self._open_sequence = 0
        self._task_runner = BackgroundTaskRunner(self)
        self._update_progress: QProgressDialog | None = None
        self._update_check_progress: QProgressDialog | None = None
        self.setWindowIcon(app_icon)
        self.setAcceptDrops(True)
        self.resize(1380, 860)
        self.setMinimumSize(980, 640)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setMinimumWidth(238)
        self.sidebar.setMaximumWidth(286)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(16, 18, 16, 14)
        sidebar_layout.setSpacing(11)

        brand_row = QHBoxLayout()
        self.brand_mark = QLabel("PS")
        self.brand_mark.setObjectName("BrandMark")
        self.brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.brand_mark.setFixedSize(38, 38)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        self.brand_title = QLabel(APP_NAME)
        self.brand_title.setObjectName("BrandTitle")
        self.brand_subtitle = QLabel()
        self.brand_subtitle.setObjectName("MutedLabel")
        brand_text.addWidget(self.brand_title)
        brand_text.addWidget(self.brand_subtitle)
        brand_row.addWidget(self.brand_mark)
        brand_row.addLayout(brand_text)
        brand_row.addStretch(1)
        sidebar_layout.addLayout(brand_row)

        self.open_button = QPushButton()
        self.open_button.setProperty("primary", True)
        self.open_button.setIcon(make_icon("folder", "#FFFFFF"))
        self.open_button.setMinimumHeight(38)
        sidebar_layout.addWidget(self.open_button)

        files_header = QHBoxLayout()
        files_header.setSpacing(7)
        self.files_caption = QLabel()
        self.files_caption.setObjectName("EyebrowLabel")
        self.file_sort_combo = RoundedComboBox()
        self.file_sort_combo.setObjectName("FileSortCombo")
        self.file_sort_combo.setMinimumWidth(112)
        files_header.addWidget(self.files_caption, 1)
        files_header.addWidget(self.file_sort_combo)
        sidebar_layout.addLayout(files_header)
        self.file_list = QListWidget()
        self.file_list.setObjectName("FileList")
        self.file_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.file_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.file_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.file_list.setSpacing(2)
        # 中文：侧栏文件名只做中间省略并通过 Tooltip 保留完整路径，避免长文件名触发破坏布局的横向滚动条。
        # English: Sidebar filenames are elided in the middle while tooltips retain the full path, preventing long names from creating a layout-breaking horizontal scrollbar.
        sidebar_layout.addWidget(self.file_list, 1)
        self.close_file_button = QPushButton()
        self.close_file_button.setProperty("ghost", True)
        self.close_file_button.setVisible(False)
        sidebar_layout.addWidget(self.close_file_button)

        self.document_stack = QStackedWidget()
        self.welcome = EmptyState()
        self.document_stack.addWidget(self.welcome)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("MainSplitter")
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.document_stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setHandleWidth(1)
        splitter.setSizes([250, 1100])
        self.setCentralWidget(splitter)

        self.coordinate_status = QLabel()
        self.rows_status = QLabel()
        self.memory_status = QLabel()
        status = QStatusBar()
        status.setSizeGripEnabled(False)
        status.addWidget(self.coordinate_status)
        status.addPermanentWidget(self.rows_status)
        status.addPermanentWidget(self.memory_status)
        self.setStatusBar(status)

        self._create_menus()
        self.open_button.clicked.connect(self.open_file_dialog)
        self.close_file_button.clicked.connect(self.close_current_document)
        self.file_list.currentRowChanged.connect(self._switch_document)
        self.file_sort_combo.currentIndexChanged.connect(self._file_sort_changed)
        self.translator.language_changed.connect(self.retranslate)

        self.memory_timer = QTimer(self)
        self.memory_timer.setInterval(MEMORY_STATUS_INTERVAL_MS)
        self.memory_timer.timeout.connect(self._update_memory_status)
        self.memory_timer.start()
        self.retranslate()
        self._update_memory_status()

    def _create_menus(self) -> None:
        menu_bar = self.menuBar()

        def add_rounded_menu() -> RoundedMenu:
            menu = RoundedMenu(self)
            menu_bar.addMenu(menu)
            return menu

        self.file_menu = add_rounded_menu()
        self.open_action = QAction(self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self.open_file_dialog)
        self.recent_menu = RoundedMenu(self)
        self.close_action = QAction(self)
        self.close_action.setShortcut("Ctrl+W")
        self.close_action.triggered.connect(self.close_current_document)
        self.exit_action = QAction(self)
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.triggered.connect(self.close)
        self.file_menu.addAction(self.open_action)
        self.file_menu.addMenu(self.recent_menu)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.close_action)
        self.file_menu.addAction(self.exit_action)

        self.export_menu = add_rounded_menu()
        self.export_actions: dict[str, QAction] = {}
        for kind in ("csv", "json", "excel", "markdown", "sql"):
            action = QAction(self)
            action.triggered.connect(lambda checked=False, export_kind=kind: self.export_current(export_kind))
            self.export_actions[kind] = action
            self.export_menu.addAction(action)
        self.export_menu.addSeparator()
        self.fragment_action = QAction(self)
        self.fragment_action.triggered.connect(self.export_fragment)
        self.export_menu.addAction(self.fragment_action)

        self.view_menu = add_rounded_menu()
        self.search_action = QAction(self)
        self.search_action.setShortcut("Ctrl+F")
        self.search_action.triggered.connect(self.focus_search)
        self.view_menu.addAction(self.search_action)

        self.find_next_action = QAction(self)
        self.find_next_action.setShortcut("F3")
        self.find_next_action.triggered.connect(lambda: self._navigate_current_search(1))
        self.addAction(self.find_next_action)

        self.find_prev_action = QAction(self)
        self.find_prev_action.setShortcut("Shift+F3")
        self.find_prev_action.triggered.connect(lambda: self._navigate_current_search(-1))
        self.addAction(self.find_prev_action)

        self.tab_meta_action = QAction(self)
        self.tab_meta_action.setShortcut("Alt+1")
        self.tab_meta_action.triggered.connect(lambda: self._switch_current_tab(0))
        self.addAction(self.tab_meta_action)

        self.tab_data_action = QAction(self)
        self.tab_data_action.setShortcut("Alt+2")
        self.tab_data_action.triggered.connect(lambda: self._switch_current_tab(1))
        self.addAction(self.tab_data_action)
        self.view_menu.addSeparator()
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_actions: dict[str, QAction] = {}
        for theme in ("system", "light", "dark"):
            action = QAction(self, checkable=True)
            action.triggered.connect(lambda checked=False, name=theme: self.set_theme(name))
            self.theme_group.addAction(action)
            self.view_menu.addAction(action)
            self.theme_actions[theme] = action
        selected_theme = self.config.get("theme", "system")
        self.theme_actions.get(selected_theme, self.theme_actions["system"]).setChecked(True)

        self.language_menu = add_rounded_menu()
        self.language_group = QActionGroup(self)
        self.language_group.setExclusive(True)
        self.language_actions: dict[str, QAction] = {}
        for language in ("en", "zh"):
            action = QAction(self, checkable=True)
            action.triggered.connect(lambda checked=False, name=language: self.set_language(name))
            self.language_group.addAction(action)
            self.language_menu.addAction(action)
            self.language_actions[language] = action
        self.language_actions[self.translator.language].setChecked(True)

        self.help_menu = add_rounded_menu()
        self.check_updates_action = QAction(self)
        self.check_updates_action.triggered.connect(self.check_updates_manual)
        self.help_menu.addAction(self.check_updates_action)
        self.about_action = QAction(self)
        self.about_action.triggered.connect(self.show_about)
        self.help_menu.addAction(self.about_action)
        if self.update_controller is not None:
            self.update_controller.check_started.connect(self._on_update_check_started)
            self.update_controller.check_busy.connect(self._on_update_check_busy)
            self.update_controller.check_finished.connect(self._on_update_check_finished)
            self.update_controller.check_failed.connect(self._on_update_check_failed)
            self.update_controller.download_progress.connect(self._on_update_download_progress)
            self.update_controller.download_finished.connect(self._on_update_download_finished)
            self.update_controller.download_failed.connect(self._on_update_download_failed)
        self._rebuild_recent_menu()
        self.close_action.setEnabled(False)
        self.export_menu.setEnabled(False)

    def current_context(self) -> DocumentContext | None:
        row = self.file_list.currentRow()
        return self.contexts[row] if 0 <= row < len(self.contexts) else None

    def open_file_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, self.translator.tr("file.open"), "", "Parquet (*.parquet *.parq *.pq);;All files (*)")
        for path in paths:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        normalized = str(Path(path).expanduser().resolve())
        for index, context in enumerate(self.contexts):
            if context.document.path == normalized:
                self.file_list.setCurrentRow(index)
                return
        try:
            document = ParquetDocument(normalized)
            widget = DocumentWidget(document, self.translator, self.config)
        except Exception as error:
            show_message(
                self,
                self.translator.tr("common.error"),
                self.translator.tr("file.open_failed", error=str(error)),
                critical=True,
            )
            return

        item = QListWidgetItem(document.display_name)
        item.setToolTip(document.path)
        item.setSizeHint(QSize(0, max(36, self.file_list.fontMetrics().height() + 20)))
        self.file_list.addItem(item)
        self._open_sequence += 1
        context = DocumentContext(document, widget, item, self._open_sequence)
        self.contexts.append(context)
        self.document_stack.addWidget(widget)
        widget.coordinate_changed.connect(
            lambda r, c, w=widget: self._update_coordinate_status_for(w, r, c)
        )
        widget.loaded_rows_changed.connect(
            lambda loaded, w=widget: self._update_rows_status_for(w, loaded)
        )
        widget.status_message.connect(lambda msg: self.statusBar().showMessage(msg, 2500))
        self.config.add_recent_file(document.path)
        self._rebuild_recent_menu()
        self.close_action.setEnabled(False)
        self.export_menu.setEnabled(False)
        self._apply_file_list_sort(document.path)
        self.files_caption.setText(self.translator.tr("sidebar.open_files_count", count=len(self.contexts)))

    def _file_sort_changed(self) -> None:
        mode = self.file_sort_combo.currentData()
        if not isinstance(mode, str):
            return
        self.config.set("file_list_sort", mode)
        current = self.current_context()
        self._apply_file_list_sort(current.document.path if current is not None else None)

    def _apply_file_list_sort(self, selected_path: str | None = None) -> None:
        mode = self.config.file_list_sort()
        if mode == "name_asc":
            self.contexts.sort(key=lambda context: context.document.display_name.casefold())
        elif mode == "name_desc":
            self.contexts.sort(key=lambda context: context.document.display_name.casefold(), reverse=True)
        elif mode == "size_desc":
            self.contexts.sort(key=lambda context: context.document.file_size, reverse=True)
        else:
            self.contexts.sort(key=lambda context: context.opened_order)

        # 中文：侧栏排序必须同步重排上下文列表，否则可见文件名与右侧文档会错位。
        # English: Sidebar sorting must reorder the context list together with visible items, otherwise filenames and document pages become mismatched.
        self.file_list.blockSignals(True)
        while self.file_list.count():
            self.file_list.takeItem(0)
        selected_row = -1
        for row, context in enumerate(self.contexts):
            self.file_list.addItem(context.list_item)
            if context.document.path == selected_path:
                selected_row = row
        self.file_list.blockSignals(False)
        if selected_row >= 0:
            self.file_list.setCurrentRow(selected_row)
        elif self.contexts:
            self.file_list.setCurrentRow(0)
        else:
            self._switch_document(-1)

    def _switch_document(self, row: int) -> None:
        has_doc = 0 <= row < len(self.contexts)
        self.close_action.setEnabled(has_doc)
        self.export_menu.setEnabled(has_doc)
        if has_doc:
            context = self.contexts[row]
            self.document_stack.setCurrentWidget(context.widget)
            self.setWindowTitle(f"{APP_NAME} — {context.document.display_name}")
            self._update_rows_status(context.widget.loaded_rows)
            self.close_file_button.setVisible(True)
        else:
            self.document_stack.setCurrentWidget(self.welcome)
            self.setWindowTitle(APP_NAME)
            self._update_rows_status(0)
            self.coordinate_status.clear()
            self.close_file_button.setVisible(False)

    def close_current_document(self) -> None:
        row = self.file_list.currentRow()
        if row < 0 or row >= len(self.contexts):
            return
        context = self.contexts.pop(row)
        context.widget.shutdown()
        self.document_stack.removeWidget(context.widget)
        context.widget.deleteLater()
        self.file_list.takeItem(row)
        self.files_caption.setText(self.translator.tr("sidebar.open_files_count", count=len(self.contexts)))
        if self.contexts:
            self.file_list.setCurrentRow(min(row, len(self.contexts) - 1))
        else:
            self._switch_document(-1)

    def focus_search(self) -> None:
        context = self.current_context()
        if context is not None:
            context.widget.focus_search()

    def set_theme(self, theme: str) -> None:
        self.config.set("theme", theme)
        self.theme_manager.apply(theme)

    def set_language(self, language: str) -> None:
        self.config.set("language", language)
        self.translator.set_language(language)

    def export_current(self, export_kind: str) -> None:
        context = self.current_context()
        if context is None:
            return
        extensions = {"csv": "csv", "json": "json", "excel": "xlsx", "markdown": "md", "sql": "sql"}
        extension = extensions[export_kind]
        target, _ = QFileDialog.getSaveFileName(
            self,
            self.translator.tr("export.title"),
            f"{Path(context.document.path).stem}.{extension}",
        )
        if not target:
            return
        worker = ExportWorker(context.document, target, export_kind)
        self._run_worker(worker, self.translator.tr("progress.exporting"), self._export_finished)

    def export_fragment(self) -> None:
        context = self.current_context()
        if context is None:
            return
        dialog = RangeExportDialog(context.document, self.translator, self)
        if not dialog.exec():
            return
        start_row, end_row, columns = dialog.values()
        if not columns or end_row < start_row:
            return
        target, _ = QFileDialog.getSaveFileName(self, self.translator.tr("range.title"), "fragment.parquet", "Parquet (*.parquet)")
        if not target:
            return
        worker = FragmentExportWorker(context.document, target, start_row, end_row, columns)
        self._run_worker(worker, self.translator.tr("progress.exporting"), self._export_finished)

    def _run_worker(self, worker, title: str, callback: Callable[[object], None]) -> None:
        self._task_runner.start(
            worker,
            on_finished=callback,
            on_failed=lambda message: show_message(self, self.translator.tr("common.error"), message, critical=True),
            progress_title=title,
            cancel_label=self.translator.tr("common.cancel"),
        )

    def _navigate_current_search(self, direction: int) -> None:
        context = self.current_context()
        if context is None:
            return
        context.widget.tabs.setCurrentWidget(context.widget.data_widget)
        if direction >= 0:
            context.widget.data_widget.search_next()
        else:
            context.widget.data_widget.search_previous()

    def _switch_current_tab(self, index: int) -> None:
        context = self.current_context()
        if context is not None and 0 <= index < context.widget.tabs.count():
            context.widget.tabs.setCurrentIndex(index)

    def _export_finished(self, target: object) -> None:
        if target:
            show_message(
                self,
                self.translator.tr("common.completed"),
                self.translator.tr("export.completed", path=str(target)),
            )

    def _update_coordinate_status_for(self, widget: DocumentWidget, row: int, column: int) -> None:
        context = self.current_context()
        if context is None or context.widget is not widget:
            return
        self._update_coordinate_status(row, column)

    def _update_rows_status_for(self, widget: DocumentWidget, loaded: int) -> None:
        context = self.current_context()
        if context is None or context.widget is not widget:
            return
        self._update_rows_status(loaded)

    def _update_coordinate_status(self, row: int, column: int) -> None:
        self.coordinate_status.setText(self.translator.tr("status.coordinate", row=row, column=column))

    def _update_rows_status(self, loaded: int) -> None:
        context = self.current_context()
        total = context.document.total_rows if context is not None else 0
        self.rows_status.setText(self.translator.tr("status.page_rows", loaded=loaded, total=f"{total:,}"))

    def _update_memory_status(self) -> None:
        memory = psutil.Process(os.getpid()).memory_info().rss
        self.memory_status.setText(self.translator.tr("status.memory", memory=format_size(memory)))

    def _rebuild_recent_menu(self) -> None:
        self.recent_menu.clear()
        files = self.config.recent_files()
        if not files:
            action = self.recent_menu.addAction(self.translator.tr("file.no_recent"))
            action.setEnabled(False)
            return
        for path in files:
            action = self.recent_menu.addAction(Path(path).name)
            action.setToolTip(path)
            action.triggered.connect(lambda checked=False, recent_path=path: self.open_path(recent_path))

    def check_updates_manual(self) -> None:
        if self.update_controller is None:
            return
        self.update_controller.check_for_updates(manual=True)

    def _on_update_check_started(self, manual: bool) -> None:
        if not manual:
            return
        self._close_update_check_progress()
        progress = QProgressDialog(
            self.translator.tr("update.checking"),
            self.translator.tr("common.cancel"),
            0,
            0,
            self,
        )
        progress.setObjectName("TaskProgressDialog")
        progress.setWindowTitle(self.translator.tr("update.checking_title"))
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setRange(0, 0)
        progress.canceled.connect(self._cancel_update_check)
        progress.show()
        self._update_check_progress = progress

    def _cancel_update_check(self) -> None:
        if self.update_controller is not None:
            self.update_controller.cancel_check()
        self._close_update_check_progress()

    def _on_update_check_busy(self) -> None:
        if self._update_check_progress is None:
            self._on_update_check_started(True)

    def _close_update_check_progress(self) -> None:
        if self._update_check_progress is not None:
            self._update_check_progress.close()
            self._update_check_progress = None

    def _on_update_check_finished(self, result: object, manual: bool) -> None:
        self._close_update_check_progress()
        if result is None:
            if manual:
                show_message(
                    self,
                    self.translator.tr("update.up_to_date_title"),
                    self.translator.tr("update.up_to_date_text", release=release_name()),
                )
            return
        if not isinstance(result, UpdateCheckResult):
            return
        if not manual and self.update_controller is not None and self.update_controller.is_dismissed(result.release.version):
            return
        self._prompt_update(result)

    def _on_update_check_failed(self, message: str, manual: bool) -> None:
        self._close_update_check_progress()
        if not manual:
            return
        show_message(
            self,
            self.translator.tr("common.error"),
            self.translator.tr("update.check_failed", error=message),
            critical=True,
        )

    def _prompt_update(self, result: UpdateCheckResult) -> None:
        if self.update_controller is None:
            return
        self.update_controller.set_pending_release(result.release)
        detail = ""
        if not UpdateController.can_install_in_place() or not result.release.download_url:
            detail = self.translator.tr("update.non_windows_text")
        choice = show_choice(
            self,
            self.translator.tr("update.available_title"),
            self.translator.tr(
                "update.available_text",
                version=result.release.version,
                current=result.current_version,
            ),
            [
                ChoiceOption("release", self.translator.tr("update.open_release"), secondary=True),
                ChoiceOption("later", self.translator.tr("update.later"), secondary=True),
                ChoiceOption("install", self.translator.tr("update.install_now"), primary=True),
            ],
            detail=detail,
        )
        if choice == "later":
            self.update_controller.dismiss_version(result.release.version)
            return
        if choice == "release":
            webbrowser.open(result.release.release_page_url or UpdateController.releases_page_url())
            return
        if choice != "install":
            return
        if UpdateController.can_install_in_place() and result.release.download_url:
            self._start_update_download(result.release)
            return
        webbrowser.open(result.release.release_page_url or UpdateController.releases_page_url())

    def _start_update_download(self, release) -> None:
        if self.update_controller is None:
            return
        progress = QProgressDialog(self.translator.tr("update.downloading"), "", 0, 100, self)
        progress.setObjectName("TaskProgressDialog")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.setAutoClose(False)
        progress.show()
        self._update_progress = progress
        self.update_controller.download_and_install(release)

    def _on_update_download_progress(self, downloaded: int, total: int) -> None:
        if self._update_progress is None:
            return
        self._update_progress.setMaximum(max(total, 1))
        self._update_progress.setValue(min(downloaded, total if total > 0 else downloaded))

    def _on_update_download_finished(self, installer_path: str) -> None:
        if self._update_progress is not None:
            self._update_progress.close()
            self._update_progress = None
        show_message(self, self.translator.tr("update.available_title"), self.translator.tr("update.installing"))
        UpdateController.launch_installer(installer_path)
        QApplication.instance().quit()

    def _on_update_download_failed(self, message: str) -> None:
        if self._update_progress is not None:
            self._update_progress.close()
            self._update_progress = None
        error_text = message
        if message == "missing_download_url":
            error_text = self.translator.tr("update.non_windows_text")
        show_message(
            self,
            self.translator.tr("common.error"),
            self.translator.tr("update.download_failed", error=error_text),
            critical=True,
        )

    def show_about(self) -> None:
        # 中文：关于窗口应展示项目自身 Logo，避免通用信息或警告图标削弱品牌识别。
        # English: The About dialog uses the product logo so generic information or warning symbols never replace the application identity.
        show_message(
            self,
            self.translator.tr("about.title"),
            self.translator.tr("about.text", release=release_name()),
            icon=self.app_icon,
        )

    def retranslate(self) -> None:
        self.brand_subtitle.setText(self.translator.tr("app.subtitle"))
        self.open_button.setText(self.translator.tr("file.open"))
        self.files_caption.setText(
            self.translator.tr("sidebar.open_files_count", count=len(self.contexts))
        )
        current_sort = self.config.file_list_sort()
        self.file_sort_combo.blockSignals(True)
        self.file_sort_combo.clear()
        for key in ("opened", "name_asc", "name_desc", "size_desc"):
            self.file_sort_combo.addItem(self.translator.tr(f"sidebar.sort_{key}"), key)
        self.file_sort_combo.setCurrentIndex(max(0, self.file_sort_combo.findData(current_sort)))
        self.file_sort_combo.blockSignals(False)
        self.close_file_button.setText(self.translator.tr("file.close"))
        self.welcome.title_label.setText(self.translator.tr("welcome.title"))
        self.welcome.description_label.setText(self.translator.tr("welcome.description"))

        self.file_menu.setTitle(self.translator.tr("menu.file"))
        self.open_action.setText(self.translator.tr("file.open"))
        self.recent_menu.setTitle(self.translator.tr("file.recent"))
        self.close_action.setText(self.translator.tr("file.close"))
        self.exit_action.setText(self.translator.tr("file.exit"))
        self.export_menu.setTitle(self.translator.tr("menu.export"))
        for kind, action in self.export_actions.items():
            action.setText(self.translator.tr(f"export.{kind}"))
        self.fragment_action.setText(self.translator.tr("export.fragment"))
        self.view_menu.setTitle(self.translator.tr("menu.view"))
        self.search_action.setText(self.translator.tr("data.focus_search"))
        for theme, action in self.theme_actions.items():
            action.setText(self.translator.tr(f"theme.{theme}"))
        self.language_menu.setTitle(self.translator.tr("menu.language"))
        self.language_actions["en"].setText("English")
        self.language_actions["zh"].setText("中文")
        self.help_menu.setTitle(self.translator.tr("menu.help"))
        self.check_updates_action.setText(self.translator.tr("update.check"))
        self.about_action.setText(self.translator.tr("about.title"))
        self.coordinate_status.setText(self.translator.tr("status.no_selection"))
        self._update_rows_status(self.current_context().widget.data_widget.model.loaded_rows if self.current_context() else 0)
        self._update_memory_status()
        self._rebuild_recent_menu()
        self.close_action.setEnabled(False)
        self.export_menu.setEnabled(False)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() and any(url.toLocalFile().lower().endswith((".parquet", ".parq", ".pq")) for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".parquet", ".parq", ".pq")):
                self.open_path(path)
        event.acceptProposedAction()

    def closeEvent(self, event) -> None:
        for context in self.contexts:
            context.widget.shutdown()
        self._task_runner.shutdown()
        encoded = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self.config.set_window_geometry("main_window", encoded)
        super().closeEvent(event)
