"""Saved ASR alternatives for explicit caption review, never editorial approval.

The canonical analysis stays immutable. A selection is a caption-only layer,
bound to that source/transcript and the reviewed edit geometry. Moving footage
expires it instead of applying a partial transcript to unrelated speech.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any

FORMAT = "cutroom-caption-alternative/v1"
MAX_BYTES = 512 * 1024
EDIT_LAYERS = ("caption_corrections", "caption_overrides", "caption_override_anchors", "caption_dormant_overrides")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf8")).hexdigest()


def binding(project: dict[str, Any]) -> dict[str, Any]:
    analysis = project.get("analysis") or {}
    slot = str(analysis.get("audio_source") or "A").upper()
    source = (project.get("sources") or {}).get(slot) or {}
    if slot != "A" or analysis.get("audio_timeline_offset", 0) != 0:
        raise ValueError("Saved caption alternatives currently require analysed source A with original source timestamps.")
    if not source.get("generation") or not isinstance(analysis.get("transcript"), dict):
        raise ValueError("Analyse a versioned source before loading a caption alternative.")
    return {"slot": slot, "source_generation": source["generation"],
            "canonical_sha256": digest(analysis["transcript"])}


def geometry(project: dict[str, Any]) -> str:
    # Caption ownership depends on source/audio time mapping, not visual crops
    # or clip IDs introduced when a framing operation splits a continuous clip.
    from .caption_items import _pieces
    from .render import caption_context
    context = caption_context(project, aligned=False)
    pieces = _pieces(project, context["slot"], context["offset"], context["keeps"])
    return digest({"slot": context["slot"], "offset": context["offset"],
                   "pieces": [[round(n, 6) for n in p[:4]] for p in pieces],
                   "fps": (project.get("settings") or {}).get("fps")})


def _legacy_geometry(project: dict[str, Any]) -> str:
    """Read previously saved selections without changing their source binding."""
    manual, draft, settings = project.get("manual") or {}, project.get("draft") or {}, project.get("settings") or {}
    return digest({"manual": {k: manual.get(k) for k in ("source_tracks", "sequence", "cuts", "keeps", "keep_ranges", "source_mixer")},
                   "draft": {k: draft.get(k) for k in ("keep_ranges", "cuts", "audio_source", "sync_offset")},
                   "settings": {k: settings.get(k) for k in ("fps", "audio_source")}})


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Transcript timestamps must be finite numbers.")
    return float(value)


def register(project: dict[str, Any], value: Any) -> str:
    """Import only a bounded, explicitly source-bound local JSON transcript."""
    if not isinstance(value, dict) or value.get("format") != FORMAT:
        raise ValueError("Choose a source-bound CUTROOM caption alternative JSON file.")
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf8")) > MAX_BYTES:
        raise ValueError("A saved caption alternative must be no larger than 512 KiB.")
    current = binding(project)
    if value.get("binding") != current:
        raise ValueError("This alternative belongs to a different source or canonical transcript. Nothing was applied.")
    interval = value.get("source_interval")
    duration = float(project["sources"]["A"]["duration"])
    if not isinstance(interval, list) or len(interval) != 2:
        raise ValueError("The alternative must declare its original source interval.")
    left, right = map(_number, interval)
    if not 0 <= left < right <= duration + .001:
        raise ValueError("The alternative's source interval is outside this recording.")
    raw = value.get("transcript")
    rows = raw.get("segments") if isinstance(raw, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
        raise ValueError("The alternative must contain 1–1000 original ASR segments.")
    clean, seen, previous, count = [], set(), left, 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid transcript segment.")
        key, text = row.get("id"), row.get("text")
        start, end = _number(row.get("start")), _number(row.get("end"))
        if not isinstance(key, str) or not 1 <= len(key) <= 64 or key in seen:
            raise ValueError("ASR segments need unique original IDs of at most 64 characters.")
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError("ASR segments need nonempty text of at most 4000 characters.")
        if not left - .001 <= start < end <= right + .001 or start < previous - .001:
            raise ValueError("ASR segments must remain ordered inside the declared source interval.")
        words, word_start = [], start
        if not isinstance(row.get("words", []), list):
            raise ValueError("ASR words must be a list.")
        for word in row.get("words", []):
            if not isinstance(word, dict):
                raise ValueError("Invalid ASR word.")
            a, b, label = _number(word.get("start")), _number(word.get("end")), word.get("word")
            if not isinstance(label, str) or not label.strip() or len(label) > 256 or not start - .001 <= a < b <= end + .001 or a < word_start - .001:
                raise ValueError("ASR words need exact ordered timestamps inside their original segment.")
            entry = {"start": a, "end": b, "word": label}
            if isinstance(word.get("probability"), (int, float)) and not isinstance(word["probability"], bool) and math.isfinite(word["probability"]):
                entry["probability"] = max(0., min(1., word["probability"]))
            words.append(entry); word_start = a
        count += len(words)
        if count > 20_000:
            raise ValueError("This caption review exceeds the 20,000-word import limit.")
        clean.append({"id": key, "start": start, "end": end, "text": text, "words": words})
        seen.add(key); previous = start
    transcript = {"language": str(raw.get("language") or "unknown")[:32],
                  "model": str(raw.get("model") or "saved ASR").replace("\\", "/").rsplit("/", 1)[-1][:120], "segments": clean}
    saved = {"binding": current, "source_interval": [left, right], "transcript": transcript,
             "label": str(value.get("label") or "Saved alternative")[:80], "verified_by_listening": False}
    if value.get("scope") is not None:
        from .caption_ranges import selected_scope
        raw_scope=value["scope"]
        if not isinstance(raw_scope,dict) or not isinstance(raw_scope.get("timeline_range"),list) or len(raw_scope["timeline_range"])!=2:
            raise ValueError("Invalid selected caption scope.")
        scope=selected_scope(project,dict(zip(("start","end"),raw_scope["timeline_range"])))
        if scope!=raw_scope:raise ValueError("The selected source mapping changed. Generate or review again.")
        if [left,right]!=[min(p[2] for p in scope["pieces"]),max(p[3] for p in scope["pieces"])]:
            raise ValueError("Selected source bounds do not match the edit mapping.")
        if any(not any(p[2]-.001<=r["start"]<r["end"]<=p[3]+.001 for p in scope["pieces"]) for r in clean):
            raise ValueError("An ASR segment crosses a selected source cut.")
        saved["scope"]=scope
    key = digest(saved)
    registry = project.get("caption_alternatives") or {}
    if key not in registry and len(registry) >= 3:
        raise ValueError("This project already has three saved alternatives. Keep the current edit or use another project.")
    project.setdefault("caption_alternatives", {})[key] = saved
    return key


def status(project: dict[str, Any]) -> dict[str, Any]:
    selection = (project.get("manual") or {}).get("caption_alternative")
    if not isinstance(selection, dict):
        return {"active_id": "original", "state": "original"}
    saved = (project.get("caption_alternatives") or {}).get(selection.get("id"))
    try:
        valid = isinstance(saved, dict) and digest(saved) == selection.get("id") and saved["binding"] == binding(project) and selection.get("geometry") in {geometry(project), _legacy_geometry(project)}
    except (ValueError, TypeError, KeyError):
        valid = False
    if valid:
        return {"active_id": selection["id"], "state": "alternative", "label": saved["label"], "unverified": True}
    return {"active_id": "original", "state": "stale", "requested_id": selection.get("id"),
            "reason": "The source, transcript or edit changed. Original captions are active; review the alternative again."}


def caption_transcript(project: dict[str, Any]) -> dict[str, Any]:
    current = status(project)
    if current["active_id"] == "original":
        return (project.get("analysis") or {}).get("transcript") or {}
    saved = project["caption_alternatives"][current["active_id"]]
    if saved.get("scope"):
        return (project.get("analysis") or {}).get("transcript") or {}
    raw = saved["transcript"]
    view = copy.deepcopy(raw)
    # Native IDs remain stored untouched; namespace only the derived caption view
    # so corrections from another ASR version can never attach by coincident ID.
    for row in view["segments"]:
        row["id"] = f"alt:{current['active_id'][:16]}:{row['id']}"
    return view


def review(project: dict[str, Any], key: str) -> dict[str, Any]:
    from .caption_items import _pieces
    from .render import caption_context
    current = binding(project)
    if not isinstance(project.get("draft"), dict):
        raise ValueError("Open an edit before reviewing caption alternatives.")
    context = caption_context(project, aligned=False)
    if context["slot"] != "A":
        raise ValueError("Caption alternatives require the analysed source A audio.")
    pieces = _pieces(project, context["slot"], context["offset"], context["keeps"])
    ranges = [{"start": p[2], "end": p[3]} for p in pieces if p[3] > p[2]]
    if not ranges:
        raise ValueError("There is no source speech range in this edit.")
    saved = None if key == "original" else (project.get("caption_alternatives") or {}).get(key)
    if key != "original":
        if not isinstance(saved, dict) or digest(saved) != key or saved["binding"] != current:
            raise ValueError("This saved alternative is stale or missing. Nothing was applied.")
        left, right = saved["source_interval"]
        if saved.get("scope"):
            from .caption_ranges import selected_scope
            scope=saved["scope"]
            if selected_scope(project,dict(zip(("start","end"),scope["timeline_range"])))!=scope:
                raise ValueError("The selected edit mapping changed. Nothing was applied.")
            ranges=[{"start":p[2],"end":p[3]} for p in scope["pieces"]]
        elif any(r["start"] < left - .001 or r["end"] > right + .001 for r in ranges):
            raise ValueError("The saved transcript does not cover this whole edit. Trim to its source interval before applying.")
    def visible(transcript):
        return [{k: row[k] for k in ("id", "start", "end", "text")} for row in transcript.get("segments", [])
                if any(row["start"] < r["end"] and row["end"] > r["start"] for r in ranges)]
    manual = project.get("manual") or {}
    blocked=any(manual.get(k) for k in EDIT_LAYERS)
    blocked_reason="Existing caption edits are preserved. Undo conflicting edits before switching versions." if blocked else ""
    if saved and saved.get("scope"):
        from .caption_ranges import conflicts
        active=status(project)["active_id"]
        conflict=conflicts(project,saved["scope"])
        blocked=conflict or active not in {"original",key}
        blocked_reason="Manual caption edits overlap this range or have uncertain ownership. Nothing will be replaced." if conflict else "Undo the active alternative before applying a different selected-range alternative." if blocked else ""
    fingerprint = digest([current, geometry(project), key, {k: manual.get(k) for k in EDIT_LAYERS}])
    return {"id": key, "revision": project.get("revision"), "review_fingerprint": fingerprint,
            "label": saved["label"] if saved else "Original captions", "binding": current, "ranges": ranges,
            "duration": sum(r["end"] - r["start"] for r in ranges), "verified_by_listening": False,
            "original": visible((project.get("analysis") or {}).get("transcript") or {}),
            "alternative": visible(saved["transcript"]) if saved else [],
            "manual_caption_edits": blocked, "blocked_reason":blocked_reason, "scope": saved.get("scope") if saved else None}


def prepare_selection(project: dict[str, Any], key: str, fingerprint: str) -> dict[str, Any] | None:
    proposal = review(project, key)
    if fingerprint != proposal["review_fingerprint"]:
        raise ValueError("The reviewed caption proposal changed. Open it again; nothing was applied.")
    selection = None if key == "original" else {"id": key, "geometry": geometry(project)}
    existing = (project.get("manual") or {}).get("caption_alternative")
    if existing == selection:
        return None
    if proposal["manual_caption_edits"]:
        raise ValueError(proposal.get("blocked_reason") or "Existing caption edits are preserved. Undo those edits before switching transcript versions.")
    return selection or {}
