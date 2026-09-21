from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SPEC_FILE = ROOT / "ParqScan.spec"
DIST_DIRECTORY = ROOT / "dist"
INSTALLER_SCRIPT = ROOT / "packaging" / "inno" / "ParqScan.iss"
WINDOWS_INSTALLER_NAME = "ParqScan-Windows-Setup.exe"
INNO_SETUP_DOWNLOAD_URL = "https://jrsoftware.org/isdl.php"
INNO_SETUP_INSTALL_HINT = (
    "Install Inno Setup 6, then rerun the installer step. Options:\n"
    f"- Download: {INNO_SETUP_DOWNLOAD_URL}\n"
    "- winget: winget install --id JRSoftware.InnoSetup -e\n"
    "- choco: choco install innosetup -y\n"
    "- Or set ISCC to the full path of ISCC.exe"
)
BLOAT_MODULES = (
    "pandas",
    "notebook",
    "IPython",
    "matplotlib",
    "scipy",
    "sklearn",
    "bokeh",
    "sympy",
    "statsmodels",
    "numba",
    "dask",
    "plotly",
)
ONEDIR_SIZE_LIMIT_MB = 600
CONDA_PYTHON_HINT = (
    "Release builds require a non-Conda Python (for example python.org 3.12). "
    "Install one with: winget install --id Python.Python.3.12 -e "
    "Then rerun scripts/build_windows.ps1 or set PARQSCAN_BUILD_PYTHON to its python.exe path."
)


@dataclass(frozen=True)
class BuildOptions:
    onefile: bool = False
    debug: bool = False
    skip_smoke_test: bool = False
    installer: bool = False
    installer_only: bool = False


def parse_arguments(arguments: list[str] | None = None) -> BuildOptions:
    parser = argparse.ArgumentParser(description="Build ParqScan with PyInstaller.")
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Build a single executable instead of the default onedir package.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Keep a console window and enable PyInstaller bootloader diagnostics.",
    )
    parser.add_argument(
        "--skip-smoke-test",
        action="store_true",
        help="Skip launching the packaged application after the build.",
    )
    parser.add_argument(
        "--installer",
        action="store_true",
        help="After packaging, build the Windows Inno Setup installer (Windows only).",
    )
    parser.add_argument(
        "--installer-only",
        action="store_true",
        help="Build only the Windows installer from an existing dist/ParqScan output.",
    )
    namespace = parser.parse_args(arguments)
    installer = namespace.installer or namespace.installer_only
    return BuildOptions(
        onefile=namespace.onefile,
        debug=namespace.debug,
        skip_smoke_test=namespace.skip_smoke_test,
        installer=installer,
        installer_only=namespace.installer_only,
    )


def ensure_pyinstaller() -> None:
    if importlib.util.find_spec("PyInstaller") is not None:
        return
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def validate_runtime_dependencies() -> None:
    simple_modules = ("pyarrow", "openpyxl", "psutil")
    missing = [module_name for module_name in simple_modules if importlib.util.find_spec(module_name) is None]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Missing runtime dependencies: {joined}. "
            f"Install them with: {sys.executable} -m pip install -r {ROOT / 'requirements.txt'}"
        )

    try:
        import PySide6.QtCore  # noqa: F401
        import PySide6.QtSvg  # noqa: F401
    except ImportError as error:
        message = str(error)
        requirements_hint = f"{sys.executable} -m pip install -r {ROOT / 'requirements.txt'}"
        if "shiboken" in message.casefold():
            install_hint = (
                "PySide6 looks incomplete, often because pip was run with --no-deps. "
                f"Reinstall with: {sys.executable} -m pip install --force-reinstall PySide6 "
                f"or {requirements_hint}"
            )
        else:
            install_hint = f"Install with: {requirements_hint}"
        raise RuntimeError(f"PySide6 could not be imported: {error}. {install_hint}") from error


def is_conda_python() -> bool:
    prefix = Path(sys.prefix)
    if (prefix / "conda-meta").exists():
        return True
    executable = Path(sys.executable).as_posix().casefold()
    return "conda" in executable or "anaconda" in executable


def validate_build_environment(strict: bool | None = None) -> None:
    enforce = strict if strict is not None else os.environ.get("PARQSCAN_STRICT_BUILD", "").strip() in {"1", "true", "yes"}
    if is_conda_python():
        message = (
            "Conda Python was detected in the build environment. "
            "venv copies of Conda still inherit broken Qt DLL resolution and oversized artifacts. "
            f"{CONDA_PYTHON_HINT}"
        )
        if enforce:
            raise RuntimeError(message)
        print(f"WARNING: {message}", file=sys.stderr)

    found = [module_name for module_name in BLOAT_MODULES if importlib.util.find_spec(module_name) is not None]
    if not found:
        return
    joined = ", ".join(found)
    message = (
        f"Detected non-runtime packages in the build environment: {joined}. "
        "They can inflate the frozen artifact to over 1 GB. "
        f"Use scripts/build_windows.ps1 or a clean pip virtual environment before packaging."
    )
    if enforce:
        raise RuntimeError(message)
    print(f"WARNING: {message}", file=sys.stderr)


def directory_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def validate_packaged_size(options: BuildOptions | None = None) -> int:
    selected = options or BuildOptions()
    if effective_onefile(selected):
        packaged = packaged_executable(selected)
        size_bytes = packaged.stat().st_size if packaged.is_file() else 0
    else:
        size_bytes = directory_size_bytes(DIST_DIRECTORY / "ParqScan")
    size_mb = size_bytes / (1024 * 1024)
    if size_mb > ONEDIR_SIZE_LIMIT_MB:
        raise RuntimeError(
            f"Packaged artifact is {size_mb:.1f} MB, which exceeds the {ONEDIR_SIZE_LIMIT_MB} MB limit. "
            "Rebuild from a clean pip virtual environment."
        )
    return size_bytes


def validate_build_inputs() -> None:
    required_paths = (
        SPEC_FILE,
        ROOT / "main.py",
        ROOT / "parqscan" / "resources" / "ParqScan.svg",
        ROOT / "parqscan" / "resources" / "ParqScan.png",
        ROOT / "parqscan" / "resources" / "ParqScan.ico",
        ROOT / "parqscan" / "resources" / "release.json",
        ROOT / "parqscan" / "locales" / "en.json",
        ROOT / "parqscan" / "locales" / "zh.json",
        ROOT / "parqscan" / "styles" / "light.qss",
        ROOT / "parqscan" / "styles" / "dark.qss",
    )
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        joined = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"Required build files are missing:\n{joined}")


def effective_onefile(options: BuildOptions | None = None) -> bool:
    selected = options or BuildOptions()
    # Windows 默认使用 onedir，避免大型 Qt/PyArrow 单文件首次解压或安全软件扫描表现为“无响应”；Linux 仍保持原需求的一体化输出。
    # Windows defaults to onedir so large Qt/PyArrow extraction or antivirus scanning does not look like a hang; Linux keeps the original single-file output.
    return selected.onefile or (not sys.platform.startswith("win") and sys.platform != "darwin")


def build_arguments(options: BuildOptions | None = None) -> list[str]:
    selected = options or BuildOptions()
    arguments = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--log-level",
        "INFO",
    ]
    arguments.append(str(SPEC_FILE))
    return arguments


def build_environment(options: BuildOptions | None = None) -> dict[str, str]:
    selected = options or BuildOptions()
    environment = os.environ.copy()

    # 将 Qt 抽象层固定为 PySide6，避免 Conda 中其他 Qt 绑定通过可选依赖干扰分析或运行时插件路径。
    # Pinning the Qt abstraction layer to PySide6 prevents other Conda Qt bindings from interfering through optional imports or plugin paths.
    environment["QT_API"] = "pyside6"
    environment["PARQSCAN_BUILD_ONEFILE"] = "1" if effective_onefile(selected) else "0"
    environment["PARQSCAN_BUILD_DEBUG"] = "1" if selected.debug else "0"
    return environment


def read_release_version() -> str:
    payload = json.loads((ROOT / "parqscan" / "resources" / "release.json").read_text(encoding="utf-8"))
    value = payload.get("release") if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("parqscan/resources/release.json must define a non-empty release string.")
    return value.strip()


def installer_executable() -> Path:
    return DIST_DIRECTORY / "installer" / WINDOWS_INSTALLER_NAME


def _iscc_candidates_from_registry() -> list[Path]:
    if not sys.platform.startswith("win"):
        return []
    try:
        import winreg
    except ImportError:
        return []

    candidates: list[Path] = []
    registry_paths = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
        ),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"),
    )
    for hive, subkey in registry_paths:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                install_location, _ = winreg.QueryValueEx(key, "InstallLocation")
        except OSError:
            continue
        if isinstance(install_location, str) and install_location.strip():
            candidates.append(Path(install_location.strip()) / "ISCC.exe")
    return candidates


def find_iscc() -> Path:
    candidates: list[Path] = []
    for environment_name in ("ISCC", "INNO_SETUP_HOME"):
        environment_path = os.environ.get(environment_name, "").strip()
        if not environment_path:
            continue
        path = Path(environment_path)
        candidates.append(path if path.suffix.lower() == ".exe" else path / "ISCC.exe")

    candidates.extend(_iscc_candidates_from_registry())
    candidates.extend(
        [
            Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
            Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
            Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe")),
        ]
    )

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve() if candidate.exists() else candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        if candidate.is_file():
            return candidate

    discovered = shutil.which("ISCC")
    if discovered:
        return Path(discovered)

    raise FileNotFoundError(
        "Inno Setup compiler (ISCC.exe) was not found.\n" + INNO_SETUP_INSTALL_HINT
    )


def build_installer() -> Path:
    if not sys.platform.startswith("win"):
        raise RuntimeError("--installer is only supported on Windows.")

    packaged = packaged_executable(BuildOptions())
    if not packaged.is_file():
        raise FileNotFoundError(f"Packaged executable was not created: {packaged}")
    if not INSTALLER_SCRIPT.is_file():
        raise FileNotFoundError(f"Installer script was not found: {INSTALLER_SCRIPT}")

    iscc = find_iscc()
    version = read_release_version()
    subprocess.check_call(
        [str(iscc), f"/DAppVersion={version}", str(INSTALLER_SCRIPT)],
        cwd=ROOT,
    )
    output = installer_executable()
    if not output.is_file():
        raise FileNotFoundError(f"Installer was not created: {output}")
    return output


def packaged_executable(options: BuildOptions | None = None) -> Path:
    selected = options or BuildOptions()
    executable_name = "ParqScan.exe" if sys.platform.startswith("win") else "ParqScan"
    if sys.platform == "darwin":
        return DIST_DIRECTORY / "ParqScan.app" / "Contents" / "MacOS" / "ParqScan"
    if effective_onefile(selected):
        return DIST_DIRECTORY / executable_name
    return DIST_DIRECTORY / "ParqScan" / executable_name


def run_smoke_test(options: BuildOptions | None = None) -> None:
    selected = options or BuildOptions()
    executable = packaged_executable(selected)
    if not executable.is_file():
        raise FileNotFoundError(f"Packaged executable was not created: {executable}")

    environment = os.environ.copy()
    if not sys.platform.startswith("win"):
        environment["QT_QPA_PLATFORM"] = "offscreen"

    # 构建完成后立即启动打包产物，可以在交付前发现缺失 DLL、Qt 平台插件或资源路径错误，而不是留下一个双击后无反应的文件。
    # Launching the packaged artifact immediately catches missing DLLs, Qt platform plugins, and resource path failures before delivery instead of leaving a silent executable.
    completed = subprocess.run(
        [str(executable), "--smoke-test"],
        cwd=executable.parent,
        env=environment,
        timeout=240,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Packaged application smoke test failed with exit code "
            f"{completed.returncode}. Check the startup log under the ParqScan application data directory."
        )


def main(arguments: list[str] | None = None) -> int:
    options = parse_arguments(arguments)

    if options.installer_only:
        installer_path = build_installer()
        print(f"Installer completed: {installer_path}")
        return 0

    ensure_pyinstaller()
    validate_runtime_dependencies()
    validate_build_environment()
    validate_build_inputs()
    result = subprocess.call(build_arguments(options), cwd=ROOT, env=build_environment(options))
    if result != 0:
        return result
    packaged_size = validate_packaged_size(options)
    if not options.skip_smoke_test:
        run_smoke_test(options)
    print(f"Build completed: {packaged_executable(options)} ({packaged_size / (1024 * 1024):.1f} MB)")

    if options.installer:
        installer_path = build_installer()
        print(f"Installer completed: {installer_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
