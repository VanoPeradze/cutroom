from __future__ import annotations

import shutil
import subprocess

import pytest

from cutroom.captions import build_ass
from cutroom.text_clips import TextClipError, validate_text_clip

CLIP_ID = "text_" + "a" * 32


def clip(**fields):
    return {"id": CLIP_ID, "kind": "title", "start": 0.0, "end": 2.0, "text": "Dana Levi", "position": "bottom",
            "scale": 100, "style": "bold", **fields}


def test_templates_are_a_finite_set_and_plain_stays_backward_compatible():
    assert validate_text_clip(clip(), 10) == clip()
    assert "template" not in validate_text_clip(clip(template="plain"), 10)
    lower = validate_text_clip(clip(template="lower_third", subtext="  Producer  "), 10)
    assert lower["template"] == "lower_third" and lower["subtext"] == "Producer"
    # A second line only belongs to templates that show one.
    assert "subtext" not in validate_text_clip(clip(template="callout", subtext="ignored"), 10)
    for bad in ({"template": "ticker"}, {"template": "lower_third", "subtext": "x" * 201},
                {"template": "chapter", "subtext": "bad\x07"}, {"template": "chapter", "subtext": 5}):
        with pytest.raises(TextClipError):
            validate_text_clip(clip(**bad), 10)


def _events(tmp_path, rows, width=1080, height=1920):
    path = build_ass({}, [], tmp_path / "templates.ass", width, height, text_clips=rows, caption_lines=[])
    content = path.read_text(encoding="utf-8-sig")
    return content, [line for line in content.splitlines() if line.startswith("Dialogue: 1,")]


def test_each_template_has_a_fixed_layout_and_user_text_is_escaped(tmp_path):
    rows = [
        validate_text_clip(clip(template="lower_third", subtext="Producer"), 10),
        validate_text_clip(clip(template="chapter", subtext="Chapter 2", text="The plan"), 10),
        validate_text_clip(clip(template="callout", text="{\\pos(0,0)}Watch the left door"), 10),
        validate_text_clip(clip(template="highlight", position="center", text="Clutch!"), 10),
        validate_text_clip(clip(text="Plain words"), 10),
    ]
    content, events = _events(tmp_path, rows)
    lower, chapter, callout, highlight, plain = events
    assert "\\an1\\pos(65,1613)}Dana Levi\\N{\\fs" in lower and lower.endswith("\\b0}Producer")
    assert "\\an5\\pos(540,960)\\fad(250,250)" in chapter and chapter.index("Chapter 2") < chapter.index("The plan")
    assert "\\an7\\pos(65,144)" in callout and "▌" in callout
    assert "\\{\\\\pos(0,0)\\}Watch the left door" in callout, "a user's braces never become ASS tags"
    assert "\\c&H4DE1FF&" in highlight and "\\pos(540,960)" in highlight
    assert plain.endswith("{\\q0\\pos(540,1776)}Plain words")
    # Lower thirds and callouts sit on a box (BorderStyle 3), as in the preview.
    styles = {line.split(",")[0].removeprefix("Style: "): line.split(",")[15] for line in content.splitlines() if line.startswith("Style: Text")}
    lower_style, callout_style = lower.split(",")[3], callout.split(",")[3]
    assert styles[lower_style] == "3" and styles[callout_style] == "3"


def test_templates_render_with_ffmpeg(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg runtime is not installed")
    rows = [validate_text_clip(clip(template="lower_third", subtext="Producer מפיקה"), 10),
            validate_text_clip(clip(template="callout", text="Watch the left door"), 10)]
    path = build_ass({}, [], tmp_path / "render.ass", 720, 1280, text_clips=rows, caption_lines=[])
    frame = tmp_path / "frame.png"
    result = subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x203040:s=720x1280:d=1",
                             "-vf", f"ass={path.name}", "-frames:v", "1", str(frame)], cwd=tmp_path, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert frame.stat().st_size > 1000
