"""Real production encode of a synthetic reviewed reset, never AI quality evidence."""
import copy
import hashlib
import shutil
import threading
import pytest
from cutroom.ai_draft_proposals import record_ai_draft_proposal, record_isolated_ai_draft
from cutroom.editing import apply_manual_edit
from cutroom.jobs import Job, JobContext
from cutroom.projects import ProjectStore
from cutroom.render import render_project
from cutroom.sequence import editor_sequence_snapshot
from test_ai_draft_review import base_api, review, apply, post
from test_media_render import media, pixel, samples, tone_level


@pytest.mark.parametrize("isolated", [False, True])
def test_reviewed_apply_matches_independent_reset_encode_and_undo(base_api, media, isolated):
    app, _, store, pid, _ = base_api; settings = app.extensions["cutroom_settings"]
    settings.raw["render"].update(prefer_hardware=False,min_free_mb=0)
    root = store.project_dir(pid); source = root/"media/actual-source.mp4"; shutil.copyfile(media[3],source)
    aid = "asset_"+"c"*32; image_path = root/f"media/assets/{aid}/original.png"
    image_path.parent.mkdir(parents=True); shutil.copyfile(media[5],image_path)
    p = store.load(pid)
    p.update(sources={"A":{"duration":3.,"width":160,"height":90,"has_audio":True,"relative_path":"media/actual-source.mp4","generation":"test-only-real-source"},"B":None},
             assets={aid:{"id":aid,"name":"Test image","kind":"image","status":"ready","path":f"media/assets/{aid}/original.png","width":80,"height":80}},
             analysis={"transcript":{"segments":[]}},manual={"cuts":[],"keeps":[],"camera_overrides":[]},
             draft={"engine":"synthetic_ai_review","source_duration":3.,"output_duration":3.,"keep_ranges":[{"start":0.,"end":3.}],"cuts":[],"camera_plan":[{"start":0.,"end":3.,"camera":"A"}],"edit_points":[],"audio_plan":[],"audio_policy":{"normalize":False}})
    p["settings"].update(workflow="manual",aspect="source",resolution="1440",quality="fast",fps=30,burn_captions=False,editorial_effects=False)
    apply_manual_edit(p,{"action":"sequence_split_all","time":1.})
    apply_manual_edit(p,{"action":"media_add","asset_id":aid,"start":.2,"end":1.8,"x":.7,"y":0.,"w":.3,"h":.3})
    apply_manual_edit(p,{"action":"text_add","kind":"title","start":.4,"end":1.6,"text":"Retained title","position":"bottom","scale":75})
    current_render_state = {key:copy.deepcopy(p[key]) for key in ("draft", "analysis")}
    p["draft"].update(title="Synthetic candidate",output_duration=2.,keep_ranges=[{"start":0.,"end":.5},{"start":1.5,"end":3.}],cuts=[{"start":.5,"end":1.5}])
    candidate = copy.deepcopy(p)
    if isolated:
        p.update(copy.deepcopy(current_render_state))
        record_isolated_ai_draft(p, candidate)
    else:
        record_ai_draft_proposal(p)
    store.save(p)
    originals=[source,image_path];hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    def encoded(label):
        record=render_project(JobContext(Job(label,"render",pid),threading.Lock()),pid,store,settings,{"quality":"fast","_force_software":True})["export"]
        return settings.exports_dir/record["name"],record
    original,original_info=encoded("ai-review-current")
    before=store.load(pid)
    def independent_reset(p):
        if isolated:
            p.update({key:copy.deepcopy(candidate[key]) for key in ("draft", "analysis")})
        p["manual"].pop("sequence");p["manual"].pop("source_tracks",None)
    store.update(pid,independent_reset);reference,reference_info=encoded("ai-review-independent-reference")
    store.update(pid,lambda p:p.update({key:copy.deepcopy(before[key]) for key in ("manual", "draft", "analysis")}))
    proposal=review(base_api).get_json()["proposal"]
    assert proposal["current"]["duration"]==3 and proposal["impact"]["duration"]==2
    assert proposal["impact"]["media_preserved"] and proposal["impact"]["text_preserved"]
    response=apply(base_api,proposal);assert response.status_code==200,response.get_json()
    actual,actual_info=encoded("ai-review-applied")
    saved=store.load(pid)
    assert saved["manual"]["media_clips"]==before["manual"]["media_clips"]
    assert saved["manual"]["text_clips"]==before["manual"]["text_clips"]
    assert post(base_api,"undo").status_code==200
    assert editor_sequence_snapshot(store.load(pid))==editor_sequence_snapshot(before)
    if isolated:
        assert store.load(pid)["draft"] == before["draft"]
        assert store.load(pid)["analysis"] == before["analysis"]
    undone,undo_info=encoded("ai-review-undone")
    assert post(base_api,"redo").status_code==200
    assert editor_sequence_snapshot(ProjectStore(settings).load(pid))["duration"]==2
    for expected,info in [(3,original_info),(2,reference_info),(2,actual_info),(3,undo_info)]:assert info["duration"]==pytest.approx(expected,abs=1/30)
    for at in (.2,.4,.8,1.2,1.7):
        for x,y in ((5,5),(80,45),(145,10),(80,75)):
            old,ref,got,undo=[pixel(media[1],p,at,x,y) for p in (original,reference,actual,undone)]
            assert got==pytest.approx(ref,abs=20)
            assert undo==pytest.approx(old,abs=20)
    # Actual retained source content changed: edit .8s moves red->green; 1.7s green->blue.
    assert pixel(media[1],original,.8,5,5)[0]>200 and pixel(media[1],actual,.8,5,5)[1]>200
    assert pixel(media[1],original,1.7,5,5)[1]>200 and pixel(media[1],actual,1.7,5,5)[2]>200
    sound=[samples(media[1],p) for p in (original,reference,actual,undone)]
    for at in (.2,.65,.8,1.2,1.7):
        levels=[tone_level(s,at,440) for s in sound]
        assert levels[1]==pytest.approx(levels[2],abs=.003)
        assert levels[0]==pytest.approx(levels[3],abs=.003)
    assert tone_level(sound[2],.65,440)>.15 and tone_level(sound[0],.65,440)<.003
    assert {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}==hashes
    assert len(store.load(pid)["exports"])==4 and all(p.exists() for p in (original,reference,actual,undone))


def test_actual_director_job_keeps_current_encoded_output_until_apply(base_api, media, monkeypatch):
    from cutroom import director
    app, _, store, pid, _ = base_api
    settings=app.extensions["cutroom_settings"]
    settings.raw["render"].update(prefer_hardware=False,min_free_mb=0)
    root=store.project_dir(pid);source=root/"media/actual-source.mp4";shutil.copyfile(media[3],source)
    p=store.load(pid)
    p.update(sources={"A":{"duration":3.,"width":160,"height":90,"has_audio":True,"relative_path":"media/actual-source.mp4","generation":"production-fixture"},"B":None},
        analysis={"transcript":{"segments":[]}},manual={"cuts":[],"keeps":[],"camera_overrides":[]},
        draft={"engine":"synthetic_current","title":"Current edit","source_duration":3.,"output_duration":3.,"keep_ranges":[{"start":0.,"end":3.}],"cuts":[],"camera_plan":[{"start":0.,"end":3.,"camera":"A"}],"edit_points":[],"audio_plan":[],"audio_policy":{"normalize":False}})
    p["settings"].update(workflow="manual",goal="youtube",aspect="source",resolution="1440",quality="fast",fps=30,burn_captions=False,captions=False,editorial_effects=False,auto_reframe=False)
    apply_manual_edit(p,{"action":"sequence_split_all","time":1.})
    store.save(p)
    monkeypatch.setattr(director,"analyze_audio",lambda *a,**k:{"available":True,"duration":3.,"ranges":{},"summary":{},"waveform":[]})
    monkeypatch.setattr(director,"detect_scenes",lambda *a,**k:[])
    monkeypatch.setattr(director,"analyze_faces_and_embedded_camera",lambda *a,**k:{"available":False,"focus_safe":False})
    monkeypatch.setattr(director,"_transcribe_safely",lambda *a,**k:({"segments":[],"text":"","words":[],"duration":3.},None))
    def encode(label):
        record=render_project(JobContext(Job(label,"render",pid),threading.Lock()),pid,store,settings,{"quality":"fast","_force_software":True})["export"]
        return settings.exports_dir/record["name"]
    original=encode("isolated-before-job")
    before=store.load(pid)
    result=director.analyze_project(JobContext(Job("isolated-job","director",pid),threading.Lock()),pid,store,settings,{"goal":"youtube","instruction":"Keep the recording in source order."},preserve_current_edit=True)
    after=store.load(pid)
    assert result["proposal_only"]
    for key in ("draft","analysis","settings","manual","name"):assert after[key]==before[key]
    generated=encode("isolated-after-job")
    proposal=review(base_api).get_json()["proposal"]
    assert apply(base_api,proposal).status_code==200
    applied=encode("isolated-after-apply")
    assert post(base_api,"undo").status_code==200
    undone=encode("isolated-job-undone")
    restored=store.load(pid)
    assert restored["draft"]==before["draft"] and restored["analysis"]==before["analysis"]
    for at in (.2,.8,1.5,2.5):
        expected=pixel(media[1],original,at,5,5)
        for path in (generated,undone):assert pixel(media[1],path,at,5,5)==pytest.approx(expected,abs=5)
    sound=[samples(media[1],path) for path in (original,generated,undone)]
    for at in (.2,.8,1.5,2.5):
        levels=[tone_level(row,at,440) for row in sound]
        assert levels[1]==pytest.approx(levels[0],abs=.001)
        assert levels[2]==pytest.approx(levels[0],abs=.001)
    assert all(path.exists() for path in (original,generated,applied,undone))
