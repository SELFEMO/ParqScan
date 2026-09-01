from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from parqscan.data.parquet_document import ParquetDocument
from parqscan.i18n import Translator
from parqscan.widgets.design_system import CardFrame


class RangeExportDialog(QDialog):
    def __init__(self, document: ParquetDocument, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document = document
        self.translator = translator
        self.setObjectName("DetailDialog")

        self.start_spin = QSpinBox()
        self.start_spin.setRange(1, max(1, document.total_rows))
        self.end_spin = QSpinBox()
        self.end_spin.setRange(1, max(1, document.total_rows))
        self.end_spin.setValue(max(1, document.total_rows))
        self.column_list = QListWidget()
        for name in document.schema.names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.column_list.addItem(item)

        form_card = CardFrame(object_name="Card")
        form_layout = QVBoxLayout(form_card)
        row_layout = QHBoxLayout()
        self.start_label = QLabel()
        self.end_label = QLabel()
        row_layout.addWidget(self.start_label)
        row_layout.addWidget(self.start_spin)
        row_layout.addSpacing(16)
        row_layout.addWidget(self.end_label)
        row_layout.addWidget(self.end_spin)
        form_layout.addLayout(row_layout)
        self.columns_label = QLabel()
        self.columns_label.setObjectName("SectionTitle")
        form_layout.addWidget(self.columns_label)
        form_layout.addWidget(self.column_list, 1)

        self.cancel_button = QPushButton()
        self.cancel_button.setProperty("secondary", True)
        self.export_button = QPushButton()
        self.export_button.setProperty("primary", True)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.export_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(form_card, 1)
        layout.addLayout(buttons)
        self.cancel_button.clicked.connect(self.reject)
        self.export_button.clicked.connect(self.accept)
        self.translator.language_changed.connect(self.retranslate)
        self.resize(560, 620)
        self.retranslate()

    def values(self) -> tuple[int, int, list[str]]:
        columns = [
            self.column_list.item(index).text()
            for index in range(self.column_list.count())
            if self.column_list.item(index).checkState() == Qt.CheckState.Checked
        ]
        return self.start_spin.value() - 1, self.end_spin.value() - 1, columns

    def retranslate(self) -> None:
        self.setWindowTitle(self.translator.tr("range.title"))
        self.start_label.setText(self.translator.tr("range.start_row"))
        self.end_label.setText(self.translator.tr("range.end_row"))
        self.columns_label.setText(self.translator.tr("range.columns"))
        self.cancel_button.setText(self.translator.tr("common.cancel"))
        self.export_button.setText(self.translator.tr("common.export"))
