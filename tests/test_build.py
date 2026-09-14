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
        self.assertIn('collect_plugins("iconengines")', source)
        self.assertIn('collect_plugins("imageformats")', source)
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


if __name__ == "__main__":
    unittest.main()
