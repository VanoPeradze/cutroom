import copy
import hashlib
# Bytes from master's build_ass (verified identical before the shared event-plan refactor).
GOLDENS = {'bold:auto': '22f6705432365e1aafbe22eaa79ea0f028fb954f1eff91419be1d010b131961d', 'bold:top': '966a70a2d34c3b57f099ba32ee446477d6220897b8bcfd2404af75745c83c916', 'bold:center': 'b6a1b14ca509731d146a27b69be9737c4caf0687969f68035aec15839360bc40', 'bold:bottom': '47bbd6fe5f994b791ed15293bc7e734d6d1761c1c10c4436cdef2f9ebe561416', 'clean:auto': 'ae2defb14d1645628403b326aac70cba3a4ed0896b77d3739fd078bbde0e3bd3', 'clean:top': 'e03148604fb27daef3223ab4a31286983c5a0a39b81d9f3bcfeb6dadd1e0ec32', 'clean:center': '14aaddf0e1b6602be5ad5bd8b29fe38eb8fe20d277787c897c386eb943df476c', 'clean:bottom': '7603ca81db2b13351a00d04f2843ed7527ea77f1a4613bc6a2601abc47a704a4', 'boxed:auto': 'a7159b2c4a4a29778fd5d7faceac02ea0508146253e466b9d9b2b32c835072ef', 'boxed:top': 'b0d2edf711ad9823b914fb1f829daf329e57141d51889a0d28b472a4a5ce2948', 'boxed:center': '3bfdf424f8dc5c4ed82816c7520470973c5e77e2aa09e853bedd9caf6699caef', 'boxed:bottom': '257786179b79718da343366b2bb473c9c9aac56304df30ca25005a481da2ced8', 'highlight:auto': '7b70ee4bd904f4d0dc65f7e1c6b1ad37ab648b6bc491a0b325da410e6b423f35', 'highlight:top': '78b83a5c8a04152a6bb4c29444362375140593df1776c579f85084afb9e9d43e', 'highlight:center': 'c19b8d56d67e4fe87ce0d1450f7254ffca51ef09c860b5da1d01e5ae34d2dfb5', 'highlight:bottom': '1dc4644de3183fa2807f811431d596ded9d1f851ca0afd3939df1577c83409ff'}
from pathlib import Path
import pytest
from cutroom.captions import build_ass, automatic_caption_plan
from cutroom.render import caption_preview_scene
from test_caption_items import sequence_project

@pytest.mark.parametrize("style", ["bold","clean","boxed","highlight"])
@pytest.mark.parametrize("position", ["auto","top","center","bottom"])
def test_ass_exact_preimage_bytes(tmp_path, style, position):
    lines=[{"start":.105,"end":2.345,"text":"One two", "item_id":"a", "words":[{"start":.105,"end":1.1,"word":"One"},{"start":1.2,"end":2.345,"word":"two"}]},
           {"start":.2,"end":1.8,"text":"Overlap", "words":[]}]
    kw=dict(caption_style=style,caption_position=position,caption_scale=103,caption_lines=lines,
            layout_ranges=[{"start":1,"end":2,"camera":"stacked"}])
    build_ass({},[{"start":0,"end":3}],tmp_path/"new.ass",720,1280,**kw)
    assert hashlib.sha256((tmp_path/"new.ass").read_bytes()).hexdigest()==GOLDENS[style+":"+position]


def test_scene_readonly_burn_independent_and_saved_identity():
    p=sequence_project();p.update(id="p",revision=7);before=copy.deepcopy(p)
    scene=caption_preview_scene(p)
    assert scene["available"] and scene["events"]
    assert scene["revision"]==7 and scene["project_id"]=="p"
    assert p==before
    p["settings"]["burn_captions"]=False
    assert caption_preview_scene(p)["events"]==scene["events"]
    for event in scene["events"]:
        assert event["layer"]==0 and event["end"]>event["start"]
        assert "_ass" not in event
        assert event["start"]==round(event["start"]*100)/100

@pytest.mark.parametrize("change", ["draft","future","tracks"])
def test_unavailable_no_fallback(change):
    p=sequence_project()
    if change=="draft":p["draft"]=None
    elif change=="future":p["manual"]["sequence"]["version"]=99
    else:p["manual"]["layer_tracks"]={"version":99,"tracks":[]}
    before=copy.deepcopy(p);result=caption_preview_scene(p)
    assert not result["available"] and result["issue"] and result["events"]==[]
    assert p==before


def test_highlight_layout_and_collision_flags():
    line={"item_id":"cue", "start":0,"end":2,"text":"one two", "words":[{"start":0,"end":1,"word":"one"},{"start":1,"end":2,"word":"two"}]}
    _,events=automatic_caption_plan([line],[{"start":0,"end":2}],720,1280,caption_style="highlight")
    assert events and all(e["positioned"] and e["alignment"]==8 for e in events)
    assert all(e["tokens"]==["one","two"] for e in events)
    assert {e["active_index"] for e in events}>={0,1}
    _,normal=automatic_caption_plan([line],[{"start":0,"end":2}],1280,720)
    assert normal[0]["positioned"] is False and "x" not in normal[0]
    assert normal[0]["alignment"]==2


def test_public_projection_no_write_and_editor_items_unchanged():
    from server import _public_captions
    p=sequence_project();before=copy.deepcopy(p);public=copy.deepcopy(p)
    _public_captions(p,public)
    assert public["caption_preview"]==caption_preview_scene(p)
    assert public["editor_captions"] and p==before


def test_zero_rounded_event_retained_in_ass_not_scene(monkeypatch):
    import cutroom.render as render
    p=sequence_project()
    monkeypatch.setattr(render,"caption_lines",lambda *a,**k:[{"start":.101,"end":.104,"text":"tiny","words":[]}])
    assert render.caption_preview_scene(p)["events"]==[]
    _,events=automatic_caption_plan([{"start":.101,"end":.104,"text":"tiny","words":[]}],[{"start":0,"end":1}],1280,720)
    assert len(events)==1 and "0:00:00.10,0:00:00.10" in events[0]["_ass"]


from test_source_tracks_render import media

def test_real_encode_scene_events_equal_burned_ass(tmp_path, media, monkeypatch):
    import cutroom.render as render
    from test_caption_items import test_real_export_uses_the_edited_caption_items
    original=render.build_ass
    seen=[]
    def checked(*args,**kwargs):
        result=original(*args,**kwargs)
        _,events=automatic_caption_plan(kwargs["caption_lines"],args[1],args[3],args[4],
            layout_ranges=kwargs["layout_ranges"],caption_style=kwargs["caption_style"],
            caption_position=kwargs["caption_position"],caption_scale=kwargs["caption_scale"])
        burned=result.read_text(encoding="utf-8-sig")
        assert events and all(event["_ass"] in burned for event in events)
        seen.extend(events)
        return result
    monkeypatch.setattr(render,"build_ass",checked)
    test_real_export_uses_the_edited_caption_items(tmp_path,media,monkeypatch)
    assert seen


def test_fractional_export_boundary_binds_editor_provenance():
    p=sequence_project();p["manual"]={};p["settings"]["fps"]=30
    p["draft"]={"keep_ranges":[{"start":.249,"end":1}],"camera_plan":[{"start":0,"end":4,"camera":"A"}]}
    p["analysis"]["transcript"]["segments"]=[{"id":"s0","start":.23,"end":.8,"text":"First second",
        "words":[{"start":.23,"end":.25,"word":"First"},{"start":.4,"end":.8,"word":"second"}]}]
    scene=caption_preview_scene(p)
    assert scene["available"] and scene["events"]
    event=scene["events"][0]
    assert event["export_item_id"]=="s0:w0" and event["item_id"]=="s0:w1"
    assert event["text"]=="First second" and event["selectable"] and event["selection_issue"]==""

@pytest.mark.parametrize("case",["missing","ambiguous","different_source","hidden"])
def test_binding_never_guesses_or_changes_canonical_content(monkeypatch,case):
    import cutroom.render as render
    p=sequence_project();original=render.project_caption_items
    canonical=original(p,include_hidden=False,aligned=True)
    def items(project,*,include_hidden=True,aligned=True):
        rows=original(project,include_hidden=include_hidden,aligned=aligned)
        if aligned:return rows
        if case=="missing":return []
        if case=="ambiguous":return rows+[{**copy.deepcopy(row),"id":row["id"]+"duplicate"} for row in rows]
        if case=="different_source":
            for row in rows:row["_caption_anchor"]["source"]="changed"
        if case=="hidden":
            for row in rows:row["hidden"]=True
        return rows
    baseline=render.caption_preview_scene(p)
    monkeypatch.setattr(render,"project_caption_items",items)
    scene=render.caption_preview_scene(p)
    for old,event in zip(baseline["events"],scene["events"]):
        assert {k:v for k,v in event.items() if k not in {"item_id","selectable","selection_issue"}}=={k:v for k,v in old.items() if k not in {"item_id","selectable","selection_issue"}}
        if case=="hidden":assert event["selectable"] and event["item_id"]
        else:assert event["item_id"] is None and not event["selectable"] and event["selection_issue"]
