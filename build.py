from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SPEC_FILE = ROOT / "ParqScan.spec"
DIST_DIRECTORY = ROOT / "dist"
INSTALLER_SCRIPT = ROOT / "packaging" / "inno" / "ParqScan.iss"
LINUX_PACKAGING_DIR = ROOT / "packaging" / "linux"
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
    "Then rerun scripts/build_windows.ps1 (or scripts/build_macos.sh / scripts/build_linux.sh) "
    "or set PARQSCAN_BUILD_PYTHON to its Python executable path."
)


@dataclass(frozen=True)
class BuildOptions:
    onefile: bool = False
    debug: bool = False
    skip_smoke_test: bool = False
    installer: bool = False
    installer_only: bool = False
    package_format: str = "auto"


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
        help="After packaging, build the platform installer (.exe on Windows, .dmg on macOS, .deb/.rpm on Linux).",
    )
    parser.add_argument(
        "--installer-only",
        action="store_true",
        help="Build only the platform installer from an existing dist/ParqScan or dist/ParqScan.app output.",
    )
    parser.add_argument(
        "--package-format",
        choices=("auto", "exe", "dmg", "deb", "rpm", "all"),
        default="auto",
        help="Select installer package format (auto detects by platform; Linux supports deb, rpm, or all).",
    )
    namespace = parser.parse_args(arguments)
    installer = namespace.installer or namespace.installer_only
    return BuildOptions(
        onefile=namespace.onefile,
        debug=namespace.debug,
        skip_smoke_test=namespace.skip_smoke_test,
        installer=installer,
        installer_only=namespace.installer_only,
        package_format=namespace.package_format,
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
        "Use a clean pip virtual environment before packaging."
    )
    if enforce:
        raise RuntimeError(message)
    print(f"WARNING: {message}", file=sys.stderr)


def directory_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            total += child.stat().st_size
    return total


def packaged_artifact_root(options: BuildOptions | None = None) -> Path:
    selected = options or BuildOptions()
    if sys.platform == "darwin":
        return DIST_DIRECTORY / "ParqScan.app"
    if effective_onefile(selected):
        return packaged_executable(selected)
    return DIST_DIRECTORY / "ParqScan"


def validate_packaged_size(options: BuildOptions | None = None) -> int:
    selected = options or BuildOptions()
    target = packaged_artifact_root(selected)
    if effective_onefile(selected) and sys.platform != "darwin":
        size_bytes = target.stat().st_size if target.is_file() else 0
    else:
        size_bytes = directory_size_bytes(target)
    size_mb = size_bytes / (1024 * 1024)
    if size_mb > ONEDIR_SIZE_LIMIT_MB:
        raise RuntimeError(
            f"Packaged artifact is {size_mb:.1f} MB, which exceeds the {ONEDIR_SIZE_LIMIT_MB} MB limit. "
            "Rebuild from a clean pip virtual environment."
        )
    return size_bytes


def validate_build_inputs() -> None:
    required_paths = [
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
    ]
    if sys.platform == "darwin":
        required_paths.append(ROOT / "parqscan" / "resources" / "ParqScan.icns")
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        joined = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"Required build files are missing:\n{joined}")


def effective_onefile(options: BuildOptions | None = None) -> bool:
    selected = options or BuildOptions()
    # 全平台默认使用 onedir（macOS 为 .app bundle，Linux 用于 .deb/.rpm 安装到 /opt/parqscan），避免单文件每次启动解压带来的冷启动延迟。
    # All platforms default to onedir (macOS uses .app bundle, Linux installs into /opt/parqscan via .deb/.rpm) to avoid onefile extraction overhead on launch.
    if sys.platform == "darwin":
        return False
    return selected.onefile


def build_arguments(options: BuildOptions | None = None) -> list[str]:
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


def normalized_macos_arch() -> str:
    machine = (os.environ.get("PARQSCAN_TARGET_ARCH") or platform.machine()).strip().lower()
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    return machine or "arm64"


def normalized_linux_deb_arch() -> str:
    machine = platform.machine().strip().lower()
    if machine in {"x86_64", "amd64"}:
        return "amd64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    return machine or "amd64"


def normalized_linux_rpm_arch() -> str:
    machine = platform.machine().strip().lower()
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "aarch64"
    return machine or "x86_64"


def macos_dmg_name() -> str:
    return f"ParqScan-macOS-{normalized_macos_arch()}.dmg"


def linux_deb_name() -> str:
    return f"ParqScan-Linux-{normalized_linux_deb_arch()}.deb"


def linux_rpm_name() -> str:
    return f"ParqScan-Linux-{normalized_linux_rpm_arch()}.rpm"


def installer_executable(package_format: str = "auto") -> Path:
    if package_format == "dmg" or (package_format == "auto" and sys.platform == "darwin"):
        return DIST_DIRECTORY / "installer" / macos_dmg_name()
    if package_format == "deb":
        return DIST_DIRECTORY / "installer" / linux_deb_name()
    if package_format == "rpm":
        return DIST_DIRECTORY / "installer" / linux_rpm_name()
    if package_format == "auto" and sys.platform.startswith("linux"):
        return DIST_DIRECTORY / "installer" / linux_deb_name()
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


def _build_windows_installer() -> Path:
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
    output = installer_executable("exe")
    if not output.is_file():
        raise FileNotFoundError(f"Installer was not created: {output}")
    return output


def build_macos_dmg() -> Path:
    if sys.platform != "darwin":
        raise RuntimeError("macOS .dmg installer can only be built on macOS.")
    app_bundle = DIST_DIRECTORY / "ParqScan.app"
    if not app_bundle.is_dir():
        raise FileNotFoundError(f"Packaged macOS app bundle was not created: {app_bundle}")

    hdiutil = shutil.which("hdiutil")
    if not hdiutil:
        raise FileNotFoundError("hdiutil was not found. macOS disk image creation requires /usr/bin/hdiutil.")

    codesign = shutil.which("codesign")
    if codesign:
        identity = os.environ.get("PARQSCAN_CODESIGN_IDENTITY", "").strip() or "-"
        subprocess.check_call([codesign, "--force", "--deep", "--sign", identity, str(app_bundle)])

    output = installer_executable("dmg")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with tempfile.TemporaryDirectory(prefix="parqscan-dmg-") as temp_dir:
        staging = Path(temp_dir) / "staging"
        staging.mkdir(parents=True, exist_ok=True)
        shutil.copytree(app_bundle, staging / "ParqScan.app", symlinks=True)
        os.symlink("/Applications", staging / "Applications")
        subprocess.check_call(
            [
                hdiutil,
                "create",
                "-volname",
                "ParqScan",
                "-srcfolder",
                str(staging),
                "-ov",
                "-format",
                "UDZO",
                str(output),
            ],
            cwd=ROOT,
        )

    if not output.is_file():
        raise FileNotFoundError(f"macOS DMG was not created: {output}")
    return output


def _linux_post_install_script() -> str:
    return (
        "#!/bin/sh\n"
        "set -e\n"
        "if command -v update-desktop-database >/dev/null 2>&1; then\n"
        "    update-desktop-database -q /usr/share/applications || true\n"
        "fi\n"
        "if command -v update-mime-database >/dev/null 2>&1; then\n"
        "    update-mime-database /usr/share/mime >/dev/null 2>&1 || true\n"
        "fi\n"
        "if command -v gtk-update-icon-cache >/dev/null 2>&1; then\n"
        "    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true\n"
        "fi\n"
    )


def build_linux_deb() -> Path:
    if not sys.platform.startswith("linux"):
        raise RuntimeError("Linux .deb package can only be built on Linux.")
    source_dir = DIST_DIRECTORY / "ParqScan"
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Packaged onedir directory was not created: {source_dir}")
    dpkg_deb = shutil.which("dpkg-deb")
    if not dpkg_deb:
        raise FileNotFoundError("dpkg-deb was not found. Install dpkg to build .deb packages.")

    version = read_release_version()
    arch = normalized_linux_deb_arch()
    installed_kb = max(1, directory_size_bytes(source_dir) // 1024)
    output = installer_executable("deb")
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="parqscan-deb-") as temp_dir:
        pkg_root = Path(temp_dir) / f"parqscan_{version}_{arch}"
        debian_dir = pkg_root / "DEBIAN"
        opt_dir = pkg_root / "opt" / "parqscan"
        bin_dir = pkg_root / "usr" / "bin"
        apps_dir = pkg_root / "usr" / "share" / "applications"
        mime_dir = pkg_root / "usr" / "share" / "mime" / "packages"
        icon_svg_dir = pkg_root / "usr" / "share" / "icons" / "hicolor" / "scalable" / "apps"
        icon_png_dir = pkg_root / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps"

        for directory in (debian_dir, bin_dir, apps_dir, mime_dir, icon_svg_dir, icon_png_dir):
            directory.mkdir(parents=True, exist_ok=True)

        shutil.copytree(source_dir, opt_dir, symlinks=True)
        binary = opt_dir / "ParqScan"
        if binary.is_file():
            binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.symlink("/opt/parqscan/ParqScan", bin_dir / "parqscan")

        shutil.copy2(LINUX_PACKAGING_DIR / "parqscan.desktop", apps_dir / "parqscan.desktop")
        shutil.copy2(LINUX_PACKAGING_DIR / "parqscan-mime.xml", mime_dir / "parqscan.xml")
        shutil.copy2(ROOT / "parqscan" / "resources" / "ParqScan.svg", icon_svg_dir / "parqscan.svg")
        shutil.copy2(ROOT / "parqscan" / "resources" / "ParqScan.png", icon_png_dir / "parqscan.png")

        control_content = (
            "Package: parqscan\n"
            f"Version: {version}\n"
            "Section: utils\n"
            "Priority: optional\n"
            f"Architecture: {arch}\n"
            f"Installed-Size: {installed_kb}\n"
            "Maintainer: ParqScan Contributors <https://github.com/SELFEMO/ParqScan>\n"
            "Homepage: https://github.com/SELFEMO/ParqScan\n"
            "Description: Desktop inspector and converter for Apache Parquet files\n"
            " ParqScan reads one page at a time without materializing full datasets\n"
            " into memory, with embedded image preview and binary inspection.\n"
        )
        (debian_dir / "control").write_text(control_content, encoding="utf-8")

        script = _linux_post_install_script()
        for hook_name in ("postinst", "postrm"):
            hook_path = debian_dir / hook_name
            hook_path.write_text(script, encoding="utf-8")
            hook_path.chmod(0o755)

        subprocess.check_call(
            [dpkg_deb, "--build", "--root-owner-group", str(pkg_root), str(output)],
            cwd=ROOT,
        )

    if not output.is_file():
        raise FileNotFoundError(f"Linux DEB package was not created: {output}")
    return output


def build_linux_rpm() -> Path:
    if not sys.platform.startswith("linux"):
        raise RuntimeError("Linux .rpm package can only be built on Linux.")
    source_dir = DIST_DIRECTORY / "ParqScan"
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Packaged onedir directory was not created: {source_dir}")
    rpmbuild = shutil.which("rpmbuild")
    if not rpmbuild:
        raise FileNotFoundError("rpmbuild was not found. Install rpm-build (or rpm) to build .rpm packages.")
    spec_template = LINUX_PACKAGING_DIR / "parqscan.spec.in"
    if not spec_template.is_file():
        raise FileNotFoundError(f"RPM spec template was not found: {spec_template}")

    version = read_release_version()
    output = installer_executable("rpm")
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="parqscan-rpm-") as temp_dir:
        topdir = Path(temp_dir) / "rpmbuild"
        for sub in ("BUILD", "RPMS", "SOURCES", "SPECS", "SRPMS"):
            (topdir / sub).mkdir(parents=True, exist_ok=True)
        rendered = (
            spec_template.read_text(encoding="utf-8")
            .replace("@VERSION@", version)
            .replace("@SOURCE_DIR@", str(source_dir.resolve()))
            .replace("@DESKTOP_FILE@", str((LINUX_PACKAGING_DIR / "parqscan.desktop").resolve()))
            .replace("@MIME_FILE@", str((LINUX_PACKAGING_DIR / "parqscan-mime.xml").resolve()))
            .replace("@ICON_SVG@", str((ROOT / "parqscan" / "resources" / "ParqScan.svg").resolve()))
            .replace("@ICON_PNG@", str((ROOT / "parqscan" / "resources" / "ParqScan.png").resolve()))
        )
        spec_path = topdir / "SPECS" / "parqscan.spec"
        spec_path.write_text(rendered, encoding="utf-8")
        subprocess.check_call(
            [rpmbuild, "-bb", "--define", f"_topdir {topdir}", str(spec_path)],
            cwd=ROOT,
        )
        rpms = sorted((topdir / "RPMS").rglob("*.rpm"))
        if not rpms:
            raise FileNotFoundError("rpmbuild completed without producing an .rpm artifact.")
        shutil.copy2(rpms[0], output)

    if not output.is_file():
        raise FileNotFoundError(f"Linux RPM package was not created: {output}")
    return output


def build_installers(package_format: str = "auto") -> list[Path]:
    if sys.platform.startswith("win"):
        if package_format not in {"auto", "exe", "all"}:
            raise RuntimeError(f"Package format '{package_format}' is not supported on Windows.")
        return [_build_windows_installer()]
    if sys.platform == "darwin":
        if package_format not in {"auto", "dmg", "all"}:
            raise RuntimeError(f"Package format '{package_format}' is not supported on macOS.")
        return [build_macos_dmg()]
    if sys.platform.startswith("linux"):
        if package_format == "deb":
            return [build_linux_deb()]
        if package_format == "rpm":
            return [build_linux_rpm()]
        if package_format == "all":
            return [build_linux_deb(), build_linux_rpm()]
        if package_format == "auto":
            outputs: list[Path] = []
            if shutil.which("dpkg-deb"):
                outputs.append(build_linux_deb())
            if shutil.which("rpmbuild"):
                outputs.append(build_linux_rpm())
            if not outputs:
                raise FileNotFoundError(
                    "Neither dpkg-deb nor rpmbuild was found on Linux. "
                    "Install dpkg (for .deb) or rpm / rpm-build (for .rpm)."
                )
            return outputs
        raise RuntimeError(f"Package format '{package_format}' is not supported on Linux.")
    raise RuntimeError(f"--installer is not supported on platform '{sys.platform}'.")


def build_installer(package_format: str = "auto") -> Path:
    return build_installers(package_format)[0]


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
        installer_paths = build_installers(options.package_format)
        for installer_path in installer_paths:
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
        installer_paths = build_installers(options.package_format)
        for installer_path in installer_paths:
            print(f"Installer completed: {installer_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
