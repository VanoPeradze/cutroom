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


@pytest.mark.parametrize("phrase", ["4K", "K15", "Swit", "Sony A7 IV", "Sony A7 IV / H.264", "Sony, Canon", "Sony (A7 IV)", "4K 60fps", "H.264", "S-Log3", "4K/60fps", "24-70mm", "f/2.8", "ISO 100", "USB-C"])
def test_rtl_latin_phrases_are_isolated_as_a_whole(phrase):
    text = f"\u05e9\u05dc\u05d5\u05dd {phrase} \u05d4\u05d9\u05d5\u05dd."
    assert _ass_caption_text(text) == "\u200f" + text.replace(phrase, "\u2066" + phrase + "\u2069") + "\u200f"


def test_hebrew_prefix_brackets_and_sentence_punctuation_stay_outside_isolate():
    text = "\u05e6\u05d9\u05dc\u05d5\u05dd \u05d14K, \u05d5\u05d0\u05d6 (H.264)."
    assert _ass_caption_text(text) == "\u200f" + text.replace("4K", "\u20664K\u2069").replace("H.264", "\u2066H.264\u2069") + "\u200f"


@pytest.mark.parametrize("suffix", ["12.5", "Caf\u00e9", "Cafe\u0301", r"{\b1}", r"C:\tmp"])
def test_numeric_runs_accents_and_literal_ass_markup_are_not_partially_isolated(suffix):
    from cutroom.captions import _ass_escape
    text = "\u05e9\u05dc\u05d5\u05dd " + suffix
    assert _ass_caption_text(text) == "\u200f" + _ass_escape(text) + "\u200f"


def test_mixed_paragraphs_keep_first_strong_direction():
    assert _ass_caption_text("English 4K \u05e9\u05dc\u05d5\u05dd.\n\u05e9\u05dc\u05d5\u05dd 4K.") == "English 4K \u05e9\u05dc\u05d5\u05dd.\\N\u200f\u05e9\u05dc\u05d5\u05dd \u20664K\u2069.\u200f"


@pytest.mark.parametrize("style", ["clean", "bold", "boxed", "highlight"])
def test_mixed_caption_presentation_does_not_modify_source_or_srt(tmp_path, style):
    text = "\u05e9\u05dc\u05d5\u05dd Sony A7 IV \u05d4\u05d9\u05d5\u05dd."
    rows = [{"start": 0, "end": 2, "text": text}]
    original = copy.deepcopy(rows)
    ass = build_ass({}, [], tmp_path / "mixed.ass", 720, 1280, caption_style=style, caption_lines=rows).read_text("utf-8-sig")
    srt = build_srt({}, [], tmp_path / "mixed.srt", caption_lines=rows).read_text("utf8")
    assert "\u2066Sony A7 IV\u2069" in ass
    assert text in srt and not any(char in srt for char in "\u200f\u2066\u2069")
    assert rows == original
