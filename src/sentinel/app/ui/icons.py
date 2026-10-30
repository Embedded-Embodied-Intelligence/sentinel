"""The icons of the pages (WP10; ADR-0027): inline SVG line icons drawn for this project on a 24 px
grid, one stroke width, no icon font and no network. Icons are decoration: `aria-hidden` always,
and the word next to them carries the meaning (docs/design/brief.md, section 3.5)."""

from markupsafe import Markup

PATHS = {
    "alert": '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.4v.1"/>',
    "arrow-down": '<path d="M12 5v14M6 13l6 6 6-6"/>',
    "arrow-left": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    "arrow-right": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "arrow-up": '<path d="M12 19V5M6 11l6-6 6 6"/>',
    "book": '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5zM4 20.5A2.5 2.5 0 '
    '0 0 6.5 21H20v-3"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.8 2.8L16 9.6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5.4l3.6 2.1"/>',
    "clock-dashed": '<path d="M12 3a9 9 0 0 1 9 9M21 12a9 9 0 0 1-9 9" stroke-dasharray="3 3"/>'
    '<path d="M12 21a9 9 0 1 1 0-18"/><path d="M12 7v5.4l3.6 2.1"/>',
    "cross-circle": '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    "document": '<path d="M6 3h8l5 5v13H6zM14 3v5h5M9 13h7M9 17h7"/>',
    "dot": '<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>',
    "flag": '<path d="M6 21V4M6 4h11l-2 4 2 4H6"/>',
    "folder": '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v9a1.5 1.5 0 0 1'
    '-1.5 1.5h-15A1.5 1.5 0 0 1 3 18z"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1'
    'M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.5v.1"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "minus": '<path d="M5 12h14"/>',
    "more": '<circle cx="5" cy="12" r="1.5" fill="currentColor" stroke="none"/>'
    '<circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"/>'
    '<circle cx="19" cy="12" r="1.5" fill="currentColor" stroke="none"/>',
    "person-off": '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c.6-3.8 3.3-5.8 7-5.8s6.4 2 7 5.8'
    'M4 4l16 16"/>',
    "play": '<circle cx="12" cy="12" r="9"/><path d="M10 8.5l5.5 3.5-5.5 3.5z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "sliders": '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/>'
    '<circle cx="9" cy="17" r="2"/>',
    "swap": '<path d="M4 8h14M14 4l4 4-4 4M20 16H6M10 12l-4 4 4 4"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
}
SIZES = (12, 14, 16, 20, 24, 40)


def icon(name: str, size: int = 16) -> Markup:
    """An inline SVG icon of `size` px, hidden from screen readers."""
    return Markup(
        f'<svg class="icon" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true" focusable="false">{PATHS[name]}</svg>'
    )
