import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("evaluate_edit", Path(__file__).resolve().parents[1] / "scripts" / "evaluate_edit.py")
evaluate_edit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate_edit)


def project(keeps, words=()):
    return {
        "id": "p1",
        "sources": {"A": {"duration": 100.0}},
        "draft": {"keep_ranges": [{"start": a, "end": b} for a, b in keeps],
                  "chapters": [{"source_start": 0.0}, {"source_start": 52.0}]},
        "analysis": {"transcript": {"segments": [{"words": [{"start": a, "end": b} for a, b in words]}]}},
    }


def test_scores_keep_recall_cut_leak_duration_words_and_chapters():
    reference = {"must_keep": [{"start": 10, "end": 30}], "must_cut": [{"start": 60, "end": 80}],
                 "target_duration": 40, "chapters": [0, 50]}
    report = evaluate_edit.evaluate(reference, project([(0, 20), (70, 90)], words=[(19.5, 20.5)]))
    assert report["must_keep_recall"] == 0.5
    assert report["must_cut_leak"] == 0.5
    assert report["duration_error"] == 0.0
    assert report["mid_word_cuts"] == 1 and report["cut_boundaries"] == 3
    assert report["chapter_mean_error_seconds"] == 1.0


def test_reference_contradictions_are_rejected():
    with pytest.raises(evaluate_edit.InputError):
        evaluate_edit.evaluate({"must_keep": [{"start": 0, "end": 5}], "must_cut": [{"start": 4, "end": 6}]}, project([(0, 5)]))
    with pytest.raises(evaluate_edit.InputError):
        evaluate_edit.evaluate({"must_keep": [{"start": 5, "end": 1}]}, project([(0, 5)]))


def test_suite_reports_thresholds_and_exit_code(tmp_path, capsys):
    (tmp_path / "ref.json").write_text(json.dumps({"must_keep": [{"start": 0, "end": 10}]}))
    (tmp_path / "good.json").write_text(json.dumps(project([(0, 10)])))
    (tmp_path / "bad.json").write_text(json.dumps(project([(50, 60)])))
    manifest = {"cases": [{"name": "good", "reference": "ref.json", "project": "good.json"},
                          {"name": "bad", "reference": "ref.json", "project": "bad.json"}]}
    (tmp_path / "suite.json").write_text(json.dumps(manifest))
    assert evaluate_edit.main(["--suite", str(tmp_path / "suite.json")]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["summary"] == {"cases": 2, "passed": 1, "mean_must_keep_recall": 0.5, "mean_mid_word_cut_rate": 0.0}
    assert report["results"][1]["failures"] == ["must_keep_recall=0.0 (limit 0.9)"]
    assert evaluate_edit.main(["--suite", str(tmp_path / "missing.json")]) == 2
