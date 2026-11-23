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
        self.setMinimumSize(460, 480)

        header = CardFrame(object_name="DialogHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(18, 14, 18, 14)
        header_layout.setSpacing(4)
        self.header_title = QLabel()
        self.header_title.setObjectName("DialogTitle")
        self.header_subtitle = QLabel()
        self.header_subtitle.setObjectName("MutedLabel")
        self.header_subtitle.setWordWrap(True)
        header_layout.addWidget(self.header_title)
        header_layout.addWidget(self.header_subtitle)

        total_rows = max(1, document.total_rows)
        self.start_spin = QSpinBox()
        self.start_spin.setRange(1, total_rows)
        self.end_spin = QSpinBox()
        self.end_spin.setRange(1, total_rows)
        self.end_spin.setValue(total_rows)
        self.column_list = QListWidget()
        for name in document.schema.names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.column_list.addItem(item)

        form_card = CardFrame(object_name="Card")
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(16, 14, 16, 14)
        form_layout.setSpacing(10)
        row_layout = QHBoxLayout()
        self.start_label = QLabel()
        self.end_label = QLabel()
        row_layout.addWidget(self.start_label)
        row_layout.addWidget(self.start_spin)
        row_layout.addSpacing(16)
        row_layout.addWidget(self.end_label)
        row_layout.addWidget(self.end_spin)
        row_layout.addStretch(1)
        form_layout.addLayout(row_layout)

        col_header = QHBoxLayout()
        self.columns_label = QLabel()
        self.columns_label.setObjectName("SectionTitle")
        self.select_all_button = QPushButton()
        self.select_all_button.setProperty("ghost", True)
        self.clear_all_button = QPushButton()
        self.clear_all_button.setProperty("ghost", True)
        col_header.addWidget(self.columns_label)
        col_header.addStretch(1)
        col_header.addWidget(self.select_all_button)
        col_header.addWidget(self.clear_all_button)
        form_layout.addLayout(col_header)
        form_layout.addWidget(self.column_list, 1)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("MutedLabel")
        self.error_label = QLabel()
        self.error_label.setObjectName("MessageIconCritical")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        form_layout.addWidget(self.summary_label)
        form_layout.addWidget(self.error_label)

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
        layout.addWidget(header)
        layout.addWidget(form_card, 1)
        layout.addLayout(buttons)

        self.start_spin.valueChanged.connect(self._validate)
        self.end_spin.valueChanged.connect(self._validate)
        self.column_list.itemChanged.connect(self._validate)
        self.select_all_button.clicked.connect(lambda: self._set_all_columns(True))
        self.clear_all_button.clicked.connect(lambda: self._set_all_columns(False))
        self.cancel_button.clicked.connect(self.reject)
        self.export_button.clicked.connect(self.accept)
        self.translator.language_changed.connect(self.retranslate)
        self.resize(560, 620)
        self.retranslate()

    def _set_all_columns(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.column_list.blockSignals(True)
        try:
            for index in range(self.column_list.count()):
                item = self.column_list.item(index)
                if item is not None:
                    item.setCheckState(state)
        finally:
            self.column_list.blockSignals(False)
        self._validate()

    def _selected_columns(self) -> list[str]:
        return [
            self.column_list.item(index).text()
            for index in range(self.column_list.count())
            if self.column_list.item(index).checkState() == Qt.CheckState.Checked
        ]

    def _validate(self) -> None:
        cols = self._selected_columns()
        total_cols = self.column_list.count()
        start = self.start_spin.value()
        end = self.end_spin.value()
        row_count = max(0, end - start + 1) if self.document.total_rows > 0 else 0
        self.summary_label.setText(
            self.translator.tr("range.selection_summary", rows=row_count, cols=len(cols), total_cols=total_cols)
        )

        error_key: str | None = None
        if self.document.total_rows <= 0:
            error_key = "range.invalid_empty"
        elif end < start:
            error_key = "range.invalid_range"
        elif not cols:
            error_key = "range.invalid_columns"

        if error_key is not None:
            self.error_label.setText(self.translator.tr(error_key))
            self.error_label.show()
            self.export_button.setEnabled(False)
        else:
            self.error_label.hide()
            self.export_button.setEnabled(True)

    def values(self) -> tuple[int, int, list[str]]:
        return self.start_spin.value() - 1, self.end_spin.value() - 1, self._selected_columns()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming convention
        try:
            self.translator.language_changed.disconnect(self.retranslate)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)

    def retranslate(self) -> None:
        title = self.translator.tr("range.title")
        self.setWindowTitle(title)
        self.header_title.setText(title)
        self.header_subtitle.setText(self.translator.tr("range.subtitle"))
        self.start_label.setText(self.translator.tr("range.start_row"))
        self.end_label.setText(self.translator.tr("range.end_row"))
        self.columns_label.setText(self.translator.tr("range.columns"))
        self.select_all_button.setText(self.translator.tr("range.select_all"))
        self.clear_all_button.setText(self.translator.tr("range.clear_all"))
        self.cancel_button.setText(self.translator.tr("common.cancel"))
        self.export_button.setText(self.translator.tr("common.export"))
        self._validate()
