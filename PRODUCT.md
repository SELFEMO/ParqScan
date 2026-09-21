# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Static HTML, CSS, and JavaScript in `docs/` for GitHub Pages. No build step. Desktop app remains Python 3, PySide6, and PyArrow.

## Users

Data engineers, ML practitioners, and analysts who inspect Parquet files on disk. They work with large files, embedded images, and nested binary payloads. They need to browse schema and row data without loading an entire file into memory.

## Product Purpose

ParqScan is a cross-platform desktop inspector for Parquet files. It reads data page by page, previews embedded images on demand, inspects binary attachments, and exports to common formats. Success means opening a large file, understanding its structure, and inspecting or exporting specific rows without memory blowups.

## Positioning

The table model keeps only the current page in memory while still supporting file-wide search and column sort via row-index scans. Image decoding is deferred: thumbnails and hover previews use target sizes; full-resolution images decode only when record details are opened.

## Operating Context

Users open files from the file dialog, drag-and-drop, recent files, or the command line (`python main.py sample.parquet`). Typical workflow: metadata tab → data preview with explicit pagination → record details or raw-byte view → export. Configuration defaults to the user app-data directory; `portable.flag` in the program directory stores settings beside the binary.

## Capabilities and Constraints

- Fixed pagination: 20, 50, 100, or 200 rows per page.
- File-wide search (`Ctrl+F`) and current-page search are separate scopes.
- Column sort builds a file-wide row-index; table header does not provide full global sort UI.
- Current-page filter and copy-column apply only to the visible page.
- Supported image formats: JPEG, PNG, BMP, GIF, WEBP, TIFF, ICO, data URI, validated Base64; nested binary leaves are traversed.
- Export: CSV, JSON, Excel, Markdown, SQL, Parquet fragments; batch image extraction.
- Themes: light, dark, follow system. UI languages: Chinese and English.
- Current release: 0.3.2 (see `parqscan/resources/release.json`).
- License: Apache License 2.0.

## Brand Commitments

- Product name: ParqScan.
- Logo: mosaic tile blocks with a scan line (`parqscan/resources/ParqScan.svg`).
- Desktop visual system: cool blue-gray surfaces, `#258BFF` accent, rounded cards and controls (see `parqscan/styles/light.qss` and `dark.qss`).
- Voice: plain, task-oriented; errors state what happened and how to recover.
- GitHub repository: https://github.com/SELFEMO/ParqScan

## Evidence on Hand

- README.md: install, features, packaging, portable config.
- PROJECT_OVERVIEW.md: architecture and behavior boundaries.
- `parqscan/locales/zh.json` and `en.json`: in-app copy.
- `parqscan/resources/ParqScan.svg`: brand mark.
- No user testimonials, download counts, or performance benchmarks in the repository. The GitHub Pages site must not invent them.

## Product Principles

1. Never materialize an entire large Parquet file into memory for browsing.
2. Defer expensive work—full image decode, whole-file exports—until the user asks.
3. Keep file search, page filter, and navigation scopes explicit and isolated.
4. Match desktop affordances on the web site only where they aid comprehension; the site explains and links, it does not replace the app.
5. State only facts documented in the repository.

## Accessibility & Inclusion

- Web site: keyboard focus, sufficient contrast in light and dark themes, `prefers-reduced-motion` respected.
- Desktop app: bilingual UI; theme follows system when selected.
