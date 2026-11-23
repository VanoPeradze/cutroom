"""Atomic same-kind rank translation, without allocating or retiming content."""
import copy
import math
from pathlib import Path
import pytest
from cutroom.editing import apply_manual_edit, ManualEditError
from cutroom.projects import ProjectStore
from test_media_append import content, library_api
from test_media_insert import unlocked
from test_mixed_media_insert import mixed_layers, media_row, text_row, VIDEO, AUDIO, post

T = ["track_" + format(i, "032x") for i in range(8)]

def setup(p, kind="visual", version=2):
    mixed_layers(p)
    p["manual"]["media_clips"] = []
    p["manual"]["text_clips"] = []
    rows = [text_row(str(i+1), 2.123456789123, 4.123456789123) if kind=="text" else media_row(str(i+1), AUDIO if kind=="audio" else VIDEO, 2.123456789123, 4.123456789123) for i in range(2)]
    for i,row in enumerate(rows):row.update(track_id=T[i*2], enabled=i==0)
    p["manual"]["text_clips" if kind=="text" else "media_clips"] = rows
    p["manual"]["layer_tracks"] = {"version":version,"tracks":[{"id":t,"kind":kind,"name":f"Track {i}",**({"locked":False} if version==2 else {})} for i,t in enumerate(T[:5])]}
    return rows

def params(p, delta=0, target=1):
    rows=p["manual"]["media_clips"] or p["manual"]["text_clips"]
    return dict(clip_ids=[r["id"] for r in rows],anchor_id=rows[0]["id"],track_id=T[target],delta=delta)

@pytest.mark.parametrize("kind",["visual","audio","text"])
@pytest.mark.parametrize("version",[1,2])
@pytest.mark.parametrize("delta",[0,1/24])
def test_raw_translation_history_reopen(unlocked,kind,version,delta):
    app,_,store,pid=unlocked
    store.update(pid,lambda p:(setup(p,kind,version),None)[1])
    before=store.load(pid);fields=params(before,delta)
    response=post(unlocked,"layers_relocate",**fields)
    assert response.status_code==200,response.get_json()
    after=store.load(pid)
    import os,json
    if os.environ.get("CUTROOM_RELOCATE_FIXTURES"):
        from server import _public_project
        folder=Path(os.environ["CUTROOM_RELOCATE_FIXTURES"]);folder.mkdir(exist_ok=True)
        (folder/f"public-{kind}-{version}-{delta}.json").write_text(json.dumps({"before":_public_project(before),"after":response.get_json()["project"],"payload":fields},ensure_ascii=False),encoding="utf8")
    key="text_clips" if kind=="text" else "media_clips"
    expected=copy.deepcopy(before["manual"][key])
    for i,row in enumerate(expected):
        row["track_id"]=T[i*2+1]
        if delta:
            factor=10**(6 if kind=="text" else 9)
            for edge in ("start","end"):row[edge]=math.floor((row[edge]+delta)*factor+.5)/factor
    assert after["manual"][key]==expected
    for k,v in before["manual"].items():
        if k not in {key,"history","_history"}:assert after["manual"][k]==v
    for k in ("assets","sources","settings","analysis"):assert after[k]==before[k]
    assert after["manual"]["history"]["undo_count"]==1
    assert post(unlocked,"undo").status_code==200
    assert content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200
    assert content(ProjectStore(app.extensions["cutroom_settings"]).load(pid))==content(after)

@pytest.mark.parametrize("bad",["legacy","future","anchor","target","range","mixed","source_lock","target_lock","occupied","unknown","bool","missing","duplicate"])
def test_refusal_is_atomic(unlocked,bad):
    _,_,store,pid=unlocked
    def prepare(p):
        rows=setup(p)
        if bad=="source_lock":p["manual"]["layer_tracks"]["tracks"][0]["locked"]=True
        if bad=="target_lock":p["manual"]["layer_tracks"]["tracks"][1]["locked"]=True
        if bad=="occupied":p["manual"]["media_clips"].append(media_row("3",VIDEO,2,5,track_id=T[1],enabled=False))
        if bad=="mixed":
            p["assets"][VIDEO]["kind"]="audio"
            p["manual"]["layer_tracks"]["tracks"][0]["kind"]="audio"
            rows[1]["asset_id"]=AUDIO
            p["assets"][AUDIO]["kind"]="image"
    store.update(pid,prepare)
    before=store.load(pid);fields=params(before)
    if bad=="occupied":fields["clip_ids"]=fields["clip_ids"][:2]
    if bad=="anchor":fields["anchor_id"]="media_"+"f"*32
    if bad=="target":fields["track_id"]=None
    if bad=="range":fields["track_id"]=T[4]
    if bad=="unknown":fields["start"]=1
    if bad=="bool":fields["delta"]=True
    if bad=="missing":fields["clip_ids"][1]="media_"+"f"*32
    if bad=="duplicate":fields["clip_ids"][1]=fields["clip_ids"][0]
    if bad in {"legacy","future"}:
        value=copy.deepcopy(before)
        if bad=="legacy":
            del value["manual"]["layer_tracks"]
            for row in value["manual"]["media_clips"]:row.pop("track_id")
        else:value["manual"]["layer_tracks"]["version"]=99
        original=copy.deepcopy(value)
        with pytest.raises(ValueError):apply_manual_edit(value,{"action":"layers_relocate",**fields})
        assert value==original
        return
    raw=store.state_path(pid).read_bytes()
    assert post(unlocked,"layers_relocate",**fields).status_code in (400,409)
    assert store.state_path(pid).read_bytes()==raw

def test_noop_stale_busy_and_intermediate_lock(unlocked,monkeypatch):
    app,client,store,pid=unlocked
    store.update(pid,lambda p:(setup(p),None)[1])
    before=store.load(pid);fields=params(before,target=0);raw=store.state_path(pid).read_bytes()
    assert post(unlocked,"layers_relocate",**fields).status_code==200
    assert store.state_path(pid).read_bytes()==raw
    endpoint=f"/api/projects/{pid}/manual/edit"
    assert client.post(endpoint,json={"action":"layers_relocate",**fields}).status_code==400
    assert post(unlocked,"layers_relocate",expected_revision=before["revision"]-1,**fields).status_code==409
    with monkeypatch.context() as m:
        m.setattr(app.extensions["cutroom_jobs"],"active",lambda **_:[object()])
        assert post(unlocked,"layers_relocate",**fields).status_code==409
    assert store.state_path(pid).read_bytes()==raw
    # Jump over a locked intermediate empty lane; destination/source stay unlocked.
    store.update(pid,lambda p:p["manual"]["layer_tracks"]["tracks"][1].update(locked=True))
    assert post(unlocked,"layers_relocate",**params(store.load(pid),target=2)).status_code==200


def test_selected_vacancies_validate_simultaneously(unlocked):
    _,_,store,pid=unlocked
    def prepare(p):
        rows=setup(p)
        rows[1]["track_id"]=T[1]
    store.update(pid,prepare)
    assert post(unlocked,"layers_relocate",**params(store.load(pid))).status_code==200


def test_existing_move_rejects_relocation_fields(unlocked):
    _,_,store,pid=unlocked;store.update(pid,lambda p:(setup(p),None)[1])
    raw=store.state_path(pid).read_bytes()
    assert post(unlocked,"layers_move",**params(store.load(pid))).status_code==400
    assert store.state_path(pid).read_bytes()==raw


from test_media_render import media

def test_actual_vertical_mixed_render_matches_independent_reference(media,tmp_path):
    import threading,uuid
    from test_track_destination_render import prepared
    from test_layer_tracks_render import decoded
    from cutroom.render import render_project
    from cutroom.jobs import Job,JobContext
    p,store,settings,_,unchanged=prepared(media,tmp_path)
    p["settings"].update(captions=False,burn_captions=False)
    p["analysis"]=None
    originals=copy.deepcopy(p["manual"])
    p["manual"]["media_clips"]=[];p["manual"]["text_clips"]=[]
    tracks=[];groups=[]
    for kind in ("visual","audio","text"):
        key="text_clips" if kind=="text" else "media_clips"
        candidates=[r for r in originals[key] if kind=="text" or (p["assets"][r["asset_id"]]["kind"]=="audio")== (kind=="audio")]
        assert candidates
        lanes=["track_"+uuid.uuid4().hex for _ in range(5)]
        tracks.extend({"id":lane,"kind":kind,"name":"Render track"} for lane in lanes)
        rows=[]
        for i in range(2):
            row=copy.deepcopy(candidates[i%len(candidates)])
            row.update(id=("text_" if kind=="text" else "media_")+uuid.uuid4().hex,track_id=lanes[i*2])
            rows.append(row)
        p["manual"][key].extend(rows)
        groups.append((key,rows,lanes))
    p["manual"]["layer_tracks"]={"version":1,"tracks":tracks}
    before=copy.deepcopy(p);reference=copy.deepcopy(p)
    for key,rows,lanes in groups:
        for i,row in enumerate(rows):
            next(r for r in reference["manual"][key] if r["id"]==row["id"])["track_id"]=lanes[i*2+1]
        apply_manual_edit(p,{"action":"layers_relocate","clip_ids":[r["id"] for r in rows],"anchor_id":rows[0]["id"],"track_id":lanes[1],"delta":0})
    for key in ("media_clips","text_clips"):
        assert p["manual"][key]==reference["manual"][key]
        assert [{k:v for k,v in r.items() if k!="track_id"} for r in p["manual"][key]]==[{k:v for k,v in r.items() if k!="track_id"} for r in before["manual"][key]]
    def encode(value,tag):
        store.save(value)
        record=render_project(JobContext(Job(tag,"render",value["id"]),threading.Lock()),value["id"],store,settings,{"quality":"fast"})["export"]
        return settings.exports_dir/record["name"]
    baseline=encode(before,"before");expected=encode(reference,"reference");actual=encode(p,"relocated")
    assert decoded(media[1],actual)==decoded(media[1],expected)==decoded(media[1],baseline)
    assert decoded(media[1],actual,False)==decoded(media[1],expected,False)==decoded(media[1],baseline,False)
    unchanged()


@pytest.mark.parametrize("case",["locked_noop","unrelated_offline","delta_nan","delta_bound"])
def test_additional_fail_closed_admission(unlocked,case):
    _,_,store,pid=unlocked
    def prepare(p):
        setup(p)
        if case=="locked_noop":p["manual"]["layer_tracks"]["tracks"][0]["locked"]=True
        if case=="unrelated_offline":
            from test_mixed_media_insert import IMAGE
            p["assets"][IMAGE]["status"]="failed"
            p["manual"]["media_clips"].append(media_row("3",IMAGE,6,8,track_id=T[4]))
    store.update(pid,prepare)
    before=store.load(pid);fields=params(before,target=0)
    fields["clip_ids"]=fields["clip_ids"][:2]
    if case=="delta_nan":fields["delta"]=float("nan")
    if case=="delta_bound":fields["delta"]=604801
    original=copy.deepcopy(before)
    with pytest.raises(ValueError):apply_manual_edit(before,{"action":"layers_relocate",**fields})
    assert before==original
