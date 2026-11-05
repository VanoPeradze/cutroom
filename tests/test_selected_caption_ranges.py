"""Selected-range source mapping and explicit overlay application, no ASR calls."""
import copy
import pytest
from test_caption_alternatives import api, binding, FORMAT, load, proposal, apply  # noqa:F401
from test_caption_generation import backend  # noqa:F401
from cutroom.caption_ranges import selected_scope
from cutroom.caption_alternatives import register,status
from cutroom.render import project_caption_items
from cutroom.sequence import materialize_sequence

@pytest.fixture
def ranged(api):
    _,_,store,pid=api
    def prepare(p):
        p["sources"]["A"]["duration"]=100
        p["analysis"]["transcript"]["segments"]=[{"id":f"s{i}","start":i*2.,"end":i*2.+2.,"text":f"original {i}","words":[{"start":i*2.,"end":i*2.+1.,"word":"original"},{"start":i*2.+1.,"end":i*2.+2.,"word":str(i)}]} for i in range(50)]
        p["draft"].update(source_duration=100.,output_duration=100.,keep_ranges=[{"start":0.,"end":100.}],camera_plan=[{"start":0.,"end":100.,"camera":"A"}])
        return materialize_sequence(p)[0]
    store.update(pid,prepare)
    return api

def alternative(p,start=4.,end=8.):
    scope=selected_scope(p,{"start":start,"end":end})
    pieces=scope["pieces"]
    rows=[{"id":f"p{i}","start":r[2],"end":r[3],"text":f"alternate {i}","words":[]} for i,r in enumerate(pieces)]
    return {"format":FORMAT,"label":"Selected ASR unverified","binding":binding(p),"scope":scope,
            "source_interval":[min(r[2] for r in pieces),max(r[3] for r in pieces)],"transcript":{"language":"en","model":"mocked","segments":rows}}

def test_range_inside_long_edit_preserves_every_outside_caption_and_undo(ranged):
    _,client,store,pid=ranged;before=store.load(pid);items=project_caption_items(before,aligned=False)
    key=load(ranged,alternative(before));preview=proposal(ranged,key)
    assert preview["duration"]==4 and preview["scope"]["timeline_range"]==[4.,8.]
    assert apply(ranged,preview).status_code==200
    after=store.load(pid);actual=project_caption_items(after,aligned=False)
    expected=[r for r in items if r["end"]<=4 or r["start"]>=8]
    assert [r for r in actual if r["end"]<=4 or r["start"]>=8]==expected
    assert [r["text"] for r in actual if r["start"]>=4 and r["end"]<=8]==["alternate 0"]
    assert after["analysis"]==before["analysis"] and after["manual"]["source_tracks"]==before["manual"]["source_tracks"]
    for action in ["undo","redo"]:
        response=client.post(f"/api/projects/{pid}/manual/edit",json={"action":action,"expected_revision":store.load(pid)["revision"]});assert response.status_code==200
    assert status(store.load(pid))["active_id"]==key

def test_ordered_cut_maps_selection_to_exact_original_source_times(ranged):
    _,_,store,pid=ranged;p=store.load(pid);c=p["manual"]["source_tracks"]["A"][0]
    p["manual"]["source_tracks"]["A"]=[{**c,"end":10.},{**c,"id":"second","start":10.,"end":20.,"source_start":40.}]
    p["manual"]["sequence"]["camera_plan"]=[{"start":0.,"end":20.,"camera":"A"}]
    scope=selected_scope(p,{"start":8.,"end":13.})
    assert scope["pieces"]==[[8.,10.,8.,10.],[10.,13.,40.,43.]]
    key=register(p,alternative(p,8.,13.));store.save(p);preview=proposal(ranged,key)
    assert preview["duration"]==5 and preview["ranges"]==[{"start":8.,"end":10.},{"start":40.,"end":43.}]
    assert apply(ranged,preview).status_code==200
    rows=project_caption_items(store.load(pid),aligned=False)
    assert [(r["start"],r["end"],r["text"]) for r in rows if r["text"].startswith("alternate")]==[(8.,10.,"alternate 0"),(10.,13.,"alternate 1")]

def test_outside_manual_caption_edit_keeps_text_timing_and_anchor(ranged):
    _,client,store,pid=ranged;item=project_caption_items(store.load(pid),aligned=False)[0]
    response=client.post(f"/api/projects/{pid}/manual/edit",json={"action":"caption_update","caption_id":item["id"],"text":"Keep this manual wording","scope":"item","expected_revision":store.load(pid)["revision"]});assert response.status_code==200
    p=store.load(pid);outside=project_caption_items(p,aligned=False)[0];saved_manual=copy.deepcopy(p["manual"])
    key=load(ranged,alternative(p));preview=proposal(ranged,key);assert not preview["manual_caption_edits"]
    assert apply(ranged,preview).status_code==200
    after=store.load(pid);assert project_caption_items(after,aligned=False)[0]==outside
    for name in ("caption_overrides","caption_override_anchors"):assert after["manual"][name]==saved_manual[name]

def test_conflicting_manual_caption_is_not_replaced(ranged):
    _,client,store,pid=ranged;item=project_caption_items(store.load(pid),aligned=False)[2]
    assert client.post(f"/api/projects/{pid}/manual/edit",json={"action":"caption_update","caption_id":item["id"],"text":"User wins","scope":"item","expected_revision":store.load(pid)["revision"]}).status_code==200
    key=load(ranged,alternative(store.load(pid)));preview=proposal(ranged,key);before=store.state_path(pid).read_bytes()
    assert preview["manual_caption_edits"] and apply(ranged,preview).status_code==400
    assert store.state_path(pid).read_bytes()==before

@pytest.mark.parametrize("kind",["gap","reverse","sourceB","offset","oversize"])
def test_unsupported_mapping_rejected(ranged,kind):
    _,_,store,pid=ranged;p=store.load(pid);selection={"start":4.,"end":8.}
    if kind=="gap":p["manual"]["source_tracks"]["A"][0]["start"]=6.
    elif kind=="reverse":
        c=p["manual"]["source_tracks"]["A"][0];p["manual"]["source_tracks"]["A"]=[{**c,"end":6.,"source_start":10.},{**c,"id":"second","start":6.,"end":10.,"source_start":0.}]
    elif kind=="sourceB":p["sources"]["B"]={"duration":100.}
    elif kind=="offset":p["analysis"]["audio_timeline_offset"]=1.
    else:selection={"start":0.,"end":91.}
    with pytest.raises(ValueError):selected_scope(p,selection)

def test_crossing_caption_keeps_outside_words_with_no_fabricated_text(ranged):
    _,_,store,pid=ranged;p=store.load(pid);key=load(ranged,alternative(p,3.,5.));assert apply(ranged,proposal(ranged,key)).status_code==200
    rows=project_caption_items(store.load(pid),aligned=False)
    assert any(r["start"]==2 and r["end"]==3 and r["text"]=="original" for r in rows)
    assert any(r["start"]==5 and r["end"]==6 and r["text"]=="2" for r in rows)

def test_scope_tampering_and_stale_geometry_rejected(ranged):
    _,_,store,pid=ranged;p=store.load(pid);value=alternative(p);value["scope"]["pieces"][0][2]+=1
    with pytest.raises(ValueError):register(p,value)

def test_generation_api_extracts_only_selected_cut_pieces_and_saves_review_scope(ranged,monkeypatch,tmp_path):
    from cutroom import caption_generation as g
    import time
    _,client,store,pid=ranged;p=store.load(pid);c=p["manual"]["source_tracks"]["A"][0]
    p["manual"]["source_tracks"]["A"]=[{**c,"end":10.},{**c,"id":"second","start":10.,"end":20.,"source_start":40.}]
    p["manual"]["sequence"]["camera_plan"]=[{"start":0.,"end":20.,"camera":"A"}];p=store.save(p)
    monkeypatch.setattr(g,"cached_model",lambda *_:tmp_path)
    monkeypatch.setattr(g.importlib.util,"find_spec",lambda _:object())
    extracted=[]
    def extract(source,target,settings,start,duration,check):
        check();extracted.append((start,duration));target.write_bytes(b"mocked PCM");return target
    def asr(*args,**kw):
        return {"segments":[{"id":"native","start":0.,"end":kw["duration"],"text":"Unverified generated speech","words":[]}],"language":kw["language"]}
    monkeypatch.setattr(g,"_extract_audio_chunk",extract);monkeypatch.setattr(g,"transcribe",asr)
    response=client.post(f"/api/projects/{pid}/caption-generation",json={"language":"en","expected_revision":p["revision"],"selection":{"start":8.,"end":13.}})
    assert response.status_code==202,response.get_json();job_id=response.get_json()["job"]["id"]
    until=time.monotonic()+2
    while time.monotonic()<until:
        job=client.get(f"/api/jobs/{job_id}").get_json()["job"]
        if job["status"] not in {"queued","running"}:break
        time.sleep(.01)
    assert job["status"]=="completed",job
    assert extracted==[(8.,2.),(40.,3.)]
    after=store.load(pid);assert after["analysis"]==p["analysis"] and after["manual"]==p["manual"]
    review=proposal(ranged,job["result"]["alternative_id"])
    assert review["scope"]["timeline_range"]==[8.,13.] and review["duration"]==5.
    assert apply(ranged,review).status_code==200

def test_word_crossing_selection_edge_remains_visible_outside(ranged):
    _,_,store,pid=ranged
    def longer_word(p):p["analysis"]["transcript"]["segments"][0]={"id":"boundary","start":0.,"end":8.,"text":"one longword","words":[{"start":0.,"end":3.,"word":"one"},{"start":3.,"end":8.,"word":"longword"}]}
    p=store.update(pid,longer_word);key=load(ranged,alternative(p,2.,6.));assert apply(ranged,proposal(ranged,key)).status_code==200
    rows=project_caption_items(store.load(pid),aligned=False)
    assert any(r["start"]==6 and r["end"]==8 and r["text"]=="longword" for r in rows)

def test_picture_crop_preserves_active_partial_overlay(ranged):
    _,client,store,pid=ranged;p=store.load(pid);key=load(ranged,alternative(p));assert apply(ranged,proposal(ranged,key)).status_code==200
    before=project_caption_items(store.load(pid),aligned=False)
    response=client.post(f"/api/projects/{pid}/manual/edit",json={"action":"sequence_crop","slot":"A","start":5.,"end":7.,"x":.5,"y":.8,"zoom":1.5,"expected_revision":store.load(pid)["revision"]})
    assert response.status_code==200,response.get_json()
    after=store.load(pid);assert status(after)["active_id"]==key
    assert [{k:r[k] for k in ("text","start","end")} for r in project_caption_items(after,aligned=False)]==[{k:r[k] for k in ("text","start","end")} for r in before]
