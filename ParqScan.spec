# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os
import sys

from PyInstaller.compat import is_pure_conda
from PyInstaller.utils.hooks import collect_dynamic_libs
from PyInstaller.utils.hooks.qt import pyside6_library_info


ROOT = Path(SPECPATH).resolve()
BUILD_ONEFILE = os.environ.get("PARQSCAN_BUILD_ONEFILE", "0") == "1"
BUILD_DEBUG = os.environ.get("PARQSCAN_BUILD_DEBUG", "0") == "1"
IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"

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
        target_arch=None,
        codesign_identity=None,
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
        icon=None,
        bundle_identifier="ParqScan.Desktop",
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
        console=BUILD_DEBUG if IS_WINDOWS else True,
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
        console=BUILD_DEBUG if IS_WINDOWS else True,
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
