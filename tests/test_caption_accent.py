from pathlib import Path

import pytest

from cutroom.captions import build_ass, normalize_caption_accent, normalize_caption_settings

WORDS = [("We", 0, .3), ("made", .3, .6), ("12000", .6, 1.0), ("dollars", 1.0, 1.5)]
TRANSCRIPT = {"segments": [{"start": 0, "end": 1.5, "text": "We made 12000 dollars",
                            "words": [{"word": w, "start": a, "end": b} for w, a, b in WORDS]}]}


def _dialogues(tmp_path: Path, style: str, accent: str = "") -> list[str]:
    target = build_ass(TRANSCRIPT, [{"start": 0, "end": 3}], tmp_path / f"{style}{accent[1:]}.ass", 1080, 1920,
                       caption_style=style, caption_accent=accent)
    return [line.split(",,", 1)[1] for line in target.read_text(encoding="utf-8-sig").splitlines() if line.startswith("Dialogue")]


@pytest.mark.parametrize("value,expected", [("#ff4d6d", "#FF4D6D"), ("#FF4D6D", "#FF4D6D"), ("", ""), ("red", ""),
                                            ("#FF4D6D}{\\b1", ""), (None, ""), (12, ""), ("#FFF", "")])
def test_accent_is_a_strict_hex_colour(value, expected):
    assert normalize_caption_accent(value) == expected
    assert normalize_caption_settings({"caption_accent": value})["caption_accent"] == expected


def test_accent_recolours_the_spoken_word_in_bgr(tmp_path):
    # #FF4D6D is &H6D4DFF& in ASS (blue, green, red).
    for style in ("highlight", "pop", "box", "neon", "word"):
        assert "&H6D4DFF&" in _dialogues(tmp_path, style, "#FF4D6D")[0], style
    assert "&H6D4DFF&" not in "".join(_dialogues(tmp_path, "highlight"))


def test_accent_recolours_key_words_and_leaves_plain_styles_alone(tmp_path):
    later = _dialogues(tmp_path, "emphasis", "#4DB8FF")[0]  # active "We"; "12000" and "dollars" are key words
    assert later.count("&HFFB84D&") == 3
    assert "&H" not in "".join(_dialogues(tmp_path, "bold", "#4DB8FF"))
