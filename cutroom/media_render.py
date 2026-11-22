"""Compile project-local library clips on the final edit clock."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .layer_tracks import validate_layer_tracks, ordered_layer_clips, layer_audio_gain
from .composition import source_chroma_key
from .effects import build_chroma_key_nodes
from .frame_rates import first_display_frame as _first_display_frame, project_export_fps
from .render_inventory import RenderInputInventory, audible as _audible, compile_render_inputs, library_clips, library_picture_end, library_visual_start


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def library_has_audio(project: dict[str, Any]) -> bool:
    return any(_audible(clip, asset) for clip, asset in library_clips(project))


def library_input_args(project: dict[str, Any], project_dir: Path,
                       input_inventory: RenderInputInventory | None = None) -> list[str]:
    """Only open validated local asset paths, in the same order as the graph."""
    inventory = input_inventory or compile_render_inputs(project, include_chroma=False)
    inventory.validate(project, require_chroma=False)
    return inventory.input_args(project_dir, category="library")


def _gain(mixer: dict[str, Any], role: str) -> float:
    return 0.0 if mixer.get(f"{role}_muted") else 10 ** (max(-60, min(12, _number(mixer.get(f"{role}_db")))) / 20)


def master_gain_db(project: dict[str, Any]) -> float:
    return max(-60, min(12, _number(((project.get("manual") or {}).get("audio_mixer") or {}).get("master_db"))))


def append_media_graph(
    project: dict[str, Any], width: int, height: int, duration: float,
    video_label: str, audio_label: str | None,
    *, chroma_background_labels: dict[str, str] | None = None,
    input_inventory: RenderInputInventory | None = None,
) -> tuple[list[str], str, str | None]:
    tracked = validate_layer_tracks(project) is not None
    inventory = input_inventory or compile_render_inputs(project, include_chroma=False)
    inventory.validate(project, require_chroma=False)
    inputs = inventory.inputs("library")
    clips = [(entry.clip, entry.media) for entry in inputs]
    mixer = (project.get("manual") or {}).get("audio_mixer") or {}
    if not clips and not mixer:
        return [], video_label, audio_label
    fps = project_export_fps(project)
    filters: list[str] = []
    # Each occurrence has an independent decoded input and clip clock. Split a
    # selected still image once so duplicated uses cannot consume its label twice.
    backgrounds: dict[int, str] = {}
    image_labels = chroma_background_labels or {}
    for target in dict.fromkeys(clip.get("asset_id") for clip, _ in clips):
        config = source_chroma_key(project, target)
        if not config["enabled"] or config["background_mode"] == "transparent" or config["background_asset_id"] is None:
            continue
        label = image_labels.get(target)
        if label is None:
            raise ValueError("The selected video Chroma Key background input is unavailable")
        indices = [index for index, (clip, _) in enumerate(clips) if clip.get("asset_id") == target]
        if len(indices) > 1:
            outputs = [f"[libchromaimage{index}]" for index in indices]
            filters.append(f"{label}split={len(indices)}{''.join(outputs)}")
            backgrounds.update(zip(indices, outputs))
        else:
            backgrounds[indices[0]] = label
    # Decode/input/audio order stays byte-for-byte in saved occurrence order.
    # Only the visual overlay chain is ordered by user-owned visual tracks.
    visual_overlays = {}
    track_mixed = ((project.get("manual") or {}).get("layer_tracks") or {}).get("version") == 3
    audible_voice = False
    track_muted_voice = False
    audio_roles: dict[str, list[str]] = {role: [] for role in ("source", "music", "effects", "voice")}
    if audio_label:
        filters.append(f"{audio_label}aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                       f"apad,atrim=duration={duration:.9f},asetpts=N/48000/TB[libsource]")
        audio_roles["source"].append("[libsource]")
    for index, (clip, asset) in enumerate(clips):
        start = max(0.0, min(duration, _number(clip.get("start"))))
        end = max(start, min(duration, _number(clip.get("end"))))
        length = end - start
        if length < 1 / fps - 1e-8:
            continue
        source_start = max(0.0, _number(clip.get("source_start"))) - inputs[index].seek_start
        input_index = inputs[index].index
        fade_in = max(0.0, min(length, _number(clip.get("fade_in"))))
        fade_out = max(0.0, min(length, _number(clip.get("fade_out"))))
        if asset["kind"] in {"video", "image"}:
            speed = max(0.25, min(4.0, _number(clip.get("speed"), 1)))
            first, last = _first_display_frame(start, fps), _first_display_frame(end, fps)
            # Start the decoded picture on the first covered timeline frame. An
            # off-grid outside edge does not buy a whole extra source frame.
            visual_start = library_visual_start(clip, asset, fps)
            if asset["kind"] == "video" and abs(first / fps - start) > 5.1e-10:
                visual_start += max(0., first / fps - start) * speed
                limit = library_picture_end(asset) or _number(asset.get("duration"))
                if limit > 0:
                    visual_start = min(visual_start, max(0., limit - 1e-6))
            visual_start -= inputs[index].seek_start
            target_w = max(2, min(width, int(round(width * max(0.01, min(1.0, _number(clip.get("w"), 1))))) // 2 * 2))
            target_h = max(2, min(height, int(round(height * max(0.01, min(1.0, _number(clip.get("h"), 1))))) // 2 * 2))
            x = int(round(max(0.0, min(1.0, _number(clip.get("x")))) * width))
            y = int(round(max(0.0, min(1.0, _number(clip.get("y")))) * height))
            x, y = min(width - target_w, x), min(height - target_h, y)
            fit = (f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                   f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=black"
                   if clip.get("fit", "cover") == "contain" else
                   f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}")
            frames = max(1, last - first)
            visual_input = f"[{input_index}:v]"
            config = source_chroma_key(project, clip.get("asset_id")) if asset["kind"] == "video" else None
            if config and config["enabled"]:
                native_w = max(2, int(asset["width"]) // 2 * 2)
                native_h = max(2, int(asset["height"]) // 2 * 2)
                output = f"[libchromasource{index}]"
                filters.extend(build_chroma_key_nodes(
                    visual_input, output, config, native_w, native_h, fps,
                    max(1 / fps, _number(asset.get("duration"))), prefix=f"libchroma{index}",
                    background_label=backgrounds.get(index),
                ))
                visual_input = output
            if config and config["enabled"] and config["background_mode"] == "transparent":
                # Keep alpha through fit/motion until the overlay meets the edit
                # beneath it. Opaque padding or zoompan's YUV output would hide it.
                fit = fit.replace("color=black", "color=black@0")
            if asset["kind"] == "video":
                # Sample the continuous source clock, not the first decoded
                # frame after a cut. Restarting at that frame quantizes the
                # phase a second time and can alter retained footage outside an
                # overwrite. Negative input PTS carry the predecessor of In.
                upper_source = visual_start + (length + 2 / fps) * speed
                source_duration = library_picture_end(asset)
                native = f"{visual_input}trim=end={upper_source:.9f},"
                if source_duration <= 0 or upper_source + inputs[index].seek_start >= source_duration:
                    # Pad before resampling: an actual last frame can be less
                    # than one output-frame interval long. A post-fps clone
                    # alone would freeze its predecessor instead. Immediately
                    # bound the native pad to this occurrence's needed window.
                    pad = source_duration + (length + 2 / fps) * speed if source_duration > 0 else upper_source + 1 / fps
                    native += (f"tpad=stop_mode=clone:stop_duration={pad:.9f},"
                               f"trim=end={upper_source:.9f},")
                # Four nanoseconds absorb rescaling noise at mathematically aligned CFR boundaries.
                sample = (f"{native}settb=1/1000000000,setpts=(PTS-{visual_start:.9f}/TB)/{speed:.9f}-4,"
                          f"fps={fps}:start_time=0:round=up")
            else:
                sample = f"{visual_input}trim=start={visual_start:.9f}:end={visual_start + length * speed + 1 / fps:.9f},setpts=PTS-STARTPTS,fps={fps}"
            visual = (f"{sample},{fit},setsar=1,"
                      f"tpad=stop_mode=clone:stop_duration={length + 2 / fps:.9f},trim=end_frame={frames},settb=1/{fps},setpts=N")
            motion = clip.get("motion", "none")
            if motion == "zoom_in":
                if config and config["enabled"] and config["background_mode"] == "transparent":
                    zoom = f"(1+0.12*min(n/{max(1, length * fps):.9f},1))"
                    visual += (f",scale=w='ceil({target_w}*{zoom}/2)*2':h='ceil({target_h}*{zoom}/2)*2':eval=frame,"
                               f"crop={target_w}:{target_h}:(iw-ow)/2:(ih-oh)/2")
                else:
                    visual += (f",zoompan=z='1+0.12*min(on/{max(1, length * fps):.9f},1)':"
                               f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={target_w}x{target_h}:fps={fps}")
            elif motion == "pan":
                pan_w = int(math.ceil(target_w * 1.12 / 2)) * 2
                pan_h = int(math.ceil(target_h * 1.12 / 2)) * 2
                visual += f",scale={pan_w}:{pan_h},crop={target_w}:{target_h}:x='(iw-ow)*min(n/{max(1, length * fps):.9f},1)':y='(ih-oh)/2'"
            visual += ",format=rgba"
            opacity = clip.get("opacity_percent", 100)
            if opacity != 100:
                # Multiply the alpha generated by the source/key/fit/motion;
                # never replace per-pixel alpha or disable the sound input.
                visual += f",colorchannelmixer=aa={opacity / 100:.2f}"
            # A stored decimal frame edge may sit half a nanosecond either side
            # of the exact CFR timestamp. Never truncate a frame-aligned delay
            # one tick early, or let FFmpeg's seconds comparison expose a gap.
            visual += f",settb=1/{fps},setpts=N+{first}[libvideo{index}]"
            filters.append(visual)
            lower, upper = (first - .5) / fps, (last - .5) / fps
            overlay = (f"[libvideo{index}]overlay=x={x}:y={y}:eof_action=pass:repeatlast=0:"
                       f"enable='gte(t,{lower:.9f})*lt(t,{upper:.9f})'[libcomposite{index}]")
            if tracked:
                visual_overlays[clip["id"]] = (overlay, f"[libcomposite{index}]")
            else:
                filters.append(f"{video_label}{overlay}")
                video_label = f"[libcomposite{index}]"
        if _audible(clip, asset):
            role = clip.get("role", "music")
            if role not in {"music", "effects", "voice"}:
                role = "music"
            gain = 0.0 if clip.get("muted") else 10 ** (max(-60, min(12, _number(clip.get("volume_db")))) / 20)
            track_gain = layer_audio_gain(project, clip)
            if role == "voice" and track_gain == 0:
                track_muted_voice = True
            gain *= track_gain
            if role == "voice" and gain > 0:
                audible_voice = True
            # Picture speed never retimes speech or a music/effects recording.
            audio = (f"[{input_index}:a]atrim=start={source_start:.9f}:end={source_start + length:.9f},"
                     "asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     f"apad,atrim=duration={length:.9f},volume={gain:.9f}")
            if fade_in:
                audio += f",afade=t=in:st=0:d={fade_in:.9f}"
            if fade_out:
                audio += f",afade=t=out:st={length - fade_out:.9f}:d={fade_out:.9f}"
            # Delay can emit leading silence before its first timestamped
            # input frame. Establish the sample clock before a time-based trim
            # can discard that padding and pull speech earlier in the edit.
            audio += f",adelay={round(start * 48000)}S:all=1,asetpts=N/48000/TB,apad,atrim=duration={duration:.9f},asetpts=N/48000/TB[libaudio{index}]"
            filters.append(audio)
            audio_roles[role].append(f"[libaudio{index}]")
    if tracked:
        for clip in ordered_layer_clips(project, "visual"):
            if clip["id"] in visual_overlays:
                overlay, output_label = visual_overlays[clip["id"]]
                filters.append(f"{video_label}{overlay}")
                video_label = output_label
    def aligned(labels: list[str], name: str) -> list[str]:
        # FFmpeg 6.1 amix drops an input after a short frame (the uneven
        # piece edges of a source track); fixed-size frames keep it mixed.
        if len(labels) < 2:
            return labels
        out = []
        for position, label in enumerate(labels):
            filters.append(f"{label}asetnsamples=n=1024:p=0[lib{name}al{position}]")
            out.append(f"[lib{name}al{position}]")
        return out

    buses: dict[str, str] = {}
    for role, labels in audio_roles.items():
        if not labels:
            continue
        labels = aligned(labels, role)
        mix = f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0" if len(labels) > 1 else "anull"
        filters.append(f"{''.join(labels)}{mix},volume={_gain(mixer, role):.9f}[libbus{role}]")
        buses[role] = f"[libbus{role}]"
    speech_roles = [role for role in ("source", "voice") if role in buses and _gain(mixer, role) > 0
                    and not (track_mixed and role == "voice" and track_muted_voice and not audible_voice)]
    if mixer.get("ducking") and "music" in buses and speech_roles:
        speech_keys = []
        for role in speech_roles:
            filters.append(f"{buses[role]}asplit=2[libdry{role}][libkey{role}]")
            buses[role] = f"[libdry{role}]"
            speech_keys.append(f"[libkey{role}]")
        key_mix = f"amix=inputs={len(speech_keys)}:normalize=0" if len(speech_keys) > 1 else "anull"
        filters.append(f"{''.join(speech_keys)}{key_mix}[libduckkey]")
        filters.append(f"{buses['music']}[libduckkey]sidechaincompress=threshold=0.025:ratio=8:attack=20:release=350[libducked]")
        buses["music"] = "[libducked]"
    if buses:
        labels = aligned(list(buses.values()), "bus")
        mix = f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0" if len(labels) > 1 else "anull"
        # When loudness normalization is enabled, apply the master fader after it.
        normalize = bool(((project.get("draft") or {}).get("audio_policy") or {}).get("normalize"))
        gain = 1.0 if normalize else 10 ** (master_gain_db(project) / 20)
        filters.append(f"{''.join(labels)}{mix},volume={gain:.9f},alimiter=limit=0.98:level=0:latency=1,"
                       f"apad,atrim=duration={duration:.9f},asetpts=N/48000/TB[libmix]")
        audio_label = "[libmix]"
    return filters, video_label, audio_label
