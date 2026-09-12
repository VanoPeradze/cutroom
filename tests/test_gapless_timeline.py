"""Normal dragging inserts without black holes; edges reveal real media."""
import copy
import json

import pytest

from cutroom import render
from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.sequence import editor_sequence_snapshot
from cutroom.source_tracks import timeline_duration
from test_sequence_editing import project, edit, geometry
from test_source_tracks_api import post, track_api


@pytest.mark.parametrize("slot", [None,"A","B"])
@pytest.mark.parametrize("start,end,to", [(0,4,6),(4,10,0),(0,4,100),(1,3,5)])
def test_ripple_moves_preserve_all_media_and_never_add_gaps(slot,start,end,to):
    value=project()
    before=editor_sequence_snapshot(value)
    edit(value,"move_range",start=start,end=end,to=to,mode="ripple",**({"slot":slot} if slot else {}))
    assert timeline_duration(value)==10
    for target in ([slot] if slot else ["A","B"]):
        clips=geometry(value,target)
        assert clips[0][0]==0 and clips[-1][1]==10
        assert all(a[1]==b[0] for a,b in zip(clips,clips[1:]))
        # Every original half-second survives exactly once, despite reordering.
        frames=sorted(round(source+i/2,3) for left,right,source in clips for i in range(round((right-left)*2)))
        assert frames==[i/2 for i in range(8)]+[10+i/2 for i in range(12)]
    if slot:
        other="B" if slot=="A" else "A"
        assert value["manual"]["source_tracks"][other]==before["source_tracks"][other]
    moved=copy.deepcopy(value["manual"]["source_tracks"])
    value=json.loads(json.dumps(value))
    apply_manual_edit(value,{"action":"undo"})
    assert editor_sequence_snapshot(value)["source_tracks"]==before["source_tracks"]
    apply_manual_edit(value,{"action":"redo"})
    assert value["manual"]["source_tracks"]==moved


def test_single_clip_move_uses_same_gapless_mode():
    value=project()
    clip=editor_sequence_snapshot(value)["source_tracks"]["A"][0]
    edit(value,"move",slot="A",clip_id=clip["id"],start=100,mode="ripple")
    assert geometry(value)==[(0,6,10),(6,10,0)]


def test_close_gaps_preserves_paired_coverage_layout_crops_and_captions():
    value=project()
    edit(value,"crop",slot="A",start=4,end=10,x=.8,y=.5,zoom=1)
    for slot in ["A","B"]:
        edit(value,"remove_range",slot=slot,start=0,end=2)
        edit(value,"remove_range",slot=slot,start=8,end=10)
    # Only A has a gap here. Both-track closing must retain B's footage.
    edit(value,"remove_range",slot="A",start=3,end=4)
    before=copy.deepcopy(value)
    edit(value,"close_gaps")
    assert timeline_duration(value)==6
    assert geometry(value)==[(0,1,2),(2,6,10)]
    assert geometry(value,"B")==[(0,2,2),(2,6,10)]
    assert value["manual"]["source_tracks"]["A"][-1]["crop"]["x"]==.8
    assert render._caption_transcript(value)["segments"]==[{"start":2,"end":4,"text":"original speech"}]
    assert render._expected_output_duration(value)==6
    apply_manual_edit(value,{"action":"undo"})
    assert value["manual"]["source_tracks"]==before["manual"]["source_tracks"]


def test_close_all_gaps_is_atomic_idempotent_and_can_empty_an_empty_edit():
    value=project()
    for slot in ["A","B"]:
        edit(value,"remove_range",slot=slot,start=0,end=10)
    edit(value,"close_gaps")
    assert timeline_duration(value)==0 and value["manual"]["sequence"]["camera_plan"]==[]
    before=copy.deepcopy(value)
    edit(value,"close_gaps")
    assert value==before


def test_close_one_track_does_not_move_other_or_extend_sequence():
    value=project()
    edit(value,"remove_range",slot="B",start=1,end=3)
    before=copy.deepcopy(value["manual"]["source_tracks"]["A"])
    edit(value,"close_gaps",slot="B")
    assert geometry(value,"B")==[(0,1,0),(1,2,3),(2,8,10)]
    assert value["manual"]["source_tracks"]["A"]==before
    assert timeline_duration(value)==10


@pytest.mark.parametrize("slot", [None,"A"])
@pytest.mark.parametrize("edge,time,expected", [("end",4,[(0,4,0),(4,10,10)]),("start",2,[(0,2,0),(2,10,8)])])
def test_drag_edge_restores_real_source_into_gap(slot,edge,time,expected):
    value=project()
    for target in ["A","B"]:
        edit(value,"remove_range",slot=target,start=2,end=4)
    start,end=(0,2) if edge=="end" else (4,10)
    before=copy.deepcopy(value)
    edit(value,"trim_edge",start=start,end=end,edge=edge,time=time,**({"slot":slot} if slot else {}))
    assert geometry(value)==expected
    assert geometry(value,"B")== ([(0,2,0),(4,10,10)] if slot else expected)
    assert timeline_duration(value)==10
    apply_manual_edit(value,{"action":"undo"})
    assert value["manual"]["source_tracks"]==before["manual"]["source_tracks"]


@pytest.mark.parametrize("fps", [30,60])
def test_extending_tail_and_shortening_edges_preserves_frame_precision_and_framing(fps):
    value=project();value["settings"]["fps"]=fps
    edit(value,"crop",slot="A",start=4,end=10,x=.8,y=.5,zoom=1)
    edit(value,"trim_edge",start=4,end=10,edge="end",time=10+1/fps)
    assert timeline_duration(value)==pytest.approx(10+1/fps)
    assert value["manual"]["source_tracks"]["A"][-1]["crop"]["x"]==.8
    edit(value,"trim_edge",start=0,end=4,edge="start",time=1)
    assert geometry(value)[0]==(0,3,1)
    assert timeline_duration(value)==pytest.approx(9+1/fps)


@pytest.mark.parametrize("payload", [
    {"start":0,"end":4,"edge":"end","time":5}, # neighbor blocks extension
    {"start":4,"end":10,"edge":"end","time":15}, # source ends at20
    {"start":0,"end":4,"edge":"start","time":-1},
    {"start":0,"end":4,"edge":"end","time":0},
    {"start":0,"end":4,"edge":"wrong","time":2},
])
def test_invalid_edge_never_partially_changes_sources(payload):
    value=project();before=copy.deepcopy(value)
    with pytest.raises(ManualEditError): edit(value,"trim_edge",**payload)
    assert value==before


def test_api_closes_gap_then_trims_with_revision_protection(track_api):
    client,store,project_id=track_api
    for slot in ["A","B"]:
        assert post(track_api,{"action":"sequence_remove_range","slot":slot,"start":2,"end":4}).status_code==200
    extended=post(track_api,{"action":"sequence_trim_edge","start":0,"end":2,"edge":"end","time":3})
    assert extended.status_code==200,extended.get_json()
    closed=post(track_api,{"action":"sequence_close_gaps"})
    assert closed.status_code==200,closed.get_json()
    assert closed.get_json()["project"]["editor_sequence"]["duration"]==19
    stale=post(track_api,{"action":"sequence_close_gaps"},revision=extended.get_json()["project"]["revision"])
    assert stale.status_code==409
