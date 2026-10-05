from __future__ import annotations

from cutroom.projects import _summary_workflow, apply_automatic_name, apply_draft_name, name_from_source


def test_recorder_timestamps_become_readable_names():
    assert name_from_source("2026-03-04 19-28-20.mp4") == "Recording Mar 4, 2026 · 19:28"
    assert name_from_source("2026-09-06_23-55-50.mkv") == "Recording Sep 6, 2026 · 23:55"
    assert name_from_source("boss_fight_final.mp4") == "boss fight final"
    assert name_from_source("") == "Untitled project"


def test_automatic_names_never_replace_a_typed_name():
    project = {"name": "New project"}
    apply_automatic_name(project, "Recording Mar 4, 2026 · 19:28")
    assert project == {"name": "Recording Mar 4, 2026 · 19:28", "name_auto": True}
    # A later AI draft refines an automatic name...
    apply_draft_name(project, "The Rogue Virus: From City Hall to Haven")
    assert project["name"] == "The Rogue Virus: From City Hall to Haven"
    # ...but not with a generic placeholder title.
    apply_draft_name(project, "CUTROOM first draft")
    assert project["name"] == "The Rogue Virus: From City Hall to Haven"
    typed = {"name": "My boss fight"}
    apply_draft_name(typed, "Something else")
    assert typed == {"name": "My boss fight"}


def test_home_kind_follows_the_starting_point():
    assert _summary_workflow({"settings": {"workflow": "ai", "goal": "short"}}) == "short"
    assert _summary_workflow({"settings": {"workflow": "ai", "goal": "youtube"}}) == "youtube"
    assert _summary_workflow({"settings": {"workflow": "manual", "goal": "youtube"}}) == "manual"
    assert _summary_workflow({"settings": {}}) is None


def test_renaming_clears_the_automatic_flag(tmp_path, monkeypatch):
    from cutroom.config import load_settings
    from cutroom.projects import ProjectStore

    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    store = ProjectStore(load_settings())
    project = store.create("New project")
    named = store.update(project["id"], lambda item: apply_automatic_name(item, "Recording"))
    assert named["name"] == "Recording" and named["name_auto"] is True
    renamed = store.patch(project["id"], {"name": "Mine"})
    assert renamed["name"] == "Mine" and "name_auto" not in renamed
    apply_draft_name(renamed, "A draft title")
    assert renamed["name"] == "Mine"


def test_display_name_skips_default_titles():
    from cutroom.projects import display_name

    manual = {"name": "New project", "draft": {"title": "New project"},
              "sources": {"A": {"name": "2026-09-06 23-55-50.mp4"}, "B": None}}
    assert display_name(manual) == "Recording Sep 6, 2026 · 23:55"
    ai = {"name": "New project", "draft": {"title": "Clutch defuse"}, "sources": {"A": {"name": "x.mp4"}}}
    assert display_name(ai) == "Clutch defuse"
    assert display_name({"name": "Mine", "draft": {"title": "Other"}}) == "Mine"
    assert display_name({"name": "New project", "sources": {"A": None}}) == "New project"
