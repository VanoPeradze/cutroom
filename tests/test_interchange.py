from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from cutroom.config import load_settings
from cutroom.interchange import build_edl, build_fcpxml, edit_events, left_out, timecode
from server import create_app

SNAPSHOT = {
    "duration": 10.0,
    "sequence": {"camera_plan": [
        {"start": 0.0, "end": 4.0, "camera": "A"},
        {"start": 4.0, "end": 6.0, "camera": "B"},
        {"start": 6.0, "end": 10.0, "camera": "side_by_side"},
    ]},
    "source_tracks": {
        "A": [{"id": "a1", "start": 0.0, "end": 5.0, "source_start": 12.0},
              {"id": "a2", "start": 5.0, "end": 10.0, "source_start": 30.0, "video_speed": 2, "video_source_start": 30.0}],
        "B": [{"id": "b1", "start": 0.0, "end": 10.0, "source_start": 2.0}],
    },
}
PROJECT = {"name": "My <edit> & co", "sources": {"A": {"name": "cam a.mp4", "duration": 120, "has_audio": True},
                                                 "B": {"name": "cam b.mp4", "duration": 60}},
           "manual": {"text_clips": [{}], "keyframes": [{}]}, "settings": {"burn_captions": True}}


def test_timecode_is_non_drop_frame():
    assert timecode(0, 30) == "00:00:00:00"
    assert timecode(30 * 3661 + 7, 30) == "01:01:01:07"


def test_events_follow_the_camera_plan_and_source_offsets():
    events = edit_events(SNAPSHOT, "A", 30)
    video = [e for e in events if e["track"] != "A"]
    # A 0-4 (clip a1), B 4-6, side by side: A 6-10 (a2 at 2x) on V1, B 6-10 on V2.
    assert [(e["track"], e["slot"], e["rec_in"], e["rec_out"]) for e in video] == [
        ("V1", "A", 0, 120), ("V1", "B", 120, 180), ("V1", "A", 180, 300), ("V2", "B", 180, 300)]
    assert video[0]["src_in"] == 360  # 12 s into source A
    assert video[1]["src_in"] == 180  # 2 + 4 s into source B
    fast = video[2]
    assert fast["speed"] == 2 and fast["src_in"] == 900 + 60 and fast["src_out"] - fast["src_in"] == 240
    audio = [e for e in events if e["track"] == "A"]
    assert [(e["rec_in"], e["rec_out"], e["speed"]) for e in audio] == [(0, 150, 1.0), (150, 300, 1.0)]
    assert edit_events(SNAPSHOT, None, 30) == video


def test_edl_is_cmx3600_with_notes():
    edl = build_edl(PROJECT, SNAPSHOT, "A", 30)
    assert edl.startswith("TITLE: My <edit> & co\r\nFCM: NON-DROP FRAME\r\n")
    assert "\n" not in edl.replace("\r\n", "")
    assert "001  SRCA     V     C        00:00:12:00 00:00:16:00 00:00:00:00 00:00:04:00" in edl
    assert "* TRACK V2: side_by_side layout" in edl
    assert "* SPEED 2x" in edl
    assert "* FROM CLIP NAME: cam b.mp4" in edl
    assert "NOT INCLUDED" in edl and "title/text" in edl and "zoom keyframes" in edl and "captions" in edl
    assert build_edl(PROJECT, SNAPSHOT, "A", 29)  # unsupported fps falls back to 30
    assert "FCM" in build_edl({}, {}, None)


def test_fcpxml_is_valid_xml_with_connected_clips(tmp_path):
    source = tmp_path / "cam a.mp4"
    source.write_bytes(b"x")
    xml = build_fcpxml(PROJECT, SNAPSHOT, "A", {"A": source}, 25, (1080, 1920))
    root = ET.fromstring(xml.split("\n", 2)[2])
    assert root.tag == "fcpxml" and root.get("version") == "1.8"
    fmt = root.find("resources/format")
    assert fmt.get("frameDuration") == "1/25s" and fmt.get("width") == "1080"
    assets = {a.get("id"): a for a in root.iter("asset")}
    assert set(assets) == {"aA", "aB"}
    assert assets["aA"].get("src").startswith("file:///") and "cam%20a.mp4" in assets["aA"].get("src")
    assert assets["aA"].get("hasAudio") == "1" and assets["aB"].get("hasAudio") == "0"
    gap = root.find("library/event/project/sequence/spine/gap")
    assert gap.get("duration") == "250/25s"
    clips = gap.findall("asset-clip")
    assert {c.get("lane") for c in clips} == {"1", "2", "-1"}
    assert all(c.get("srcEnable") == "audio" for c in clips if c.get("lane") == "-1")
    timed = [c for c in clips if c.find("timeMap") is not None]
    assert len(timed) == 1 and timed[0].get("ref") == "aA"
    assert "Not included" in gap.find("note").text
    assert root.find("library/event/project").get("name") == "My <edit> & co"


def test_left_out_is_empty_for_a_plain_edit():
    assert left_out({"manual": {"color": {"look": "none"}}}) == []


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings()
    settings.raw["ai"]["enabled"] = False
    application = create_app(settings)
    application.config.update(TESTING=True)
    return application.test_client()


def test_interchange_endpoint_needs_an_edit_and_a_known_format(client):
    project = client.post("/api/projects", json={"name": "Hand-off"}).get_json()["project"]
    base = f"/api/projects/{project['id']}/interchange"
    assert client.get(base + ".aaf").status_code == 404
    assert client.get(base + ".edl?x=1").status_code == 400
    missing = client.get(base + ".edl")
    assert missing.status_code == 409 and missing.get_json()["error"] == "draft_required"
