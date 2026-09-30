"""Preserve the shared 8 ms source-duration edge found by Mac media smoke."""
import copy

import pytest

from cutroom.editing import ManualEditError, apply_manual_edit


class KnownSourceDurationBoundary(AssertionError):
    """Only the confirmed subframe materialization rejection is expected."""


@pytest.mark.xfail(
    strict=True,
    raises=KnownSourceDurationBoundary,
    reason="Known shared timeline edge: 8 ms source-duration mismatch rejects adding media",
)
def test_add_media_accepts_keeps_ending_eight_ms_after_secondary_source():
    asset_id = "asset_" + "a" * 32
    project = {
        "settings": {"fps": 60},
        "sources": {"A": {"duration": 3.008}, "B": {"duration": 3.000}},
        "manual": {},
        "draft": {"keep_ranges": [{"start": 0, "end": 1}, {"start": 2, "end": 3.008}]},
        "assets": {asset_id: {"id": asset_id, "kind": "audio", "duration": 1, "status": "ready"}},
    }
    before = copy.deepcopy(project)
    try:
        apply_manual_edit(project, {"action": "media_add", "asset_id": asset_id, "start": 0})
    except ManualEditError as error:
        # An unrelated error or partial mutation must fail, not be masked by xfail.
        assert str(error) == "Source clips must contain at least one output frame"
        assert project == before
        raise KnownSourceDurationBoundary(
            "Source B ends at 3.000s, causing materialization to split source A's final 8ms into a rejected clip."
        ) from error
    clip = project["manual"]["media_clips"][0]
    assert (clip["asset_id"], clip["start"], clip["end"]) == (asset_id, 0, 1)
    assert project["sources"] == before["sources"]
