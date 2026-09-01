from __future__ import annotations

import string

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from parqscan.constants import HEX_BYTES_PER_LINE
from parqscan.i18n import Translator
from parqscan.utils.binary import format_size, hex_dump
from parqscan.utils.icons import make_icon
from parqscan.widgets.design_system import (
    CardFrame,
    ElidingLabel,
    EmptyState,
    RoundedComboBox,
    SearchField,
)


class HexPreviewWidget(QWidget):
    def __init__(
        self,
        translator: Translator,
        parent: QWidget | None = None,
        *,
        embedded: bool = False,
    ) -> None:
        super().__init__(parent)
        self.translator = translator
        self._data = b""
        self._label = ""
        self._matches: list[tuple[int, int]] = []
        self._match_cursor = -1
        self._search_signature: tuple[str, str] | None = None

        self.mode_chip = QLabel("HEX + ASCII")
        self.mode_chip.setObjectName("Chip")
        self.info_label = ElidingLabel(mode=Qt.TextElideMode.ElideMiddle)
        self.info_label.setObjectName("HexInfoLabel")
        self.purpose_label = QLabel()
        self.purpose_label.setObjectName("HexPurposeLabel")
        self.purpose_label.setWordWrap(True)

        self.search_mode_combo = RoundedComboBox()
        self.search_mode_combo.setObjectName("HexSearchMode")
        self.search_mode_combo.setFixedWidth(116)
        self.search_field = SearchField()
        self.search_edit = self.search_field.editor
        self.search_button = QPushButton()
        self.search_button.setProperty("primary", True)
        self.search_button.setIcon(make_icon("search", "#FFFFFF", 16))
        self.search_button.setMinimumWidth(82)
        self.previous_button = self._nav_button("left")
        self.next_button = self._nav_button("right")
        self.search_status_label = QLabel()
        self.search_status_label.setObjectName("SearchStatus")
        self.search_status_label.setMinimumWidth(128)
        self.search_status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("CodeEditor")
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

        self.empty_state = EmptyState()
        self.empty_state.setObjectName("HexEmptyState")
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("HexContentStack")
        self.content_stack.addWidget(self.empty_state)
        self.content_stack.addWidget(self.editor)

        summary_row = QHBoxLayout()
        summary_row.setContentsMargins(0, 0, 0, 0)
        summary_row.setSpacing(9)
        summary_row.addWidget(self.mode_chip)
        summary_row.addWidget(self.info_label, 1)

        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(8)
        search_row.addWidget(self.search_mode_combo)
        search_row.addWidget(self.search_field, 1)
        search_row.addWidget(self.search_button)
        search_row.addWidget(self.previous_button)
        search_row.addWidget(self.next_button)
        search_row.addWidget(self.search_status_label)

        toolbar = CardFrame(object_name="HexToolbar")
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(13, 10, 13, 11)
        toolbar_layout.setSpacing(7)
        toolbar_layout.addLayout(summary_row)
        toolbar_layout.addWidget(self.purpose_label)
        toolbar_layout.addLayout(search_row)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0 if embedded else 14, 0 if embedded else 12, 0 if embedded else 14, 0 if embedded else 14)
        layout.setSpacing(10)
        layout.addWidget(toolbar)
        layout.addWidget(self.content_stack, 1)

        self.search_edit.textChanged.connect(self._mark_search_dirty)
        self.search_edit.returnPressed.connect(self.execute_search)
        self.search_mode_combo.currentIndexChanged.connect(self._mark_search_dirty)
        self.search_button.clicked.connect(self.execute_search)
        self.previous_button.clicked.connect(self.find_previous)
        self.next_button.clicked.connect(self.find_next)
        self.translator.language_changed.connect(self.retranslate)
        self.retranslate()
        self._set_has_data(False)

    @staticmethod
    def _nav_button(icon_name: str) -> QPushButton:
        button = QPushButton()
        button.setProperty("hexNav", True)
        button.setIcon(make_icon(icon_name))
        button.setMinimumWidth(88)
        button.setFixedHeight(34)
        return button

    def set_data(self, data: bytes, label: str = "") -> None:
        self._data = data
        self._label = label
        self.editor.setPlainText(hex_dump(data))
        self.info_label.setText(f"{label} · {format_size(len(data))}" if label else format_size(len(data)))
        self.editor.moveCursor(QTextCursor.MoveOperation.Start)
        self._matches.clear()
        self._match_cursor = -1
        self._search_signature = None
        self._set_has_data(True)
        self._mark_search_dirty()

    def clear_data(self) -> None:
        self._data = b""
        self._label = ""
        self._matches.clear()
        self._match_cursor = -1
        self._search_signature = None
        self.editor.clear()
        self.search_edit.clear()
        self._set_has_data(False)
        self.retranslate()

    def _set_has_data(self, has_data: bool) -> None:
        self.content_stack.setCurrentWidget(self.editor if has_data else self.empty_state)
        for control in (self.search_mode_combo, self.search_edit, self.search_button):
            control.setEnabled(has_data)
        self.previous_button.setEnabled(False)
        self.next_button.setEnabled(False)
        if not has_data:
            self.search_status_label.clear()

    def _selected_mode(self) -> str:
        value = self.search_mode_combo.currentData()
        return str(value) if value is not None else "auto"

    def _mark_search_dirty(self, *_args) -> None:
        self._search_signature = None
        self._matches.clear()
        self._match_cursor = -1
        self.previous_button.setEnabled(False)
        self.next_button.setEnabled(False)
        if not self._data:
            self.search_status_label.clear()
        elif self.search_edit.text().strip():
            self.search_status_label.setText(self.translator.tr("hex.search_ready"))
        else:
            self.search_status_label.setText(self.translator.tr("hex.search_idle"))

    @staticmethod
    def _decode_hex_query(query: str) -> bytes | None:
        normalized = query.strip().lower().replace("\\x", "")
        for separator in ("0x", " ", "-", ":", ",", "_"):
            normalized = normalized.replace(separator, "")
        if not normalized or len(normalized) % 2 or any(char not in string.hexdigits for char in normalized):
            return None
        try:
            return bytes.fromhex(normalized)
        except ValueError:
            return None

    @staticmethod
    def _looks_like_hex(query: str) -> bool:
        stripped = query.strip()
        compact = stripped.lower().replace("\\x", "").replace("0x", "")
        for separator in (" ", "-", ":", ",", "_"):
            compact = compact.replace(separator, "")
        # 中文：自动模式把纯偶数字节串（包括仅含 A-F 的“FF”）解释为 Hex，避免用户输入常见文件头却被当成文本。
        # English: Auto mode treats every even-length hexadecimal byte string, including letter-only values such as “FF”, as Hex rather than text.
        return bool(compact) and len(compact) % 2 == 0 and all(char in string.hexdigits for char in compact)

    @staticmethod
    def _all_occurrences(haystack: bytes, needle: bytes, *, case_insensitive: bool = False) -> list[tuple[int, int]]:
        if not needle:
            return []
        source = haystack.lower() if case_insensitive else haystack
        target = needle.lower() if case_insensitive else needle
        matches: list[tuple[int, int]] = []
        cursor = 0
        while cursor <= len(source) - len(target):
            found = source.find(target, cursor)
            if found < 0:
                break
            matches.append((found, len(needle)))
            # 中文：按一个字节推进可保留重叠匹配，避免重复签名或填充数据的结果数量被低估。
            # English: Advancing one byte preserves overlapping matches so repeated signatures or padding are not undercounted.
            cursor = found + 1
            if len(matches) >= 10000:
                break
        return matches

    def _offset_match(self, query: str) -> list[tuple[int, int]] | None:
        text = query.strip().lower().replace("offset:", "").replace("@", "")
        if not text:
            return []
        try:
            offset = int(text, 0) if text.startswith("0x") else int(text, 10)
        except ValueError:
            return None
        if offset < 0 or offset >= len(self._data):
            return []
        return [(offset, 1)]

    def execute_search(self) -> None:
        self._matches.clear()
        self._match_cursor = -1
        query = self.search_edit.text().strip()
        mode = self._selected_mode()
        self._search_signature = (mode, query)

        if not self._data or not query:
            self.search_status_label.setText(self.translator.tr("hex.search_idle") if self._data else "")
            self._refresh_search_buttons()
            return

        invalid = False
        if mode == "offset":
            offset_matches = self._offset_match(query)
            if offset_matches is None:
                invalid = True
            else:
                self._matches = offset_matches
        elif mode == "hex" or (mode == "auto" and self._looks_like_hex(query)):
            pattern = self._decode_hex_query(query)
            if pattern is None:
                invalid = True
            else:
                self._matches = self._all_occurrences(self._data, pattern)
        else:
            try:
                pattern = query.encode("utf-8")
            except UnicodeEncodeError:
                invalid = True
            else:
                self._matches = self._all_occurrences(self._data, pattern, case_insensitive=True)

        if invalid:
            self.search_status_label.setText(self.translator.tr("hex.invalid_query"))
        elif not self._matches:
            self.search_status_label.setText(self.translator.tr("hex.no_match"))
        else:
            self._match_cursor = 0
            self._select_current_match()
        self._refresh_search_buttons()

    def _ensure_current_search(self) -> bool:
        signature = (self._selected_mode(), self.search_edit.text().strip())
        if signature != self._search_signature:
            self.execute_search()
        return bool(self._matches)

    def _refresh_search_buttons(self) -> None:
        enabled = bool(self._data and self._matches)
        self.previous_button.setEnabled(enabled)
        self.next_button.setEnabled(enabled)

    def _select_current_match(self) -> None:
        if not self._matches or self._match_cursor < 0:
            return
        offset, length = self._matches[self._match_cursor]
        self._select_offset(offset, length)
        self.search_status_label.setText(
            self.translator.tr(
                "hex.match_summary",
                current=self._match_cursor + 1,
                total=len(self._matches),
                offset=f"0x{offset:08X}",
            )
        )

    def _select_offset(self, offset: int, length: int) -> None:
        line_index = offset // HEX_BYTES_PER_LINE
        byte_index = offset % HEX_BYTES_PER_LINE
        block = self.editor.document().findBlockByNumber(line_index)
        if not block.isValid():
            return

        bytes_in_line = min(length, HEX_BYTES_PER_LINE - byte_index)
        start = block.position() + 10 + byte_index * 3
        selection_length = max(2, bytes_in_line * 3 - 1)
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(start)
        cursor.setPosition(start + selection_length, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()

    def find_next(self) -> None:
        if not self._ensure_current_search():
            return
        self._match_cursor = (self._match_cursor + 1) % len(self._matches)
        self._select_current_match()

    def find_previous(self) -> None:
        if not self._ensure_current_search():
            return
        self._match_cursor = (self._match_cursor - 1) % len(self._matches)
        self._select_current_match()

    def focus_search(self) -> None:
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def retranslate(self) -> None:
        current_mode = self.search_mode_combo.currentData()
        self.search_mode_combo.blockSignals(True)
        self.search_mode_combo.clear()
        self.search_mode_combo.addItem(self.translator.tr("hex.mode_auto"), "auto")
        self.search_mode_combo.addItem(self.translator.tr("hex.mode_hex"), "hex")
        self.search_mode_combo.addItem(self.translator.tr("hex.mode_text"), "text")
        self.search_mode_combo.addItem(self.translator.tr("hex.mode_offset"), "offset")
        selected = self.search_mode_combo.findData(current_mode)
        self.search_mode_combo.setCurrentIndex(max(0, selected))
        self.search_mode_combo.blockSignals(False)

        self.purpose_label.setText(self.translator.tr("hex.purpose_compact"))
        self.search_edit.setPlaceholderText(self.translator.tr("hex.search_placeholder"))
        self.search_button.setText(self.translator.tr("common.search"))
        self.empty_state.title_label.setText(self.translator.tr("hex.empty_title"))
        self.empty_state.description_label.setText(self.translator.tr("hex.empty_hint"))
        if not self._data:
            self.info_label.setText(self.translator.tr("hex.empty_title"))
        elif not self.search_edit.text().strip():
            self.search_status_label.setText(self.translator.tr("hex.search_idle"))

        self.previous_button.setText(self.translator.tr("common.previous"))
        self.next_button.setText(self.translator.tr("common.next"))
        self._refresh_search_buttons()


class HexDialog(QDialog):
    def __init__(self, translator: Translator, data: bytes, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.translator = translator
        self.setObjectName("DetailDialog")
        self.preview = HexPreviewWidget(translator, embedded=True)
        self.preview.set_data(data, label)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(self.preview)
        self.resize(980, 700)
        self.translator.language_changed.connect(self.retranslate)
        self.retranslate()

    def retranslate(self) -> None:
        self.setWindowTitle(self.translator.tr("hex.window_title"))
