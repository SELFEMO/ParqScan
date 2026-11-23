from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from parqscan.constants import THUMBNAIL_SIZE
from parqscan.models.parquet_table_model import ParquetTableModel
from parqscan.tokens import get_theme_tokens


class BinaryCellDelegate(QStyledItemDelegate):
    def _theme_tokens(self, option: QStyleOptionViewItem):
        base_color = option.palette.base().color()
        return get_theme_tokens("dark" if base_color.lightness() < 128 else "light")

    def _paint_search_match(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
        *,
        border_only: bool = False,
    ) -> None:
        if not index.data(ParquetTableModel.SearchMatchRole):
            return
        tokens = self._theme_tokens(option)
        painter.save()
        if border_only:
            pen = QPen(QColor(tokens.search_match_border), 2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(option.rect).adjusted(1.0, 1.0, -1.0, -1.0))
        else:
            fill = QColor(tokens.search_match_bg)
            fill.setAlpha(72 if option.state & QStyle.StateFlag.State_Selected else 46)
            painter.fillRect(option.rect, fill)
        painter.restore()

    def paint(self, painter, option: QStyleOptionViewItem, index) -> None:
        if index.data(ParquetTableModel.LoadingRole):
            # 中文：使用主题化背景后再叠加骨架条，避免跨主题切换时发生底色闪白。
            # English: Paint the themed item background before the skeleton bar to prevent white flashes across themes.
            styled_option = QStyleOptionViewItem(option)
            self.initStyleOption(styled_option, index)
            styled_option.text = ""
            styled_option.icon = QIcon()
            style = styled_option.widget.style() if styled_option.widget is not None else QApplication.style()
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, styled_option, painter, styled_option.widget)

            tokens = self._theme_tokens(option)
            painter.save()
            width = max(28, min(option.rect.width() - 24, 140))
            skeleton = QRectF(option.rect.x() + 12, option.rect.center().y() - 4, width, 8)
            painter.setPen(Qt.PenStyle.NoPen)
            fill = QColor(tokens.skeleton_fill)
            fill.setAlpha(120)
            painter.setBrush(fill)
            painter.drawRoundedRect(skeleton, 4, 4)
            painter.restore()
            return

        if not index.data(ParquetTableModel.IsImageRole):
            self._paint_search_match(painter, option, index)
            super().paint(painter, option, index)
            return

        styled_option = QStyleOptionViewItem(option)
        self.initStyleOption(styled_option, index)
        styled_option.text = ""
        styled_option.icon = QIcon()
        style = styled_option.widget.style() if styled_option.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, styled_option, painter, styled_option.widget)

        pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if pixmap is None:
            return
        logical_size = pixmap.deviceIndependentSize()
        draw_w = min(logical_size.width(), max(16.0, float(option.rect.width() - 8)))
        draw_h = min(logical_size.height(), max(16.0, float(option.rect.height() - 8)))
        scale = min(draw_w / max(1.0, logical_size.width()), draw_h / max(1.0, logical_size.height()))
        final_w = logical_size.width() * scale
        final_h = logical_size.height() * scale
        target = QRectF(
            option.rect.x() + (option.rect.width() - final_w) / 2.0,
            option.rect.y() + (option.rect.height() - final_h) / 2.0,
            final_w,
            final_h,
        )
        tokens = self._theme_tokens(option)
        painter.save()
        painter.setClipRect(option.rect)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        border_color = QColor(tokens.border)
        border_color.setAlpha(140)
        painter.setPen(border_color)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(target.adjusted(-3, -3, 3, 3), 6, 6)
        painter.drawPixmap(target, pixmap, QRectF(0, 0, pixmap.width(), pixmap.height()))
        painter.restore()
        self._paint_search_match(painter, option, index, border_only=True)

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        if index.data(ParquetTableModel.IsImageRole):
            return QSize(THUMBNAIL_SIZE + 16, THUMBNAIL_SIZE + 16)
        return super().sizeHint(option, index)
