"""Explicit creation destinations are atomic and never auto-reallocated."""
import copy
import pytest
from test_layer_tracks import tracked, unlocked
from test_mixed_media_insert import post, VIDEO
from test_media_append import content, library_api
from cutroom.projects import ProjectStore
from cutroom.layer_tracks import validate_layer_tracks


def lane(api,kind="visual"):
    assert post(api,"layer_track_add",kind=kind,name="Chosen destination").status_code==200
    return api[2].load(api[3])["manual"]["layer_tracks"]["tracks"][-1]["id"]

@pytest.mark.parametrize("action",["media_add","media_insert","media_append"])
def test_explicit_creation_exact_destination_history(tracked,action):
    app,client,store,pid=tracked;target=lane(tracked);before=store.load(pid)
    fields={"asset_id":VIDEO,"track_id":target}
    if action!="media_append":fields["start"]=4
    if action!="media_add":fields.update(source_start=1,source_end=2)
    response=post(tracked,action,**fields);assert response.status_code==200,response.get_json()
    after=store.load(pid);placed=after["manual"]["media_clips"][-1]
    assert placed["track_id"]==target and placed["id"] not in {r["id"] for r in before["manual"]["media_clips"]}
    assert after["manual"]["layer_tracks"]==before["manual"]["layer_tracks"]
    assert after["manual"]["history"]["undo_count"]==before["manual"]["history"]["undo_count"]+1
    if action!="media_add":assert placed["source_start"]==1 and placed["end"]-placed["start"]==1
    validate_layer_tracks(after)
    assert post(tracked,"undo").status_code==200;assert content(store.load(pid))==content(before)
    assert post(tracked,"redo").status_code==200;assert content(ProjectStore(app.extensions["cutroom_settings"]).load(pid))==content(after)
    raw=store.state_path(pid).read_bytes()
    stale=client.post(f"/api/projects/{pid}/manual/edit",json={"action":action,"expected_revision":before["revision"],**fields})
    assert stale.status_code==409 and store.state_path(pid).read_bytes()==raw

@pytest.mark.parametrize("action",["media_add","media_insert","media_append"])
@pytest.mark.parametrize("target",[None,"",False,1,{},"track_"+"f"*32])
def test_bad_target_no_mutation(tracked,action,target):
    _,_,store,pid=tracked;raw=store.state_path(pid).read_bytes()
    response=post(tracked,action,asset_id=VIDEO,track_id=target,**({"start":4} if action!="media_append" else {}))
    assert response.status_code==400,response.get_json();assert store.state_path(pid).read_bytes()==raw

@pytest.mark.parametrize("kind",["audio","text"])
def test_wrong_kind_no_mutation(tracked,kind):
    target=lane(tracked,kind);_,_,store,pid=tracked;raw=store.state_path(pid).read_bytes()
    assert post(tracked,"media_add",asset_id=VIDEO,start=4,track_id=target).status_code==400
    assert store.state_path(pid).read_bytes()==raw

@pytest.mark.parametrize("disabled",[False,True])
def test_occupied_add_rejects_instead_of_allocating(tracked,disabled):
    _,_,store,pid=tracked
    if disabled:store.update(pid,lambda p:p["manual"]["media_clips"][0].update(enabled=False))
    p=store.load(pid);row=p["manual"]["media_clips"][0];raw=store.state_path(pid).read_bytes()
    response=post(tracked,"media_add",asset_id=VIDEO,start=row["start"],track_id=row["track_id"])
    assert response.status_code==400 and "overlap" in response.get_json()["message"]
    assert store.state_path(pid).read_bytes()==raw


def test_insert_uses_gap_opened_on_crossing_chosen_lane(tracked):
    _,_,store,pid=tracked;before=store.load(pid);row=before["manual"]["media_clips"][1]
    response=post(tracked,"media_insert",asset_id=VIDEO,start=5,source_start=1,source_end=2,track_id=row["track_id"])
    assert response.status_code==200,response.get_json()
    after=store.load(pid);assert after["manual"]["media_clips"][-1]["track_id"]==row["track_id"]
    assert after["manual"]["layer_tracks"]==before["manual"]["layer_tracks"]
    validate_layer_tracks(after)


def test_legacy_explicit_refuses_without_enabling(unlocked):
    _,_,store,pid=unlocked;raw=store.state_path(pid).read_bytes()
    r=post(unlocked,"media_add",asset_id=VIDEO,start=1,track_id="track_"+"a"*32)
    assert r.status_code==400 and store.state_path(pid).read_bytes()==raw


def test_deleted_target_cannot_fall_back(tracked):
    target=lane(tracked);assert post(tracked,"layer_track_remove",track_id=target).status_code==200
    _,_,store,pid=tracked;raw=store.state_path(pid).read_bytes()
    assert post(tracked,"media_append",asset_id=VIDEO,track_id=target).status_code==400
    assert store.state_path(pid).read_bytes()==raw


@pytest.mark.parametrize("asset,kind",[("asset_"+"e"*32,"audio"),("asset_"+"f"*32,"visual")])
def test_audio_image_explicit_destination(tracked,asset,kind):
    target=lane(tracked,kind)
    r=post(tracked,"media_add",asset_id=asset,start=2,end=3,track_id=target)
    assert r.status_code==200,r.get_json()
    assert tracked[2].load(tracked[3])["manual"]["media_clips"][-1]["track_id"]==target


def test_explicit_lower_lane_not_promoted_above_other_overlaps(tracked):
    target=lane(tracked)
    assert post(tracked,"layer_track_reorder",track_id=target,position="back").status_code==200
    before=tracked[2].load(tracked[3])
    r=post(tracked,"media_add",asset_id=VIDEO,start=4,end=5,track_id=target)
    assert r.status_code==200,r.get_json()
    after=tracked[2].load(tracked[3])
    assert after["manual"]["media_clips"][-1]["track_id"]==target
    assert after["manual"]["layer_tracks"]==before["manual"]["layer_tracks"]


def test_track_id_not_general_media_update_field(tracked):
    target=lane(tracked);_,_,store,pid=tracked;raw=store.state_path(pid).read_bytes()
    clip=store.load(pid)["manual"]["media_clips"][0]
    assert post(tracked,"media_update",clip_id=clip["id"],track_id=target).status_code==400
    assert store.state_path(pid).read_bytes()==raw
