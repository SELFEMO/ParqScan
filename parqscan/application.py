from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Sequence

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon, QImageReader
from PySide6.QtWidgets import QApplication

from parqscan.config import ConfigManager
from parqscan.constants import APP_NAME
from parqscan.i18n import Translator
from parqscan.main_window import MainWindow
from parqscan.release import release_name
from parqscan.themes import ThemeManager
from parqscan.update.controller import UpdateController

_SUPPORTED_PARQUET_SUFFIXES = {".parquet", ".parq", ".pq"}


def _command_line_paths(arguments: Sequence[str]) -> list[str]:
    paths: list[str] = []
    for argument in arguments[1:]:
        path = Path(argument).expanduser()
        if path.is_file() and path.suffix.casefold() in _SUPPORTED_PARQUET_SUFFIXES:
            paths.append(str(path.resolve()))
    return paths


def run(
    arguments: Sequence[str] | None = None,
    icon_factory: Callable[[], QIcon] | None = None,
    *,
    smoke_test: bool = False,
) -> int:
    args = list(sys.argv) if arguments is None else list(arguments)
    application = QApplication(args)
    application.setApplicationName(APP_NAME)
    application.setApplicationVersion(release_name())
    application.setOrganizationName(APP_NAME)
    application.setStyle("Fusion")
    QImageReader.setAllocationLimit(256)

    config = ConfigManager()
    translator = Translator(config.get("language"))
    themes = ThemeManager(application)
    themes.apply(config.get("theme", "system"))
    icon = icon_factory() if icon_factory is not None else QIcon()
    application.setWindowIcon(icon)

    update_controller = UpdateController(config)
    window = MainWindow(config, translator, themes, icon, update_controller)

    # 构建后的冒烟测试只验证依赖、Qt 平台插件和资源能完整初始化，不进入事件循环可避免 CI 或无显示器环境挂起。
    # The packaged smoke test validates dependencies, the Qt platform plugin, and resources without entering the event loop, avoiding hangs in CI or display-less environments.
    if smoke_test:
        if application.windowIcon().isNull() or application.windowIcon().pixmap(64, 64).isNull():
            return 1
        window.close()
        return 0

    window.show()
    update_timer = QTimer(window)
    update_timer.setSingleShot(True)
    update_timer.setInterval(3000)
    update_timer.timeout.connect(update_controller.maybe_auto_check)
    update_timer.start()
    for path in _command_line_paths(args):
        window.open_path(path)
    return application.exec()
