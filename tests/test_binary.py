from __future__ import annotations

import base64
import unittest

import pyarrow as pa

from parqscan.utils.binary import (
    contains_binary_type,
    embedded_binary_payload,
    embedded_file_name_hint,
    embedded_image_payload,
    hex_dump,
    image_payload,
)


PNG = b"\x89PNG\r\n\x1a\n" + b"payload"


class BinaryUtilityTests(unittest.TestCase):
    def test_nested_struct_image(self) -> None:
        value = {"bytes": PNG, "path": "images/example.png"}
        image = embedded_image_payload(value)
        self.assertIsNotNone(image)
        self.assertEqual(image.image_format.name, "PNG")
        self.assertEqual(embedded_binary_payload(value), PNG)
        self.assertEqual(embedded_file_name_hint(value), "example.png")

    def test_data_uri(self) -> None:
        value = b"data:image/png;base64," + base64.b64encode(PNG)
        payload = image_payload(value)
        self.assertIsNotNone(payload)
        self.assertEqual(payload[0], PNG)

    def test_recursive_arrow_type(self) -> None:
        data_type = pa.struct([pa.field("bytes", pa.binary()), pa.field("path", pa.string())])
        self.assertTrue(contains_binary_type(data_type))

    def test_hex_dump_contains_offset_and_ascii(self) -> None:
        dump = hex_dump(b"Hello")
        self.assertIn("00000000", dump)
        self.assertIn("Hello", dump)


if __name__ == "__main__":
    unittest.main()
