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

    def test_non_windows_output_modes_preserve_platform_expectations(self) -> None:
        with patch.object(sys, "platform", "darwin"):
            self.assertFalse(build.effective_onefile(build.BuildOptions()))
        with patch.object(sys, "platform", "linux"):
            self.assertTrue(build.effective_onefile(build.BuildOptions()))

    def test_windows_icon_and_svg_support_are_declared_in_spec(self) -> None:
        source = (ROOT / "ParqScan.spec").read_text(encoding="utf-8")
        self.assertIn('"PySide6.QtSvg"', source)
        self.assertIn('"ParqScan.ico"', source)
        self.assertIn("icon=WINDOWS_ICON", source)
        self.assertIn('_collect_qt_plugins("iconengines")', source)
        self.assertIn('_collect_qt_plugins("imageformats")', source)
        self.assertIn("PYARROW_BINARIES + QT_PLUGIN_BINARIES", source)

    def test_conda_pyarrow_dlls_are_collected_without_collecting_tests(self) -> None:
        source = (ROOT / "ParqScan.spec").read_text(encoding="utf-8")
        self.assertIn('collect_dynamic_libs("pyarrow")', source)
        self.assertIn('conda_support.collect_dynamic_libs(', source)
        self.assertIn('"pyarrow.tests"', source)
        self.assertNotIn("collect_submodules", source)

    def test_required_icon_files_exist(self) -> None:
        resources = ROOT / "parqscan" / "resources"
        for filename in ("ParqScan.svg", "ParqScan.png", "ParqScan.ico"):
            self.assertTrue((resources / filename).is_file(), filename)

    def test_packaged_path_matches_build_mode(self) -> None:
        with patch.object(sys, "platform", "win32"):
            onedir = build.packaged_executable(build.BuildOptions())
            onefile = build.packaged_executable(build.BuildOptions(onefile=True))
        self.assertEqual(onedir, ROOT / "dist" / "ParqScan" / "ParqScan.exe")
        self.assertEqual(onefile, ROOT / "dist" / "ParqScan.exe")

    def test_installer_flag_is_parsed(self) -> None:
        options = build.parse_arguments(["--installer", "--skip-smoke-test"])
        self.assertTrue(options.installer)
        self.assertTrue(options.skip_smoke_test)

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

    def test_installer_paths_and_script(self) -> None:
        self.assertTrue((ROOT / "packaging" / "inno" / "ParqScan.iss").is_file())
        self.assertEqual(
            build.installer_executable(),
            ROOT / "dist" / "installer" / "ParqScan-Windows-Setup.exe",
        )
        source = (ROOT / "packaging" / "inno" / "ParqScan.iss").read_text(encoding="utf-8")
        self.assertIn("OutputBaseFilename=ParqScan-Windows-Setup", source)
        self.assertIn("dist\\ParqScan", source)

    def test_read_release_version(self) -> None:
        self.assertEqual(build.read_release_version(), "0.3.3")

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

    def test_validate_packaged_size_rejects_large_onedir(self) -> None:
        with patch.object(build, "directory_size_bytes", return_value=700 * 1024 * 1024):
            with patch.object(sys, "platform", "win32"):
                with self.assertRaisesRegex(RuntimeError, "exceeds the 600 MB limit"):
                    build.validate_packaged_size(build.BuildOptions())

    def test_build_installer_invokes_iscc_on_windows(self) -> None:
        packaged = ROOT / "dist" / "ParqScan" / "ParqScan.exe"
        iscc = ROOT / "ISCC.exe"
        with patch.object(sys, "platform", "win32"):
            with patch.object(build, "packaged_executable", return_value=packaged):
                with patch.object(build, "find_iscc", return_value=iscc):
                    with patch.object(build, "installer_executable", return_value=build.installer_executable()):
                        with patch("build.subprocess.check_call") as check_call:
                            with patch.object(Path, "is_file", return_value=True):
                                output = build.build_installer()
        check_call.assert_called_once()
        self.assertEqual(check_call.call_args.args[0][0], str(iscc))
        self.assertEqual(output, build.installer_executable())


if __name__ == "__main__":
    unittest.main()
