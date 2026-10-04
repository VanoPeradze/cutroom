"""Contracts for the visual refresh; viewport geometry is checked in a browser."""
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def test_ai_dialog_controls_use_theme_surfaces_instead_of_dark_only_colors():
    css = (ROOT / "web/welcome.css").read_text(encoding="utf-8")
    for selector, surface in (
        (".connection-modes label:has(input:checked)", "--surface-selected"),
        (".local-runtime", "--surface-inset"),
        (".local-model-card select", "--surface-raised"),
        (".connection-field input,.connection-field select", "--surface-inset"),
        (".download-confirm", "--surface-selected"),
    ):
        rule = css.split(selector + " {", 1)[1].split("}", 1)[0]
        assert f"background:var({surface})" in rule


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.workflows = []
        self.styles = []
        self.elements = []
        self.stack = []
        self.resources = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs, tuple(self.stack)))
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append((tag, attrs))
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if "data-start-workflow" in attrs:
            self.workflows.append(attrs["data-start-workflow"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.styles.append(attrs["href"])
        for attr in ("src", "poster", "srcset"):
            if attrs.get(attr):
                self.resources.extend(part.split()[0] for part in attrs[attr].split(","))
        if tag == "link" and attrs.get("href"):
            self.resources.append(attrs["href"])
        if tag == "object" and attrs.get("data"):
            self.resources.append(attrs["data"])

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)


def test_project_choices_precede_optional_ai_setup_and_preserve_controls():
    page = Page()
    page.feed((ROOT / "web/index.html").read_text(encoding="utf-8"))
    assert len(page.ids) == len(set(page.ids))
    assert page.workflows == ["short", "youtube", "manual"]
    assert all(tag == "button" and attrs.get("type") == "button" and "disabled" not in attrs
               for tag, attrs, _ in page.elements if "data-start-workflow" in attrs)
    assert page.ids.index("welcomeServices") < page.ids.index("homeSetupTitle")
    for control in ("homeModelsButton", "homeConnectionButton", "homeConnectionStatus",
                    "homeLocalStatus", "newProjectButton", "previewPlay", "playButton",
                    "welcomeView", "workspaceView", "welcomeTourButton", "recentProjects",
                    "recentList", "homePrivacyNote", "sourceInputA", "sourceInputB",
                    "previewA", "previewB", "previewSeek", "previewMode", "timelineCanvas",
                    "studioPreviewDock", "studioTimelineDock"):
        assert control in page.ids


def test_home_guide_uses_native_progressive_disclosure():
    page = Page()
    page.feed((ROOT / "web/index.html").read_text(encoding="utf-8"))
    guides = [(tag, attrs) for tag, attrs, _ in page.elements
              if "home-guide" in attrs.get("class", "").split()]
    assert len(guides) == 1
    tag, guide = guides[0]
    assert tag == "details" and "open" not in guide and "hidden" not in guide
    children = [(tag, attrs) for tag, attrs, parents in page.elements
                if parents and parents[-1][1] is guide]
    assert children[0][0] == "summary"
    assert children[0][1].get("tabindex") != "-1"
    for heading in ("homeWorkflowTitle", "homeProcessingTitle"):
        assert any(attrs.get("id") == heading and any(parent is guide for _, parent in parents)
                   for _, attrs, parents in page.elements)


def test_visual_refresh_has_no_third_party_resource_dependencies():
    page = Page()
    page.feed((ROOT / "web/index.html").read_text(encoding="utf-8"))
    for resource in page.resources:
        assert resource.startswith("/assets/"), resource
        assert (ROOT / "web" / urlsplit(resource).path.removeprefix("/assets/")).is_file()
    css = (ROOT / "web/creator-ui.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    assert not re.search(r"@import\b", css, re.I)
    for resource in re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", css, re.I):
        url = urlsplit(resource)
        assert not url.netloc and url.scheme in ("", "data"), resource


def test_visual_layer_is_shipped_after_existing_geometry_styles():
    page = Page()
    page.feed((ROOT / "web/index.html").read_text(encoding="utf-8"))
    # The shared visual skin follows geometry; the scoped editor panel layer
    # follows that skin so inspector sizing and the separate Master win the cascade.
    # The studio design system and its editor chrome come last.
    style_paths = [urlsplit(href).path for href in page.styles]
    assert style_paths[-4:] == ["/assets/creator-ui.css", "/assets/editor-panels.css",
                                "/assets/studio-design.css", "/assets/studio-chrome.css"]
    assert len(style_paths) == len(set(style_paths))
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


def test_skin_only_changes_appearance_of_playback_and_timeline_surfaces():
    css = (ROOT / "web/creator-ui.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    protected = re.compile(
        r"(?:\b(?:video|canvas)\b|#(?:previewA|previewB|previewStage|previewPaneA|previewPaneB|"
        r"previewColumn|timelineCanvas|timelineScroll|audioMeterCanvas)\b|"
        r"\.(?:preview-stage|preview-pane|preview-column|studio-preview-dock|timeline-scroll)\b)"
    )
    appearance = {"color", "color-scheme", "background", "background-color", "border-color", "box-shadow"}
    for selectors, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if not protected.search(selectors):
            continue
        for declaration in declarations.split(";"):
            if ":" not in declaration:
                continue
            name, value = map(str.strip, declaration.split(":", 1))
            # Media-local custom properties may set colors, never sizing/cropping values.
            assert name in appearance or (name.startswith("--") and value.startswith("#")), (selectors, declaration)


def test_header_and_progress_share_one_stack_and_theme_initializes_before_styles():
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    assert html.index('id="appChrome"') < html.index('class="topbar"') < html.index('id="activeJobBar"') < html.index('<main')
    assert html.index('/assets/ui-shell.js?') < html.index('rel="stylesheet"')
    assert 'id="themeToggle"' in html and 'aria-label="Night mode"' in html
    css = (ROOT / "web/creator-ui.css").read_text(encoding="utf-8")
    assert 'inset-block-start:var(--app-chrome-height)' in css
    assert 'height:calc(100dvh - var(--app-chrome-height))' in css
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    assert 'analysisPanel.offsetTop - 100' not in app
    assert 'panelTop - chromeHeight - 16' in app


def test_layout_keeps_recovery_and_extra_monitors_in_disclosures():
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    assert html.index('id="sourceSetupDisclosure"') < html.index('id="creatorFramePreset"') < html.index('id="sourceIdentityCards"')
    assert '<details class="embedded-camera-editor"' in html
    assert '<details class="framing-source-preview"><summary>Original source preview</summary>' in html
    assert 'Restore 30/70 stack' in html
