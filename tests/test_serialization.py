from __future__ import annotations

import json
import unittest

from parqscan.utils.serialization import pretty_text


class SerializationTests(unittest.TestCase):
    def test_json_object_text_is_pretty_printed(self) -> None:
        value = '{"name":"ParqScan","items":[{"enabled":true},2]}'
        expected = json.dumps(json.loads(value), ensure_ascii=False, indent=2)
        self.assertEqual(pretty_text(value), expected)

    def test_json_array_text_is_pretty_printed(self) -> None:
        value = '[{"name":"A"},[1,2,3]]'
        expected = json.dumps(json.loads(value), ensure_ascii=False, indent=2)
        self.assertEqual(pretty_text(value), expected)

    def test_json_text_with_bom_and_whitespace_is_pretty_printed(self) -> None:
        value = '\ufeff  {"message":"中文","nested":{"value":1}}  '
        expected = json.dumps({"message": "中文", "nested": {"value": 1}}, ensure_ascii=False, indent=2)
        self.assertEqual(pretty_text(value), expected)

    def test_invalid_json_text_is_preserved(self) -> None:
        value = '{"name":"ParqScan",}'
        self.assertEqual(pretty_text(value), value)

    def test_json_scalar_text_is_preserved(self) -> None:
        for value in ('true', '123', '"text"'):
            with self.subTest(value=value):
                self.assertEqual(pretty_text(value), value)

    def test_native_container_remains_pretty_printed(self) -> None:
        value = {"items": ["A", {"value": 1}]}
        expected = json.dumps(value, ensure_ascii=False, indent=2)
        self.assertEqual(pretty_text(value), expected)


if __name__ == "__main__":
    unittest.main()
