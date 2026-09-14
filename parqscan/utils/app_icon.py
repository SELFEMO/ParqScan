from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon

from parqscan.utils.paths import resource_path

_ICON_PROBE_SIZE = 64


def _icon_candidate_paths() -> list[Path]:
    resources = resource_path("resources")
    if sys.platform.startswith("win"):
        return [
            resources / "ParqScan.ico",
            resources / "ParqScan.png",
            resources / "ParqScan.svg",
        ]
    return [
        resources / "ParqScan.svg",
        resources / "ParqScan.png",
    ]


def _icon_from_path(path: Path) -> QIcon | None:
    icon = QIcon(str(path))
    if icon.isNull() or icon.pixmap(_ICON_PROBE_SIZE, _ICON_PROBE_SIZE).isNull():
        return None
    return icon


def create_app_icon() -> QIcon:
    tried_paths: list[Path] = []
    for path in _icon_candidate_paths():
        tried_paths.append(path)
        icon = _icon_from_path(path)
        if icon is not None:
            return icon
    joined = ", ".join(str(path) for path in tried_paths)
    raise RuntimeError(f"Application icon could not be loaded from {joined}")
