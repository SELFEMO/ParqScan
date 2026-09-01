from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from parqscan.data.parquet_document import ParquetDocument


PNG = b"\x89PNG\r\n\x1a\n" + b"payload"


class ParquetDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "sample.parquet"
        self._open_documents: list[ParquetDocument] = []
        image_type = pa.struct([pa.field("bytes", pa.binary()), pa.field("path", pa.string())])
        table = pa.table(
            {
                "image": pa.array(
                    [{"bytes": PNG, "path": f"images/{index}.png"} for index in range(123)],
                    type=image_type,
                ),
                "text": [f"row-{index}" for index in range(123)],
                "number": list(range(123)),
            }
        )
        pq.write_table(table, self.path, row_group_size=25)

    def tearDown(self) -> None:
        for document in self._open_documents:
            document.close()
        self._open_documents.clear()
        self.temporary.cleanup()

    def _open_document(self) -> ParquetDocument:
        document = ParquetDocument(str(self.path))
        self._open_documents.append(document)
        return document

    def test_page_window_crosses_row_groups(self) -> None:
        document = self._open_document()
        progress_values: list[tuple[int, int]] = []
        page = document.read_rows(40, 50, progress=lambda current, total: progress_values.append((current, total)))
        self.assertEqual(page.num_rows, 50)
        self.assertEqual(page.column("number")[0].as_py(), 40)
        self.assertEqual(page.column("number")[-1].as_py(), 89)
        self.assertTrue(progress_values)
        self.assertEqual(progress_values[-1][0], progress_values[-1][1])

    def test_last_page_is_truncated(self) -> None:
        document = self._open_document()
        page = document.read_rows(100, 50)
        self.assertEqual(page.num_rows, 23)

    def test_nested_binary_metadata(self) -> None:
        document = self._open_document()
        image = next(column for column in document.column_metadata() if column.name == "image")
        self.assertTrue(image.is_binary)
        self.assertGreater(image.binary_compressed_size, 0)

    def test_close_is_idempotent_and_page_loader_closes_temporary_files(self) -> None:
        document = self._open_document()
        self.assertIsNotNone(document.file)
        document.close()
        self.assertIsNone(document.file)
        document.close()
        loader_source = Path(__file__).resolve().parents[1].joinpath("parqscan", "data", "page_loader.py").read_text(encoding="utf-8")
        document_source = Path(__file__).resolve().parents[1].joinpath("parqscan", "data", "parquet_document.py").read_text(encoding="utf-8")
        data_source = Path(__file__).resolve().parents[1].joinpath("parqscan", "widgets", "data_widget.py").read_text(encoding="utf-8")
        self.assertIn("document.close()", loader_source)
        self.assertIn("finally:", loader_source)
        self.assertIn("def close(self) -> None:", document_source)
        self.assertIn("self.file.iter_batches(", document_source)
        self.assertNotIn("parquet_file = pq.ParquetFile(self.path)", document_source)
        self.assertIn("self.document.close()", data_source)


if __name__ == "__main__":
    unittest.main()
