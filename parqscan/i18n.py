from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QLocale, QObject, Signal

from parqscan.utils.paths import resource_path


class Translator(QObject):
    language_changed = Signal()

    def __init__(self, configured_language: str | None = None) -> None:
        super().__init__()
        system_language = "zh" if QLocale.system().name().lower().startswith("zh") else "en"
        self.language = configured_language if configured_language in {"zh", "en"} else system_language
        self._messages: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        path = resource_path("locales", f"{self.language}.json")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._messages = {}
            return
        self._messages = payload if isinstance(payload, dict) else {}

    def set_language(self, language: str) -> None:
        if language not in {"zh", "en"} or language == self.language:
            return
        self.language = language
        self._load()
        self.language_changed.emit()

    def tr(self, key: str, **values: Any) -> str:
        node: Any = self._messages
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return key
            node = node[part]
        text = str(node)
        try:
            return text.format(**values)
        except (KeyError, ValueError):
            return text
