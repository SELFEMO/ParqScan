from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _draw_chevron(painter: QPainter, direction: str, size: int, center_x: float | None = None) -> None:
    center = size / 2 if center_x is None else center_x
    horizontal = size * 0.15
    top = size * 0.26
    bottom = size * 0.74

    # 中文：箭头尖端必须位于实际移动方向一侧，使用明确坐标而不是符号翻转，避免左右图标名称与绘制结果再次颠倒。
    # English: The arrow tip must sit on the actual movement side; explicit coordinates avoid another mismatch between icon names and rendered directions.
    if direction == "left":
        start = QPointF(center + horizontal, top)
        tip = QPointF(center - horizontal, size / 2)
        end = QPointF(center + horizontal, bottom)
    else:
        start = QPointF(center - horizontal, top)
        tip = QPointF(center + horizontal, size / 2)
        end = QPointF(center - horizontal, bottom)
    painter.drawLine(start, tip)
    painter.drawLine(tip, end)


def make_icon(name: str, color: str = "#64748B", size: int = 20) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(
        QColor(color),
        max(1.6, size / 12),
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    center = size / 2
    margin = size * 0.22

    if name == "left":
        _draw_chevron(painter, "left", size)
    elif name == "right":
        _draw_chevron(painter, "right", size)
    elif name == "first":
        bar_x = size * 0.27
        painter.drawLine(QPointF(bar_x, margin), QPointF(bar_x, size - margin))
        _draw_chevron(painter, "left", size, size * 0.57)
    elif name == "last":
        _draw_chevron(painter, "right", size, size * 0.43)
        bar_x = size * 0.73
        painter.drawLine(QPointF(bar_x, margin), QPointF(bar_x, size - margin))
    elif name == "folder":
        path = QPainterPath()
        path.moveTo(margin, size * 0.38)
        path.lineTo(size * 0.42, size * 0.38)
        path.lineTo(size * 0.5, size * 0.28)
        path.lineTo(size - margin, size * 0.28)
        path.lineTo(size - margin, size - margin)
        path.lineTo(margin, size - margin)
        path.closeSubpath()
        painter.drawPath(path)
    elif name == "copy":
        painter.drawRoundedRect(QRectF(size * 0.34, size * 0.24, size * 0.44, size * 0.5), 2, 2)
        painter.drawRoundedRect(QRectF(size * 0.22, size * 0.36, size * 0.44, size * 0.5), 2, 2)
    elif name == "download":
        painter.drawLine(QPointF(center, margin), QPointF(center, size * 0.62))
        painter.drawLine(QPointF(center, size * 0.62), QPointF(size * 0.34, size * 0.46))
        painter.drawLine(QPointF(center, size * 0.62), QPointF(size * 0.66, size * 0.46))
        painter.drawLine(QPointF(margin, size * 0.78), QPointF(size - margin, size * 0.78))
    elif name == "search":
        painter.drawEllipse(QRectF(size * 0.22, size * 0.2, size * 0.42, size * 0.42))
        painter.drawLine(QPointF(size * 0.58, size * 0.58), QPointF(size * 0.8, size * 0.8))
    elif name in {"zoom_in", "zoom_out"}:
        painter.drawEllipse(QRectF(size * 0.2, size * 0.18, size * 0.46, size * 0.46))
        painter.drawLine(QPointF(size * 0.58, size * 0.58), QPointF(size * 0.8, size * 0.8))
        painter.drawLine(QPointF(size * 0.31, center), QPointF(size * 0.55, center))
        if name == "zoom_in":
            painter.drawLine(QPointF(size * 0.43, size * 0.31), QPointF(size * 0.43, size * 0.55))
    elif name == "reset_view":
        painter.drawArc(QRectF(size * 0.22, size * 0.22, size * 0.56, size * 0.56), 35 * 16, 285 * 16)
        painter.drawLine(QPointF(size * 0.22, size * 0.42), QPointF(size * 0.22, size * 0.24))
        painter.drawLine(QPointF(size * 0.22, size * 0.24), QPointF(size * 0.4, size * 0.24))
    elif name == "maximize":
        painter.drawRoundedRect(QRectF(size * 0.24, size * 0.24, size * 0.52, size * 0.52), 1.5, 1.5)
    elif name == "restore":
        painter.drawRoundedRect(QRectF(size * 0.32, size * 0.22, size * 0.46, size * 0.46), 1.5, 1.5)
        painter.drawRoundedRect(QRectF(size * 0.22, size * 0.32, size * 0.46, size * 0.46), 1.5, 1.5)
    elif name == "close":
        painter.drawLine(QPointF(margin, margin), QPointF(size - margin, size - margin))
        painter.drawLine(QPointF(size - margin, margin), QPointF(margin, size - margin))
    elif name == "image":
        painter.drawRoundedRect(QRectF(margin, margin, size - margin * 2, size - margin * 2), 3, 3)
        painter.drawEllipse(QPointF(size * 0.38, size * 0.38), size * 0.06, size * 0.06)
        path = QPainterPath()
        path.moveTo(size * 0.27, size * 0.7)
        path.lineTo(size * 0.46, size * 0.52)
        path.lineTo(size * 0.58, size * 0.62)
        path.lineTo(size * 0.7, size * 0.47)
        path.lineTo(size * 0.78, size * 0.7)
        painter.drawPath(path)
    else:
        painter.drawEllipse(QRectF(margin, margin, size - margin * 2, size - margin * 2))
    painter.end()
    return QIcon(pixmap)
