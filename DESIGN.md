---
name: ParqScan
description: Cool blue-gray desktop inspector extended to a static marketing and guide site.
colors:
  accent: "#258BFF"
  accent-hover-light: "#147BE8"
  accent-hover-dark: "#47A3FF"
  accent-soft-light: "#EEF5FF"
  accent-text-light: "#0F6FDB"
  bg-light: "#F6F8FC"
  surface-light: "#FFFFFF"
  surface-raised-light: "#FBFCFE"
  text-light: "#172033"
  text-strong-light: "#101828"
  text-muted-light: "#667085"
  border-light: "#E3E8F0"
  bg-dark: "#111827"
  surface-dark: "#1A2433"
  surface-raised-dark: "#151D2A"
  text-dark: "#E6EDF7"
  text-strong-dark: "#F8FAFC"
  text-muted-dark: "#94A3B8"
  border-dark: "#344154"
typography:
  body:
    fontFamily: "\"Noto Sans SC\", \"Segoe UI\", \"Microsoft YaHei UI\", \"PingFang SC\", sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
  display:
    fontFamily: "\"Noto Sans SC\", \"Segoe UI\", \"Microsoft YaHei UI\", \"PingFang SC\", sans-serif"
    fontSize: "clamp(2rem, 4vw, 2.75rem)"
    fontWeight: 760
    lineHeight: 1.12
    letterSpacing: "-0.03em"
  mono:
    fontFamily: "\"Cascadia Mono\", \"Consolas\", \"Noto Sans Mono\", monospace"
rounded:
  card: "13px"
  toolbar: "11px"
  control: "9px"
  brand: "11px"
  chip: "10px"
spacing:
  section: "64px"
  block: "32px"
  card: "24px"
  control-gap: "12px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#FFFFFF"
    rounded: "{rounded.control}"
    padding: "0 16px"
  button-secondary:
    backgroundColor: "{colors.surface-light}"
    textColor: "{colors.text-strong-light}"
    rounded: "{rounded.control}"
    padding: "0 16px"
  card-surface:
    backgroundColor: "{colors.surface-light}"
    textColor: "{colors.text-light}"
    rounded: "{rounded.card}"
    padding: "24px"
---

## Overview

ParqScan’s visual world is a cool blue-gray productivity surface with one committed accent (`#258BFF`). The desktop app established rounded cards, metric accent bars, and restrained chips; the GitHub Pages site inherits those tokens and adds a single persuasive device—the interactive “current page only” table demo on the home page.

Surfaces: static web (`docs/`) for persuasion and reading; PySide6 desktop app for operation. Web uses Noto Sans SC for embeddable bilingual body and display type.

## Colors

| Role | Light | Dark |
|------|-------|------|
| Page background | `#F6F8FC` | `#111827` |
| Card / panel | `#FFFFFF` | `#1A2433` |
| Raised chrome | `#FBFCFE` | `#151D2A` |
| Primary text | `#101828` / `#172033` | `#F8FAFC` / `#E6EDF7` |
| Muted text | `#667085` | `#94A3B8` |
| Border | `#E3E8F0` | `#344154` |
| Accent | `#258BFF` | `#258BFF` |
| Accent hover | `#147BE8` | `#47A3FF` |
| Accent soft fill | `#EEF5FF` | `#223047` |

Accent is reserved for primary actions, current pagination, metric bars, and the memory indicator—not decorative gradients.

## Typography

- One family for display and body on web: **Noto Sans SC** with system CJK fallbacks.
- Desktop app uses Segoe UI / Microsoft YaHei UI in QSS; web mirrors weight steps (620–760) without importing Inter or other generic SaaS defaults.
- Prose measure: **65–75ch** on guide pages; code in Cascadia Mono / Consolas.
- Headings use negative tracking on hero only (`-0.03em`); no eyebrow labels above titles.

## Layout

- Content shell: `min(1120px, viewport − 48px)`.
- Home hero: two-column grid collapsing to single column ≤960px.
- Mechanisms: split rows (title column + body), not three identical cards.
- Guide: sticky side nav + article; nav becomes static on small screens.
- Mobile header hides inline nav links; brand + theme + language remain.

## Elevation & Depth

- Cards use a single soft shadow: `0 14px 40px rgba(16,24,40,.08)` (light) / deeper black shadow in dark.
- Sticky header uses translucent raised surface + `backdrop-filter: blur(10px)`.
- No glass decoration, gradient text, or hard offset neobrutalist shadows.

## Shapes

| Token | Value | Usage |
|-------|-------|-------|
| Card radius | 13px | Panels, demo table, guide nav |
| Control radius | 9px | Buttons, inputs, pagination |
| Brand mark | 11px | Logo tile |
| Metric accent | 2px bar | Mechanism titles (left edge) |

## Components

- **Primary button**: filled `#258BFF`, white label, 38px min height.
- **Secondary button**: white/dark surface, border `#D7DFEA` / `#39485C`.
- **Ghost control**: language toggle; no arrow suffix on links.
- **Demo table**: rounded card, monospace labels, 48px color-block thumbnails standing in for decoded images.
- **Theme control**: segmented group (system / light / dark), persisted in `localStorage`.
- **Focus**: `box-shadow` ring `rgba(37,139,255,.28)`; visible keyboard focus on all controls.

## Do's and Don'ts

**Do**

- Lead the home page with the paging mechanism, not hero metrics or feature-icon grids.
- Keep copy factual—README and locale files are the source of claims.
- Use relative asset paths in `docs/` for GitHub Pages project sites.
- Respect `prefers-reduced-motion` and `prefers-color-scheme` when theme is “system”.

**Don't**

- Add eyebrow kickers, gradient headlines, or numbered section markers without sequential meaning.
- Invent testimonials, download counts, or screenshots not in the repo.
- Reference files outside `docs/` from the published site.
- Use emoji as structural icons.
