from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from parqscan.update.constants import RELEASE_API_URL, USER_AGENT, WINDOWS_ASSET_NAME
from parqscan.update.versioning import normalize_version


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag_name: str
    download_url: str
    release_page_url: str
    body: str


def find_asset_url(assets: Any, asset_name: str) -> str:
    if not isinstance(assets, list) or not asset_name:
        return ""
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if asset.get("name") != asset_name:
            continue
        url = asset.get("browser_download_url")
        if isinstance(url, str) and url:
            return url
    return ""


def parse_release_payload(payload: dict[str, Any], asset_name: str = WINDOWS_ASSET_NAME) -> ReleaseInfo:
    tag_name = payload.get("tag_name")
    if not isinstance(tag_name, str) or not tag_name.strip():
        raise ValueError("Release payload is missing tag_name.")
    version = normalize_version(tag_name)
    download_url = find_asset_url(payload.get("assets"), asset_name)
    html_url = payload.get("html_url")
    release_page_url = html_url if isinstance(html_url, str) and html_url else ""
    body = payload.get("body")
    return ReleaseInfo(
        version=version,
        tag_name=tag_name.strip(),
        download_url=download_url,
        release_page_url=release_page_url,
        body=body if isinstance(body, str) else "",
    )


def fetch_latest_release(api_url: str = RELEASE_API_URL, asset_name: str = WINDOWS_ASSET_NAME) -> ReleaseInfo:
    request = Request(api_url, headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"GitHub API returned HTTP {error.code}.") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach GitHub API: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError("GitHub API returned invalid JSON.") from error

    if not isinstance(payload, dict):
        raise RuntimeError("GitHub API returned an unexpected payload.")
    return parse_release_payload(payload, asset_name)
