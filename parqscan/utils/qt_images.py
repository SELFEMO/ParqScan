from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
from PySide6.QtGui import QImage, QImageReader

from parqscan.utils.binary import BinaryFormat


def decode_image_bytes(data: bytes, image_format: BinaryFormat, maximum_size: int | None = None) -> QImage:
    byte_array = QByteArray(data)
    buffer = QBuffer()
    buffer.setData(byte_array)
    if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
        return QImage()

    # 中文：在读取前传入目标尺寸，让 Qt 直接生成缩略图，避免先展开完整高分辨率图片造成瞬时内存峰值。
    # English: Supplying the target size before reading lets Qt decode a thumbnail directly, avoiding full-resolution memory spikes.
    reader = QImageReader(buffer, QByteArray(image_format.qt_format))
    reader.setAutoTransform(True)
    if maximum_size is not None and maximum_size > 0:
        source_size = reader.size()
        if source_size.isValid() and not source_size.isEmpty():
            scaled_size = QSize(source_size)
            scaled_size.scale(maximum_size, maximum_size, Qt.AspectRatioMode.KeepAspectRatio)
            reader.setScaledSize(scaled_size)
    image = reader.read()
    buffer.close()
    if not image.isNull():
        return image

    image = QImage.fromData(data)
    if image.isNull() or maximum_size is None or maximum_size <= 0:
        return image
    return image.scaled(
        maximum_size,
        maximum_size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
