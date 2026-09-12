"""Small static UI contracts; browser QA owns actual overflow and computed styles."""

from pathlib import Path

import pytest

from test_editor_layout import _properties


CSS = (Path(__file__).resolve().parents[1] / "web/styles.css").read_text(encoding="utf-8")


def _rgb(hex_color):
    return tuple(int(hex_color[offset:offset + 2], 16) / 255 for offset in (1, 3, 5))


def _contrast(foreground, background):
    def luminance(color):
        channels = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in _rgb(color)]
        return sum(channel * weight for channel, weight in zip(channels, (.2126, .7152, .0722)))

    first, second = sorted((luminance(foreground), luminance(background)))
    return (second + .05) / (first + .05)


@pytest.mark.parametrize("width,columns", [(375, 1), (768, 3), (1024, 3), (1440, 3)])
def test_welcome_steps_use_shrinkable_tracks_and_reflow_at_phone_width(width, columns):
    props = _properties(".welcome-workflow", width)
    expected = "minmax(0,1fr)" if columns == 1 else "repeat(3,minmax(0,1fr))"
    assert props["grid-template-columns"] == expected
    assert props["gap"] == "var(--space-4)"


@pytest.mark.parametrize("width,columns", [(375, 1), (768, 2), (1024, 2), (1440, 3)])
def test_style_cards_wrap_before_their_labels_are_squeezed(width, columns):
    expected = "minmax(0,1fr)" if columns == 1 else f"repeat({columns},minmax(0,1fr))"
    assert _properties(".edit-style-grid", width)["grid-template-columns"] == expected
    assert _properties(".edit-style-card small", width)["font-size"] == "var(--text-caption)"
    assert _properties(".edit-style-card > b", width)["white-space"] == "normal"


def test_style_selection_has_a_filled_radio_shape_and_only_selected_detail():
    assert _properties(".edit-style-card::before")["border-radius"] == "50%"
    assert _properties(".edit-style-card.active::before")["box-shadow"].startswith("inset")
    assert _properties(".edit-style-card .style-story-flow")["display"] == "none"
    assert _properties(".edit-style-card.active .style-story-flow")["display"] == "block"


@pytest.mark.parametrize("selector", [
    ".button:hover:not(:disabled)",
    ".button:active:not(:disabled)",
    "#newProjectButton:hover:not(:disabled)",
    ".recent-project:hover",
    ".edit-style-card:hover",
    ".choice.outcome-primary:hover",
    ".draft-tool-grid button:hover:not(:disabled)",
])
def test_primary_hit_targets_do_not_move_on_hover_or_press(selector):
    props = _properties(selector)
    assert props["transform"] == "none"
    assert props["translate"] == "none"


@pytest.mark.parametrize("width", [375, 768, 1024, 1440])
def test_fps_controls_keep_readable_help_and_flexible_width(width):
    for selector in (".output-control-grid select", ".export-fps-field select"):
        props = _properties(selector, width)
        assert props["min-height"] == "44px"
        assert props["width"] == "100%"
        assert props["min-width"] == "0"
    for selector in (".fps-field small", ".export-fps-field small"):
        props = _properties(selector, width)
        assert props["font-size"] == "var(--text-caption)"
        assert props["overflow-wrap"] == "anywhere"


def test_disclosure_uses_native_marker_and_a_visible_focus_ring():
    props = _properties(".setup-audio-disclosure > summary")
    assert props["min-height"] == "64px"
    assert props["list-style-position"] == "inside"
    focused = _properties(".setup-audio-disclosure > summary:focus-visible")
    assert focused["outline"] == "3pxsolidvar(--focus-ring)"
    assert focused["outline-offset"] == "3px"
    assert "animation-duration: .01ms !important" in CSS
    assert "transition-duration: .01ms !important" in CSS


@pytest.mark.parametrize("background", ["#0d181c", "#1b2630", "#24313b", "#29263a"])
def test_new_dark_surfaces_have_readable_labels_and_control_boundaries(background):
    tokens = _properties(":root")
    assert _contrast(tokens["--paper-dim"], background) >= 4.5
    assert _contrast(tokens["--muted"], background) >= 4.5
    assert _contrast(tokens["--control-border"], background) >= 3
    assert _contrast(tokens["--palette-cyan"], background) >= 3


def test_phone_actions_stay_in_flow_and_header_does_not_need_sideways_scrolling():
    assert _properties(".director-action", 375)["position"] == "static"
    assert _properties("body:not(.studio-open) .topbar .top-actions", 375)["overflow"] == "visible"
    assert _properties("body:not(.studio-open) .topbar .top-actions .button", 375)["min-height"] == "44px"
