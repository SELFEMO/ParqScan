from __future__ import annotations

import json
import unittest
from pathlib import Path


class LocaleTests(unittest.TestCase):
    def test_language_keys_match(self) -> None:
        root = Path(__file__).resolve().parents[1] / "parqscan" / "locales"
        english = json.loads((root / "en.json").read_text(encoding="utf-8"))
        chinese = json.loads((root / "zh.json").read_text(encoding="utf-8"))

        def flatten(value, prefix="") -> set[str]:
            keys: set[str] = set()
            for key, nested in value.items():
                full = f"{prefix}.{key}" if prefix else key
                if isinstance(nested, dict):
                    keys.update(flatten(nested, full))
                else:
                    keys.add(full)
            return keys

        self.assertEqual(flatten(english), flatten(chinese))


if __name__ == "__main__":
    unittest.main()
