from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QStandardPaths

from parqscan.constants import APP_NAME, DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS, RECENT_FILE_LIMIT


class ConfigManager:
    def __init__(self) -> None:
        self.path = self._resolve_path()
        self.data = self._load()

    def _resolve_path(self) -> Path:
        application_directory = Path(os.path.abspath(os.path.dirname(sys.executable)))
        if (application_directory / "portable.flag").exists():
            return application_directory / "config.json"
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
        directory = Path(base or Path.home() / f".{APP_NAME.casefold()}")
        directory.mkdir(parents=True, exist_ok=True)
        return directory / "config.json"

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(prefix="parqscan-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream, ensure_ascii=False, indent=2)
            os.replace(temporary_name, self.path)
        except (OSError, TypeError, ValueError):
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()

    def recent_files(self) -> list[str]:
        values = self.data.get("recent_files", [])
        return [path for path in values if isinstance(path, str) and Path(path).exists()]

    def add_recent_file(self, path: str) -> None:
        normalized = str(Path(path).resolve())
        values = [item for item in self.recent_files() if item != normalized]
        values.insert(0, normalized)
        self.data["recent_files"] = values[:RECENT_FILE_LIMIT]
        self.save()

    def page_size(self) -> int:
        value = self.data.get("page_size", DEFAULT_PAGE_SIZE)
        return value if isinstance(value, int) and value in PAGE_SIZE_OPTIONS else DEFAULT_PAGE_SIZE

    def column_order(self, schema_names: list[str]) -> list[int] | None:
        layouts = self.data.get("column_orders", {})
        key = "\u001f".join(schema_names)
        value = layouts.get(key) if isinstance(layouts, dict) else None
        if not isinstance(value, list) or sorted(value) != list(range(len(schema_names))):
            return None
        return [int(index) for index in value]

    def set_column_order(self, schema_names: list[str], logical_order: list[int]) -> None:
        if sorted(logical_order) != list(range(len(schema_names))):
            return
        layouts = self.data.setdefault("column_orders", {})
        if not isinstance(layouts, dict):
            layouts = {}
            self.data["column_orders"] = layouts
        # 中文：列顺序按 Schema 保存而不是按临时页面保存，同结构文件可复用布局且不会污染数据本身。
        # English: Column order is stored by schema rather than by transient page, so files with the same structure reuse the layout without modifying data.
        layouts["\u001f".join(schema_names)] = list(logical_order)
        self.save()

    def clear_column_order(self, schema_names: list[str]) -> None:
        layouts = self.data.get("column_orders", {})
        if not isinstance(layouts, dict):
            return
        layouts.pop("\u001f".join(schema_names), None)
        self.save()

    def file_list_sort(self) -> str:
        value = self.data.get("file_list_sort", "opened")
        return value if value in {"opened", "name_asc", "name_desc", "size_desc"} else "opened"
