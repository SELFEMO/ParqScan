from __future__ import annotations

import re


_VERSION_PATTERN = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-+].*)?$")


def normalize_version(value: str) -> str:
    if not isinstance(value, str):
        return ""
    stripped = value.strip()
    lowered = stripped.casefold()
    for prefix in ("pre-release-v", "v"):
        if lowered.startswith(prefix):
            stripped = stripped[len(prefix) :].strip()
            break
    match = _VERSION_PATTERN.match(stripped)
    if match:
        major, minor, patch = match.groups()
        return f"{int(major)}.{int(minor or 0)}.{int(patch or 0)}"
    return stripped


def version_tuple(value: str) -> tuple[int, int, int]:
    normalized = normalize_version(value)
    match = _VERSION_PATTERN.match(normalized)
    if not match:
        return (0, 0, 0)
    major, minor, patch = match.groups()
    return (int(major), int(minor or 0), int(patch or 0))


def compare_versions(left: str, right: str) -> int:
    left_tuple = version_tuple(left)
    right_tuple = version_tuple(right)
    if left_tuple < right_tuple:
        return -1
    if left_tuple > right_tuple:
        return 1
    return 0
