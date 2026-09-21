from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def i18n_keys(obj: object, prefix: str = "") -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            found.add(path)
            found.update(i18n_keys(value, path))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            found.update(i18n_keys(value, f"{prefix}[{index}]"))
    return found


class DocsSiteTests(unittest.TestCase):
    def test_required_pages_exist(self) -> None:
        for name in ("index.html", "guide.html", "404.html"):
            self.assertTrue((DOCS / name).is_file(), f"missing docs/{name}")

    def test_assets_and_config(self) -> None:
        self.assertTrue((DOCS / ".nojekyll").is_file())
        self.assertTrue((DOCS / "assets" / "logo.svg").is_file())
        self.assertTrue((DOCS / "css" / "app.css").is_file())
        self.assertTrue((DOCS / "js" / "site.js").is_file())
        self.assertTrue((DOCS / "js" / "i18n.js").is_file())
        version = json.loads((DOCS / "version.json").read_text(encoding="utf-8"))
        self.assertIn("release", version)

    def test_pages_include_embedded_i18n_script(self) -> None:
        for page in ("index.html", "guide.html", "404.html"):
            content = (DOCS / page).read_text(encoding="utf-8")
            self.assertIn('src="js/i18n.js"', content, page)
            self.assertLess(
                content.index('src="js/i18n.js"'),
                content.index('src="js/site.js"'),
                page,
            )

    def test_embedded_i18n_matches_json_sources(self) -> None:
        zh = json.loads((DOCS / "i18n" / "zh.json").read_text(encoding="utf-8"))
        en = json.loads((DOCS / "i18n" / "en.json").read_text(encoding="utf-8"))
        js = (DOCS / "js" / "i18n.js").read_text(encoding="utf-8")
        self.assertIn("window.ParqScanI18n", js)
        match = re.search(r"window\.ParqScanI18n\s*=\s*(\{.*\})\s*;", js, re.DOTALL)
        self.assertIsNotNone(match)
        embedded = json.loads(match.group(1))
        self.assertEqual(i18n_keys(embedded["zh"]), i18n_keys(zh))
        self.assertEqual(i18n_keys(embedded["en"]), i18n_keys(en))

    def test_relative_resource_paths(self) -> None:
        html = (DOCS / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="css/app.css"', html)
        self.assertIn('src="js/site.js"', html)
        self.assertIn('href="assets/favicon.svg"', html)
        self.assertNotRegex(html, r'href="/css/')
        self.assertNotRegex(html, r'src="/js/')

    def test_i18n_files_have_matching_keys(self) -> None:
        zh = json.loads((DOCS / "i18n" / "zh.json").read_text(encoding="utf-8"))
        en = json.loads((DOCS / "i18n" / "en.json").read_text(encoding="utf-8"))
        self.assertEqual(i18n_keys(zh), i18n_keys(en))

    def test_guide_has_nonempty_fallback_copy(self) -> None:
        guide = (DOCS / "guide.html").read_text(encoding="utf-8")
        required_keys = (
            "guide.intro",
            "guide.open.body",
            "guide.browse.body",
            "guide.detail.body",
            "guide.images.body",
            "guide.binary.body",
            "guide.portable.body",
            "guide.license.body",
        )
        for key in required_keys:
            pattern = re.compile(
                rf'<[^>]+data-i18n="{key}"[^>]*>(?P<body>[^<]+)</',
                re.MULTILINE,
            )
            match = pattern.search(guide)
            self.assertIsNotNone(match, f"missing fallback for {key}")
            self.assertTrue(match.group("body").strip(), f"empty fallback for {key}")

    def test_site_json_has_repo_url(self) -> None:
        site = json.loads((DOCS / "site.json").read_text(encoding="utf-8"))
        self.assertTrue(site.get("repoUrl", "").startswith("https://github.com/"))
        self.assertTrue(site.get("licenseUrl", "").startswith("https://www.apache.org/licenses/"))

    def test_no_root_absolute_paths_in_docs_html(self) -> None:
        pattern = re.compile(r'(?:href|src)="/(?!/)')
        for page in ("index.html", "guide.html", "404.html"):
            content = (DOCS / page).read_text(encoding="utf-8")
            self.assertIsNone(pattern.search(content), f"root-absolute path in {page}")


if __name__ == "__main__":
    unittest.main()
