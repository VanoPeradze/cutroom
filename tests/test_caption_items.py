from __future__ import annotations

import copy
import shutil
import threading

import pytest

from cutroom import render
from cutroom.caption_items import caption_lines, effective_transcript
from cutroom.captions import build_ass, build_srt
from cutroom.config import load_settings
from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.jobs import Job, JobContext
from cutroom.projects import ProjectStore
from server import create_app
from test_source_tracks_render import clip, media  # noqa: F401  (isolated colour/tone media fixture)


def word(start, end, text):
    return {"start": start, "end": end, "word": text}


def sequence_project():
    """A clip of speech used twice: s1 plays at 0-1 and again at 4-6."""
    return {
        "sources": {slot: {"duration": 4, "width": 160, "height": 100, "has_audio": True} for slot in ("A", "B")},
        "settings": {"fps": 60, "aspect": "source", "resolution": "720", "captions": True, "burn_captions": True,
                     "editorial_effects": False},
        "manual": {
            "sequence": {"version": 1, "duration": 6, "camera_plan": [{"start": 0, "end": 6, "camera": "A"}]},
            "source_mixer": {"first_slot": "A", "audio_slot": "A", "stack_fit": "cover"},
            "source_tracks": {"A": [clip(0, 1, 2, "a"), clip(2, 3, 0, "b"), clip(4, 6, 2, "c")],
                              "B": [clip(0, 1.5, 0, "d")]},
        },
        "draft": {"keep_ranges": [{"start": 1, "end": 2}], "camera_plan": [{"start": 0, "end": 4, "camera": "A"}]},
        "analysis": {"audio_source": "A", "transcript": {"language": "en", "segments": [
            {"id": "s0", "start": 0.1, "end": 0.9, "text": "First words",
             "words": [word(0.1, 0.4, "First"), word(0.5, 0.9, "words")]},
            {"id": "s1", "start": 2.1, "end": 2.9, "text": "Later words",
             "words": [word(2.1, 2.4, "Later"), word(2.5, 2.9, "words")]},
        ]}},
    }


def legacy_project():
    return {
        "sources": {"A": {"duration": 10, "width": 160, "height": 100, "has_audio": True}, "B": None},
        "settings": {"fps": 30, "captions": True, "burn_captions": True},
        "manual": {"cuts": []},
        "draft": {"keep_ranges": [{"start": 0, "end": 2}, {"start": 3, "end": 10}],
                  "camera_plan": [{"start": 0, "end": 10, "camera": "A"}]},
        "analysis": {"audio_source": "A", "transcript": {"language": "en", "segments": [
            {"id": "s0", "start": 1.0, "end": 4.0, "text": "one cut three",
             "words": [word(1.0, 1.5, "one"), word(2.2, 2.8, "cut"), word(3.2, 3.8, "three")]},
        ]}},
    }


def rows(items):
    return [(item["id"], item["start"], item["end"], item["text"]) for item in items]


def test_sequence_items_follow_clips_and_repeat_reused_speech():
    items = render.project_caption_items(sequence_project())
    assert rows(items) == [
        ("s1:w0", 0.1, 0.9, "Later words"),
        ("s0:w0", 2.1, 2.9, "First words"),
        ("s1:w0~1", 4.1, 4.9, "Later words"),
    ]
    assert all(item["direction"] == "ltr" for item in items)
    # The editor shows the same items; only the export snaps cuts to frames.
    assert rows(render.project_caption_items(sequence_project(), aligned=False)) == rows(items)


def test_legacy_items_use_the_export_clock_and_split_at_cuts():
    items = render.project_caption_items(legacy_project())
    # The word inside the removed 2-3 s is not shown; the rest is split at the cut.
    assert rows(items) == [("s0:w0", 1.0, 1.5, "one"), ("s0:w2", 2.2, 2.8, "three")]
    assert rows(render.project_caption_items(legacy_project(), aligned=False)) == rows(items)
    lines = caption_lines(items, 9)
    assert [(line["start"], line["end"], line["text"]) for line in lines] == [(1.0, 1.5, "one"), (2.2, 2.8, "three")]


def test_source_correction_reaches_every_use_and_item_text_only_one():
    value = sequence_project()
    apply_manual_edit(value, {"action": "caption_update", "caption_id": "s1:w0", "text": "Later, friends", "scope": "source"})
    items = {item["id"]: item for item in render.project_caption_items(value)}
    assert items["s1:w0"]["text"] == items["s1:w0~1"]["text"] == "Later, friends"
    assert items["s1:w0"]["corrected"] and items["s1:w0"]["words"][1]["start"] == 0.5  # Same word count keeps timing.
    assert value["analysis"]["transcript"]["segments"][1]["text"] == "Later words"

    apply_manual_edit(value, {"action": "caption_update", "caption_id": "s1:w0~1", "text": "Only here"})
    items = {item["id"]: item for item in render.project_caption_items(value)}
    assert (items["s1:w0"]["text"], items["s1:w0~1"]["text"]) == ("Later, friends", "Only here")
    assert items["s1:w0~1"]["local_text"] and not items["s1:w0"]["local_text"]

    apply_manual_edit(value, {"action": "undo"})
    assert render.project_caption_items(value)[2]["text"] == "Later, friends"
    apply_manual_edit(value, {"action": "undo"})
    assert {item["text"] for item in render.project_caption_items(value)} == {"Later words", "First words"}
    assert "caption_corrections" not in value["manual"] and "caption_overrides" not in value["manual"]
    apply_manual_edit(value, {"action": "redo"})
    apply_manual_edit(value, {"action": "redo"})
    assert [item["text"] for item in render.project_caption_items(value)] == ["Later, friends", "First words", "Only here"]


def test_hidden_items_leave_the_export_and_retiming_moves_with_the_clip():
    value = sequence_project()
    apply_manual_edit(value, {"action": "caption_visibility", "caption_id": "s0:w0", "hidden": True})
    assert [line["text"] for line in caption_lines(render.project_caption_items(value, include_hidden=False), 9)] == [
        "Later words", "Later words"]
    assert render.project_caption_items(value)[1]["hidden"]

    apply_manual_edit(value, {"action": "caption_update", "caption_id": "s1:w0~1", "start": 4.0, "end": 5.2})
    item = render.project_caption_items(value)[2]
    assert (item["start"], item["end"], item["timing_changed"]) == (4.0, 5.2, True)
    line = caption_lines([item], 9)[0]
    assert (line["start"], line["end"]) == (4.0, 5.2)
    # The change is relative to the speech, so moving its clip carries it along.
    value["manual"]["source_tracks"]["A"][2].update({"start": 3.5, "end": 5.5})
    item = render.project_caption_items(value)[2]
    assert (item["start"], item["end"]) == (pytest.approx(3.5), pytest.approx(4.7))

    apply_manual_edit(value, {"action": "caption_reset", "caption_id": "s1:w0~1"})
    item = render.project_caption_items(value)[2]
    assert (item["start"], item["end"], item["timing_changed"]) == (pytest.approx(3.6), pytest.approx(4.4), False)
    assert render.project_caption_items(value)[1]["hidden"]  # Reset is per caption.


def test_stale_source_correction_is_reported_instead_of_landing_on_new_speech():
    value = sequence_project()
    apply_manual_edit(value, {"action": "caption_update", "caption_id": "s0:w0", "text": "Fixed words", "scope": "source"})
    value["analysis"]["transcript"]["segments"][0]["text"] = "Different speech"  # A new transcription.
    transcript, stale = effective_transcript(value)
    assert stale == ["s0"] and transcript["segments"][0]["text"] == "Different speech"
    assert render.project_caption_items(value)[1]["text"] == "Different speech"
    assert not render.project_caption_items(value)[1]["corrected"]


def test_direction_follows_hebrew_text_including_mixed_lines():
    value = sequence_project()
    segments = value["analysis"]["transcript"]["segments"]
    segments[0].update(text="CUTROOM שלום", words=[word(0.1, 0.4, "CUTROOM"), word(0.5, 0.9, "שלום")])
    items = {item["id"]: item for item in render.project_caption_items(value)}
    assert items["s0:w0"]["direction"] == "rtl" and items["s1:w0"]["direction"] == "ltr"
    apply_manual_edit(value, {"action": "caption_update", "caption_id": "s1:w0", "text": "שלום לכום"})
    assert {item["id"]: item for item in render.project_caption_items(value)}["s1:w0"]["direction"] == "rtl"


def test_a_new_word_count_spreads_timing_and_never_colours_estimated_words(tmp_path):
    value = sequence_project()
    apply_manual_edit(value, {"action": "caption_update", "caption_id": "s1:w0", "text": "Later my good friends"})
    item = render.project_caption_items(value)[0]
    assert [entry["word"] for entry in item["words"]] == ["Later", "my", "good", "friends"]
    assert all(entry.get("estimated") for entry in item["words"])
    assert item["words"][0]["start"] == pytest.approx(0.1) and item["words"][-1]["end"] == pytest.approx(0.9)
    assert all(left["end"] == pytest.approx(right["start"]) for left, right in zip(item["words"], item["words"][1:]))
    lines = caption_lines(render.project_caption_items(value), 9, default_style="highlight")
    ass = build_ass({}, [], tmp_path / "estimated.ass", 1080, 1920, caption_style="highlight",
                    caption_lines=lines).read_text(encoding="utf-8-sig")
    estimated = [row for row in ass.splitlines() if row.startswith("Dialogue:") and "friends" in row]
    measured = [row for row in ass.splitlines() if row.startswith("Dialogue:") and "First" in row]
    assert estimated and all("\\c" not in row for row in estimated)
    assert any("\\c" in row for row in measured)


def test_invalid_caption_edits_change_nothing():
    value = sequence_project()
    original = copy.deepcopy(value)
    for payload in (
        {"action": "caption_update", "caption_id": "s1:w0", "text": "   "},
        {"action": "caption_update", "caption_id": "missing:w0", "text": "x"},
        {"action": "caption_update", "caption_id": "s1:w0", "start": 0.8, "end": 0.75},
        {"action": "caption_update", "caption_id": "s1:w0", "start": 5.5, "end": 6.5},
        {"action": "caption_update", "caption_id": "s1:w0", "style": "neon"},
        {"action": "caption_update", "caption_id": "s1:w0", "scale": 300},
        {"action": "caption_update", "caption_id": "s1:w0", "text": "x", "scope": "everywhere"},
        {"action": "caption_visibility", "caption_id": "s1:w0", "hidden": "yes"},
    ):
        with pytest.raises(ManualEditError):
            apply_manual_edit(value, payload)
    assert value == original
    # Re-saving the same text is not an edit and adds no undo step.
    apply_manual_edit(value, {"action": "caption_update", "caption_id": "s1:w0", "text": "Later words"})
    assert value == original


def test_caption_style_overrides_reach_the_burned_captions(tmp_path):
    value = sequence_project()
    apply_manual_edit(value, {"action": "caption_update", "caption_id": "s0:w0", "style": "boxed", "position": "top", "scale": 120})
    item = render.project_caption_items(value)[1]
    assert (item["style"], item["position"], item["scale"]) == ("boxed", "top", 120)
    lines = caption_lines(render.project_caption_items(value), 9, default_style="bold")
    ass = build_ass({}, [], tmp_path / "styled.ass", 1080, 1920, caption_lines=lines).read_text(encoding="utf-8-sig")
    assert "Style: Caption1," in ass
    assert [row.split(",")[3] for row in ass.splitlines() if row.startswith("Dialogue:")] == ["Default", "Caption1", "Default"]
    srt = build_srt({}, [], tmp_path / "styled.srt", caption_lines=caption_lines(render.project_caption_items(value), 9))
    assert srt.read_text(encoding="utf-8").count("Later words") == 2


def test_real_export_uses_the_edited_caption_items(tmp_path, media, monkeypatch):  # noqa: F811
    _, _, paths = media
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    settings.render["prefer_hardware"] = False
    store = ProjectStore(settings)
    saved = store.create("Caption items export")
    value = sequence_project()
    for slot, source in zip(("A", "B"), paths):
        target = store.project_dir(saved["id"]) / "media" / f"{slot}.mp4"
        shutil.copyfile(source, target)
        value["sources"][slot]["relative_path"] = f"media/{slot}.mp4"
    saved.update(value)
    saved["settings"].update({"captions": True, "burn_captions": True, "quality": "fast"})
    apply_manual_edit(saved, {"action": "caption_visibility", "caption_id": "s0:w0", "hidden": True})
    apply_manual_edit(saved, {"action": "caption_update", "caption_id": "s1:w0~1", "text": "Second time", "start": 4.0, "end": 5.5})
    store.save(saved)
    context = JobContext(Job("caption-items-export", "render", saved["id"]), threading.Lock())
    record = render.render_project(context, saved["id"], store, settings, {"quality": "fast"})["export"]
    srt = (settings.exports_dir / record["captions_name"]).read_text(encoding="utf-8")
    assert "00:00:00,100 --> 00:00:00,900\nLater words" in srt
    assert "00:00:04,000 --> 00:00:05,500\nSecond time" in srt
    assert "First" not in srt
    reopened = store.load(saved["id"])
    assert reopened["manual"]["caption_overrides"]["s0:w0"] == {"hidden": True}
    assert render._render_input_fingerprint(reopened) == record["input_fingerprint"]


def test_caption_api_payload_revision_and_reopen(monkeypatch, tmp_path):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    settings.raw["ai"]["enabled"] = False
    app = create_app(settings)
    app.config.update(TESTING=True)
    store = app.extensions["cutroom_store"]
    value = store.create("caption-api")
    value.update(sequence_project())
    value = store.save(value)
    client = app.test_client()
    public = client.get(f"/api/projects/{value['id']}").get_json()
    public = public.get("project", public)
    assert [item["id"] for item in public["editor_captions"]] == ["s1:w0", "s0:w0", "s1:w0~1"]
    assert public["editor_captions"][0]["words"][0] == [0.1, 0.4, "Later"]
    assert (public["editor_captions"][0]["start"], public["editor_captions"][0]["end"]) == (0.1, 0.9)
    endpoint = f"/api/projects/{value['id']}/manual/edit"
    edit = {"action": "caption_update", "caption_id": "s1:w0", "text": "Later, friends", "scope": "source"}
    assert client.post(endpoint, json=edit).status_code == 400  # The displayed revision is required.
    assert client.post(endpoint, json={**edit, "colour": "red", "expected_revision": value["revision"]}).status_code == 400
    response = client.post(endpoint, json={**edit, "expected_revision": value["revision"]})
    assert response.status_code == 200
    result = response.get_json()["project"]
    assert [item["text"] for item in result["editor_captions"]] == ["Later, friends", "First words", "Later, friends"]
    assert result["analysis"]["transcript"]["segments"][1]["text"] == "Later, friends"
    assert client.post(endpoint, json={**edit, "expected_revision": value["revision"]}).status_code == 409
    reopened = store.load(value["id"])
    assert reopened["manual"]["caption_corrections"] == {"s1": {"original": "Later words", "text": "Later, friends"}}
    assert reopened["analysis"]["transcript"]["segments"][1]["text"] == "Later words"


def test_splitting_a_clip_keeps_caption_identity_and_overrides():
    value = sequence_project()
    apply_manual_edit(value, {"action": "caption_update", "caption_id": "s1:w0~1", "text": "Second time"})
    before = rows(render.project_caption_items(value))
    apply_manual_edit(value, {"action": "sequence_split", "slot": "A", "time": 0.5})
    apply_manual_edit(value, {"action": "sequence_layout", "start": 4.5, "end": 6, "layout": "B"})
    assert len(value["manual"]["source_tracks"]["A"]) == 4  # The split is real...
    assert rows(render.project_caption_items(value)) == before  # ...but captions are unchanged.
    # Moving the second half away is a real discontinuity: that speech becomes two
    # captions, and the edit made on the later use stays on it.
    apply_manual_edit(value, {"action": "sequence_move_range", "start": 0.5, "end": 1, "to": 1.5, "slot": "A", "mode": "overwrite"})
    assert rows(render.project_caption_items(value)) == [
        ("s1:w0", 0.1, 0.4, "Later"),
        ("s1:w1", 1.5, 1.9, "words"),
        ("s0:w0", 2.1, 2.9, "First words"),
        ("s1:w0~1", 4.1, 4.9, "Second time"),
    ]


def test_reordering_repeated_speech_keeps_each_caption_edit_on_its_clip():
    value = sequence_project()
    apply_manual_edit(value, {"action": "caption_update", "caption_id": "s1:w0~1", "text": "Second time",
                              "style": "boxed", "position": "top"})
    apply_manual_edit(value, {"action": "caption_visibility", "caption_id": "s1:w0", "hidden": True})
    apply_manual_edit(value, {"action": "sequence_move_range", "start": 4, "end": 6, "to": 0, "mode": "insert"})
    items = render.project_caption_items(value)
    assert items[0]["text"] == "Second time"
    assert (items[0]["style"], items[0]["position"], items[0]["hidden"]) == ("boxed", "top", False)
    assert items[1]["source_text"] == "Later words" and items[1]["hidden"]
    apply_manual_edit(value, {"action": "undo"})
    assert render.project_caption_items(value)[2]["text"] == "Second time"
    apply_manual_edit(value, {"action": "redo"})
    assert render.project_caption_items(value)[0]["text"] == "Second time"


def test_trimming_first_spoken_word_preserves_the_caption_edit():
    value = sequence_project()
    apply_manual_edit(value, {"action": "caption_update", "caption_id": "s1:w0~1", "text": "Second time",
                              "style": "boxed"})
    apply_manual_edit(value, {"action": "sequence_trim", "slot": "A", "clip_id": "c", "start": 4.5,
                              "end": 6, "source_start": 2.5})
    item = render.project_caption_items(value)[2]
    assert item["text"] == "Second time" and item["style"] == "boxed"
    assert item["start"] == 4.5
    assert render.project_caption_items(value)[0]["text"] == "Later words"
    apply_manual_edit(value, {"action": "undo"})
    assert render.project_caption_items(value)[2]["text"] == "Second time"
    apply_manual_edit(value, {"action": "redo"})
    assert render.project_caption_items(value)[2]["text"] == "Second time"


def test_long_captions_split_into_readable_parts_with_or_without_word_timing():
    from cutroom.caption_items import MAX_CAPTION_CHARACTERS
    long_text = " ".join(f"word{index:02d}" for index in range(30))  # 209 characters
    wordless = [{"id": "s0:t0.0", "start": 0.0, "end": 9.0, "text": long_text, "words": [], "hidden": False}]
    lines = caption_lines(wordless, 12)
    assert [len(line["text"]) <= MAX_CAPTION_CHARACTERS for line in lines] == [True] * len(lines) and len(lines) == 3
    assert " ".join(line["text"] for line in lines) == long_text
    assert lines[0]["start"] == 0.0 and lines[-1]["end"] == 9.0 and all(line["estimated"] for line in lines)
    assert all(left["end"] == pytest.approx(right["start"]) for left, right in zip(lines, lines[1:]))
    timed = [{"id": "s1:w0", "start": 0.0, "end": 12.0, "text": long_text, "hidden": False,
              "words": [{"start": index * 0.4, "end": index * 0.4 + 0.3, "word": f"word{index:02d}"} for index in range(30)]}]
    lines = caption_lines(timed, 12)
    assert all(len(line["text"]) <= MAX_CAPTION_CHARACTERS for line in lines) and len(lines) == 3
    assert caption_lines([{**wordless[0], "text": "Short line"}], 9)[0]["text"] == "Short line"
