from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Any, Callable

from .composition import FACE_LAYOUT_VERSION


VISION_ANALYSIS_VERSION = FACE_LAYOUT_VERSION


def normalized_vision_sample_count(value: Any, fallback: int) -> int:
    """Return the bounded number of frames used by every vision entry point."""

    try:
        parsed = int(fallback if isinstance(value, bool) else value)
    except (TypeError, ValueError, OverflowError):
        parsed = int(fallback)
    return max(10, min(56, parsed))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def _distance(a: dict[str, float], b: dict[str, float]) -> float:
    return math.hypot(float(a["cx"]) - float(b["cx"]), float(a["cy"]) - float(b["cy"]))


def _cluster_face_detections(detections: list[dict[str, float]], samples: int) -> list[dict[str, Any]]:
    """Cluster face detections by stable screen position.

    Embedded facecams are usually small and stay in one corner for most of the
    recording. A normal game/video scene can contain larger transient faces. The
    old implementation kept only the largest face from every sampled frame, which
    systematically preferred gameplay characters over the creator's camera box.
    """
    clusters: list[list[dict[str, float]]] = []
    for detection in sorted(detections, key=lambda item: (item.get("sample", 0), item.get("time", 0))):
        best_index: int | None = None
        best_distance = 999.0
        for index, cluster in enumerate(clusters):
            center = {
                "cx": statistics.median(item["cx"] for item in cluster),
                "cy": statistics.median(item["cy"] for item in cluster),
                "w": statistics.median(item["w"] for item in cluster),
                "h": statistics.median(item["h"] for item in cluster),
            }
            distance = _distance(detection, center)
            tolerance = max(0.07, min(0.18, 1.8 * max(center["w"], center["h"])))
            size_ratio = max(
                detection["w"] / max(center["w"], 1e-6),
                center["w"] / max(detection["w"], 1e-6),
                detection["h"] / max(center["h"], 1e-6),
                center["h"] / max(detection["h"], 1e-6),
            )
            if distance <= tolerance and size_ratio <= 2.4 and distance < best_distance:
                best_index = index
                best_distance = distance
        if best_index is None:
            clusters.append([detection])
        else:
            # One face per cluster/sample is enough and avoids double-counting a
            # noisy detector result in the same frame.
            existing = [item for item in clusters[best_index] if int(item.get("sample", -1)) == int(detection.get("sample", -2))]
            if existing:
                current = existing[0]
                # Haar cascades can report the same shape at several sizes. The
                # old code claimed to prefer the closest result but actually kept
                # the largest box. In gameplay that let a large HUD/weapon shape
                # replace a plausible small face and corrupt the temporal cluster.
                reference = [
                    item for item in clusters[best_index]
                    if int(item.get("sample", -1)) != int(detection.get("sample", -2))
                ]
                if not reference:
                    continue
                reference_center = {
                    "cx": statistics.median(item["cx"] for item in reference),
                    "cy": statistics.median(item["cy"] for item in reference),
                    "w": statistics.median(item["w"] for item in reference),
                    "h": statistics.median(item["h"] for item in reference),
                }
                replacement_size_ratio = max(
                    detection["w"] / max(reference_center["w"], 1e-6),
                    reference_center["w"] / max(detection["w"], 1e-6),
                    detection["h"] / max(reference_center["h"], 1e-6),
                    reference_center["h"] / max(detection["h"], 1e-6),
                )
                if (
                    replacement_size_ratio <= 1.75
                    and _distance(detection, reference_center) + 0.003 < _distance(current, reference_center)
                ):
                    clusters[best_index].remove(current)
                    clusters[best_index].append(detection)
            else:
                clusters[best_index].append(detection)

    results: list[dict[str, Any]] = []
    for cluster in clusters:
        if not cluster:
            continue
        cx = statistics.median(item["cx"] for item in cluster)
        cy = statistics.median(item["cy"] for item in cluster)
        w = statistics.median(item["w"] for item in cluster)
        h = statistics.median(item["h"] for item in cluster)
        spread = statistics.mean(abs(item["cx"] - cx) + abs(item["cy"] - cy) for item in cluster)
        unique_samples = len({int(item.get("sample", -1)) for item in cluster})
        coverage = unique_samples / max(1, samples)
        area = w * h
        near_edge = cx < 0.36 or cx > 0.64 or cy < 0.34 or cy > 0.66
        stability = _clamp(1.0 - spread / 0.20, 0.0, 1.0)
        small_face_bonus = _clamp((0.16 - area) / 0.16, 0.0, 1.0)
        edge_bonus = 1.0 if near_edge else 0.0
        score = coverage * 1.55 + stability * 0.55 + edge_bonus * 0.38 + small_face_bonus * 0.28
        results.append({
            "detections": cluster,
            "cx": cx,
            "cy": cy,
            "w": w,
            "h": h,
            "area": area,
            "coverage": coverage,
            "spread": spread,
            "stability": stability,
            "near_edge": near_edge,
            "score": score,
        })
    return sorted(results, key=lambda item: float(item["score"]), reverse=True)


def _focus_is_safe(cluster: dict[str, Any]) -> bool:
    """Only move the automatic crop when a face persists across the footage."""
    return bool(
        float(cluster.get("coverage", 0.0)) >= 0.35
        and float(cluster.get("stability", 0.0)) >= 0.68
        and float(cluster.get("area", 1.0)) <= 0.22
    )


def _embedded_candidate(cluster: dict[str, Any], frame_width: int, frame_height: int) -> dict[str, Any] | None:
    coverage = float(cluster["coverage"])
    stability = float(cluster["stability"])
    area = float(cluster["area"])
    cx, cy = float(cluster["cx"]), float(cluster["cy"])
    face_w, face_h = float(cluster["w"]), float(cluster["h"])
    # A layout that duplicates and crops the source is a much larger editorial
    # decision than ordinary auto-reframing. Only offer it for a persistent face
    # in a real corner. Sparse gameplay/HUD false positives must not qualify.
    in_side_band = cx <= 0.30 or cx >= 0.70
    in_vertical_band = cy <= 0.34 or cy >= 0.66
    in_corner = in_side_band and in_vertical_band
    # Stream overlays are not always placed in a literal corner. A common OBS
    # layout docks a small 16:9 creator panel halfway down the left/right edge.
    # Accept that shape only with substantially stronger temporal evidence than
    # an ordinary corner suggestion. The result still requires user confirmation
    # and is never allowed to duplicate the source automatically.
    side_docked = bool(
        in_side_band
        and coverage >= 0.65
        and stability >= 0.82
        and area <= 0.035
    )
    if coverage < 0.50 or stability < 0.75 or (not in_corner and not side_docked) or area > 0.10:
        return None

    # Build a creator-camera crop around the stable face rather than cropping only
    # the face rectangle. The final top panel is close to 16:9, so a 16:9 source
    # crop keeps shoulders/background and looks like a real facecam shot.
    source_aspect = frame_width / max(1, frame_height)
    target_aspect = 16.0 / 9.0
    crop_w = _clamp(face_w * 4.25, 0.20, 0.48)
    crop_h = crop_w * source_aspect / target_aspect
    crop_h = max(crop_h, face_h * 2.4)
    crop_h = _clamp(crop_h, 0.18, 0.50)
    crop_w = max(crop_w, crop_h * target_aspect / max(source_aspect, 1e-6))
    crop_w = _clamp(crop_w, 0.20, 0.52)

    # A face in a side-docked panel is usually framed toward the outer screen
    # edge, leaving its background/nameplate toward the content side. Bias the
    # crop inward and slightly below the face to recover the actual OBS panel.
    # On the reported 1920x1080 stream this resolves to 0.718/0.314/0.249/0.249,
    # within a few pixels of the stable 0.719/0.315/0.247/0.247 overlay.
    horizontal_bias = min(0.07, face_w * 0.8)
    center_x = cx - horizontal_bias if cx > 0.5 else cx + horizontal_bias
    center_y = cy + min(0.06, face_h * 0.32)
    x = _clamp(center_x - crop_w / 2, 0.0, 1.0 - crop_w)
    y = _clamp(center_y - crop_h / 2, 0.0, 1.0 - crop_h)

    # Gameplay/screen content is the same source minus the facecam corner. Move the
    # content crop away from that corner so the facecam is not duplicated below.
    content_x = 0.30 if cx > 0.60 else 0.70 if cx < 0.40 else 0.50
    content_y = 0.38 if cy > 0.62 else 0.62 if cy < 0.38 else 0.50
    confidence = _clamp(coverage * 0.55 + stability * 0.30 + 0.15, 0.0, 0.99)
    return {
        "x": round(x, 4),
        "y": round(y, 4),
        "w": round(crop_w, 4),
        "h": round(crop_h, 4),
        "confidence": round(confidence, 3),
        # Detection is a suggestion. The Director requires an explicit layout
        # choice before it may duplicate the source into a stacked composition.
        "requires_confirmation": True,
        "auto_safe": False,
        "content_focus": {"x": round(content_x, 3), "y": round(content_y, 3)},
        "layout_hint": "embedded_stack",
        "facecam_position": "top",
        "content_position": "bottom",
        "detector": VISION_ANALYSIS_VERSION,
        "method": "temporal_face_cluster",
        "placement": "corner" if in_corner else "side_docked",
        "coverage": round(coverage, 3),
        "stability": round(stability, 3),
    }


def _embedded_candidate_from_clusters(
    clusters: list[dict[str, Any]],
    frame_width: int,
    frame_height: int,
) -> dict[str, Any] | None:
    """Choose the strongest qualifying overlay, not merely the best focus face."""

    for index, cluster in enumerate(clusters):
        candidate = _embedded_candidate(cluster, frame_width, frame_height)
        if candidate is not None:
            return {**candidate, "cluster_rank": index + 1}
    return None


def analyze_faces_and_embedded_camera(
    path: Path,
    duration: float,
    progress: Callable[[float, str], None] | None = None,
    samples: int = 24,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    if cancel_check:
        cancel_check()
    try:
        import cv2
    except ImportError:
        return {"version": VISION_ANALYSIS_VERSION, "available": False, "reason": "opencv_not_installed", "faces": [], "focus": {"x": 0.5, "y": 0.5}, "focus_safe": False, "embedded_camera": None}

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return {"version": VISION_ANALYSIS_VERSION, "available": False, "reason": "video_open_failed", "faces": [], "focus": {"x": 0.5, "y": 0.5}, "focus_safe": False, "embedded_camera": None}
    cascade_root = Path(cv2.data.haarcascades)
    classifiers = [
        cv2.CascadeClassifier(str(cascade_root / "haarcascade_frontalface_default.xml")),
        cv2.CascadeClassifier(str(cascade_root / "haarcascade_frontalface_alt2.xml")),
    ]
    profile_classifier = cv2.CascadeClassifier(str(cascade_root / "haarcascade_profileface.xml"))
    detections: list[dict[str, float]] = []
    frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    sample_count = normalized_vision_sample_count(samples, 24)
    try:
        for index in range(sample_count):
            if cancel_check:
                cancel_check()
            timestamp = (duration * (index + 0.5)) / max(1, sample_count)
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            if progress:
                progress((index + 1) / sample_count, "Finding the creator camera and screen")
            # Downscale large frames for much cheaper detection while retaining the
            # normalized coordinates needed for cropping.
            scale = min(1.0, 960.0 / max(frame.shape[1], frame.shape[0]))
            working = frame if scale >= 0.999 else cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(working, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            faces = []
            for classifier in classifiers:
                found = classifier.detectMultiScale(gray, scaleFactor=1.10, minNeighbors=4, minSize=(28, 28))
                if len(found):
                    faces.extend(found)
            if not faces:
                found = profile_classifier.detectMultiScale(gray, scaleFactor=1.10, minNeighbors=4, minSize=(28, 28))
                faces.extend(found)
                # Haar profile detection is directional; mirror once for the other
                # side only when frontal detectors found nothing.
                mirrored = cv2.flip(gray, 1)
                mirrored_faces = profile_classifier.detectMultiScale(mirrored, scaleFactor=1.10, minNeighbors=4, minSize=(28, 28))
                for x, y, width, height in mirrored_faces:
                    faces.append((working.shape[1] - x - width, y, width, height))
            for x, y, width, height in faces:
                detections.append({
                    "sample": float(index),
                    "time": round(timestamp, 3),
                    "x": x / working.shape[1],
                    "y": y / working.shape[0],
                    "w": width / working.shape[1],
                    "h": height / working.shape[0],
                    "cx": (x + width / 2) / working.shape[1],
                    "cy": (y + height / 2) / working.shape[0],
                })
            if cancel_check:
                cancel_check()
    finally:
        capture.release()

    if not detections:
        return {"version": VISION_ANALYSIS_VERSION, "available": True, "reason": "no_stable_face", "faces": [], "focus": {"x": 0.5, "y": 0.5}, "focus_safe": False, "embedded_camera": None}

    clusters = _cluster_face_detections(detections, sample_count)
    best = clusters[0] if clusters else None
    if not best:
        return {"version": VISION_ANALYSIS_VERSION, "available": True, "reason": "no_stable_face", "faces": [], "focus": {"x": 0.5, "y": 0.5}, "focus_safe": False, "embedded_camera": None}

    # For auto reframe, prefer the most persistent face cluster rather than a random
    # large transient face from gameplay footage.
    focus_safe = _focus_is_safe(best)
    median_cx = float(best["cx"]) if focus_safe else 0.5
    median_cy = float(best["cy"]) if focus_safe else 0.5
    embedded = None
    landscape = frame_width > frame_height * 1.15 if frame_width and frame_height else True
    if landscape:
        embedded = _embedded_candidate_from_clusters(clusters, frame_width, frame_height)

    return {
        "version": VISION_ANALYSIS_VERSION,
        "available": True,
        "frame": {"width": frame_width, "height": frame_height},
        "faces": best["detections"],
        "face_clusters": [
            {
                "coverage": round(float(item["coverage"]), 3),
                "stability": round(float(item["stability"]), 3),
                "score": round(float(item["score"]), 3),
                "cx": round(float(item["cx"]), 4),
                "cy": round(float(item["cy"]), 4),
                "w": round(float(item["w"]), 4),
                "h": round(float(item["h"]), 4),
            }
            for item in clusters[:5]
        ],
        "focus": {"x": round(median_cx, 4), "y": round(median_cy, 4)},
        "focus_safe": focus_safe,
        "coverage": round(float(best["coverage"]), 3),
        "stability": round(float(best["stability"]), 3),
        "embedded_camera": embedded,
    }
