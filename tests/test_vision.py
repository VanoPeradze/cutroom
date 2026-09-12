from __future__ import annotations

from cutroom.vision import (
    _cluster_face_detections,
    _embedded_candidate,
    _embedded_candidate_from_clusters,
    _focus_is_safe,
    normalized_vision_sample_count,
)


def test_vision_sample_count_is_bounded_and_malformed_config_uses_fallback():
    assert normalized_vision_sample_count("32", 12) == 32
    assert normalized_vision_sample_count("not-a-number", 12) == 12
    assert normalized_vision_sample_count(None, 20) == 20
    assert normalized_vision_sample_count(True, 20) == 20
    assert normalized_vision_sample_count(-5, 12) == 10
    assert normalized_vision_sample_count(500, 12) == 56


def test_temporal_face_cluster_prefers_persistent_corner_facecam():
    detections = []
    for sample in range(20):
        # Stable creator facecam in the top-right corner.
        detections.append({"sample": sample, "time": sample, "cx": .86 + (sample % 2) * .002, "cy": .16, "w": .075, "h": .13, "x": .82, "y": .095})
        # A large gameplay face appears only occasionally near the center.
        if sample in {2, 8, 15}:
            detections.append({"sample": sample, "time": sample, "cx": .50, "cy": .48, "w": .24, "h": .35, "x": .38, "y": .30})
    clusters = _cluster_face_detections(detections, 20)
    assert clusters
    best = clusters[0]
    assert best["coverage"] > .9
    assert best["cx"] > .8
    candidate = _embedded_candidate(best, 1920, 1080)
    assert candidate is not None
    assert candidate["facecam_position"] == "top"
    assert candidate["content_position"] == "bottom"
    assert candidate["content_focus"]["x"] < .5


def test_unstable_center_face_is_not_classified_as_embedded_camera():
    detections = [
        {"sample": i, "time": i, "cx": .45 + (i % 4) * .08, "cy": .45, "w": .25, "h": .32, "x": .3, "y": .28}
        for i in range(8)
    ]
    clusters = _cluster_face_detections(detections, 20)
    if clusters:
        assert _embedded_candidate(clusters[0], 1920, 1080) is None


def test_facecam_crop_keeps_creator_context_not_only_face_pixels():
    cluster = {
        "coverage": .8, "stability": .92, "area": .01, "near_edge": True,
        "cx": .86, "cy": .18, "w": .07, "h": .13,
    }
    candidate = _embedded_candidate(cluster, 1920, 1080)
    assert candidate is not None
    assert candidate["w"] >= cluster["w"] * 3
    assert candidate["h"] >= cluster["h"] * 2.35


def test_persistent_side_docked_stream_camera_is_detected_with_its_panel_bounds():
    # Regression from the reported two-hour 1920x1080 stream. The facecam is a
    # fixed 16:9 panel on the right edge, but vertically centered rather than in
    # a literal corner. v2 found the face reliably and then rejected the layout.
    cluster = {
        "coverage": .80,
        "stability": .911,
        "area": .0583 * .1037,
        "near_edge": True,
        "cx": .8891,
        "cy": .4056,
        "w": .0583,
        "h": .1037,
    }

    candidate = _embedded_candidate(cluster, 1920, 1080)

    assert candidate is not None
    assert candidate["placement"] == "side_docked"
    assert abs(candidate["x"] - .7193) < .01
    assert abs(candidate["y"] - .3148) < .01
    assert abs(candidate["w"] - .2474) < .01
    assert abs(candidate["h"] - .2472) < .01
    assert candidate["requires_confirmation"] is True


def test_weak_side_docked_face_does_not_become_an_embedded_camera():
    cluster = {
        "coverage": .54,
        "stability": .78,
        "area": .01,
        "near_edge": True,
        "cx": .88,
        "cy": .45,
        "w": .07,
        "h": .13,
    }
    assert _embedded_candidate(cluster, 1920, 1080) is None


def test_embedded_overlay_can_win_when_a_center_face_has_the_higher_focus_score():
    center_face = {
        "coverage": .92, "stability": .95, "area": .02,
        "cx": .50, "cy": .48, "w": .12, "h": .17, "score": 2.40,
    }
    side_camera = {
        "coverage": .82, "stability": .91, "area": .008,
        "cx": .88, "cy": .43, "w": .065, "h": .12, "score": 2.28,
    }

    candidate = _embedded_candidate_from_clusters(
        [center_face, side_camera], 1920, 1080,
    )

    assert candidate is not None
    assert candidate["placement"] == "side_docked"
    assert candidate["cluster_rank"] == 2


def test_real_gameplay_false_positive_is_not_a_camera_or_safe_focus():
    # Regression from the reported 38-minute FPS recording: three unrelated
    # gameplay shapes were joined into one weak top-center "face" cluster.
    cluster = {
        "coverage": .25,
        "stability": .602,
        "area": .05 * .0889,
        "near_edge": True,
        "cx": .4021,
        "cy": .2611,
        "w": .05,
        "h": .0889,
    }
    assert _focus_is_safe(cluster) is False
    assert _embedded_candidate(cluster, 1920, 1080) is None


def test_sparse_top_center_faces_do_not_qualify_as_embedded_camera():
    cluster = {
        "coverage": .8,
        "stability": .92,
        "area": .01,
        "near_edge": True,
        "cx": .50,
        "cy": .15,
        "w": .07,
        "h": .13,
    }
    assert _embedded_candidate(cluster, 1920, 1080) is None


def test_larger_duplicate_in_same_sample_does_not_hijack_stable_cluster():
    detections = [
        {"sample": 0, "time": 0, "cx": .86, "cy": .16, "w": .07, "h": .13, "x": .825, "y": .095},
        {"sample": 1, "time": 1, "cx": .862, "cy": .161, "w": .071, "h": .13, "x": .8265, "y": .096},
        # Same sample, noisier and much larger. The old replacement rule kept it.
        {"sample": 1, "time": 1, "cx": .861, "cy": .160, "w": .13, "h": .23, "x": .796, "y": .045},
        {"sample": 2, "time": 2, "cx": .859, "cy": .159, "w": .069, "h": .129, "x": .8245, "y": .0945},
    ]
    clusters = _cluster_face_detections(detections, 3)
    assert clusters
    best = clusters[0]
    assert best["coverage"] == 1.0
    assert best["w"] < .08
    assert max(item["w"] for item in best["detections"]) < .08


def test_embedded_candidate_is_always_a_confirmation_suggestion():
    candidate = _embedded_candidate({
        "coverage": .9,
        "stability": .95,
        "area": .01,
        "near_edge": True,
        "cx": .86,
        "cy": .18,
        "w": .07,
        "h": .13,
    }, 1920, 1080)
    assert candidate is not None
    assert candidate["requires_confirmation"] is True
    assert candidate["auto_safe"] is False
