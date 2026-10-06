from __future__ import annotations

import copy
import threading
from pathlib import Path

import pytest

from cutroom import director, intelligence, visual_moments as vm
from cutroom.config import load_settings
from cutroom.jobs import Job, JobCancelled, JobContext
from cutroom.projects import ProjectStore
from cutroom.vision import VISION_ANALYSIS_VERSION


class Settings:
    raw: dict = {}
    ai = {"enabled": True, "ollama_url": "http://127.0.0.1:11434", "performance_mode": "auto"}


def answer(screen="gameplay", event="player fires", **flags):
    return {"screen": screen, "event": event, **{name: bool(flags.get(name)) for name in vm.ACTION_FLAGS}}


def test_parse_answer_validates_and_ignores_flags_outside_gameplay():
    parsed = vm.parse_answer(answer(shooting=True, enemies_visible=True))
    assert parsed == {"screen": "gameplay", "flags": ["shooting", "enemies_visible"], "event": "player fires"}
    # A cinematic can look explosive; its flags are not gameplay evidence.
    assert vm.parse_answer(answer("cutscene", shooting=True))["flags"] == []
    assert vm.parse_answer({"screen": "space battle"}) is None
    assert vm.parse_answer("not json") is None
    long_event = vm.parse_answer(answer(event="one two three four five six seven eight nine ten eleven twelve thirteen"))
    assert len(long_event["event"].split()) == 12


def test_score_rewards_visible_action_and_zeroes_dead_screens():
    fight = vm.score_answer("gameplay", ["shooting", "enemies_visible", "explosion_fire_or_smoke"])
    walk = vm.score_answer("gameplay", [])
    assert fight > 0.8 > walk > 0
    assert vm.score_answer("gameplay", list(vm.ACTION_FLAGS)) == 1.0
    assert vm.score_answer("menu_or_map", []) == vm.score_answer("loading_or_black", []) == 0.0
    assert vm.score_answer("cutscene", []) < walk


def test_plan_windows_tiles_short_sources_and_samples_long_ones_with_loud_peaks():
    windows, stride = vm.plan_windows(60.0, 120)
    assert stride == vm.WINDOW_SECONDS
    assert windows[0] == (0.0, 8.0) and windows[-1][1] == 60.0
    assert all(start < end for start, end in windows)

    waveform = [{"start": float(t), "end": float(t + 2), "rms_dbfs": -60.0, "peak_dbfs": -40.0} for t in range(0, 1800, 2)]
    waveform[700]["rms_dbfs"] = -10.0  # a loud moment at 1400 s
    windows, stride = vm.plan_windows(1800.0, 40, waveform)
    assert len(windows) == 40
    assert stride == pytest.approx(1800.0 / 30)
    assert any(start <= 1401.0 <= end for start, end in windows)
    assert windows == sorted(windows)
    assert all(0.0 <= start < end <= 1800.0 for start, end in windows)


def _plan(monkeypatch, brief, *, cloud=False, accelerated=True, vision=True, ready=True, settings=None):
    monkeypatch.setattr(vm, "model_supports_vision", lambda *_args, **_kwargs: vision)
    status = {"ready": ready, "selected_model": "qwen3.5:4b" if ready else None}
    return vm.resolve_visual_pass(settings or Settings(), brief, cloud=cloud, accelerated=accelerated, story_status=lambda: status)


def test_auto_runs_only_for_streamer_styles_on_accelerated_devices(monkeypatch):
    streamer = {"goal": "short", "edit_style": "stream_highlights", "performance_mode": "balanced"}
    plan = _plan(monkeypatch, streamer)
    assert plan["run"] is True and plan["model"] == "qwen3.5:4b" and plan["budget"] == 120
    assert _plan(monkeypatch, {**streamer, "edit_style": "smart"})["reason"] == "not_gameplay_style"
    assert _plan(monkeypatch, streamer, accelerated=False)["reason"] == "no_accelerator"
    assert _plan(monkeypatch, {**streamer, "goal": "youtube"})["reason"] == "not_short"


def test_explicit_choices_and_privacy_rules(monkeypatch):
    smart = {"goal": "short", "edit_style": "smart", "performance_mode": "quality"}
    on_cpu = _plan(monkeypatch, {**smart, "visual_ai": "on"}, accelerated=False)
    assert on_cpu["run"] is True and on_cpu["budget"] == vm.DEFAULT_BUDGETS["lite"]
    assert _plan(monkeypatch, {**smart, "visual_ai": "off"})["reason"] == "off"
    # Frames are never uploaded: a cloud connection never runs the pass.
    assert _plan(monkeypatch, {**smart, "visual_ai": "on"}, cloud=True)["reason"] == "cloud_connection"
    assert _plan(monkeypatch, {**smart, "visual_ai": "on"}, vision=False)["reason"] == "model_without_vision"
    assert _plan(monkeypatch, {**smart, "visual_ai": "on"}, ready=False)["reason"] == "story_ai_unavailable"
    assert vm.normalized_visual_mode("ON") == "on" and vm.normalized_visual_mode("bogus") == "auto"


@pytest.fixture
def tiny_video(tmp_path: Path) -> Path:
    cv2 = pytest.importorskip("cv2")
    numpy = pytest.importorskip("numpy")
    path = tmp_path / "gameplay.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (160, 90))
    if not writer.isOpened():
        pytest.skip("OpenCV cannot write a test video here")
    for index in range(10 * 40):
        frame = numpy.full((90, 160, 3), (index * 3) % 255, dtype=numpy.uint8)
        writer.write(frame)
    writer.release()
    return path


def test_analysis_rates_every_window_without_a_real_model(tiny_video):
    calls = []

    def ask(_settings, model, image_b64, timeout):
        calls.append((model, timeout))
        assert image_b64 and len(image_b64) > 100
        index = len(calls)
        return vm.parse_answer(answer("menu_or_map") if index == 2 else answer(shooting=True, enemies_visible=index % 2 == 1))

    progress = []
    result = vm.analyze_visual_moments(tiny_video, 40.0, Settings(), "qwen3.5:4b", budget=50,
                                       progress=lambda value, message: progress.append(value), ask=ask)
    assert result["available"] is True and result["partial"] is False
    assert result["analyzed_windows"] == result["planned_windows"] == 5
    assert calls[0][1] > calls[1][1]  # the first request may load the model
    assert result["windows"][1]["screen"] == "menu_or_map" and result["windows"][1]["score"] == 0.0
    assert result["windows"][0]["score"] > result["windows"][3]["score"] > 0
    assert progress[-1] == 1.0


def test_model_failures_degrade_instead_of_failing_and_cancellation_propagates(tiny_video):
    def broken(*_args):
        raise vm.VisualModelError("The local model did not answer: TimeoutError.")

    failed = vm.analyze_visual_moments(tiny_video, 40.0, Settings(), "qwen3.5:4b", budget=50, ask=broken)
    assert failed["available"] is False and failed["reason"] == "model_failed"

    def rejected(*_args):
        raise vm.VisualModelError("The local model rejected the image request (HTTP 400).")

    calls = []
    stopped = vm.analyze_visual_moments(tiny_video, 40.0, Settings(), "m", budget=50,
                                        ask=lambda *args: calls.append(1) or rejected())
    assert stopped["reason"] == "model_failed" and len(calls) == 1

    def cancel():
        raise JobCancelled("Job cancelled")

    with pytest.raises(JobCancelled):
        vm.analyze_visual_moments(tiny_video, 40.0, Settings(), "m", budget=50, cancel_check=cancel,
                                  ask=lambda *_args: pytest.fail("cancelled work must not call the model"))


def visual_result(rows, stride=8.0):
    return {"available": True, "window_seconds": 8.0, "stride_seconds": stride, "model": "qwen3.5:4b",
            "cache_key": "visual-fixture", "windows": [
                {"start": start, "end": start + 8.0, "screen": screen, "flags": [], "score": score, "event": event}
                for start, screen, score, event in rows
            ]}


def test_timeline_evidence_weights_overlap_and_reports_dead_time():
    timeline = vm.VisualTimeline(visual_result([
        (0.0, "gameplay", 0.9, "firefight at the gate"),
        (8.0, "menu_or_map", 0.0, "inventory"),
        (16.0, "gameplay", 0.2, "walking"),
    ]))
    fight = timeline.evidence(0.0, 8.0)
    assert fight == {"action": 0.9, "dead": 0.0, "screen": "gameplay", "event": "firefight at the gate"}
    mixed = timeline.evidence(4.0, 12.0)
    assert mixed["dead"] == 0.5 and mixed["event"] == "firefight at the gate"
    assert timeline.evidence(8.0, 16.0)["event"] == ""  # nothing notable is named
    assert timeline.evidence(100.0, 110.0) is None
    assert not vm.VisualTimeline({"available": False, "windows": []})
    # A sparse grid speaks for the gap around each analyzed window.
    sparse = vm.VisualTimeline(visual_result([(26.0, "gameplay", 0.8, "sniper duel")], stride=60.0))
    assert sparse.evidence(5.0, 8.0)["action"] == 0.8


def test_on_screen_notes_are_short_and_only_for_clear_evidence():
    assert vm.on_screen_note({"action": 0.84, "dead": 0.0, "screen": "gameplay", "event": "shoots enemies"}) == "gameplay action 8/10: shoots enemies"
    assert vm.on_screen_note({"action": 0.0, "dead": 0.8, "screen": "menu_or_map", "event": ""}) == "menu, map or loading screen"
    assert vm.on_screen_note({"action": 0.1, "dead": 0.0, "screen": "cutscene", "event": ""}) == "cutscene"
    assert vm.on_screen_note({"action": 0.2, "dead": 0.0, "screen": "gameplay", "event": "walks"}) is None
    assert vm.on_screen_note(None) is None


def test_story_beats_get_vision_notes_and_prompts_explain_them_only_when_present():
    beats = [{"id": "b1", "position": 0.0, "start": 0.0, "end": 6.0, "text": "Watch out!"},
             {"id": "b2", "position": 0.6, "start": 9.0, "end": 15.0, "text": "Let me check my gear."}]
    visual = visual_result([(0.0, "gameplay", 0.9, "firefight at the gate"), (8.0, "menu_or_map", 0.0, "")])
    noted = intelligence.annotate_story_beats(beats, visual)
    assert noted[0]["on_screen"] == "gameplay action 9/10: firefight at the gate"
    assert noted[1]["on_screen"] == "menu, map or loading screen"
    assert intelligence.annotate_story_beats(beats, None) is beats
    payload = intelligence._chapter_prompt_payload({"id": "c1", "position": 0, "duration": 15, "beats": noted}, 500)
    assert payload["beats"][0]["on_screen"].startswith("gameplay action")
    assert "on_screen" in intelligence._on_screen_guidance(noted)
    assert intelligence._on_screen_guidance(beats) == ""
    # Without vision evidence the story cache identity is unchanged.
    segments = [{"id": "s1", "start": 0.0, "end": 6.0, "text": "Watch out!"}]
    brief = {"goal": "short"}
    base = intelligence.story_cache_fingerprint(segments, brief, "qwen3.5:4b")
    assert intelligence.story_cache_fingerprint(segments, brief, "qwen3.5:4b", None) == base
    assert intelligence.story_cache_fingerprint(segments, brief, "qwen3.5:4b", "visual-fixture") != base


def test_segment_value_prefers_visible_action_over_menus():
    decision = {"keep_ids": [], "highlight_ids": []}
    plain = director._short_segment_value({"id": "a", "editorial_score": 0.5}, decision)
    action = director._short_segment_value({"id": "a", "editorial_score": 0.5, "visual_action": 0.9}, decision)
    menu = director._short_segment_value({"id": "a", "editorial_score": 0.5, "visual_dead": 1.0}, decision)
    assert action > plain > menu


def test_nonverbal_highlights_follow_visible_action_not_a_loud_menu():
    waveform = []
    for start in range(0, 600, 2):
        loud = 300 <= start < 330  # a loud lobby screen
        waveform.append({"start": float(start), "end": float(start + 2),
                         "rms_dbfs": -12.0 if loud else -40.0, "peak_dbfs": -3.0 if loud else -25.0})
    rows = [(float(t), "gameplay", 0.95 if 120 <= t < 150 else 0.15, "close firefight") for t in range(0, 600, 8)]
    rows = [(t, "menu_or_map", 0.0, "") if 296 <= t < 336 else row for t, *rest in rows for row in [(t, *rest)]]
    timeline = vm.VisualTimeline(visual_result(rows))
    policy = {"max_moments": 1, "pre_roll_seconds": 2.0, "post_roll_seconds": 2.0}
    profile = {"waveform": waveform}
    audio_only = director._select_audio_highlight_ranges(profile, 600.0, 30.0, [], selection_policy=policy)
    with_vision = director._select_audio_highlight_ranges(profile, 600.0, 30.0, [], selection_policy=policy, visual=timeline)
    assert any(row["start"] < 330 and row["end"] > 300 for row in audio_only)
    assert any(row["start"] < 150 and row["end"] > 120 for row in with_vision)
    assert not any(row["start"] < 330 and row["end"] > 300 for row in with_vision)


def test_reel_options_add_best_gameplay_action_with_visual_signals():
    waveform = [{"start": float(t), "end": float(t + 2), "rms_dbfs": -20.0 if 400 <= t < 460 else -45.0,
                 "peak_dbfs": -6.0 if 400 <= t < 460 else -30.0} for t in range(0, 900, 2)]
    rows = [(float(t), "cutscene" if 400 <= t < 460 else "gameplay", 0.95 if 100 <= t < 160 else 0.1,
             "squad clears the rooftop" if 100 <= t < 160 else "") for t in range(0, 900, 8)]
    timeline = vm.VisualTimeline(visual_result(rows))
    draft = {"goal": "short", "source_duration": 900.0, "target_duration": 60.0, "output_duration": 60.0,
             "keep_ranges": [{"start": 600.0, "end": 660.0}], "cuts": [], "camera_plan": []}
    candidates = director._build_reel_candidates({"sources": {"A": {}}, "manual": {}}, draft, [], [], [], None,
                                                 {"waveform": waveform}, timeline)
    kinds = {row["kind"]: row for row in candidates}
    assert "action_moment" in kinds
    action = kinds["action_moment"]
    assert action["keep_ranges"][0]["start"] < 160 and action["keep_ranges"][0]["end"] > 100
    assert action["signals"]["visual"]["action"] >= 50
    assert action["preview"].startswith("squad clears the rooftop")
    without = director._build_reel_candidates({"sources": {"A": {}}, "manual": {}}, draft, [], [], [], None,
                                              {"waveform": waveform})
    assert "action_moment" not in {row["kind"] for row in without}
    assert all("visual" not in row["signals"] for row in without)


@pytest.fixture
def streamer_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    store = ProjectStore(settings)
    project_id = store.create("Gameplay")["id"]
    source = store.project_dir(project_id) / "media" / "source-A.mp4"
    source.write_bytes(b"fixture-source")

    def attach(current):
        current["sources"]["A"] = {"slot": "A", "name": "source.mp4", "relative_path": "media/source-A.mp4",
                                   "duration": 600.0, "width": 1920, "height": 1080, "has_audio": True,
                                   "size": source.stat().st_size}
        current["settings"].update({"goal": "short", "edit_style": "stream_highlights", "target_duration": 60.0,
                                    "duration_mode": "style", "spoken_language": "en", "auto_reframe": False})

    store.update(project_id, attach)
    segments = [{"id": f"s{index}", "start": float(index * 20), "end": float(index * 20 + 6),
                 "text": f"Enemy squad incoming, line {index}!", "words": [], "avg_logprob": -0.1}
                for index in range(30)]
    transcript = {"language": "en", "language_probability": 0.99, "duration": 600.0,
                  "segments": segments, "text": " ".join(row["text"] for row in segments), "words": []}
    calls = {"vision": 0, "plan": [], "plan_visual": []}

    monkeypatch.setattr(director, "_transcribe_safely", lambda *_a, **_k: (copy.deepcopy(transcript), None))
    monkeypatch.setattr(director, "analyze_audio", lambda *_a, **_k: {
        "available": True, "duration": 600.0, "ranges": {}, "summary": {"silence_threshold_dbfs": -42.0},
        "waveform": [{"start": float(t), "end": float(t + 2), "rms_dbfs": -30.0, "peak_dbfs": -12.0} for t in range(0, 600, 2)],
    })
    monkeypatch.setattr(director, "detect_scenes", lambda *_a, **_k: [])
    monkeypatch.setattr(director, "analyze_faces_and_embedded_camera", lambda *_a, **_k: {"version": VISION_ANALYSIS_VERSION, "focus_safe": False})

    def plan(_context, current_segments, *_args, visual_moments=None, **_kwargs):
        calls["plan"].append(1)
        calls["plan_visual"].append((visual_moments or {}).get("cache_key"))
        return {"segments": [{**row, "editorial_score": 0.6} for row in current_segments],
                "decision": {"keep_ids": [row["id"] for row in current_segments], "remove_ids": [],
                             "highlight_ids": ["s1"], "title": "Highlights", "summary": "Fights.",
                             "opening_id": "s1", "closing_id": "s20"},
                "story_beats": [], "story_hierarchy": {"fixture": True}}, "ollama_hierarchical_story"

    monkeypatch.setattr(director, "_plan_edit_with_cancel", plan)
    from cutroom import intelligence as intel
    monkeypatch.setattr(intel, "story_ai_status", lambda *_a, **_k: {"ready": True, "selected_model": "qwen3.5:4b"})
    monkeypatch.setattr(director, "accelerated_inference_available", lambda _settings: True)
    monkeypatch.setattr(vm, "model_supports_vision", lambda *_a, **_k: True)

    def analyze(_path, duration, _settings, model, *, budget, **_kwargs):
        calls["vision"] += 1
        windows = [{"start": float(t), "end": float(t + 8), "screen": "gameplay", "flags": ["shooting"],
                    "score": 0.95 if 200 <= t < 260 else 0.12, "event": "close firefight" if 200 <= t < 260 else ""}
                   for t in range(0, int(duration), 8)]
        return {"version": vm.VISUAL_MOMENTS_VERSION, "available": True, "model": model, "window_seconds": 8.0,
                "stride_seconds": 8.0, "planned_windows": len(windows), "analyzed_windows": len(windows),
                "partial": False, "windows": windows}

    monkeypatch.setattr(director, "analyze_visual_moments", analyze)

    def context():
        return JobContext(Job("fixture_job", "director", project_id), threading.Lock())

    return store, settings, project_id, calls, context


def test_director_runs_gameplay_vision_once_and_reuses_it(streamer_project):
    store, settings, project_id, calls, context = streamer_project
    result = director.analyze_project(context(), project_id, store, settings)
    saved = store.load(project_id)
    assert calls["vision"] == 1
    key = saved["analysis"]["visual_moments"]["cache_key"]
    assert key and calls["plan_visual"] == [key]
    assert saved["analysis"]["cache_fingerprints"]["visual_moments"] == key
    assert result["draft"]["visual_ai"]["used"] is True
    assert result["draft"]["decisions"][0] == {"type": "visual_ai", "count": 75}
    # Flat audio: the most intense option is the firefight the vision pass saw,
    # so a duplicate "best action" option is correctly not added.
    fight = [row for row in result["draft"]["reel_candidates"]
             if row["kind"] in {"intense_moment", "action_moment"}
             and any(item["start"] < 260 and item["end"] > 200 for item in row["keep_ranges"])]
    assert len(fight) == 1 and fight[0]["signals"]["visual"]["action"] >= 50

    director.refine_project(context(), project_id, store, settings, "new_variation")
    assert calls["vision"] == 1  # same source and model: reused, not watched again
    assert len(calls["plan"]) == 1  # equal evidence: story decisions reused too


def test_turning_gameplay_vision_off_replans_without_the_evidence(streamer_project):
    store, settings, project_id, calls, context = streamer_project
    director.analyze_project(context(), project_id, store, settings)
    director.analyze_project(context(), project_id, store, settings, {"visual_ai": "off"})
    saved = store.load(project_id)
    assert calls["vision"] == 1
    assert calls["plan_visual"][-1] is None
    assert saved["analysis"]["visual_moments"] is None
    assert saved["draft"]["visual_ai"] == {**saved["draft"]["visual_ai"], "used": False, "reason": "off"}


def test_a_failed_vision_pass_never_fails_the_edit(streamer_project, monkeypatch):
    store, settings, project_id, calls, context = streamer_project
    monkeypatch.setattr(director, "analyze_visual_moments", lambda *_a, **_k: {
        "version": vm.VISUAL_MOMENTS_VERSION, "available": False, "reason": "model_failed", "windows": []})
    result = director.analyze_project(context(), project_id, store, settings)
    saved = store.load(project_id)
    assert result["draft"]["visual_ai"]["used"] is False
    assert any(row.get("type") == "visual_ai" for row in saved["analysis"]["warnings"])
    assert calls["plan_visual"] == [None]


def test_silent_menus_inside_the_edit_are_cut_but_talked_over_menus_stay():
    timeline = vm.VisualTimeline(visual_result([
        (100.0, "menu_or_map", 0.0, "inventory"),
        (108.0, "gameplay", 0.8, "firefight"),
        (116.0, "loading_or_black", 0.0, ""),
        (300.0, "menu_or_map", 0.0, "map"),
    ]))
    segments = [{"start": 117.0, "end": 120.0, "text": "Okay, loading in."}]
    cuts = [{"start": 0.0, "end": 100.0}, {"start": 124.0, "end": 600.0}]
    output, count = director._cut_dead_screens(cuts, timeline, segments, 600.0)
    assert count == 1
    # The silent inventory is removed with a half-second margin; the loading
    # screen someone talks over stays, and a menu outside the edit is ignored.
    assert {"start": 100.5, "end": 107.5} in output
    kept = director.invert_ranges(output, 600.0)
    assert any(row["start"] <= 108.0 and row["end"] >= 124.0 for row in kept)
    assert director._cut_dead_screens(cuts, vm.VisualTimeline(None), segments, 600.0) == (cuts, 0)
