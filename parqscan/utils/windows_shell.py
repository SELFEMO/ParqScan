from __future__ import annotations

import ctypes
import sys

WINDOWS_APP_USER_MODEL_ID = "ParqScan.Desktop"


def set_windows_app_user_model_id(app_id: str = WINDOWS_APP_USER_MODEL_ID) -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass
