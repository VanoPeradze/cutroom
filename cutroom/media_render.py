"""Compile project-local library clips on the final edit clock."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .frame_rates import project_export_fps


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def library_clips(project: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows = (project.get("manual") or {}).get("media_clips") or []
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError("The media timeline must contain at most 200 clips")
    assets = project.get("assets") or {}
    result = []
    for clip in rows:
        if not isinstance(clip, dict):
            raise ValueError("Invalid library clip")
        asset = assets.get(clip.get("asset_id")) if isinstance(assets, dict) else None
        if not isinstance(asset, dict) or asset.get("kind") not in {"video", "image", "audio"}:
            raise ValueError("A timeline asset is missing; remove its clip or import it again")
        if asset.get("status", "ready") != "ready":
            raise ValueError("Wait until timeline media finishes importing before exporting")
        result.append((clip, asset))
    return result


def _audible(clip: dict[str, Any], asset: dict[str, Any]) -> bool:
    return asset["kind"] == "audio" or asset["kind"] == "video" and bool(asset.get("has_audio")) and bool(clip.get("audio_enabled", False))


def library_has_audio(project: dict[str, Any]) -> bool:
    return any(_audible(clip, asset) for clip, asset in library_clips(project))


def library_input_args(project: dict[str, Any], project_dir: Path) -> list[str]:
    """Only open validated local asset paths, in the same order as the graph."""
    result: list[str] = []
    root = project_dir.resolve()
    fps = project_export_fps(project)
    for clip, asset in library_clips(project):
        path_value = asset.get("path") or asset.get("relative_path")
        if not isinstance(path_value, str) or not path_value:
            raise ValueError("The timeline asset has no local media path")
        path = (root / path_value).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Timeline media must belong to this project")
        if not path.is_file():
            raise FileNotFoundError(f"Timeline media is missing: {path.name}")
        if asset["kind"] == "image":
            length = max(1 / fps, _number(clip.get("end")) - _number(clip.get("start")))
            result += ["-loop", "1", "-framerate", str(fps), "-t", f"{length + 2 / fps:.9f}"]
        result += ["-protocol_whitelist", "file,pipe", "-i", str(path)]
    return result


def _gain(mixer: dict[str, Any], role: str) -> float:
    return 0.0 if mixer.get(f"{role}_muted") else 10 ** (max(-60, min(12, _number(mixer.get(f"{role}_db")))) / 20)


def master_gain_db(project: dict[str, Any]) -> float:
    return max(-60, min(12, _number(((project.get("manual") or {}).get("audio_mixer") or {}).get("master_db"))))


def append_media_graph(
    project: dict[str, Any], width: int, height: int, duration: float,
    video_label: str, audio_label: str | None,
) -> tuple[list[str], str, str | None]:
    clips = library_clips(project)
    mixer = (project.get("manual") or {}).get("audio_mixer") or {}
    if not clips and not mixer:
        return [], video_label, audio_label
    fps = project_export_fps(project)
    first_input = 2 if (project.get("sources") or {}).get("B") else 1
    filters: list[str] = []
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
        source_start = max(0.0, _number(clip.get("source_start")))
        input_index = first_input + index
        fade_in = max(0.0, min(length, _number(clip.get("fade_in"))))
        fade_out = max(0.0, min(length, _number(clip.get("fade_out"))))
        if asset["kind"] in {"video", "image"}:
            speed = max(0.25, min(4.0, _number(clip.get("speed"), 1)))
            visual_start = max(0.0, _number(clip.get("video_source_start"), source_start)) if asset["kind"] == "video" else 0.0
            if asset["kind"] == "video" and _number(asset.get("duration")) > 0:
                visual_start = min(visual_start, max(0.0, _number(asset.get("duration")) - 1 / fps))
            target_w = max(2, min(width, int(round(width * max(0.01, min(1.0, _number(clip.get("w"), 1))))) // 2 * 2))
            target_h = max(2, min(height, int(round(height * max(0.01, min(1.0, _number(clip.get("h"), 1))))) // 2 * 2))
            x = int(round(max(0.0, min(1.0, _number(clip.get("x")))) * width))
            y = int(round(max(0.0, min(1.0, _number(clip.get("y")))) * height))
            x, y = min(width - target_w, x), min(height - target_h, y)
            fit = (f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                   f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=black"
                   if clip.get("fit", "cover") == "contain" else
                   f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}")
            frames = max(1, round(length * fps))
            visual = (f"[{input_index}:v]trim=start={visual_start:.9f}:end={visual_start + length * speed + 1 / fps:.9f},"
                      f"setpts=(PTS-STARTPTS)/{speed:.9f},fps={fps},{fit},setsar=1,"
                      f"tpad=stop_mode=clone:stop_duration={length + 2 / fps:.9f},trim=end_frame={frames},setpts=N/{fps}/TB")
            motion = clip.get("motion", "none")
            if motion == "zoom_in":
                visual += (f",zoompan=z='1+0.12*min(on/{max(1, length * fps):.9f},1)':"
                           f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={target_w}x{target_h}:fps={fps}")
            elif motion == "pan":
                pan_w = int(math.ceil(target_w * 1.12 / 2)) * 2
                pan_h = int(math.ceil(target_h * 1.12 / 2)) * 2
                visual += f",scale={pan_w}:{pan_h},crop={target_w}:{target_h}:x='(iw-ow)*min(n/{max(1, length * fps):.9f},1)':y='(ih-oh)/2'"
            visual += ",format=rgba"
            visual += f",setpts=PTS+{start:.9f}/TB[libvideo{index}]"
            filters.append(visual)
            filters.append(f"{video_label}[libvideo{index}]overlay=x={x}:y={y}:eof_action=pass:repeatlast=0:"
                           f"enable='gte(t,{start:.9f})*lt(t,{end:.9f})'[libcomposite{index}]")
            video_label = f"[libcomposite{index}]"
        if _audible(clip, asset):
            role = clip.get("role", "music")
            if role not in {"music", "effects", "voice"}:
                role = "music"
            gain = 0.0 if clip.get("muted") else 10 ** (max(-60, min(12, _number(clip.get("volume_db")))) / 20)
            # Picture speed never retimes speech or a music/effects recording.
            audio = (f"[{input_index}:a]atrim=start={source_start:.9f}:end={source_start + length:.9f},"
                     "asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     f"apad,atrim=duration={length:.9f},volume={gain:.9f}")
            if fade_in:
                audio += f",afade=t=in:st=0:d={fade_in:.9f}"
            if fade_out:
                audio += f",afade=t=out:st={length - fade_out:.9f}:d={fade_out:.9f}"
            audio += f",adelay={round(start * 48000)}S:all=1,apad,atrim=duration={duration:.9f},asetpts=N/48000/TB[libaudio{index}]"
            filters.append(audio)
            audio_roles[role].append(f"[libaudio{index}]")
    buses: dict[str, str] = {}
    for role, labels in audio_roles.items():
        if not labels:
            continue
        mix = f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0" if len(labels) > 1 else "anull"
        filters.append(f"{''.join(labels)}{mix},volume={_gain(mixer, role):.9f}[libbus{role}]")
        buses[role] = f"[libbus{role}]"
    speech_roles = [role for role in ("source", "voice") if role in buses and _gain(mixer, role) > 0]
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
        labels = list(buses.values())
        mix = f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0" if len(labels) > 1 else "anull"
        # When loudness normalization is enabled, apply the master fader after it.
        normalize = bool(((project.get("draft") or {}).get("audio_policy") or {}).get("normalize"))
        gain = 1.0 if normalize else 10 ** (master_gain_db(project) / 20)
        filters.append(f"{''.join(labels)}{mix},volume={gain:.9f},alimiter=limit=0.98:level=0:latency=1,"
                       f"apad,atrim=duration={duration:.9f},asetpts=N/48000/TB[libmix]")
        audio_label = "[libmix]"
    return filters, video_label, audio_label
