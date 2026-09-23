"""Contracts for the visual refresh; viewport geometry is checked in a browser."""
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.workflows = []
        self.styles = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if "data-start-workflow" in attrs:
            self.workflows.append(attrs["data-start-workflow"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.styles.append(attrs["href"])


def test_project_choices_precede_optional_ai_setup_and_preserve_controls():
    page = Page()
    page.feed((ROOT / "web/index.html").read_text(encoding="utf-8"))
    assert len(page.ids) == len(set(page.ids))
    assert page.workflows == ["short", "youtube", "manual"]
    assert page.ids.index("welcomeServices") < page.ids.index("homeSetupTitle")
    for control in ("homeModelsButton", "homeConnectionButton", "homeConnectionStatus",
                    "homeLocalStatus", "newProjectButton", "previewPlay", "playButton"):
        assert control in page.ids


def test_visual_layer_is_shipped_after_existing_geometry_styles():
    page = Page()
    page.feed((ROOT / "web/index.html").read_text(encoding="utf-8"))
    assert page.styles[-1].startswith("/assets/creator-ui.css?")
    for href in page.styles:
        assert href.startswith("/assets/")
        assert (ROOT / "web" / href.split("/")[-1].split("?")[0]).is_file()


def test_visual_layer_has_mobile_and_motion_rules_without_media_geometry():
    css = (ROOT / "web/creator-ui.css").read_text(encoding="utf-8")
    assert "max-width:800px" in css and "max-width:440px" in css
    assert "prefers-reduced-motion:reduce" in css
    assert ".home-hub :focus-visible" in css
    for media_geometry in ("object-fit", "aspect-ratio", "--workspace-timeline-height", "#timelineCanvas"):
        assert media_geometry not in css
