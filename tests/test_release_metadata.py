from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts import sync_release_metadata


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_sync_updates_docs_version(self) -> None:
        release = sync_release_metadata.read_release()
        sync_release_metadata.sync_release_metadata(release)
        docs_version = json.loads((ROOT / "docs" / "version.json").read_text(encoding="utf-8"))["release"]
        self.assertEqual(docs_version, release)

    def test_release_js_helpers_exist(self) -> None:
        source = (ROOT / "docs" / "js" / "release.js").read_text(encoding="utf-8")
        for name in ("normalizeTag", "findAssetUrl", "latestDownloadUrl"):
            self.assertIn(name, source)


if __name__ == "__main__":
    unittest.main()
