from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import build


ROOT = Path(__file__).resolve().parents[1]


class BuildConfigurationTests(unittest.TestCase):
    def test_build_uses_the_versioned_spec_instead_of_regenerating_it(self) -> None:
        arguments = build.build_arguments()
        self.assertEqual(arguments[-1], str(ROOT / "ParqScan.spec"))
        self.assertNotIn("--collect-submodules", arguments)
        self.assertNotIn("--collect-all", arguments)

    def test_missing_runtime_dependencies_fail_before_the_long_build(self) -> None:
        with patch("build.importlib.util.find_spec", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Missing runtime dependencies"):
                build.validate_runtime_dependencies()

    def test_incomplete_pyside6_reports_no_deps_hint(self) -> None:
        with patch("build.importlib.util.find_spec", return_value=object()):
            with patch.dict("sys.modules", {"PySide6.QtCore": None, "PySide6.QtSvg": None}):
                with patch(
                    "builtins.__import__",
                    side_effect=ImportError("C:\\fake\\shiboken6\\libshiboken does not exist"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "--no-deps"):
                        build.validate_runtime_dependencies()

    def test_qt_api_is_pinned_to_pyside6(self) -> None:
        with patch.dict(os.environ, {"QT_API": "pyqt5"}, clear=False):
            environment = build.build_environment()
        self.assertEqual(environment["QT_API"], "pyside6")

    def test_windows_defaults_to_onedir_but_allows_onefile(self) -> None:
        with patch.object(sys, "platform", "win32"):
            self.assertFalse(build.effective_onefile(build.BuildOptions()))
            self.assertTrue(build.effective_onefile(build.BuildOptions(onefile=True)))
            default_environment = build.build_environment(build.BuildOptions())
            onefile_environment = build.build_environment(build.BuildOptions(onefile=True))
        self.assertEqual(default_environment["PARQSCAN_BUILD_ONEFILE"], "0")
        self.assertEqual(onefile_environment["PARQSCAN_BUILD_ONEFILE"], "1")

    def test_non_windows_output_modes_default_to_onedir(self) -> None:
        with patch.object(sys, "platform", "darwin"):
            self.assertFalse(build.effective_onefile(build.BuildOptions()))
            self.assertFalse(build.effective_onefile(build.BuildOptions(onefile=True)))
        with patch.object(sys, "platform", "linux"):
            self.assertFalse(build.effective_onefile(build.BuildOptions()))
            self.assertTrue(build.effective_onefile(build.BuildOptions(onefile=True)))

    def test_windows_macos_and_linux_packaging_config_are_declared_in_spec(self) -> None:
        source = (ROOT / "ParqScan.spec").read_text(encoding="utf-8")
        self.assertIn('"PySide6.QtSvg"', source)
        self.assertIn('"ParqScan.ico"', source)
        self.assertIn('"ParqScan.icns"', source)
        self.assertIn("icon=WINDOWS_ICON", source)
        self.assertIn("icon=MACOS_ICON", source)
        self.assertIn("info_plist=MACOS_INFO_PLIST", source)
        self.assertIn("CFBundleDocumentTypes", source)
        self.assertIn("NSHighResolutionCapable", source)
        self.assertIn('_collect_qt_plugins("iconengines")', source)
        self.assertIn('_collect_qt_plugins("imageformats")', source)
        self.assertIn('_collect_qt_plugins("platforms")', source)
        self.assertIn("PYARROW_BINARIES + QT_PLUGIN_BINARIES", source)

    def test_conda_pyarrow_dlls_are_collected_without_collecting_tests(self) -> None:
        source = (ROOT / "ParqScan.spec").read_text(encoding="utf-8")
        self.assertIn('collect_dynamic_libs("pyarrow")', source)
        self.assertIn("conda_support.collect_dynamic_libs(", source)
        self.assertIn('"pyarrow.tests"', source)
        self.assertNotIn("collect_submodules", source)

    def test_required_icon_and_linux_packaging_files_exist(self) -> None:
        resources = ROOT / "parqscan" / "resources"
        for filename in ("ParqScan.svg", "ParqScan.png", "ParqScan.ico", "ParqScan.icns"):
            self.assertTrue((resources / filename).is_file(), filename)
        linux_dir = ROOT / "packaging" / "linux"
        for filename in ("parqscan.desktop", "parqscan-mime.xml", "parqscan.spec.in"):
            self.assertTrue((linux_dir / filename).is_file(), filename)

    def test_packaged_path_matches_build_mode(self) -> None:
        with patch.object(sys, "platform", "win32"):
            onedir = build.packaged_executable(build.BuildOptions())
            onefile = build.packaged_executable(build.BuildOptions(onefile=True))
        self.assertEqual(onedir, ROOT / "dist" / "ParqScan" / "ParqScan.exe")
        self.assertEqual(onefile, ROOT / "dist" / "ParqScan.exe")
        with patch.object(sys, "platform", "darwin"):
            mac_bin = build.packaged_executable(build.BuildOptions())
        self.assertEqual(mac_bin, ROOT / "dist" / "ParqScan.app" / "Contents" / "MacOS" / "ParqScan")
        with patch.object(sys, "platform", "linux"):
            linux_onedir = build.packaged_executable(build.BuildOptions())
            linux_onefile = build.packaged_executable(build.BuildOptions(onefile=True))
        self.assertEqual(linux_onedir, ROOT / "dist" / "ParqScan" / "ParqScan")
        self.assertEqual(linux_onefile, ROOT / "dist" / "ParqScan")

    def test_installer_and_package_format_flags_are_parsed(self) -> None:
        options = build.parse_arguments(["--installer", "--package-format", "deb", "--skip-smoke-test"])
        self.assertTrue(options.installer)
        self.assertTrue(options.skip_smoke_test)
        self.assertEqual(options.package_format, "deb")

    def test_installer_only_flag_is_parsed(self) -> None:
        options = build.parse_arguments(["--installer-only"])
        self.assertTrue(options.installer)
        self.assertTrue(options.installer_only)

    def test_find_iscc_error_includes_install_hint(self) -> None:
        with patch.object(build.shutil, "which", return_value=None):
            with patch.object(build, "_iscc_candidates_from_registry", return_value=[]):
                with patch.dict("os.environ", {}, clear=True):
                    with self.assertRaisesRegex(FileNotFoundError, "winget install"):
                        build.find_iscc()

    def test_installer_paths_for_all_platforms(self) -> None:
        self.assertTrue((ROOT / "packaging" / "inno" / "ParqScan.iss").is_file())
        with patch.object(sys, "platform", "win32"):
            self.assertEqual(
                build.installer_executable(),
                ROOT / "dist" / "installer" / "ParqScan-Windows-Setup.exe",
            )
        with patch.object(sys, "platform", "darwin"), patch.object(build.platform, "machine", return_value="arm64"):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("PARQSCAN_TARGET_ARCH", None)
                self.assertEqual(
                    build.installer_executable(),
                    ROOT / "dist" / "installer" / "ParqScan-macOS-arm64.dmg",
                )
        with patch.object(sys, "platform", "linux"), patch.object(build.platform, "machine", return_value="x86_64"):
            self.assertEqual(
                build.installer_executable("deb"),
                ROOT / "dist" / "installer" / "ParqScan-Linux-amd64.deb",
            )
            self.assertEqual(
                build.installer_executable("rpm"),
                ROOT / "dist" / "installer" / "ParqScan-Linux-x86_64.rpm",
            )
        source = (ROOT / "packaging" / "inno" / "ParqScan.iss").read_text(encoding="utf-8")
        self.assertIn("OutputBaseFilename=ParqScan-Windows-Setup", source)
        self.assertIn("dist\\ParqScan", source)

    def test_read_release_version(self) -> None:
        self.assertEqual(build.read_release_version(), "0.3.8")

    def test_conda_python_fails_in_strict_mode(self) -> None:
        with patch.object(build, "is_conda_python", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "Conda Python was detected"):
                build.validate_build_environment(strict=True)

    def test_bloat_modules_fail_in_strict_mode(self) -> None:
        with patch.object(build, "is_conda_python", return_value=False):
            with patch("build.importlib.util.find_spec", side_effect=lambda name: object() if name == "pandas" else None):
                with self.assertRaisesRegex(RuntimeError, "non-runtime packages"):
                    build.validate_build_environment(strict=True)

    def test_bloat_modules_warn_in_non_strict_mode(self) -> None:
        with patch("build.importlib.util.find_spec", side_effect=lambda name: object() if name == "pandas" else None):
            with patch("builtins.print") as printed:
                build.validate_build_environment(strict=False)
        printed.assert_called()

    def test_excluded_modules_include_common_bloat_packages(self) -> None:
        source = (ROOT / "ParqScan.spec").read_text(encoding="utf-8")
        for module_name in ("pandas", "matplotlib", "notebook", "scipy", "sklearn"):
            self.assertIn(f'"{module_name}"', source)

    def test_validate_packaged_size_checks_macos_app_bundle(self) -> None:
        with patch.object(sys, "platform", "darwin"):
            self.assertEqual(build.packaged_artifact_root(), ROOT / "dist" / "ParqScan.app")
            with patch.object(build, "directory_size_bytes", return_value=700 * 1024 * 1024):
                with self.assertRaisesRegex(RuntimeError, "exceeds the 600 MB limit"):
                    build.validate_packaged_size(build.BuildOptions())

    def test_validate_packaged_size_rejects_large_onedir(self) -> None:
        with patch.object(build, "directory_size_bytes", return_value=700 * 1024 * 1024):
            with patch.object(sys, "platform", "win32"):
                with self.assertRaisesRegex(RuntimeError, "exceeds the 600 MB limit"):
                    build.validate_packaged_size(build.BuildOptions())

    def test_build_installer_invokes_iscc_on_windows(self) -> None:
        packaged = ROOT / "dist" / "ParqScan" / "ParqScan.exe"
        iscc = ROOT / "ISCC.exe"
        with patch.object(sys, "platform", "win32"):
            expected = build.installer_executable("exe")
            with patch.object(build, "packaged_executable", return_value=packaged):
                with patch.object(build, "find_iscc", return_value=iscc):
                    with patch.object(build, "installer_executable", return_value=expected):
                        with patch("build.subprocess.check_call") as check_call:
                            with patch.object(Path, "is_file", return_value=True):
                                output = build.build_installer()
        check_call.assert_called_once()
        self.assertEqual(check_call.call_args.args[0][0], str(iscc))
        self.assertEqual(output, expected)

    def test_build_installer_invokes_macos_dmg_on_darwin(self) -> None:
        expected = ROOT / "dist" / "installer" / "ParqScan-macOS-arm64.dmg"
        with patch.object(sys, "platform", "darwin"):
            with patch.object(build, "build_macos_dmg", return_value=expected) as mock_dmg:
                output = build.build_installer("dmg")
        mock_dmg.assert_called_once()
        self.assertEqual(output, expected)

    def test_build_installers_invokes_deb_and_rpm_on_linux(self) -> None:
        deb_out = ROOT / "dist" / "installer" / "ParqScan-Linux-amd64.deb"
        rpm_out = ROOT / "dist" / "installer" / "ParqScan-Linux-x86_64.rpm"
        with patch.object(sys, "platform", "linux"):
            with patch.object(build, "build_linux_deb", return_value=deb_out) as mock_deb:
                with patch.object(build, "build_linux_rpm", return_value=rpm_out) as mock_rpm:
                    outputs = build.build_installers("all")
        mock_deb.assert_called_once()
        mock_rpm.assert_called_once()
        self.assertEqual(outputs, [deb_out, rpm_out])


if __name__ == "__main__":
    unittest.main()
