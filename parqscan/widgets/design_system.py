from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QIcon,
    QImage,
    QIntValidator,
    QPainter,
    QPainterPath,
    QPalette,
    QPixmap,
    QRegion,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListView,
    QMenu,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from parqscan.constants import PAGE_SIZE_OPTIONS
from parqscan.i18n import Translator
from parqscan.utils.icons import make_icon


def _apply_rounded_mask(widget: QWidget, radius: int = 10) -> None:
    """Clip a top-level popup because QSS border-radius does not clip native popup windows."""
    rect = widget.rect()
    if rect.isEmpty():
        return
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    widget.setMask(QRegion(path.toFillPolygon().toPolygon()))


class CardFrame(QFrame):
    def __init__(self, parent: QWidget | None = None, object_name: str = "Card") -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)


class RoundedTableView(QTableView):
    """Table view clipped to the same radius as its themed border."""

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt naming convention
        super().resizeEvent(event)
        # 中文：表格包含 viewport 与滚动条等子控件，只有裁切整个视图才能让四角真正保持圆角而不是仅画一条圆形边框。
        # English: A table contains a viewport and scrollbars, so clipping the whole view is required for real rounded corners rather than a decorative border alone.
        _apply_rounded_mask(self, 10)


class RoundedMenu(QMenu):
    """Menu whose popup window is actually clipped to the same radius used by the theme."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RoundedMenu")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt naming convention
        super().showEvent(event)
        # 中文：QMenu 是独立顶层窗口，仅写 QSS 圆角不会裁掉系统方形窗口；显示后设置蒙版才能消除四角白块。
        # English: QMenu is a top-level popup, so QSS alone cannot clip its square native window; a mask removes the exposed corner blocks.
        QTimer.singleShot(0, lambda: _apply_rounded_mask(self, 10))

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt naming convention
        super().resizeEvent(event)
        _apply_rounded_mask(self, 10)


class RoundedComboBox(QComboBox):
    """Combo box with stable value painting and a clipped rounded popup."""

    _TEXT_LEFT_MARGIN = 12
    _ARROW_AREA_WIDTH = 28
    _TEXT_RIGHT_GAP = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        popup_view = QListView(self)
        popup_view.setObjectName("RoundedComboPopup")
        popup_view.setFrameShape(QFrame.Shape.NoFrame)
        popup_view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        popup_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setView(popup_view)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming convention
        del event
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        current_text = option.currentText
        current_icon = option.currentIcon
        option.currentText = ""
        option.currentIcon = QIcon()

        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)

        # 中文：不再依赖平台样式返回的 edit-field 区域，因为 Windows 的 DPI 与字体缩放会错误压缩该区域；
        # 当前值直接在控件真实内容矩形内绘制，因此“包含”“等于”“20”“50”等短文本无需放大控件也能完整显示。
        # English: The platform-reported edit field is avoided because Windows DPI and font scaling can incorrectly shrink it;
        # painting inside the real content rectangle keeps short values such as operators and page sizes visible without oversized controls.
        text_rect = self.contentsRect().adjusted(
            self._TEXT_LEFT_MARGIN,
            0,
            -(self._ARROW_AREA_WIDTH + self._TEXT_RIGHT_GAP),
            0,
        )
        alignment = Qt.AlignmentFlag.AlignVCenter
        alignment |= (
            Qt.AlignmentFlag.AlignHCenter
            if bool(self.property("centerText"))
            else Qt.AlignmentFlag.AlignLeft
        )

        if not current_icon.isNull():
            icon_size = min(max(0, text_rect.height() - 8), max(1, self.iconSize().width()))
            icon_rect = text_rect.adjusted(0, 0, -(max(0, text_rect.width() - icon_size)), 0)
            current_icon.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter)
            text_rect.adjust(icon_size + 6, 0, 0, 0)

        metrics = self.fontMetrics()
        visible_text = (
            current_text
            if metrics.horizontalAdvance(current_text) <= text_rect.width()
            else metrics.elidedText(current_text, Qt.TextElideMode.ElideRight, max(0, text_rect.width()))
        )
        color_group = (
            QPalette.ColorGroup.Active
            if self.isEnabled()
            else QPalette.ColorGroup.Disabled
        )
        painter.setPen(self.palette().color(color_group, QPalette.ColorRole.Text))
        painter.drawText(text_rect, int(alignment), visible_text)

    def showPopup(self) -> None:  # noqa: N802 - Qt naming convention
        # 中文：弹层宽度只按当前控件和真实内容需要计算，避免为了显示当前值而把主界面下拉框设计得过宽。
        # English: Popup width follows the control and actual item content, so the closed combo never needs to be oversized merely to display its value.
        content_width = 0
        for row in range(self.count()):
            content_width = max(content_width, self.fontMetrics().horizontalAdvance(self.itemText(row)))
        popup_width = max(self.width(), content_width + 30)
        self.view().setFixedWidth(popup_width)
        super().showPopup()
        QTimer.singleShot(0, self._style_popup_window)

    def _style_popup_window(self) -> None:
        popup = self.view().window()
        popup.setObjectName("RoundedComboPopupWindow")
        popup.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        popup.setAutoFillBackground(True)
        popup.setContentsMargins(0, 0, 0, 0)
        if isinstance(popup, QFrame):
            popup.setFrameShape(QFrame.Shape.NoFrame)
        popup.resize(self.view().width(), popup.height())
        style = popup.style()
        style.unpolish(popup)
        style.polish(popup)
        popup.update()
        # 中文：弹层使用不透明主题背景并裁切顶层窗口，避免透明原生容器在 Windows 上合成出黑色外边。
        # English: The popup uses an opaque themed surface and clips the top-level window, preventing transparent native containers from compositing a black rim on Windows.
        _apply_rounded_mask(popup, 10)


class ElidingLabel(QLabel):
    """A label that keeps the complete value while painting an elided display string."""

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        mode: Qt.TextElideMode = Qt.TextElideMode.ElideMiddle,
    ) -> None:
        super().__init__(parent)
        self._full_text = ""
        self._elide_mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming convention
        self._full_text = str(text)
        self.setToolTip(self._full_text)
        self._refresh_elision()

    def full_text(self) -> str:
        return self._full_text

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt naming convention
        super().resizeEvent(event)
        self._refresh_elision()

    def _refresh_elision(self) -> None:
        # 中文：完整路径和超长文件名必须可复制，但不应撑宽布局，因此只在绘制文本时省略中间部分。
        # English: Full paths and long filenames must remain available without widening the layout, so only the painted text is elided.
        available = max(0, self.contentsRect().width())
        visible = self.fontMetrics().elidedText(self._full_text, self._elide_mode, available)
        QLabel.setText(self, visible)


class SearchField(QFrame):
    """Compound search input whose icon is independent from QLineEdit action rendering."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SearchField")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.icon_label = QLabel()
        self.icon_label.setObjectName("SearchFieldIcon")
        self.icon_label.setPixmap(make_icon("search", "#718096", 16).pixmap(16, 16))
        self.icon_label.setFixedSize(18, 18)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.editor = QLineEdit()
        self.editor.setObjectName("SearchFieldEdit")
        self.editor.setFrame(False)
        self.editor.installEventFilter(self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(7)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.editor, 1)

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self.editor:
            if event.type() == QEvent.Type.FocusIn:
                self._set_focused(True)
            elif event.type() == QEvent.Type.FocusOut:
                self._set_focused(False)
        return super().eventFilter(watched, event)

    def _set_focused(self, focused: bool) -> None:
        # 中文：输入框和图标是一个视觉控件，焦点边框必须由外层统一绘制，避免内置 action 被裁切成异常图形。
        # English: The editor and icon form one visual control, so the outer frame owns focus painting and avoids clipped built-in action icons.
        self.setProperty("focused", focused)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()


class FloatingHint(QFrame):
    """Small branded hover card that does not use the platform tooltip renderer."""

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setObjectName("FloatingHint")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.label = QLabel(self)
        self.label.setObjectName("FloatingHintText")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.addWidget(self.label)

    def show_for(self, owner: QWidget, text: str) -> None:
        if not text or not owner.isVisible():
            return
        self.label.setText(text)
        self.adjustSize()
        point = owner.mapToGlobal(QPoint(owner.width() // 2 - self.width() // 2, owner.height() + 7))
        screen = owner.screen().availableGeometry() if owner.screen() is not None else owner.rect()
        x = max(screen.left() + 6, min(point.x(), screen.right() - self.width() - 6))
        y = point.y() if point.y() + self.height() <= screen.bottom() else owner.mapToGlobal(QPoint(0, -self.height() - 7)).y()
        self.move(x, y)
        _apply_rounded_mask(self, 8)
        self.show()


class HintToolButton(QToolButton):
    """Accessible icon button with a design-system hover hint."""

    hint_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hint_text = ""
        self._floating_hint = FloatingHint()
        self._hint_timer = QTimer(self)
        self._hint_timer.setSingleShot(True)
        self._hint_timer.setInterval(360)
        self._hint_timer.timeout.connect(lambda: self._floating_hint.show_for(self, self._hint_text))

    def set_hint(self, text: str) -> None:
        self._hint_text = str(text)
        self.setAccessibleName(self._hint_text)
        self.setStatusTip(self._hint_text)
        self.setToolTip("")

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Enter and self.isEnabled():
            self.hint_changed.emit(self._hint_text)
            self._hint_timer.start()
        elif event.type() in {
            QEvent.Type.Leave,
            QEvent.Type.Hide,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.FocusOut,
        }:
            self._hint_timer.stop()
            self._floating_hint.hide()
            self.hint_changed.emit("")
        elif event.type() == QEvent.Type.ToolTip:
            return True
        return super().event(event)


class ResponsiveImageLabel(QLabel):
    """Image label that keeps the source pixmap and fits it to the available canvas."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source_pixmap = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(1, 1)

    def set_source_pixmap(self, pixmap: QPixmap) -> None:
        self._source_pixmap = QPixmap(pixmap)
        self._refresh_pixmap()

    def clear_source(self) -> None:
        self._source_pixmap = QPixmap()
        self.clear()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt naming convention
        super().resizeEvent(event)
        self._refresh_pixmap()

    def _refresh_pixmap(self) -> None:
        if self._source_pixmap.isNull():
            return
        target = self.contentsRect().size()
        if target.width() <= 1 or target.height() <= 1:
            return
        # 中文：详情图片默认按画布等比缩放，窗口变化时重新计算，避免原图尺寸强迫用户横纵滚动。
        # English: Detail images fit the canvas proportionally and are recalculated on resize, avoiding mandatory scrolling caused by source dimensions.
        scaled = self._source_pixmap.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        QLabel.setPixmap(self, scaled)


class OriginalImageItem(QGraphicsItem):
    """Graphics item that paints the decoded source image without creating a resized intermediate."""

    def __init__(self) -> None:
        super().__init__()
        self._image = QImage()

    def set_image(self, image: QImage) -> None:
        self.prepareGeometryChange()
        self._image = QImage(image)
        self.update()

    def clear(self) -> None:
        self.prepareGeometryChange()
        self._image = QImage()
        self.update()

    def is_null(self) -> bool:
        return self._image.isNull()

    def boundingRect(self) -> QRectF:  # noqa: N802 - Qt naming convention
        if self._image.isNull():
            return QRectF()
        return QRectF(0, 0, self._image.width(), self._image.height())

    def paint(self, painter: QPainter, option, widget: QWidget | None = None) -> None:
        del option, widget
        if self._image.isNull():
            return
        # 中文：画布始终绘制完整解码后的原始像素，缩放仅由视图变换完成，绝不先生成低分辨率缩略图。
        # English: The canvas always paints the fully decoded source pixels; zooming is performed only by the view transform and never through a low-resolution intermediate thumbnail.
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(0, 0, self._image)


class ZoomableImageView(QGraphicsView):
    """Image canvas with fit-to-window, wheel zoom, buttons, and drag panning."""

    zoom_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ImageCanvas")
        self._scene = QGraphicsScene(self)
        self._item = OriginalImageItem()
        self._scene.addItem(self._item)
        self.setScene(self._scene)
        self._fit_mode = True

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAutoFillBackground(True)
        self.setBackgroundBrush(QBrush(self.palette().color(QPalette.ColorRole.Base)))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def set_source_image(self, image: QImage) -> None:
        self._item.set_image(image)
        self._scene.setSceneRect(self._item.boundingRect())
        # 中文：保留完整 QImage 作为唯一图像源，视图适配和用户缩放只改变矩阵，不改变源图分辨率。
        # English: The full QImage remains the single image source, while fitting and user zoom modify only the view matrix and never the source resolution.
        QTimer.singleShot(0, self.reset_view)

    def set_source_pixmap(self, pixmap: QPixmap) -> None:
        self.set_source_image(pixmap.toImage())

    def clear_source(self) -> None:
        self._item.clear()
        self._scene.setSceneRect(QRectF())
        self.resetTransform()
        self._fit_mode = True
        self.zoom_changed.emit(100)

    def has_image(self) -> bool:
        return not self._item.is_null()

    def zoom_in(self) -> None:
        self._zoom_by(1.2)

    def zoom_out(self) -> None:
        self._zoom_by(1 / 1.2)

    def reset_view(self) -> None:
        if not self.has_image():
            return
        self.resetTransform()
        target = self._item.boundingRect()
        if target.isEmpty() or self.viewport().width() <= 2 or self.viewport().height() <= 2:
            return
        self.fitInView(target, Qt.AspectRatioMode.KeepAspectRatio)
        self._fit_mode = True
        self._emit_zoom()

    def _zoom_by(self, factor: float) -> None:
        if not self.has_image():
            return
        current = abs(self.transform().m11())
        target = current * factor
        if target < 0.03 or target > 24.0:
            return
        # 中文：手动缩放从当前适配比例继续计算，避免第一次点击放大时图片突然跳回原始比例。
        # English: Manual zoom continues from the current fit scale so the first zoom click never jumps back to the source scale.
        self.scale(factor, factor)
        self._fit_mode = False
        self._emit_zoom()

    def _emit_zoom(self) -> None:
        percent = max(1, round(abs(self.transform().m11()) * 100))
        self.zoom_changed.emit(percent)

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt naming convention
        delta = event.angleDelta().y()
        if delta == 0 or not self.has_image():
            super().wheelEvent(event)
            return
        self._zoom_by(1.15 if delta > 0 else 1 / 1.15)
        event.accept()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt naming convention
        super().resizeEvent(event)
        # 中文：图片画布包含 viewport 和滚动条，统一裁切整个控件才能让缩放状态下仍保持真实圆角。
        # English: The image canvas contains a viewport and scrollbars, so clipping the full control preserves real rounded corners while zoomed.
        _apply_rounded_mask(self, 10)
        if self._fit_mode and self.has_image():
            self.reset_view()


class MetricCard(CardFrame):
    def __init__(self, title: str = "", value: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent, "MetricCard")
        self.accent = QFrame()
        self.accent.setObjectName("MetricAccent")
        self.accent.setFixedWidth(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("MetricTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")
        self.value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.value_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 13, 16, 13)
        layout.setSpacing(12)
        layout.addWidget(self.accent)
        layout.addLayout(text_layout, 1)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class LoadingOverlay(QWidget):
    def __init__(self, translator: Translator, parent: QWidget) -> None:
        super().__init__(parent)
        self.translator = translator
        self.setObjectName("LoadingOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setVisible(False)

        self.card = CardFrame(self, "LoadingCard")
        self.title_label = QLabel()
        self.title_label.setObjectName("LoadingTitle")
        self.detail_label = QLabel()
        self.detail_label.setObjectName("MutedLabel")
        self.progress = QProgressBar()
        self.progress.setObjectName("PageLoadProgress")
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(300)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(9)
        card_layout.addWidget(self.title_label)
        card_layout.addWidget(self.detail_label)
        card_layout.addWidget(self.progress)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addStretch(1)
        layout.addWidget(self.card, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

    def start(self, page_number: int, total_pages: int) -> None:
        self.title_label.setText(self.translator.tr("data.loading_page", page=page_number, total=total_pages))
        self.detail_label.setText(self.translator.tr("data.loading_preparing"))
        self.progress.setValue(0)
        self.setVisible(True)
        self.raise_()

    def update_progress(self, current: int, total: int) -> None:
        percent = 0 if total <= 0 else min(100, round(current * 100 / total))
        self.progress.setValue(percent)
        self.detail_label.setText(self.translator.tr("data.loading_progress", percent=percent))

    def finish(self) -> None:
        self.progress.setValue(100)
        self.hide()


class PaginationBar(CardFrame):
    page_requested = Signal(int)
    page_size_changed = Signal(int)

    def __init__(self, translator: Translator, page_size: int, parent: QWidget | None = None) -> None:
        super().__init__(parent, "PaginationBar")
        self.translator = translator
        self._current_page = 1
        self._total_pages = 1
        self._total_rows = 0
        self._page_size = page_size
        self._loading = False

        self.summary_label = QLabel()
        self.summary_label.setObjectName("PaginationSummary")
        self.page_size_label = QLabel()
        self.page_size_label.setObjectName("MutedLabel")
        self.page_size_combo = RoundedComboBox()
        self.page_size_combo.setObjectName("PageSizeCombo")
        for value in PAGE_SIZE_OPTIONS:
            self.page_size_combo.addItem(str(value), value)
        combo_index = self.page_size_combo.findData(page_size)
        self.page_size_combo.setCurrentIndex(max(0, combo_index))
        self.page_size_combo.setProperty("centerText", True)
        self.page_size_combo.setFixedWidth(74)

        self.first_button = self._nav_button("first")
        self.previous_button = self._nav_button("left")
        self.next_button = self._nav_button("right")
        self.last_button = self._nav_button("last")

        self.page_edit = QLineEdit("1")
        self.page_edit.setObjectName("PageNumberEdit")
        self.page_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_edit.setValidator(QIntValidator(1, 1, self.page_edit))
        self.page_edit.setFixedWidth(50)
        self.page_total_label = QLabel()
        self.page_total_label.setObjectName("PaginationTotal")
        self.page_total_label.setMinimumWidth(64)

        navigation = QFrame()
        navigation.setObjectName("PageNavigation")
        navigation_layout = QHBoxLayout(navigation)
        navigation_layout.setContentsMargins(0, 0, 0, 0)
        navigation_layout.setSpacing(6)
        navigation_layout.addWidget(self.first_button)
        navigation_layout.addWidget(self.previous_button)
        navigation_layout.addSpacing(2)
        navigation_layout.addWidget(self.page_edit)
        navigation_layout.addWidget(self.page_total_label)
        navigation_layout.addSpacing(2)
        navigation_layout.addWidget(self.next_button)
        navigation_layout.addWidget(self.last_button)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(9)
        layout.addWidget(self.summary_label)
        layout.addStretch(1)
        layout.addWidget(self.page_size_label)
        layout.addWidget(self.page_size_combo)
        layout.addSpacing(10)
        layout.addWidget(navigation)

        self.first_button.clicked.connect(lambda: self._emit_page(0))
        self.previous_button.clicked.connect(lambda: self._emit_page(max(0, self._current_page - 2)))
        self.next_button.clicked.connect(lambda: self._emit_page(min(self._total_pages - 1, self._current_page)))
        self.last_button.clicked.connect(lambda: self._emit_page(self._total_pages - 1))
        self.page_edit.editingFinished.connect(self._page_edit_requested)
        self.page_size_combo.currentIndexChanged.connect(self._size_requested)
        self.translator.language_changed.connect(self.retranslate)
        self.retranslate()
        self._refresh_buttons()

    @staticmethod
    def _nav_button(icon_name: str) -> HintToolButton:
        button = HintToolButton()
        button.setProperty("paginationNav", True)
        button.setIcon(make_icon(icon_name))
        button.setIconSize(QSize(15, 15))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setFixedSize(34, 32)
        return button

    def _emit_page(self, page_index: int) -> None:
        page_index = max(0, min(page_index, self._total_pages - 1))
        if page_index + 1 != self._current_page and not self._loading:
            self.page_requested.emit(page_index)

    def _page_edit_requested(self) -> None:
        text = self.page_edit.text().strip()
        requested = int(text) if text.isdigit() else self._current_page
        requested = max(1, min(requested, self._total_pages))
        self.page_edit.setText(str(requested))
        self._emit_page(requested - 1)

    def _size_requested(self) -> None:
        value = self.page_size_combo.currentData()
        if isinstance(value, int):
            self.page_size_changed.emit(value)

    def set_state(self, current_page: int, total_pages: int, page_size: int, total_rows: int) -> None:
        self._current_page = max(1, current_page)
        self._total_pages = max(1, total_pages)
        self._total_rows = max(0, total_rows)
        self._page_size = max(1, page_size)

        validator = self.page_edit.validator()
        if isinstance(validator, QIntValidator):
            validator.setTop(self._total_pages)
        self.page_edit.blockSignals(True)
        self.page_edit.setText(str(self._current_page))
        self.page_edit.blockSignals(False)

        combo_index = self.page_size_combo.findData(page_size)
        if combo_index >= 0:
            self.page_size_combo.blockSignals(True)
            self.page_size_combo.setCurrentIndex(combo_index)
            self.page_size_combo.blockSignals(False)
        self.retranslate()
        self._refresh_buttons()

    def set_loading(self, loading: bool) -> None:
        self._loading = loading
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        at_first = self._current_page <= 1
        at_last = self._current_page >= self._total_pages
        self.first_button.setEnabled(not self._loading and not at_first)
        self.previous_button.setEnabled(not self._loading and not at_first)
        self.next_button.setEnabled(not self._loading and not at_last)
        self.last_button.setEnabled(not self._loading and not at_last)
        self.page_edit.setEnabled(not self._loading)
        self.page_size_combo.setEnabled(not self._loading)

    def retranslate(self) -> None:
        self.page_size_label.setText(self.translator.tr("data.items_per_page"))
        if self._total_rows:
            start = (self._current_page - 1) * self._page_size + 1
            end = min(self._current_page * self._page_size, self._total_rows)
        else:
            start = end = 0
        self.summary_label.setText(
            self.translator.tr(
                "data.page_range_summary",
                start=f"{start:,}",
                end=f"{end:,}",
                rows=f"{self._total_rows:,}",
            )
        )
        self.page_total_label.setText(self.translator.tr("data.page_total", total=self._total_pages))

        button_texts = (
            (self.first_button, "data.first_page"),
            (self.previous_button, "data.previous_page"),
            (self.next_button, "data.next_page"),
            (self.last_button, "data.last_page"),
        )
        for button, key in button_texts:
            text = self.translator.tr(key)
            # 中文：分页只显示清晰图标，文字用于无障碍和状态栏，不再因按钮宽度不足出现省略号。
            # English: Pagination shows unambiguous icons only; labels remain available to accessibility and the status bar without eliding inside buttons.
            button.setText("")
            button.set_hint(text)

        page_hint = self.translator.tr("data.page_input_hint")
        self.page_edit.setAccessibleDescription(page_hint)
        self.page_edit.setStatusTip(page_hint)
        self.page_edit.setToolTip("")


class EmptyState(CardFrame):
    def __init__(self, title: str = "", description: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent, "EmptyState")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("EmptyTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.description_label = QLabel(description)
        self.description_label.setObjectName("MutedLabel")
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.description_label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(8)
        layout.addStretch(1)
        layout.addWidget(self.title_label)
        layout.addWidget(self.description_label)
        layout.addStretch(1)


class MessageDialog(QDialog):
    """Compact themed replacement for platform-native message boxes."""

    def __init__(
        self,
        title: str,
        message: str,
        parent: QWidget | None = None,
        *,
        critical: bool = False,
        icon: QIcon | QPixmap | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MessageDialog")
        self.setModal(True)
        self.setWindowTitle(title)
        self.setSizeGripEnabled(False)

        card = CardFrame(object_name="MessageCard")
        card.setMinimumWidth(410)
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if isinstance(icon, QIcon) and not icon.isNull():
            icon_label.setObjectName("MessageLogo")
            icon_label.setPixmap(icon.pixmap(QSize(52, 52)))
            icon_label.setFixedSize(56, 56)
        elif isinstance(icon, QPixmap) and not icon.isNull():
            icon_label.setObjectName("MessageLogo")
            icon_label.setPixmap(
                icon.scaled(52, 52, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
            icon_label.setFixedSize(56, 56)
        else:
            icon_label.setText("!" if critical else "i")
            icon_label.setObjectName("MessageIconCritical" if critical else "MessageIcon")
            icon_label.setFixedSize(36, 36)

        title_label = QLabel(title)
        title_label.setObjectName("DialogTitle")
        title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        message_label = QLabel(message)
        message_label.setObjectName("MessageText")
        message_label.setWordWrap(True)
        message_label.setMinimumWidth(320)
        message_label.setMaximumWidth(430)
        message_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(5)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        text_layout.addWidget(title_label, 0, Qt.AlignmentFlag.AlignTop)
        text_layout.addWidget(message_label, 0, Qt.AlignmentFlag.AlignTop)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(13)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        content_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)
        content_layout.addLayout(text_layout, 1)

        ok_button = QPushButton("OK")
        ok_button.setProperty("primary", True)
        ok_button.setFixedSize(76, 36)
        ok_button.clicked.connect(self.accept)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 16)
        card_layout.setSpacing(12)
        card_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        card_layout.addLayout(content_layout)
        card_layout.addWidget(ok_button, 0, Qt.AlignmentFlag.AlignRight)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        root.addWidget(card)

        # 中文：消息窗口严格跟随内容尺寸，避免 QLabel 在高 DPI 下被垂直拉伸并形成大块无意义留白。
        # English: The message window follows its content size so QLabel cannot stretch vertically at high DPI and create a large empty block.
        self.adjustSize()


def show_message(
    parent: QWidget | None,
    title: str,
    message: str,
    *,
    critical: bool = False,
    icon: QIcon | QPixmap | None = None,
) -> None:
    MessageDialog(title, message, parent, critical=critical, icon=icon).exec()


@dataclass(frozen=True)
class ChoiceOption:
    id: str
    label: str
    primary: bool = False
    secondary: bool = False


class ChoiceDialog(QDialog):
    """Themed replacement for multi-button confirmation dialogs."""

    def __init__(
        self,
        title: str,
        message: str,
        choices: list[ChoiceOption],
        parent: QWidget | None = None,
        *,
        detail: str = "",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MessageDialog")
        self.setModal(True)
        self.setWindowTitle(title)
        self._selected_id = ""

        card = CardFrame(object_name="MessageCard")
        card.setMinimumWidth(410)
        title_label = QLabel(title)
        title_label.setObjectName("DialogTitle")
        message_label = QLabel(message)
        message_label.setObjectName("MessageText")
        message_label.setWordWrap(True)
        message_label.setMinimumWidth(320)
        message_label.setMaximumWidth(430)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(title_label)
        layout.addWidget(message_label)
        if detail:
            detail_label = QLabel(detail)
            detail_label.setObjectName("MutedLabel")
            detail_label.setWordWrap(True)
            detail_label.setMinimumWidth(320)
            detail_label.setMaximumWidth(430)
            layout.addWidget(detail_label)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        actions.addStretch(1)
        for choice in reversed(choices):
            button = QPushButton(choice.label)
            if choice.primary:
                button.setProperty("primary", True)
            elif choice.secondary:
                button.setProperty("secondary", True)
            button.clicked.connect(lambda checked=False, choice_id=choice.id: self._choose(choice_id))
            actions.addWidget(button)
        layout.addSpacing(4)
        layout.addLayout(actions)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        root.addWidget(card)
        self.adjustSize()

    def _choose(self, choice_id: str) -> None:
        self._selected_id = choice_id
        self.accept()

    def selected_id(self) -> str:
        return self._selected_id


def show_choice(
    parent: QWidget | None,
    title: str,
    message: str,
    choices: list[ChoiceOption],
    *,
    detail: str = "",
) -> str | None:
    dialog = ChoiceDialog(title, message, choices, parent, detail=detail)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.selected_id() or None


class ItemSelectionDialog(QDialog):
    """Themed replacement for QInputDialog item selection."""

    def __init__(
        self,
        title: str,
        label: str,
        items: list[str],
        accept_text: str,
        cancel_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MessageDialog")
        self.setModal(True)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        card = CardFrame(object_name="MessageCard")
        title_label = QLabel(title)
        title_label.setObjectName("DialogTitle")
        field_label = QLabel(label)
        field_label.setObjectName("MutedLabel")
        self.combo = RoundedComboBox()
        self.combo.addItems(items)
        self.combo.setMinimumHeight(36)

        cancel_button = QPushButton(cancel_text)
        cancel_button.setProperty("secondary", True)
        accept_button = QPushButton(accept_text)
        accept_button.setProperty("primary", True)
        cancel_button.clicked.connect(self.reject)
        accept_button.clicked.connect(self.accept)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addStretch(1)
        actions.addWidget(cancel_button)
        actions.addWidget(accept_button)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(title_label)
        layout.addWidget(field_label)
        layout.addWidget(self.combo)
        layout.addSpacing(4)
        layout.addLayout(actions)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.addWidget(card)

    def selected_text(self) -> str:
        return self.combo.currentText()


def select_item(
    parent: QWidget | None,
    title: str,
    label: str,
    items: list[str],
    accept_text: str,
    cancel_text: str,
) -> tuple[str, bool]:
    dialog = ItemSelectionDialog(title, label, items, accept_text, cancel_text, parent)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return dialog.selected_text(), accepted
