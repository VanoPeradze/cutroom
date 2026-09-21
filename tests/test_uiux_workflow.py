"""Semantic structure contracts, complemented by real browser QA."""
from html.parser import HTMLParser
from pathlib import Path


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def page():
    result = Page()
    result.feed((Path(__file__).parents[1] / "web/index.html").read_text(encoding="utf-8"))
    return result.elements


def test_setup_follows_the_editing_decision_order():
    ids = [attrs["id"] for _, attrs in page() if "id" in attrs]
    assert ids.index("goalChoices") < ids.index("editStyleChoices") < ids.index("audioCalibration") < ids.index("generateButton")
    assert len(ids) == len(set(ids))


def test_optional_audio_is_a_closed_native_disclosure():
    tag, attrs = next((tag, attrs) for tag, attrs in page() if attrs.get("id") == "audioCalibration")
    assert tag == "details"
    assert "open" not in attrs


def test_advanced_layout_and_precision_controls_are_collapsed_by_default():
    elements = page()
    for control_id in ("moreSourceLayouts", "preciseEmbeddedPosition"):
        tag, attrs = next((tag, attrs) for tag, attrs in elements if attrs.get("id") == control_id)
        assert tag == "details"
        assert "open" not in attrs
    html = (Path(__file__).parents[1] / "web/index.html").read_text(encoding="utf-8")
    assert "Save and use layout" not in html
    assert "changes save automatically" in html.lower()


def test_fps_controls_have_separate_label_and_description():
    elements = page()
    ids = {attrs.get("id") for _, attrs in elements}
    for name in ("fpsSelect", "exportFpsSelect"):
        tag, attrs = next((tag, attrs) for tag, attrs in elements if attrs.get("id") == name)
        assert tag == "select"
        assert attrs["aria-labelledby"] in ids
        assert attrs["aria-describedby"] in ids
        assert attrs["aria-labelledby"] != attrs["aria-describedby"]


def test_new_vector_icons_are_decorative_and_never_keyboard_targets():
    icons = [attrs for tag, attrs in page() if tag == "svg" and attrs.get("class") == "ui-icon"]
    assert len(icons) >= 6
    assert all(attrs.get("aria-hidden") == "true" and attrs.get("focusable") == "false" for attrs in icons)
