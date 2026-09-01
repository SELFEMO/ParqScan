from __future__ import annotations

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from parqscan.config import ConfigManager
from parqscan.data.parquet_document import ParquetDocument
from parqscan.i18n import Translator
from parqscan.widgets.data_widget import DataWidget
from parqscan.widgets.metadata_widget import MetadataWidget


class DocumentWidget(QWidget):
    def __init__(
        self,
        document: ParquetDocument,
        translator: Translator,
        config: ConfigManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.document = document
        self.translator = translator
        self.tabs = QTabWidget()
        self.tabs.setObjectName("DocumentTabs")
        self.metadata_widget = MetadataWidget(document, translator)
        self.data_widget = DataWidget(document, translator, config)
        self.tabs.addTab(self.metadata_widget, "")
        self.tabs.addTab(self.data_widget, "")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

        # 中文：原始字节检查属于单个字段的高级工具，移入详情和右键菜单后，主工作区只保留高频的元数据与数据预览。
        # English: Raw-byte inspection is an advanced field-level tool, so moving it into details and context actions keeps the main workspace focused on metadata and data browsing.
        self.translator.language_changed.connect(self.retranslate)
        self.retranslate()

    def focus_search(self) -> None:
        self.tabs.setCurrentWidget(self.data_widget)
        self.data_widget.focus_search()

    def shutdown(self) -> None:
        self.data_widget.shutdown()

    def retranslate(self) -> None:
        self.tabs.setTabText(0, self.translator.tr("tabs.metadata"))
        self.tabs.setTabText(1, self.translator.tr("tabs.data"))
