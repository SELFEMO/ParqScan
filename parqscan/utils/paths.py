from __future__ import annotations

import sys
from pathlib import Path


def package_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / "parqscan"
    return Path(__file__).resolve().parents[1]


def resource_path(*parts: str) -> Path:
    return package_root().joinpath(*parts)
