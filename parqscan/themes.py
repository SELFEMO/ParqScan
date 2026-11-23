from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from parqscan.tokens import ThemePaletteTokens, get_theme_tokens
from parqscan.utils.paths import resource_path


def build_qt_palette(tokens: ThemePaletteTokens) -> QPalette:
    palette = QPalette()
    bg = QColor(tokens.bg)
    surface = QColor(tokens.surface)
    surface_muted = QColor(tokens.surface_muted)
    text = QColor(tokens.text)
    text_muted = QColor(tokens.text_muted)
    accent = QColor(tokens.accent)
    on_primary = QColor(tokens.on_primary)

    palette.setColor(QPalette.ColorRole.Window, bg)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, surface)
    palette.setColor(QPalette.ColorRole.AlternateBase, surface_muted)
    palette.setColor(QPalette.ColorRole.ToolTipBase, surface)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, surface_muted)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor(tokens.text_strong))
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, on_primary)
    palette.setColor(QPalette.ColorRole.PlaceholderText, text_muted)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, text_muted)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, text_muted)
    return palette


class ThemeManager(QObject):
    theme_changed = Signal(str)

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

    def current_tokens(self) -> ThemePaletteTokens:
        return get_theme_tokens(self.effective_theme())

    def apply(self, selected_theme: str) -> None:
        self.selected_theme = selected_theme if selected_theme in {"light", "dark", "system"} else "system"
        effective = self.effective_theme()
        tokens = get_theme_tokens(effective)
        self.application.setPalette(build_qt_palette(tokens))
        path = resource_path("styles", f"{effective}.qss")
        try:
            self.application.setStyleSheet(path.read_text(encoding="utf-8"))
        except OSError:
            self.application.setStyleSheet("")
        self.theme_changed.emit(effective)

    def _system_scheme_changed(self, _scheme) -> None:
        if self.selected_theme == "system":
            self.apply("system")
