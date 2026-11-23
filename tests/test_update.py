from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from parqscan.config import ConfigManager
from parqscan.update.controller import UpdateCheckWorker, UpdateController
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
        from parqscan.update.constants import WINDOWS_ASSET_NAME

        release = parse_release_payload(payload, asset_name=WINDOWS_ASSET_NAME)
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
                from parqscan.update.constants import WINDOWS_ASSET_NAME

                release = fetch_latest_release(asset_name=WINDOWS_ASSET_NAME)
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

    def test_platform_asset_name_resolves_per_os(self) -> None:
        from parqscan.update.constants import (
            LINUX_DEB_AMD64_ASSET_NAME,
            LINUX_RPM_X86_64_ASSET_NAME,
            MACOS_ARM64_ASSET_NAME,
            WINDOWS_ASSET_NAME,
            platform_asset_name,
        )

        self.assertEqual(platform_asset_name("win32", "AMD64"), WINDOWS_ASSET_NAME)
        self.assertEqual(platform_asset_name("darwin", "arm64"), MACOS_ARM64_ASSET_NAME)
        self.assertEqual(platform_asset_name("linux", "x86_64", "deb"), LINUX_DEB_AMD64_ASSET_NAME)
        self.assertEqual(platform_asset_name("linux", "x86_64", "rpm"), LINUX_RPM_X86_64_ASSET_NAME)

    def test_can_install_in_place_supports_windows_and_macos(self) -> None:
        import sys

        with patch.object(sys, "platform", "win32"):
            self.assertTrue(UpdateController.can_install_in_place())
        with patch.object(sys, "platform", "darwin"):
            self.assertTrue(UpdateController.can_install_in_place())
        with patch.object(sys, "platform", "linux"):
            self.assertFalse(UpdateController.can_install_in_place())

    def test_launch_installer_opens_dmg_on_macos(self) -> None:
        import sys

        with patch.object(sys, "platform", "darwin"):
            with patch("parqscan.update.controller.subprocess.Popen") as popen:
                UpdateController.launch_installer("/tmp/ParqScan.dmg")
        popen.assert_called_once_with(["open", "/tmp/ParqScan.dmg"], close_fds=True)

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

    def test_manual_check_emits_busy_when_check_is_in_progress(self) -> None:
        controller, _path = self._make_controller()
        busy_calls: list[bool] = []
        finished_calls: list[tuple[object, bool]] = []
        controller.check_busy.connect(lambda: busy_calls.append(True))
        controller.check_finished.connect(lambda result, manual: finished_calls.append((result, manual)))
        controller._check_in_progress = True
        controller.check_for_updates(manual=True)
        self.assertEqual(busy_calls, [True])
        self.assertEqual(finished_calls, [])

    def test_worker_finished_preserves_manual_flag(self) -> None:
        controller, _path = self._make_controller()
        finished_calls: list[tuple[object, bool]] = []
        controller.check_finished.connect(lambda result, manual: finished_calls.append((result, manual)))
        controller._handle_check_worker_finished(None, True)
        self.assertEqual(finished_calls, [(None, True)])
        self.assertFalse(controller._check_in_progress)

    def test_manual_check_does_not_record_last_update_check(self) -> None:
        controller, _path = self._make_controller()
        started: list[bool] = []
        controller.check_started.connect(lambda manual: started.append(manual))
        with patch.object(controller, "_record_check_time") as record_check:
            with patch("parqscan.update.controller.QThread") as thread_cls:
                thread = MagicMock()
                thread.isRunning.return_value = False
                thread_cls.return_value = thread
                with patch.object(UpdateCheckWorker, "moveToThread"):
                    controller.check_for_updates(manual=True)
        record_check.assert_not_called()
        self.assertEqual(started, [True])
        thread.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
