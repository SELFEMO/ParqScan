from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from parqscan.data.parquet_document import ParquetDocument


class PageLoadSignals(QObject):
    started = Signal(int, int, int)
    progress = Signal(int, int, int)
    loaded = Signal(int, int, object)
    failed = Signal(int, int, str)
    cancelled = Signal(int, int)


class PageLoadTask(QRunnable):
    def __init__(
        self,
        generation: int,
        path: str,
        page_index: int,
        start_row: int,
        row_count: int,
        source_rows: list[int] | None = None,
    ) -> None:
        super().__init__()
        self.generation = generation
        self.path = path
        self.page_index = page_index
        self.start_row = start_row
        self.row_count = row_count
        self.source_rows = list(source_rows) if source_rows is not None else None
        self.signals = PageLoadSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        if self._cancelled:
            self.signals.cancelled.emit(self.generation, self.page_index)
            return
        document = None
        try:
            document = ParquetDocument(self.path)
            self.signals.started.emit(self.generation, self.page_index, self.row_count)

            last_percent = -1

            def report(current: int, total: int) -> None:
                nonlocal last_percent
                percent = 100 if total <= 0 else min(100, int(current * 100 / total))
                # 中文：只在百分比变化时回传进度，避免超大行组产生数千个 GUI 信号反而拖慢加载。
                # English: Progress is emitted only when the percentage changes so huge row groups cannot flood the GUI with thousands of signals.
                if not self._cancelled and percent != last_percent:
                    last_percent = percent
                    self.signals.progress.emit(self.generation, current, total)

            # 中文：普通分页按连续区间读取；文件级排序后的分页携带原始行号列表，因此必须按索引抽取并保持排序结果。
            # English: Normal pages read a contiguous range, while file-level sorting supplies source-row indices that must be taken in the requested order.
            if self.source_rows is None:
                table = document.read_rows(
                    self.start_row,
                    self.row_count,
                    progress=report,
                    is_cancelled=lambda: self._cancelled,
                )
            else:
                table = document.read_row_indices(
                    self.source_rows,
                    progress=report,
                    is_cancelled=lambda: self._cancelled,
                )
            if self._cancelled:
                self.signals.cancelled.emit(self.generation, self.page_index)
            else:
                self.signals.loaded.emit(self.generation, self.page_index, table)
        except Exception as error:
            if not self._cancelled:
                self.signals.failed.emit(self.generation, self.page_index, str(error))
        finally:
            if document is not None:
                document.close()
