(function () {
  "use strict";

  const STORAGE_LANG = "parqscan.lang";
  const STORAGE_THEME = "parqscan.theme";

  const state = {
    lang: "zh",
    theme: "system",
    strings: {},
    release: "0.3.8",
    repoUrl: "https://github.com/SELFEMO/ParqScan",
    licenseUrl: "https://www.apache.org/licenses/LICENSE-2.0.html",
    releaseApiUrl: "https://api.github.com/repos/SELFEMO/ParqScan/releases/latest",
    releasesListApiUrl: "https://api.github.com/repos/SELFEMO/ParqScan/releases",
    windowsAssetName: "ParqScan-Windows-Setup.exe",
    macosArm64AssetName: "ParqScan-macOS-arm64.dmg",
    linuxDebAssetName: "ParqScan-Linux-amd64.deb",
    linuxRpmAssetName: "ParqScan-Linux-x86_64.rpm",
    releaseDownloadUrl: "",
    releaseDownloadAvailable: null,
    demoPage: 0,
    demoPageSize: 20,
  };

  function detectLang() {
    const saved = localStorage.getItem(STORAGE_LANG);
    if (saved === "zh" || saved === "en") {
      return saved;
    }
    const nav = (navigator.language || "en").toLowerCase();
    return nav.startsWith("zh") ? "zh" : "en";
  }

  function detectTheme() {
    const saved = localStorage.getItem(STORAGE_THEME);
    if (saved === "light" || saved === "dark" || saved === "system") {
      return saved;
    }
    return "system";
  }

  function applyTheme(theme) {
    state.theme = theme;
    localStorage.setItem(STORAGE_THEME, theme);
    const root = document.documentElement;
    if (theme === "system") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", theme);
    }
    document.querySelectorAll("[data-theme-btn]").forEach((btn) => {
      btn.setAttribute("aria-pressed", btn.dataset.themeBtn === theme ? "true" : "false");
    });
  }

  function t(path, vars) {
    const parts = path.split(".");
    let value = state.strings;
    for (const part of parts) {
      if (value == null) {
        return path;
      }
      value = value[part];
    }
    if (typeof value !== "string") {
      return path;
    }
    if (!vars) {
      return value;
    }
    return value.replace(/\{(\w+)\}/g, (_, key) => (vars[key] != null ? String(vars[key]) : `{${key}}`));
  }

  function setText(selector, path, vars) {
    document.querySelectorAll(selector).forEach((el) => {
      el.textContent = t(path, vars);
    });
  }

  function setHtml(selector, html) {
    document.querySelectorAll(selector).forEach((el) => {
      el.innerHTML = html;
    });
  }

  async function loadJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to load ${url}`);
    }
    return response.json();
  }

  function loadStrings(lang) {
    const catalog = window.ParqScanI18n;
    if (!catalog || !catalog[lang]) {
      throw new Error(`Missing embedded locale: ${lang}`);
    }
    state.strings = catalog[lang];
    state.lang = lang;
    localStorage.setItem(STORAGE_LANG, lang);
    document.documentElement.lang = lang === "zh" ? "zh-Hans" : "en";
  }

  function bindControls() {
    document.querySelectorAll("[data-lang-toggle]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const next = state.lang === "zh" ? "en" : "zh";
        loadStrings(next);
        applyI18n();
        initDemo();
      });
    });

    document.querySelectorAll("[data-theme-btn]").forEach((btn) => {
      btn.addEventListener("click", () => {
        applyTheme(btn.dataset.themeBtn);
      });
    });
  }

  function applyMeta() {
    const page = document.body.dataset.page || "home";
    const titleKey = page === "guide" ? "meta.titleGuide" : page === "404" ? "meta.title404" : "meta.titleHome";
    const descKey = page === "guide" ? "meta.descriptionGuide" : "meta.descriptionHome";
    document.title = t(titleKey);
    const meta = document.querySelector('meta[name="description"]');
    if (meta) {
      meta.setAttribute("content", t(descKey));
    }
  }

  function detectedPlatformInfo() {
    const releaseApi = window.ParqScanRelease;
    const detected = releaseApi?.detectPlatform(navigator.userAgent, navigator.platform) || "windows";
    const platformName = releaseApi?.platformDisplayName(detected) || "Windows";
    const assetName = releaseApi?.preferredAssetName(state, navigator.userAgent, navigator.platform) || state.windowsAssetName;
    return { detected, platformName, assetName };
  }

  function applyReleaseLinks() {
    const releaseApi = window.ParqScanRelease;
    const { detected, platformName, assetName } = detectedPlatformInfo();
    const releasesPage = releaseApi?.allReleasesPageUrl(state.repoUrl) || state.repoUrl;
    const fallbackUrl =
      detected === "windows"
        ? releaseApi?.latestDownloadUrl(state.repoUrl, assetName) || releasesPage
        : releasesPage;
    const downloadUrl = state.releaseDownloadUrl || fallbackUrl;
    const unavailable = state.releaseDownloadAvailable === false || (state.releaseDownloadAvailable === null && detected !== "windows");

    document.querySelectorAll("[data-release-download]").forEach((el) => {
      el.href = downloadUrl || releasesPage;
      el.textContent = unavailable
        ? t("hero.ctaReleases")
        : t("hero.ctaDownloadPlatform", { platform: platformName });
    });

    const statusEl = document.getElementById("release-status");
    if (statusEl) {
      if (unavailable) {
        statusEl.hidden = false;
        statusEl.textContent = t("hero.noPackageNotice", { platform: platformName });
      } else {
        statusEl.hidden = true;
        statusEl.textContent = "";
      }
    }
  }

  async function loadLatestRelease() {
    const releaseApi = window.ParqScanRelease;
    if (!releaseApi) {
      return;
    }

    let releasePayload = null;

    if (state.releasesListApiUrl) {
      try {
        const response = await fetch(state.releasesListApiUrl, {
          headers: { Accept: "application/vnd.github+json" },
        });
        if (response.ok) {
          const listPayload = await response.json();
          releasePayload = releaseApi.selectNewestRelease(listPayload);
        }
      } catch (_error) {
        /* fall back to /releases/latest */
      }
    }

    if (!releasePayload && state.releaseApiUrl) {
      try {
        const response = await fetch(state.releaseApiUrl, {
          headers: { Accept: "application/vnd.github+json" },
        });
        if (response.ok) {
          releasePayload = await response.json();
        }
      } catch (_error) {
        /* keep offline fallback */
      }
    }

    if (releasePayload) {
      const info = releaseApi.resolveDownloadInfo(
        releasePayload,
        state,
        navigator.userAgent,
        navigator.platform,
        state.repoUrl
      );
      if (info.version) {
        state.release = info.version;
      }
      state.releaseDownloadAvailable = info.available;
      state.releaseDownloadUrl = info.url;
    }
  }

  function applyI18n() {
    applyMeta();

    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.dataset.i18n;
      const html = el.dataset.i18nHtml === "true";
      const value = t(key);
      if (html) {
        el.innerHTML = value;
      } else {
        el.textContent = value;
      }
    });

    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.setAttribute("placeholder", t(el.dataset.i18nPlaceholder));
    });

    document.querySelectorAll("[data-repo-link]").forEach((el) => {
      el.href = state.repoUrl;
    });

    document.querySelectorAll("[data-license-link]").forEach((el) => {
      el.href = state.licenseUrl;
    });

    setText("[data-version]", "footer.version", { release: state.release });

    const workflow = document.getElementById("workflow-steps");
    if (workflow && Array.isArray(state.strings.workflow?.steps)) {
      workflow.innerHTML = state.strings.workflow.steps.map((step) => `<li>${step}</li>`).join("");
    }

    const exportList = document.getElementById("export-formats");
    const exportSection = state.strings.guide?.export;
    if (exportList && Array.isArray(exportSection?.items)) {
      const items = exportSection.items.map((item) => `<li>${item}</li>`).join("");
      const note = exportSection.note ? `<li>${exportSection.note}</li>` : "";
      exportList.innerHTML = items + note;
    }

    applyReleaseLinks();
  }

  function demoTotalPages() {
    const pages = state.strings.demo?.pages || [];
    return Math.max(pages.length, 1);
  }

  function renderDemoTable() {
    const tbody = document.getElementById("demo-tbody");
    if (!tbody) {
      return;
    }
    const pages = state.strings.demo?.pages || [];
    const rows = pages[state.demoPage] || [];
    tbody.innerHTML = rows
      .map(
        (row) => `
      <tr>
        <td>${row.id}</td>
        <td><span class="demo-thumb" style="background: hsl(${row.hue} 62% 58% / 0.88)" role="img" aria-label=""></span></td>
        <td class="demo-label">${row.label}</td>
      </tr>`
      )
      .join("");
  }

  function renderDemoPagination() {
    const summary = document.getElementById("demo-summary");
    const pageButtons = document.getElementById("demo-page-buttons");
    const prev = document.getElementById("demo-prev");
    const next = document.getElementById("demo-next");
    const first = document.getElementById("demo-first");
    const last = document.getElementById("demo-last");
    const total = demoTotalPages();
    const current = state.demoPage + 1;

    if (summary) {
      summary.textContent = t("demo.pageSummary", { page: current, total });
    }
    if (prev) {
      prev.disabled = state.demoPage <= 0;
      prev.setAttribute("aria-label", t("demo.prev"));
    }
    if (next) {
      next.disabled = state.demoPage >= total - 1;
      next.setAttribute("aria-label", t("demo.next"));
    }
    if (first) {
      first.disabled = state.demoPage <= 0;
      first.setAttribute("aria-label", t("demo.first"));
    }
    if (last) {
      last.disabled = state.demoPage >= total - 1;
      last.setAttribute("aria-label", t("demo.last"));
    }
    if (pageButtons) {
      pageButtons.innerHTML = "";
      for (let i = 0; i < total; i += 1) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = String(i + 1);
        btn.setAttribute("aria-label", t("demo.pageSummary", { page: i + 1, total }));
        if (i === state.demoPage) {
          btn.setAttribute("aria-current", "page");
        }
        btn.addEventListener("click", () => {
          state.demoPage = i;
          renderDemo();
        });
        pageButtons.appendChild(btn);
      }
    }
  }

  function renderDemo() {
    renderDemoTable();
    renderDemoPagination();
  }

  let demoBound = false;

  function bindDemoControls() {
    if (demoBound) {
      return;
    }
    demoBound = true;

    const sizeGroup = document.getElementById("demo-page-size");
    if (sizeGroup) {
      sizeGroup.querySelectorAll("[data-size]").forEach((btn) => {
        btn.addEventListener("click", () => {
          state.demoPageSize = Number(btn.dataset.size);
          syncDemoPageSize();
        });
      });
    }

    document.getElementById("demo-prev")?.addEventListener("click", () => {
      if (state.demoPage > 0) {
        state.demoPage -= 1;
        renderDemo();
      }
    });
    document.getElementById("demo-next")?.addEventListener("click", () => {
      if (state.demoPage < demoTotalPages() - 1) {
        state.demoPage += 1;
        renderDemo();
      }
    });
    document.getElementById("demo-first")?.addEventListener("click", () => {
      state.demoPage = 0;
      renderDemo();
    });
    document.getElementById("demo-last")?.addEventListener("click", () => {
      state.demoPage = demoTotalPages() - 1;
      renderDemo();
    });
  }

  function syncDemoPageSize() {
    const sizeGroup = document.getElementById("demo-page-size");
    if (!sizeGroup) {
      return;
    }
    sizeGroup.querySelectorAll("[data-size]").forEach((btn) => {
      const active = Number(btn.dataset.size) === state.demoPageSize;
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function initDemo() {
    const table = document.getElementById("demo-panel");
    if (!table) {
      return;
    }

    bindDemoControls();
    setText("#demo-col-id", "demo.columns.id");
    setText("#demo-col-image", "demo.columns.image");
    setText("#demo-col-label", "demo.columns.label");

    syncDemoPageSize();

    renderDemo();
  }

  async function boot() {
    state.lang = detectLang();
    state.theme = detectTheme();
    applyTheme(state.theme);
    bindControls();

    try {
      loadStrings(state.lang);
    } catch (_error) {
      const fallback = window.ParqScanI18n?.zh;
      if (fallback) {
        state.strings = fallback;
        state.lang = "zh";
      }
    }

    try {
      const [version, site] = await Promise.all([
        loadJson("version.json").catch(() => ({ release: state.release })),
        loadJson("site.json").catch(() => ({
          repoUrl: state.repoUrl,
          licenseUrl: state.licenseUrl,
          releaseApiUrl: state.releaseApiUrl,
          releasesListApiUrl: state.releasesListApiUrl,
          windowsAssetName: state.windowsAssetName,
          macosArm64AssetName: state.macosArm64AssetName,
          linuxDebAssetName: state.linuxDebAssetName,
          linuxRpmAssetName: state.linuxRpmAssetName,
        })),
      ]);
      state.release = version.release || state.release;
      state.repoUrl = site.repoUrl || state.repoUrl;
      state.licenseUrl = site.licenseUrl || state.licenseUrl;
      state.releaseApiUrl = site.releaseApiUrl || state.releaseApiUrl;
      state.releasesListApiUrl = site.releasesListApiUrl || state.releasesListApiUrl;
      state.windowsAssetName = site.windowsAssetName || state.windowsAssetName;
      state.macosArm64AssetName = site.macosArm64AssetName || state.macosArm64AssetName;
      state.linuxDebAssetName = site.linuxDebAssetName || state.linuxDebAssetName;
      state.linuxRpmAssetName = site.linuxRpmAssetName || state.linuxRpmAssetName;
      await loadLatestRelease();
    } catch (_error) {
      /* keep defaults */
    }

    applyI18n();
    initDemo();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
