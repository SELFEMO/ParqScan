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
    releasesPageUrl,
    latestDownloadUrl,
  };
})();
