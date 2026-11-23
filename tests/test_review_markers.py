"""Persistent, frame-based edit notes must never become media or undo actions."""
import copy
import hashlib
import json
import threading

import pytest

from cutroom.config import load_settings
from cutroom.review_markers import apply_marker, saved_rows, MarkerError
from cutroom.render import _render_input_fingerprint, render_project
from cutroom.jobs import Job, JobContext
from server import create_app
from test_media_render import media
from test_track_destination_render import prepared


def add(frame=20,fps=30):
    return dict(action="add",expected_revision=1,frame=frame,fps=fps,label="Check cut",note="Review the speaker",color="teal")


def project():
    return {"id":"project_112233445566","revision":1,"sources":{"A":{"duration":8.,"width":160,"height":90,"has_audio":True}},
            "settings":{"fps":30},"manual":{},"assets":{},"draft":{"output_duration":2.,
            "keep_ranges":[{"start":0.,"end":1.},{"start":5.,"end":6.}],"camera_plan":[{"start":0.,"end":8.,"camera":"A"}]}}


def test_times_are_edit_frames_not_recording_time_and_notes_sort_without_mutating_edits():
    p=project();before=copy.deepcopy(p)
    for f in (59,0,30):
        apply_marker(p,add(f))
    assert [r["frame"] for r in saved_rows(p)]==[0,30,59]
    assert len(set(r["id"] for r in saved_rows(p)))==3
    assert {k:p[k] for k in before}==before
    with pytest.raises(MarkerError):apply_marker(p,add(60))
    with pytest.raises(MarkerError):apply_marker(p,add(200))


@pytest.mark.parametrize("patch", [{"frame":True},{"frame":-1},{"frame":"7"},{"frame":.5},{"fps":29.97},{"fps":25},
    {"label":""},{"label":"a"*81},{"label":"a\nb"},{"label":42},{"note":"a"*321},{"note":"x\x00z"},{"color":"unknown"},
    {"color":["teal"]},{"action":"scan"},{"action":{}},{"unexpected":4}])
def test_invalid_or_unreviewed_input_never_creates_a_collection(patch):
    p=project()
    with pytest.raises(MarkerError):apply_marker(p,{**add(),**patch})
    assert "review_markers" not in p


@pytest.mark.parametrize("value",[None,[],{"version":2,"items":[]},{"version":True,"items":[]},
    {"version":1,"items":[{}]},{"version":1,"items":[],"new_feature":1}])
def test_unknown_saved_formats_fail_closed_without_data_loss(value):
    p=project();p["review_markers"]=copy.deepcopy(value)
    with pytest.raises(MarkerError) as err:apply_marker(p,add())
    assert err.value.status==409 and p["review_markers"]==value


def test_strict_capacity_exact_identity_and_reversible_note_actions():
    p=project();apply_marker(p,add());m=saved_rows(p)[0]
    with pytest.raises(MarkerError):apply_marker(p,{"action":"move","id":m["id"],"frame":20,"fps":30,"expected_revision":1})
    apply_marker(p,{"action":"move","id":m["id"],"frame":3,"fps":30,"expected_revision":1})
    apply_marker(p,{"action":"edit","id":m["id"],"label":"<b>literal</b>","note":"first\nsecond","color":"violet","expected_revision":1})
    row=saved_rows(p)[0];assert row["id"]==m["id"] and row["frame"]==3 and row["label"]=="<b>literal</b>"
    with pytest.raises(MarkerError):apply_marker(p,{"action":"remove","id":"marker_111111111111","expected_revision":1})
    apply_marker(p,{"action":"remove","id":m["id"],"expected_revision":1});assert saved_rows(p)==[]
    p["review_markers"]["items"]=[{**m,"id":f"marker_{i:012x}"} for i in range(200)]
    with pytest.raises(MarkerError,match="200"):apply_marker(p,add())
    apply_marker(p,{"action":"remove","id":"marker_000000000000","expected_revision":1})
    apply_marker(p,add());assert len(saved_rows(p))==200


def test_api_reopen_isolation_stale_replay_fps_and_no_undo_history(media,tmp_path):
    p,store,settings,_,unchanged=prepared(media,tmp_path);app=create_app(settings);c=app.test_client()
    pid=p["id"];other=store.create("Other synthetic project");url=f"/api/projects/{pid}/review-markers"
    initial=store.load(pid);rev=initial["revision"]
    response=c.post(url,json={**add(),"expected_revision":rev});r=response.get_json()
    assert response.status_code==200 and set(r)=={"project_id","previous_revision","revision","review_markers"}
    assert (r["project_id"],r["previous_revision"],r["revision"])==(pid,rev,rev+1)
    for wrong in [None,False,rev-1,rev]:
        reply=c.post(url,json={**add(),"expected_revision":wrong})
        assert reply.status_code in (400,409)
    viewed=c.get(f"/api/projects/{pid}").get_json()["project"]
    assert viewed["review_markers"]==r["review_markers"];m=r["review_markers"]["items"][0]
    assert "review_markers" not in c.get(f"/api/projects/{other['id']}").get_json()["project"]
    for k in ("manual","draft","sources","assets","settings","analysis","exports"):
        assert store.load(pid)[k]==initial[k]
    assert _render_input_fingerprint(store.load(pid))==_render_input_fingerprint(initial)
    updated=store.update(pid,lambda c:c["settings"].update(fps=60))
    assert saved_rows(updated)[0]==m
    rejected=c.post(url,json={**add(),"fps":30,"expected_revision":updated["revision"]})
    assert rejected.status_code==409 and saved_rows(store.load(pid))[0]==m
    unchanged()


def test_shortened_edit_keeps_out_of_bounds_notes_until_explicitly_moved_or_removed():
    p=project();apply_marker(p,add(50));row=copy.deepcopy(saved_rows(p)[0]);p["draft"]["keep_ranges"]=[{"start":0.,"end":1.}]
    assert saved_rows(p)==[row]
    apply_marker(p,{"action":"move","frame":5,"fps":30,"id":row["id"],"expected_revision":1})
    assert saved_rows(p)[0]["id"]==row["id"] and saved_rows(p)[0]["frame"]==5


def test_saved_sequence_marker_does_not_rebuild_the_whole_editor_projection(media,tmp_path,monkeypatch):
    import cutroom.review_markers as markers
    from cutroom.sequence import materialize_sequence
    p,_,_,_,unchanged=prepared(media,tmp_path)
    effective,duration=materialize_sequence(p)
    monkeypatch.setattr(markers,"editor_sequence_snapshot",lambda *_:pytest.fail("should use the saved sequence clock"))
    apply_marker(effective,add(int(duration*30)-1))
    assert saved_rows(effective)[0]["frame"]==int(duration*30)-1
    unchanged()


def test_actual_whole_mp4_and_srt_unchanged_by_marker_only_commits(media,tmp_path):
    p,store,settings,_,unchanged=prepared(media,tmp_path);settings.raw["ffmpeg_threads"]=2;pid=p["id"]
    def digest():
        r=render_project(JobContext(Job("no-marker-burn","render",pid),threading.Lock()),pid,store,settings,
            {"quality":"fast","_force_software":True})["export"];f=settings.exports_dir/r["name"]
        return [hashlib.sha256(x.read_bytes()).hexdigest() for x in (f,f.with_suffix(".srt"))]
    before=store.load(pid);original=digest()
    for f in (0,22,89):
        touched=store.update(pid,lambda p:apply_marker(p,add(f)))
    assert [r["frame"] for r in saved_rows(touched)]==[0,22,89]
    assert digest()==original
    for k in ("sources","assets","manual","draft","analysis","settings"):assert before[k]==store.load(pid)[k]
    unchanged()
    print(json.dumps({"mp4_sha256":original[0],"srt_sha256":original[1],"marker_count":3}))


def test_save_a_copy_contains_independent_markers(media,tmp_path):
    from test_project_copy import start,wait
    p,store,settings,_,unchanged=prepared(media,tmp_path);pid=p["id"]
    original=store.update(pid,lambda p:apply_marker(p,add()))["review_markers"]
    app=create_app(settings);client=app.test_client()
    token,_=start((app,client,store,pid));done=wait(client,token)
    assert done["status"]=="completed",done
    other=done["copy_project_id"];duplicate=store.load(other)
    assert original==duplicate["review_markers"]
    r=client.post(f"/api/projects/{other}/review-markers",json={"action":"remove",
        "id":original["items"][0]["id"],"expected_revision":duplicate["revision"]})
    assert r.status_code==200 and r.get_json()["review_markers"]["items"]==[]
    assert store.load(pid)["review_markers"]==original
    unchanged()
