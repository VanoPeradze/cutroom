from __future__ import annotations

import copy

import pytest

from cutroom.captions import _ass_caption_text, build_ass, build_srt


@pytest.mark.parametrize("text", ["לא ישנתי טוב.", "שלום,", "גרסה 12, תקינה.", "مرحبا بالعالم.", "2026: שלום!", "🎙 שלום."])
def test_rtl_punctuation_is_bound_without_reversing_or_rewriting_words(text):
    assert _ass_caption_text(text) == "\u200f" + text + "\u200f"


@pytest.mark.parametrize("text", ["Hello.", "2026.", "English שלום,", "नमस्ते."])
def test_first_strong_direction_preserves_ltr_and_neutral_captions(text):
    assert _ass_caption_text(text) == text


def test_each_multiline_paragraph_has_its_own_direction_and_ass_escaping():
    assert _ass_caption_text("שלום.\r\nEnglish.\r{לא}") == "\u200fשלום.\u200f\\NEnglish.\\N\u200f\\{לא\\}\u200f"
    assert _ass_caption_text(r"שלום \N עולם.") == "\u200fשלום \\\\N עולם.\u200f"


@pytest.mark.parametrize("style", ["clean", "bold", "boxed", "highlight"])
def test_real_ass_entry_keeps_source_and_srt_unchanged(tmp_path, style):
    transcript = {"segments": [{"start": 10, "end": 12, "text": "לא ישנתי טוב.", "words": [
        {"start": 10, "end": 10.3, "word": "לא"},
        {"start": 10.3, "end": 10.8, "word": "ישנתי"},
        {"start": 10.8, "end": 11.5, "word": "טוב."},
    ]}]}
    original = copy.deepcopy(transcript)
    keep = [{"start": 10, "end": 12}]
    ass = build_ass(transcript, keep, tmp_path / "captions.ass", 720, 1280, caption_style=style).read_text("utf-8-sig")
    srt = build_srt(transcript, keep, tmp_path / "captions.srt").read_text("utf8")
    assert "\u200fלא ישנתי טוב.\u200f" in ass
    assert "0:00:00.00,0:00:01.50" in ass
    assert "לא ישנתי טוב." in srt and "\u200f" not in srt
    assert transcript == original


def test_edit_clock_caption_lines_use_same_presentation_and_escaped_markup(tmp_path):
    rows = [{"start": 1.25, "end": 2.5, "text": "שלום {\\b1}."}]
    before = copy.deepcopy(rows)
    ass = build_ass({}, [], tmp_path / "manual.ass", 720, 1280, caption_lines=rows).read_text("utf-8-sig")
    assert "0:00:01.25,0:00:02.50" in ass
    assert "\u200fשלום \\{\\\\b1\\}.\u200f" in ass
    assert rows == before
