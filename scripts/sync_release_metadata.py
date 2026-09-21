from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_JSON = ROOT / "parqscan" / "resources" / "release.json"


def read_release() -> str:
    payload = json.loads(RELEASE_JSON.read_text(encoding="utf-8"))
    release = payload.get("release")
    if not isinstance(release, str) or not release.strip():
        raise ValueError(f"Invalid release metadata in {RELEASE_JSON}")
    return release.strip()


def write_json(path: Path, release: str) -> None:
    path.write_text(json.dumps({"release": release}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def replace_in_file(path: Path, replacements: list[tuple[re.Pattern[str], str]]) -> None:
    text = path.read_text(encoding="utf-8")
    updated = text
    for pattern, replacement in replacements:
        updated, count = pattern.subn(replacement, updated, count=1)
        if count != 1:
            raise ValueError(f"Expected one replacement in {path} for pattern {pattern.pattern}")
    path.write_text(updated, encoding="utf-8")


def sync_release_metadata(release: str) -> None:
    write_json(ROOT / "docs" / "version.json", release)

    replace_in_file(
        ROOT / "docs" / "js" / "site.js",
        [(re.compile(r'release:\s*"[^"]+"'), f'release: "{release}"')],
    )

    for page in ("docs/index.html", "docs/guide.html"):
        replace_in_file(
            ROOT / page,
            [(re.compile(r"(<span data-version>版本 )[^<]+(</span>)"), rf"\g<1>{release}\g<2>")],
        )

    replace_in_file(
        ROOT / "README.md",
        [(re.compile(r"当前版本 \*\*[^*]+\*\*"), f"当前版本 **{release}**")],
    )

    replace_in_file(
        ROOT / "PRODUCT.md",
        [(re.compile(r"Current release: [^\s]+"), f"Current release: {release}")],
    )


def main() -> int:
    release = read_release()
    sync_release_metadata(release)
    print(f"Synced release metadata for {release}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
