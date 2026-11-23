(function () {
  "use strict";

  function normalizeTag(tag) {
    if (typeof tag !== "string") {
      return "";
    }
    return tag.replace(/^v/i, "");
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

  function releasesPageUrl(repoUrl) {
    if (typeof repoUrl !== "string" || !repoUrl) {
      return "";
    }
    return `${repoUrl.replace(/\/$/, "")}/releases/latest`;
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
    findAssetUrl,
    detectPlatform,
    preferredAssetName,
    releasesPageUrl,
    latestDownloadUrl,
  };
})();
