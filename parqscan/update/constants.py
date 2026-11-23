from __future__ import annotations

import platform
import shutil
import sys

GITHUB_REPO = "https://github.com/SELFEMO/ParqScan"
RELEASE_API_URL = "https://api.github.com/repos/SELFEMO/ParqScan/releases/latest"
RELEASES_LIST_API_URL = "https://api.github.com/repos/SELFEMO/ParqScan/releases"
WINDOWS_ASSET_NAME = "ParqScan-Windows-Setup.exe"
MACOS_ARM64_ASSET_NAME = "ParqScan-macOS-arm64.dmg"
MACOS_X64_ASSET_NAME = "ParqScan-macOS-x86_64.dmg"
LINUX_DEB_AMD64_ASSET_NAME = "ParqScan-Linux-amd64.deb"
LINUX_DEB_ARM64_ASSET_NAME = "ParqScan-Linux-arm64.deb"
LINUX_RPM_X86_64_ASSET_NAME = "ParqScan-Linux-x86_64.rpm"
LINUX_RPM_AARCH64_ASSET_NAME = "ParqScan-Linux-aarch64.rpm"
CHECK_INTERVAL_SECONDS = 24 * 60 * 60
USER_AGENT = "ParqScan-Update"


def platform_asset_name(
    current_platform: str | None = None,
    machine: str | None = None,
    linux_package_manager: str | None = None,
) -> str:
    plat = (current_platform or sys.platform).lower()
    arch = (machine or platform.machine()).strip().lower()

    if plat.startswith("win"):
        return WINDOWS_ASSET_NAME
    if plat == "darwin":
        if arch in {"x86_64", "amd64"}:
            return MACOS_X64_ASSET_NAME
        return MACOS_ARM64_ASSET_NAME
    if plat.startswith("linux"):
        pkg = linux_package_manager
        if pkg is None:
            if shutil.which("dpkg"):
                pkg = "deb"
            elif shutil.which("rpm"):
                pkg = "rpm"
            else:
                pkg = "deb"
        is_arm = arch in {"aarch64", "arm64"}
        if pkg == "rpm":
            return LINUX_RPM_AARCH64_ASSET_NAME if is_arm else LINUX_RPM_X86_64_ASSET_NAME
        return LINUX_DEB_ARM64_ASSET_NAME if is_arm else LINUX_DEB_AMD64_ASSET_NAME
    return WINDOWS_ASSET_NAME
