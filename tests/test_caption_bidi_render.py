"""Optional real libass checks with an independent visual-order oracle.

Only unpointed Hebrew is reversed in the test oracle, never production text.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest
from cutroom.captions import build_ass


@pytest.fixture(scope="module")
def caption_renderer():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("Real caption rendering requires FFmpeg/libass")
    filters = subprocess.run([ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True, check=True)
    if " ass " not in filters.stdout:
        pytest.skip("FFmpeg was built without the libass ass filter")
    if os.name == "nt":
        if not (Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arial.ttf").is_file():
            pytest.skip("Windows render oracle requires installed Arial")
        return ffmpeg, "Arial"
    fc_match = shutil.which("fc-match")
    if not fc_match:
        pytest.skip("Linux render oracle requires fontconfig and DejaVu Sans")
    font = subprocess.run([fc_match, "-f", "%{family}", "DejaVu Sans"], capture_output=True, text=True, check=True)
    if "DejaVu Sans" not in font.stdout:
        pytest.skip("Render oracle requires DejaVu Sans with Hebrew glyphs")
    return ffmpeg, "DejaVu Sans"


def _render(renderer, tmp_path, name, text, *, visual_reference=False):
    ffmpeg, font = renderer
    path = build_ass({}, [], tmp_path / f"{name}.ass", 1000, 160, caption_style="clean",
                     caption_lines=[{"start": 0, "end": 1, "text": "REFERENCE" if visual_reference else text}])
    script = path.read_text("utf-8-sig").replace(",Arial,", f",{font},")
    if visual_reference:
        script = script.replace("REFERENCE", text)
    path.write_text(script, encoding="utf-8-sig")
    result = subprocess.run([
        ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=black:s=1000x160",
        "-vf", f"ass={path.name}", "-frames:v", "1", "-threads", "1",
        "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1",
    ], cwd=tmp_path, capture_output=True, check=True, timeout=30)
    assert len(result.stdout) == 1000 * 160
    assert max(result.stdout) > 200, "A blank frame is not a successful caption render"
    return result.stdout


def _logical(phrase):
    return f"\u05de\u05e6\u05dc\u05de\u05d9\u05dd \u05d1 {phrase} \u05d4\u05d9\u05d5\u05dd."


def _visual(phrase):
    return f"\u202d.\u05dd\u05d5\u05d9\u05d4 {phrase} \u05d1 \u05dd\u05d9\u05de\u05dc\u05e6\u05de\u202c"


def _pixel_error(actual, expected):
    return sum(abs(a - b) for a, b in zip(actual, expected)) / sum(expected)


@pytest.mark.parametrize("phrase", ["4K", "4K 60fps", "Sony A7 IV", "Sony A7 IV / H.264", "Sony, Canon", "Sony (A7 IV)", "H.264", "S-Log3", "4K/60fps", "(4K)", "Swit"])
def test_mixed_hebrew_caption_matches_expected_visual_order(caption_renderer, tmp_path, phrase):
    actual = _render(caption_renderer, tmp_path, "actual", _logical(phrase))
    # Bypass presentation code for the independent LRO/PDF reference.
    expected = _render(caption_renderer, tmp_path, "expected", _visual(phrase), visual_reference=True)
    # Allow subpixel raster differences, normalized by caption ink, not black background.
    assert _pixel_error(actual, expected) < 0.12


def test_render_oracle_detects_reversed_adjacent_tokens(caption_renderer, tmp_path):
    actual = _render(caption_renderer, tmp_path, "actual", _logical("4K 60fps"))
    wrong = _render(caption_renderer, tmp_path, "wrong", _visual("60fps 4K"), visual_reference=True)
    assert _pixel_error(actual, wrong) > 0.12


@pytest.mark.parametrize("per_token", [False, True])
def test_render_oracle_rejects_original_and_per_token_regressions(caption_renderer, tmp_path, monkeypatch, per_token):
    import cutroom.captions as captions
    if per_token:
        monkeypatch.setattr(captions, "_isolate_caption_ltr_runs", lambda text: re.sub(
            r"[0-9]+[A-Za-z]+", lambda match: "\u2066" + match.group(0) + "\u2069", text))
    else:
        monkeypatch.setattr(captions, "_isolate_caption_ltr_runs", lambda text: text)
    actual = _render(caption_renderer, tmp_path, "regression", _logical("4K 60fps"))
    expected = _render(caption_renderer, tmp_path, "expected", _visual("4K 60fps"), visual_reference=True)
    assert _pixel_error(actual, expected) > 0.12
