# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import json
import os
import platform
import sys

from PyInstaller.compat import is_pure_conda
from PyInstaller.utils.hooks import collect_dynamic_libs
from PyInstaller.utils.hooks.qt import pyside6_library_info


ROOT = Path(SPECPATH).resolve()
BUILD_ONEFILE = os.environ.get("PARQSCAN_BUILD_ONEFILE", "0") == "1"
BUILD_DEBUG = os.environ.get("PARQSCAN_BUILD_DEBUG", "0") == "1"
IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def _read_app_version() -> str:
    release_file = ROOT / "parqscan" / "resources" / "release.json"
    try:
        payload = json.loads(release_file.read_text(encoding="utf-8"))
        value = payload.get("release") if isinstance(payload, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    except OSError:
        pass
    return "0.0.0"


APP_VERSION = _read_app_version()

# 项目运行时只依赖 PySide6；排除其他 Qt 绑定可防止同一冻结产物混入多套互不兼容的 Qt 插件。
# The runtime depends only on PySide6; excluding other bindings prevents incompatible Qt plugin sets from entering the same frozen artifact.
EXCLUDED_MODULES = [
    "PyQt5",
    "PyQt6",
    "PySide2",
    "pyarrow.tests",
    "pandas",
    "pandas.tests",
    "numpy.distutils",
    "scipy",
    "matplotlib",
    "sklearn",
    "bokeh",
    "plotly",
    "dask",
    "distributed",
    "notebook",
    "jupyter",
    "IPython",
    "sympy",
    "statsmodels",
    "numba",
    "llvmlite",
    "pytest",
    "sphinx",
]

DATAS = [
    (str(ROOT / "parqscan" / "resources"), "parqscan/resources"),
    (str(ROOT / "parqscan" / "locales"), "parqscan/locales"),
    (str(ROOT / "parqscan" / "styles"), "parqscan/styles"),
]

HIDDEN_IMPORTS = [
    "PySide6.QtSvg",
]

# 显式收集图标引擎与图片格式插件，避免冻结产物在缺少 qsvgicon/qpng/qico 时无法渲染 SVG/PNG 图标。
# Collect icon engine and image format plugins explicitly so frozen builds can still render SVG/PNG icons when plugin discovery is incomplete.
def _collect_qt_plugins(plugin_type: str) -> list:
    try:
        return pyside6_library_info.collect_plugins(plugin_type)
    except Exception as error:
        print(f"WARNING: Unable to collect PySide6 {plugin_type} plugins: {error}")
        return []


QT_PLUGIN_BINARIES = _collect_qt_plugins("iconengines") + _collect_qt_plugins("imageformats")
if IS_MACOS:
    QT_PLUGIN_BINARIES += _collect_qt_plugins("platforms") + _collect_qt_plugins("styles")
elif IS_LINUX:
    QT_PLUGIN_BINARIES += _collect_qt_plugins("platforms") + _collect_qt_plugins("platformthemes")

# 官方 PyArrow hook 只收集 pyarrow 包目录内的 DLL；Conda 会把 Arrow 及其依赖放在 Library/bin，因此需额外收集该发行包的共享库依赖。
# The official PyArrow hook only collects DLLs inside the pyarrow package; Conda stores Arrow and its dependencies in Library/bin, so those distribution DLLs must be added separately.
PYARROW_BINARIES = collect_dynamic_libs("pyarrow")
if is_pure_conda:
    print("Building from Conda; expect larger artifacts. Prefer a clean pip virtual environment.")
    try:
        from PyInstaller.utils.hooks import conda_support

        PYARROW_BINARIES += conda_support.collect_dynamic_libs(
            "pyarrow",
            dest=".",
            dependencies=True,
            excludes={"python", "pyside6", "pyqt", "pyqt6", "qt-main", "qt6-main"},
        )
    except Exception as error:
        print(f"WARNING: Unable to collect Conda PyArrow DLL dependencies explicitly: {error}")

WINDOWS_ICON = str(ROOT / "parqscan" / "resources" / "ParqScan.ico") if IS_WINDOWS else None
MACOS_ICON_PATH = ROOT / "parqscan" / "resources" / "ParqScan.icns"
MACOS_ICON = str(MACOS_ICON_PATH) if IS_MACOS and MACOS_ICON_PATH.is_file() else None
MACOS_TARGET_ARCH = (
    os.environ.get("PARQSCAN_TARGET_ARCH", "").strip()
    or ("arm64" if IS_MACOS and platform.machine().lower() in {"arm64", "aarch64"} else None)
)
MACOS_INFO_PLIST = {
    "CFBundleName": "ParqScan",
    "CFBundleDisplayName": "ParqScan",
    "CFBundleIdentifier": "io.github.selfemo.parqscan",
    "CFBundleShortVersionString": APP_VERSION,
    "CFBundleVersion": APP_VERSION,
    "NSHighResolutionCapable": True,
    "LSMinimumSystemVersion": "12.0",
    "LSApplicationCategoryType": "public.app-category.developer-tools",
    "CFBundleDocumentTypes": [
        {
            "CFBundleTypeName": "Apache Parquet File",
            "CFBundleTypeRole": "Viewer",
            "LSHandlerRank": "Alternate",
            "CFBundleTypeExtensions": ["parquet", "parq", "pq"],
            "CFBundleTypeMIMETypes": ["application/vnd.apache.parquet", "application/x-parquet"],
        }
    ],
}

analysis = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=PYARROW_BINARIES + QT_PLUGIN_BINARIES,
    datas=DATAS,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_MODULES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

if IS_MACOS:
    executable = EXE(
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name="ParqScan",
        debug=BUILD_DEBUG,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=BUILD_DEBUG,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=MACOS_TARGET_ARCH,
        codesign_identity=os.environ.get("PARQSCAN_CODESIGN_IDENTITY") or None,
        entitlements_file=None,
    )
    collection = COLLECT(
        executable,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="ParqScan",
    )
    app = BUNDLE(
        collection,
        name="ParqScan.app",
        icon=MACOS_ICON,
        bundle_identifier="io.github.selfemo.parqscan",
        info_plist=MACOS_INFO_PLIST,
    )
elif BUILD_ONEFILE:
    executable = EXE(
        pyz,
        analysis.scripts,
        analysis.binaries,
        analysis.datas,
        [],
        name="ParqScan",
        debug=BUILD_DEBUG,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=BUILD_DEBUG,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=WINDOWS_ICON,
    )
else:
    executable = EXE(
        pyz,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name="ParqScan",
        debug=BUILD_DEBUG,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=BUILD_DEBUG,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=WINDOWS_ICON,
    )
    collection = COLLECT(
        executable,
        analysis.binaries,
        analysis.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="ParqScan",
    )
