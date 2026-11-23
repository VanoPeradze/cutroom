"""Exact settings PATCH scope, using only isolated temporary projects."""
import copy
import pytest
from test_media_library import api
from cutroom.projects import ProjectStore

AUDIO = {
    "preset": "clean", "silence_action": "shorten", "silence_min_seconds": .75125,
    "silence_threshold_dbfs": None, "silence_keep_seconds": .3025,
    "max_remove_ratio": .283333, "quiet_action": "boost", "quiet_gain_db": 2.375,
    "loud_action": "lower", "loud_gain_db": -3.625, "normalize": True, "target_lufs": -18.75,
}


def seed(api):
    _, _, store, pid = api
    return store.update(pid, lambda p: p["settings"].update(audio_cleanup=copy.deepcopy(AUDIO), target_duration=75.125))


def patch(api, settings, revision=None):
    _, client, store, pid = api
    return client.patch(f"/api/projects/{pid}", json={"settings":settings,"expected_revision":revision or store.load(pid)["revision"]})


@pytest.mark.parametrize("field,value", [
    ("preset","natural"),("silence_action","keep"),("silence_min_seconds",1.125),
    ("silence_threshold_dbfs",-38.75),("silence_keep_seconds",.125),
    ("max_remove_ratio",.32125),("quiet_action","keep"),("quiet_gain_db",4.125),
    ("loud_action","keep"),("loud_gain_db",-1.375),("normalize",False),("target_lufs",-20.125),
])
def test_each_audio_leaf_preserves_all_siblings_and_other_saved_state(api, field, value):
    before=seed(api);response=patch(api,{"audio_cleanup":{field:value}})
    assert response.status_code==200,response.get_json()
    saved=api[2].load(api[3]);expected=copy.deepcopy(before["settings"])
    expected["audio_cleanup"][field]=value
    assert saved["settings"]==expected
    for key in ("manual","draft","analysis","sources","assets","exports","name"):
        assert saved.get(key)==before.get(key)
    assert ProjectStore(api[0].extensions["cutroom_settings"]).load(api[3])["settings"]==expected


@pytest.mark.parametrize("settings", [{"fps":60},{"quality":"quality"},{"resolution":"720"},{"caption_style":"clean"},{"burn_captions":False},{"spoken_language":"he"}])
def test_top_level_save_cannot_rewrite_hidden_audio_or_request_values(api, settings):
    before=seed(api);response=patch(api,settings);assert response.status_code==200,response.get_json()
    assert api[2].load(api[3])["settings"]=={**before["settings"],**settings}


def test_explicit_auto_threshold_is_retained_not_dropped(api):
    seed(api);assert patch(api,{"audio_cleanup":{"silence_threshold_dbfs":-35.125}}).status_code==200
    before=api[2].load(api[3]);assert patch(api,{"audio_cleanup":{"silence_threshold_dbfs":None}}).status_code==200
    saved=api[2].load(api[3]);assert saved["settings"]["audio_cleanup"]=={**before["settings"]["audio_cleanup"],"silence_threshold_dbfs":None}


def test_old_revision_rejected_and_leaf_retry_preserves_concurrent_other_window(api):
    old=seed(api);concurrent={"quality":"quality","audio_cleanup":{"quiet_gain_db":7.125,"target_lufs":-21.25}}
    assert patch(api,concurrent,old["revision"]).status_code==200
    before=api[2].state_path(api[3]).read_bytes();response=patch(api,{"audio_cleanup":{"normalize":False}},old["revision"])
    assert response.status_code==409;assert api[2].state_path(api[3]).read_bytes()==before
    assert patch(api,{"audio_cleanup":{"normalize":False}}).status_code==200
    saved=api[2].load(api[3]);assert saved["settings"]["quality"]=="quality"
    assert saved["settings"]["audio_cleanup"]=={**AUDIO,"quiet_gain_db":7.125,"target_lufs":-21.25,"normalize":False}


def test_multiple_partial_and_full_preset_objects_preserve_undefined_fields(api):
    seed(api);changes={"normalize":False,"quiet_gain_db":1.25,"silence_keep_seconds":.375}
    assert patch(api,{"audio_cleanup":changes,"caption_position":"top"}).status_code==200
    before=api[2].load(api[3]);preset={"preset":"tight","silence_action":"shorten","silence_min_seconds":.45,"silence_keep_seconds":.16,"max_remove_ratio":.42,"quiet_action":"boost","quiet_gain_db":4,"loud_action":"lower","loud_gain_db":-4,"normalize":True}
    assert patch(api,{"audio_cleanup":preset}).status_code==200
    assert api[2].load(api[3])["settings"]["audio_cleanup"]=={**before["settings"]["audio_cleanup"],**preset}


@pytest.mark.parametrize("value", [None,[],{"normalize":"false"},{"unknown":1},{"silence_threshold_dbfs":True},{"max_remove_ratio":2},{"target_lufs":float("nan")}])
def test_invalid_audio_patch_is_atomic(api,value):
    seed(api);before=api[2].state_path(api[3]).read_bytes()
    response=patch(api,{"fps":60,"audio_cleanup":value});assert response.status_code==400,response.get_json()
    assert api[2].state_path(api[3]).read_bytes()==before


def test_merge_does_not_mutate_callers_patch_and_empty_audio_means_no_leaf_change(api):
    before=seed(api);store,pid=api[2:];payload={"settings":{"audio_cleanup":{"normalize":False}}};original=copy.deepcopy(payload)
    saved=store.patch(pid,payload,expected_revision=before["revision"]);assert payload==original
    unchanged=store.patch(pid,{"settings":{"audio_cleanup":{}}},expected_revision=saved["revision"])
    assert unchanged["settings"]["audio_cleanup"]==saved["settings"]["audio_cleanup"]


def test_missing_audio_bucket_starts_with_explicit_fields_only(api):
    _,_,store,pid=api;store.update(pid,lambda p:p["settings"].pop("audio_cleanup",None) and None)
    assert patch(api,{"audio_cleanup":{"normalize":False}}).status_code==200
    assert store.load(pid)["settings"]["audio_cleanup"]=={"normalize":False}


def test_non_audio_nested_settings_and_manual_keep_their_existing_shallow_semantics(api):
    _,_,store,pid=api
    store.update(pid,lambda p:p.update(settings={**p["settings"],"opaque":{"old":1,"keep":2}},manual={**p.get("manual",{}),"opaque":{"old":1,"keep":2}}))
    saved=store.patch(pid,{"settings":{"opaque":{"new":3}},"manual":{"opaque":{"new":3}}})
    assert saved["settings"]["opaque"]=={"new":3}
    assert saved["manual"]["opaque"]=={"new":3}


from test_media_render import media, pixel, samples, tone_level


def test_actual_saved_fps_export_keeps_current_picture_and_sound(api,media):
    import hashlib
    import shutil
    import threading
    from cutroom.editing import apply_manual_edit
    from cutroom.jobs import Job,JobContext
    from cutroom.render import render_project
    app,_,store,pid=api;settings=app.extensions["cutroom_settings"]
    settings.raw["render"].update(prefer_hardware=False,min_free_mb=0)
    source=store.project_dir(pid)/"media/settings-source.mp4";shutil.copyfile(media[3],source)
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    p=store.load(pid)
    p.update(sources={"A":{"duration":3.,"width":160,"height":90,"has_audio":True,"relative_path":"media/settings-source.mp4","generation":"synthetic-settings-only"},"B":None},
        analysis={"transcript":{"segments":[]}},assets={},manual={"cuts":[],"keeps":[],"camera_overrides":[]},
        draft={"engine":"synthetic-settings","source_duration":3.,"output_duration":3.,"keep_ranges":[{"start":0.,"end":3.}],"cuts":[],"camera_plan":[{"start":0.,"end":3.,"camera":"A"}],"edit_points":[],"audio_plan":[],"audio_policy":{"normalize":False}})
    p["settings"].update(workflow="manual",goal="youtube",aspect="source",resolution="1440",quality="fast",fps=30,burn_captions=False,captions=False,editorial_effects=False,auto_reframe=False,audio_cleanup=copy.deepcopy(AUDIO))
    apply_manual_edit(p,{"action":"sequence_split_all","time":1.})
    store.save(p)
    def encode(label):
        record=render_project(JobContext(Job(label,"render",pid),threading.Lock()),pid,store,settings,{"_force_software":True})["export"]
        return settings.exports_dir/record["name"],record
    original,old_record=encode("settings-before")
    before=store.load(pid);assert patch(api,{"fps":60}).status_code==200
    saved=store.load(pid)
    assert saved["settings"]=={**before["settings"],"fps":60}
    for key in ("draft","analysis","manual","sources","assets"):assert saved[key]==before[key]
    actual,new_record=encode("settings-after")
    assert old_record["fps"]==30 and new_record["fps"]==60
    assert old_record["duration"]==pytest.approx(3,abs=1/30)
    assert new_record["duration"]==pytest.approx(3,abs=1/60)
    for at in (.2,.8,1.5,2.5):assert pixel(media[1],actual,at,5,5)==pytest.approx(pixel(media[1],original,at,5,5),abs=5)
    sound=[samples(media[1],path) for path in (original,actual)]
    for at in (.2,.8,1.5,2.5):assert tone_level(sound[0],at,440)==pytest.approx(tone_level(sound[1],at,440),abs=.002)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
    assert len(store.load(pid)["exports"])==2 and original.exists() and actual.exists()
