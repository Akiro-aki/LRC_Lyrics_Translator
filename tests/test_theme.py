"""Tests for the TUI theme palettes and prompt_toolkit Style builder."""

import pytest

from prompt_toolkit.styles import Style

from audio2lrc.theme import (
    DEFAULT_THEME,
    THEME_BUILDERS,
    available_themes,
    build_style,
    get_theme,
)

COLOR_FIELDS = (
    "primary",
    "accent",
    "secondary",
    "text",
    "muted",
    "background",
    "panel",
    "element",
    "border",
    "success",
    "error",
    "warning",
    "info",
    "selected_bg",
)


@pytest.mark.parametrize("name", list(THEME_BUILDERS))
def test_every_theme_has_all_color_fields(name):
    colors = get_theme(name)
    for field in COLOR_FIELDS:
        assert getattr(colors, field) is not None, f"{name}.{field} is missing"


@pytest.mark.parametrize("name", list(THEME_BUILDERS))
def test_every_theme_builds_a_style(name):
    style = build_style(get_theme(name))
    assert isinstance(style, Style)
    keys = {k for k, _ in style.style_rules}
    for expected in ("dialog", "dialog.body", "dialog frame.label", "button.focused", "radio-selected"):
        assert expected in keys, f"{name} style missing rule {expected}"


def test_system_theme_uses_terminal_adaptive_tokens():
    sys = get_theme("system")
    assert sys.primary == "ansicyan"
    assert sys.background == "transparent"
    assert sys.text == "default"
    # Transparent/default tokens must never leak an empty "bg:"/"fg:" prefix.
    from prompt_toolkit.styles.style import _parse_style_str

    for _, style_str in build_style(sys).style_rules:
        _parse_style_str(style_str)  # raises ValueError on e.g. "fg:"


def test_get_theme_none_uses_default():
    colors = get_theme(None)
    assert colors == get_theme(DEFAULT_THEME)
    assert colors.primary == get_theme("opencode").primary


@pytest.mark.parametrize(
    "name,expected",
    [
        ("opencode", "opencode"),
        ("OPEncode", "opencode"),
        ("one-dark", "one-dark"),
        ("one_dark", "one-dark"),
        ("One Dark", "one-dark"),
        ("TOKYONIGHT", "tokyonight"),
    ],
)
def test_get_theme_normalizes_names(name, expected):
    assert get_theme(name).primary == get_theme(expected).primary


def test_get_theme_falls_back_on_unknown():
    colors = get_theme("bogus")
    assert colors == get_theme(DEFAULT_THEME)


def test_available_themes_are_selectable_pairs():
    themes = dict(available_themes())
    assert "system" in themes
    assert "opencode" in themes
    assert len(themes) == len(THEME_BUILDERS)
    for key, label in themes.items():
        assert key in THEME_BUILDERS
        assert label.strip()


def test_opencode_is_default_theme():
    assert DEFAULT_THEME == "opencode"


def test_build_style_is_consistent_for_all_themes():
    from prompt_toolkit.styles.style import _parse_style_str  # internals

    for name in THEME_BUILDERS:
        for _, style_str in build_style(get_theme(name)).style_rules:
            # Every rule must parse cleanly (raises ValueError otherwise).
            _parse_style_str(style_str)
