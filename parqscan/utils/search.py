from __future__ import annotations

from parqscan.utils.binary import (
    contains_binary_type,
    embedded_binary_candidate,
    embedded_file_name_hint,
    embedded_image_payload,
    format_size,
)
from parqscan.utils.serialization import display_text


def searchable_text(value: object, field_type: object) -> str:
    # 中文：文件级和页内搜索必须共享完全相同的文本归一化规则，否则同一查询会因搜索范围不同而得到不同结果。
    # English: File and page search must share identical text normalization, otherwise the same query produces different results solely because its scope changed.
    if contains_binary_type(field_type):
        candidate = embedded_binary_candidate(value)
        if candidate is None:
            return "NULL"
        image = embedded_image_payload(value)
        prefix = f"IMAGE {image.image_format.name}" if image is not None else "BLOB"
        payload = image.data if image is not None else candidate.data
        hint = embedded_file_name_hint(value) or candidate.path_text
        return f"{prefix} {format_size(len(payload))} {hint}".strip()
    return display_text(value)
