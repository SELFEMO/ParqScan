from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QStandardPaths

from parqscan.constants import APP_NAME, DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS, RECENT_FILE_LIMIT

MAX_COLUMN_ORDER_SCHEMAS = 100


class ConfigManager:
    def __init__(self) -> None:
        self.path = self._resolve_path()
        self.data = self._load()

    def _resolve_path(self) -> Path:
        if getattr(sys, "frozen", False):
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
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary_name = tempfile.mkstemp(prefix="parqscan-", suffix=".json", dir=self.path.parent)
        except OSError:
            return
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream, ensure_ascii=False, indent=2)
            os.replace(temporary_name, self.path)
        except (OSError, TypeError, ValueError):
            try:
                os.unlink(temporary_name)
            except OSError:
                pass

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()

    def recent_files(self, check_exists: bool = False) -> list[str]:
        values = self.data.get("recent_files", [])
        items = [path for path in values if isinstance(path, str) and path.strip()]
        if check_exists:
            return [path for path in items if Path(path).exists()]
        return items

    def add_recent_file(self, path: str) -> None:
        normalized = str(Path(path).resolve())
        values = [item for item in self.recent_files(check_exists=False) if item != normalized]
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
        key = "\u001f".join(schema_names)
        layouts.pop(key, None)
        layouts[key] = list(logical_order)
        while len(layouts) > MAX_COLUMN_ORDER_SCHEMAS:
            oldest_key = next(iter(layouts))
            layouts.pop(oldest_key, None)
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

    def window_geometry(self, key: str = "main_window") -> str | None:
        geometries = self.data.get("window_geometries", {})
        if not isinstance(geometries, dict):
            return None
        val = geometries.get(key)
        return val if isinstance(val, str) and val else None

    def set_window_geometry(self, key: str, encoded_geometry: str) -> None:
        geometries = self.data.setdefault("window_geometries", {})
        if not isinstance(geometries, dict):
            geometries = {}
            self.data["window_geometries"] = geometries
        geometries[key] = encoded_geometry
        self.save()
