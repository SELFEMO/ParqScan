from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SPEC_FILE = ROOT / "ParqScan.spec"
DIST_DIRECTORY = ROOT / "dist"


@dataclass(frozen=True)
class BuildOptions:
    onefile: bool = False
    debug: bool = False
    skip_smoke_test: bool = False


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
    namespace = parser.parse_args(arguments)
    return BuildOptions(
        onefile=namespace.onefile,
        debug=namespace.debug,
        skip_smoke_test=namespace.skip_smoke_test,
    )


def ensure_pyinstaller() -> None:
    if importlib.util.find_spec("PyInstaller") is not None:
        return
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def validate_runtime_dependencies() -> None:
    required_modules = ("PySide6", "PySide6.QtSvg", "pyarrow", "openpyxl", "psutil")
    missing = [module_name for module_name in required_modules if importlib.util.find_spec(module_name) is None]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Missing runtime dependencies: {joined}. "
            f"Install them with: {sys.executable} -m pip install -r {ROOT / 'requirements.txt'}"
        )


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
    ensure_pyinstaller()
    validate_runtime_dependencies()
    validate_build_inputs()
    result = subprocess.call(build_arguments(options), cwd=ROOT, env=build_environment(options))
    if result != 0:
        return result
    if not options.skip_smoke_test:
        run_smoke_test(options)
    print(f"Build completed: {packaged_executable(options)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
