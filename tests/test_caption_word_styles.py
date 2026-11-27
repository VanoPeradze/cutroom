from pathlib import Path

from cutroom.captions import (CAPTION_STYLE_CHOICES, WORD_CAPTION_STYLES, build_ass, emphasis_indices,
                              normalize_caption_settings, word_caption_limit)

WORDS = [("We", 0, .3), ("made", .3, .6), ("12000", .6, 1.0), ("dollars", 1.0, 1.5), ("yesterday", 1.5, 2.0)]
TRANSCRIPT = {"segments": [{"start": 0, "end": 2.0, "text": "We made 12000 dollars yesterday",
                            "words": [{"word": w, "start": a, "end": b} for w, a, b in WORDS]}]}


def _dialogues(tmp_path: Path, style: str) -> list[str]:
    target = build_ass(TRANSCRIPT, [{"start": 0, "end": 3}], tmp_path / f"{style}.ass", 1080, 1920, caption_style=style)
    return [line.split(",,", 1)[1] for line in target.read_text(encoding="utf-8-sig").splitlines() if line.startswith("Dialogue")]


def test_every_word_style_is_a_valid_project_choice():
    for style in WORD_CAPTION_STYLES:
        assert style in CAPTION_STYLE_CHOICES
        assert normalize_caption_settings({"caption_style": style})["caption_style"] == style


def test_word_styles_emit_one_event_per_spoken_word(tmp_path):
    for style in ("highlight", "pop", "box", "neon", "emphasis"):
        assert len(_dialogues(tmp_path, style)) == len(WORDS), style


def test_one_word_style_shows_a_single_word(tmp_path):
    rows = _dialogues(tmp_path, "word")
    assert len(rows) == len(WORDS)
    assert all(" " not in row.rsplit("}", 2)[-2] for row in rows)
    assert word_caption_limit("word", 9) == 1 and word_caption_limit("pop", 9) == 4 and word_caption_limit("bold", 9) == 9


def test_active_word_looks_differ_by_style(tmp_path):
    assert "\\fscx125" in _dialogues(tmp_path, "pop")[0]
    assert "\\3c&H4DE1FF&" in _dialogues(tmp_path, "box")[0]
    assert "\\blur" in _dialogues(tmp_path, "neon")[0]


def test_emphasis_colours_numbers_and_long_words_for_the_whole_line(tmp_path):
    assert emphasis_indices(["We", "made", "12000", "dollars,", "really"]) == [2, 3]
    first = _dialogues(tmp_path, "emphasis")[0]
    assert first.count("&H3D8AFF&") == 2  # 12000 and dollars; "We" is the active word


def test_right_to_left_lines_stay_plain(tmp_path):
    transcript = {"segments": [{"start": 0, "end": 1, "text": "שלום עולם", "words": [
        {"word": "שלום", "start": 0, "end": .5}, {"word": "עולם", "start": .5, "end": 1}]}]}
    target = build_ass(transcript, [{"start": 0, "end": 2}], tmp_path / "he.ass", 1080, 1920, caption_style="neon")
    rows = [line for line in target.read_text(encoding="utf-8-sig").splitlines() if line.startswith("Dialogue")]
    assert len(rows) == 1 and "\\blur" not in rows[0]
