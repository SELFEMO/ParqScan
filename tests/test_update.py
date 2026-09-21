from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from parqscan.config import ConfigManager
from parqscan.update.controller import UpdateController
from parqscan.update.github import find_asset_url, fetch_latest_release, parse_release_payload
from parqscan.update.versioning import compare_versions, normalize_version, version_tuple


class VersioningTests(unittest.TestCase):
    def test_normalize_version_strips_v_prefix(self) -> None:
        self.assertEqual(normalize_version("v0.3.1"), "0.3.1")
        self.assertEqual(normalize_version("V1.2.3"), "1.2.3")
        self.assertEqual(normalize_version("pre-release-v0.3.2"), "0.3.2")

    def test_version_tuple_parses_semver(self) -> None:
        self.assertEqual(version_tuple("0.3.1"), (0, 3, 1))
        self.assertEqual(version_tuple("v2.10"), (2, 10, 0))

    def test_compare_versions_orders_correctly(self) -> None:
        self.assertEqual(compare_versions("0.3.0", "0.3.1"), -1)
        self.assertEqual(compare_versions("0.3.1", "0.3.1"), 0)
        self.assertEqual(compare_versions("1.0.0", "0.9.9"), 1)


class GitHubReleaseTests(unittest.TestCase):
    def test_find_asset_url_matches_windows_installer(self) -> None:
        assets = [
            {"name": "notes.txt", "browser_download_url": "https://example.com/notes.txt"},
            {"name": "ParqScan-Windows-Setup.exe", "browser_download_url": "https://example.com/setup.exe"},
        ]
        self.assertEqual(find_asset_url(assets, "ParqScan-Windows-Setup.exe"), "https://example.com/setup.exe")

    def test_parse_release_payload(self) -> None:
        payload = {
            "tag_name": "v0.3.2",
            "html_url": "https://github.com/SELFEMO/ParqScan/releases/tag/v0.3.2",
            "body": "Release notes",
            "assets": [
                {"name": "ParqScan-Windows-Setup.exe", "browser_download_url": "https://example.com/setup.exe"},
            ],
        }
        release = parse_release_payload(payload)
        self.assertEqual(release.version, "0.3.2")
        self.assertEqual(release.download_url, "https://example.com/setup.exe")
        self.assertEqual(release.release_page_url, payload["html_url"])
        self.assertEqual(release.body, "Release notes")

    def test_fetch_latest_release_picks_newest_including_prerelease(self) -> None:
        payloads = [
            {
                "tag_name": "v0.3.1",
                "draft": False,
                "prerelease": False,
                "html_url": "https://github.com/SELFEMO/ParqScan/releases/tag/v0.3.1",
                "assets": [
                    {"name": "ParqScan-Windows-Setup.exe", "browser_download_url": "https://example.com/031.exe"},
                ],
            },
            {
                "tag_name": "pre-release-v0.3.2",
                "draft": False,
                "prerelease": True,
                "html_url": "https://github.com/SELFEMO/ParqScan/releases/tag/pre-release-v0.3.2",
                "assets": [
                    {"name": "ParqScan-Windows-Setup.exe", "browser_download_url": "https://example.com/032.exe"},
                ],
            },
        ]
        response = unittest.mock.MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with patch("parqscan.update.github.urlopen", return_value=response):
            with patch("parqscan.update.github.json.load", return_value=payloads):
                release = fetch_latest_release()
        self.assertEqual(release.version, "0.3.2")
        self.assertEqual(release.download_url, "https://example.com/032.exe")


class UpdateControllerTests(unittest.TestCase):
    def _make_controller(self, data: dict | None = None) -> tuple[UpdateController, Path]:
        temporary_directory = tempfile.mkdtemp()
        config_path = Path(temporary_directory) / "config.json"
        if data:
            config_path.write_text(json.dumps(data), encoding="utf-8")
        config = ConfigManager()
        config.path = config_path
        config.data = config._load()
        return UpdateController(config), config_path

    def test_should_auto_check_respects_interval(self) -> None:
        recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        controller, _path = self._make_controller({"auto_check_updates": True, "last_update_check": recent})
        self.assertFalse(controller._should_check_now())

    def test_dismissed_version_is_recorded(self) -> None:
        controller, config_path = self._make_controller()
        controller.dismiss_version("0.3.2")
        self.assertTrue(controller.is_dismissed("0.3.2"))
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["dismissed_update_version"], "0.3.2")

    def test_auto_check_disabled(self) -> None:
        controller, _path = self._make_controller({"auto_check_updates": False})
        self.assertFalse(controller._auto_check_enabled())


if __name__ == "__main__":
    unittest.main()
