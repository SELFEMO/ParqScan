from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QThread, Qt
from PySide6.QtWidgets import QProgressDialog, QWidget

from parqscan.data.workers import CancellableWorker


class BackgroundTaskRunner(QObject):
    """Unified runner for CancellableWorker on a dedicated QThread with optional progress dialog."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._host = parent
        self._active: dict[int, tuple[QThread, CancellableWorker, QProgressDialog | None]] = {}
        self._next_id = 1

    def start(
        self,
        worker: CancellableWorker,
        *,
        on_finished: Callable[[object], None],
        on_failed: Callable[[str], None],
        progress_title: str | None = None,
        cancel_label: str = "Cancel",
        show_progress_dialog: bool = True,
    ) -> int:
        task_id = self._next_id
        self._next_id += 1

        thread = QThread(self._host)
        worker.moveToThread(thread)

        dialog: QProgressDialog | None = None
        if show_progress_dialog and progress_title is not None:
            dialog = QProgressDialog(progress_title, cancel_label, 0, 100, self._host)
            dialog.setWindowModality(Qt.WindowModality.WindowModal)
            dialog.setMinimumDuration(250)
            dialog.setAutoClose(False)
            dialog.setAutoReset(False)
            dialog.canceled.connect(worker.cancel)
            worker.progress.connect(
                lambda current, total, dlg=dialog: dlg.setValue(
                    0 if total <= 0 else min(100, round(current * 100 / total))
                )
            )

        self._active[task_id] = (thread, worker, dialog)
        thread.started.connect(worker.run)

        def _cleanup() -> None:
            entry = self._active.pop(task_id, None)
            if entry is not None:
                _t, _w, dlg = entry
                if dlg is not None:
                    dlg.close()
                    dlg.deleteLater()
            thread.quit()
            thread.deleteLater()
            worker.deleteLater()

        def _handle_finished(result: object) -> None:
            _cleanup()
            on_finished(result)

        def _handle_failed(message: str) -> None:
            _cleanup()
            on_failed(message)

        worker.finished.connect(_handle_finished)
        worker.failed.connect(_handle_failed)
        thread.start()
        return task_id

    def active_count(self) -> int:
        return len(self._active)

    def shutdown(self) -> None:
        for _task_id, (thread, worker, dialog) in list(self._active.items()):
            worker.cancel()
            if dialog is not None:
                dialog.close()
                dialog.deleteLater()
            thread.quit()
            thread.wait(1000)
        self._active.clear()
