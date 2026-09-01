from __future__ import annotations

import json

from parqscan.utils.paths import resource_path


def release_name() -> str:
    try:
        payload = json.loads(resource_path("resources", "release.json").read_text(encoding="utf-8"))
        value = payload.get("release") if isinstance(payload, dict) else None
        return str(value) if value else ""
    except (OSError, json.JSONDecodeError):
        # 中文：版本信息缺失不应阻止数据工具启动，因此只回退为空文本并继续运行。
        # English: Missing release metadata must not prevent a data tool from starting, so the application falls back to empty text and continues.
        return ""
