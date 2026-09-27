from __future__ import annotations

import copy
import shutil
import subprocess
import threading

import pytest

from cutroom.captions import build_ass, build_srt
from cutroom.config import DEFAULTS, Settings, load_settings
from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.jobs import Job, JobContext
from cutroom.projects import ProjectStore
from cutroom.render import _estimate_render_storage, _render_input_fingerprint, render_project
from cutroom.text_clips import MAX_CAPTION_IMPORT_BYTES, TextClipError, parse_caption_file
from server import _public_project, _reset_manual_after_source_change, create_app


def project():
    return {
        "id": "project_012345abcdef", "sources": {"A": {"duration": 20, "width": 640, "height": 360, "has_audio": False}, "B": None},
        "settings": {"captions": False, "burn_captions": False, "fps": 30, "editorial_effects": False},
        "manual": {}, "draft": {"keep_ranges": [{"start": 0, "end": 10}, {"start": 15, "end": 20}], "cuts": [{"start": 10, "end": 15}], "output_duration": 15,
                                  "camera_plan": [{"start": 0, "end": 10, "camera": "A"}, {"start": 15, "end": 20, "camera": "A"}]},
    }


def add(value, **fields):
    apply_manual_edit(value, {"action": "text_add", "kind": "title", "start": 1, "end": 3, "text": "שלום Hello", **fields})
    return value["manual"]["text_clips"][-1]


def test_edit_clock_title_caption_split_and_history_without_ai():
    value = project()
    value["manual"]["track_locks"] = {"A": True}
    title = copy.deepcopy(add(value, start=11, end=14))
    assert title["position"] == "center" and title["style"] == "bold"
    caption = copy.deepcopy(add(value, kind="caption", start=2, end=4))
    assert caption["position"] == "bottom" and caption["style"] == "clean"
    apply_manual_edit(value, {"action": "text_split", "clip_id": caption["id"], "time": 3})
    assert [(row["start"], row["end"]) for row in value["manual"]["text_clips"]] == [(11, 14), (2, 3), (3, 4)]
    apply_manual_edit(value, {"action": "undo"})
    assert value["manual"]["text_clips"] == [title, caption]
    apply_manual_edit(value, {"action": "redo"})
    assert value["manual"]["text_clips"][2]["text"] == caption["text"]
    assert not value.get("analysis")
    assert value["manual"]["track_locks"] == {"A": True}


@pytest.mark.parametrize("fields", [{"start": True}, {"start": "1"}, {"end": float("inf")}, {"end": 16}, {"end": 1.079}, {"text": " "}, {"text": "x" * 1001}, {"text": "bad\x00"}, {"kind": []}, {"position": "auto"}, {"style": "{\\an1}"}, {"scale": True}, {"scale": 151}, {"scale": 99.5}, {"path": "private"}])
def test_bad_additions_are_atomic(fields):
    value = project()
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        add(value, **fields)
    assert value == before


def test_update_remove_noop_preserves_redo():
    value = project()
    title = copy.deepcopy(add(value))
    apply_manual_edit(value, {"action": "text_update", "clip_id": title["id"], "text": "Changed", "scale": 125, "position": "top", "style": "boxed"})
    apply_manual_edit(value, {"action": "undo"})
    before = copy.deepcopy(value)
    apply_manual_edit(value, {"action": "text_update", "clip_id": title["id"], "text": title["text"]})
    assert value == before
    apply_manual_edit(value, {"action": "redo"})
    apply_manual_edit(value, {"action": "text_remove", "clip_id": title["id"]})
    assert value["manual"]["text_clips"] == []
    apply_manual_edit(value, {"action": "undo"})
    assert value["manual"]["text_clips"][0]["text"] == "Changed"


@pytest.mark.parametrize("action,payload", [("delete_range", {"start": 0, "end": 5}), ("sequence_ripple_delete", {"start": 0, "end": 5})])
def test_shortening_cannot_strand_text(action, payload):
    value = project()
    add(value, start=12, end=15)
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="Trim, move, or remove"):
        apply_manual_edit(value, {"action": action, **payload})
    assert value == before


SRT = "\ufeff1\r\n00:00:01,000 --> 00:00:02,500\r\nשלום <i>Hello</i> &amp; hi\r\nSecond line\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\nNext\r\n"
VTT = "WEBVTT\n\nNOTE local captions\nmetadata\n\nSTYLE\n::cue { color: red }\n\nintro\n00:01.000 --> 00:02.500 align:start position:10%\n<v Narrator>שלום &amp; Hello</v>\n\n00:00:03.000 --> 00:00:04.000\nNext"


@pytest.mark.parametrize("format,content", [("srt", SRT), ("vtt", VTT)])
def test_import_is_one_history_step_and_only_replaces_custom_captions(format, content):
    value = project()
    title = copy.deepcopy(add(value))
    add(value, kind="caption", text="old")
    value["analysis"] = {"transcript": {"segments": [{"text": "AI", "start": 0, "end": 1}]}}
    before = copy.deepcopy(value)
    apply_manual_edit(value, {"action": "text_import", "format": format, "content": content, "replace": True})
    imported = copy.deepcopy(value["manual"]["text_clips"])
    assert len(imported) == 3 and imported[0] == title
    assert imported[1]["start"] == 1 and imported[1]["end"] == 2.5
    assert "שלום" in imported[1]["text"] and "&" in imported[1]["text"] and "<" not in imported[1]["text"]
    assert value["analysis"] == before["analysis"]
    assert value["manual"]["history"]["undo_count"] == before["manual"]["history"]["undo_count"] + 1
    apply_manual_edit(value, {"action": "undo"})
    assert value["manual"]["text_clips"] == before["manual"]["text_clips"]
    apply_manual_edit(value, {"action": "redo"})
    assert value["manual"]["text_clips"] == imported


@pytest.mark.parametrize("format,content", [("srt", "garbage"), ("srt", ""), ("vtt", "WEBVTT\n\nNOTE no cues"), ("vtt", "00:01.000 --> 00:02.000\nHello"), ("srt", SRT + "\nBAD CUE"), ("srt", "1\n00:00:01,000 --> 00:00:20,000\nOutside"), ("srt", "1\n00:00:01,000 --> 00:00:02,000\n"), ("srt", "1\n00:99:01,000 --> 00:99:02,000\nBad"), ("srt", "x" * (MAX_CAPTION_IMPORT_BYTES + 1)), ("srt", "1\n00:00:01,000 --> 00:00:02,000\n" + "a" * 1001), ("srt", "\ud800")], ids=["garbage", "empty", "no-cues", "header", "bad-trailing", "bounds", "blank", "clock", "oversize", "long-cue", "unicode"])
def test_import_failure_preserves_everything(format, content):
    value = project()
    add(value)
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, {"action": "text_import", "format": format, "content": content, "replace": True})
    assert value == before


def test_import_and_overlap_limits():
    content = "\n\n".join(f"{index}\n00:00:01,000 --> 00:00:02,000\nCaption" for index in range(2001))
    with pytest.raises(TextClipError, match="2000"):
        parse_caption_file(content, "srt", 3)
    value = project()
    for _ in range(16):
        add(value)
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="same time"):
        add(value)
    assert value == before
    add(value, start=3, end=5)  # End-before-start ties are not simultaneous.


def test_import_preserves_literal_angle_brackets_and_accepts_2000_sequential_cues():
    text = parse_caption_file("1\n00:00:01,000 --> 00:00:02,000\n1 < 3 > 2", "srt", 3)[0]["text"]
    assert text == "1 < 3 > 2"
    value = project()
    value["sources"]["A"]["duration"] = 2000
    value["draft"].update(keep_ranges=[{"start": 0, "end": 2000}], camera_plan=[{"start": 0, "end": 2000, "camera": "A"}], cuts=[])
    content = "WEBVTT\n\n" + "\n\n".join(f"{i // 60:02}:{i % 60:02}.000 --> {(i + 1) // 60:02}:{(i + 1) % 60:02}.000\nCue {i}" for i in range(2000))
    apply_manual_edit(value, {"action": "text_import", "format": "vtt", "content": content})
    assert len(value["manual"]["text_clips"]) == 2000


def test_public_contract_b_source_preservation_and_fingerprint():
    value = project()
    fingerprint = _render_input_fingerprint(value)
    clip = copy.deepcopy(add(value))
    assert _render_input_fingerprint(value) != fingerprint
    _reset_manual_after_source_change(value, "B", replacing=True)
    assert value["manual"]["text_clips"] == [clip]
    value["manual"]["text_clips"][0]["private_path"] = "C:/private"
    public = _public_project(value)
    assert public["manual"]["text_clips"] == [clip]
    assert "private_path" in value["manual"]["text_clips"][0]


def test_ass_keeps_text_on_edit_clock_and_sidecar_combines_only_captions(tmp_path):
    value = project()
    title = add(value, start=10, end=12, text="TITLE {\\pos(0,0)}\nשלום")
    caption = add(value, kind="caption", start=2, end=4, text="Manual caption")
    transcript = {"segments": [{"start": 15, "end": 17, "text": "AI subtitle"}]}
    keeps = value["draft"]["keep_ranges"]
    clips = value["manual"]["text_clips"]
    ass = build_ass(transcript, keeps, tmp_path / "text.ass", 1280, 720, text_clips=clips).read_text(encoding="utf-8-sig")
    assert "Dialogue: 1,0:00:10.00,0:00:12.00" in ass
    assert "Dialogue: 0,0:00:10.00,0:00:12.00" in ass
    assert r"TITLE \{\\pos(0,0)\}\Nשלום" in ass
    assert "Style: Text0,Arial" in ass
    srt = build_srt(transcript, keeps, tmp_path / "text.srt", text_clips=[title, caption]).read_text(encoding="utf-8")
    assert "TITLE" not in srt and "Manual caption" in srt and "AI subtitle" in srt
    assert srt.index("Manual caption") < srt.index("AI subtitle")
    assert "00:00:02,000 --> 00:00:04,000" in srt
    assert "00:00:10,000 --> 00:00:12,000" in srt


def test_real_ass_text_cannot_inject_alpha_or_new_dialogue(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg runtime is not installed")
    value = project()
    add(value, start=0, end=1, text="{\\alpha&HFF&} VISIBLE\r\nDialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,INJECTED")
    ass = build_ass({}, [], tmp_path / "escape.ass", 640, 360, text_clips=value["manual"]["text_clips"])
    content = ass.read_text(encoding="utf-8-sig")
    assert sum(line.startswith("Dialogue:") for line in content.splitlines()) == 1
    escaped = ass.as_posix().replace(":", "\\:").replace("'", "\\'")
    frame = subprocess.check_output([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=black:s=640x360:r=1:d=1", "-vf", f"ass='{escaped}'", "-frames:v", "1", "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1"], timeout=15)
    assert sum(pixel > 150 for pixel in frame) > 100


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings()
    settings.raw["ai"]["enabled"] = False
    app = create_app(settings)
    app.config["TESTING"] = True
    store = app.extensions["cutroom_store"]
    created = store.create("Text test")
    value = {**created, **project(), "id": created["id"]}
    store.save(value)
    yield app, app.test_client(), store, value["id"]
    app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


def test_api_requires_revision_strict_schema_and_never_calls_ai(api):
    app, client, store, pid = api
    payload = {"action": "text_add", "kind": "caption", "start": 1, "end": 3, "text": "שלום"}
    endpoint = f"/api/projects/{pid}/manual/edit"
    assert client.post(endpoint, json=payload).status_code == 400
    payload["expected_revision"] = store.load(pid)["revision"]
    response = client.post(endpoint, json=payload)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["project"]["manual"]["text_clips"][0]["text"] == "שלום"
    assert client.post(endpoint, json=payload).status_code == 409
    payload["expected_revision"] = store.load(pid)["revision"]
    for field in ("source_start", "path", "volume_db"):
        assert client.post(endpoint, json={**payload, field: 0}).status_code == 400
    assert not app.extensions["cutroom_jobs"].active(project_id=pid)


def test_api_import_allows_normal_files_over_20k_and_rejects_oversize(api):
    _, client, store, pid = api
    content = "1\n00:00:01,000 --> 00:00:02,000\nHello\n\n" + "\n\n".join("NOTE " + "x" * 1000 for _ in range(30))
    payload = {"action": "text_import", "format": "vtt", "content": "WEBVTT\n\n" + content, "expected_revision": store.load(pid)["revision"]}
    endpoint = f"/api/projects/{pid}/manual/edit"
    # Use WebVTT timestamp syntax in the single cue.
    payload["content"] = payload["content"].replace(",000", ".000")
    response = client.post(endpoint, json=payload)
    assert response.status_code == 200, response.get_json()
    payload["expected_revision"] = store.load(pid)["revision"]
    prefix = "WEBVTT\n\n00:01.000 --> 00:02.000\nHello\n\nNOTE "
    payload["content"] = prefix + "x" * (MAX_CAPTION_IMPORT_BYTES - len(prefix))
    response = client.post(endpoint, json=payload)
    assert response.status_code == 200, response.get_json()
    payload["expected_revision"] = store.load(pid)["revision"]
    payload["content"] = "x" * (MAX_CAPTION_IMPORT_BYTES + 1)
    assert client.post(endpoint, json=payload).status_code == 400
    payload["action"] = "text_add"
    assert client.post(endpoint, json=payload).status_code == 400


@pytest.mark.parametrize("sidecar", [False, True])
def test_real_export_burns_manual_text_without_ai_caption_toggle(tmp_path, sidecar):
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg runtime is not installed")
    raw = copy.deepcopy(DEFAULTS)
    raw["render"].update(prefer_hardware=False, min_free_mb=0)
    data = tmp_path / "data"
    projects, exports, cache = (data / name for name in ("projects", "exports", "cache"))
    for folder in (projects, exports, cache):
        folder.mkdir(parents=True)
    settings = Settings(raw, tmp_path, data, projects, exports, cache, ffmpeg, ffprobe)
    store = ProjectStore(settings)
    created = store.create("Text render")
    value = {**created, **project(), "id": created["id"]}
    value["sources"]["A"].update(duration=3, relative_path="media/source.mp4")
    value["settings"].update(aspect="source", resolution="720", quality="fast", captions=sidecar)
    value["draft"].update(keep_ranges=[{"start": 0, "end": 3}], cuts=[], camera_plan=[{"start": 0, "end": 3, "camera": "A"}], output_duration=3)
    add(value, start=1, end=2, text="Hello שלום", position="center")
    add(value, kind="caption", start=1, end=2, text="Manual caption", position="bottom")
    estimate = _estimate_render_storage(value, 640, 360, "fast", settings)
    assert estimate["caption_ass_bytes"] > 0
    assert bool(estimate["caption_srt_bytes"]) == sidecar
    directory = store.project_dir(value["id"])
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=black:s=640x360:r=30:d=3", "-c:v", "libx264", "-preset", "ultrafast", str(directory / "media" / "source.mp4")], check=True, capture_output=True, timeout=20)
    store.save(value)
    result = render_project(JobContext(Job("text-export", "render", value["id"]), threading.Lock()), value["id"], store, settings)
    record = result["export"]
    assert record["captions_burned"] and record["manual_text_count"] == 2
    output = exports / record["name"]
    def lit_pixels(at):
        frame = subprocess.check_output([ffmpeg, "-v", "error", "-ss", str(at), "-i", str(output), "-frames:v", "1", "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1"])
        return sum(value > 150 for value in frame)
    assert lit_pixels(.5) == 0 and lit_pixels(2.5) == 0
    assert lit_pixels(1.5) > 100
    assert bool(record.get("captions_name")) == sidecar
    if sidecar:
        srt = (exports / record["captions_name"]).read_text(encoding="utf-8")
        assert "Manual caption" in srt and "Hello" not in srt
