"""Explicit creator roles/PiP/fit use normal edit and render contracts."""
import copy
import pytest
from test_caption_alternatives import api  # noqa:F401
from cutroom.creator_layout import controls,pip_geometry
from cutroom.render import _segment_nodes,_source_mixer

@pytest.fixture
def dual(api):
    _,_,store,pid=api
    def prepare(p):
        p["sources"]["A"].update(width=320,height=180)
        p["sources"]["B"]={**p["sources"]["A"],"generation":"b-v1","relative_path":"media/source-B.mp4","width":160,"height":120}
    store.update(pid,prepare)
    return api

def apply(dual,**values):
    _,client,store,pid=dual
    return client.post(f"/api/projects/{pid}/manual/edit",json={"action":"set_source_mixer","screen_slot":"A","camera_slot":"B","primary_role":"screen","audio_slot":"A","first_slot":"B","expected_revision":store.load(pid)["revision"],**values})

def test_explicit_controls_persist_reopen_undo_and_do_not_rewrite_sources_or_captions(dual):
    _,client,store,pid=dual;before=store.load(pid)
    result=apply(dual,screen_fit="contain",pip_scale=.25,pip_x=0.,pip_y=.5);assert result.status_code==200,result.get_json()
    p=store.load(pid);assert p["analysis"]==before["analysis"] and p["sources"]==before["sources"]
    assert controls(p["manual"]["source_mixer"])=={"screen_fit":"contain","pip_scale":.25,"pip_x":0.,"pip_y":.5}
    for action in ["undo","redo"]:
        assert client.post(f"/api/projects/{pid}/manual/edit",json={"action":action,"expected_revision":store.load(pid)["revision"]}).status_code==200
    assert store.load(pid)["manual"]["source_mixer"]["pip_scale"]==.25

@pytest.mark.parametrize("values",[{"pip_scale":.01},{"pip_scale":True},{"pip_x":2},{"pip_y":float("nan")},{"screen_fit":"stretch"}])
def test_invalid_controls_are_atomic(dual,values):
    _,_,store,pid=dual;before=store.state_path(pid).read_bytes();assert apply(dual,**values).status_code==400
    assert store.state_path(pid).read_bytes()==before

def test_source_role_swapping_preserves_explicit_fit_and_geometry(dual):
    assert apply(dual,screen_fit="contain",pip_scale=.3,pip_x=0.,pip_y=0.).status_code==200
    assert apply(dual,screen_slot="B",camera_slot="A").status_code==200
    _,_,store,pid=dual;p=store.load(pid);m=_source_mixer(p)
    assert m["screen_slot"]=="B" and m["screen_fit"]=="contain" and m["pip_scale"]==.3

def test_geometry_preserves_inset_aspect_and_bounds(dual):
    _,_,store,pid=dual;p=store.load(pid);m={"screen_slot":"A","camera_slot":"B","primary_role":"screen","pip_scale":.25,"pip_x":0.,"pip_y":.5}
    assert pip_geometry(p,1280,720,m)==(320,240,0,240)
    p["sources"]["B"].update(width=100,height=800)
    w,h,x,y=pip_geometry(p,720,1280,{**m,"pip_scale":.55,"pip_x":1.,"pip_y":1.})
    assert 0<w<=720 and 0<h<=1280 and x+w<=720 and y+h<=1280

def test_absent_controls_retain_legacy_geometry(dual):
    _,_,store,pid=dual
    assert pip_geometry(store.load(pid),1280,720,{})==(434,200,814,488)

def test_renderer_screen_contain_overrides_saved_zoom_and_positions_inset(dual):
    assert apply(dual,screen_fit="contain",pip_scale=.25,pip_x=0.,pip_y=.5).status_code==200
    _,_,store,pid=dual;p=store.load(pid)
    item={"start":0.,"end":1.,"camera":"pip","crop":{"A":{"x":1.,"y":1.,"zoom":3.}}}
    graph=";".join(_segment_nodes(0,item,1280,720,p,True,8.,0.)[0])
    assert "overlay=0:240" in graph and "force_original_aspect_ratio=decrease" in graph
    assert "scale=3840:2160" not in graph

def test_creator_fit_does_not_override_single_source_podcast_crop(dual):
    assert apply(dual,screen_fit="contain",pip_scale=.3).status_code==200
    _,_,store,pid=dual;p=store.load(pid);p["sources"]["B"]=None
    graph=";".join(_segment_nodes(0,{"start":0.,"end":1.,"camera":"A","crop":{"A":{"x":.5,"y":0.,"zoom":2.}}},360,640,p,False,0.,0.)[0])
    assert "scale=720:1280" in graph and "force_original_aspect_ratio=decrease" not in graph
