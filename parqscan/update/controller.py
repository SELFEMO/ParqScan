from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, QThread, Signal, Slot

from parqscan.config import ConfigManager
from parqscan.release import release_name
from parqscan.update.constants import CHECK_INTERVAL_SECONDS, GITHUB_REPO, WINDOWS_ASSET_NAME
from parqscan.update.github import ReleaseInfo, fetch_latest_release
from parqscan.update.versioning import compare_versions


@dataclass(frozen=True)
class UpdateCheckResult:
    release: ReleaseInfo
    current_version: str


class UpdateCheckWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    @Slot()
    def run(self) -> None:
        try:
            release = fetch_latest_release()
            current_version = release_name()
            if compare_versions(release.version, current_version) <= 0:
                self.finished.emit(None)
                return
            self.finished.emit(UpdateCheckResult(release=release, current_version=current_version))
        except Exception as error:
            self.failed.emit(str(error))


class UpdateDownloadWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, download_url: str, target_path: Path) -> None:
        super().__init__()
        self.download_url = download_url
        self.target_path = target_path

    @Slot()
    def run(self) -> None:
        request = Request(self.download_url, headers={"User-Agent": "ParqScan-Update"})
        try:
            with urlopen(request, timeout=120) as response:
                total_header = response.headers.get("Content-Length")
                total = int(total_header) if total_header and total_header.isdigit() else 0
                downloaded = 0
                chunk_size = 256 * 1024
                self.target_path.parent.mkdir(parents=True, exist_ok=True)
                with self.target_path.open("wb") as stream:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        stream.write(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(downloaded, total if total > 0 else max(downloaded, 1))
        except Exception as error:
            self.failed.emit(str(error))
            return
        self.finished.emit(str(self.target_path))


class UpdateController(QObject):
    check_finished = Signal(object, bool)
    check_failed = Signal(str, bool)
    download_progress = Signal(int, int)
    download_finished = Signal(str)
    download_failed = Signal(str)

    def __init__(self, config: ConfigManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self._check_thread: QThread | None = None
        self._download_thread: QThread | None = None
        self._pending_release: ReleaseInfo | None = None

    def maybe_auto_check(self) -> None:
        if not self._auto_check_enabled():
            return
        if not self._should_check_now():
            return
        self.check_for_updates(manual=False)

    def check_for_updates(self, manual: bool = False) -> None:
        if self._check_thread is not None and self._check_thread.isRunning():
            return
        if manual or self._should_check_now():
            self._record_check_time()
        thread = QThread(self)
        worker = UpdateCheckWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda result: self._on_check_finished(result, manual))
        worker.failed.connect(lambda message: self._on_check_failed(message, manual))
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_check_thread)
        self._check_thread = thread
        thread.start()

    def is_dismissed(self, version: str) -> bool:
        dismissed = self.config.get("dismissed_update_version", "")
        return isinstance(dismissed, str) and dismissed == version

    def dismiss_version(self, version: str) -> None:
        self.config.set("dismissed_update_version", version)

    def pending_release(self) -> ReleaseInfo | None:
        return self._pending_release

    def set_pending_release(self, release: ReleaseInfo | None) -> None:
        self._pending_release = release

    def download_and_install(self, release: ReleaseInfo) -> None:
        if self._download_thread is not None and self._download_thread.isRunning():
            return
        if not release.download_url:
            self.download_failed.emit("missing_download_url")
            return
        target = Path(tempfile.gettempdir()) / f"ParqScan-{release.version}-setup.exe"
        thread = QThread(self)
        worker = UpdateDownloadWorker(release.download_url, target)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.download_progress.emit)
        worker.finished.connect(self._on_download_finished)
        worker.failed.connect(self.download_failed.emit)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_download_thread)
        self._download_thread = thread
        thread.start()

    @staticmethod
    def can_install_in_place() -> bool:
        return sys.platform.startswith("win")

    @staticmethod
    def releases_page_url() -> str:
        return f"{GITHUB_REPO.rstrip('/')}/releases/latest"

    @staticmethod
    def launch_installer(installer_path: str) -> None:
        subprocess.Popen([installer_path, "/SILENT", "/CLOSEAPPLICATIONS"], close_fds=True)

    def _auto_check_enabled(self) -> bool:
        value = self.config.get("auto_check_updates", True)
        return value is not False

    def _should_check_now(self) -> bool:
        last_check = self._last_check_time()
        if last_check is None:
            return True
        return datetime.now(timezone.utc) - last_check >= timedelta(seconds=CHECK_INTERVAL_SECONDS)

    def _last_check_time(self) -> datetime | None:
        value = self.config.get("last_update_check")
        if not isinstance(value, str) or not value.strip():
            return None
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _record_check_time(self) -> None:
        self.config.set("last_update_check", datetime.now(timezone.utc).isoformat())

    def _on_check_finished(self, result: Any, manual: bool) -> None:
        self.check_finished.emit(result, manual)

    def _on_check_failed(self, message: str, manual: bool) -> None:
        self.check_failed.emit(message, manual)

    def _on_download_finished(self, installer_path: str) -> None:
        self.download_finished.emit(installer_path)

    def _clear_check_thread(self) -> None:
        self._check_thread = None

    def _clear_download_thread(self) -> None:
        self._download_thread = None
