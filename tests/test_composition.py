from __future__ import annotations

import math

import pytest

from cutroom.composition import (
    FACE_LAYOUT_VERSION,
    build_manual_embedded_candidate,
    embedded_content_rectangle,
    normalize_content_focus,
    normalize_facecam_rectangle,
    normalize_vision_embedded_candidate,
    select_embedded_candidate,
)


def _vision_candidate(**overrides):
    candidate = {
        "x": 0.72,
        "y": 0.04,
        "w": 0.24,
        "h": 0.28,
        "confidence": 0.91,
        "content_focus": {"x": 0.3, "y": 0.6},
        "detector": FACE_LAYOUT_VERSION,
    }
    candidate.update(overrides)
    return candidate


def test_normalize_facecam_rectangle_keeps_only_trusted_geometry():
    source = {"x": 0.7, "y": 0.05, "w": 0.25, "h": 0.3, "raw_filter": "evil"}
    normalized = normalize_facecam_rectangle(source)
    assert normalized == {"x": 0.7, "y": 0.05, "w": 0.25, "h": 0.3}
    assert source["raw_filter"] == "evil"


@pytest.mark.parametrize(
    "rectangle",
    [
        None,
        {},
        {"x": "0", "y": 0.0, "w": 0.2, "h": 0.2},
        {"x": True, "y": 0.0, "w": 0.2, "h": 0.2},
        {"x": math.nan, "y": 0.0, "w": 0.2, "h": 0.2},
        {"x": 0.0, "y": math.inf, "w": 0.2, "h": 0.2},
        {"x": -0.01, "y": 0.0, "w": 0.2, "h": 0.2},
        {"x": 0.9, "y": 0.0, "w": 0.2, "h": 0.2},
        {"x": 0.0, "y": 0.9, "w": 0.2, "h": 0.2},
        {"x": 0.0, "y": 0.0, "w": 0.03, "h": 0.2},
        {"x": 0.0, "y": 0.0, "w": 0.2, "h": 0.03},
        {"x": 0.0, "y": 0.0, "w": 0.9, "h": 0.9},
    ],
)
def test_normalize_facecam_rectangle_rejects_unsafe_geometry(rectangle):
    assert normalize_facecam_rectangle(rectangle) is None


def test_rectangle_clamps_only_tiny_boundary_drift():
    normalized = normalize_facecam_rectangle({"x": -1e-7, "y": 0.8, "w": 0.2, "h": 0.2000001})
    assert normalized == {"x": 0.0, "y": 0.8, "w": 0.2, "h": 0.2}

    assert normalize_facecam_rectangle({"x": -1e-4, "y": 0.8, "w": 0.2, "h": 0.2}) is None


def test_content_focus_is_clamped_and_non_finite_axes_fall_back_to_center():
    assert normalize_content_focus({"x": -4.0, "y": 9.0}) == {"x": 0.0, "y": 1.0}
    assert normalize_content_focus({"x": math.nan, "y": 0.25}) == {"x": 0.5, "y": 0.25}
    assert normalize_content_focus(None) == {"x": 0.5, "y": 0.5}


def test_manual_candidate_is_clearly_marked_and_never_automatically_enabled():
    candidate = build_manual_embedded_candidate(
        {"x": 0.65, "y": 0.05, "w": 0.3, "h": 0.35},
        {"x": 1.2, "y": -0.2},
    )
    assert candidate is not None
    assert candidate["candidate_source"] == "manual"
    assert candidate["manual"] is True
    assert candidate["content_focus"] == {"x": 1.0, "y": 0.0}
    assert candidate["requires_confirmation"] is True
    assert candidate["confirmed"] is False
    assert candidate["auto_safe"] is False
    assert candidate["auto_enable"] is False
    assert candidate["enabled"] is False


def test_embedded_content_focus_can_be_read_from_manual_rectangle():
    candidate = build_manual_embedded_candidate(
        {"x": 0.65, "y": 0.05, "w": 0.3, "h": 0.35, "content_focus": {"x": 0.2, "y": 0.8}}
    )
    assert candidate is not None
    assert candidate["content_focus"] == {"x": 0.2, "y": 0.8}


def test_valid_manual_candidate_takes_precedence_over_vision():
    selected = select_embedded_candidate(
        {"x": 0.02, "y": 0.05, "w": 0.3, "h": 0.4, "content_focus": {"x": 0.8, "y": 0.55}},
        _vision_candidate(),
    )
    assert selected is not None
    assert selected["candidate_source"] == "manual"
    assert selected["x"] == 0.02
    assert selected["content_focus"] == {"x": 0.8, "y": 0.55}


def test_invalid_manual_candidate_falls_back_to_current_face_layout_suggestion():
    selected = select_embedded_candidate(
        {"x": 0.95, "y": 0.0, "w": 0.2, "h": 0.2},
        _vision_candidate(),
    )
    assert selected is not None
    assert selected["candidate_source"] == "vision"
    assert selected["detector"] == FACE_LAYOUT_VERSION
    assert selected["requires_confirmation"] is True
    assert selected["enabled"] is False


def test_complete_vision_envelope_is_supported_and_version_is_required():
    candidate = _vision_candidate()
    candidate.pop("detector")
    selected = normalize_vision_embedded_candidate(
        {"version": FACE_LAYOUT_VERSION, "embedded_camera": candidate}
    )
    assert selected is not None
    assert selected["candidate_source"] == "vision"

    assert normalize_vision_embedded_candidate(
        {"version": "face-layout-v1", "embedded_camera": candidate}
    ) is None
    assert normalize_vision_embedded_candidate(
        {"version": "face-layout-v2", "embedded_camera": candidate}
    ) is None


def test_untrusted_vision_flags_cannot_enable_embedded_layout():
    selected = normalize_vision_embedded_candidate(
        _vision_candidate(enabled=True, confirmed=True, auto_safe=True, requires_confirmation=False)
    )
    assert selected is not None
    assert selected["requires_confirmation"] is True
    assert selected["confirmed"] is False
    assert selected["auto_safe"] is False
    assert selected["auto_enable"] is False
    assert selected["enabled"] is False


def test_invalid_or_unknown_vision_candidate_is_rejected():
    assert normalize_vision_embedded_candidate(_vision_candidate(detector="face-layout-v1")) is None
    assert normalize_vision_embedded_candidate(_vision_candidate(w=math.inf)) is None


def test_no_valid_candidate_returns_none():
    assert select_embedded_candidate(None, None) is None
    assert select_embedded_candidate(
        {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
        _vision_candidate(detector="legacy-detector"),
    ) is None


@pytest.mark.parametrize("camera,expected", [
    ({"x": 0.0, "y": 0.0, "w": 1.0, "h": .3}, {"x": 0.0, "y": .3, "w": 1.0, "h": .7}),
    ({"x": 0.0, "y": .7, "w": 1.0, "h": .3}, {"x": 0.0, "y": 0.0, "w": 1.0, "h": .7}),
    ({"x": 0.0, "y": 0.0, "w": .5, "h": 1.0}, {"x": .5, "y": 0.0, "w": .5, "h": 1.0}),
    ({"x": .5, "y": 0.0, "w": .5, "h": 1.0}, {"x": 0.0, "y": 0.0, "w": .5, "h": 1.0}),
    ({"x": .7, "y": .05, "w": .25, "h": .35}, {"x": 0.0, "y": 0.0, "w": .7, "h": 1.0}),
])
def test_content_region_excludes_camera_for_combined_recording_shapes(camera, expected):
    region = embedded_content_rectangle(camera)
    assert region == expected
    assert min(region["x"] + region["w"], camera["x"] + camera["w"]) <= max(region["x"], camera["x"]) + 1e-6 or min(region["y"] + region["h"], camera["y"] + camera["h"]) <= max(region["y"], camera["y"]) + 1e-6


def test_equal_clear_regions_prefer_content_focus_and_ignore_saved_region():
    camera = {"x": .4, "y": .3, "w": .2, "h": .4,
              "content_focus": {"x": 1.0, "y": .5},
              "content_region": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}}
    expected = {"x": .6, "y": 0.0, "w": .4, "h": 1.0}
    assert embedded_content_rectangle(camera) == expected
    assert build_manual_embedded_candidate(camera)["content_region"] == expected
    assert normalize_vision_embedded_candidate({**camera, "detector": FACE_LAYOUT_VERSION})["content_region"] == expected
    assert embedded_content_rectangle(None) is None


def test_content_regions_are_safe_across_valid_camera_positions():
    # Property-style coverage without model inference or another dependency.
    for x in (0.0, .1, .25, .4, .6, .8):
        for y in (0.0, .1, .25, .4, .6, .8):
            for width, height in ((.1, .1), (.2, .2), (.4, .3), (.6, .7)):
                camera = {"x": x, "y": y, "w": width, "h": height}
                if normalize_facecam_rectangle(camera) is None:
                    continue
                region = embedded_content_rectangle(camera)
                assert region and region["w"] >= .06 and region["h"] >= .06
                assert region["x"] + region["w"] <= 1.0 + 1e-6
                assert region["y"] + region["h"] <= 1.0 + 1e-6
                overlap_w = max(0, min(region["x"] + region["w"], x + width) - max(region["x"], x))
                overlap_h = max(0, min(region["y"] + region["h"], y + height) - max(region["y"], y))
                assert overlap_w * overlap_h < 1e-6
