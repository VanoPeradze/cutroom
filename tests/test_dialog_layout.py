"""CSS/markup regression contracts; actual clipping is also checked in-browser."""

import pytest

from test_editor_layout import HTML, _Markup, _properties


@pytest.mark.parametrize("width", [320, 390, 1024, 1440])
def test_dialogs_have_one_viewport_bounded_scroller(width):
    for selector in ("dialog.sheet-dialog", "dialog.export-dialog"):
        dialog = _properties(selector, width)
        assert dialog["max-width"] == "calc(100vw-24px)"
        assert "100dvh-24px" in dialog["max-height"]
        assert dialog["overflow-y"] == "auto"
        shell = _properties(f"{selector} .dialog-shell", width)
        assert shell["max-height"] == "none"
        assert shell["overflow-y"] == "visible"
    projects = _properties("dialog.sheet-dialog .dialog-projects", width)
    assert projects["max-height"] == "none"
    assert projects["overflow-y"] == "visible"


def test_long_project_names_and_shortcut_keys_can_shrink_and_wrap():
    row = _properties(".dialog-project-row .dialog-project")
    assert row["grid-template-columns"] == "minmax(0,1fr)auto"
    assert _properties(".dialog-project > span")["min-width"] == "0"
    assert _properties(".dialog-project strong")["overflow-wrap"] == "anywhere"
    keys = _properties("dialog.keyboard-dialog .shortcut-row kbd")
    assert keys["white-space"] == "normal"
    assert keys["overflow-wrap"] == "anywhere"


def test_dialog_headers_keep_the_close_button_separate_from_wrapping_title():
    heading = _properties("dialog.sheet-dialog .dialog-shell > header > div")
    close = _properties("dialog.sheet-dialog .dialog-shell > header > .icon-button")
    assert heading["min-width"] == "0"
    assert close["flex"] == "0038px"
    markup = _Markup()
    markup.feed(HTML)
    for node_id in ("projectsDialog", "keyboardDialog", "exportDialog"):
        assert markup.nodes[node_id]["tag"] == "dialog"
    assert ("dialog", "exportDialog") in markup.nodes["closeExportDialog"]["ancestors"]


def test_dashboard_header_does_not_inherit_legacy_second_row():
    project = _properties("body:not(.studio-open) .project-head", 1024)
    assert project["grid-column"] == "auto"
    assert project["order"] == "0"
    assert _properties(".active-job-bar", 390)["inset-block-start"] == "64px"
    assert _properties("body:not(.studio-open) .topbar", 390)["min-height"] == "64px"
    assert _properties(".topbar .top-actions", 1024)["overflow-x"] == "auto"


def test_small_export_actions_and_toasts_stay_within_the_viewport():
    assert _properties(".export-actions", 390)["grid-template-columns"] == "minmax(0,1fr)"
    toast = _properties(".toast", 320)
    assert toast["min-width"] == "0"
    assert toast["max-width"] == "100%"
    assert toast["overflow-wrap"] == "anywhere"
    assert "100vw-24px" in _properties(".toast-region", 320)["width"]
