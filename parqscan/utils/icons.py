from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from parqscan.tokens import get_theme_tokens


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


def _paint_icon(painter: QPainter, name: str, color: str, size: int) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(
        QColor(color),
        max(1.5, size / 12.0),
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
        painter.drawRoundedRect(QRectF(size * 0.22, size * 0.34, size * 0.44, size * 0.46), 2, 2)
        back = QPainterPath()
        back.moveTo(size * 0.34, size * 0.34)
        back.lineTo(size * 0.34, size * 0.22)
        back.lineTo(size * 0.78, size * 0.22)
        back.lineTo(size * 0.78, size * 0.68)
        back.lineTo(size * 0.66, size * 0.68)
        painter.drawPath(back)
    elif name == "download":
        painter.drawLine(QPointF(center, margin), QPointF(center, size * 0.62))
        painter.drawLine(QPointF(center, size * 0.62), QPointF(size * 0.34, size * 0.46))
        painter.drawLine(QPointF(center, size * 0.62), QPointF(size * 0.66, size * 0.46))
        painter.drawLine(QPointF(margin, size * 0.78), QPointF(size - margin, size * 0.78))
    elif name == "search":
        painter.drawEllipse(QRectF(size * 0.22, size * 0.2, size * 0.42, size * 0.42))
        painter.drawLine(QPointF(size * 0.58, size * 0.58), QPointF(size * 0.8, size * 0.8))
    elif name in {"zoom_in", "zoom_out"}:
        cx, cy = size * 0.43, size * 0.41
        painter.drawEllipse(QRectF(size * 0.2, size * 0.18, size * 0.46, size * 0.46))
        painter.drawLine(QPointF(size * 0.59, size * 0.57), QPointF(size * 0.8, size * 0.78))
        painter.drawLine(QPointF(cx - size * 0.12, cy), QPointF(cx + size * 0.12, cy))
        if name == "zoom_in":
            painter.drawLine(QPointF(cx, cy - size * 0.12), QPointF(cx, cy + size * 0.12))
    elif name == "reset_view":
        painter.drawArc(QRectF(size * 0.22, size * 0.22, size * 0.56, size * 0.56), 135 * 16, -285 * 16)
        painter.drawLine(QPointF(size * 0.30, size * 0.30), QPointF(size * 0.22, size * 0.18))
        painter.drawLine(QPointF(size * 0.30, size * 0.30), QPointF(size * 0.42, size * 0.26))
    elif name == "maximize":
        painter.drawRoundedRect(QRectF(size * 0.24, size * 0.24, size * 0.52, size * 0.52), 1.5, 1.5)
    elif name == "restore":
        painter.drawRoundedRect(QRectF(size * 0.22, size * 0.34, size * 0.44, size * 0.44), 1.5, 1.5)
        back = QPainterPath()
        back.moveTo(size * 0.34, size * 0.34)
        back.lineTo(size * 0.34, size * 0.22)
        back.lineTo(size * 0.78, size * 0.22)
        back.lineTo(size * 0.78, size * 0.66)
        back.lineTo(size * 0.66, size * 0.66)
        painter.drawPath(back)
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


def make_icon(name: str, color: str = "#475569", size: int = 20, disabled_color: str | None = None) -> QIcon:
    icon = QIcon()
    for scale in (1, 2):
        pixmap = QPixmap(size * scale, size * scale)
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.scale(scale, scale)
        _paint_icon(painter, name, color, size)
        painter.end()
        icon.addPixmap(pixmap, QIcon.Mode.Normal)

        disabled_hex = disabled_color or "#94A3B8"
        disabled_pixmap = QPixmap(size * scale, size * scale)
        disabled_pixmap.setDevicePixelRatio(scale)
        disabled_pixmap.fill(Qt.GlobalColor.transparent)
        disabled_painter = QPainter(disabled_pixmap)
        disabled_painter.scale(scale, scale)
        _paint_icon(disabled_painter, name, disabled_hex, size)
        disabled_painter.end()
        icon.addPixmap(disabled_pixmap, QIcon.Mode.Disabled)
    return icon


def make_themed_icon(name: str, theme: str = "light", role: str = "muted", size: int = 20) -> QIcon:
    tokens = get_theme_tokens(theme)
    color = tokens.icon_accent if role == "accent" else (tokens.on_primary if role == "on_primary" else tokens.icon_muted)
    return make_icon(name, color=color, size=size, disabled_color=tokens.icon_disabled)
