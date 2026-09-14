from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, QTimer, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QGuiApplication,
    QKeySequence,
    QPainter,
    QPalette,
    QPen,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from parqscan.dialogs.hex_dialog import HexPreviewWidget
from parqscan.i18n import Translator
from parqscan.models.parquet_table_model import ParquetTableModel
from parqscan.utils.binary import (
    contains_binary_type,
    embedded_binary_payload,
    embedded_file_name_hint,
    embedded_image_payload,
    format_size,
    to_base64,
)
from parqscan.utils.icons import make_icon
from parqscan.utils.qt_images import decode_image_bytes
from parqscan.utils.serialization import json_safe, pretty_text
from parqscan.widgets.design_system import (
    CardFrame,
    ElidingLabel,
    SearchField,
    ZoomableImageView,
    _apply_rounded_mask,
    show_message,
)


MAX_SELECTION_HIGHLIGHTS = 5000
DETAIL_PANE_MIN_WIDTH = 280
DETAIL_PANE_MIN_HEIGHT = 220
DETAIL_DOCK_TITLE_HEIGHT = 30
DETAIL_TILE_CORNER_RADIUS = 10
DETAIL_TILE_BORDER_WIDTH = 2
MAX_DETAIL_SEARCH_MATCHES = 5000


@dataclass(frozen=True)
class DetailSearchMatch:
    editor: QPlainTextEdit
    start: int
    end: int


class DockGripWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DetailDockGrip")
        self.setFixedSize(24, 30)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#718096"))
        center_y = self.height() // 2
        for center_x in (6, 12, 18):
            painter.drawEllipse(QPoint(center_x, center_y), 1, 1)


class DockTitleBar(QFrame):
    def __init__(self, owner: object, widget: QWidget, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._owner = owner
        self._widget = widget
        self._press_position: QPoint | None = None
        self._dragging = False
        self.setObjectName("DetailDockTitle")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(30)
        self.setMaximumHeight(30)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(8)
        self._title_label = QLabel(title)
        self._title_label.setObjectName("DetailDockTitleLabel")
        self._grip_label = DockGripWidget(self)
        self._title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._title_label, 1)
        layout.addWidget(self._grip_label)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._press_position = event.globalPosition().toPoint()
        self._dragging = False
        self.grabMouse()
        event.accept()

    def _update_drag_position(self, current: QPoint) -> None:
        if self._press_position is None:
            return
        if not self._dragging and (current - self._press_position).manhattanLength() >= QApplication.startDragDistance():
            self._dragging = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._owner._begin_preview_drag(self._widget, current, self._press_position)
        if self._dragging:
            self._owner._update_preview_drag(self._widget, current)

    def mouseMoveEvent(self, event) -> None:
        if self._press_position is None or not event.buttons() & Qt.MouseButton.LeftButton:
            super().mouseMoveEvent(event)
            return
        self._update_drag_position(event.globalPosition().toPoint())
        event.accept()

    def _finish_drag(self, current: QPoint) -> None:
        dragging = self._dragging
        start_position = self._press_position
        self.releaseMouse()
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._press_position = None
        self._dragging = False
        if dragging:
            self._owner._finish_preview_drag(self._widget, current, start_position)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._finish_drag(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseReleaseEvent(event)


class TileResizeHandle(QWidget):
    def __init__(self, owner: object, widget: QWidget, direction: str, parent: QWidget) -> None:
        super().__init__(parent)
        self._owner = owner
        self._widget = widget
        self._direction = direction
        self._press_position: QPoint | None = None
        self.setObjectName("DetailResizeHandle")
        self.setCursor(self._cursor_for_direction(direction))

    @staticmethod
    def _cursor_for_direction(direction: str) -> Qt.CursorShape:
        return {
            "top-left": Qt.CursorShape.SizeFDiagCursor,
            "top": Qt.CursorShape.SizeVerCursor,
            "top-right": Qt.CursorShape.SizeBDiagCursor,
            "right": Qt.CursorShape.SizeHorCursor,
            "bottom-right": Qt.CursorShape.SizeFDiagCursor,
            "bottom": Qt.CursorShape.SizeVerCursor,
            "bottom-left": Qt.CursorShape.SizeBDiagCursor,
            "left": Qt.CursorShape.SizeHorCursor,
        }[direction]

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._press_position = event.globalPosition().toPoint()
        self.grabMouse()
        self._owner._begin_preview_resize(self._widget, self._direction, self._press_position)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._press_position is not None:
            self._owner._update_preview_resize(self._widget, self._direction, event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._press_position is not None:
            self.releaseMouse()
            self._owner._finish_preview_resize(self._widget, self._direction, event.globalPosition().toPoint())
            self._press_position = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


class PreviewTile(QFrame):
    """An in-dialog preview tile; it never becomes a native top-level window."""

    def __init__(self, owner: object, widget: QWidget, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._widget: QWidget | None = widget
        self._title = title
        self._title_bar = DockTitleBar(owner, widget, title, self)
        self.setObjectName("DetailPreviewTile")
        self.setProperty("detailDock", True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLineWidth(0)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._resize_handles = {
            direction: TileResizeHandle(owner, widget, direction, self)
            for direction in (
                "top-left",
                "top",
                "top-right",
                "right",
                "bottom-right",
                "bottom",
                "bottom-left",
                "left",
            )
        }
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._title_bar, 0)
        layout.addWidget(widget, 1)
        widget.show()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        # 中文：QSS 的 border 按矩形描边，圆角 mask 裁切后会留下一条直角灰框；边框改在圆角路径上绘制。
        # English: QSS borders are stroked as rectangles, so a rounded mask leaves a square gray frame; the outline is painted on the rounded path instead.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        inset = DETAIL_TILE_BORDER_WIDTH / 2
        rect = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        radius = max(0.0, DETAIL_TILE_CORNER_RADIUS - inset)
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.WindowText), DETAIL_TILE_BORDER_WIDTH))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        handle_size = 9
        width = self.width()
        height = self.height()
        center_width = max(0, width - 2 * handle_size)
        center_height = max(0, height - 2 * handle_size)
        geometries = {
            "top-left": QRect(0, 0, handle_size, handle_size),
            "top": QRect(handle_size, 0, center_width, handle_size),
            "top-right": QRect(width - handle_size, 0, handle_size, handle_size),
            "right": QRect(width - handle_size, handle_size, handle_size, center_height),
            "bottom-right": QRect(width - handle_size, height - handle_size, handle_size, handle_size),
            "bottom": QRect(handle_size, height - handle_size, center_width, handle_size),
            "bottom-left": QRect(0, height - handle_size, handle_size, handle_size),
            "left": QRect(0, handle_size, handle_size, center_height),
        }
        for direction, handle in self._resize_handles.items():
            handle.setGeometry(geometries[direction])
            handle.raise_()
        _apply_rounded_mask(self, DETAIL_TILE_CORNER_RADIUS)

    def widget(self) -> QWidget | None:
        return self._widget

    def titleBarWidget(self) -> DockTitleBar:
        return self._title_bar

    def setWindowTitle(self, title: str) -> None:
        self._title = title
        self._title_bar.set_title(title)

    def windowTitle(self) -> str:
        return self._title

    def take_widget(self) -> QWidget | None:
        widget = self._widget
        if widget is None:
            return None
        widget.hide()
        widget.setParent(None)
        self._widget = None
        return widget


class AdaptivePreviewGrid(QWidget):
    """A free-form canvas whose preview tiles can be moved and resized independently."""

    NEW_TILE_ORIGIN = QPoint(0, 0)
    CANVAS_MARGIN = 24
    DEFAULT_TILE_SIZE = QSize(480, 340)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._widgets: list[QWidget] = []
        self._docks: dict[QWidget, PreviewTile] = {}
        self._positions: dict[str, QPoint] = {}
        self._sizes: dict[str, QSize] = {}
        self._drag_widget: QWidget | None = None
        self._drag_offset = QPoint()
        self._resize_widget: QWidget | None = None
        self._resize_direction = ""
        self._resize_start_position = QPoint()
        self._resize_start_rect = QRect()
        self.setObjectName("DetailPreviewGrid")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._update_canvas_size()

    @staticmethod
    def _widget_id(widget: QWidget) -> str:
        return str(widget.property("dock_id") or id(widget))

    def preview_position(self, widget: QWidget) -> QPoint:
        tile = self._docks.get(widget)
        if tile is not None:
            return tile.pos()
        return QPoint(self._positions.get(self._widget_id(widget), self.NEW_TILE_ORIGIN))

    def move_preview(self, widget: QWidget, position: QPoint) -> None:
        tile = self._docks.get(widget)
        if tile is None:
            return
        clamped = QPoint(max(0, position.x()), max(0, position.y()))
        tile.move(clamped)
        self._positions[self._widget_id(widget)] = clamped
        self._update_canvas_size()

    def tile_for(self, widget: QWidget) -> PreviewTile | None:
        return self._docks.get(widget)

    def _tile_rect(self, widget: QWidget) -> QRect:
        widget_id = self._widget_id(widget)
        position = self._positions.get(widget_id, QPoint(self.NEW_TILE_ORIGIN))
        size = self._sizes.get(widget_id, QSize(self.DEFAULT_TILE_SIZE))
        return QRect(position, size)

    def _update_canvas_size(self) -> None:
        right = self.DEFAULT_TILE_SIZE.width() + self.CANVAS_MARGIN
        bottom = self.DEFAULT_TILE_SIZE.height() + self.CANVAS_MARGIN
        for widget in self._widgets:
            tile = self._docks.get(widget)
            rect = tile.geometry() if tile is not None else self._tile_rect(widget)
            right = max(right, rect.right() + self.CANVAS_MARGIN + 1)
            bottom = max(bottom, rect.bottom() + self.CANVAS_MARGIN + 1)
        self.setMinimumSize(right, bottom)
        if self.width() < right or self.height() < bottom:
            self.resize(max(self.width(), right), max(self.height(), bottom))
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:
        return QSize(self.minimumWidth(), self.minimumHeight())

    def update_preview_title(self, widget: QWidget, title: str) -> None:
        tile = self._docks.get(widget)
        if tile is not None:
            tile.setWindowTitle(title)

    def reveal_preview(self, widget: QWidget) -> None:
        tile = self._docks.get(widget)
        if tile is not None:
            tile.show()
            tile.raise_()

    def add_preview(self, widget: QWidget) -> None:
        if widget in self._widgets:
            return
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        widget.setMinimumSize(DETAIL_PANE_MIN_WIDTH, DETAIL_PANE_MIN_HEIGHT)
        widget_id = self._widget_id(widget)
        size = QSize(self._sizes.get(widget_id, self.DEFAULT_TILE_SIZE))
        if size.width() < DETAIL_PANE_MIN_WIDTH or size.height() < DETAIL_PANE_MIN_HEIGHT:
            size = QSize(self.DEFAULT_TILE_SIZE)
        self._sizes[widget_id] = size
        self._positions[widget_id] = QPoint(self.NEW_TILE_ORIGIN)
        self._widgets.append(widget)
        title = str(widget.property("dock_title") or "")
        tile = PreviewTile(self, widget, title, self)
        tile.setMinimumSize(DETAIL_PANE_MIN_WIDTH, DETAIL_PANE_MIN_HEIGHT + DETAIL_DOCK_TITLE_HEIGHT)
        tile.setGeometry(QRect(self._positions[widget_id], size))
        self._docks[widget] = tile
        tile.show()
        tile.raise_()
        self._update_canvas_size()

    def remove_preview(self, widget: QWidget) -> None:
        if widget not in self._widgets:
            return
        widget_id = self._widget_id(widget)
        self._widgets.remove(widget)
        self._positions.pop(widget_id, None)
        tile = self._docks.pop(widget, None)
        if tile is not None:
            tile.hide()
            tile.take_widget()
            tile.deleteLater()
        self._update_canvas_size()

    def _begin_preview_drag(
        self,
        widget: QWidget,
        global_position: QPoint,
        start_position: QPoint | None = None,
    ) -> None:
        tile = self._docks.get(widget)
        if tile is None:
            return
        self._drag_widget = widget
        self._drag_offset = tile.mapFromGlobal(start_position or global_position)
        tile.raise_()

    def _update_preview_drag(self, widget: QWidget, global_position: QPoint) -> None:
        if self._drag_widget is not widget:
            return
        tile = self._docks.get(widget)
        if tile is None:
            return
        position = self.mapFromGlobal(global_position) - self._drag_offset
        position.setX(max(0, position.x()))
        position.setY(max(0, position.y()))
        tile.move(position)
        self._positions[self._widget_id(widget)] = position
        self._update_canvas_size()

    def _finish_preview_drag(
        self,
        widget: QWidget,
        global_position: QPoint,
        start_position: QPoint | None = None,
    ) -> None:
        del start_position
        self._update_preview_drag(widget, global_position)
        if self._drag_widget is widget:
            self._drag_widget = None

    def _begin_preview_resize(self, widget: QWidget, direction: str, global_position: QPoint) -> None:
        tile = self._docks.get(widget)
        if tile is None:
            return
        self._resize_widget = widget
        self._resize_direction = direction
        self._resize_start_position = global_position
        self._resize_start_rect = tile.geometry()
        tile.raise_()

    def _update_preview_resize(self, widget: QWidget, direction: str, global_position: QPoint) -> None:
        if self._resize_widget is not widget or direction != self._resize_direction:
            return
        tile = self._docks.get(widget)
        if tile is None:
            return
        delta = global_position - self._resize_start_position
        rect = QRect(self._resize_start_rect)
        minimum_width = DETAIL_PANE_MIN_WIDTH
        minimum_height = DETAIL_PANE_MIN_HEIGHT + DETAIL_DOCK_TITLE_HEIGHT
        left = rect.left()
        right = rect.right()
        top = rect.top()
        bottom = rect.bottom()
        if "left" in direction:
            left = min(max(0, rect.left() + delta.x()), rect.right() - minimum_width + 1)
        if "right" in direction:
            right = max(rect.left() + minimum_width - 1, rect.right() + delta.x())
        if "top" in direction:
            top = min(max(0, rect.top() + delta.y()), rect.bottom() - minimum_height + 1)
        if "bottom" in direction:
            bottom = max(rect.top() + minimum_height - 1, rect.bottom() + delta.y())
        rect = QRect(left, top, right - left + 1, bottom - top + 1)
        tile.setGeometry(rect)
        widget_id = self._widget_id(widget)
        self._positions[widget_id] = rect.topLeft()
        self._sizes[widget_id] = rect.size()
        self._update_canvas_size()

    def _finish_preview_resize(self, widget: QWidget, direction: str, global_position: QPoint) -> None:
        self._update_preview_resize(widget, direction, global_position)
        if self._resize_widget is widget:
            self._resize_widget = None
            self._resize_direction = ""


class FieldPreviewPane(CardFrame):
    def __init__(
        self,
        translator: Translator,
        field,
        column: int,
        value: object,
        source_row: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, "DetailPreviewCard")
        self.translator = translator
        self.column = column
        self._value = value
        self._source_row = source_row
        self._field_name = field.name
        self._field_type = field.type
        self.setMinimumSize(DETAIL_PANE_MIN_WIDTH, DETAIL_PANE_MIN_HEIGHT)
        self.setProperty("dock_id", f"field-{column}")
        self.setProperty("dock_title", field.name)

        metadata_layout = QHBoxLayout()
        metadata_layout.setSpacing(7)
        self.field_name_label = ElidingLabel(field.name, mode=Qt.TextElideMode.ElideRight)
        self.field_name_label.setObjectName("FieldTitle")
        self.type_chip = ElidingLabel(str(field.type), mode=Qt.TextElideMode.ElideRight)
        self.type_chip.setObjectName("Chip")
        self.type_chip.setMaximumWidth(300)
        self.row_chip = QLabel()
        self.row_chip.setObjectName("Chip")
        self.size_chip = QLabel()
        self.size_chip.setObjectName("Chip")
        self.wrap_button = QPushButton()
        self.wrap_button.setProperty("toggle", True)
        self.wrap_button.setCheckable(True)
        self.wrap_button.setMinimumHeight(30)
        self.wrap_button.setVisible(False)
        metadata_layout.addWidget(self.field_name_label, 1)
        metadata_layout.addWidget(self.wrap_button)
        metadata_layout.addWidget(self.type_chip)
        metadata_layout.addWidget(self.row_chip)
        metadata_layout.addWidget(self.size_chip)

        self.stack = QStackedWidget()
        self.text_editor = QPlainTextEdit()
        self.text_editor.setObjectName("DetailEditor")
        self.text_editor.setReadOnly(True)
        self.text_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.stack.addWidget(self.text_editor)

        self.image_page = QWidget()
        image_layout = QVBoxLayout(self.image_page)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(8)
        image_toolbar = QHBoxLayout()
        image_toolbar.setContentsMargins(0, 0, 0, 0)
        image_toolbar.setSpacing(7)
        self.image_info_label = ElidingLabel(mode=Qt.TextElideMode.ElideMiddle)
        self.image_info_label.setObjectName("MutedLabel")
        self.zoom_out_button = QPushButton()
        self.zoom_out_button.setProperty("secondary", True)
        self.zoom_out_button.setIcon(make_icon("zoom_out", "#0F6FDB"))
        self.zoom_in_button = QPushButton()
        self.zoom_in_button.setProperty("secondary", True)
        self.zoom_in_button.setIcon(make_icon("zoom_in", "#0F6FDB"))
        self.reset_view_button = QPushButton()
        self.reset_view_button.setProperty("secondary", True)
        self.reset_view_button.setIcon(make_icon("reset_view", "#0F6FDB"))
        self.zoom_level_label = QLabel("100%")
        self.zoom_level_label.setObjectName("Chip")
        self.zoom_level_label.setMinimumWidth(54)
        self.zoom_level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for button in (self.zoom_out_button, self.zoom_in_button, self.reset_view_button):
            button.setMinimumHeight(30)
        image_toolbar.addWidget(self.image_info_label, 1)
        image_toolbar.addWidget(self.zoom_out_button)
        image_toolbar.addWidget(self.zoom_level_label)
        image_toolbar.addWidget(self.zoom_in_button)
        image_toolbar.addWidget(self.reset_view_button)
        self.image_view = ZoomableImageView()
        image_layout.addLayout(image_toolbar)
        image_layout.addWidget(self.image_view, 1)
        self.stack.addWidget(self.image_page)

        self.hex_preview = HexPreviewWidget(translator, embedded=True)
        self.stack.addWidget(self.hex_preview)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 13, 14, 14)
        layout.setSpacing(9)
        layout.addLayout(metadata_layout)
        layout.addWidget(self.stack, 1)

        self.wrap_button.toggled.connect(self._set_text_wrapping)
        self.zoom_out_button.clicked.connect(self.image_view.zoom_out)
        self.zoom_in_button.clicked.connect(self.image_view.zoom_in)
        self.reset_view_button.clicked.connect(self.image_view.reset_view)
        self.image_view.zoom_changed.connect(self._update_zoom_level)

        self._render_value()
        self.retranslate()

    def _set_text_wrapping(self, enabled: bool) -> None:
        mode = QPlainTextEdit.LineWrapMode.WidgetWidth if enabled else QPlainTextEdit.LineWrapMode.NoWrap
        self.text_editor.setLineWrapMode(mode)

    def _update_zoom_level(self, percent: int) -> None:
        self.zoom_level_label.setText(f"{percent}%")

    def _render_value(self) -> None:
        value = self._value
        field_type = self._field_type
        self.size_chip.clear()
        self.wrap_button.setVisible(False)
        self.image_view.clear_source()

        image = embedded_image_payload(value) if contains_binary_type(field_type) else None
        binary = embedded_binary_payload(value) if contains_binary_type(field_type) else None
        if image is not None:
            decoded = decode_image_bytes(image.data, image.image_format)
            if not decoded.isNull():
                self.image_view.set_source_image(decoded)
                hint = embedded_file_name_hint(value)
                self.image_info_label.setText(
                    f"{image.image_format.name} · {decoded.width()} × {decoded.height()} · {format_size(len(image.data))}"
                    + (f" · {hint}" if hint else "")
                )
                self.size_chip.setText(format_size(len(image.data)))
                self.stack.setCurrentWidget(self.image_page)
                return
        if binary is not None:
            label = f"{self._field_name} · {self.translator.tr('detail.source_row', row=self._source_row + 1)}"
            self.hex_preview.set_data(binary, label)
            self.size_chip.setText(format_size(len(binary)))
            self.stack.setCurrentWidget(self.hex_preview)
            return

        # 中文：普通字段统一经过详情格式化入口，使原生容器和以字符串存储的 JSON 都能按层级完整展开。
        # English: Normal fields use the shared detail formatter so native containers and JSON stored as text expand by hierarchy.
        text = pretty_text(value)
        self.text_editor.setPlainText(text)
        self.text_editor.moveCursor(QTextCursor.MoveOperation.Start)
        self.size_chip.setText(self.translator.tr("detail.characters", count=f"{len(text):,}"))
        self.stack.setCurrentWidget(self.text_editor)
        self.wrap_button.setVisible(True)

    def text_editors(self) -> tuple[QPlainTextEdit, ...]:
        # 中文：并排预览可能显示普通文本或 Hex 文本，统一暴露两类只读编辑器，才能让选区高亮在当前详情窗口中同步传播。
        # English: A side-by-side preview may show plain text or Hex text, so exposing both read-only editors lets selection highlighting propagate consistently across the current detail window.
        return self.text_editor, self.hex_preview.editor

    def visible_text_editors(self) -> tuple[QPlainTextEdit, ...]:
        current = self.stack.currentWidget()
        if current is self.text_editor:
            return (self.text_editor,)
        if current is self.hex_preview:
            return (self.hex_preview.editor,)
        return ()

    def reveal_editor(self, editor: QPlainTextEdit) -> None:
        if editor is self.text_editor:
            self.stack.setCurrentWidget(self.text_editor)
        elif editor is self.hex_preview.editor:
            self.stack.setCurrentWidget(self.hex_preview)

    def retranslate(self) -> None:
        self.row_chip.setText(self.translator.tr("detail.row_chip", row=self._source_row + 1))
        self.wrap_button.setText(self.translator.tr("detail.wrap_text"))
        self.zoom_out_button.setText(self.translator.tr("detail.zoom_out"))
        self.zoom_in_button.setText(self.translator.tr("detail.zoom_in"))
        self.reset_view_button.setText(self.translator.tr("detail.reset_view"))
        self.zoom_out_button.setAccessibleName(self.translator.tr("detail.zoom_out"))
        self.zoom_in_button.setAccessibleName(self.translator.tr("detail.zoom_in"))
        self.reset_view_button.setAccessibleName(self.translator.tr("detail.reset_view"))
        if self.stack.currentWidget() is self.text_editor:
            text = self.text_editor.toPlainText()
            self.size_chip.setText(self.translator.tr("detail.characters", count=f"{len(text):,}"))


class RecordDetailDialog(QDialog):
    def __init__(
        self,
        translator: Translator,
        model: ParquetTableModel,
        row: int,
        initial_column: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.translator = translator
        self.model = model
        self.row = row
        self.source_row = model.source_row(row)
        self._field_values = [model.raw_value(row, column) for column in range(model.columnCount())]
        self.current_column = initial_column
        self._row_json_generated = False
        self._panes: dict[int, FieldPreviewPane] = {}
        self._highlight_editors: list[QPlainTextEdit] = []
        self._highlight_term = ""
        self._search_query = ""
        self._search_matches: list[DetailSearchMatch] = []
        self._search_cursor = -1
        self._highlight_timer = QTimer(self)
        self._highlight_timer.setSingleShot(True)
        self._highlight_timer.setInterval(35)
        self._highlight_timer.timeout.connect(self._refresh_selection_highlights)
        self.setObjectName("DetailDialog")
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(900, 620)
        self.setSizeGripEnabled(True)
        self.setWindowIcon(QApplication.windowIcon())

        self.header = CardFrame(object_name="DialogHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(18, 14, 16, 14)
        header_layout.setSpacing(9)
        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        self.title_label = QLabel()
        self.title_label.setObjectName("DialogTitle")
        self.subtitle_label = ElidingLabel(mode=Qt.TextElideMode.ElideMiddle)
        self.subtitle_label.setObjectName("MutedLabel")
        title_layout.addWidget(self.title_label)
        title_layout.addWidget(self.subtitle_label)
        header_layout.addLayout(title_layout, 1)

        self.copy_button = QPushButton()
        self.copy_button.setProperty("secondary", True)
        self.copy_button.setIcon(make_icon("copy", "#0F6FDB"))
        self.export_button = QPushButton()
        self.export_button.setProperty("secondary", True)
        self.export_button.setIcon(make_icon("download", "#0F6FDB"))
        self.close_button = QPushButton()
        self.close_button.setProperty("primary", True)
        header_layout.addWidget(self.copy_button)
        header_layout.addWidget(self.export_button)
        header_layout.addWidget(self.close_button)

        self.search_bar = CardFrame(object_name="DetailSearchBar")
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(10, 8, 10, 8)
        search_layout.setSpacing(7)
        self.detail_search_field = SearchField()
        self.detail_search_edit = self.detail_search_field.editor
        self.detail_search_edit.installEventFilter(self)
        self.detail_search_field.setMinimumWidth(280)
        self.detail_search_previous = QPushButton()
        self.detail_search_previous.setProperty("secondary", True)
        self.detail_search_next = QPushButton()
        self.detail_search_next.setProperty("secondary", True)
        self.detail_search_status = QLabel()
        self.detail_search_status.setObjectName("DetailSearchStatus")
        self.detail_search_close = QPushButton()
        self.detail_search_close.setProperty("secondary", True)
        search_layout.addWidget(self.detail_search_field, 1)
        search_layout.addWidget(self.detail_search_previous)
        search_layout.addWidget(self.detail_search_next)
        search_layout.addWidget(self.detail_search_status)
        search_layout.addWidget(self.detail_search_close)
        self.search_bar.setVisible(False)

        self.find_action = QAction(self)
        self.find_action.setShortcut(QKeySequence.StandardKey.Find)
        self.find_action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        self.find_action.triggered.connect(self.show_detail_search)
        self.addAction(self.find_action)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("DetailSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(7)

        fields_card = CardFrame(object_name="Card")
        fields_layout = QVBoxLayout(fields_card)
        fields_layout.setContentsMargins(12, 12, 12, 12)
        fields_layout.setSpacing(8)
        self.fields_caption = QLabel()
        self.fields_caption.setObjectName("SectionTitle")
        self.field_list = QListWidget()
        self.field_list.setObjectName("FieldList")
        self.field_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.field_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.field_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.field_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        for column, field in enumerate(self.model.document.schema):
            item = QListWidgetItem(field.name)
            item.setData(Qt.ItemDataRole.UserRole, column)
            item.setToolTip(f"{field.name}\n{field.type}")
            self.field_list.addItem(item)
        self.selection_hint = QLabel()
        self.selection_hint.setObjectName("MutedLabel")
        self.selection_hint.setWordWrap(True)
        fields_layout.addWidget(self.fields_caption)
        fields_layout.addWidget(self.selection_hint)
        fields_layout.addWidget(self.field_list, 1)
        fields_card.setMinimumWidth(200)
        fields_card.setMaximumWidth(286)

        self.preview_grid = AdaptivePreviewGrid()
        self.preview_grid.setObjectName("DetailPreviewGrid")
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setObjectName("DetailPreviewScroll")
        self.preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.preview_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.preview_scroll.setWidget(self.preview_grid)

        self.row_page = QWidget()
        row_layout = QVBoxLayout(self.row_page)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self.row_editor = QPlainTextEdit()
        self.row_editor.setObjectName("DetailEditor")
        self.row_editor.setReadOnly(True)
        self.row_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        row_layout.addWidget(self.row_editor)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("DetailTabs")
        self.tabs.addTab(self.preview_scroll, "")
        self.tabs.addTab(self.row_page, "")

        splitter.addWidget(fields_card)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 850])

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(11)
        root_layout.addWidget(self.header)
        root_layout.addWidget(self.search_bar)
        root_layout.addWidget(splitter, 1)

        self.field_list.currentItemChanged.connect(self._current_field_changed)
        self.field_list.itemSelectionChanged.connect(self._sync_selected_previews)
        self.copy_button.clicked.connect(self._copy_current)
        self.export_button.clicked.connect(self._export_current)
        self.close_button.clicked.connect(self.accept)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.detail_search_edit.textChanged.connect(self._update_detail_search)
        self.detail_search_previous.clicked.connect(lambda: self._navigate_detail_search(-1))
        self.detail_search_next.clicked.connect(lambda: self._navigate_detail_search(1))
        self.detail_search_close.clicked.connect(self._hide_detail_search)
        self.translator.language_changed.connect(self.retranslate)

        self._register_highlight_editor(self.row_editor)

        self.field_list.setCurrentRow(max(0, min(initial_column, self.field_list.count() - 1)))
        self.resize(1120, 760)
        self.retranslate()

    def _field_value(self, column: int) -> object:
        if 0 <= column < len(self._field_values):
            return self._field_values[column]
        return None

    def _current_field_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        self.current_column = int(current.data(Qt.ItemDataRole.UserRole))
        self._update_header_actions()
        pane = self._panes.get(self.current_column)
        if pane is not None:
            self.preview_grid.reveal_preview(pane)

    def _selected_columns(self) -> list[int]:
        columns = [int(item.data(Qt.ItemDataRole.UserRole)) for item in self.field_list.selectedItems()]
        return sorted(set(columns))

    def _add_preview_pane(self, column: int) -> None:
        field = self.model.document.schema.field(column)
        pane = FieldPreviewPane(
            self.translator,
            field,
            column,
            self._field_value(column),
            self.source_row,
            self.preview_grid,
        )
        pane.hide()
        self._panes[column] = pane
        for editor in pane.text_editors():
            self._register_highlight_editor(editor)
        self.preview_grid.add_preview(pane)

    def _remove_preview_pane(self, column: int) -> None:
        pane = self._panes.pop(column, None)
        if pane is None:
            return
        pane.hide()
        for editor in pane.text_editors():
            self._unregister_highlight_editor(editor)
        self.preview_grid.remove_preview(pane)
        pane.setParent(None)
        pane.deleteLater()

    def _scroll_canvas_to_origin(self) -> None:
        self.preview_scroll.horizontalScrollBar().setValue(0)
        self.preview_scroll.verticalScrollBar().setValue(0)

    def _sync_selected_previews(self) -> None:
        selected = self._selected_columns()
        selected_set = set(selected)
        for column in tuple(self._panes):
            if column not in selected_set:
                self._remove_preview_pane(column)
        added = False
        for column in selected:
            if column in self._panes:
                continue
            self._add_preview_pane(column)
            added = True
        if added:
            self._scroll_canvas_to_origin()
        if self._search_query:
            QTimer.singleShot(0, lambda: self._update_detail_search(self._search_query))
        else:
            QTimer.singleShot(0, self._refresh_selection_highlights)

    def _update_header_actions(self) -> None:
        value = self._field_value(self.current_column)
        field = self.model.document.schema.field(self.current_column)
        image = embedded_image_payload(value) if contains_binary_type(field.type) else None
        binary = embedded_binary_payload(value) if contains_binary_type(field.type) else None
        self.export_button.setVisible(image is not None or binary is not None)

    def _register_highlight_editor(self, editor: QPlainTextEdit) -> None:
        if editor in self._highlight_editors:
            return
        self._highlight_editors.append(editor)
        editor.selectionChanged.connect(self._text_selection_changed)

    def _unregister_highlight_editor(self, editor: QPlainTextEdit) -> None:
        if editor not in self._highlight_editors:
            return
        editor.setExtraSelections([])
        try:
            editor.selectionChanged.disconnect(self._text_selection_changed)
        except (RuntimeError, TypeError):
            pass
        self._highlight_editors.remove(editor)

    def _text_selection_changed(self) -> None:
        source = self.sender()
        if not isinstance(source, QPlainTextEdit):
            return
        cursor = source.textCursor()
        if not cursor.hasSelection() and not source.hasFocus():
            # 中文：忽略 setPlainText 等操作产生的非焦点空选区信号，否则整行 JSON 延迟生成时会误清除用户在另一个并排字段中的有效高亮。
            # English: Ignore unfocused empty-selection signals from operations such as setPlainText, otherwise lazy row-JSON generation would incorrectly clear a valid highlight selected in another side-by-side field.
            return
        selected = cursor.selectedText().replace("\u2029", "\n").replace("\u2028", "\n")
        self._highlight_term = selected if selected and not selected.isspace() else ""
        # 中文：拖动选择会连续触发信号，短暂合并刷新可以避免每移动一个字符都重新扫描大型详情文本。
        # English: Drag selection emits continuously, so briefly coalescing refreshes avoids rescanning large detail text for every character crossed.
        self._highlight_timer.start()

    def _matching_selections(self, editor: QPlainTextEdit, term: str) -> list[QTextEdit.ExtraSelection]:
        selections: list[QTextEdit.ExtraSelection] = []
        search_cursor = QTextCursor(editor.document())
        match_format = QTextCharFormat()
        highlight_color = QColor("#1E90FF")
        highlight_color.setAlpha(92)
        match_format.setBackground(highlight_color)

        while len(selections) < MAX_SELECTION_HIGHLIGHTS:
            match_cursor = editor.document().find(
                term,
                search_cursor,
                QTextDocument.FindFlag.FindCaseSensitively,
            )
            if match_cursor.isNull():
                break
            selection = QTextEdit.ExtraSelection()
            selection.cursor = match_cursor
            selection.format = match_format
            selections.append(selection)

            next_position = match_cursor.selectionEnd()
            if next_position <= search_cursor.position():
                break
            search_cursor.setPosition(next_position)

        return selections

    def _search_selections(self, editor: QPlainTextEdit) -> list[QTextEdit.ExtraSelection]:
        selections: list[QTextEdit.ExtraSelection] = []
        for index, match in enumerate(self._search_matches):
            if match.editor is not editor:
                continue
            cursor = QTextCursor(editor.document())
            cursor.setPosition(match.start)
            cursor.setPosition(match.end, QTextCursor.MoveMode.KeepAnchor)
            selection = QTextEdit.ExtraSelection()
            color = QColor("#1E90FF")
            color.setAlpha(155 if index == self._search_cursor else 86)
            selection.format.setBackground(color)
            selection.cursor = cursor
            selections.append(selection)
        return selections

    def _refresh_text_highlights(self) -> None:
        for editor in tuple(self._highlight_editors):
            selections: list[QTextEdit.ExtraSelection] = []
            if self._highlight_term and editor.isVisibleTo(self):
                selections.extend(self._matching_selections(editor, self._highlight_term))
            selections.extend(self._search_selections(editor))
            editor.setExtraSelections(selections)

    def _refresh_selection_highlights(self) -> None:
        self._refresh_text_highlights()

    def show_detail_search(self) -> None:
        self.search_bar.setVisible(True)
        self.detail_search_edit.setFocus()
        self.detail_search_edit.selectAll()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.detail_search_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                direction = -1 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
                self._navigate_detail_search(direction)
                return True
            if event.key() == Qt.Key.Key_Escape:
                self._hide_detail_search()
                return True
        return super().eventFilter(watched, event)

    def _ensure_row_json_generated(self) -> None:
        if self._row_json_generated:
            return
        payload = {
            name: json_safe(self._field_value(column))
            for column, name in enumerate(self.model.document.schema.names)
        }
        self.row_editor.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
        self._row_json_generated = True

    def _detail_search_editors(self) -> tuple[QPlainTextEdit, ...]:
        editors: list[QPlainTextEdit] = []
        for pane in self._panes.values():
            editors.extend(pane.visible_text_editors())
        editors.append(self.row_editor)
        return tuple(dict.fromkeys(editors))

    def _collect_detail_search_matches(self, query: str) -> list[DetailSearchMatch]:
        matches: list[DetailSearchMatch] = []
        for editor in self._detail_search_editors():
            search_cursor = QTextCursor(editor.document())
            while len(matches) < MAX_DETAIL_SEARCH_MATCHES:
                match_cursor = editor.document().find(query, search_cursor)
                if match_cursor.isNull():
                    break
                matches.append(DetailSearchMatch(editor, match_cursor.selectionStart(), match_cursor.selectionEnd()))
                next_position = match_cursor.selectionEnd()
                if next_position <= search_cursor.position():
                    break
                search_cursor.setPosition(next_position)
        return matches

    def _update_detail_search(self, query: str) -> None:
        self._search_query = query.strip()
        self._search_cursor = -1
        self._search_matches = []
        if self._search_query:
            self._ensure_row_json_generated()
            self._search_matches = self._collect_detail_search_matches(self._search_query)
            if self._search_matches:
                self._search_cursor = 0
                self._reveal_detail_search_match()
        self._refresh_text_highlights()
        self._update_detail_search_status()

    def _navigate_detail_search(self, direction: int) -> None:
        if not self._search_query:
            return
        if not self._search_matches:
            self._update_detail_search_status()
            return
        self._search_cursor = (self._search_cursor + direction) % len(self._search_matches)
        self._reveal_detail_search_match()
        self._refresh_text_highlights()
        self._update_detail_search_status()

    def _reveal_detail_search_match(self) -> None:
        if not (0 <= self._search_cursor < len(self._search_matches)):
            return
        match = self._search_matches[self._search_cursor]
        editor = match.editor
        if editor is self.row_editor:
            self.tabs.setCurrentWidget(self.row_page)
        else:
            self.tabs.setCurrentWidget(self.preview_scroll)
            for pane in self._panes.values():
                if editor in pane.text_editors():
                    pane.reveal_editor(editor)
                    self.preview_grid.reveal_preview(pane)
                    tile = self.preview_grid.tile_for(pane)
                    if tile is not None:
                        self.preview_scroll.ensureWidgetVisible(tile)
                    break
        cursor = QTextCursor(editor.document())
        cursor.setPosition(match.start)
        cursor.setPosition(match.end, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()
        editor.setFocus()

    def _update_detail_search_status(self) -> None:
        if not self._search_query:
            self.detail_search_status.clear()
        elif not self._search_matches:
            self.detail_search_status.setText(self.translator.tr("detail.search_no_match"))
        else:
            self.detail_search_status.setText(
                self.translator.tr(
                    "detail.search_position",
                    current=self._search_cursor + 1,
                    count=len(self._search_matches),
                )
            )

    def _hide_detail_search(self) -> None:
        self._search_query = ""
        self._search_matches = []
        self._search_cursor = -1
        self.detail_search_edit.clear()
        self.search_bar.setVisible(False)
        self._refresh_text_highlights()

    def _tab_changed(self, index: int) -> None:
        QTimer.singleShot(0, self._refresh_selection_highlights)
        if index != 1 or self._row_json_generated:
            return
        # 中文：整行 JSON 在用户真正切换到该页时才生成，避免包含大二进制字段的记录在打开详情窗时立即进行昂贵 Base64 转换。
        # English: Row JSON is generated only when the user opens that tab, avoiding expensive Base64 conversion for large binary fields during dialog startup.
        self._ensure_row_json_generated()
        QTimer.singleShot(0, self._refresh_selection_highlights)

    def _copy_current(self) -> None:
        value = self._field_value(self.current_column)
        image = embedded_image_payload(value)
        binary = embedded_binary_payload(value)
        if image is not None or binary is not None:
            data = image.data if image is not None else binary
            QGuiApplication.clipboard().setText(to_base64(data or b""))
            return
        QGuiApplication.clipboard().setText(pretty_text(value))

    def _export_current(self) -> None:
        value = self._field_value(self.current_column)
        image = embedded_image_payload(value)
        data = image.data if image is not None else embedded_binary_payload(value)
        if data is None:
            return
        extension = image.image_format.extension if image is not None else "bin"
        hint = embedded_file_name_hint(value)
        suggested = hint or f"row_{self.source_row + 1}.{extension}"
        if not Path(suggested).suffix:
            suggested += f".{extension}"
        target, _ = QFileDialog.getSaveFileName(self, self.translator.tr("context.export_binary"), suggested)
        if not target:
            return
        try:
            Path(target).write_bytes(data)
        except OSError as error:
            show_message(self, self.translator.tr("common.error"), str(error), critical=True)

    def retranslate(self) -> None:
        source_row = self.source_row + 1
        self.setWindowTitle(self.translator.tr("detail.window_title", row=source_row))
        self.title_label.setText(self.translator.tr("detail.title", row=source_row))
        self.subtitle_label.setText(self.model.document.display_name)
        self.fields_caption.setText(self.translator.tr("detail.fields"))
        self.selection_hint.setText(self.translator.tr("detail.multi_select_hint"))
        self.copy_button.setText(self.translator.tr("detail.copy_value"))
        self.export_button.setText(self.translator.tr("context.export_binary"))
        self.close_button.setText(self.translator.tr("common.close"))
        self.detail_search_edit.setPlaceholderText(self.translator.tr("detail.search_placeholder"))
        self.detail_search_previous.setText(self.translator.tr("detail.search_previous"))
        self.detail_search_next.setText(self.translator.tr("detail.search_next"))
        self.detail_search_close.setText(self.translator.tr("detail.search_close"))
        self.detail_search_previous.setAccessibleName(self.translator.tr("detail.search_previous"))
        self.detail_search_next.setAccessibleName(self.translator.tr("detail.search_next"))
        self.detail_search_close.setAccessibleName(self.translator.tr("detail.search_close"))
        self.tabs.setTabText(0, self.translator.tr("detail.value_tab"))
        self.tabs.setTabText(1, self.translator.tr("detail.row_json_tab"))
        for pane in self._panes.values():
            pane.retranslate()
        self._update_header_actions()
        self._update_detail_search_status()
