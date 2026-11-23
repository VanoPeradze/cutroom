import copy
import pytest
from test_layer_tracks import tracked, unlocked
from test_media_append import library_api, content
from test_mixed_media_insert import post, mixed_layers, VIDEO, media_row
from cutroom.projects import ProjectStore


def insert(api,**fields):
    return post(api,"sequence_insert_all",**{"slot":"A","start":5,"source_start":1,"source_end":2,**fields})

@pytest.mark.parametrize("slot",["A","B"])
@pytest.mark.parametrize("at",[0,5,15])
def test_all_layer_insert_atomic_history_and_clocks(tracked,slot,at):
    app,client,store,pid=tracked;before=store.load(pid);r=insert(tracked,slot=slot,start=at)
    assert r.status_code==200,r.get_json();after=store.load(pid)
    assert after["manual"]["sequence"]["duration"]==16
    assert after["manual"]["layer_tracks"]==before["manual"]["layer_tracks"]
    assert after["manual"]["source_mixer"]==before["manual"]["source_mixer"]
    selected=[c for c in after["manual"]["source_tracks"][slot] if c["start"]==at and c["end"]==at+1]
    assert len(selected)==1 and selected[0]["source_start"]==1
    other="B" if slot=="A" else "A"
    assert not any(c["start"]<at+1 and c["end"]>at for c in after["manual"]["source_tracks"][other])
    if at==5:
        left=next(c for c in after["manual"]["media_clips"] if c["id"]==before["manual"]["media_clips"][1]["id"])
        right=next(c for c in after["manual"]["media_clips"] if c["asset_id"]==VIDEO and c["start"]==6)
        assert left["end"]==5 and right["end"]==7
        assert right["source_start"]==2 and right["video_source_start"]==3.75
        assert right["track_id"]==left["track_id"]
    for key in ("settings","assets","sources","analysis"):assert after[key]==before[key]
    assert after["manual"]["history"]["undo_count"]==before["manual"]["history"]["undo_count"]+1
    assert post(tracked,"undo").status_code==200;assert content(store.load(pid))==content(before)
    assert post(tracked,"redo").status_code==200;assert content(ProjectStore(app.extensions["cutroom_settings"]).load(pid))==content(after)
    raw=store.state_path(pid).read_bytes()
    r=client.post(f"/api/projects/{pid}/manual/edit",json={"action":"sequence_insert_all","slot":slot,"start":at,"source_start":1,"source_end":2,"expected_revision":before["revision"]})
    assert r.status_code==409 and store.state_path(pid).read_bytes()==raw

@pytest.mark.parametrize("fields",[{"start":16},{"start":-1},{"start":True},{"source_start":float("nan")},{"source_end":30},{"source_end":1},{"source_end":1.001},{"slot":"C"},{"extra":1}])
def test_invalid_no_mutation(tracked,fields):
    _,_,store,pid=tracked;raw=store.state_path(pid).read_bytes()
    r=insert(tracked,**fields);assert r.status_code==400,r.get_json();assert store.state_path(pid).read_bytes()==raw

@pytest.mark.parametrize("slot",["A","B"])
def test_either_source_lock_refuses_all_layer_insert(tracked,slot):
    _,_,store,pid=tracked;store.update(pid,lambda p:p["manual"].update(track_locks={slot:True}))
    raw=store.state_path(pid).read_bytes();assert insert(tracked).status_code in (400,409);assert store.state_path(pid).read_bytes()==raw

@pytest.mark.parametrize("guard",["motion","fade","tiny","audio_plan","dormant"])
def test_shared_middle_guards(tracked,guard):
    _,_,store,pid=tracked
    def setup(p):
        if guard=="motion":p["manual"]["media_clips"][3]["motion"]="pan"
        elif guard=="fade":p["manual"]["media_clips"][1]["fade_in"]=1.5
        elif guard=="audio_plan":p["draft"]["audio_plan"]=[{"start":1,"end":2}]
        elif guard=="dormant":p["manual"]["caption_dormant_overrides"]={"unknown":{}}
    store.update(pid,setup);raw=store.state_path(pid).read_bytes()
    r=insert(tracked,start=4.02 if guard=="tiny" else 5)
    assert r.status_code==400,r.get_json();assert store.state_path(pid).read_bytes()==raw


def test_source_insert_reserves_no_imported_capacity(unlocked):
    _,_,store,pid=unlocked
    def setup(p):
        mixed_layers(p)
        p["manual"]["media_clips"]=[{**media_row("1",VIDEO,0,1),"id":f"media_{i:032x}"} for i in range(200)]
        p["manual"]["text_clips"]=[]
    store.update(pid,setup)
    assert post(unlocked,"layer_tracks_enable").status_code==200
    r=insert(unlocked,start=2);assert r.status_code==200,r.get_json()
    assert len(store.load(pid)["manual"]["media_clips"])==200
    raw=store.state_path(pid).read_bytes()
    assert post(unlocked,"media_insert",asset_id=VIDEO,start=2,source_start=0,source_end=1).status_code==400
    assert store.state_path(pid).read_bytes()==raw

@pytest.mark.parametrize("action",["sequence_insert","sequence_insert_linked","sequence_overwrite"])
def test_old_source_action_keeps_independent_layers_unchanged(tracked,action):
    _,_,store,pid=tracked;before=store.load(pid)
    r=post(tracked,action,slot="A",start=5,source_start=1,source_end=2,**({"scope":"edit"} if action=="sequence_overwrite" else {}))
    assert r.status_code==200,r.get_json()
    after=store.load(pid)
    for key in ("media_clips","text_clips","layer_tracks"):assert after["manual"][key]==before["manual"][key]


def test_legacy_absent_layer_arrays_stay_absent(unlocked):
    _,_,store,pid=unlocked;before=store.load(pid)
    assert "media_clips" not in before["manual"] and "text_clips" not in before["manual"]
    r=insert(unlocked);assert r.status_code==200,r.get_json()
    after=store.load(pid)
    assert "media_clips" not in after["manual"] and "text_clips" not in after["manual"]



def test_empty_other_source_lock_still_blocks(tracked):
    _,_,store,pid=tracked
    def setup(p):
        p["manual"]["source_tracks"]["B"]=[]
        p["manual"]["track_locks"]={"B":True}
    store.update(pid,setup);raw=store.state_path(pid).read_bytes()
    r=insert(tracked);assert r.status_code in (400,409),r.get_json()
    assert store.state_path(pid).read_bytes()==raw


def test_missing_revision_and_frame_minimum(tracked):
    _,client,store,pid=tracked;raw=store.state_path(pid).read_bytes()
    r=client.post(f"/api/projects/{pid}/manual/edit",json={"action":"sequence_insert_all","slot":"A","start":5,"source_start":1,"source_end":2})
    assert r.status_code==400 and store.state_path(pid).read_bytes()==raw
    r=insert(tracked,start=15,source_start=1,source_end=1+1/30)
    assert r.status_code==200,r.get_json()



def test_unknown_caption_override_middle_refuses_tail_remains_available(tracked):
    _,_,store,pid=tracked
    store.update(pid,lambda p:p["manual"].update(caption_overrides={"missing-caption":{"text":"Keep me"}}))
    raw=store.state_path(pid).read_bytes();r=insert(tracked)
    assert r.status_code==400 and store.state_path(pid).read_bytes()==raw


def test_twenty_four_hour_cap_is_atomic(tracked):
    _,_,store,pid=tracked
    def setup(p):
        p["manual"]["sequence"]["duration"]=86400
        p["manual"]["sequence"]["camera_plan"]=[{"start":0,"end":86400,"camera":"A"}]
    store.update(pid,setup);raw=store.state_path(pid).read_bytes()
    r=insert(tracked,start=86400);assert r.status_code==400 and store.state_path(pid).read_bytes()==raw
