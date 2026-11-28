"""Several Together removals commit as one Undo step (one-click cleanup)."""
from __future__ import annotations

import copy

import pytest

from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.source_tracks import timeline_duration
from test_sequence_editing import edit, geometry, project


def test_batch_matches_single_removals_applied_from_the_end():
    batch, single = project(), project()
    original = copy.deepcopy(batch)
    apply_manual_edit(batch, {"action": "sequence_ripple_delete_ranges", "ranges": [{"start": 1, "end": 2}, {"start": 6, "end": 7.5}]})
    edit(single, "ripple_delete", start=6, end=7.5)
    edit(single, "ripple_delete", start=1, end=2)
    assert timeline_duration(batch) == timeline_duration(single) == 7.5
    assert geometry(batch) == geometry(single) and geometry(batch, "B") == geometry(single, "B")
    assert batch["manual"]["history"] == {"undo_count": 1, "redo_count": 0}
    apply_manual_edit(batch, {"action": "undo"})
    assert timeline_duration(batch) == timeline_duration(original)


@pytest.mark.parametrize("ranges", [[], [{"start": 1, "end": 1.01}], [{"start": 1, "end": 3}, {"start": 2, "end": 4}],
                                    [{"start": 9, "end": 12}], "1-2"])
def test_invalid_batches_change_nothing(ranges):
    value = project()
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, {"action": "sequence_ripple_delete_ranges", "ranges": ranges})
    assert value == before
