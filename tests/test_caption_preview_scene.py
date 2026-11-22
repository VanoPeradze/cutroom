import copy
import hashlib
GOLDENS = {'bold:auto': 'df572659e41bfa2fb5f079978f9a6dd26af5f7144b7b04769d284db94b314f3f', 'bold:top': 'd2fa173124df39eced368161a34e4b626ebd97dfc284e6006d11a7ab9b85130b', 'bold:center': '7d2cab22fe50100b98bb5d96543c6afaf70ef0f1a9f0b05c2962b4c3059dcced', 'bold:bottom': 'c9f6b8686dd3429ff2ffd0545bb0bfc21f39e0eff1f130907cf55a8e11d00f6b', 'clean:auto': 'dce7c7c8eb1a622af7b6dc23c70a5922a3ad091fd09c87d951f86830a6c6cb9a', 'clean:top': 'd6307e06c8dcd544fb50b210f74e2a8a951fc06a42aeccacf36740f94dc7c668', 'clean:center': 'b2623a4695b96e34ed3fd9df98b76c954b7e82baf3e4cfdaf713eeedda4ef94e', 'clean:bottom': 'dbb87372b56e6605fbb7f0faa50effa41895278f3988118daeebe3b904ad13eb', 'boxed:auto': '76075f2e4a18866139459ce45a5f78f52ea76761dbd22ff661e046d0769c6e2b', 'boxed:top': '9cc01d8389d1a5b6c562fdf231aa722c6c71103b4d8ead0fe19436ce728114df', 'boxed:center': '63100ec076f7d9540c275468ba19f01562e89aacf68aeadaa2ae5c3ef0bc7219', 'boxed:bottom': '17ce5e05b5288f3b1a1e9fa313ce948f9c4375056e0610b8a96c5eb9ee5ef63c', 'highlight:auto': 'cc02c4e64c291f1028462534a438f3a70d3ccb03851694f5468f4b1c4ae7300a', 'highlight:top': '9effcfa154c64ab7631068f770e94000fa42e8c4980c4ce2b45edf82df112de3', 'highlight:center': '4d8167cd00c2416bb2ebedb73af6a2eacdb94e988daa5874e40c2e4c4add7d84', 'highlight:bottom': 'ecefaca5e8629ee068908ce2a3f2d634827bd2e42a19353b439a9b0f8f69510e'}
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
