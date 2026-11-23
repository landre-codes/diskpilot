from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
from appshell.theme import init_theme


def _luminance(color: str) -> float:
    text = color.lstrip("#")
    red, green, blue = (int(text[index : index + 2], 16) / 255 for index in (0, 2, 4))

    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(red)
        + 0.7152 * channel(green)
        + 0.0722 * channel(blue)
    )


def _contrast(foreground: str, background: str) -> float:
    first, second = sorted(
        (_luminance(foreground), _luminance(background)),
        reverse=True,
    )
    return (first + 0.05) / (second + 0.05)


def test_theme_text_roles_meet_wcag_aa(qapp, tmp_path: Path) -> None:
    theme = init_theme(qapp, AppConfig(tmp_path / "config"))

    for key in ("dark", "light"):
        theme.apply(key, persist=False)
        surface = theme.color("surface")
        for role in (
            "text",
            "input_text",
            "muted",
            "faint",
            "primary",
            "danger",
            "warn",
            "info",
        ):
            ratio = _contrast(theme.color(role), surface)
            assert ratio >= 4.5, f"{key}/{role}: {ratio:.2f}"

        on_primary = theme.color("on_primary")
        for role in ("primary", "primary_hover", "primary_pressed"):
            ratio = _contrast(on_primary, theme.color(role))
            assert ratio >= 4.5, f"{key}/on_primary/{role}: {ratio:.2f}"
