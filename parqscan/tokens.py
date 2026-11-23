from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemePaletteTokens:
    name: str
    bg: str
    surface: str
    surface_raised: str
    surface_muted: str
    grid_canvas: str
    text: str
    text_strong: str
    text_muted: str
    border: str
    border_input: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_text: str
    accent_soft: str
    on_primary: str
    on_primary_hover: str
    icon_muted: str
    icon_accent: str
    icon_disabled: str
    skeleton_fill: str
    search_match_bg: str
    search_match_border: str
    search_current_bg: str
    search_current_border: str
    selection_highlight: str
    null_text: str
    danger: str


LIGHT_TOKENS = ThemePaletteTokens(
    name="light",
    bg="#F6F8FC",
    surface="#FFFFFF",
    surface_raised="#FBFCFE",
    surface_muted="#EEF2F7",
    grid_canvas="#E8EEF6",
    text="#172033",
    text_strong="#101828",
    text_muted="#5A6B82",
    border="#CBD5E1",
    border_input="#94A3B8",
    accent="#0F6FDB",
    accent_hover="#0D5EC0",
    accent_pressed="#0A4EA3",
    accent_text="#0B5FC4",
    accent_soft="#E7F2FF",
    on_primary="#FFFFFF",
    on_primary_hover="#FFFFFF",
    icon_muted="#475569",
    icon_accent="#0B5FC4",
    icon_disabled="#94A3B8",
    skeleton_fill="#CBD5E1",
    search_match_bg="#258BFF",
    search_match_border="#0B5FC4",
    search_current_bg="#F59E0B",
    search_current_border="#B45309",
    selection_highlight="#258BFF",
    null_text="#64748B",
    danger="#D92D20",
)

DARK_TOKENS = ThemePaletteTokens(
    name="dark",
    bg="#0F1622",
    surface="#141E2B",
    surface_raised="#1A2433",
    surface_muted="#1E2A3A",
    grid_canvas="#0E1520",
    text="#E6EDF7",
    text_strong="#F8FAFC",
    text_muted="#94A3B8",
    border="#344154",
    border_input="#4B5E78",
    accent="#0F6FDB",
    accent_hover="#47A3FF",
    accent_pressed="#0E5EC0",
    accent_text="#7DBEFF",
    accent_soft="#1D3856",
    on_primary="#FFFFFF",
    on_primary_hover="#0B1220",
    icon_muted="#94A3B8",
    icon_accent="#7DBEFF",
    icon_disabled="#475569",
    skeleton_fill="#334155",
    search_match_bg="#38BDF8",
    search_match_border="#7DBEFF",
    search_current_bg="#FBBF24",
    search_current_border="#F59E0B",
    selection_highlight="#38BDF8",
    null_text="#7A8EA8",
    danger="#F87171",
)

THEME_TOKENS: dict[str, ThemePaletteTokens] = {
    "light": LIGHT_TOKENS,
    "dark": DARK_TOKENS,
}


def get_theme_tokens(theme: str) -> ThemePaletteTokens:
    return THEME_TOKENS.get(theme, LIGHT_TOKENS)
