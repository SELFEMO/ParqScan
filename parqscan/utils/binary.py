from __future__ import annotations

import base64
import binascii
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterator

import pyarrow as pa

from parqscan.constants import HEX_BYTES_PER_LINE


@dataclass(frozen=True)
class BinaryFormat:
    name: str
    extension: str
    mime_type: str
    qt_format: bytes
    is_image: bool = True


@dataclass(frozen=True)
class BinaryCandidate:
    data: bytes
    path: tuple[str, ...]

    @property
    def path_text(self) -> str:
        return ".".join(self.path)


@dataclass(frozen=True)
class EmbeddedImage:
    data: bytes
    image_format: BinaryFormat
    path: tuple[str, ...]


@dataclass
class BinaryColumnProfile:
    column_name: str
    sampled_values: int = 0
    image_values: int = 0
    formats: Counter[str] = field(default_factory=Counter)

    @property
    def image_ratio(self) -> float:
        return self.image_values / self.sampled_values if self.sampled_values else 0.0

    @property
    def likely_image(self) -> bool:
        return self.image_values > 0 and self.image_ratio >= 0.5


IMAGE_SIGNATURES: tuple[tuple[bytes, BinaryFormat], ...] = (
    (b"\xff\xd8\xff", BinaryFormat("JPEG", "jpg", "image/jpeg", b"jpeg")),
    (b"\x89PNG\r\n\x1a\n", BinaryFormat("PNG", "png", "image/png", b"png")),
    (b"GIF87a", BinaryFormat("GIF", "gif", "image/gif", b"gif")),
    (b"GIF89a", BinaryFormat("GIF", "gif", "image/gif", b"gif")),
    (b"BM", BinaryFormat("BMP", "bmp", "image/bmp", b"bmp")),
    (b"II*\x00", BinaryFormat("TIFF", "tif", "image/tiff", b"tiff")),
    (b"MM\x00*", BinaryFormat("TIFF", "tif", "image/tiff", b"tiff")),
    (b"\x00\x00\x01\x00", BinaryFormat("ICO", "ico", "image/x-icon", b"ico")),
    (b"RIFF", BinaryFormat("WEBP", "webp", "image/webp", b"webp")),
)

_FILE_NAME_KEYS = {"path", "filename", "file_name", "name", "uri", "url"}
_PREFERRED_BINARY_KEYS = {
    "bytes": 0,
    "data": 1,
    "content": 2,
    "payload": 3,
    "blob": 4,
    "image": 5,
    "body": 6,
    "value": 7,
}


def normalize_binary(value: Any) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, pa.Scalar):
        return normalize_binary(value.as_py())
    return None


def _format_from_magic(data: bytes) -> BinaryFormat | None:
    for signature, image_format in IMAGE_SIGNATURES:
        if not data.startswith(signature):
            continue
        if image_format.name == "WEBP" and (len(data) < 12 or data[8:12] != b"WEBP"):
            continue
        return image_format
    return None


def image_payload(value: Any) -> tuple[bytes, BinaryFormat] | None:
    data = normalize_binary(value)
    if not data:
        return None
    image_format = _format_from_magic(data)
    if image_format is not None:
        return data, image_format

    # 中文：只有明确的图片 data URI 或解码后带可信文件头的 Base64 才视为图片，避免普通文本 BLOB 被误判。
    # English: Only explicit image data URIs or Base64 values with trusted decoded signatures are accepted, preventing ordinary text BLOBs from being misclassified.
    encoded = data
    if data[:11].lower() == b"data:image/":
        try:
            header, encoded = data.split(b",", 1)
        except ValueError:
            return None
        if b";base64" not in header.lower():
            return None
    else:
        encoded = b"".join(data.split())
        if len(encoded) < 16 or len(encoded) % 4 != 0:
            return None

    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None
    image_format = _format_from_magic(decoded)
    return (decoded, image_format) if image_format is not None else None


def is_binary_type(data_type: pa.DataType) -> bool:
    return (
        pa.types.is_binary(data_type)
        or pa.types.is_large_binary(data_type)
        or pa.types.is_fixed_size_binary(data_type)
    )


def contains_binary_type(data_type: pa.DataType) -> bool:
    # 中文：数据集经常把附件包进结构体或集合，递归判断能让预览、统计和导出共享同一套真实类型规则。
    # English: Datasets often wrap attachments inside structs or collections, so recursive inspection keeps preview, metadata, and export behavior aligned.
    if is_binary_type(data_type):
        return True
    if pa.types.is_struct(data_type):
        return any(contains_binary_type(field.type) for field in data_type)
    if pa.types.is_list(data_type) or pa.types.is_large_list(data_type) or pa.types.is_fixed_size_list(data_type):
        return contains_binary_type(data_type.value_type)
    if pa.types.is_map(data_type):
        return contains_binary_type(data_type.key_type) or contains_binary_type(data_type.item_type)
    if pa.types.is_dictionary(data_type):
        return contains_binary_type(data_type.value_type)
    return False


def binary_leaf_paths(data_type: pa.DataType, prefix: tuple[str, ...] = ()) -> tuple[tuple[str, ...], ...]:
    if is_binary_type(data_type):
        return (prefix,)
    if pa.types.is_struct(data_type):
        paths: list[tuple[str, ...]] = []
        for field in data_type:
            paths.extend(binary_leaf_paths(field.type, prefix + (field.name,)))
        return tuple(paths)
    if pa.types.is_list(data_type) or pa.types.is_large_list(data_type) or pa.types.is_fixed_size_list(data_type):
        return binary_leaf_paths(data_type.value_type, prefix + ("element",))
    if pa.types.is_map(data_type):
        return (
            *binary_leaf_paths(data_type.key_type, prefix + ("key",)),
            *binary_leaf_paths(data_type.item_type, prefix + ("value",)),
        )
    if pa.types.is_dictionary(data_type):
        return binary_leaf_paths(data_type.value_type, prefix)
    return ()


def _candidate_key(item: tuple[Any, Any]) -> tuple[int, str]:
    key = str(item[0])
    return _PREFERRED_BINARY_KEYS.get(key.casefold(), 100), key.casefold()


def iter_binary_candidates(value: Any, path: tuple[str, ...] = (), max_items: int = 64) -> Iterator[BinaryCandidate]:
    if isinstance(value, pa.Scalar):
        value = value.as_py()
    direct = normalize_binary(value)
    if direct is not None:
        yield BinaryCandidate(direct, path)
        return
    if isinstance(value, dict):
        # 中文：优先遍历 bytes、data 等常见载荷键，能避免先处理路径文本并更快找到真正图片。
        # English: Prioritizing common payload keys such as bytes and data avoids path text and finds the actual image sooner.
        for key, nested in sorted(value.items(), key=_candidate_key):
            yield from iter_binary_candidates(nested, path + (str(key),), max_items=max_items)
        return
    if isinstance(value, (list, tuple)):
        # 中文：限制嵌套容器扫描数量，防止异常大数组在详情或表格渲染时阻塞界面。
        # English: Bounding nested-container scanning prevents unusually large arrays from blocking table rendering or detail views.
        for index, nested in enumerate(value[:max_items]):
            yield from iter_binary_candidates(nested, path + (str(index),), max_items=max_items)


def embedded_image_payload(value: Any) -> EmbeddedImage | None:
    for candidate in iter_binary_candidates(value):
        payload = image_payload(candidate.data)
        if payload is not None:
            image_data, image_format = payload
            return EmbeddedImage(image_data, image_format, candidate.path)
    return None


def embedded_binary_candidate(value: Any) -> BinaryCandidate | None:
    candidates = list(iter_binary_candidates(value))
    if not candidates:
        return None
    for candidate in candidates:
        if image_payload(candidate.data) is not None:
            return candidate
    return candidates[0]


def embedded_binary_payload(value: Any) -> bytes | None:
    image = embedded_image_payload(value)
    if image is not None:
        return image.data
    candidate = embedded_binary_candidate(value)
    return candidate.data if candidate is not None else None


def embedded_file_name_hint(value: Any, max_items: int = 64) -> str:
    if isinstance(value, pa.Scalar):
        value = value.as_py()
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).casefold() in _FILE_NAME_KEYS and isinstance(nested, str) and nested.strip():
                normalized = nested.replace("\\", "/").rstrip("/")
                return normalized.rsplit("/", 1)[-1]
        for _key, nested in sorted(value.items(), key=_candidate_key):
            hint = embedded_file_name_hint(nested, max_items=max_items)
            if hint:
                return hint
    elif isinstance(value, (list, tuple)):
        for nested in value[:max_items]:
            hint = embedded_file_name_hint(nested, max_items=max_items)
            if hint:
                return hint
    return ""


def inspect_binary_columns(table: pa.Table) -> dict[str, BinaryColumnProfile]:
    profiles: dict[str, BinaryColumnProfile] = {}
    for field_index, field in enumerate(table.schema):
        if not contains_binary_type(field.type):
            continue
        profile = BinaryColumnProfile(field.name)
        for scalar in table.column(field_index):
            candidate = embedded_binary_candidate(scalar)
            if candidate is None:
                continue
            profile.sampled_values += 1
            payload = image_payload(candidate.data)
            if payload is not None:
                profile.image_values += 1
                profile.formats[payload[1].name] += 1
        profiles[field.name] = profile
    return profiles


def format_size(byte_count: int | None) -> str:
    if byte_count is None:
        return "0 B"
    size = float(byte_count)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def hex_dump(data: bytes, bytes_per_line: int = HEX_BYTES_PER_LINE) -> str:
    lines: list[str] = []
    for offset in range(0, len(data), bytes_per_line):
        chunk = data[offset : offset + bytes_per_line]
        hex_part = " ".join(f"{value:02X}" for value in chunk)
        padded_hex = hex_part.ljust(bytes_per_line * 3 - 1)
        ascii_part = "".join(chr(value) if 32 <= value <= 126 else "." for value in chunk)
        lines.append(f"{offset:08X}  {padded_hex}  |{ascii_part}|")
    return "\n".join(lines)


def to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
