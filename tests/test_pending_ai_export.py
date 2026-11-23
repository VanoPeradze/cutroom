"""Next-analysis preferences must not change the already assembled export."""
from __future__ import annotations

import copy

import pytest

from cutroom import render
from test_sequence_render import sequence_project


DRAFT_ONLY_PREFERENCES = {
    "instruction": "Find a different story next time.",
    "allow_extractive_rough_cut": True,
    "pace": "dynamic",
    "spoken_language": "he",
    "performance_mode": "quality",
    "visual_ai": "off",
    "duration_mode": "target",
    "target_duration": 75,
}


@pytest.mark.parametrize("sequence", [False, True], ids=["legacy", "sequence"])
@pytest.mark.parametrize("changed", [*DRAFT_ONLY_PREFERENCES, "all"])
def test_pending_draft_preferences_preserve_current_picture_sound_captions_and_duration(sequence, changed):
    original = sequence_project()
    if not sequence:
        original["manual"].pop("sequence")
        original["manual"].pop("source_tracks")
    original["settings"].update({"captions": True, "burn_captions": True})
    pending = copy.deepcopy(original)
    updates = DRAFT_ONLY_PREFERENCES if changed == "all" else {changed: DRAFT_ONLY_PREFERENCES[changed]}
    pending["settings"].update(updates)
    before = copy.deepcopy(pending)

    assert render._render_input_fingerprint(pending) == render._render_input_fingerprint(original)
    assert render._render_plan(pending) == render._render_plan(original)
    assert render._expected_output_duration(pending) == render._expected_output_duration(original)
    assert render._caption_transcript(pending) == render._caption_transcript(original)
    assert render.build_filter_graph(pending, 160, 100) == render.build_filter_graph(original, 160, 100)
    assert pending == before
