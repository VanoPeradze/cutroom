from __future__ import annotations

import copy
import json
from pathlib import Path
import threading

import pytest

from cutroom import transcript_batch as batch
from cutroom import editing
import server
from cutroom.caption_items import effective_transcript
from cutroom.config import load_settings
from cutroom.render import project_caption_items
from cutroom.utils import atomic_write_json


def project(count=21):
    segments = [{"id": f"s{i}", "start": i + .1, "end": i + .9,
                 "text": f"Name {i}", "words": [{"start": i + .1, "end": i + .4, "word": "Name"},
                                                   {"start": i + .5, "end": i + .9, "word": str(i)}],
                 "normalized": f"Name {i}", "opaque": {"keep": i}}
                for i in range(count)]
    return {"sources": {"A": {"duration": 30, "width": 160, "height": 90, "has_audio": True}, "B": None},
            "assets": {}, "settings": {"fps": 30, "captions": True, "burn_captions": True},
            "manual": {"cuts": []},
            "draft": {"keep_ranges": [{"start": 0, "end": 30}], "camera_plan": [{"start": 0, "end": 30, "camera": "A"}]},
            "analysis": {"audio_source": "A", "transcript": {"text": " ".join(x["text"] for x in segments),
                          "language": "en", "segments": segments}, "segments": copy.deepcopy(segments),
                         "story_hierarchy": {"old": True}, "editorial_cache": {"old": True}, "opaque": 17}}


def items(value, count=None):
    segments = effective_transcript(value)[0]["segments"]
    return [{"segment_id": str(row.get("id", i)), "base_text": row["text"], "start": row["start"],
             "end": row["end"], "text": f"Fixed {i}"} for i, row in enumerate(segments[:count])]


def action(value, count=None):
    return {"action": "transcript_text_batch", "items": items(value, count)}


def apply(value, body=None):
    return editing.apply_manual_edit(value, body or action(value))


def caption_snapshot(value):
    return editing._caption_snapshot(value)


def test_twenty_one_is_one_undo_and_redo_and_raw_source_exact():
    value = project()
    before = copy.deepcopy(value)
    apply(value)
    assert len(value["manual"]["_history"]["undo"]) == 1
    assert value["manual"]["history"] == {"undo_count": 1, "redo_count": 0}
    assert len(value["manual"]["caption_corrections"]) == 21
    for key in ("transcript", "segments", "opaque", "audio_source"):
        assert value["analysis"][key] == before["analysis"][key]
    for key in ("sources", "assets", "settings"):
        assert value[key] == before[key]
    assert "story_hierarchy" not in value["analysis"] and "editorial_cache" not in value["analysis"]
    saved = caption_snapshot(value)
    editing.apply_manual_edit(value, {"action": "undo"})
    assert caption_snapshot(value) == caption_snapshot(before)
    assert value["analysis"]["transcript"] == before["analysis"]["transcript"]
    editing.apply_manual_edit(value, {"action": "redo"})
    assert caption_snapshot(value) == saved
    assert all(row["text"].startswith("Fixed") for row in effective_transcript(value)[0]["segments"])


@pytest.mark.parametrize("index", [0, 14, 20])
@pytest.mark.parametrize("fault", ["empty", "base", "start", "end", "duplicate", "missing", "extra", "long", "booltime", "nonstring"])
def test_every_invalid_position_refuses_whole_state(index, fault):
    value = project(); before = copy.deepcopy(value); body = action(value); row = body["items"][index]
    if fault == "empty": row["text"] = " \n\t"
    elif fault == "base": row["base_text"] += " changed"
    elif fault == "start": row["start"] += .01
    elif fault == "end": row["end"] += .01
    elif fault == "duplicate": row["segment_id"] = body["items"][(index + 1) % 21]["segment_id"]
    elif fault == "missing": row["segment_id"] = "absent"
    elif fault == "extra": row["extra"] = True
    elif fault == "long": row["text"] = "x" * 4001
    elif fault == "booltime": row["start"] = False
    elif fault == "nonstring": row["text"] = 42
    with pytest.raises(editing.ManualEditError): apply(value, body)
    assert value == before


@pytest.mark.parametrize("ids", [["s0", "s0"], [1, "1"], [None, "1"]])
def test_ambiguous_source_ids_fail_closed(ids):
    value = project(2)
    if ids[0] is None: value["analysis"]["transcript"]["segments"][0]["id"] = "1"; value["analysis"]["transcript"]["segments"][1].pop("id")
    else:
        for row, key in zip(value["analysis"]["transcript"]["segments"], ids): row["id"] = key
    before = copy.deepcopy(value); body = action(value, 1)
    with pytest.raises(editing.ManualEditError, match="ambiguous"): apply(value, body)
    assert value == before


def test_valid_prior_correction_uses_effective_base_and_restores_raw_text():
    value = project(2)
    value["manual"]["caption_corrections"] = {"s0": {"original": "Name 0", "text": "Already fixed"}}
    body = action(value, 1); assert body["items"][0]["base_text"] == "Already fixed"
    body["items"][0]["text"] = "Name 0"
    apply(value, body)
    assert value["manual"]["caption_corrections"] == {}
    editing.apply_manual_edit(value, {"action": "undo"})
    assert value["manual"]["caption_corrections"]["s0"]["text"] == "Already fixed"


def test_stale_target_is_replaced_against_current_raw_anchor():
    value = project(2)
    value["manual"]["caption_corrections"] = {"s0": {"original": "Old original", "text": "Old fix"}, "unused": {"opaque": 7}}
    before = copy.deepcopy(value)
    apply(value, action(value, 1))
    assert value["manual"]["caption_corrections"] == {"s0": {"original": "Name 0", "text": "Fixed 0"}, "unused": {"opaque": 7}}
    assert value["analysis"]["transcript"] == before["analysis"]["transcript"]


def test_sparse_private_layers_and_unrelated_malformed_entry_are_preserved():
    value = project(2)
    layers = {"caption_overrides": {}, "caption_override_anchors": {}, "caption_dormant_overrides": [],
              "caption_corrections": {"unrelated": None, "stale": {"original": "gone", "text": "kept", "opaque": []}}}
    value["manual"].update(copy.deepcopy(layers)); before = copy.deepcopy(value)
    apply(value, action(value, 1))
    for key in layers:
        if key != "caption_corrections": assert value["manual"][key] == before["manual"][key]
    assert value["manual"]["caption_corrections"]["unrelated"] is None
    assert value["manual"]["caption_corrections"]["stale"] == layers["caption_corrections"]["stale"]
    editing.apply_manual_edit(value, {"action": "undo"})
    assert caption_snapshot(value) == caption_snapshot(before)


def test_mixed_noop_and_changed_and_all_noop():
    value = project(3); body = action(value)
    body["items"][0]["text"] = " Name 0 "
    apply(value, body)
    assert set(value["manual"]["caption_corrections"]) == {"s1", "s2"}
    before = copy.deepcopy(value)
    body = action(value)
    for row in body["items"]: row["text"] = row["base_text"]
    apply(value, body)
    assert value == before


@pytest.mark.parametrize("version,pv,locked", [(None, None, False), (1, None, False), (2, None, True), (3, 1, False), (3, 2, True)])
def test_schema_and_locks_do_not_change(version, pv, locked):
    value = project(2)
    if version:
        track = {"id": "track_" + "a" * 32, "kind": "audio", "name": "Locked music"}
        if version >= 2: track["locked"] = locked
        if version == 3: track["audio"] = {"gain_db": -6.1234567, "muted": True}
        value["manual"]["layer_tracks"] = {"version": version, "tracks": [track]}
        if pv: value["manual"]["layer_tracks"]["protection_version"] = pv
    before = copy.deepcopy(value)
    apply(value)
    assert value["manual"].get("layer_tracks") == before["manual"].get("layer_tracks")
    editing.apply_manual_edit(value, {"action": "undo"})
    assert value["manual"].get("layer_tracks") == before["manual"].get("layer_tracks")


@pytest.mark.parametrize("text", ["😀" * 4000, "\u2003  Corrected name \t", "\ufeffBOM remains"], ids=["4000-non-BMP", "strip", "BOM"])
def test_unicode_exact_backend_semantics(text):
    value = project(1); body = action(value); body["items"][0]["text"] = text
    apply(value, body)
    assert value["manual"]["caption_corrections"]["s0"]["text"] == text.strip()


def test_negative_source_offset_times_are_exact_not_clamped():
    value = project(1); row = value["analysis"]["transcript"]["segments"][0]; row.update(start=-.9, end=-.1)
    apply(value)
    assert value["analysis"]["transcript"]["segments"][0]["start"] == -.9


def test_active_alternative_refusal_is_atomic(monkeypatch):
    value = project(); before = copy.deepcopy(value)
    monkeypatch.setattr(batch, "alternative_status", lambda project: {"active_id": "saved-alt"})
    with pytest.raises(editing.ManualEditError, match="Alternative"): apply(value)
    assert value == before


@pytest.mark.parametrize("invalid", [[], [{}] * 1001, None, {}, "items"])
def test_count_or_type_invalid(invalid):
    value = project(); before = copy.deepcopy(value)
    with pytest.raises(editing.ManualEditError): apply(value, {"action": "transcript_text_batch", "items": invalid})
    assert value == before


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings(); settings.raw["ai"]["enabled"] = False
    app = server.create_app(settings); app.config.update(TESTING=True)
    store = app.extensions["cutroom_store"]
    value = store.create("Synthetic atomic transcript proof")
    seed = project(); value["settings"].update(seed.pop("settings")); value.update(seed); value = store.save(value)
    try: yield app, store, value
    finally: app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


def request_body(value):
    return {**action(value), "expected_revision": value["revision"]}


def post(app, value, body):
    return app.test_client().post(f"/api/projects/{value['id']}/manual/edit", json=body)


def test_api_exact_atomic_receipt_reopen_undo_redo(api, tmp_path):
    app, store, value = api; before = copy.deepcopy(value); body = request_body(value)
    response = post(app, value, body); assert response.status_code == 200, response.get_json()
    public = response.get_json()["project"]; saved = store.load(value["id"])
    assert saved["revision"] == value["revision"] + 1
    assert saved["manual"]["history"] == {"undo_count": 1, "redo_count": 0}
    assert saved["analysis"]["transcript"] == before["analysis"]["transcript"]
    assert all(s["text"] == f"Fixed {i}" for i, s in enumerate(public["analysis"]["transcript"]["segments"]))
    assert len(public["editor_captions"]) == 21
    assert all(s["text"].startswith("Fixed") for s in public["editor_captions"])
    assert post(app, saved, {"action": "undo", "expected_revision": saved["revision"]}).status_code == 200
    undone = store.load(value["id"]); assert caption_snapshot(undone) == caption_snapshot(before)
    assert post(app, undone, {"action": "redo", "expected_revision": undone["revision"]}).status_code == 200
    redone = store.load(value["id"]); assert caption_snapshot(redone) == caption_snapshot(saved)
    (tmp_path / "api-21-receipt.json").write_text(json.dumps({"before": before, "request": body, "public": public,
        "saved": saved, "undone": undone, "redone": redone}, indent=2) + "\n", encoding="utf8")


@pytest.mark.parametrize("fault", ["missing_revision", "stale_revision", "bool_revision", "unknown_top", "invalid_item15"])
def test_api_refuses_without_file_changes(api, fault):
    app, store, value = api; path = store.state_path(value["id"]); before = path.read_bytes(); body = request_body(value)
    if fault == "missing_revision": body.pop("expected_revision")
    elif fault == "stale_revision": body["expected_revision"] -= 1
    elif fault == "bool_revision": body["expected_revision"] = True
    elif fault == "unknown_top": body["extra"] = []
    else: body["items"][14]["base_text"] = "changed elsewhere"
    response = post(app, value, body)
    assert response.status_code in (400, 409), response.get_json()
    assert path.read_bytes() == before


def test_api_noop_does_not_write_or_invalidate(api, monkeypatch):
    app, store, value = api; body = request_body(value)
    for row in body["items"]: row["text"] = row["base_text"]
    path = store.state_path(value["id"]); before = path.read_bytes(); mtime = path.stat().st_mtime_ns
    calls = []; save = store._save_unlocked
    monkeypatch.setattr(store, "_save_unlocked", lambda *a, **kw: (calls.append(True), save(*a, **kw))[1])
    response = post(app, value, body)
    assert response.status_code == 200, response.get_json()
    assert not calls and path.read_bytes() == before and path.stat().st_mtime_ns == mtime
    assert response.get_json()["project"]["revision"] == value["revision"]


@pytest.mark.parametrize("first_name", ["original", "explicit_retry"])
def test_same_body_original_revision_race_commits_at_most_once(api, monkeypatch, first_name):
    app, store, value = api; body = request_body(value); immutable = json.dumps(body, sort_keys=True)
    entered = threading.Event(); release = threading.Event(); other_started = threading.Event()
    real = server.apply_manual_edit; calls = []; outcomes = {}
    def held(project, payload, **kwargs):
        calls.append(threading.current_thread().name)
        entered.set(); assert release.wait(5)
        return real(project, payload, **kwargs)
    monkeypatch.setattr(server, "apply_manual_edit", held)
    def invoke(name):
        if name != first_name: other_started.set()
        response = post(app, value, copy.deepcopy(body)); outcomes[name] = response.status_code
    second_name = "explicit_retry" if first_name == "original" else "original"
    first = threading.Thread(target=invoke, args=(first_name,), name=first_name)
    second = threading.Thread(target=invoke, args=(second_name,), name=second_name)
    first.start(); assert entered.wait(5); second.start(); assert other_started.wait(5); release.set()
    first.join(5); second.join(5)
    assert not first.is_alive() and not second.is_alive()
    assert outcomes == {first_name: 200, second_name: 409}
    assert calls == [first_name]
    saved = store.load(value["id"])
    assert saved["revision"] == value["revision"] + 1 and saved["manual"]["history"]["undo_count"] == 1
    assert json.dumps(body, sort_keys=True) == immutable


def test_lost_committed_response_then_check_then_same_retry_is_not_replayed(api):
    app, store, value = api; body = request_body(value)
    assert post(app, value, body).status_code == 200  # response intentionally not installed by a caller
    latest = app.test_client().get(f"/api/projects/{value['id']}").get_json()["project"]
    assert latest["revision"] == value["revision"] + 1
    path = store.state_path(value["id"]); before = path.read_bytes()
    assert post(app, value, body).status_code == 409
    assert path.read_bytes() == before


def test_never_arrived_first_request_baseline_get_then_explicit_retry(api):
    app, store, value = api; body = request_body(value); path = store.state_path(value["id"]); before = path.read_bytes()
    latest = app.test_client().get(f"/api/projects/{value['id']}").get_json()["project"]
    assert latest["revision"] == value["revision"] and path.read_bytes() == before
    # A GET alone cannot prove whether a first request is delayed. This explicit
    # same-body/same-revision request shares the exact CAS with any late first.
    assert post(app, value, body).status_code == 200
    assert post(app, value, body).status_code == 409
    assert store.load(value["id"])["manual"]["history"]["undo_count"] == 1


def test_busy_job_refusal(api):
    app, store, value = api
    event = threading.Event()
    job = app.extensions["cutroom_jobs"].submit("transcript-proof-hold", value["id"], lambda ctx: event.wait(5))
    try:
        before = store.state_path(value["id"]).read_bytes()
        response = post(app, value, request_body(value))
        assert response.status_code == 409, response.get_json()
        assert store.state_path(value["id"]).read_bytes() == before
    finally: event.set()


@pytest.mark.parametrize("field", ["segment_id", "base_text", "text"])
def test_lone_surrogate_rejected(field):
    value = project(1); before = copy.deepcopy(value); body = action(value)
    body["items"][0][field] = "bad\ud800text"
    with pytest.raises(editing.ManualEditError): apply(value, body)
    assert value == before


@pytest.mark.parametrize("fix", [None, [], {"opaque": True}, {"original": "Name 0", "text": "Old", "future": 1}])
def test_selected_malformed_correction_refuses_instead_of_dropping_fields(fix):
    value = project(1); value["manual"]["caption_corrections"] = {"s0": fix}; before = copy.deepcopy(value)
    with pytest.raises(editing.ManualEditError): apply(value)
    assert value == before


@pytest.mark.parametrize("time", [float("nan"), float("inf"), -(10 ** 500), 604801])
def test_nonfinite_or_extreme_source_time_rejects_atomically(time):
    value = project(1); before = copy.deepcopy(value); body = action(value); body["items"][0]["start"] = time
    with pytest.raises(editing.ManualEditError): apply(value, body)
    assert value == before


def test_real_copy_lease_refuses_api_without_writes(api):
    app, store, value = api; coordinator = app.extensions["cutroom_project_copies"]
    coordinator.lease.write_text(json.dumps({"pid": 123, "source_project_id": value["id"], "operation_token": "proof"}), encoding="utf8")
    try:
        before = store.state_path(value["id"]).read_bytes()
        response = post(app, value, request_body(value))
        assert response.status_code == 409, response.get_json()
        assert store.state_path(value["id"]).read_bytes() == before
    finally: coordinator.lease.unlink()


def test_actual_active_alternative_refuses_api(api):
    from cutroom.caption_alternatives import FORMAT, binding, register, review, status
    app, store, value = api
    value["sources"]["A"]["generation"] = "proof-generation"
    value = store.save(value)
    alternate = {"format": FORMAT, "label": "Proof alternative", "binding": binding(value), "source_interval": [0., 30.],
                 "transcript": {"language": "en", "segments": [{"id": "s0", "start": 0., "end": 30., "text": "Alternative words"}]}}
    imported = app.test_client().post(f"/api/projects/{value['id']}/caption-alternatives", json={"alternative": alternate, "expected_revision": value["revision"]})
    assert imported.status_code == 200, imported.get_json()
    public = imported.get_json()["project"]; key = public["caption_alternatives"][0]["id"]
    reviewed = app.test_client().get(f"/api/projects/{value['id']}/caption-alternatives/{key}").get_json()["proposal"]
    selected = post(app, value, {"action": "caption_alternative", "alternative_id": key,
                                "review_fingerprint": reviewed["review_fingerprint"], "expected_revision": reviewed["revision"]})
    assert selected.status_code == 200, selected.get_json()
    value = store.load(value["id"]); assert status(value)["active_id"] == key
    before = store.state_path(value["id"]).read_bytes()
    response = post(app, value, {"action": "transcript_text_batch", "items": [{"segment_id": "s0", "base_text": "Name 0", "start": .1, "end": .9, "text": "New"}], "expected_revision": value["revision"]})
    assert response.status_code == 400, response.get_json()
    assert store.state_path(value["id"]).read_bytes() == before


def test_reused_speech_local_override_keeps_its_own_text():
    from test_caption_items import sequence_project
    value = sequence_project()
    editing.apply_manual_edit(value, {"action": "caption_update", "caption_id": "s1:w0~1", "text": "Only here"})
    before = copy.deepcopy(value)
    body = {"action": "transcript_text_batch", "items": [{"segment_id": "s1", "base_text": "Later words", "start": 2.1, "end": 2.9, "text": "Corrected phrase"}]}
    apply(value, body)
    by_id = {row["id"]: row for row in project_caption_items(value)}
    assert by_id["s1:w0"]["text"] == "Corrected phrase" and by_id["s1:w0~1"]["text"] == "Only here"
    assert value["manual"]["caption_overrides"] == before["manual"]["caption_overrides"]
    assert value["manual"]["caption_override_anchors"] == before["manual"]["caption_override_anchors"]
    assert value["analysis"]["transcript"] == before["analysis"]["transcript"]


def test_unchanged_singular_save_still_one_caption_action():
    value = project(1)
    editing.apply_manual_edit(value, {"action": "transcript_text", "segment_id": "s0", "text": "Single corrected"})
    assert value["manual"]["caption_corrections"]["s0"]["text"] == "Single corrected"
    assert value["manual"]["history"]["undo_count"] == 1


def test_caption_scene_ass_and_srt_match_independent_overlay_reference(tmp_path):
    from test_caption_items import sequence_project
    from cutroom.caption_items import caption_lines
    from cutroom.captions import build_ass, build_srt
    from cutroom.render import caption_preview_scene
    value = sequence_project()
    editing.apply_manual_edit(value, {"action": "caption_update", "caption_id": "s1:w0~1", "text": "Only here", "style": "boxed"})
    before = copy.deepcopy(value); reference = copy.deepcopy(value)
    wanted = {"s0": "Hello corrected words", "s1": "שלום CUTROOM"}
    body = action(value)
    for item in body["items"]: item["text"] = wanted[item["segment_id"]]
    # Independent specification: overlay the known original text with reviewed
    # replacements, without using the candidate planner or singular edit action.
    reference["manual"]["caption_corrections"] = {
        row["id"]: {"original": row["text"].strip(), "text": wanted[row["id"]]}
        for row in reference["analysis"]["transcript"]["segments"]}
    apply(value, body)
    assert value["analysis"]["transcript"] == before["analysis"]["transcript"]
    assert caption_preview_scene(value) == caption_preview_scene(reference)
    for aligned in (False, True):
        assert project_caption_items(value, aligned=aligned) == project_caption_items(reference, aligned=aligned)
    produced = []
    for label, source in (("candidate", value), ("reference", reference)):
        lines = caption_lines(project_caption_items(source), 6, default_style="highlight")
        ass = build_ass({}, [], tmp_path / f"{label}.ass", 1080, 1920, caption_style="highlight", caption_lines=lines)
        srt = build_srt({}, [], tmp_path / f"{label}.srt", caption_lines=lines)
        produced.append((ass.read_bytes(), srt.read_bytes()))
    assert produced[0] == produced[1]


@pytest.mark.parametrize("kind", ["id-too-long", "base-too-long", "text-too-long-raw", "bad-manual", "bad-corrections"])
def test_remaining_boundaries_fail_without_mutation(kind):
    value = project(1); body = action(value)
    if kind == "id-too-long": body["items"][0]["segment_id"] = "a" * 129
    elif kind == "base-too-long": body["items"][0]["base_text"] = "a" * 20001
    elif kind == "text-too-long-raw": body["items"][0]["text"] = " " * 20001 + "x"
    elif kind == "bad-manual": value["manual"] = None
    else: value["manual"]["caption_corrections"] = []
    before = copy.deepcopy(value)
    with pytest.raises(editing.ManualEditError): apply(value, body)
    assert value == before


def test_maximum_1000_entries_is_one_prepared_overlay():
    value = project(1000)
    result = batch.prepare_transcript_batch(value, action(value))
    assert len(result) == 1000 and "_history" not in value["manual"]


@pytest.mark.parametrize("history,counts", [
    (None, None), ([], None), ({}, None), ({"undo": [], "redo": None}, None),
    ({"undo": ["bad"], "redo": []}, {"undo_count": 1, "redo_count": 0}),
    ({"undo": [{}] * 21, "redo": []}, {"undo_count": 21, "redo_count": 0}),
    ({"undo": [{}], "redo": []}, None),
    ({"undo": [], "redo": []}, {"undo_count": True, "redo_count": 0}),
    ({"undo": [], "redo": []}, {"undo_count": 1, "redo_count": 0}),
    ({"undo": [], "redo": []}, {"undo_count": 0, "redo_count": 0, "future": 1}),
], ids=["null", "list", "missing-stacks", "bad-stack", "bad-entry", "over-cap", "absent-counts", "bool-count", "mismatch", "extra-visible"])
def test_malformed_history_cannot_be_normalized(history, counts):
    value = project(1); value["manual"]["_history"] = copy.deepcopy(history)
    if counts is not None: value["manual"]["history"] = copy.deepcopy(counts)
    before = copy.deepcopy(value)
    with pytest.raises(editing.ManualEditError, match="history"): apply(value)
    assert value == before


def test_valid_opaque_history_entries_preserved_with_normal_cap():
    value = project(1)
    old = [{"kind": "opaque-existing", "ordinal": i, "before": {"private": i}, "after": {"private": i + 1}} for i in range(20)]
    value["manual"].update({"_history": {"undo": copy.deepcopy(old), "redo": [{"opaque": "redo"}], "private": {"keep": True}},
                           "history": {"undo_count": 20, "redo_count": 1}})
    apply(value)
    history = value["manual"]["_history"]
    assert history["undo"][:-1] == old[1:] and len(history["undo"]) == 20
    assert history["redo"] == [] and history["private"] == {"keep": True}
    assert history["undo"][-1]["kind"] == "captions"
    editing.apply_manual_edit(value, {"action": "undo"})
    assert "caption_corrections" not in value["manual"]


def test_api_history_refusal_is_byte_exact(api):
    app, store, value = api
    value["manual"].update({"_history": {"undo": [], "redo": []}, "history": {"undo_count": 7, "redo_count": 0}})
    value = store.save(value); path = store.state_path(value["id"]); before = path.read_bytes()
    response = post(app, value, request_body(value))
    assert response.status_code == 400 and path.read_bytes() == before


def test_existing_transport_limit_is_not_relaxed(api):
    app, store, value = api; before = store.state_path(value["id"]).read_bytes()
    huge = '{"action":"transcript_text_batch","items":[],"padding":"' + 'x' * (7 * 1024 * 1024) + '"}'
    response = app.test_client().post(f"/api/projects/{value['id']}/manual/edit", data=huge, content_type="application/json")
    assert response.status_code == 413
    assert store.state_path(value["id"]).read_bytes() == before


def test_locked_actual_source_media_and_text_members_are_untouched():
    value = project(1)
    visual, text = "track_" + "a" * 32, "track_" + "b" * 32
    asset = "asset_" + "a" * 32
    value["assets"][asset] = {"id": asset, "kind": "image", "status": "ready", "opaque": 1}
    value["manual"].update({"track_locks": {"A": True},
        "layer_tracks": {"version": 3, "protection_version": 2, "tracks": [
            {"id": visual, "kind": "visual", "name": "Image", "locked": True, "audio": {"gain_db": -3, "muted": False}},
            {"id": text, "kind": "text", "name": "Title", "locked": True}]},
        "media_clips": [{"id": "media_" + "a" * 32, "asset_id": asset, "start": 0, "end": 3, "track_id": visual, "enabled": False, "opaque": []}],
        "text_clips": [{"id": "text_" + "a" * 32, "start": 0, "end": 3, "track_id": text, "text": "Original title", "opaque": []}]})
    before = copy.deepcopy(value)
    apply(value)
    for key in ("track_locks", "layer_tracks", "media_clips", "text_clips"):
        assert value["manual"][key] == before["manual"][key]
    assert value["assets"] == before["assets"] and value["sources"] == before["sources"]


def test_retained_edit_api_is_not_bypassed(api):
    app, store, value = api
    value["draft"] = None; value["manual"]["cuts"] = [{"start": 1, "end": 2}]
    value = store.save(value); before = store.state_path(value["id"]).read_bytes()
    response = post(app, value, request_body(value))
    assert response.status_code in (400, 409), response.get_json()
    assert store.state_path(value["id"]).read_bytes() == before


def test_future_track_schema_api_fails_closed(api):
    app, store, value = api
    value["manual"]["layer_tracks"] = {"version": 999, "tracks": []}
    atomic_write_json(store.state_path(value["id"]), value)
    before = store.state_path(value["id"]).read_bytes()
    response = post(app, value, request_body(value))
    assert response.status_code in (400, 409), response.get_json()
    assert store.state_path(value["id"]).read_bytes() == before


def test_unrelated_writer_wins_old_original_and_retry_both_conflict(api):
    app, store, value = api; body = request_body(value)
    changed = store.patch(value["id"], {"name": "A newer unrelated name"}, expected_revision=value["revision"])
    assert changed["revision"] == value["revision"] + 1
    path = store.state_path(value["id"]); before = path.read_bytes()
    assert post(app, value, copy.deepcopy(body)).status_code == 409
    assert post(app, value, copy.deepcopy(body)).status_code == 409
    assert path.read_bytes() == before
    saved = store.load(value["id"])
    assert "caption_corrections" not in saved["manual"]
    assert "_history" not in saved["manual"] and "history" not in saved["manual"]


def test_rejected_retry_does_not_determine_delayed_original_outcome(api, monkeypatch):
    app, store, value = api; body = request_body(value)
    entered = threading.Event(); release = threading.Event(); results = {}
    real = server.apply_manual_edit
    def held(project, payload, **kwargs):
        entered.set(); assert release.wait(5)
        return real(project, payload, **kwargs)
    monkeypatch.setattr(server, "apply_manual_edit", held)
    def original(): results["original"] = post(app, value, copy.deepcopy(body)).status_code
    worker = threading.Thread(target=original, name="delayed-original")
    baseline_bytes = store.state_path(value["id"]).read_bytes()
    worker.start()
    try:
        assert entered.wait(5)
        retry = app.test_client().post(f"/api/projects/{value['id']}/manual/edit", json=copy.deepcopy(body),
                                      headers={"Origin": "https://untrusted.invalid"})
        assert retry.status_code == 403, retry.get_json()
        assert store.state_path(value["id"]).read_bytes() == baseline_bytes
    finally:
        release.set(); worker.join(5)
    assert not worker.is_alive() and results["original"] == 200
    latest = app.test_client().get(f"/api/projects/{value['id']}").get_json()["project"]
    assert latest["revision"] == value["revision"] + 1
    assert latest["manual"]["history"] == {"undo_count": 1, "redo_count": 0}
    assert all(row["text"] == f"Fixed {i}" for i, row in enumerate(latest["analysis"]["transcript"]["segments"]))
