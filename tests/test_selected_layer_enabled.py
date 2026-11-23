"""Occurrence bypass is saved, reversible and shared by preview/export contracts."""
from __future__ import annotations
import copy
import hashlib
import subprocess
import pytest
from cutroom.projects import ProjectStore
from cutroom.editing import apply_manual_edit
from cutroom.media_library import validate_media_clip, MediaLibraryError
from cutroom.render_inventory import library_clips, audible, compile_render_inputs
from cutroom.composition import chroma_video_targets
from cutroom.text_clips import validated_text_clips, public_text_clips, TextClipError
from test_media_append import ASSET, content, library_api  # noqa: F401
from test_media_insert import unlocked  # noqa: F401
from test_media_render import media  # noqa: F401
from test_mixed_media_insert import mixed_layers, media_row, text_row, VIDEO, AUDIO, IMAGE, post
from test_selected_layer_trim import render_setup


@pytest.mark.parametrize("key,index", [("media_clips",1),("media_clips",2),("media_clips",3),("text_clips",1),("text_clips",2)])
def test_disable_reenable_keeps_exact_occurrence_timing_content_and_history(unlocked,key,index):
    app,_,store,pid=unlocked
    def prepare(p):
        mixed_layers(p);p["manual"]["track_locks"]={"A":True,"B":True}
        p["manual"]["media_clips"][1].update(motion="pan")
    store.update(pid,prepare);before=store.load(pid);clip=before["manual"][key][index]
    hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (store.project_dir(pid)/"media").rglob("*") if p.is_file()}
    action="text_set_enabled" if key=="text_clips" else "media_set_enabled"
    response=post(unlocked,action,clip_id=clip["id"],enabled=False);assert response.status_code==200,response.get_json()
    after=store.load(pid);wanted=copy.deepcopy(before["manual"][key]);wanted[index]["enabled"]=False
    assert after["manual"][key]==wanted
    assert response.get_json()["project"]["manual"][key][index]["enabled"] is False
    for field,value in before["manual"].items():
        if field not in (key,"history","_history"):assert after["manual"][field]==value
    for field in ("sources","assets","analysis"):assert after[field]==before[field]
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200 and content(ProjectStore(app.extensions["cutroom_settings"]).load(pid))==content(after)
    assert post(unlocked,action,clip_id=clip["id"],enabled=True).status_code==200
    assert content(store.load(pid))==content(before)
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes}==hashes


@pytest.mark.parametrize("action,clip", [("media_set_enabled","media_"+"2"*32),("text_set_enabled","text_"+"2"*32)])
@pytest.mark.parametrize("enabled", [None,0,1,"false",[],{}])
def test_enable_requires_strict_boolean_atomically(unlocked,action,clip,enabled):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    assert post(unlocked,action,clip_id=clip,enabled=enabled).status_code==400
    assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("action,clip", [("media_set_enabled","media_"+"2"*32),("text_set_enabled","text_"+"2"*32)])
def test_enable_requires_explicit_state_and_refuses_incidental_edits(unlocked,action,clip):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    for fields in ({},{"enabled":False,"start":0.},{"enabled":False,"muted":True}):
        assert post(unlocked,action,clip_id=clip,**fields).status_code==400
        assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("action,clip", [("media_set_enabled","A:sequence:0:0"),("text_set_enabled","automatic_caption"),("media_set_enabled","media_"+"f"*32)])
def test_stale_or_unsupported_targets_never_disable_underlying_source(unlocked,action,clip):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    assert post(unlocked,action,clip_id=clip,enabled=False).status_code==400
    assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("key,index", [("media_clips",1),("text_clips",1)])
@pytest.mark.parametrize("enabled", [False,True])
def test_enabled_noop_retains_redo_without_rewriting_legacy_default(unlocked,key,index,enabled):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p);clip=p["manual"][key][index];action="text_set_enabled" if key=="text_clips" else "media_set_enabled"
    if not enabled:clip["enabled"]=False
    apply_manual_edit(p,{"action":action,"clip_id":clip["id"],"enabled":not enabled});apply_manual_edit(p,{"action":"undo"});before=copy.deepcopy(p)
    apply_manual_edit(p,{"action":action,"clip_id":clip["id"],"enabled":enabled})
    assert p==before and p["manual"]["history"]["redo_count"]==1


@pytest.mark.parametrize("key,index", [("media_clips",1),("text_clips",1)])
def test_disabled_occurrences_remain_editable_and_split_duplicate_inherit_flag(unlocked,key,index):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);clip=store.load(pid)["manual"][key][index];prefix="text" if key=="text_clips" else "media"
    assert post(unlocked,prefix+"_set_enabled",clip_id=clip["id"],enabled=False).status_code==200
    assert post(unlocked,prefix+"_move",clip_id=clip["id"],start=8.).status_code==200
    assert post(unlocked,prefix+"_duplicate",clip_id=clip["id"],start=0.).status_code==200
    assert post(unlocked,prefix+"_split",clip_id=clip["id"],time=9.).status_code==200
    rows=store.load(pid)["manual"][key]
    assert len([r for r in rows if r.get("enabled") is False])==3
    assert all(r["start"]>=0 and r["end"]<=15 for r in rows)


def test_unavailable_media_can_be_disabled_but_cannot_be_reenabled(unlocked):
    _,_,store,pid=unlocked
    def prepare(p):mixed_layers(p);p["assets"][VIDEO]["status"]="failed"
    store.update(pid,prepare)
    for digit in ("1","2","5"):
        assert post(unlocked,"media_set_enabled",clip_id="media_"+digit*32,enabled=False).status_code==200
    value=store.load(pid);assert all(a["kind"]!="video" for _,a in library_clips(value))
    before=store.state_path(pid).read_bytes()
    assert post(unlocked,"media_set_enabled",clip_id="media_"+"2"*32,enabled=True).status_code==400
    assert store.state_path(pid).read_bytes()==before


def test_disabled_media_missing_asset_is_omitted_before_render_input_validation(unlocked):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p)
    for r in p["manual"]["media_clips"]:r["enabled"]=False
    p["assets"]={}
    assert library_clips(p)==[] and compile_render_inputs(p).inputs("library")==()
    assert audible({"enabled":False,"audio_enabled":True},{"kind":"video","has_audio":True}) is False
    assert audible({"enabled":False},{"kind":"audio"}) is False


def test_disabled_chroma_occurrences_do_not_request_unused_background_inputs(unlocked):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p)
    p["assets"][VIDEO].update(id=VIDEO,width=160,height=90,path=f"media/assets/{VIDEO}/original.mp4")
    p["manual"]["chroma_key"]={VIDEO:{"enabled":True,"background_asset_id":IMAGE,"background_mode":"replace"}}
    for r in p["manual"]["media_clips"]:
        if r["asset_id"]==VIDEO:r["enabled"]=False
    assert VIDEO not in chroma_video_targets(p,used_only=True)
    p["manual"]["media_clips"][0].pop("enabled")
    assert VIDEO in chroma_video_targets(p,used_only=True)
    assert VIDEO in chroma_video_targets(p)  # effect settings remain editable


def test_disabled_text_is_retained_publicly_but_filtered_from_render_contract(unlocked):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p);p["manual"]["text_clips"][1]["enabled"]=False
    all_rows=validated_text_clips(p);active=validated_text_clips(p,enabled_only=True)
    assert len(all_rows)==4 and len(active)==3
    assert public_text_clips(all_rows)[1]["enabled"] is False
    assert p["manual"]["text_clips"][1] not in active


@pytest.mark.parametrize("bad", [0,1,"false",None])
def test_corrupt_saved_enabled_flags_fail_closed_not_silently_hidden(unlocked,bad):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p)
    p["manual"]["media_clips"][0]["enabled"]=bad
    with pytest.raises(ValueError,match="enabled"):library_clips(p)
    with pytest.raises(MediaLibraryError,match="enabled"):validate_media_clip(p,p["manual"]["media_clips"][0],15)
    p["manual"]["text_clips"][0]["enabled"]=bad
    with pytest.raises(TextClipError,match="enabled"):validated_text_clips(p,enabled_only=True)


def test_disabled_occurrences_still_count_for_existing_safe_text_overlap_limit(unlocked):
    _,_,store,pid=unlocked
    def prepare(p):
        mixed_layers(p);p["manual"]["text_clips"]=[{**text_row("1",1.,3.,id=f"text_{i:032x}"),"enabled":False} for i in range(16)]
    store.update(pid,prepare);before=store.state_path(pid).read_bytes()
    response=post(unlocked,"text_add",kind="title",start=1.,end=3.,text="Retained disabled clips still occupy editable spans")
    assert response.status_code==400 and "disabled" in response.get_json()["message"]
    assert store.state_path(pid).read_bytes()==before


def test_enable_revision_conflict_is_atomic(unlocked):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);revision=store.load(pid)["revision"]
    store.update(pid,lambda p:p.update(name="Elsewhere"));before=store.state_path(pid).read_bytes()
    assert post(unlocked,"media_set_enabled",clip_id="media_"+"2"*32,enabled=False,expected_revision=revision).status_code==409
    assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("speed,motion", [(.5,"pan"),(2.,"zoom_in")])
def test_real_disabled_export_matches_removed_reference_and_reenable_restores_output(library_api,media,speed,motion):
    from test_media_render import pixel,samples,tone_level
    pattern=media[0]/f"enable-pattern-{speed}.mp4"
    subprocess.run([media[1],"-v","error","-y","-f","lavfi","-i","testsrc2=s=160x90:r=30:d=3","-f","lavfi","-i","aevalsrc='if(between(t,1,2),0.3*sin(2*PI*440*t),0)':s=48000:d=3","-c:v","libx264","-preset","ultrafast","-c:a","aac","-t","3",str(pattern)],check=True,capture_output=True,timeout=20)
    generated=(*media[:3],pattern,*media[4:]);store,pid,settings,encoded,hashes,originals=render_setup(library_api,generated,speed)
    def configure(p):
        p["manual"]["media_clips"][0]["motion"]=motion
        p["manual"]["text_clips"].append(text_row("2",.75,2.25,kind="caption",text="ENABLED CAPTION",template="plain",subtext="",position="top"))
        p["settings"].update(captions=True,burn_captions=False)
        p["analysis"]={"transcript":{"segments":[]}}
    store.update(pid,configure);original,original_record=encoded("enable-original");before_manual=copy.deepcopy(store.load(pid)["manual"])
    assert "ENABLED CAPTION" in (settings.exports_dir/original_record["captions_name"]).read_text(encoding="utf-8")
    store.update(pid,lambda p:p["manual"].update(media_clips=[],text_clips=[]));expected,expected_record=encoded("enable-reference")
    store.update(pid,lambda p:p.update(manual=copy.deepcopy(before_manual)))
    ids=[("media_set_enabled",r["id"]) for r in before_manual["media_clips"]]+[("text_set_enabled",r["id"]) for r in before_manual["text_clips"]]
    for action,clip in ids:
        before=content(store.load(pid));response=post(library_api,action,clip_id=clip,enabled=False);assert response.status_code==200,response.get_json()
        after=content(store.load(pid));assert post(library_api,"undo").status_code==200 and content(store.load(pid))==before
        assert post(library_api,"redo").status_code==200 and content(ProjectStore(settings).load(pid))==after
    disabled,disabled_record=encoded("enable-disabled")
    assert disabled_record["manual_text_count"]==0 and not disabled_record.get("captions_name") and not disabled_record["captions_burned"]
    assert len(store.load(pid)["manual"]["media_clips"])==3 and len(store.load(pid)["manual"]["text_clips"])==2
    for action,clip in ids:assert post(library_api,action,clip_id=clip,enabled=True).status_code==200
    enabled,enabled_record=encoded("enable-restored")
    assert enabled_record["manual_text_count"]==2 and "ENABLED CAPTION" in (settings.exports_dir/enabled_record["captions_name"]).read_text(encoding="utf-8")
    assert store.load(pid)["manual"]["media_clips"]==before_manual["media_clips"] and store.load(pid)["manual"]["text_clips"]==before_manual["text_clips"]
    for r in (original_record,expected_record,disabled_record,enabled_record):assert r["duration"]==pytest.approx(3.,abs=1/30)
    old_audio,off_audio,new_audio=(samples(media[1],path) for path in (original,disabled,enabled))
    for at in (.3,.6,.9,1.3,1.9,2.3,2.6):
        for x,y in ((30,15),(50,40),(120,15),(80,75)):
            for want_path,got_path in ((expected,disabled),(original,enabled)):
                want,got=pixel(media[1],want_path,at,x,y),pixel(media[1],got_path,at,x,y)
                assert max(abs(a-b) for a,b in zip(want,got))<24,(speed,at,want,got)
        for hz in (440,880):
            assert tone_level(off_audio,at,hz)<.003
            assert tone_level(new_audio,at,hz)==pytest.approx(tone_level(old_audio,at,hz),abs=.003)
    assert tone_level(old_audio,1.3,440)>.2 and tone_level(old_audio,1.3,880)>.03
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}==hashes
    assert len(store.load(pid)["exports"])==4 and all(p.exists() for p in (original,expected,disabled,enabled))


def test_real_disabled_only_sequence_keeps_black_silent_duration_then_recovers(library_api,media):
    from cutroom.render import require_layout_coverage
    from test_media_render import pixel,samples,tone_level
    store,pid,settings,encoded,hashes,originals=render_setup(library_api,media,.5)
    def configure(p):
        p["manual"].update(sequence={"version":1,"duration":3.,"camera_plan":[]},source_tracks={"A":[],"B":[]})
        for key in ("media_clips","text_clips"):
            for row in p["manual"][key]:row["enabled"]=False
    store.update(pid,configure);before=content(store.load(pid));require_layout_coverage(store.load(pid))
    disabled,record=encoded("enable-disabled-only")
    assert record["duration"]==pytest.approx(3.,abs=1/30) and record["manual_text_count"]==0
    sound=samples(media[1],disabled)
    for at in (.3,.9,1.3,2.3,2.7):
        for x,y in ((30,15),(50,40),(120,15),(80,75)):assert max(pixel(media[1],disabled,at,x,y))<12
        for hz in (440,880):assert tone_level(sound,at,hz)<.003
    assert content(store.load(pid))==before
    clip=store.load(pid)["manual"]["media_clips"][0]
    assert post(library_api,"media_set_enabled",clip_id=clip["id"],enabled=True).status_code==200
    enabled,restored=encoded("enable-recovered-only")
    assert restored["duration"]==pytest.approx(3.,abs=1/30)
    assert max(pixel(media[1],enabled,1.3,30,15))>90
    assert max(pixel(media[1],enabled,1.3,120,15))<12
    assert tone_level(samples(media[1],enabled),1.3,440)>.1
    assert post(library_api,"undo").status_code==200 and content(ProjectStore(settings).load(pid))==before
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}==hashes
    assert len(store.load(pid)["exports"])==2 and disabled.exists() and enabled.exists()
