from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from parqscan.data.parquet_document import ParquetDocument
from parqscan.i18n import Translator
from parqscan.utils.binary import format_size
from parqscan.utils.icons import make_icon
from parqscan.widgets.design_system import CardFrame, ElidingLabel, HintToolButton, MetricCard


class MetadataWidget(QWidget):
    GROUP_INDEX_ROLE = Qt.ItemDataRole.UserRole + 1
    PLACEHOLDER_ROLE = Qt.ItemDataRole.UserRole + 2

    def __init__(self, document: ParquetDocument, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MetadataPage")
        self.document = document
        self.translator = translator
        columns = document.column_metadata()
        compression = document.compression_algorithms()

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("MetadataScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content = QWidget()
        self.content.setObjectName("MetadataContent")
        self.scroll_area.setWidget(self.content)

        self.eyebrow = QLabel()
        self.eyebrow.setObjectName("EyebrowLabel")
        self.title_label = ElidingLabel(document.display_name, mode=Qt.TextElideMode.ElideMiddle)
        self.title_label.setObjectName("PageTitle")
        self.title_label.setMinimumHeight(34)

        heading = QVBoxLayout()
        heading.setSpacing(3)
        heading.addWidget(self.eyebrow)
        heading.addWidget(self.title_label)

        self.path_card = CardFrame(object_name="PathCard")
        path_layout = QHBoxLayout(self.path_card)
        path_layout.setContentsMargins(15, 10, 10, 10)
        path_layout.setSpacing(11)
        self.path_caption = QLabel()
        self.path_caption.setObjectName("MutedLabel")
        self.path_caption.setMinimumWidth(62)
        self.path_label = ElidingLabel(document.path, mode=Qt.TextElideMode.ElideMiddle)
        self.path_label.setObjectName("PathLabel")
        self.copy_path_button = HintToolButton()
        self.copy_path_button.setProperty("nav", True)
        self.copy_path_button.setIcon(make_icon("copy"))
        self.copy_path_button.setFixedSize(32, 32)
        path_layout.addWidget(self.path_caption)
        path_layout.addWidget(self.path_label, 1)
        path_layout.addWidget(self.copy_path_button)

        self.rows_card = MetricCard(value=f"{document.total_rows:,}")
        self.columns_card = MetricCard(value=f"{document.total_columns:,}")
        self.file_size_card = MetricCard(value=format_size(document.file_size))
        self.binary_size_card = MetricCard(value=format_size(document.binary_compressed_size()))
        self.compression_card = MetricCard(value=", ".join(compression) or "—")
        self.groups_card = MetricCard(value=f"{document.metadata.num_row_groups:,}")

        metrics = QGridLayout()
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setHorizontalSpacing(11)
        metrics.setVerticalSpacing(11)
        cards = (
            self.rows_card,
            self.columns_card,
            self.file_size_card,
            self.binary_size_card,
            self.compression_card,
            self.groups_card,
        )
        for index, card in enumerate(cards):
            metrics.addWidget(card, index // 3, index % 3)
            metrics.setColumnStretch(index % 3, 1)

        self.detail_tabs = QTabWidget()
        self.detail_tabs.setObjectName("MetadataTabs")

        self.schema_panel = CardFrame(object_name="Card")
        schema_layout = QVBoxLayout(self.schema_panel)
        schema_layout.setContentsMargins(0, 0, 0, 0)
        self.schema_table = QTableWidget()
        self.schema_table.setObjectName("SchemaTable")
        self.schema_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.schema_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.schema_table.setAlternatingRowColors(True)
        self.schema_table.setShowGrid(False)
        self.schema_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.schema_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.schema_table.verticalHeader().setVisible(False)
        self.schema_table.verticalHeader().setDefaultSectionSize(39)
        self.schema_table.horizontalHeader().setMinimumHeight(42)
        self.schema_table.horizontalHeader().setStretchLastSection(False)
        schema_layout.addWidget(self.schema_table)

        self.groups_panel = CardFrame(object_name="Card")
        groups_layout = QVBoxLayout(self.groups_panel)
        groups_layout.setContentsMargins(0, 0, 0, 0)
        self.row_group_tree = QTreeWidget()
        self.row_group_tree.setObjectName("RowGroupTree")
        self.row_group_tree.setAlternatingRowColors(True)
        self.row_group_tree.setUniformRowHeights(True)
        self.row_group_tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.row_group_tree.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.row_group_tree.header().setMinimumHeight(42)
        self.row_group_tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.row_group_tree.header().setStretchLastSection(False)
        self.row_group_tree.itemExpanded.connect(self._populate_row_group_children)
        groups_layout.addWidget(self.row_group_tree)

        self.detail_tabs.addTab(self.schema_panel, "")
        self.detail_tabs.addTab(self.groups_panel, "")

        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(24, 20, 24, 24)
        content_layout.setSpacing(14)
        content_layout.addLayout(heading)
        content_layout.addWidget(self.path_card)
        content_layout.addLayout(metrics)
        content_layout.addWidget(self.detail_tabs, 1)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.scroll_area)

        self.copy_path_button.clicked.connect(self._copy_path)
        self._populate_schema(columns)
        self._populate_row_group_summaries()
        self._configure_columns()
        self.translator.language_changed.connect(self.retranslate)
        self.retranslate()

    def _copy_path(self) -> None:
        QGuiApplication.clipboard().setText(self.document.path)

    def _configure_columns(self) -> None:
        header = self.schema_table.horizontalHeader()
        # 中文：将逻辑类型列设为弹性列，并为其余统计列保留稳定宽度，避免正常窗口下最后一列被截断并出现无意义的横向滚动。
        # English: The logical-type column absorbs spare space while statistical columns keep stable widths, preventing the final column from being clipped in a normal window.
        modes = (
            QHeaderView.ResizeMode.Interactive,
            QHeaderView.ResizeMode.Stretch,
            QHeaderView.ResizeMode.Interactive,
            QHeaderView.ResizeMode.Fixed,
            QHeaderView.ResizeMode.Fixed,
            QHeaderView.ResizeMode.Fixed,
            QHeaderView.ResizeMode.Fixed,
            QHeaderView.ResizeMode.Fixed,
        )
        widths = (156, 280, 142, 72, 104, 108, 88, 94)
        for column, (mode, width) in enumerate(zip(modes, widths)):
            header.setSectionResizeMode(column, mode)
            self.schema_table.setColumnWidth(column, width)

        tree_header = self.row_group_tree.header()
        tree_modes = (
            QHeaderView.ResizeMode.Fixed,
            QHeaderView.ResizeMode.Fixed,
            QHeaderView.ResizeMode.Fixed,
            QHeaderView.ResizeMode.Stretch,
            QHeaderView.ResizeMode.Interactive,
            QHeaderView.ResizeMode.Interactive,
            QHeaderView.ResizeMode.Fixed,
        )
        tree_widths = (78, 94, 104, 240, 170, 170, 94)
        for column, (mode, width) in enumerate(zip(tree_modes, tree_widths)):
            tree_header.setSectionResizeMode(column, mode)
            self.row_group_tree.setColumnWidth(column, width)

    def _populate_schema(self, columns) -> None:
        self.schema_table.setRowCount(len(columns))
        self.schema_table.setColumnCount(8)
        for row, column in enumerate(columns):
            values = (
                column.name,
                column.logical_type,
                column.physical_type,
                "✓" if column.nullable else "—",
                column.compression,
                format_size(column.compressed_size),
                f"{column.storage_ratio:.1%}",
                "✓" if column.is_binary else "—",
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if col in {3, 6, 7}:
                    item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
                self.schema_table.setItem(row, col, item)

    def _populate_row_group_summaries(self) -> None:
        self.row_group_tree.clear()
        for group_index in range(self.document.metadata.num_row_groups):
            row_group = self.document.metadata.row_group(group_index)
            parent = QTreeWidgetItem(
                [
                    str(group_index + 1),
                    f"{row_group.num_rows:,}",
                    format_size(row_group.total_byte_size),
                    "",
                    "",
                    "",
                    "",
                ]
            )
            parent.setData(0, self.GROUP_INDEX_ROLE, group_index)
            placeholder = QTreeWidgetItem([""])
            placeholder.setData(0, self.PLACEHOLDER_ROLE, True)
            parent.addChild(placeholder)
            self.row_group_tree.addTopLevelItem(parent)

    def _populate_row_group_children(self, parent: QTreeWidgetItem) -> None:
        if parent.data(0, self.GROUP_INDEX_ROLE) is None:
            return
        if parent.childCount() != 1 or not parent.child(0).data(0, self.PLACEHOLDER_ROLE):
            return

        # 中文：行组统计按展开时生成，避免文件打开阶段创建大量用户暂时看不到的树节点。
        # English: Row-group statistics are built on expansion so opening a file never creates large numbers of invisible tree nodes.
        parent.takeChildren()
        group = self.document.row_group_metadata_at(int(parent.data(0, self.GROUP_INDEX_ROLE)))
        for column in group.columns:
            parent.addChild(
                QTreeWidgetItem(
                    [
                        "",
                        "",
                        "",
                        column.name,
                        column.min_value,
                        column.max_value,
                        column.null_count,
                    ]
                )
            )

    def retranslate(self) -> None:
        self.eyebrow.setText(self.translator.tr("metadata.eyebrow"))
        self.path_caption.setText(self.translator.tr("metadata.path"))
        self.copy_path_button.set_hint(self.translator.tr("metadata.copy_path"))
        self.rows_card.set_title(self.translator.tr("metadata.rows"))
        self.columns_card.set_title(self.translator.tr("metadata.columns"))
        self.file_size_card.set_title(self.translator.tr("metadata.file_size"))
        self.binary_size_card.set_title(self.translator.tr("metadata.binary_size"))
        self.compression_card.set_title(self.translator.tr("metadata.compression"))
        self.groups_card.set_title(self.translator.tr("metadata.row_groups"))

        schema_headers = (
            "metadata.name",
            "metadata.logical_type",
            "metadata.physical_type",
            "metadata.nullable",
            "metadata.compression",
            "metadata.compressed_size",
            "metadata.storage_ratio",
            "metadata.binary",
        )
        self.schema_table.setHorizontalHeaderLabels([self.translator.tr(key) for key in schema_headers])
        tree_headers = (
            "metadata.row_group",
            "metadata.rows",
            "metadata.total_size",
            "metadata.name",
            "metadata.minimum",
            "metadata.maximum",
            "metadata.null_count",
        )
        self.row_group_tree.setHeaderLabels([self.translator.tr(key) for key in tree_headers])
        self.detail_tabs.setTabText(0, self.translator.tr("metadata.schema"))
        self.detail_tabs.setTabText(1, self.translator.tr("metadata.row_group_details"))
