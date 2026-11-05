"""Synthetic response faults and clocks; no saved private model receipts."""
from __future__ import annotations
import copy
import json

from .source_fixture import source_context, source_fixture, understanding_reply


def false_omission_fixture():
    rows = [
        {"id": "s0015", "start": 0., "end": 4., "text": "The dry surfaces move because no adhesive joins them.", "selected_in_proposal": True},
        {"id": "s0016", "start": 4., "end": 8., "text": "That movement explains why the first load test failed.", "selected_in_proposal": True},
        {"id": "s0017", "start": 9., "end": 12., "text": "The next trial used a different finish.", "selected_in_proposal": False},
    ]
    data = {"source_utterances": rows, "actual_playback": {"joins": []},
            "brief": {"instruction": "Keep the source meaning."}}
    reply = {"summary": "The proposal omits the explanation.", "issues": ["An alleged omission, not verified truth."],
             "issue_evidence": [{"issue_index": 0, "kind": "missing_context", "source_segment_ids": ["s0015"],
                                 "missing_context_segment_ids": ["s0016"], "join_id": None, "instruction_quote": ""}]}
    return copy.deepcopy(data), copy.deepcopy(reply)


def transport_fixture(truncated, variant=0):
    body = {"verdict": "revise", "issues": ["Unverified synthetic interpretation."],
            "summary": "No automatic approval.", "variant": variant}
    content = json.dumps(body)
    return {"done": True, "done_reason": "length" if truncated else "stop",
            "message": {"role": "assistant", "content": content[:-3] if truncated else content}}


def playback_projection_fixture():
    # Seventeen utterances in ten real runs: nine omitted gaps, independent of
    # deliberately stale optional pause metadata from a hypothetical proposal.
    sizes = [2]*7 + [1]*3
    row_duration = 57.19 / 17
    gap = 4.36 / 9
    rows, ranges, position, index = [], [], 0., 5
    for group, count in enumerate(sizes):
        start = position
        for _ in range(count):
            end = position + row_duration
            rows.append({"id": f"s{index:04d}", "start": position, "end": end,
                         "text": f"The workshop recorded measurement {index} without changing its meaning."})
            index += 1
            position = end
        ranges.append({"start": start, "end": position})
        if group < len(sizes)-1:
            position += gap
    option = {"segment_ids": [row["id"] for row in rows], "playback_ranges": ranges,
              "cost": {"pause_count": 8}}
    return {"fixed_passage_candidate": option, "selected_source_utterances": rows,
            "brief": {"instruction": "Make one video.", "goal": "short", "target_duration": 60.}}, \
           {"semantic_reason": "The fixture calls these 8 distinct pauses; that is not actual cut evidence."}


def editorial_control():
    source = source_fixture()
    # Eighteen canonical rows keep this generic three-run control inside the
    # documented twenty-unit ordered-search scope, with omitted neighbors.
    domain = set(range(4, 9)) | set(range(12, 19)) | set(range(25, 31))
    source["segments"] = [row for row in source["segments"] if int(row["id"][1:]) in domain]
    ids = [f"s{n:04d}" for start, end in [(4, 6), (12, 16), (25, 30)] for n in range(start, end+1)]
    return source, {"canonical_segment_ids": ids,
                    "full_exact_text": " ".join(row["text"] for row in source["segments"] if row["id"] in ids)}


def legacy_precision_reply(kind):
    """A bounded, source-exact old-format proposal outside the fixed shortlist."""
    from cutroom import intelligence as story
    from cutroom.edit_styles import enrich_brief_with_style
    source, rows, units, chapters, plan = source_context()
    brief = enrich_brief_with_style(copy.deepcopy(source["brief"]))
    options = story._passage_options(units, rows, chapters, plan, brief)
    memberships = {tuple(option["beat_ids"]) for option in options["options"]}
    chosen = None
    for first in range(len(units)):
        for count in range(1, min(20, len(units)-first)+1):
            ids = [unit["id"] for unit in units[first:first+count]]
            seconds = story._story_selection_cost(ids, units, rows, brief)["approved_seconds"]
            in_band = 20 <= seconds < 45 if kind == "05_precision" else 45 <= seconds < 54
            if in_band and tuple(ids) not in memberships:
                chosen = ids
                break
        if chosen:
            break
    if chosen is None:
        raise AssertionError("Synthetic source must expose an under-target/nonshortlisted legacy control")
    by_choice = story._story_evidence_choice_catalog(story.build_story_evidence_catalog(units, rows))
    choices = [next(choice for choice, proof in by_choice.items() if proof["beat_id"] == identifier) for identifier in chosen]
    return {"verdict": "fit", "role_selections": {story.SINGLE_PASSAGE_PURPOSE: {
            "primary_anchor_choice": choices[-1], "additional_primary_evidence_choices": choices[:-1],
            "context_evidence_choices_by_chapter": {}}}, "highlight_beat_ids": [],
            "title": "Synthetic obsolete proposal", "summary": "A source-exact old shape is not a fixed candidate choice."}


def response_reader(language="en"):
    source = source_fixture(language)
    def response(stem, payload=None):
        if stem in {"01_summary", "02_outline", "03_plan"}:
            if payload is not None:
                return understanding_reply(payload)
            _source, _rows, _units, chapters, plan = source_context(language)
            if stem == "03_plan":
                return copy.deepcopy(plan)
            stage = "first pass" if stem == "01_summary" else "global story analyst"
            return understanding_reply({"messages": [{"content": stage}, {"content": json.dumps({"chapters": chapters})}]})
        if language == "en":
            return legacy_precision_reply(stem)
        return {"verdict": "no_fit", "candidate_id": None, "refusal_category": "temporal_uncertainty",
                "semantic_reason": "Synthetic source_order uncertainty is not a proof about the source.", "cited_segment_ids": [], "reason_evidence": []}
    return copy.deepcopy(source["segments"]), {"instruction": source["brief"]["instruction"], "fixture_kind": "generated"}, response
