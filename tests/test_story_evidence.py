from __future__ import annotations

import copy

import pytest

from cutroom.story_evidence import (
    EVIDENCE_POLICY_VERSION,
    build_story_evidence_catalog,
    validate_story_evidence,
)


ROLES = ["premise", "setup", "evidence", "result"]


def sources(texts=None):
    texts = texts or ["The question.", "The setup.", "We tested it.", "The result."]
    segments = [{"id": f"s{index}", "start": index * 10.0, "end": index * 10.0 + 8,
                 "text": text} for index, text in enumerate(texts, 1)]
    beats = [{"id": f"b{index}", "start": segment["start"], "end": segment["end"],
              "segment_ids": [segment["id"]], "text": segment["text"]}
             for index, segment in enumerate(segments, 1)]
    return beats, segments


def slot(index, role, beat, evidence, *, context=None, context_evidence=None):
    return {"slot_index": index, "purpose": role, "primary_beat_ids": [beat],
            "context_beat_ids": context or [], "primary_evidence_ids": [evidence],
            "context_evidence_ids": context_evidence or [], "temporal_witness_id": evidence}


def mapped_fixture():
    beats, segments = sources()
    catalog = build_story_evidence_catalog(beats, segments)
    rows = [slot(index, role, row["beat_id"], row["id"])
            for index, (role, row) in enumerate(zip(ROLES, catalog))]
    return beats, segments, catalog, rows


def validate(rows, beats, segments, **kwargs):
    return validate_story_evidence(rows, beats, segments,
                                   selected_beat_ids=[beat.get("id", beat.get("beat_id")) for beat in beats],
                                   **kwargs)


def test_catalog_is_verbatim_deterministic_bounded_and_ignores_beat_prose():
    text = "  רעיון ראשון, רעיון שני; " + "source word " * 40 + "Done."
    beats, segments = sources([text])
    beats[0]["text"] = "Invented English outcome."
    before = copy.deepcopy((beats, segments))

    catalog = build_story_evidence_catalog(beats, segments)

    assert catalog == build_story_evidence_catalog(list(reversed(beats)), list(reversed(segments)))
    assert len(catalog) > 4
    assert len({row["id"] for row in catalog}) == len(catalog)
    for row in catalog:
        assert row["text"] == text[row["char_start"]:row["char_end"]]
        assert len(row["text"]) <= 160
        assert (row["start"], row["end"]) == (segments[0]["start"], segments[0]["end"])
    assert (beats, segments) == before


def test_catalog_can_filter_rejected_units_without_exposing_their_quotes():
    beats, segments = sources(["Allowed question.", "MVP proof belongs here."])

    catalog = build_story_evidence_catalog(beats, segments, allowed_beat_ids=["b1"])

    assert {row["beat_id"] for row in catalog} == {"b1"}
    assert all("MVP" not in row["text"] for row in catalog)


def test_canonical_proof_discards_model_claims_and_does_not_mutate_inputs():
    beats, segments, _, rows = mapped_fixture()
    rows[-1].update(role_evidence="The MVP proves victory.", text="Invented quote",
                    start=-200, source_evidence=[{"text": "Fake proof"}], invented_fact="Won 20 awards")
    original = copy.deepcopy(rows)

    proof = validate(rows, beats, segments, required_roles=ROLES)

    assert proof["policy_version"] == EVIDENCE_POLICY_VERSION
    assert proof["verification_scope"] == "source_attribution_and_order"
    assert proof["slot_map"][-1]["role_evidence"] == "The result."
    assert proof["slot_map"][-1]["source_evidence"][0]["text"] == "The result."
    assert "MVP" not in str(proof) and "invented_fact" not in str(proof)
    assert rows == original


@pytest.mark.parametrize("field,value", [
    ("primary_evidence_ids", ["b1:s1:f99"]),
    ("primary_evidence_ids", ["b2:s2:f1"]),
    ("primary_evidence_ids", ["b1:s1:f1", "b1:s1:f1"]),
    ("primary_evidence_ids", []),
    ("temporal_witness_id", "b2:s2:f1"),
])
def test_unknown_wrong_unit_duplicate_missing_and_context_witness_references_fail(field, value):
    beats, segments, _, rows = mapped_fixture()
    rows[0][field] = value

    with pytest.raises(ValueError):
        validate(rows, beats, segments, required_roles=ROLES)


def test_unselected_and_rejected_mvp_proof_cannot_be_imported_into_other_unit():
    beats, segments = sources(["The real result happened early.", "MVP appears only in this rejected unit."])
    catalog = build_story_evidence_catalog(beats, segments)
    row = slot(0, "result", "b1", catalog[1]["id"])

    with pytest.raises(ValueError):
        validate_story_evidence([row], beats, segments, selected_beat_ids=["b1"],
                                rejected_beat_ids=["b2"], required_roles=["result"])
    with pytest.raises(ValueError):
        validate_story_evidence([slot(0, "result", "b2", catalog[1]["id"])], beats, segments,
                                selected_beat_ids=["b2"], rejected_beat_ids=["b2"])


def test_plain_english_role_claim_without_reference_ids_is_not_proof():
    beats, segments, _, rows = mapped_fixture()
    rows[0].pop("primary_evidence_ids")
    rows[0]["role_evidence"] = "This source contains the premise and exact MVP result."

    with pytest.raises(ValueError):
        validate(rows, beats, segments)


def test_each_mapped_primary_and_context_beat_requires_its_own_reference():
    beats, segments, catalog, rows = mapped_fixture()
    rows[0]["context_beat_ids"] = ["b2"]

    with pytest.raises(ValueError):
        validate(rows, beats, segments)

    rows[0]["context_evidence_ids"] = [catalog[1]["id"]]
    proof = validate(rows, beats, segments, required_roles=ROLES)
    assert proof["slot_map"][0]["context_evidence_ids"] == [catalog[1]["id"]]
    rows[0]["temporal_witness_id"] = catalog[1]["id"]
    with pytest.raises(ValueError):
        validate(rows, beats, segments)


def test_same_canonical_reference_can_supply_primary_and_context_without_repeating_footage():
    beats, segments = sources(["A complete source passage."])
    evidence = build_story_evidence_catalog(beats, segments)[0]["id"]
    row = slot(0, "result", "b1", evidence, context=["b1"], context_evidence=[evidence])

    proof = validate([row], beats, segments)

    assert proof["slot_map"][0]["beat_ids"] == ["b1"]
    assert len(proof["slot_map"][0]["source_evidence"]) == 1


def test_reversed_four_role_source_order_is_rejected():
    beats, segments, catalog, _ = mapped_fixture()
    rows = [slot(index, role, row["beat_id"], row["id"])
            for index, (role, row) in enumerate(zip(ROLES, reversed(catalog)))]

    with pytest.raises(ValueError, match="inverted"):
        validate(rows, beats, segments, required_roles=ROLES)


def test_early_result_before_later_setup_and_evidence_is_rejected():
    beats, segments, catalog, rows = mapped_fixture()
    rows[-1] = slot(3, "result", "b1", catalog[0]["id"])

    with pytest.raises(ValueError, match="inverted"):
        validate(rows, beats, segments, required_roles=ROLES)


def test_all_four_roles_can_use_distinct_quotations_in_one_whole_source_unit():
    beats, segments = sources(["A question, a setup; observed evidence. The final result."])
    catalog = build_story_evidence_catalog(beats, segments)
    rows = [slot(index, role, "b1", reference["id"])
            for index, (role, reference) in enumerate(zip(ROLES, catalog))]

    proof = validate(rows, beats, segments, required_roles=ROLES)

    assert [row["purpose"] for row in proof["slot_map"]] == ROLES
    assert [row["text"] for row in proof["order_evidence"]] == [row["text"] for row in catalog]
    assert len({(row["start"], row["end"]) for row in catalog}) == 1
    rows[1]["primary_evidence_ids"], rows[2]["primary_evidence_ids"] = (
        rows[2]["primary_evidence_ids"], rows[1]["primary_evidence_ids"])
    rows[1]["temporal_witness_id"], rows[2]["temporal_witness_id"] = (
        rows[2]["temporal_witness_id"], rows[1]["temporal_witness_id"])
    with pytest.raises(ValueError, match="inverted"):
        validate(rows, beats, segments, required_roles=ROLES)


def test_repeated_identical_quotes_have_distinct_positions_and_complete_word_mapping():
    beats, segments = sources(["Go now. Go now."])
    segment = segments[0]
    segment.update(start=0.0, end=10.0, words=[
        {"word": "Go", "start": 0.0, "end": .5}, {"word": "now.", "start": .5, "end": 1.0},
        {"word": "Go", "start": 8.0, "end": 8.5}, {"word": "now.", "start": 8.5, "end": 9.0},
    ])
    beats[0].update(start=0.0, end=10.0)
    catalog = build_story_evidence_catalog(beats, segments)
    assert catalog[0]["text"] == catalog[1]["text"]
    assert catalog[0]["id"] != catalog[1]["id"]
    row = slot(0, "result", "b1", catalog[1]["id"])

    validate([row], beats, segments, keep_ranges=[{"start": 8.0, "end": 9.0}])
    with pytest.raises(ValueError, match="omit"):
        validate([row], beats, segments, keep_ranges=[{"start": 0.0, "end": 1.0}])


def test_quotation_coverage_only_requires_its_three_words_when_mapping_is_complete():
    # Attribution coverage is independent of the caller's whole-passage policy.
    beats, segments = sources(["Keep these words, preserve the complete passage."])
    segments[0].update(start=0.0, end=10.0, words=[
        {"word": "Keep", "start": 0.0, "end": .5},
        {"word": "these", "start": .5, "end": 1.0},
        {"word": "words,", "start": 1.0, "end": 1.5},
        {"word": "preserve", "start": 6.0, "end": 6.5},
        {"word": "the", "start": 6.5, "end": 7.0},
        {"word": "complete", "start": 7.0, "end": 7.5},
        {"word": "passage.", "start": 7.5, "end": 8.0},
    ])
    beats[0].update(start=0.0, end=10.0)
    reference = build_story_evidence_catalog(beats, segments)[0]
    row = slot(0, "result", "b1", reference["id"])

    validate([row], beats, segments, keep_ranges=[{"start": 0, "end": 1.5}])


def test_shared_overlapping_and_touching_source_witnesses_are_allowed():
    beats, segments = sources(["First.", "Final."])
    beats[0].update(start=0.0, end=6.0)
    beats[1].update(start=4.0, end=10.0)
    segments[0].update(start=0.0, end=6.0)
    segments[1].update(start=4.0, end=10.0)
    catalog = build_story_evidence_catalog(beats, segments)
    rows = [slot(0, "premise", "b1", catalog[0]["id"]),
            slot(1, "setup", "b1", catalog[0]["id"]),
            slot(2, "result", "b2", catalog[1]["id"])]
    validate(rows, beats, segments)
    beats[1]["start"] = segments[1]["start"] = 6.0
    validate(rows, beats, segments)


@pytest.mark.parametrize("same_segment", [True, False], ids=["adjacent_characters", "contiguous_segments"])
def test_reversed_witnesses_at_exact_nonoverlapping_boundaries_are_rejected(same_segment):
    if same_segment:
        beats, segments = sources(["First,Second."])
        catalog = build_story_evidence_catalog(beats, segments)
        assert catalog[0]["char_end"] == catalog[1]["char_start"]
        rows = [slot(0, "premise", "b1", catalog[1]["id"]),
                slot(1, "result", "b1", catalog[0]["id"])]
    else:
        beats, segments = sources(["First.", "Second."])
        beats[0].update(start=0, end=5)
        beats[1].update(start=5, end=10)
        segments[0].update(start=0, end=5)
        segments[1].update(start=5, end=10)
        catalog = build_story_evidence_catalog(beats, segments)
        rows = [slot(0, "premise", "b2", catalog[1]["id"]),
                slot(1, "result", "b1", catalog[0]["id"])]

    with pytest.raises(ValueError, match="inverted"):
        validate(rows, beats, segments)


def test_final_primary_witness_must_be_in_final_selected_passage():
    beats, segments, catalog, _ = mapped_fixture()
    row = slot(0, "result", "b1", catalog[0]["id"], context=["b4"],
               context_evidence=[catalog[-1]["id"]])

    with pytest.raises(ValueError, match="final selected"):
        validate([row], beats, segments)


@pytest.mark.parametrize("failure", ["duplicate_segment", "duplicate_beat", "ambiguous_owner",
                                     "unknown_segment", "outside_beat", "nan_timing"])
def test_malformed_or_ambiguous_canonical_source_is_rejected(failure):
    beats, segments = sources()
    if failure == "duplicate_segment":
        segments.append(copy.deepcopy(segments[0]))
    elif failure == "duplicate_beat":
        beats.append(copy.deepcopy(beats[0]))
    elif failure == "ambiguous_owner":
        beats[1]["segment_ids"] = ["s1"]
    elif failure == "unknown_segment":
        beats[0]["segment_ids"] = ["missing"]
    elif failure == "outside_beat":
        beats[0]["start"] += 1
    else:
        segments[0]["end"] = float("nan")

    with pytest.raises(ValueError):
        build_story_evidence_catalog(beats, segments)


def paused_fixture():
    beats, segments = sources(["First word, last word."])
    segments[0].update(start=0.0, end=10.0, words=[
        {"word": "First", "start": 0.0, "end": .5}, {"word": "word,", "start": .5, "end": 1.0},
        {"word": "last", "start": 8.0, "end": 8.5}, {"word": "word.", "start": 8.5, "end": 9.0},
    ])
    beats[0].update(start=0.0, end=10.0)
    catalog = build_story_evidence_catalog(beats, segments)
    row = slot(0, "result", "b1", catalog[1]["id"])
    row["primary_evidence_ids"] = [reference["id"] for reference in catalog]
    return beats, segments, row


def test_final_pause_cut_can_remove_only_gap_and_proof_is_unchanged():
    beats, segments, row = paused_fixture()
    before = validate([row], beats, segments)

    after = validate([row], beats, segments, keep_ranges=[{"start": 0, "end": 1}, {"start": 8, "end": 10}])

    assert before == after
    with pytest.raises(ValueError, match="omit"):
        validate([row], beats, segments, keep_ranges=[{"start": 0, "end": 1}, {"start": 8.1, "end": 10}])


@pytest.mark.parametrize("failure", ["incomplete", "missing", "extra", "reordered", "invalid", "backwards"])
def test_unprovable_word_mapping_protects_entire_segment(failure):
    beats, segments, row = paused_fixture()
    if failure == "incomplete":
        segments[0]["word_timing_complete"] = False
    elif failure == "missing":
        segments[0]["words"].pop(1)
    elif failure == "extra":
        segments[0]["words"].append({"word": "extra", "start": 9, "end": 10})
    elif failure == "reordered":
        segments[0]["words"][0]["word"] = "word"
    elif failure == "invalid":
        segments[0]["words"][0]["end"] = float("inf")
    else:
        segments[0]["words"][2]["start"] = .2

    with pytest.raises(ValueError, match="omit"):
        validate([row], beats, segments, keep_ranges=[{"start": 0, "end": 1}, {"start": 8, "end": 10}])
    validate([row], beats, segments, keep_ranges=[{"start": 0, "end": 10}])


@pytest.mark.parametrize("keeps", [
    [{"start": 8, "end": 10}, {"start": 0, "end": 1}],
    [{"start": 0, "end": 9}, {"start": 8, "end": 10}],
    [{"start": 0, "end": 10}, {"start": 0, "end": 10}],
])
def test_final_keep_ranges_cannot_repeat_overlap_or_reorder_source(keeps):
    beats, segments, row = paused_fixture()
    with pytest.raises(ValueError, match="chronological"):
        validate([row], beats, segments, keep_ranges=keeps)


def test_director_style_beat_id_alias_and_selected_only_fingerprint():
    beats, segments, catalog, rows = mapped_fixture()
    selected = [dict(beat_id=beats[-1]["id"], start=beats[-1]["start"], end=beats[-1]["end"],
                     segment_ids=beats[-1]["segment_ids"])]
    row = slot(0, "result", "b4", catalog[-1]["id"])
    full = validate_story_evidence([row], beats, segments, selected_beat_ids=["b4"])
    reduced = validate([row], selected, segments)
    assert full == reduced
