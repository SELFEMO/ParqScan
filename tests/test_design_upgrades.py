from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from parqscan.data.export_service import (
    export_csv,
    export_excel,
    export_json,
    export_markdown,
    export_parquet_fragment,
    export_sql,
)
from parqscan.data.parquet_document import ParquetDocument

ROOT = Path(__file__).resolve().parents[1]


def _relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    rgb = [int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast_ratio(fg: str, bg: str) -> float:
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


class DesignUpgradeTests(unittest.TestCase):
    def test_qss_weights_are_valid_multiples_of_100_and_no_duplicates(self) -> None:
        for theme in ("light", "dark"):
            qss = (ROOT / "parqscan" / "styles" / f"{theme}.qss").read_text(encoding="utf-8")
            self.assertNotIn("letter-spacing", qss)
            weights = re.findall(r"font-weight:\s*(\d+)\s*;", qss)
            for w in weights:
                val = int(w)
                self.assertIn(val, range(100, 1000, 100), f"Invalid weight {w} in {theme}.qss")

            blocks = re.findall(r"([^{}]+)\{([^{}]*)\}", qss, re.S)
            selectors = [" ".join(sel.split()) for sel, _ in blocks]
            self.assertEqual(len(selectors), len(set(selectors)), f"Duplicate selectors found in {theme}.qss")

            if theme == "dark":
                self.assertIn("QLabel#LoadingTitle {", qss)

    def test_wcag_aa_contrast_for_core_tokens(self) -> None:
        # Light primary button & hover
        self.assertGreaterEqual(_contrast_ratio("#FFFFFF", "#0F6FDB"), 4.5)
        self.assertGreaterEqual(_contrast_ratio("#FFFFFF", "#0D5EC0"), 4.5)
        # Light selected blue text
        self.assertGreaterEqual(_contrast_ratio("#0B5FC4", "#E7F2FF"), 4.5)
        # Light DetailPreviewTile text
        self.assertGreaterEqual(_contrast_ratio("#5A6B82", "#FFFFFF"), 4.5)
        # Dark primary button & hover (dark text on bright hover)
        self.assertGreaterEqual(_contrast_ratio("#FFFFFF", "#0F6FDB"), 4.5)
        self.assertGreaterEqual(_contrast_ratio("#0B1220", "#47A3FF"), 4.5)

    def test_locales_have_no_dead_keys_and_match(self) -> None:
        en = json.loads((ROOT / "parqscan" / "locales" / "en.json").read_text(encoding="utf-8"))
        zh = json.loads((ROOT / "parqscan" / "locales" / "zh.json").read_text(encoding="utf-8"))
        self.assertNotIn("hex", en.get("tabs", {}))
        self.assertNotIn("purpose", en.get("hex", {}))
        self.assertEqual(set(en.keys()), set(zh.keys()))
        for section in en:
            self.assertEqual(set(en[section].keys()), set(zh[section].keys()), f"Key mismatch in {section}")

    def test_atomic_exports_leave_no_corrupt_files_when_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "sample.parquet"
            pq.write_table(pa.table({"id": [1, 2], 'bad"col': ["a|b", "c"]}), src)
            doc = ParquetDocument(str(src))
            try:
                for fn, ext in (
                    (export_csv, "csv"),
                    (export_json, "json"),
                    (export_excel, "xlsx"),
                    (export_markdown, "md"),
                    (export_sql, "sql"),
                ):
                    target = Path(tmp) / f"cancelled.{ext}"
                    fn(doc, str(target), lambda _a, _b: None, lambda: True)
                    self.assertFalse(target.exists(), f"Cancelled export left file: {target}")

                frag_target = Path(tmp) / "cancelled.parquet"
                export_parquet_fragment(doc, str(frag_target), 0, 1, ["id"], lambda _a, _b: None, lambda: True)
                self.assertFalse(frag_target.exists())

                # Verify SQL identifier escaping & Markdown pipe escaping on completed export
                sql_target = Path(tmp) / "ok.sql"
                export_sql(doc, str(sql_target), lambda _a, _b: None, lambda: False)
                sql_text = sql_target.read_text(encoding="utf-8")
                self.assertIn('"bad""col"', sql_text)

                md_target = Path(tmp) / "ok.md"
                export_markdown(doc, str(md_target), lambda _a, _b: None, lambda: False)
                md_text = md_target.read_text(encoding="utf-8")
                self.assertIn("a\\|b", md_text)
            finally:
                doc.close()

    def test_dotted_column_name_metadata_and_closed_document_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "dotted.parquet"
            pq.write_table(pa.table({"user.id": [10, 20], "name": ["alice", "bob"]}), src)
            doc = ParquetDocument(str(src))
            cols = {c.name: c for c in doc.column_metadata()}
            self.assertGreater(cols["user.id"].compressed_size, 0)
            doc.close()
            table = doc.read_rows(0, 10)
            self.assertEqual(table.num_rows, 0)


if __name__ == "__main__":
    unittest.main()
