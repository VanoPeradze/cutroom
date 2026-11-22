import copy
import pytest
import server
from test_layer_tracks import tracked, unlocked
from test_media_append import library_api
from test_mixed_media_insert import post
from cutroom.retained_edit import retained_edit_status, resume_retained_edit
from cutroom.projects import ProjectStore

@pytest.fixture
def retained(tracked):
    app,client,store,pid=tracked
    def reset(p):
        p["sources"]["A"]["preparation"]="ready"
        p["analysis"]=None;p["draft"]=None
        server._reset_manual_after_source_change(p,"B",replacing=True)
    store.update(pid,reset)
    return tracked

def call(api,revision=None):
    _,client,store,pid=api
    return client.post(f"/api/projects/{pid}/retained-edit/resume",json={"expected_revision":store.load(pid)["revision"] if revision is None else revision})

def test_resume_exact_preservation_readonly_status_next_edit_undo(retained):
    app,client,store,pid=retained;before=store.load(pid);raw=store.state_path(pid).read_bytes()
    status=client.get(f"/api/projects/{pid}").get_json()["project"]["retained_edit"]
    assert status["available"],status
    assert store.state_path(pid).read_bytes()==raw
    response=call(retained);assert response.status_code==200,response.get_json()
    after=store.load(pid)
    for key in ("manual","settings","sources","assets","analysis"):assert after[key]==before[key]
    assert after["draft"]["output_duration"]==before["manual"]["sequence"]["duration"]
    assert after["draft"]["keep_ranges"]==[{"start":0,"end":before["sources"]["A"]["duration"]}]
    assert "audio_policy" not in after["draft"] and after["analysis"] is None
    assert retained_edit_status(after) is None
    assert ProjectStore(app.extensions["cutroom_settings"]).load(pid)==after
    raw=store.state_path(pid).read_bytes();assert call(retained,before["revision"]).status_code==409;assert store.state_path(pid).read_bytes()==raw
    assert post(retained,"layer_track_add",kind="visual",name="Next edit").status_code==200
    assert post(retained,"undo").status_code==200
    undone=store.load(pid)
    for key in ("sequence","source_tracks","layer_tracks","media_clips","text_clips"):assert undone["manual"][key]==before["manual"][key]

@pytest.mark.parametrize("fault",["future","missing","bad_camera","gap","nonempty_b","bad_source","orphan","bad_duration"])
def test_invalid_status_and_resume_no_mutation(retained,fault):
    _,client,store,pid=retained;p=store.load(pid)
    if fault=="future":p["manual"]["sequence"]["version"]=9
    elif fault=="missing":p["manual"].pop("sequence")
    elif fault=="bad_camera":p["manual"]["sequence"]["camera_plan"][0]["camera"]="wrong"
    elif fault=="gap":p["manual"]["sequence"]["camera_plan"][0]["start"]=.2
    elif fault=="nonempty_b":p["manual"]["source_tracks"]["B"]=copy.deepcopy(p["manual"]["source_tracks"]["A"])
    elif fault=="bad_source":p["sources"]["A"]["preparation"]="failed"
    elif fault=="orphan":p["manual"].pop("layer_tracks")
    else:p["manual"]["sequence"]["duration"]=float("nan")
    import json
    store.state_path(pid).write_text(json.dumps(p),encoding="utf8");raw=store.state_path(pid).read_bytes()
    status=retained_edit_status(p);assert status and not status["available"] and status["issue"]
    response=call(retained);assert response.status_code in (400,409),response.get_json()
    assert store.state_path(pid).read_bytes()==raw

@pytest.mark.parametrize("endpoint",["manual-draft","director","director/refine"])
def test_bypass_refused_without_provider_or_job(retained,monkeypatch,endpoint):
    app,client,store,pid=retained;raw=store.state_path(pid).read_bytes()
    def forbidden(*args,**kwargs):pytest.fail("Resume bypass reached work")
    monkeypatch.setattr(app.extensions["cutroom_jobs"],"submit",forbidden)
    monkeypatch.setattr(app.extensions["cutroom_connections"],"job_settings",forbidden)
    monkeypatch.setattr(server,"story_ai_status",forbidden)
    payload={"expected_revision":store.load(pid)["revision"]} if endpoint=="manual-draft" else {"command":"shorter"} if endpoint.endswith("refine") else {}
    r=client.post(f"/api/projects/{pid}/{endpoint}",json=payload)
    assert r.status_code in (400,409),r.get_json();assert store.state_path(pid).read_bytes()==raw


def test_busy_and_bad_revision(retained,monkeypatch):
    app,_,store,pid=retained;raw=store.state_path(pid).read_bytes()
    assert call(retained,True).status_code==400
    monkeypatch.setattr(app.extensions["cutroom_jobs"],"active",lambda **kw:[object()])
    assert call(retained).status_code==409 and store.state_path(pid).read_bytes()==raw
    monkeypatch.undo()


def test_empty_zero_sequence_is_not_expanded(retained):
    _,_,store,pid=retained;p=store.load(pid)
    p["manual"]["sequence"].update(duration=0,camera_plan=[])
    p["manual"]["source_tracks"]={"A":[],"B":[]}
    p["manual"]["media_clips"]=[];p["manual"]["text_clips"]=[]
    before=copy.deepcopy(p["manual"]);resume_retained_edit(p)
    assert p["draft"]["output_duration"]==0 and p["manual"]==before


def test_reset_uses_original_source_ranges_not_edit_duration(retained):
    _,_,store,pid=retained;assert call(retained).status_code==200
    before=store.load(pid);r=post(retained,"sequence_reset")
    assert r.status_code==200,r.get_json()
    after=store.load(pid)
    assert after["draft"]["keep_ranges"]==[{"start":0,"end":before["sources"]["A"]["duration"]}]


def test_fresh_project_status_and_manual_initialization_unaffected(unlocked):
    _,_,store,pid=unlocked;p=store.load(pid);p["manual"]={};p["draft"]=None
    from cutroom.manual_start import start_manual_draft
    assert retained_edit_status(p) is None
    start_manual_draft(p);assert p["draft"]["output_duration"]==p["sources"]["A"]["duration"]



def test_reset_after_resume_cannot_truncate_long_retained_layers(tracked):
    from test_mixed_media_insert import VIDEO
    app,client,store,pid=tracked
    assert post(tracked,"media_append",asset_id=VIDEO,source_start=0,source_end=10).status_code==200
    def reset(p):
        p["sources"]["A"]["preparation"]="ready"
        p["draft"]=None;p["analysis"]=None
        server._reset_manual_after_source_change(p,"B",replacing=True)
    store.update(pid,reset);before=store.load(pid)
    assert before["manual"]["sequence"]["duration"]>before["sources"]["A"]["duration"]
    assert call(tracked).status_code==200
    raw=store.state_path(pid).read_bytes()
    r=post(tracked,"sequence_reset")
    assert r.status_code==400,r.get_json()
    assert store.state_path(pid).read_bytes()==raw

@pytest.mark.parametrize("evidence",[{"cuts":[{"start":1,"end":2}]},{"keeps":[{"start":1,"end":2}]},{"source_tracks":{"A":[]}},{"layer_tracks":{"version":1,"tracks":[]}}])
def test_retained_evidence_blocks_fresh_start_without_guessing(unlocked,evidence):
    from cutroom.manual_start import start_manual_draft
    from cutroom.editing import ManualEditError
    p=unlocked[2].load(unlocked[3]);p["draft"]=None;p["manual"]=evidence;before=copy.deepcopy(p)
    status=retained_edit_status(p);assert status and not status["available"]
    with pytest.raises(ManualEditError):start_manual_draft(p)
    assert p==before


@pytest.mark.parametrize("fault",["duplicate","unknown_kind","missing_id"])
def test_untracked_retained_layers_still_validate_identity(retained,fault):
    p=retained[2].load(retained[3]);p["manual"].pop("layer_tracks")
    for key in ("media_clips","text_clips"):
        for row in p["manual"][key]:row.pop("track_id",None)
    if fault=="duplicate":p["manual"]["media_clips"].append(copy.deepcopy(p["manual"]["media_clips"][0]))
    elif fault=="missing_id":p["manual"]["media_clips"][0].pop("id")
    else:p["assets"][p["manual"]["media_clips"][0]["asset_id"]]["kind"]="unknown"
    status=retained_edit_status(p);assert not status["available"] and status["issue"]



def test_retained_manual_mutations_block_but_name_settings_remain_available(retained):
    _,client,store,pid=retained;raw=store.state_path(pid).read_bytes()
    r=post(retained,"set_source_mixer",audio_slot="A",screen_slot="A",camera_slot="B")
    assert r.status_code==409 and r.get_json()["error"]=="retained_edit_requires_resume"
    assert store.state_path(pid).read_bytes()==raw
    r=client.patch(f"/api/projects/{pid}",json={"manual":{"crop":{"A":{"x":.5,"y":.5,"zoom":1}}}})
    assert r.status_code==409 and store.state_path(pid).read_bytes()==raw
    before=store.load(pid)
    r=client.patch(f"/api/projects/{pid}",json={"name":"Retained renamed","settings":{"fps":24}})
    assert r.status_code==200,r.get_json()
    assert store.load(pid)["manual"]==before["manual"] and store.load(pid)["draft"] is None


@pytest.mark.parametrize("fault",["source_missing","asset_missing","source_escape","asset_escape"])
def test_http_original_availability_and_containment(retained,fault,tmp_path):
    app,client,store,pid=retained;p=store.load(pid);root=store.project_dir(pid)
    if fault=="source_missing":(root/p["sources"]["A"]["relative_path"]).unlink()
    elif fault=="asset_missing":(root/p["assets"][p["manual"]["media_clips"][0]["asset_id"]]["path"]).unlink()
    else:
        outside=tmp_path/"outside.mp4";outside.write_bytes(b"must not read")
        if fault=="source_escape":p["sources"]["A"]["relative_path"]=str(outside)
        else:p["assets"][p["manual"]["media_clips"][0]["asset_id"]]["path"]=str(outside)
        import json
        store.state_path(pid).write_text(json.dumps(p),encoding="utf8")
    raw=store.state_path(pid).read_bytes()
    public=client.get(f"/api/projects/{pid}")
    if public.status_code==409:
        # Existing ProjectStore rejects unsafe paths even before public projection.
        assert fault.endswith("escape")
        response=client.post(f"/api/projects/{pid}/retained-edit/resume",json={"expected_revision":p["revision"]})
        assert response.status_code==409
        assert not retained_edit_status(p,root)["available"]
    else:
        assert public.status_code==200
        status=public.get_json()["project"]["retained_edit"]
        assert not status["available"] and status["issue"]
        assert call(retained).status_code==400
    assert store.state_path(pid).read_bytes()==raw


@pytest.mark.parametrize("state",["retained","future","fresh","ready","zero"])
def test_project_summary_reports_saved_evidence_without_activation(retained,state):
    import json
    app,client,store,pid=retained;p=store.load(pid)
    if state=="future":p["manual"]["sequence"]["version"]=7
    elif state=="fresh":p["manual"]={}
    elif state=="ready":resume_retained_edit(p)
    elif state=="zero":p["manual"]["sequence"]["duration"]=0
    store.state_path(pid).write_text(json.dumps(p),encoding="utf8");raw=store.state_path(pid).read_bytes()
    response=client.get("/api/projects");assert response.status_code==200
    summary=next(row for row in response.get_json()["projects"] if row["id"]==pid)
    assert summary["has_retained_edit"]==(state not in {"fresh","ready"})
    assert summary["retained_duration"]==(0 if state=="zero" else p["manual"]["sequence"]["duration"] if state=="retained" else None)
    assert summary["has_draft"]==(state=="ready")
    assert store.state_path(pid).read_bytes()==raw


@pytest.mark.parametrize("state",["valid","missing_metadata","not_ready","missing_file","unsafe_path","disabled","unused"])
def test_retained_chroma_dependency_matches_render_inventory(retained,state):
    from cutroom.composition import CHROMA_KEY_DEFAULTS
    import json
    app,client,store,pid=retained;p=store.load(pid);root=store.project_dir(pid)
    aid="asset_"+"9"*32;relative=f"media/assets/{aid}/background.png"
    p["assets"][aid]={"id":aid,"kind":"image","status":"ready","width":100,"height":100,"path":relative}
    target="A"
    if state=="unused":
        target="asset_"+"8"*32
        p["assets"][target]={**p["assets"][p["manual"]["media_clips"][0]["asset_id"]],"id":target,"path":f"media/assets/{target}/original.mp4"}
    p["manual"]["chroma_key"]={target:{**CHROMA_KEY_DEFAULTS,"enabled":state!="disabled","background_asset_id":aid}}
    path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b"synthetic background")
    if state in {"missing_metadata","disabled","unused"}:p["assets"].pop(aid)
    elif state=="not_ready":p["assets"][aid]["status"]="failed"
    elif state=="missing_file":path.unlink()
    elif state=="unsafe_path":p["assets"][aid]["path"]="../outside.png"
    store.state_path(pid).write_text(json.dumps(p),encoding="utf8");raw=store.state_path(pid).read_bytes()
    allowed=state in {"valid","disabled","unused"}
    status=retained_edit_status(p,root);assert status["available"]==allowed,status
    before=copy.deepcopy(p)
    if allowed:
        resume_retained_edit(p,root)
        for key in ("manual","settings","analysis","sources","assets"):assert p[key]==before[key]
    else:
        with pytest.raises(ValueError):resume_retained_edit(p,root)
        assert p==before
    assert store.state_path(pid).read_bytes()==raw
