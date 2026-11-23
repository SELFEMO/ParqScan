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
        self._fallback: dict[str, Any] = self._read_locale("en")
        self._load()

    @staticmethod
    def _read_locale(language: str) -> dict[str, Any]:
        path = resource_path("locales", f"{language}.json")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _load(self) -> None:
        self._messages = self._read_locale(self.language)

    def set_language(self, language: str) -> None:
        if language not in {"zh", "en"} or language == self.language:
            return
        self.language = language
        self._load()
        self.language_changed.emit()

    @staticmethod
    def _lookup(mapping: dict[str, Any], key: str) -> str | None:
        node: Any = mapping
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return str(node)

    def tr(self, key: str, **values: Any) -> str:
        text = self._lookup(self._messages, key)
        if text is None:
            text = self._lookup(self._fallback, key)
        if text is None:
            return key
        try:
            return text.format(**values)
        except (KeyError, ValueError):
            return text
