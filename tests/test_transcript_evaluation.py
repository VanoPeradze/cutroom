from __future__ import annotations

import json
from pathlib import Path
import random
import subprocess
import sys

import pytest

from scripts.evaluate_transcript import edit_distance, evaluate, normalize_text


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("text", ["One two three", "אחת שתיים שלוש", "واحد اثنان ثلاثة", "你好世界你好"])
def test_identical_transcripts_have_zero_errors_in_every_script(text):
    result = evaluate({"text": text}, {"text": text})
    assert result["wer"]["rate"] == 0
    assert result["cer"]["rate"] == 0
    assert result["timing"]["status"] == "unavailable"


@pytest.mark.parametrize("words", [
    ["one", "two", "three"], ["אחת", "שתיים", "שלוש"], ["واحد", "اثنان", "ثلاثة"],
])
@pytest.mark.parametrize("change", ["deletion", "substitution", "insertion"])
def test_word_error_sensitivity_is_the_same_across_spaced_languages(words, change):
    predicted = words.copy()
    if change == "deletion":
        del predicted[1]
    elif change == "substitution":
        predicted[1] = "999"
    else:
        predicted.insert(1, "999")
    result = evaluate({"text": " ".join(words)}, {"text": " ".join(predicted)})
    assert result["wer"]["errors"] == 1
    assert result["wer"]["rate"] == pytest.approx(1 / 3)
    assert result["cer"]["rate"] > 0


@pytest.mark.parametrize("text", ["你好世界你好", "今日は晴れです"])
def test_cer_detects_omissions_without_word_spaces(text):
    result = evaluate({"text": text}, {"text": text[:3]})
    assert result["cer"]["rate"] == pytest.approx((len(text) - 3) / len(text))
    # A whitespace-token WER is deliberately not a Chinese/Japanese word tokenizer.
    assert result["wer"]["rate"] == 1


def test_normalization_is_unicode_aware_and_keeps_language_significant_marks():
    assert normalize_text("  ＨＥＬＬＯ,\tCafe\u0301!  ") == "hello café"
    assert normalize_text("Straße") == "strasse"
    assert normalize_text("\u200fשלום، עולם!\u200f") == "שלום עולם"
    assert normalize_text("مرحبا، بالعالم؟") == "مرحبا بالعالم"
    assert normalize_text("你好，世界！") == "你好世界"
    assert normalize_text("שָׁלוֹם") != normalize_text("שלום")
    assert normalize_text("عَلَم") != normalize_text("علم")
    assert evaluate({"text": "你 好 世 界"}, {"text": "你好世界"})["cer"]["rate"] == 0


@pytest.mark.parametrize("prediction,rate", [("", 0.0), ("unexpected words", None)])
def test_empty_reference_is_explicit_and_json_safe(prediction, rate):
    result = evaluate({"text": ""}, {"text": prediction})
    for metric in ("wer", "cer"):
        assert result[metric]["status"] == "empty_reference"
        assert result[metric]["rate"] == rate
        assert result[metric]["errors"] == result[metric]["hypothesis_units"]
    json.dumps(result, allow_nan=False)


def test_error_rates_are_not_capped_at_one():
    assert evaluate({"text": "one"}, {"text": "one two three four"})["wer"]["rate"] == 3


@pytest.mark.parametrize("words", [
    ["opening", "middle", "ending"], ["פתיחה", "אמצע", "סיום"],
    ["بداية", "وسط", "نهاية"], ["开始", "中间", "结尾"],
])
def test_full_transcript_beats_opening_only_without_last_timestamp_shortcuts(words):
    segments = [{"start": index * 10, "end": index * 10 + 2, "text": word} for index, word in enumerate(words)]
    reference = {"segments": segments}
    full = evaluate(reference, {"analysis": {"transcript": {"segments": segments}}})
    opening = evaluate(reference, {"segments": segments[:1]})
    ending = evaluate(reference, {"segments": segments[-1:]})
    assert full["cer"]["rate"] == 0
    assert full["timing"]["speech_coverage"] == 1
    assert opening["cer"]["rate"] > 0
    assert opening["timing"]["speech_coverage"] == pytest.approx(1 / 3)
    assert ending["timing"]["speech_coverage"] == pytest.approx(1 / 3)
    assert opening["timing"]["reference_speech_seconds"] == 6
    assert opening["timing"]["missed_reference_speech_seconds"] == 4


def test_interval_unions_do_not_double_count_and_report_extra_speech():
    reference = {"text": "hello", "speech_intervals": [{"start": 1, "end": 4}, {"start": 3, "end": 6}]}
    hypothesis = {"segments": [
        {"start": 0, "end": 3, "text": "hello"},
        {"start": 2, "end": 5, "text": "hello"},
        {"start": 8, "end": 9, "text": "extra"},
    ]}
    timing = evaluate(reference, hypothesis)["timing"]
    assert timing["reference_speech_seconds"] == 5
    assert timing["hypothesis_speech_seconds"] == 6
    assert timing["covered_reference_speech_seconds"] == 4
    assert timing["speech_coverage"] == 0.8
    assert timing["outside_reference_speech_seconds"] == 2


def test_empty_timed_hypothesis_is_zero_coverage_but_missing_timing_is_unavailable():
    reference = {"text": "hello", "speech_intervals": [{"start": 5, "end": 7}]}
    assert evaluate(reference, {"segments": []})["timing"]["speech_coverage"] == 0
    assert evaluate(reference, {"text": "hello"})["timing"]["speech_coverage"] is None
    assert evaluate(reference, {"segments": [{"text": "hello"}]})["timing"]["status"] == "unavailable"
    empty_text = {"segments": [{"start": 0, "end": 100, "text": "..."}]}
    assert evaluate(reference, empty_text)["timing"]["speech_coverage"] == 0


def test_empty_speech_reference_is_not_a_perfect_coverage_claim():
    result = evaluate({"text": "", "speech_intervals": []}, {"segments": [{"start": 0, "end": 2, "text": "hallucination"}]})
    assert result["timing"]["status"] == "empty_reference"
    assert result["timing"]["speech_coverage"] is None
    assert result["timing"]["outside_reference_speech_seconds"] == 2


@pytest.mark.parametrize("interval", [
    {"start": -1, "end": 2}, {"start": 3, "end": 2}, {"start": 2, "end": 2},
    {"start": 0, "end": float("nan")}, {"start": 0, "end": float("inf")},
    {"start": "0", "end": 2}, {"start": True, "end": 2}, {"start": 0},
])
def test_invalid_intervals_fail_instead_of_inflating_coverage(interval):
    with pytest.raises(ValueError):
        evaluate({"text": "hello", "speech_intervals": [interval]}, {"segments": []})


@pytest.mark.parametrize("document", [{}, {"analysis": {}}, {"text": None}, {"segments": ["hello"]}, {"segments": None}])
def test_malformed_transcripts_cannot_silently_score_as_empty(document):
    with pytest.raises(ValueError):
        evaluate(document, {"text": ""})


def test_mixed_timed_and_untimed_segments_are_rejected():
    with pytest.raises(ValueError):
        evaluate({"segments": [{"start": 0, "end": 1, "text": "a"}, {"text": "b"}]}, {"segments": []})


def test_bit_vector_distance_matches_independent_dynamic_programming():
    def baseline(left, right):
        previous = list(range(len(right) + 1))
        for row, token in enumerate(left, 1):
            current = [row]
            for column, other in enumerate(right, 1):
                current.append(min(current[-1] + 1, previous[column] + 1, previous[column - 1] + (token != other)))
            previous = current
        return previous[-1]

    randomizer = random.Random(918)
    for _ in range(200):
        left = randomizer.choices(["a", "א", "ع", "中"], k=randomizer.randrange(85))
        right = randomizer.choices(["a", "א", "ع", "中"], k=randomizer.randrange(85))
        assert edit_distance(left, right) == baseline(left, right)
    assert edit_distance("a" * 10000, "a" * 10000 + "b") == 1


def test_cli_reads_utf8_json_without_changing_inputs(tmp_path):
    reference, hypothesis = tmp_path / "reference.json", tmp_path / "project.json"
    reference.write_text(json.dumps({"text": "שלום"}, ensure_ascii=False), encoding="utf-8-sig")
    hypothesis.write_text(json.dumps({"analysis": {"transcript": {"text": "שלום"}}}, ensure_ascii=False), encoding="utf-8")
    before = (reference.read_bytes(), hypothesis.read_bytes())
    run = subprocess.run([sys.executable, str(ROOT / "scripts/evaluate_transcript.py"), str(reference), str(hypothesis)], capture_output=True, text=True, check=True)
    assert json.loads(run.stdout)["cer"]["rate"] == 0
    assert not run.stderr
    assert before == (reference.read_bytes(), hypothesis.read_bytes())


def test_cli_reports_invalid_json_as_a_read_error(tmp_path):
    invalid = tmp_path / "bad.json"
    invalid.write_text("not json", encoding="utf-8")
    run = subprocess.run([sys.executable, str(ROOT / "scripts/evaluate_transcript.py"), str(invalid), str(invalid)], capture_output=True, text=True)
    assert run.returncode == 2
    assert not run.stdout
    assert "error:" in run.stderr
