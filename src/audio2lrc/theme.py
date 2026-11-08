"""Theme palettes and prompt_toolkit Style builders for the TUI.

mirrors opencode's approach: named hex themes plus a ``system`` theme that
adapts to the terminal's own accent colors using ANSI names and transparent
backgrounds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from prompt_toolkit.styles import Style

# ---------------------------------------------------------------------------
# Semantic color roles (mirrors opencode's ThemeColors).
# ---------------------------------------------------------------------------


@dataclass
class ThemeColors:
    """Semantic colors consumed by build_style().

    Values are prompt_toolkit style tokens: a hex color (``#rrggbb``), an ANSI
    name (``ansicyan``), ``default`` or ``transparent``.
    """

    primary: str = "ansicyan"
    accent: str = "ansicyan"
    secondary: str = "ansiblue"
    text: str = "default"
    muted: str = "default"
    background: str = "transparent"
    panel: str = "transparent"
    element: str = "transparent"
    border: str = "default"
    success: str = "ansigreen"
    error: str = "ansired"
    warning: str = "ansiyellow"
    info: str = "ansicyan"
    selected_bg: str = "transparent"


# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------


def opencode() -> ThemeColors:
    """opencode's default dark theme (near-black ramp, peach/purple accent)."""
    return ThemeColors(
        primary="#fab283",
        accent="#9d7cd8",
        secondary="#5c9cf5",
        text="#eeeeee",
        muted="#808080",
        background="#0a0a0a",
        panel="#141414",
        element="#1e1e1e",
        border="#606060",
        success="#7fd88f",
        error="#e06c75",
        warning="#f5a742",
        info="#56b6c2",
        selected_bg="#3c3c3c",
    )


def one_dark() -> ThemeColors:
    """Atom One Dark inspired palette."""
    return ThemeColors(
        primary="#61afef",
        accent="#c678dd",
        secondary="#56b6c2",
        text="#abb2bf",
        muted="#5c6370",
        background="#21252b",
        panel="#282c34",
        element="#2c313a",
        border="#3e4452",
        success="#98c379",
        error="#e06c75",
        warning="#e5c07b",
        info="#56b6c2",
        selected_bg="#3b4048",
    )


def tokyonight() -> ThemeColors:
    """Tokyo Night inspired palette."""
    return ThemeColors(
        primary="#7aa2f7",
        accent="#bb9af7",
        secondary="#2ac3de",
        text="#c0caf5",
        muted="#565f89",
        background="#1a1b26",
        panel="#1f2335",
        element="#292e42",
        border="#3b4261",
        success="#9ece6a",
        error="#f7768e",
        warning="#e0af68",
        info="#7dcfff",
        selected_bg="#33467c",
    )


def catppuccin() -> ThemeColors:
    """Catppuccin Mocha inspired palette."""
    return ThemeColors(
        primary="#89b4fa",
        accent="#cba6f7",
        secondary="#94e2d5",
        text="#cdd6f4",
        muted="#6c7086",
        background="#1e1e2e",
        panel="#181825",
        element="#313244",
        border="#45475a",
        success="#a6e3a1",
        error="#f38ba8",
        warning="#f9e2af",
        info="#89dceb",
        selected_bg="#45475a",
    )


def nord() -> ThemeColors:
    """Nord inspired palette."""
    return ThemeColors(
        primary="#88c0d0",
        accent="#b48ead",
        secondary="#5e81ac",
        text="#e5e9f0",
        muted="#4c566a",
        background="#2e3440",
        panel="#3b4252",
        element="#434c5e",
        border="#4c566a",
        success="#a3be8c",
        error="#bf616a",
        warning="#ebcb8b",
        info="#81a1c1",
        selected_bg="#4c566a",
    )


def gruvbox() -> ThemeColors:
    """Gruvbox dark inspired palette."""
    return ThemeColors(
        primary="#83a598",
        accent="#d3869b",
        secondary="#8ec07c",
        text="#ebdbb2",
        muted="#928374",
        background="#1d2021",
        panel="#282828",
        element="#32302f",
        border="#504945",
        success="#b8bb26",
        error="#fb4934",
        warning="#fabd2f",
        info="#83a598",
        selected_bg="#504945",
    )


def system() -> ThemeColors:
    """Adapt to the terminal's own accent colors.

    Uses ANSI color names (honouring whatever the user's terminal palette is
    configured to) and transparent/default backgrounds so the TUI blends in
    with the terminal rather than imposing its own palette.
    """
    return ThemeColors(
        primary="ansicyan",
        accent="ansicyan",
        secondary="ansiblue",
        text="default",
        muted="default",
        background="transparent",
        panel="transparent",
        element="transparent",
        border="default",
        success="ansigreen",
        error="ansired",
        warning="ansiyellow",
        info="ansicyan",
        selected_bg="ansigray",
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

THEME_BUILDERS: dict[str, Callable[[], ThemeColors]] = {
    "system": system,
    "opencode": opencode,
    "one-dark": one_dark,
    "tokyonight": tokyonight,
    "catppuccin": catppuccin,
    "nord": nord,
    "gruvbox": gruvbox,
}

THEME_LABELS: dict[str, str] = {
    "system": "System accent (adapt to terminal)",
    "opencode": "opencode (default)",
    "one-dark": "One Dark",
    "tokyonight": "Tokyo Night",
    "catppuccin": "Catppuccin",
    "nord": "Nord",
    "gruvbox": "Gruvbox",
}

DEFAULT_THEME = "opencode"


def get_theme(name: str | None) -> ThemeColors:
    """Return a ThemeColors for the given theme name.

    Falls back to the default theme when the name is unknown or empty.
    """
    key = (name or DEFAULT_THEME).strip().lower().replace("_", "-").replace(" ", "-")
    builder = THEME_BUILDERS.get(key)
    if builder is None:
        return THEME_BUILDERS[DEFAULT_THEME]()
    return builder()


def available_themes() -> list[tuple[str, str]]:
    """Return (key, label) pairs for the theme picker."""
    return [(k, THEME_LABELS[k]) for k in THEME_BUILDERS]


# ---------------------------------------------------------------------------
# Style builder
# ---------------------------------------------------------------------------


def _own(color: str | None) -> str | None:
    """Return a usable color token, or None when transparent/default-inherited."""
    if not color or color in ("transparent", "none"):
        return None
    return color


def _style(fg: str | None = None, bg: str | None = None, *attrs: str) -> str:
    """Build a prompt_toolkit style string, omitting empty fg/bg tokens."""
    parts: list[str] = []
    if (c := _own(fg)) is not None:
        parts.append(f"fg:{c}")
    if (c := _own(bg)) is not None:
        parts.append(f"bg:{c}")
    parts.extend(a for a in attrs if a)
    return " ".join(parts)


def build_style(theme: ThemeColors) -> Style:
    """Map a ThemeColors palette onto prompt_toolkit's dialog style classes."""
    text = _own(theme.text)
    styles = [
        # Dialog chrome.
        ("dialog", _style(bg=theme.background)),
        ("dialog.body", _style(fg=theme.text, bg=theme.panel)),
        ("dialog.body text-area", _style(fg=theme.text, bg=theme.element)),
        ("dialog.body text-area last-line", "underline"),
        ("dialog frame.label", _style(fg=theme.accent) + " bold"),
        # Buttons.
        ("button", _style(fg=theme.text)),
        ("button.arrow", _style(fg=theme.primary) + " bold"),
        ("button.text", _style(fg=theme.text)),
        ("button.focused", _style(fg=theme.background, bg=theme.primary) + " bold"),
        # Radio / checkbox list.
        ("radio", _style(fg=theme.text)),
        ("radio-selected", _style(fg=theme.text, bg=theme.selected_bg)),
        ("radio-checked", _style(fg=theme.primary) + " bold"),
        ("radio-number", _style(fg=theme.muted)),
        ("checkbox", _style(fg=theme.text)),
        ("checkbox-selected", _style(fg=theme.text, bg=theme.selected_bg)),
        ("checkbox-checked", _style(fg=theme.primary) + " bold"),
        # Scrollbars.
        ("dialog.body scrollbar.background", _style(bg=theme.element)),
        ("dialog.body scrollbar.button", _style(bg=theme.border)),
        ("dialog.body scrollbar.arrow", _style(fg=theme.muted)),
        ("dialog.body scrollbar.start", "nounderline"),
        ("dialog.body scrollbar.end", "nounderline"),
    ]
    return Style.from_dict(dict(styles))
