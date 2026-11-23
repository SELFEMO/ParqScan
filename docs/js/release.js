(function () {
  "use strict";

  function normalizeTag(tag) {
    if (typeof tag !== "string") {
      return "";
    }
    return tag.replace(/^(?:pre-release-)?v/i, "");
  }

  function versionTuple(version) {
    const normalized = normalizeTag(String(version || ""));
    const match = normalized.match(/^(\d+)(?:\.(\d+))?(?:\.(\d+))?/);
    if (!match) {
      return [0, 0, 0];
    }
    return [Number(match[1] || 0), Number(match[2] || 0), Number(match[3] || 0)];
  }

  function compareVersions(a, b) {
    const va = versionTuple(a);
    const vb = versionTuple(b);
    for (let i = 0; i < 3; i += 1) {
      if (va[i] !== vb[i]) {
        return va[i] > vb[i] ? 1 : -1;
      }
    }
    return 0;
  }

  function findAssetUrl(assets, assetName) {
    if (!Array.isArray(assets) || !assetName) {
      return "";
    }
    const match = assets.find((asset) => asset && asset.name === assetName);
    return match && typeof match.browser_download_url === "string" ? match.browser_download_url : "";
  }

  function detectPlatform(userAgent, platform) {
    const ua = String(userAgent || "").toLowerCase();
    const plat = String(platform || "").toLowerCase();
    if (plat.includes("mac") || ua.includes("mac os") || ua.includes("macintosh")) {
      return "macos";
    }
    if (plat.includes("linux") || (ua.includes("linux") && !ua.includes("android"))) {
      return "linux";
    }
    return "windows";
  }

  function platformDisplayName(detected) {
    if (detected === "macos") {
      return "macOS";
    }
    if (detected === "linux") {
      return "Linux";
    }
    return "Windows";
  }

  function preferredAssetName(assetConfig, userAgent, platform) {
    const config = assetConfig || {};
    const detected = detectPlatform(userAgent, platform);
    if (detected === "macos") {
      return config.macosArm64AssetName || "ParqScan-macOS-arm64.dmg";
    }
    if (detected === "linux") {
      return config.linuxDebAssetName || "ParqScan-Linux-amd64.deb";
    }
    return config.windowsAssetName || "ParqScan-Windows-Setup.exe";
  }

  function selectNewestRelease(releases) {
    if (!Array.isArray(releases)) {
      return null;
    }
    const published = releases.filter((item) => item && !item.draft && typeof item.tag_name === "string");
    let newest = null;
    for (const item of published) {
      if (!newest || compareVersions(item.tag_name, newest.tag_name) > 0) {
        newest = item;
      }
    }
    return newest;
  }

  function resolveDownloadInfo(releasePayload, assetConfig, userAgent, platform, repoUrl) {
    const detected = detectPlatform(userAgent, platform);
    const assetName = preferredAssetName(assetConfig, userAgent, platform);
    const releasePage =
      (releasePayload && typeof releasePayload.html_url === "string" && releasePayload.html_url) ||
      releasesPageUrl(repoUrl);
    const assetUrl = releasePayload ? findAssetUrl(releasePayload.assets, assetName) : "";

    return {
      platform: detected,
      platformName: platformDisplayName(detected),
      assetName,
      available: Boolean(assetUrl),
      url: assetUrl || releasePage,
      releasePageUrl: releasePage,
      version: releasePayload ? normalizeTag(releasePayload.tag_name) : "",
    };
  }

  function releasesPageUrl(repoUrl) {
    if (typeof repoUrl !== "string" || !repoUrl) {
      return "";
    }
    return `${repoUrl.replace(/\/$/, "")}/releases/latest`;
  }

  function allReleasesPageUrl(repoUrl) {
    if (typeof repoUrl !== "string" || !repoUrl) {
      return "";
    }
    return `${repoUrl.replace(/\/$/, "")}/releases`;
  }

  function latestDownloadUrl(repoUrl, assetName) {
    const base = releasesPageUrl(repoUrl);
    if (!base || !assetName) {
      return base;
    }
    return `${base}/download/${assetName}`;
  }

  window.ParqScanRelease = {
    normalizeTag,
    compareVersions,
    findAssetUrl,
    detectPlatform,
    platformDisplayName,
    preferredAssetName,
    selectNewestRelease,
    resolveDownloadInfo,
    releasesPageUrl,
    allReleasesPageUrl,
    latestDownloadUrl,
  };
})();
