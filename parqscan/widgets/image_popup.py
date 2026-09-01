from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QObject, QPersistentModelIndex, QPoint, QTimer, Qt
from PySide6.QtGui import QCursor, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from parqscan.constants import IMAGE_HOVER_SIZE, THUMBNAIL_SIZE
from parqscan.i18n import Translator
from parqscan.models.parquet_table_model import ParquetTableModel
from parqscan.utils.icons import make_icon
from parqscan.widgets.design_system import CardFrame, ZoomableImageView, _apply_rounded_mask


class ImageHoverPreview(QObject):
    def __init__(self, table: QTableView, model: ParquetTableModel) -> None:
        super().__init__(table)
        self.table = table
        self.model = model
        self.popup = QFrame(
            None,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.popup.setObjectName("ImageHoverCard")
        self.popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.popup.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.popup.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.image_label = QLabel()
        self.image_label.setObjectName("ImageHoverPreview")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption_label = QLabel()
        self.caption_label.setObjectName("ImageHoverCaption")
        self.caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self.popup)
        layout.setContentsMargins(10, 10, 10, 9)
        layout.setSpacing(7)
        layout.addWidget(self.image_label)
        layout.addWidget(self.caption_label)
        self._last_index: tuple[int, int] | None = None
        self._filtered_window: QWidget | None = None
        viewport = table.viewport()
        viewport.setMouseTracking(True)
        viewport.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        viewport.installEventFilter(self)
        self._ensure_window_filter()

    def hide_preview(self) -> None:
        self.popup.hide()
        self._last_index = None

    def refresh_from_cursor(self) -> None:
        self._update_from_point(self.table.viewport().mapFromGlobal(QCursor.pos()))

    def _ensure_window_filter(self) -> None:
        host = self.table.window()
        if host is None or host is self._filtered_window:
            return
        if self._filtered_window is not None:
            self._filtered_window.removeEventFilter(self)
        self._filtered_window = host
        host.installEventFilter(self)

    def _host_is_active(self) -> bool:
        host = self.table.window()
        active = QApplication.activeWindow()
        return host is not None and active is host

    def eventFilter(self, watched, event) -> bool:
        self._ensure_window_filter()
        viewport = self.table.viewport()
        if watched is self._filtered_window and event.type() in {QEvent.Type.WindowDeactivate, QEvent.Type.Hide}:
            self.hide_preview()
            return super().eventFilter(watched, event)
        if watched is not viewport:
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.MouseButtonDblClick:
            self.hide_preview()
        elif event.type() in {QEvent.Type.HoverEnter, QEvent.Type.HoverMove, QEvent.Type.MouseMove}:
            local = event.position().toPoint() if hasattr(event, "position") else viewport.mapFromGlobal(QCursor.pos())
            self._update_from_point(local)
        elif event.type() == QEvent.Type.Hide:
            self.hide_preview()
        elif event.type() in {QEvent.Type.Leave, QEvent.Type.HoverLeave}:
            local = viewport.mapFromGlobal(QCursor.pos())
            # 中文：预览窗出现时 viewport 可能收到假 Leave；若指针仍在同一图片格则保持卡片。
            # English: Showing the preview can emit a false Leave; keep the card if the cursor is still on the same image cell.
            if self._image_index_at(local) is None:
                self.hide_preview()
        return super().eventFilter(watched, event)

    def _image_index_at(self, local: QPoint):
        viewport = self.table.viewport()
        if not viewport.rect().contains(local):
            return None
        index = self.table.indexAt(local)
        if index.isValid() and index.data(ParquetTableModel.IsImageRole):
            return index
        return None

    def _update_from_point(self, local: QPoint) -> None:
        if not self._host_is_active():
            self.hide_preview()
            return
        index = self._image_index_at(local)
        if index is None:
            self.hide_preview()
            return
        key = (self.model.source_row(index.row()), index.column())
        if key != self._last_index:
            thumbnail = self.model.image_pixmap(index, THUMBNAIL_SIZE)
            hover = None if thumbnail is not None else self.model.image_pixmap(index, IMAGE_HOVER_SIZE)
            pixmap = hover or thumbnail
            if pixmap is None:
                self.hide_preview()
                return
            self.image_label.setPixmap(pixmap)
            self.caption_label.setText(
                f"{self.model.document.schema.names[index.column()]} · "
                f"{self.model.source_row(index.row()) + 1}"
            )
            self.popup.adjustSize()
            self._last_index = key
            if hover is None:
                self._schedule_hover_upgrade(index, key)
        self._place_popup(local)
        self.popup.show()

    def _schedule_hover_upgrade(self, index, key: tuple[int, int]) -> None:
        persistent = QPersistentModelIndex(index)
        QTimer.singleShot(0, lambda: self._upgrade_hover_pixmap(persistent, key))

    def _upgrade_hover_pixmap(self, index: QPersistentModelIndex, key: tuple[int, int]) -> None:
        if key != self._last_index or not index.isValid():
            return
        hover = self.model.image_pixmap(QModelIndex(index), IMAGE_HOVER_SIZE)
        if hover is None:
            return
        self.image_label.setPixmap(hover)
        self.popup.adjustSize()
        self._place_popup(self.table.viewport().mapFromGlobal(QCursor.pos()))

    def _place_popup(self, local: QPoint) -> None:
        global_point = self.table.viewport().mapToGlobal(local + QPoint(18, 18))
        screen = self.table.screen().availableGeometry() if self.table.screen() is not None else self.table.rect()
        x = min(global_point.x(), screen.right() - self.popup.width() - 8)
        y = min(global_point.y(), screen.bottom() - self.popup.height() - 8)
        self.popup.move(max(screen.left() + 8, x), max(screen.top() + 8, y))
        _apply_rounded_mask(self.popup, 12)


class ImagePreviewDialog(QDialog):
    def __init__(
        self,
        translator: Translator,
        image: QImage,
        label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.translator = translator
        self._label_text = label
        self.setObjectName("DetailDialog")

        header = CardFrame(object_name="DialogHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 14, 18, 14)
        self.info_label = QLabel(label)
        self.info_label.setObjectName("DialogTitle")
        header_layout.addWidget(self.info_label)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(7)
        controls.addStretch(1)
        self.zoom_out_button = QPushButton()
        self.zoom_out_button.setProperty("secondary", True)
        self.zoom_out_button.setIcon(make_icon("zoom_out", "#0F6FDB"))
        self.zoom_level_label = QLabel("100%")
        self.zoom_level_label.setObjectName("Chip")
        self.zoom_level_label.setMinimumWidth(54)
        self.zoom_level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_in_button = QPushButton()
        self.zoom_in_button.setProperty("secondary", True)
        self.zoom_in_button.setIcon(make_icon("zoom_in", "#0F6FDB"))
        self.reset_view_button = QPushButton()
        self.reset_view_button.setProperty("secondary", True)
        self.reset_view_button.setIcon(make_icon("reset_view", "#0F6FDB"))
        controls.addWidget(self.zoom_out_button)
        controls.addWidget(self.zoom_level_label)
        controls.addWidget(self.zoom_in_button)
        controls.addWidget(self.reset_view_button)

        self.image_view = ZoomableImageView()
        self.image_view.set_source_image(image)
        self.zoom_out_button.clicked.connect(self.image_view.zoom_out)
        self.zoom_in_button.clicked.connect(self.image_view.zoom_in)
        self.reset_view_button.clicked.connect(self.image_view.reset_view)
        self.image_view.zoom_changed.connect(lambda percent: self.zoom_level_label.setText(f"{percent}%"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addLayout(controls)
        layout.addWidget(self.image_view, 1)
        self.resize(980, 720)
        self.translator.language_changed.connect(self.retranslate)
        self.retranslate()

    def retranslate(self) -> None:
        self.setWindowTitle(self.translator.tr("images.preview_title"))
        self.info_label.setText(self._label_text)
        self.zoom_out_button.setText(self.translator.tr("detail.zoom_out"))
        self.zoom_in_button.setText(self.translator.tr("detail.zoom_in"))
        self.reset_view_button.setText(self.translator.tr("detail.reset_view"))
