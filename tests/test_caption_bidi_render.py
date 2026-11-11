"""Required real libass checks with an independent visual-order oracle.

Only unpointed Hebrew is reversed in the test oracle, never production text.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import shutil
import subprocess

import pytest
from cutroom.captions import build_ass


@pytest.fixture(scope="module")
def caption_renderer():
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "Caption release validation requires FFmpeg/libass on PATH (not an optional skip)"
    filters = subprocess.run([ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True, check=True)
    assert " ass " in filters.stdout, "Caption release validation requires FFmpeg's libass ass filter"
    # This redistributable, pinned fixture covers Hebrew and Latin on Windows,
    # macOS and Linux. No fontconfig utility, OS font or network is required.
    font = Path(__file__).parent / "fixtures" / "fonts" / "DejaVuSans.ttf"
    assert font.is_file(), "The bundled DejaVu caption fixture must be present"
    assert hashlib.sha256(font.read_bytes()).hexdigest() == "7da195a74c55bef988d0d48f9508bd5d849425c1770dba5d7bfc6ce9ed848954"
    bold = font.with_name("DejaVuSans-Bold.ttf")
    assert bold.is_file(), "The bundled bold caption fixture must be present"
    assert hashlib.sha256(bold.read_bytes()).hexdigest() == "e6476c1b80502924294eed40894c5b18e06c181444ca953e5334262df9c27724"
    return ffmpeg, (font, bold)


def _render(renderer, tmp_path, name, text, *, visual_reference=False, style="clean", size=(1000, 160), words=None, scale=100):
    ffmpeg, fonts = renderer
    width, height = size
    # Relative paths avoid filter-graph quoting differences on Windows.
    font_dir = tmp_path / "fonts"
    font_dir.mkdir(exist_ok=True)
    for font in fonts:
        shutil.copyfile(font, font_dir / font.name)
    path = build_ass({}, [], tmp_path / f"{name}.ass", width, height, caption_style=style, caption_scale=scale,
                     caption_lines=[{"start": 0, "end": 1, "text": "REFERENCE" if visual_reference else text, "words": words or []}])
    script = path.read_text("utf-8-sig").replace(",Arial,", ",DejaVu Sans,")
    if visual_reference:
        script = script.replace("REFERENCE", text.replace("\n", r"\N"))
    path.write_text(script, encoding="utf-8-sig")
    result = subprocess.run([
        ffmpeg, "-v", "error", "-f", "lavfi", "-i", f"color=black:s={width}x{height}",
        "-vf", f"ass={path.name}:fontsdir=fonts", "-frames:v", "1", "-threads", "1",
        "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1",
    ], cwd=tmp_path, capture_output=True, check=True, timeout=30)
    assert len(result.stdout) == width * height
    assert max(result.stdout) > 200, "A blank frame is not a successful caption render"
    return result.stdout


def _logical(phrase):
    return f"\u05de\u05e6\u05dc\u05de\u05d9\u05dd \u05d1 {phrase} \u05d4\u05d9\u05d5\u05dd."


def _visual(phrase):
    return f"\u202d.\u05dd\u05d5\u05d9\u05d4 {phrase} \u05d1 \u05dd\u05d9\u05de\u05dc\u05e6\u05de\u202c"


def _portrait_visual(phrase, style):
    # Fixed physical rows for the pinned DejaVu fixtures at 720x1280/100%.
    # They express the intended reading order, never infer it from the output.
    if phrase == "Sony A7 IV / H.264":
        return "\u202dSony A7 \u05d1 \u05dd\u05d9\u05de\u05dc\u05e6\u05de\u202c\n\u202d.\u05dd\u05d5\u05d9\u05d4 IV / H.264\u202c"
    if phrase == "4K 60fps" and style != "clean":
        return "\u202d4K \u05d1 \u05dd\u05d9\u05de\u05dc\u05e6\u05de\u202c\n\u202d.\u05dd\u05d5\u05d9\u05d4 60fps\u202c"
    return _visual(phrase)


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


@pytest.mark.parametrize("style", ["clean", "bold", "boxed", "highlight"])
@pytest.mark.parametrize("size", [(1280, 720), (720, 1280)])
@pytest.mark.parametrize("phrase", ["4K 60fps", "Sony A7 IV / H.264"])
def test_all_styles_landscape_and_portrait_visual_order(caption_renderer, tmp_path, style, size, phrase):
    actual = _render(caption_renderer, tmp_path, "actual", _logical(phrase), style=style, size=size)
    # A visual-LTR paragraph wraps in the opposite reading direction, so the
    # wrapped portrait fixture spells out the two intended physical rows.
    # This is an independent fixed oracle, not computed from production output.
    reference = _portrait_visual(phrase, style) if size == (720, 1280) else _visual(phrase)
    expected = _render(caption_renderer, tmp_path, "expected", reference, style=style, size=size, visual_reference=True)
    assert _pixel_error(actual, expected) < 0.12


@pytest.mark.parametrize("style", ["clean", "bold", "boxed", "highlight"])
def test_explicit_multiline_portrait_visual_order(caption_renderer, tmp_path, style):
    actual = _render(caption_renderer, tmp_path, "actual", _logical("4K 60fps") + "\n" + _logical("Sony A7 IV"), style=style, size=(720, 1280), scale=75)
    expected = _render(caption_renderer, tmp_path, "expected", _visual("4K 60fps") + "\n" + _visual("Sony A7 IV"), style=style, size=(720, 1280), scale=75, visual_reference=True)
    assert _pixel_error(actual, expected) < 0.12


def test_hebrew_highlight_word_timings_keep_plain_bidi_safe_phrase(caption_renderer, tmp_path):
    text = _logical("4K 60fps")
    labels = text.split()
    words = [{"word": label, "start": i / len(labels), "end": (i + 1) / len(labels)} for i, label in enumerate(labels)]
    actual = _render(caption_renderer, tmp_path, "highlight", text, style="highlight", size=(720, 1280), words=words)
    expected = _render(caption_renderer, tmp_path, "expected", _portrait_visual("4K 60fps", "highlight"), style="highlight", size=(720, 1280), visual_reference=True)
    assert _pixel_error(actual, expected) < 0.12
    script = (tmp_path / "highlight.ass").read_text("utf-8-sig")
    assert script.count("Dialogue: ") == 1
    assert r"{\c" not in script, "RTL words must not be split into unsafe libass colour runs"
