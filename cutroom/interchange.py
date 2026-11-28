"""Hand the edit to another editor: CMX3600 EDL and FCPXML 1.8.

Both describe the main edit only: which part of source A or B is seen and
heard at each moment of the edited timeline. Layers (imported media, titles),
captions, colour, zooms and the audio mix stay in CUTROOM and are listed in a
note, so nothing is silently dropped. Layouts that show A and B together put
B on the track above A, to be positioned in the other editor.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

COMPOSITES = {"stacked", "side_by_side", "pip"}
FPS_CHOICES = (24, 25, 30, 50, 60)


def _fps(value: Any) -> int:
    try:
        fps = int(value)
    except (TypeError, ValueError):
        return 30
    return fps if fps in FPS_CHOICES else 30


def _frames(seconds: float, fps: int) -> int:
    return max(0, int(round(float(seconds) * fps)))


def timecode(frames: int, fps: int) -> str:
    """Non-drop-frame HH:MM:SS:FF."""
    frames = max(0, int(frames))
    return f"{frames // (3600 * fps):02d}:{frames // (60 * fps) % 60:02d}:{frames // fps % 60:02d}:{frames % fps:02d}"


def _slots_for(camera: str) -> list[str]:
    camera = str(camera or "A")
    if camera == "B":
        return ["B"]
    if camera in COMPOSITES:
        return ["A", "B"]
    return ["A"]  # A, embedded_stack and anything single-source


def edit_events(snapshot: dict[str, Any], audio_slot: str | None, fps: int) -> list[dict[str, Any]]:
    """Picture and sound events in timeline order, in whole frames.

    Each event: {track: "V1"|"V2"|"A", slot, rec_in, rec_out, src_in, src_out, speed, layout}.
    """
    tracks = (snapshot or {}).get("source_tracks") or {}
    plan = ((snapshot or {}).get("sequence") or {}).get("camera_plan") or []
    events: list[dict[str, Any]] = []

    def cover(slot: str, start: float, end: float, track: str, layout: str | None) -> None:
        for clip in tracks.get(slot) or []:
            lo, hi = max(start, float(clip["start"])), min(end, float(clip["end"]))
            if hi - lo <= 1e-6:
                continue
            speed = float(clip.get("video_speed", 1) or 1) if track != "A" else 1.0
            source_start = float(clip.get("video_source_start", clip["source_start"])) if track != "A" else float(clip["source_start"])
            src_in = source_start + (lo - float(clip["start"])) * speed
            rec_in, rec_out = _frames(lo, fps), _frames(hi, fps)
            if rec_out <= rec_in:
                continue
            src_frames_in = _frames(src_in, fps)
            events.append({"track": track, "slot": slot, "rec_in": rec_in, "rec_out": rec_out,
                           "src_in": src_frames_in, "src_out": src_frames_in + int(round((rec_out - rec_in) * speed)),
                           "speed": speed, "layout": layout})

    for row in plan:
        slots = _slots_for(row.get("camera"))
        layout = str(row.get("camera")) if str(row.get("camera")) in COMPOSITES else None
        for index, slot in enumerate(slots):
            cover(slot, float(row["start"]), float(row["end"]), "V1" if index == 0 else "V2", layout)
    if audio_slot in {"A", "B"}:
        cover(audio_slot, 0.0, float((snapshot or {}).get("duration") or 0), "A", None)
    order = {"V1": 0, "V2": 1, "A": 2}
    return sorted(events, key=lambda e: (e["rec_in"], order[e["track"]]))


def left_out(project: dict[str, Any]) -> list[str]:
    manual = project.get("manual") or {}
    notes = []
    if manual.get("media_clips"):
        notes.append(f"{len(manual['media_clips'])} imported media layer(s)")
    if manual.get("text_clips"):
        notes.append(f"{len(manual['text_clips'])} title/text layer(s)")
    if (project.get("settings") or {}).get("burn_captions"):
        notes.append("burned-in captions (export an SRT from CUTROOM)")
    if manual.get("keyframes"):
        notes.append("zoom keyframes")
    if (manual.get("color") or {}).get("look") not in (None, "none"):
        notes.append("colour look")
    return notes


def _reel(slot: str) -> str:
    return f"SRC{slot}".ljust(8)[:8]


def build_edl(project: dict[str, Any], snapshot: dict[str, Any], audio_slot: str | None, fps: Any = 30) -> str:
    fps = _fps(fps)
    title = "".join(ch for ch in str(project.get("name") or "CUTROOM EDIT") if ch.isprintable())[:60] or "CUTROOM EDIT"
    lines = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    sources = project.get("sources") or {}
    number = 0
    for event in edit_events(snapshot, audio_slot, fps):
        number += 1
        kind = "A" if event["track"] == "A" else "V"
        lines.append(f"{number:03d}  {_reel(event['slot'])} {kind:<5} C        "
                     f"{timecode(event['src_in'], fps)} {timecode(event['src_out'], fps)} "
                     f"{timecode(event['rec_in'], fps)} {timecode(event['rec_out'], fps)}")
        name = (sources.get(event["slot"]) or {}).get("name") or f"Source {event['slot']}"
        lines.append(f"* FROM CLIP NAME: {name}")
        if event["track"] == "V2":
            lines.append(f"* TRACK V2: {event['layout']} layout, position this above source A")
        if abs(event["speed"] - 1) > 1e-6:
            lines.append(f"* SPEED {event['speed']:g}x: set the clip speed in your editor")
        lines.append("")
    notes = left_out(project)
    if notes:
        lines.append("* NOT INCLUDED (stays in CUTROOM): " + ", ".join(notes))
    return "\r\n".join(lines).rstrip() + "\r\n"


def _t(frames: int, fps: int) -> str:
    return "0s" if frames == 0 else f"{frames}/{fps}s"


def build_fcpxml(project: dict[str, Any], snapshot: dict[str, Any], audio_slot: str | None,
                 source_paths: dict[str, Path], fps: Any = 30, size: tuple[int, int] = (1920, 1080)) -> str:
    fps = _fps(fps)
    width, height = size
    sources = project.get("sources") or {}
    events = edit_events(snapshot, audio_slot, fps)
    duration = max([_frames(float(snapshot.get("duration") or 0), fps)] + [e["rec_out"] for e in events])
    used = sorted({e["slot"] for e in events})
    name = str(project.get("name") or "CUTROOM edit")
    out = ['<?xml version="1.0" encoding="UTF-8"?>', "<!DOCTYPE fcpxml>", '<fcpxml version="1.8">', "  <resources>",
           f'    <format id="r0"{f' name="FFVideoFormat{height}p{fps}"' if width * 9 == height * 16 else ''} frameDuration="1/{fps}s" width="{width}" height="{height}"/>']
    for slot in used:
        source = sources.get(slot) or {}
        length = _frames(float(source.get("duration") or 0), fps) or duration
        path = source_paths.get(slot)
        src = "file://" + quote(path.resolve().as_posix() if path else str(source.get("name") or slot), safe="/:")
        if src.startswith("file://") and not src.startswith("file:///"):
            src = "file:///" + src[len("file://"):].lstrip("/")
        out.append(f'    <asset id="a{slot}" name={quoteattr(str(source.get("name") or f"Source {slot}"))} src={quoteattr(src)} '
                   f'start="0s" duration="{_t(length, fps)}" hasVideo="1" hasAudio="{1 if source.get("has_audio") else 0}" format="r0"/>')
    out += ["  </resources>", "  <library>", '    <event name="CUTROOM">',
            f"      <project name={quoteattr(name)}>",
            f'        <sequence format="r0" duration="{_t(duration, fps)}" tcStart="0s" tcFormat="NDF">',
            "          <spine>",
            f'            <gap name="CUTROOM edit" offset="0s" start="0s" duration="{_t(duration, fps)}">']
    lanes = {"V1": 1, "V2": 2, "A": -1}
    for event in events:
        enable = "audio" if event["track"] == "A" else "video"
        length = event["rec_out"] - event["rec_in"]
        speed = event["speed"]
        clip = (f'              <asset-clip ref="a{event["slot"]}" lane="{lanes[event["track"]]}" offset="{_t(event["rec_in"], fps)}" '
                f'start="{_t(event["src_in"], fps)}" duration="{_t(length, fps)}" srcEnable="{enable}" '
                f'name={quoteattr((sources.get(event["slot"]) or {}).get("name") or event["slot"])}')
        if abs(speed - 1) > 1e-6:
            out.append(clip + ">")
            out.append(f'                <timeMap><timept time="0s" value="0s" interp="linear"/>'
                       f'<timept time="{_t(length, fps)}" value="{_t(int(round(length * speed)), fps)}" interp="linear"/></timeMap>')
            out.append("              </asset-clip>")
        else:
            out.append(clip + "/>")
    notes = left_out(project)
    if notes:
        out.append(f"              <note>{escape('Not included (stays in CUTROOM): ' + ', '.join(notes))}</note>")
    out += ["            </gap>", "          </spine>", "        </sequence>", "      </project>", "    </event>", "  </library>", "</fcpxml>"]
    return "\n".join(out) + "\n"
