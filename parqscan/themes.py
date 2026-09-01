from __future__ import annotations

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QApplication

from parqscan.utils.paths import resource_path


class ThemeManager(QObject):
    def __init__(self, application: QApplication) -> None:
        super().__init__(application)
        self.application = application
        self.selected_theme = "system"
        hints = application.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._system_scheme_changed)

    def effective_theme(self) -> str:
        if self.selected_theme != "system":
            return self.selected_theme
        scheme = self.application.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"

    def apply(self, selected_theme: str) -> None:
        self.selected_theme = selected_theme if selected_theme in {"light", "dark", "system"} else "system"
        path = resource_path("styles", f"{self.effective_theme()}.qss")
        try:
            self.application.setStyleSheet(path.read_text(encoding="utf-8"))
        except OSError:
            self.application.setStyleSheet("")

    def _system_scheme_changed(self, _scheme) -> None:
        if self.selected_theme == "system":
            self.apply("system")
