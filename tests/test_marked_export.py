"""Proofs for non-destructive, frame-addressed exports of the finished timeline."""
import copy
import json
import math
import subprocess
import threading

import pytest

from cutroom.editing import apply_manual_edit
from cutroom.jobs import Job, JobContext
from cutroom.range_export import ExportRange, RangeExportError, validate_range
from cutroom.render import render_project, resolve_export_range
from test_media_render import media, samples
from test_track_destination_render import prepared


def spec(a=21, b=64, fps=30, revision=7):
    return dict(start_frame=a, end_frame=b, fps=fps, expected_revision=revision)


@pytest.mark.parametrize("fps", [24, 25, 30, 50, 60])
def test_one_frame_at_the_end_and_exact_pcm_bounds(fps):
    r = validate_range(spec(fps-1, fps, fps), fps=fps, revision=7, total_frames=fps)
    assert r.duration == 1/fps and r.end == 1
    assert f"start_sample={48000-48000//fps}:end_sample=48000" in r.audio_trim()


@pytest.mark.parametrize("bad", [None, {}, [], spec(-1), spec(0, 0), spec(10, 9),
                          spec(1, 91), spec(True), spec(1.5), spec("1"), spec(fps=29),
                          spec(revision=True), {**spec(), "mode":"full"}])
def test_invalid_never_defaults_to_entire_timeline(bad):
    with pytest.raises(RangeExportError):
        validate_range(bad, fps=30, revision=7, total_frames=90)


@pytest.mark.parametrize("bad", [spec(revision=6), spec(fps=25)])
def test_stale_has_distinct_error(bad):
    with pytest.raises(RangeExportError) as e:
        validate_range(bad, fps=30, revision=7, total_frames=90)
    assert e.value.stale


def test_intersections_are_half_open_unrounded_and_nonmutating():
    scope = ExportRange(15, 60, 30)
    rows = [dict(start=0., end=.5, text="before"), dict(start=.2, end=.8, text="left"),
            dict(start=1.9, end=2.5, text="right"), dict(start=2., end=3., text="after")]
    before = copy.deepcopy(rows)
    clipped = scope.rows(rows)
    assert [r["text"] for r in clipped] == ["left", "right"]
    assert [r["start"] for r in clipped] == pytest.approx([0., 1.4])
    assert [r["end"] for r in clipped] == pytest.approx([.3, 1.5])
    assert rows == before and scope.gaps([(0., 3.)]) == [(0., 1.5)]
    assert resolve_export_range({}, {}) is None


def frames(ffmpeg, path):
    # Small luma frames preserve text position, timing and composited layers while
    # ignoring the non-deterministic quantizer differences of separately encoded GOPs.
    buf = subprocess.check_output([ffmpeg, "-v","error","-i",str(path),"-an",
        "-vf","scale=80:46","-pix_fmt","gray","-f","rawvideo","pipe:1"], timeout=25)
    stride = 80 * 46
    assert len(buf) % stride == 0
    return [buf[i:i+stride] for i in range(0, len(buf), stride)]


@pytest.mark.parametrize("normalize", [False, True])
def test_real_mp4_matches_full_composite_mix_and_captions(media, tmp_path, normalize, monkeypatch):
    p, store, settings, _, originals_unchanged = prepared(media, tmp_path)
    settings.raw["ffmpeg_threads"] = 2
    p["draft"]["audio_policy"] = {"normalize": normalize, "target_lufs": -16}
    for word, a, b in [("BEFORE",0.,.5),("IN",.5,1.),("OUT",1.8,2.6),("AFTER",2.6,3.)]:
        apply_manual_edit(p, {"action":"text_add", "kind":"caption", "text":word, "start":a, "end":b})
    store.save(p)
    pid = p["id"]
    before = store.load(pid)
    stages=[]
    import cutroom.render as renderer
    runner=renderer._run_ffmpeg_process
    def inspect_stage(ctx, command, duration):
        if "-i" in command and str(command[command.index("-i")+1]).endswith(".render-stage.mov"):
            stage=command[command.index("-i")+1]
            rows=json.loads(subprocess.check_output([media[2],"-v","error","-count_frames","-show_entries",
                "stream=codec_type,codec_name,nb_read_frames,duration","-of","json",stage]))["streams"]
            stages.append({s["codec_type"]:s for s in rows})
        return runner(ctx,command,duration)
    monkeypatch.setattr(renderer,"_run_ffmpeg_process",inspect_stage)
    def encode(scope):
        opts = {"_force_software":True, "quality":"fast"}
        if scope:
            opts["range"] = spec(*scope, revision=store.load(pid)["revision"])
        ctx = JobContext(Job("range-test","render",pid),threading.Lock())
        rec = render_project(ctx,pid,store,settings,opts)["export"]
        path = settings.exports_dir / rec["name"]
        return rec,path

    full, whole = encode(None)
    excerpt, part = encode((21, 64))  # 0.700..2.1333 s; crosses cameras, trims, titles and mixed assets
    assert "range" not in full and excerpt["range"] == {"start_frame":21,"end_frame":64,"fps":30}
    assert "-range-21-64-" in part.name
    assert excerpt["input_fingerprint"] != full["input_fingerprint"]
    assert excerpt["captions_burned"] and excerpt["manual_text_count"] < full["manual_text_count"]
    pictures, window = frames(media[1],whole), frames(media[1],part)
    expected = pictures[21:64]
    assert len(pictures)==90 and len(window)==len(expected)==43
    errors=[sum(abs(a-b) for a,b in zip(ref,out)) / len(ref) for ref,out in zip(expected,window)]
    assert max(errors)<5., errors
    # Ignore the first/last two AAC packets where separately encoded excerpts have different context.
    x,y = samples(media[1],whole), samples(media[1],part)
    length=43*1600
    x=x[21*1600+2048:21*1600+length-2048];y=y[2048:length-2048]
    assert len(x)==len(y)>60_000
    xy=sum(a*b for a,b in zip(x,y));xx=sum(a*a for a in x);yy=sum(b*b for b in y)
    corr=xy/math.sqrt(xx*yy);ratio=math.sqrt(yy/xx)
    assert corr>.985 and .98<ratio<1.02, (corr,ratio)
    srt=part.with_suffix(".srt").read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:00,300\nIN" in srt
    assert "00:00:01,100 --> 00:00:01,433\nOUT" in srt
    assert "BEFORE" not in srt and "AFTER" not in srt
    probe=json.loads(subprocess.check_output([media[2],"-v","error","-count_frames","-show_entries",
        "stream=codec_type,start_time,duration,nb_read_frames,avg_frame_rate","-of","json",str(part)]))
    streams={s["codec_type"]:s for s in probe["streams"]}
    assert int(streams["video"]["nb_read_frames"])==43 and streams["video"]["avg_frame_rate"]=="30/1"
    assert float(streams["video"]["start_time"]) == float(streams["audio"]["start_time"]) == 0
    assert abs(float(streams["audio"]["duration"])-43/30)<.002
    # AAC trailing padding is not content; the timestamped stream has the specified duration.
    after=store.load(pid)
    for key in ("sources","assets","settings","manual","draft","analysis"):
        assert before[key]==after[key], key
    assert len(after["exports"])==len(before["exports"])+2
    if normalize:
        assert [int(s["video"]["nb_read_frames"]) for s in stages]==[90,43]
        assert all(s["audio"]["codec_name"]=="pcm_s24le" and float(s["audio"]["duration"])==3. for s in stages)
    else:
        assert not stages
    originals_unchanged()
    print(json.dumps(dict(normalized=normalize,frames=len(window),max_luma_error=round(max(errors),4),
          audio_correlation=round(corr,7),audio_rms_ratio=round(ratio,7),stream_durations={
          k:v["duration"] for k,v in streams.items()},public=excerpt["range"])))


@pytest.mark.parametrize("fps", [24, 25, 30, 50, 60])
def test_final_single_frame_of_silent_video_is_a_real_one_frame_mp4(media,tmp_path,fps):
    from cutroom.projects import ProjectStore
    p,store,settings,_,unchanged=prepared(media,tmp_path)
    src=p["sources"]["A"]
    p["sources"]={"A":{**src,"has_audio":False}}
    p["assets"]={};p["manual"]={};p["analysis"]={}
    p["draft"]={"keep_ranges":[{"start":0.,"end":3.}], "camera_plan":[{"start":0.,"end":3.,"camera":"A"}]}
    p["settings"].update(fps=fps,audio_source="A",captions=False,burn_captions=False)
    settings.raw["ffmpeg_threads"]=2
    store.save(p); pid=p["id"]; projects=ProjectStore(settings)
    result=render_project(JobContext(Job("last-frame","render",pid),threading.Lock()),pid,projects,settings,
        {"_force_software":True,"range":spec(3*fps-1,3*fps,fps,projects.load(pid)["revision"])})["export"]
    out=settings.exports_dir/result["name"]
    streams=json.loads(subprocess.check_output([media[2],"-v","error","-count_frames","-show_entries",
        "stream=codec_type,nb_read_frames,start_time,duration,avg_frame_rate","-of","json",str(out)]))["streams"]
    assert [s["codec_type"] for s in streams]==["video"]
    s=streams[0]
    assert (s["nb_read_frames"],s["avg_frame_rate"],s["start_time"])==("1",f"{fps}/1","0.000000")
    assert float(s["duration"]) == pytest.approx(1/fps, abs=1e-6)
    unchanged()


def test_api_rejects_malformed_stale_empty_or_out_of_bounds_before_any_job(media,tmp_path):
    from server import create_app
    p,store,settings,_,unchanged=prepared(media,tmp_path)
    app=create_app(settings); app.config.update(TESTING=True); client=app.test_client()
    path=f"/api/projects/{p['id']}"
    rev=store.load(p["id"])["revision"]
    before=store.load(p["id"])
    for payload,code,reason in [(None,400,"invalid_export_range"),(spec(2,2,revision=rev),400,"invalid_export_range"),
            (spec(0,91,revision=rev),400,"invalid_export_range"),(spec(1,20,revision=rev+1),409,"range_changed"),
            (spec(1,20,fps=25,revision=rev),409,"range_changed")]:
        response=client.post(path+"/render",json={"range":payload})
        assert (response.status_code,response.get_json()["error"])==(code,reason)
    assert store.load(p["id"])==before and not list(settings.exports_dir.iterdir())
    unchanged()


@pytest.mark.parametrize("normalize", [False, True])
def test_range_storage_sizes_the_excerpt_but_retains_full_mix_and_graph_allowances(media,tmp_path,normalize):
    import cutroom.render as renderer
    p,store,settings,_,unchanged=prepared(media,tmp_path)
    p["draft"]["audio_policy"]={"normalize":normalize}
    whole=renderer.ensure_render_storage(p,settings,store.project_dir(p["id"]))
    r=spec(21,64,revision=p["revision"])
    part=renderer.ensure_render_storage(p,settings,store.project_dir(p["id"]),{"range":r})
    assert part["duration_seconds"]==43/30 and whole["duration_seconds"]==3
    for k in ("video_bytes","audio_bytes","output_bytes","export_work_bytes"):
        assert 0 < part[k] < whole[k]
    for k in ("filter_graph_bytes","caption_ass_bytes","project_commit_bytes","project_work_bytes","reserve_bytes"):
        assert part[k]==whole[k]
    if normalize:
        assert part["normalization_stage_bytes"]-part["output_bytes"]+part["audio_bytes"]==3*renderer.STAGE_PCM_BYTES_PER_SECOND
    else:
        assert part["normalization_stage_bytes"]==0
    unchanged()


def test_admission_rechecks_after_a_concurrent_saved_change_and_worker_checks_again(media,tmp_path,monkeypatch):
    import server
    p,store,settings,_,unchanged=prepared(media,tmp_path)
    app=server.create_app(settings); client=app.test_client();pid=p["id"]
    old={"range":spec(0,1,revision=store.load(pid)["revision"])}
    preflight=server.ensure_render_storage
    def concurrent_save(*args,**kwargs):
        result=preflight(*args,**kwargs)
        store.update(pid,lambda latest:latest.update(name="Renamed during preflight"))
        return result
    monkeypatch.setattr(server,"ensure_render_storage",concurrent_save)
    response=client.post(f"/api/projects/{pid}/render",json=old)
    assert (response.status_code,response.get_json()["error"])==(409,"range_changed")
    with pytest.raises(RangeExportError,match="changed"):
        render_project(JobContext(Job("stale","render",pid),threading.Lock()),pid,store,settings,old)
    assert not list(settings.exports_dir.iterdir()) and not store.load(pid)["exports"]
    unchanged()
