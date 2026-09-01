from __future__ import annotations

import base64
import datetime as dt
import decimal
import json
from typing import Any

import pyarrow as pa


def json_safe(value: Any) -> Any:
    if isinstance(value, pa.Scalar):
        return json_safe(value.as_py())
    if isinstance(value, bytes):
        return {"bytes_base64": base64.b64encode(value).decode("ascii"), "size": len(value)}
    if isinstance(value, bytearray):
        return json_safe(bytes(value))
    if isinstance(value, memoryview):
        return json_safe(value.tobytes())
    if isinstance(value, dict):
        return {str(key): json_safe(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(nested) for nested in value]
    if isinstance(value, (dt.date, dt.datetime, dt.time, decimal.Decimal)):
        return str(value)
    return value


def display_text(value: Any, maximum_length: int | None = None) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, pa.Scalar):
        value = value.as_py()
    if isinstance(value, bytes):
        text = f"[BLOB] {len(value):,} bytes"
    elif isinstance(value, (dict, list, tuple)):
        text = json.dumps(json_safe(value), ensure_ascii=False, separators=(", ", ": "))
    else:
        text = str(value)
    if maximum_length is not None and len(text) > maximum_length:
        return text[: max(0, maximum_length - 1)] + "…"
    return text


def _json_container_from_text(value: str) -> dict[str, Any] | list[Any] | None:
    candidate = value.strip().lstrip("\ufeff").strip()
    if not candidate or candidate[0] not in "[{":
        return None

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None

    # 中文：只展开对象和数组，避免把普通文本中的 JSON 标量（如 "true" 或 "123"）误改成另一种展示语义。
    # English: Only expand objects and arrays so JSON scalars in ordinary text, such as "true" or "123", do not silently change display semantics.
    if isinstance(parsed, (dict, list)):
        return parsed
    return None


def pretty_text(value: Any) -> str:
    if isinstance(value, pa.Scalar):
        value = value.as_py()
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(json_safe(value), ensure_ascii=False, indent=2)
    if value is None:
        return "NULL"
    if isinstance(value, str):
        # 中文：Parquet 经常把 JSON 保存为字符串；详情页在确认整段文本是合法对象或数组后再格式化，既提升层级可读性，也保留无效 JSON 和普通文本原样展示。
        # English: Parquet often stores JSON as text; the detail view formats it only after the entire value is validated as an object or array, improving hierarchy readability while preserving invalid JSON and ordinary text verbatim.
        parsed = _json_container_from_text(value)
        if parsed is not None:
            return json.dumps(parsed, ensure_ascii=False, indent=2)
    return str(value)
