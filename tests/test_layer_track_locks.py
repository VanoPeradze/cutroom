import copy
import io
import pytest
import server
from test_layer_tracks import tracked, unlocked
from test_media_append import library_api, content
from test_mixed_media_insert import post, VIDEO
from cutroom.layer_tracks import validate_layer_tracks, layer_tracks_render_identity, validate_locked_layer_changes
from cutroom.projects import ProjectStore


def lock(api,identity=None,locked=True):
    p=api[2].load(api[3]);identity=identity or p["manual"]["media_clips"][1]["track_id"]
    return post(api,"layer_track_lock",track_id=identity,locked=locked)

@pytest.fixture
def protected(tracked):
    assert lock(tracked).status_code==200
    return tracked


def test_upgrade_toggle_no_history_no_render_change(tracked):
    app,client,store,pid=tracked;before=store.load(pid);raw=store.state_path(pid).read_bytes()
    assert lock(tracked,locked=False).status_code==200 and store.state_path(pid).read_bytes()==raw
    assert lock(tracked).status_code==200;after=store.load(pid)
    assert after["manual"]["layer_tracks"]["version"]==2
    assert all(type(t["locked"]) is bool for t in after["manual"]["layer_tracks"]["tracks"])
    assert after["manual"]["_history"]==before["manual"]["_history"]
    assert layer_tracks_render_identity(after)==layer_tracks_render_identity(before)
    assert lock(tracked,locked=False).status_code==200
    assert store.load(pid)["manual"]["layer_tracks"]["version"]==2
    assert ProjectStore(app.extensions["cutroom_settings"]).load(pid)==store.load(pid)

@pytest.mark.parametrize("value",[None,0,1,"true",[],{}])
def test_lock_requires_boolean(tracked,value):
    raw=tracked[2].state_path(tracked[3]).read_bytes();assert lock(tracked,locked=value).status_code==400
    assert tracked[2].state_path(tracked[3]).read_bytes()==raw

@pytest.mark.parametrize("action,extra",[
 ("media_remove",{}),("media_move",{"start":5}),("media_split",{"time":5}),
 ("media_trim",{"edge":"start","time":5}),("media_slip",{"source_start":2}),
 ("media_update",{"volume_db":-9}),("media_set_enabled",{"enabled":False}),
 ("media_transform",{"x":.2,"y":.2,"w":.5,"h":.5})])
def test_protected_occurrence_edits_atomic(protected,action,extra):
    _,_,store,pid=protected;p=store.load(pid);row=p["manual"]["media_clips"][1];raw=store.state_path(pid).read_bytes()
    r=post(protected,action,clip_id=row["id"],**extra)
    assert r.status_code==400,r.get_json();assert store.state_path(pid).read_bytes()==raw


def test_duplicate_reads_locked_original_automatic_avoids_locked(protected):
    _,_,store,pid=protected;p=store.load(pid);row=p["manual"]["media_clips"][1]
    r=post(protected,"media_duplicate",clip_id=row["id"],start=10);assert r.status_code==200,r.get_json()
    after=store.load(pid);assert after["manual"]["media_clips"][-1]["track_id"]!=row["track_id"]
    assert next(c for c in after["manual"]["media_clips"] if c["id"]==row["id"])==row
    raw=store.state_path(pid).read_bytes()
    assert post(protected,"media_add",asset_id=VIDEO,start=10,end=11,track_id=row["track_id"]).status_code==400
    assert store.state_path(pid).read_bytes()==raw


def test_order_cannot_cross_locked_rename_allowed(protected):
    _,_,store,pid=protected;p=store.load(pid);locked=p["manual"]["media_clips"][1]["track_id"]
    assert post(protected,"layer_track_rename",track_id=locked,name="Protected picture").status_code==200
    raw=store.state_path(pid).read_bytes()
    assert post(protected,"layer_track_reorder",track_id=locked,position="front").status_code==400
    assert store.state_path(pid).read_bytes()==raw


def test_history_retains_current_flags_and_redo(tracked):
    _,_,store,pid=tracked
    assert post(tracked,"layer_track_add",kind="visual",name="History lane").status_code==200
    assert post(tracked,"undo").status_code==200
    history=copy.deepcopy(store.load(pid)["manual"]["_history"])
    assert lock(tracked).status_code==200
    assert store.load(pid)["manual"]["_history"]==history
    assert post(tracked,"redo").status_code==200
    p=store.load(pid);assert p["manual"]["layer_tracks"]["tracks"][-1]["locked"] is False
    assert any(t["locked"] for t in p["manual"]["layer_tracks"]["tracks"])
    assert post(tracked,"undo").status_code==200
    raw=store.state_path(pid).read_bytes();assert post(tracked,"undo").status_code==400
    assert store.state_path(pid).read_bytes()==raw
    assert lock(tracked,locked=False).status_code==200
    assert post(tracked,"undo").status_code==200
    assert "layer_tracks" not in store.load(pid)["manual"]
    assert post(tracked,"redo").status_code==200
    assert not any(t.get("locked",False) for t in store.load(pid)["manual"]["layer_tracks"]["tracks"])


def test_old_content_undo_refuses_without_consuming_history(tracked):
    _,_,store,pid=tracked;p=store.load(pid);row=p["manual"]["media_clips"][1]
    assert post(tracked,"media_update",clip_id=row["id"],volume_db=-9).status_code==200
    assert lock(tracked).status_code==200;raw=store.state_path(pid).read_bytes()
    assert post(tracked,"undo").status_code==400 and store.state_path(pid).read_bytes()==raw
    assert lock(tracked,locked=False).status_code==200
    assert post(tracked,"undo").status_code==200
    assert store.load(pid)["manual"]["layer_tracks"]["version"]==2
    assert all(not t["locked"] for t in store.load(pid)["manual"]["layer_tracks"]["tracks"])

@pytest.mark.parametrize("field,value",[("path","media/assets/changed.mp4"),("duration",19),("_stabilization",{"changed":True})])
def test_store_protects_asset_identity(protected,field,value):
    _,_,store,pid=protected;p=store.load(pid);aid=p["manual"]["media_clips"][1]["asset_id"];raw=store.state_path(pid).read_bytes()
    with pytest.raises(ValueError):store.update(pid,lambda p:p["assets"][aid].update({field:value}))
    assert store.state_path(pid).read_bytes()==raw


def test_preparation_metadata_and_global_settings_allowed(protected):
    _,_,store,pid=protected;p=store.load(pid);aid=p["manual"]["media_clips"][1]["asset_id"]
    store.update(pid,lambda p:p["assets"][aid].update(status="ready",waveform=[.1],preview_path="media/assets/proxy.mp4"))
    store.patch(pid,{"settings":{"fps":24},"name":"Allowed rename"})
    validate_layer_tracks(store.load(pid))


def test_asset_chroma_protected_at_store_boundary(protected):
    _,_,store,pid=protected;p=store.load(pid);aid=p["manual"]["media_clips"][1]["asset_id"];raw=store.state_path(pid).read_bytes()
    with pytest.raises(ValueError):store.update(pid,lambda p:p["manual"].update(chroma_key={aid:{"enabled":True}}))
    assert store.state_path(pid).read_bytes()==raw

@pytest.mark.parametrize("operation",["replace","remove"])
def test_source_a_preflight_preserves_files(protected,monkeypatch,operation):
    app,client,store,pid=protected
    from test_backend_hardening import _probe,_QueuedJob
    monkeypatch.setattr(server,"probe_media",_probe)
    monkeypatch.setattr(app.extensions["cutroom_jobs"],"submit",lambda *a,**kw:_QueuedJob())
    before={str(p):p.read_bytes() for p in store.project_dir(pid).rglob('*') if p.is_file()}
    r=client.delete(f"/api/projects/{pid}/sources/A") if operation=="remove" else client.post(f"/api/projects/{pid}/sources/A",data={"file":(io.BytesIO(b"replacement"),"new.mp4")},content_type="multipart/form-data")
    assert r.status_code==409,r.get_json()
    assert {str(p):p.read_bytes() for p in store.project_dir(pid).rglob('*') if p.is_file()}==before


def test_middle_all_layer_ripple_refuses_tail_can_extend(protected):
    _,_,store,pid=protected;raw=store.state_path(pid).read_bytes()
    r=post(protected,"sequence_insert_all",slot="A",start=5,source_start=0,source_end=1)
    assert r.status_code==400 and store.state_path(pid).read_bytes()==raw
    r=post(protected,"sequence_insert_all",slot="A",start=15,source_start=0,source_end=1)
    assert r.status_code==200,r.get_json()


@pytest.mark.parametrize("fault",["missing","integer","unknown","future"])
def test_v2_strict_schema(protected,fault):
    p=protected[2].load(protected[3])
    if fault=="missing":p["manual"]["layer_tracks"]["tracks"][0].pop("locked")
    elif fault=="integer":p["manual"]["layer_tracks"]["tracks"][0]["locked"]=1
    elif fault=="unknown":p["manual"]["layer_tracks"]["tracks"][0]["mute"]=False
    else:p["manual"]["layer_tracks"]["version"]=3
    with pytest.raises(ValueError):validate_layer_tracks(p)


def test_toggle_stale_and_busy_atomic(tracked,monkeypatch):
    app,client,store,pid=tracked;p=store.load(pid);target=p["manual"]["media_clips"][1]["track_id"]
    assert lock(tracked).status_code==200;raw=store.state_path(pid).read_bytes()
    r=client.post(f"/api/projects/{pid}/manual/edit",json={"action":"layer_track_lock","track_id":target,"locked":False,"expected_revision":p["revision"]})
    assert r.status_code==409 and store.state_path(pid).read_bytes()==raw
    with monkeypatch.context() as m:
        m.setattr(app.extensions["cutroom_jobs"],"active",lambda **kw:[object()])
        assert lock(tracked,locked=False).status_code==409
    assert store.state_path(pid).read_bytes()==raw


def test_empty_locked_lane_cannot_remove_or_accept_member(tracked):
    _,_,store,pid=tracked
    assert post(tracked,"layer_track_add",kind="audio",name="Protected empty").status_code==200
    lane=store.load(pid)["manual"]["layer_tracks"]["tracks"][-1]["id"]
    assert lock(tracked,lane).status_code==200;raw=store.state_path(pid).read_bytes()
    assert post(tracked,"layer_track_remove",track_id=lane).status_code==400
    assert store.state_path(pid).read_bytes()==raw


def test_text_lock_blocks_bulk_removal_and_member_edit(tracked):
    _,_,store,pid=tracked;p=store.load(pid);row=p["manual"]["text_clips"][1]
    assert lock(tracked,row["track_id"]).status_code==200;raw=store.state_path(pid).read_bytes()
    for action,fields in [("text_update",{"clip_id":row["id"],"text":"changed"}),("text_remove",{"clip_id":row["id"]}),("layers_remove",{"clip_ids":[row["id"],p["manual"]["media_clips"][0]["id"]]})]:
        r=post(tracked,action,**fields);assert r.status_code==400,r.get_json()
        assert store.state_path(pid).read_bytes()==raw


def test_store_cannot_unlock_and_change_in_one_write(protected):
    _,_,store,pid=protected;raw=store.state_path(pid).read_bytes()
    def bypass(p):
        for t in p["manual"]["layer_tracks"]["tracks"]:t["locked"]=False
        p["manual"]["media_clips"][1]["volume_db"]=-12
    with pytest.raises(ValueError):store.update(pid,bypass)
    assert store.state_path(pid).read_bytes()==raw


def test_preparation_cache_binding_refresh_is_allowed(protected):
    _,_,store,pid=protected;p=store.load(pid);aid=p["manual"]["media_clips"][1]["asset_id"]
    store.update(pid,lambda p:p["assets"][aid].update(preparation_identity="new-key",preparation_pipeline=2,preview_mode="prepared",thumbnail_path="media/assets/cache.jpg"))


def test_stabilized_retry_rejected_before_job(protected,monkeypatch):
    app,client,store,pid=protected;p=store.load(pid);aid=p["manual"]["media_clips"][1]["asset_id"]
    # Seed descriptor before protection, then re-enable the same lock.
    assert lock(protected,locked=False).status_code==200
    store.update(pid,lambda p:p["assets"][aid].update(status="failed",_stabilization={"slot":"A"}))
    assert lock(protected).status_code==200;raw=store.state_path(pid).read_bytes()
    def forbidden(*a,**kw):pytest.fail("Locked asset reached regeneration")
    monkeypatch.setattr(server,"stabilization_capability",forbidden)
    monkeypatch.setattr(app.extensions["cutroom_jobs"],"submit",forbidden)
    r=client.post(f"/api/projects/{pid}/assets/{aid}/prepare")
    assert r.status_code==409,r.get_json();assert store.state_path(pid).read_bytes()==raw


def test_b_reset_preserves_locked_layers(protected):
    _,client,store,pid=protected;before=store.load(pid)
    r=client.delete(f"/api/projects/{pid}/sources/B");assert r.status_code==200,r.get_json()
    after=store.load(pid)
    for key in ("layer_tracks","media_clips","text_clips"):assert after["manual"][key]==before["manual"][key]



def test_background_dependency_protected_even_when_video_offline(tracked):
    from cutroom.composition import CHROMA_KEY_DEFAULTS
    _,_,store,pid=tracked;p=store.load(pid);aid=p["manual"]["media_clips"][1]["asset_id"];bg="asset_"+"7"*32
    def setup(p):
        p["assets"][bg]={"id":bg,"kind":"image","status":"ready","path":f"media/assets/{bg}/original.png","width":20,"height":20}
        p["manual"]["chroma_key"]={aid:{**CHROMA_KEY_DEFAULTS,"enabled":True,"background_asset_id":bg}}
    store.update(pid,setup);assert lock(tracked).status_code==200
    store.update(pid,lambda p:p["assets"][aid].update(status="failed"));raw=store.state_path(pid).read_bytes()
    with pytest.raises(ValueError):store.update(pid,lambda p:p["assets"][bg].update(width=30))
    assert store.state_path(pid).read_bytes()==raw


def test_empty_locked_automatic_destination_skipped(tracked):
    _,_,store,pid=tracked
    assert post(tracked,"layer_track_add",kind="visual",name="Protected empty").status_code==200
    target=store.load(pid)["manual"]["layer_tracks"]["tracks"][-1]["id"]
    assert lock(tracked,target).status_code==200
    assert post(tracked,"media_add",asset_id=VIDEO,start=10,end=11).status_code==200
    assert store.load(pid)["manual"]["media_clips"][-1]["track_id"]!=target


def test_unlocked_v2_cannot_downgrade_by_store_write(protected):
    _,_,store,pid=protected;assert lock(protected,locked=False).status_code==200
    raw=store.state_path(pid).read_bytes()
    def downgrade(p):
        p["manual"]["layer_tracks"]["version"]=1
        for t in p["manual"]["layer_tracks"]["tracks"]:t.pop("locked")
    with pytest.raises(ValueError):store.update(pid,downgrade)
    assert store.state_path(pid).read_bytes()==raw

from test_ai_draft_review import api as ai_api, base_api, review as ai_review, apply as ai_apply, post as ai_post

def test_ai_apply_and_undo_keep_current_independent_lock(ai_api):
    _,_,store,pid,_=ai_api
    store.update(pid,lambda p:p["settings"].update(captions=False,burn_captions=False))
    assert ai_post(ai_api,"text_add",kind="title",start=1,end=2,text="Protected title").status_code==200
    assert ai_post(ai_api,"layer_tracks_enable").status_code==200
    target=store.load(pid)["manual"]["text_clips"][0]["track_id"]
    assert ai_post(ai_api,"layer_track_lock",track_id=target,locked=True).status_code==200
    before=store.load(pid);proposal=ai_review(ai_api).get_json()["proposal"]
    r=ai_apply(ai_api,proposal);assert r.status_code==200,r.get_json()
    after=store.load(pid)
    for key in ("layer_tracks","text_clips"):assert after["manual"][key]==before["manual"][key]
    assert ai_post(ai_api,"undo").status_code==200
    for key in ("layer_tracks","text_clips"):assert store.load(pid)["manual"][key]==before["manual"][key]



def test_future_history_model_not_silently_rewritten_to_v2(protected):
    _,_,store,pid=protected
    assert post(protected,"layer_track_add",kind="audio",name="History").status_code==200
    def corrupt(p):p["manual"]["_history"]["undo"][-1]["before"]["manual_layer_tracks"]["version"]=3
    store.update(pid,corrupt);raw=store.state_path(pid).read_bytes()
    assert post(protected,"undo").status_code==400
    assert store.state_path(pid).read_bytes()==raw



def test_source_a_postcommit_rollback_refuses_new_locked_edit(tracked,monkeypatch):
    app,client,store,pid=tracked
    from test_backend_hardening import _probe,_QueuedJob
    monkeypatch.setattr(server,"probe_media",_probe)
    monkeypatch.setattr(app.extensions["cutroom_jobs"],"submit",lambda *a,**kw:_QueuedJob())
    r=client.post(f"/api/projects/{pid}/sources/A",data={"file":(io.BytesIO(b"new source generation"),"new.mp4")},content_type="multipart/form-data")
    assert r.status_code==201,r.get_json();token=r.get_json()["upload_token"]
    def prepare(p):p["sources"]["A"]["preparation"]="ready"
    store.update(pid,prepare)
    r=client.post(f"/api/projects/{pid}/manual-draft",json={"expected_revision":store.load(pid)["revision"]})
    assert r.status_code==200,r.get_json()
    assert post(tracked,"media_add",asset_id=VIDEO,start=1,end=2).status_code==200
    assert post(tracked,"layer_tracks_enable").status_code==200
    target=store.load(pid)["manual"]["media_clips"][0]["track_id"]
    assert lock(tracked,target).status_code==200
    before={str(p):p.read_bytes() for p in store.project_dir(pid).rglob('*') if p.is_file()}
    r=client.post(f"/api/projects/{pid}/sources/A/uploads/{token}/cancel")
    assert r.status_code==409,r.get_json()
    assert {str(p):p.read_bytes() for p in store.project_dir(pid).rglob('*') if p.is_file()}==before
