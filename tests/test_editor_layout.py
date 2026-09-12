"""Static contracts for the editor shell; visual sizing is checked in the browser."""

from html.parser import HTMLParser
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]
CSS = re.sub(r"/\*.*?\*/", "", (ROOT / "web/styles.css").read_text(encoding="utf-8"), flags=re.S)
HTML = (ROOT / "web/index.html").read_text(encoding="utf-8")


def _rules(source, media=()):
    """Read declaration blocks, preserving media scope and stylesheet order."""
    cursor = 0
    while (opening := source.find("{", cursor)) != -1:
        selector = source[cursor:opening].strip()
        depth, closing = 1, opening + 1
        while depth:
            depth += (source[closing] == "{") - (source[closing] == "}")
            closing += 1
        body = source[opening + 1:closing - 1]
        if selector.startswith("@media"):
            yield from _rules(body, (*media, selector))
        elif not selector.startswith("@"):
            yield selector, body, media
        cursor = closing


def _media_matches(query, width, height):
    """Match pixel min/max dimensions; comma alternatives are OR, features are AND.

    Non-dimension features are deliberately outside this static helper's scope.
    This is not a media-query engine or a substitute for browser layout checks.
    """
    dimensions = {"width": width, "height": height}
    alternatives = re.split(r",(?![^()]*\))", query.removeprefix("@media").strip())
    return any(
        all(
            dimensions[axis] <= float(limit) if kind == "max" else dimensions[axis] >= float(limit)
            for kind, axis, limit in re.findall(
                r"\(\s*(min|max)-(width|height)\s*:\s*(\d+(?:\.\d+)?)px\s*\)", alternative
            )
        )
        for alternative in alternatives
    )


def _properties(selector, width=1440, height=900):
    """Collect declarations for one exact selector at matching viewport breakpoints.

    Other matching selectors, specificity, inheritance and container queries are
    not resolved: these assertions verify explicit contracts, not computed CSS.
    """
    result = {}
    for selectors, body, media in _rules(CSS):
        if selector not in [part.strip() for part in re.split(r",(?![^()]*\))", selectors)]:
            continue
        if not all(_media_matches(query, width, height) for query in media):
            continue
        for declaration in body.split(";"):
            if ":" in declaration:
                key, value = declaration.split(":", 1)
                key = key.strip()
                result[key] = re.sub(r"\s+", "", value)
                if key == "overflow":
                    axes = value.split()
                    result["overflow-x"] = axes[0]
                    result["overflow-y"] = axes[-1]
    return result


@pytest.mark.parametrize(
    ("query", "width", "height", "expected"),
    [
        ("@media (max-width: 960px), (max-height: 680px)", 800, 900, True),
        ("@media (max-width: 960px), (max-height: 680px)", 1440, 600, True),
        ("@media (max-width: 960px), (max-height: 680px)", 1440, 900, False),
        ("@media (max-width: 960px), (max-height: 680px)", 960, 900, True),
        ("@media (max-width: 960px), (max-height: 680px)", 1440, 680, True),
        ("@media (min-width: 961px) and (min-height: 681px)", 1024, 900, True),
        ("@media (min-width: 961px) and (min-height: 681px)", 1024, 600, False),
        ("@media (min-height: 681px) and (max-height: 900px)", 1440, 900, True),
        ("@media (min-height: 681px) and (max-height: 900px)", 1440, 901, False),
    ],
)
def test_viewport_media_dimensions_preserve_and_or_semantics(query, width, height, expected):
    assert _media_matches(query, width, height) is expected


def test_nested_media_queries_require_every_enclosing_scope(monkeypatch):
    monkeypatch.setitem(globals(), "CSS", """
        .probe { display: block; }
        @media (min-width: 1000px) {
            @media (max-height: 680px), (min-width: 1500px) {
                .probe { display: flex; }
            }
        }
    """)
    assert _properties(".probe", 1440, 600)["display"] == "flex"
    assert _properties(".probe", 1600, 900)["display"] == "flex"
    assert _properties(".probe", 800, 600)["display"] == "block"
    assert _properties(".probe", 1440, 900)["display"] == "block"


class _Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.nodes = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        node = {"tag": tag, "attrs": attributes, "ancestors": tuple(self.stack)}
        if attributes.get("id"):
            assert attributes["id"] not in self.nodes, "Duplicate editor control id"
            self.nodes[attributes["id"]] = node
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append((tag, attributes.get("id")))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


def test_preview_and_timeline_are_persistent_siblings_outside_tab_panels():
    markup = _Markup()
    markup.feed(HTML)
    for dock in ("studioPreviewDock", "studioTimelineDock"):
        ancestors = markup.nodes[dock]["ancestors"]
        assert ancestors[-1][1] == "advancedPanel"
        assert not any(node_id and node_id.startswith("studioPanel") for _, node_id in ancestors)
    assert markup.nodes["timelineCanvas"]["ancestors"][-1][1] == "timelineScroll"
    for tab in ("Timeline", "Framing", "Transcript", "Settings"):
        assert markup.nodes[f"studioTab{tab}"]["attrs"]["aria-controls"] == f"studioPanel{tab}"


@pytest.mark.parametrize("width", [1024, 1440])
def test_desktop_inspector_uses_full_height_and_does_not_share_timeline_columns(width):
    inspector = _properties(".advanced-panel.studio-workspace .advanced-content", width)
    timeline = _properties(".studio-workspace .studio-timeline-dock", width)
    assert inspector["grid-column"] == "2"
    assert inspector["grid-row"] == "2/4"
    assert timeline["grid-column"] == "3"
    assert timeline["grid-row"] == "3"
    director = _properties("#studioDirectorDock .verdict-column", width)
    assert director["grid-template-columns"] in {"1fr", "minmax(0,1fr)"}


def test_studio_topbar_resets_the_dashboard_second_row():
    topbar = _properties("body.studio-open .topbar", 1024)
    project = _properties("body.studio-open .project-head", 1024)
    assert topbar["height"] == "64px"
    assert project["grid-row"] == "1"
    assert project["grid-column"] == "2"


def test_embedded_camera_controls_fit_the_narrow_inspector():
    for selector in (".studio-workspace .embedded-camera-sliders label", ".studio-workspace .embedded-content-focus label"):
        tracks = _properties(selector, 1024)["grid-template-columns"]
        assert "minmax(0,1fr)" in tracks
        assert "minmax(100px" not in tracks
    actions = _properties(".studio-workspace .embedded-camera-actions", 1024)
    assert actions["grid-template-columns"] in {"1fr", "minmax(0,1fr)"}


@pytest.mark.parametrize("width", [390, 768, 1024, 1440])
def test_source_layout_preview_has_a_ratio_preserving_canvas_without_a_forced_minimum_height(width):
    canvas = _properties(".source-composition-canvas", width)
    assert canvas["min-width"] == canvas["min-height"] == "0"
    assert canvas["aspect-ratio"] == "16/9"  # Replaced with the selected output ratio by the UI.
    assert canvas["width"] == "min(100%,calc(360px*var(--composition-ratio)))"
    assert canvas["justify-self"] == "center"
    video = _properties(".source-composition-slot video", width)
    assert video["position"] == "absolute", "Native video dimensions must not stretch the auto layout's grid rows"
    assert video["object-fit"] == "contain"
    assert _properties('.source-composition-canvas.composition-stacked[data-stack-fit="cover"] video', width)["object-fit"] == "cover"


def test_source_layout_badge_does_not_overlay_the_top_camera():
    markup = _Markup()
    markup.feed(HTML)
    ancestors = markup.nodes["sourceCompositionMode"]["ancestors"]
    assert ancestors[-1][1] == "sourceCompositionPreview"
    assert not any(node_id == "sourceCompositionCanvas" for _, node_id in ancestors)
    badge = _properties(".source-composition-mode")
    assert badge["grid-column"] == "1/-1"
    assert badge.get("position") != "absolute"


def test_picture_in_picture_previews_share_export_geometry_without_an_unexported_border():
    monitor = _properties(".preview-stage.layout-pip.pip-inset-b #previewPaneB")
    miniature = _properties(".source-composition-canvas.composition-pip.primary-slot-b .slot-a")
    for key in ("width", "height", "inset"):
        assert monitor[key] == miniature[key]
    assert monitor["width"] == "var(--pip-width,34%)"
    assert monitor["height"] == "var(--pip-height,28%)"
    assert monitor["border"] == miniature["border"] == "0"


@pytest.mark.parametrize("width", [1024, 1366])
def test_output_settings_do_not_inherit_wide_dashboard_grids(width):
    for selector in (
        ".studio-workspace .intent-tuning",
        ".studio-workspace .audio-preset-group",
        ".studio-workspace .audio-control-grid",
    ):
        assert _properties(selector, width)["grid-template-columns"] == "minmax(0,1fr)"
    preset_fields = _properties(".studio-workspace .audio-preset-group > *", width)
    assert preset_fields["grid-column"] == "1"
    assert preset_fields["min-width"] == "0"


@pytest.mark.parametrize(("width", "height"), [(390, 900), (800, 900), (1440, 600)])
def test_stacked_workspaces_flow_while_long_transcripts_have_bounded_scrolling(width, height):
    shell = _properties(".advanced-panel.studio-workspace:not([hidden])", width, height)
    inspector = _properties(".advanced-panel.studio-workspace .advanced-content", width, height)
    timeline = _properties(".studio-workspace .studio-timeline-dock", width, height)
    assert shell["grid-template-columns"] == "56pxminmax(0,1fr)"
    # `auto auto` can squeeze these tracks into the fixed-height viewport even
    # when overflowing controls need more room. Each following panel must start
    # after the previous panel's complete content, including wrapped trim tools.
    assert shell["grid-template-rows"].endswith("max-contentmax-content")
    assert shell.get("overflow-y", shell.get("overflow")) == "auto"
    assert inspector.get("overflow-y", inspector.get("overflow")) == "visible"
    assert inspector["grid-column"] == timeline["grid-column"] == "2"
    assert inspector["grid-row"] == "4"
    assert timeline["grid-row"] == "3"
    assert timeline["min-height"] == "min-content"
    assert timeline["overflow-y"] == "visible"

    transcript = _properties(".advanced-panel.studio-workspace .transcript-list", width, height)
    assert transcript["min-height"] == "160px"
    assert transcript["max-height"] == "360px"
    assert transcript["overflow-y"] == "auto"
    scenes = _properties(".studio-workspace .scene-layout-list", width, height)
    assert scenes["max-height"] == "none"
    assert scenes["overflow-y"] == "visible"
    settings = _properties(".studio-transcript .caption-settings-disclosure[open]", width, height)
    assert settings["max-height"] == "none"
    assert settings["overflow-y"] == "visible"


def test_mobile_transcript_override_also_preserves_bounded_scrolling():
    # This distinct selector has !important overrides. Check it explicitly;
    # _properties does not merge it with the more-specific desktop selector.
    transcript = _properties(".studio-workspace .transcript-list", 390)
    assert transcript["max-height"] == "45vh!important"
    assert transcript["min-height"] == "160px!important"
    assert transcript["overflow-y"] == "auto!important"


@pytest.mark.parametrize("width", [1024, 1440])
def test_desktop_transcript_controls_cannot_be_shrunk_into_a_clipped_card(width):
    card = _properties(".studio-transcript .transcript-editor-card", width)
    assert card["min-height"] == "min-content"
    assert card["flex"] == "10auto"
    assert card["overflow-y"] == "visible"
    transcript = _properties(".advanced-panel.studio-transcript .transcript-list", width)
    assert transcript["max-height"] == "320px"
    assert transcript["overflow-y"] == "auto"
    editor = _properties(".studio-transcript .transcript-detail-editor", width)
    assert editor["flex-shrink"] == "0"
    settings = _properties(".studio-transcript .caption-settings-disclosure[open]", width)
    assert settings["max-height"] == "none"
    assert settings["overflow-y"] == "visible"


@pytest.mark.parametrize("width", [390, 480, 800, 1024, 1440])
def test_transcript_search_and_filter_have_explicit_nonoverlapping_tracks(width):
    toolbar = _properties(".studio-workspace .transcript-toolbar", width)
    assert toolbar["display"] == "grid"
    expected = "minmax(0,1fr)" if width <= 480 else "minmax(0,1fr)minmax(110px,160px)"
    assert toolbar["grid-template-columns"] == expected
    assert toolbar["flex"] == "00auto"
    for control in ("input", "select"):
        sizing = _properties(f".studio-workspace .transcript-toolbar {control}", width)
        assert sizing["min-width"] == "0"
        assert sizing["width"] == "100%"


@pytest.mark.parametrize(("width", "height"), [(390, 900), (800, 900), (1024, 900), (1440, 900), (1440, 600)])
def test_timeline_dock_grows_controls_without_implicit_grid_rows_or_clipping(width, height):
    dock = _properties(".studio-workspace .studio-timeline-dock", width, height)
    assert dock["display"] == "flex"
    assert dock["flex-direction"] == "column"
    assert dock["overflow-y"] in {"auto", "visible"}
    controls = _properties(".studio-timeline-dock > :not(.timeline-scroll)", width, height)
    assert controls["flex"] == "00auto"
    assert controls["min-width"] == "0"
    scroll = _properties(".advanced-panel.studio-workspace .studio-timeline-dock .timeline-scroll", width, height)
    assert scroll["flex"] == "10192px"
    assert scroll["min-height"] == "192px"
    corrections = _properties(".studio-timeline-dock .manual-correction-bar", width, height)
    assert corrections["flex-wrap"] == "wrap"


def test_timeline_scrolls_horizontally_without_a_nested_vertical_scroller():
    selector = ".advanced-panel.studio-workspace .studio-timeline-dock .timeline-scroll"
    timeline = _properties(selector)
    assert timeline["overflow-x"] == "auto"
    assert timeline["overflow-y"] == "hidden"
    assert _properties(f"{selector} canvas")["height"] == "180px"
