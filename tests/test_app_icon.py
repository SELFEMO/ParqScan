from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from parqscan.utils.app_icon import _icon_candidate_paths, create_app_icon


ROOT = Path(__file__).resolve().parents[1]


class AppIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_main_sets_app_user_model_id_before_pyside_import(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        app_id_index = source.index("set_windows_app_user_model_id()")
        pyside_index = source.index("import PySide6.QtSvg")
        self.assertLess(app_id_index, pyside_index)

    def test_windows_icon_candidates_prefer_ico(self) -> None:
        source = (ROOT / "parqscan" / "utils" / "app_icon.py").read_text(encoding="utf-8")
        self.assertIn('resources / "ParqScan.ico"', source)
        self.assertIn('resources / "ParqScan.png"', source)
        self.assertIn('resources / "ParqScan.svg"', source)
        with patch.object(sys, "platform", "win32"):
            paths = _icon_candidate_paths()
        self.assertEqual(paths[0].name, "ParqScan.ico")

    def test_non_windows_icon_candidates_prefer_svg(self) -> None:
        with patch.object(sys, "platform", "linux"):
            paths = _icon_candidate_paths()
        self.assertEqual(paths[0].name, "ParqScan.svg")
        self.assertEqual(paths[1].name, "ParqScan.png")

    def test_create_app_icon_returns_non_empty_pixmap(self) -> None:
        icon = create_app_icon()
        self.assertIsInstance(icon, QIcon)
        self.assertFalse(icon.isNull())
        self.assertFalse(icon.pixmap(64, 64).isNull())

    def test_application_smoke_test_rejects_blank_icon(self) -> None:
        source = (ROOT / "parqscan" / "application.py").read_text(encoding="utf-8")
        self.assertIn("if smoke_test:", source)
        self.assertIn("application.windowIcon().pixmap(64, 64).isNull()", source)
        self.assertIn("return 1", source)


if __name__ == "__main__":
    unittest.main()
