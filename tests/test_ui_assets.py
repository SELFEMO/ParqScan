from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UiAssetTests(unittest.TestCase):
    def test_labels_do_not_inherit_page_backgrounds(self) -> None:
        for theme in ("light", "dark"):
            stylesheet = (ROOT / "parqscan" / "styles" / f"{theme}.qss").read_text(encoding="utf-8")
            self.assertIn("QWidget {\n    background: transparent;", stylesheet)
            self.assertIn("QLabel {\n    background: transparent;", stylesheet)
            self.assertNotIn("QMainWindow, QDialog, QWidget", stylesheet)

    def test_scrollbars_are_compact_arrowless_and_have_a_styled_corner(self) -> None:
        for theme in ("light", "dark"):
            stylesheet = (ROOT / "parqscan" / "styles" / f"{theme}.qss").read_text(encoding="utf-8")
            self.assertIn("width: 8px;", stylesheet)
            self.assertIn("height: 8px;", stylesheet)
            self.assertIn("QScrollBar::add-line, QScrollBar::sub-line", stylesheet)
            self.assertIn("QAbstractScrollArea::corner, QWidget#ScrollCorner", stylesheet)
        source = (ROOT / "parqscan" / "widgets" / "data_widget.py").read_text(encoding="utf-8")
        self.assertIn('self.scroll_corner.setObjectName("ScrollCorner")', source)
        self.assertIn("self.table.setCornerWidget(self.scroll_corner)", source)

    def test_search_icon_uses_a_compound_field_instead_of_qlineedit_action(self) -> None:
        design_source = (ROOT / "parqscan" / "widgets" / "design_system.py").read_text(encoding="utf-8")
        data_source = (ROOT / "parqscan" / "widgets" / "data_widget.py").read_text(encoding="utf-8")
        self.assertIn("class SearchField", design_source)
        self.assertIn('self.icon_label.setObjectName("SearchFieldIcon")', design_source)
        self.assertIn("self.search_field = SearchField()", data_source)
        self.assertNotIn("self.search_edit.addAction", data_source)

    def test_pagination_is_icon_only_without_elided_button_text_or_tooltips(self) -> None:
        source = (ROOT / "parqscan" / "widgets" / "design_system.py").read_text(encoding="utf-8")
        self.assertIn('self.page_edit = QLineEdit("1")', source)
        self.assertIn("ToolButtonIconOnly", source)
        self.assertIn('button.setText("")', source)
        self.assertIn("button.setFixedSize(34, 32)", source)
        self.assertNotIn("QSpinBox", source)
        self.assertNotIn("_hint_popup", source)

    def test_directional_icons_use_direction_specific_tips(self) -> None:
        source = (ROOT / "parqscan" / "utils" / "icons.py").read_text(encoding="utf-8")
        self.assertIn('if direction == "left":', source)
        self.assertIn('tip = QPointF(center - horizontal, size / 2)', source)
        self.assertIn('tip = QPointF(center + horizontal, size / 2)', source)
        self.assertIn('elif name == "right":', source)
        self.assertIn('_draw_chevron(painter, "right", size)', source)

    def test_page_load_resets_table_scroll_position(self) -> None:
        source = (ROOT / "parqscan" / "widgets" / "data_widget.py").read_text(encoding="utf-8")
        self.assertIn("self.table.scrollToTop()", source)
        self.assertIn("self.table.horizontalScrollBar().setValue(0)", source)

    def test_raw_bytes_search_has_an_explicit_button_and_scans_bytes(self) -> None:
        source = (ROOT / "parqscan" / "dialogs" / "hex_dialog.py").read_text(encoding="utf-8")
        self.assertIn("self.search_button = QPushButton()", source)
        self.assertIn("self.search_button.clicked.connect(self.execute_search)", source)
        self.assertIn("def _decode_hex_query", source)
        self.assertIn("def _all_occurrences", source)
        self.assertIn("def _select_offset", source)
        self.assertIn("return bool(compact) and len(compact) % 2 == 0", source)

    def test_binary_inspector_is_not_a_permanent_document_tab(self) -> None:
        document_source = (ROOT / "parqscan" / "widgets" / "document_widget.py").read_text(encoding="utf-8")
        data_source = (ROOT / "parqscan" / "widgets" / "data_widget.py").read_text(encoding="utf-8")
        self.assertNotIn("HexPreviewWidget", document_source)
        self.assertNotIn("binary_selected", document_source)
        self.assertIn('self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)', data_source)
        self.assertIn('self.translator.tr("context.view_raw_bytes")', data_source)

    def test_popup_surfaces_are_really_clipped_to_rounded_masks(self) -> None:
        source = (ROOT / "parqscan" / "widgets" / "design_system.py").read_text(encoding="utf-8")
        main_source = (ROOT / "parqscan" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn("class RoundedMenu", source)
        self.assertIn("class RoundedComboBox", source)
        self.assertIn("_apply_rounded_mask", source)
        self.assertIn("add_rounded_menu", main_source)
        for theme in ("light", "dark"):
            stylesheet = (ROOT / "parqscan" / "styles" / f"{theme}.qss").read_text(encoding="utf-8")
            self.assertIn("QMenu#RoundedMenu", stylesheet)
            self.assertIn("QListView#RoundedComboPopup", stylesheet)

    def test_detail_images_support_fit_buttons_and_wheel_zoom(self) -> None:
        design_source = (ROOT / "parqscan" / "widgets" / "design_system.py").read_text(encoding="utf-8")
        detail_source = (ROOT / "parqscan" / "dialogs" / "cell_detail_dialog.py").read_text(encoding="utf-8")
        self.assertIn("class ZoomableImageView", design_source)
        self.assertIn("def wheelEvent", design_source)
        self.assertIn("def zoom_in", design_source)
        self.assertIn("def zoom_out", design_source)
        self.assertIn("def reset_view", design_source)
        self.assertIn("fitInView", design_source)
        self.assertIn("self.image_view = ZoomableImageView()", detail_source)
        self.assertIn("self.zoom_in_button.clicked.connect(self.image_view.zoom_in)", detail_source)
        self.assertIn("self.zoom_out_button.clicked.connect(self.image_view.zoom_out)", detail_source)
        self.assertIn("self.reset_view_button.clicked.connect(self.image_view.reset_view)", detail_source)

    def test_about_dialog_uses_the_application_logo(self) -> None:
        design_source = (ROOT / "parqscan" / "widgets" / "design_system.py").read_text(encoding="utf-8")
        main_source = (ROOT / "parqscan" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn('icon_label.setObjectName("MessageLogo")', design_source)
        self.assertIn("icon=self.app_icon", main_source)
        self.assertIn('self.translator.tr("about.title")', main_source)

    def test_manual_update_check_uses_themed_feedback(self) -> None:
        design_source = (ROOT / "parqscan" / "widgets" / "design_system.py").read_text(encoding="utf-8")
        main_source = (ROOT / "parqscan" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn("class ChoiceDialog", design_source)
        self.assertIn("def show_choice", design_source)
        self.assertIn('self.translator.tr("update.checking")', main_source)
        self.assertIn("show_choice(", main_source)
        self.assertNotIn("QMessageBox", main_source)

    def test_message_dialog_and_page_size_are_dpi_safe(self) -> None:
        source = (ROOT / "parqscan" / "widgets" / "design_system.py").read_text(encoding="utf-8")
        self.assertIn("card_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)", source)
        self.assertIn("root.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)", source)
        self.assertIn('self.page_size_combo.setFixedWidth(74)', source)
        self.assertIn('self.page_size_combo.setProperty("centerText", True)', source)
        self.assertIn("def paintEvent(self, event)", source)
        for theme in ("light", "dark"):
            stylesheet = (ROOT / "parqscan" / "styles" / f"{theme}.qss").read_text(encoding="utf-8")
            self.assertIn("QComboBox#PageSizeCombo", stylesheet)
            self.assertIn("min-width: 74px;", stylesheet)

    def test_combo_values_use_real_content_rect_and_compact_page_width(self) -> None:
        source = (ROOT / "parqscan" / "widgets" / "design_system.py").read_text(encoding="utf-8")
        self.assertIn("self.contentsRect().adjusted(", source)
        self.assertIn("metrics.horizontalAdvance(current_text)", source)
        self.assertIn("QPalette.ColorRole.Text", source)
        self.assertIn("self.page_size_combo.setFixedWidth(74)", source)
        self.assertNotIn("SC_ComboBoxEditField", source)

    def test_detail_images_keep_the_full_decoded_source(self) -> None:
        design_source = (ROOT / "parqscan" / "widgets" / "design_system.py").read_text(encoding="utf-8")
        detail_source = (ROOT / "parqscan" / "dialogs" / "cell_detail_dialog.py").read_text(encoding="utf-8")
        popup_source = (ROOT / "parqscan" / "widgets" / "image_popup.py").read_text(encoding="utf-8")
        self.assertIn("class OriginalImageItem", design_source)
        self.assertIn("painter.drawImage(0, 0, self._image)", design_source)
        self.assertIn("def set_source_image", design_source)
        self.assertIn("self.image_view.set_source_image(decoded)", detail_source)
        self.assertIn("self.image_view.set_source_image(image)", popup_source)

    def test_native_long_value_tooltips_are_disabled(self) -> None:
        source = (ROOT / "parqscan" / "models" / "parquet_table_model.py").read_text(encoding="utf-8")
        self.assertIn("if role == Qt.ItemDataRole.ToolTipRole:", source)
        self.assertIn("return None", source)

    def test_record_details_use_an_independent_canvas_tile_layout(self) -> None:
        source = (ROOT / "parqscan" / "dialogs" / "cell_detail_dialog.py").read_text(encoding="utf-8")
        self.assertIn("class AdaptivePreviewGrid", source)
        self.assertIn("class AdaptivePreviewGrid(QWidget)", source)
        self.assertNotIn("class AdaptivePreviewGrid(QMainWindow)", source)
        self.assertNotIn("class _LegacyAdaptivePreviewGrid", source)
        self.assertIn("class PreviewTile(QFrame)", source)
        self.assertIn("never becomes a native top-level window", source)
        self.assertIn("class TileResizeHandle", source)
        self.assertIn("NEW_TILE_ORIGIN = QPoint(0, 0)", source)
        self.assertIn("self._positions", source)
        self.assertIn("self._sizes", source)
        self.assertIn("tile.move(position)", source)
        self.assertIn("def _begin_preview_resize", source)
        self.assertIn("def _update_preview_resize", source)
        self.assertIn("SizeFDiagCursor", source)
        self.assertIn("class DockTitleBar", source)
        self.assertIn("self._title_bar = DockTitleBar", source)
        self.assertIn("self.grabMouse()", source)
        self.assertNotIn("application.installEventFilter", source)
        self.assertIn("def _finish_preview_drag", source)
        self.assertIn("def add_preview", source)
        self.assertIn("def remove_preview", source)
        self.assertNotIn("self.content_card", source)
        self.assertIn("def _set_text_wrapping", source)
        self.assertIn("def take_widget", source)
        self.assertIn("tile.take_widget()", source)
        self.assertIn("DETAIL_DOCK_TITLE_HEIGHT", source)
        self.assertNotIn("class DockDragPreview", source)
        self.assertNotIn("DockDragPreview", source)
        self.assertNotIn("QDockWidget", source)
        self.assertIn("self.preview_scroll.setWidgetResizable(True)", source)
        self.assertIn("ScrollBarPolicy.ScrollBarAsNeeded", source)
        self.assertIn("self.preview_grid.reveal_preview", source)
        self.assertIn("self._field_values", source)
        self.assertIn("def _sync_selected_previews", source)
        for theme in ("light", "dark"):
            stylesheet = (ROOT / "parqscan" / "styles" / f"{theme}.qss").read_text(encoding="utf-8")
            self.assertIn("QWidget#DetailPreviewGrid", stylesheet)
            self.assertNotIn("QMainWindow#DetailPreviewGrid", stylesheet)
            self.assertIn("QWidget#DetailResizeHandle", stylesheet)

    def test_image_hover_preview_uses_tooltip_and_follows_cursor(self) -> None:
        popup_source = (ROOT / "parqscan" / "widgets" / "image_popup.py").read_text(encoding="utf-8")
        constants_source = (ROOT / "parqscan" / "constants.py").read_text(encoding="utf-8")
        model_source = (ROOT / "parqscan" / "models" / "parquet_table_model.py").read_text(encoding="utf-8")
        data_source = (ROOT / "parqscan" / "widgets" / "data_widget.py").read_text(encoding="utf-8")
        self.assertIn("Qt.WindowType.ToolTip", popup_source)
        self.assertNotIn("Qt.WindowType.Popup", popup_source)
        self.assertIn("HoverEnter", popup_source)
        self.assertIn("HoverMove", popup_source)
        self.assertIn("WA_Hover", popup_source)
        self.assertIn("def _update_from_point", popup_source)
        self.assertIn("def refresh_from_cursor", popup_source)
        self.assertIn("IMAGE_HOVER_SIZE = 520", constants_source)
        self.assertIn("IMAGE_HOVER_CACHE_LIMIT = 16", constants_source)
        self.assertIn("self._hover_cache", model_source)
        self.assertIn("IMAGE_HOVER_CACHE_LIMIT", model_source)
        self.assertIn("def hide_preview", popup_source)
        self.assertIn("WindowDeactivate", popup_source)
        self.assertIn("MouseButtonDblClick", popup_source)
        self.assertIn("self.hover_preview.refresh_from_cursor()", data_source)
        self.assertIn("selectionChanged.connect(self._refresh_image_hover)", data_source)
        self.assertIn("self.hover_preview.hide_preview()", data_source)

    def test_detail_preview_tiles_share_one_radius_and_visible_border(self) -> None:
        import re

        detail_source = (ROOT / "parqscan" / "dialogs" / "cell_detail_dialog.py").read_text(encoding="utf-8")
        self.assertIn("DETAIL_TILE_CORNER_RADIUS = 10", detail_source)
        self.assertIn("_apply_rounded_mask(self, DETAIL_TILE_CORNER_RADIUS)", detail_source)
        self.assertIn("self.setFrameShape(QFrame.Shape.NoFrame)", detail_source)
        self.assertIn("drawRoundedRect", detail_source)
        self.assertIn("self.setAutoFillBackground(True)", detail_source)
        self.assertNotIn('setObjectName(f"detail-tile-', detail_source)
        for theme in ("light", "dark"):
            stylesheet = (ROOT / "parqscan" / "styles" / f"{theme}.qss").read_text(encoding="utf-8")
            tile = re.search(r"QFrame#DetailPreviewTile \{([^}]*)\}", stylesheet)
            card = re.search(r"QFrame#DetailPreviewCard \{([^}]*)\}", stylesheet)
            title = re.search(r"QFrame#DetailDockTitle \{([^}]*)\}", stylesheet)
            self.assertIsNotNone(tile)
            self.assertIsNotNone(card)
            self.assertIsNotNone(title)
            self.assertIn("border-radius: 10px;", tile.group(1))
            self.assertIn("border: none;", tile.group(1))
            self.assertNotIn("border: 2px solid", tile.group(1))
            self.assertRegex(tile.group(1), r"color: #[0-9A-Fa-f]{6};")
            self.assertIn("border: none;", card.group(1))
            self.assertNotIn("background: transparent;", card.group(1))
            self.assertNotIn("border-radius:", card.group(1))
            self.assertNotIn("border-radius:", title.group(1))
            self.assertIn("QAbstractScrollArea#ImageCanvas::viewport", stylesheet)
        light = (ROOT / "parqscan" / "styles" / "light.qss").read_text(encoding="utf-8")
        dark = (ROOT / "parqscan" / "styles" / "dark.qss").read_text(encoding="utf-8")
        self.assertIn("QWidget#DetailPreviewGrid {\n    background: #E8EEF6;", light)
        self.assertIn("QFrame#DetailPreviewTile {\n    background: #FFFFFF;\n    border: none;", light)
        self.assertIn("color: #8B9CB3;", light)
        self.assertIn("background: #EEF2F7;", light)
        self.assertIn("QFrame#DetailPreviewCard {\n    background: #FFFFFF;", light)
        self.assertIn("QFrame#DetailPreviewTile {\n    background: #141E2B;\n    border: none;", dark)
        self.assertIn("color: #7A8EA8;", dark)
        self.assertIn("background: #1E2A3A;", dark)
        self.assertIn("QFrame#DetailPreviewCard {\n    background: #141E2B;", dark)
        design_source = (ROOT / "parqscan" / "widgets" / "design_system.py").read_text(encoding="utf-8")
        self.assertIn("self.palette().color(QPalette.ColorRole.Base)", design_source)
        self.assertNotIn("Qt.BrushStyle.NoBrush", design_source)

    def test_detail_selection_highlights_identical_visible_text(self) -> None:
        source = (ROOT / "parqscan" / "dialogs" / "cell_detail_dialog.py").read_text(encoding="utf-8")
        self.assertIn("editor.selectionChanged.connect(self._text_selection_changed)", source)
        self.assertIn("QTextDocument.FindFlag.FindCaseSensitively", source)
        self.assertIn("self._matching_selections(editor, self._highlight_term)", source)
        self.assertIn("if self._highlight_term and editor.isVisibleTo(self):", source)
        self.assertIn("for editor in pane.text_editors():", source)

    def test_search_scopes_keep_independent_state_and_reject_stale_file_results(self) -> None:
        data_source = (ROOT / "parqscan" / "widgets" / "data_widget.py").read_text(encoding="utf-8")
        model_source = (ROOT / "parqscan" / "models" / "parquet_table_model.py").read_text(encoding="utf-8")
        self.assertIn("class SearchState", data_source)
        self.assertIn('self._search_states = {"file": SearchState(), "page": SearchState()}', data_source)
        self.assertIn("self.search_scope_combo = RoundedComboBox()", data_source)
        self.assertIn("generation != self._search_generation", data_source)
        self.assertIn("def _run_page_search", data_source)
        self.assertIn("def find_page_matches", model_source)
        self.assertIn("for offset in self._active_offsets():", model_source)
        self.assertIn("def order_search_matches", model_source)
        self.assertIn("from parqscan.utils.search import searchable_text", model_source)

    def test_detail_dialog_is_modeless_with_normal_window_controls(self) -> None:
        source = (ROOT / "parqscan" / "dialogs" / "cell_detail_dialog.py").read_text(encoding="utf-8")
        self.assertIn("self.setModal(False)", source)
        self.assertIn("Qt.WindowType.Window", source)
        self.assertIn("Qt.WindowModality.NonModal", source)
        self.assertIn("Qt.WindowType.WindowCloseButtonHint", source)
        self.assertIn("Qt.WindowType.WindowMinimizeButtonHint", source)
        self.assertIn("Qt.WindowType.WindowMaximizeButtonHint", source)
        self.assertNotIn("WindowStaysOnTopHint", source)
        self.assertNotIn("self.maximize_button", source)
        self.assertNotIn("def _toggle_maximized", source)

    def test_file_search_paints_the_entire_matching_cell(self) -> None:
        model_source = (ROOT / "parqscan" / "models" / "parquet_table_model.py").read_text(encoding="utf-8")
        delegate_source = (ROOT / "parqscan" / "widgets" / "binary_delegate.py").read_text(encoding="utf-8")
        self.assertIn("SearchMatchRole", model_source)
        self.assertIn("self.SearchMatchRole", model_source)
        self.assertIn("self.SearchMatchRole]", model_source)
        self.assertIn("def _paint_search_match", delegate_source)
        self.assertIn("ParquetTableModel.SearchMatchRole", delegate_source)
        self.assertIn("painter.fillRect(option.rect", delegate_source)

    def test_detail_search_shortcut_and_lifecycle_are_registered(self) -> None:
        detail_source = (ROOT / "parqscan" / "dialogs" / "cell_detail_dialog.py").read_text(encoding="utf-8")
        data_source = (ROOT / "parqscan" / "widgets" / "data_widget.py").read_text(encoding="utf-8")
        self.assertIn("SearchField", detail_source)
        self.assertIn("QKeySequence.StandardKey.Find", detail_source)
        self.assertIn("def eventFilter", detail_source)
        self.assertIn("def _update_detail_search", detail_source)
        self.assertIn("def _navigate_detail_search", detail_source)
        self.assertIn("self._ensure_row_json_generated()", detail_source)
        self.assertIn("editor.setExtraSelections(selections)", detail_source)
        self.assertIn("self._detail_dialogs", data_source)
        self.assertIn("dialog.show()", data_source)
        self.assertIn("dialog.close()", data_source)

    def test_file_search_reveals_a_match_without_resetting_the_current_page_filter(self) -> None:
        source = (ROOT / "parqscan" / "widgets" / "data_widget.py").read_text(encoding="utf-8")
        self.assertIn("class PageFilterState", source)
        self.assertIn("self._page_filter_state = PageFilterState()", source)
        self.assertIn("self._restore_page_filter_after_load()", source)
        self.assertIn("self._start_file_search(query, generation, auto_select)", source)
        self.assertIn("self._apply_active_search_results(auto_select=auto_select)", source)
        self.assertIn("def _select_first_visible_file_match", source)
        self.assertIn("if self._page_filter_state.active:", source)
        self.assertIn('self.translator.tr("data.file_matches_hidden_by_filter"', source)
        self.assertIn("self._select_search_match(1)", source)
        self.assertNotIn("_clear_page_filter_for_file_navigation", source)
        self.assertIn('self.translator.tr("data.match_hidden_by_filter")', source)

    def test_search_navigation_reveals_the_selected_row_after_deferred_layout(self) -> None:
        source = (ROOT / "parqscan" / "widgets" / "data_widget.py").read_text(encoding="utf-8")
        self.assertIn("QItemSelectionModel", source)
        self.assertIn("def _select_and_reveal_index", source)
        self.assertIn("QItemSelectionModel.SelectionFlag.ClearAndSelect", source)
        self.assertIn("self.table.doItemsLayout()", source)
        self.assertIn("self.table.rowViewportPosition(index.row())", source)
        self.assertIn("vertical_bar.setValue(", source)
        self.assertIn("def _schedule_search_reveal", source)
        self.assertIn("for delay in (0, 80, 240):", source)
        self.assertIn("generation != self._search_generation", source)


class DetailPreviewGridBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            cls.app = None
            return
        cls.app = QApplication.instance() or QApplication([])

    def test_new_preview_stacks_at_origin_without_moving_existing(self) -> None:
        if self.app is None:
            self.skipTest("PySide6 is unavailable")
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QLabel

        from parqscan.dialogs.cell_detail_dialog import AdaptivePreviewGrid

        grid = AdaptivePreviewGrid()
        first = QLabel("first")
        first.setProperty("dock_id", "field-0")
        second = QLabel("second")
        second.setProperty("dock_id", "field-1")
        grid.add_preview(first)
        self.assertEqual(grid.preview_position(first), QPoint(0, 0))
        grid.move_preview(first, QPoint(120, 80))
        self.assertEqual(grid.preview_position(first), QPoint(120, 80))
        grid.add_preview(second)
        self.assertEqual(grid.preview_position(first), QPoint(120, 80))
        self.assertEqual(grid.preview_position(second), QPoint(0, 0))
        grid.deleteLater()

    def test_record_detail_dialog_opens_field_tile_at_origin(self) -> None:
        if self.app is None:
            self.skipTest("PySide6 is unavailable")
        import tempfile
        from pathlib import Path

        import pyarrow as pa
        import pyarrow.parquet as pq
        from PySide6.QtCore import QPoint

        from parqscan.data.parquet_document import ParquetDocument
        from parqscan.dialogs.cell_detail_dialog import RecordDetailDialog
        from parqscan.i18n import Translator
        from parqscan.models.parquet_table_model import ParquetTableModel

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "sample.parquet"
        pq.write_table(pa.table({"a": ["one"], "b": ["two"]}), path)
        document = ParquetDocument(str(path))
        self.addCleanup(document.close)
        model = ParquetTableModel(document, 20)
        model._loading = False
        model._table = document.read_rows(0, 1)
        model._page_source_rows = [0]
        dialog = RecordDetailDialog(Translator("en"), model, 0, 0)
        self.addCleanup(dialog.close)
        self.assertEqual(len(dialog._panes), 1)
        pane = dialog._panes[0]
        self.assertEqual(dialog.preview_grid.preview_position(pane), QPoint(0, 0))
        self.assertTrue(pane.wrap_button.isVisibleTo(pane))


if __name__ == "__main__":
    unittest.main()
