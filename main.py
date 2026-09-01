from __future__ import annotations

import atexit
import ctypes
import datetime as dt
import faulthandler
import os
import sys
import traceback
from pathlib import Path
from typing import IO, Sequence


_FAULT_LOG_STREAM: IO[str] | None = None


def _application_data_directory() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "ParqScan"


def _startup_log_path() -> Path:
    path = _application_data_directory() / "logs" / "startup.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _prepare_windowed_standard_streams() -> None:
    # Windows 的 noconsole 启动器会把标准流设为 None；提前替换为空设备可避免第三方库在导入阶段调用 flush/write 时直接崩溃。
    # The Windows noconsole bootloader sets standard streams to None; replacing them early prevents third-party imports from crashing on flush/write calls.
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _enable_fault_logging() -> None:
    global _FAULT_LOG_STREAM
    try:
        _FAULT_LOG_STREAM = _startup_log_path().open("a", encoding="utf-8")
        _FAULT_LOG_STREAM.write(
            f"\n[{dt.datetime.now().isoformat(timespec='seconds')}] "
            f"process started; frozen={getattr(sys, 'frozen', False)}; executable={sys.executable}\n"
        )
        _FAULT_LOG_STREAM.flush()
        faulthandler.enable(file=_FAULT_LOG_STREAM, all_threads=True)
        atexit.register(_FAULT_LOG_STREAM.close)
    except OSError:
        _FAULT_LOG_STREAM = None


def _record_startup_exception(error: BaseException) -> Path | None:
    try:
        path = _startup_log_path()
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"[{dt.datetime.now().isoformat(timespec='seconds')}] startup failed\n")
            stream.write(f"Executable: {sys.executable}\n")
            stream.write(f"Frozen root: {getattr(sys, '_MEIPASS', 'N/A')}\n")
            traceback.print_exception(type(error), error, error.__traceback__, file=stream)
            stream.write("\n")
        return path
    except OSError:
        return None


def _show_startup_error(error: BaseException, log_path: Path | None) -> None:
    details = f"{type(error).__name__}: {error}"
    if log_path is not None:
        details += f"\n\n详细日志：\n{log_path}"
    message = f"ParqScan 启动失败。\n\n{details}"

    # 启动失败可能发生在 Qt 导入之前，因此 Windows 上使用系统消息框，确保 noconsole 构建也不会无声退出。
    # Startup can fail before Qt is importable, so the native Windows message box ensures noconsole builds never exit silently.
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.user32.MessageBoxW(None, message, "ParqScan", 0x10)
            return
        except Exception:
            pass
    print(message, file=sys.stderr)


def _create_app_icon():
    from PySide6.QtGui import QIcon

    from parqscan.utils.paths import resource_path

    svg_path = resource_path("resources", "ParqScan.svg")
    png_path = resource_path("resources", "ParqScan.png")
    icon = QIcon(str(svg_path))

    # SVG 仍是首选以保持高 DPI 清晰度，但打包环境缺少 SVG 图标引擎时必须回退到 PNG，避免窗口和任务栏图标为空。
    # SVG remains preferred for high-DPI clarity, but a PNG fallback prevents blank window and taskbar icons when the packaged SVG icon engine is unavailable.
    if icon.isNull() or icon.pixmap(64, 64).isNull():
        icon = QIcon(str(png_path))
    if icon.isNull() or icon.pixmap(64, 64).isNull():
        raise RuntimeError(f"Application icon could not be loaded from {svg_path} or {png_path}")
    return icon


def main(arguments: Sequence[str] | None = None) -> int:
    _prepare_windowed_standard_streams()
    _enable_fault_logging()
    args = list(arguments or sys.argv)
    smoke_test = "--smoke-test" in args
    args = [argument for argument in args if argument != "--smoke-test"]

    try:
        # 显式导入 QtSvg 让 PyInstaller 能静态发现 SVG 图标引擎，而不是依赖运行时插件探测。
        # Importing QtSvg explicitly lets PyInstaller discover the SVG icon engine statically instead of relying on runtime plugin probing.
        import PySide6.QtSvg  # noqa: F401

        from parqscan.application import run

        return run(args, _create_app_icon, smoke_test=smoke_test)
    except BaseException as error:
        log_path = _record_startup_exception(error)
        _show_startup_error(error, log_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
