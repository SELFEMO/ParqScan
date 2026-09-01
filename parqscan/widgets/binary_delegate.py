from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from parqscan.constants import THUMBNAIL_SIZE
from parqscan.models.parquet_table_model import ParquetTableModel


class BinaryCellDelegate(QStyledItemDelegate):
    def _paint_search_match(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        if not index.data(ParquetTableModel.SearchMatchRole):
            return
        painter.save()
        color = QColor(30, 144, 255, 92 if option.state & QStyle.StateFlag.State_Selected else 62)
        painter.fillRect(option.rect, color)
        painter.restore()

    def paint(self, painter, option: QStyleOptionViewItem, index) -> None:
        if index.data(ParquetTableModel.LoadingRole):
            # 中文：加载中绘制轻量骨架而不是空白表格，用户能立即理解当前页正在后台读取。
            # English: Lightweight skeletons replace blank cells during loading so users immediately understand that the page is being read in the background.
            painter.save()
            painter.fillRect(option.rect, option.palette.base())
            width = max(28, min(option.rect.width() - 24, 140))
            skeleton = QRectF(option.rect.x() + 12, option.rect.center().y() - 4, width, 8)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(148, 163, 184, 55))
            painter.drawRoundedRect(skeleton, 4, 4)
            painter.restore()
            return

        if not index.data(ParquetTableModel.IsImageRole):
            super().paint(painter, option, index)
            self._paint_search_match(painter, option, index)
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
        target = QRectF(
            option.rect.x() + (option.rect.width() - pixmap.width()) / 2,
            option.rect.y() + (option.rect.height() - pixmap.height()) / 2,
            pixmap.width(),
            pixmap.height(),
        )
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(148, 163, 184, 70))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(target.adjusted(-4, -4, 4, 4), 8, 8)
        painter.drawPixmap(target.topLeft(), pixmap)
        painter.restore()
        self._paint_search_match(painter, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        if index.data(ParquetTableModel.IsImageRole):
            return QSize(THUMBNAIL_SIZE + 16, THUMBNAIL_SIZE + 16)
        return super().sizeHint(option, index)
