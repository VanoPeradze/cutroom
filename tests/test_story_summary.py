from __future__ import annotations

import copy

import pytest

from cutroom.story_evidence import build_story_evidence_catalog, validate_story_evidence
from cutroom.story_summary import SUMMARY_SOURCE, extractive_story_summary
from cutroom.story_spans import SOURCE_SPAN_POLICY_VERSION, SOURCE_SPAN_SUMMARY_SOURCE, build_source_span_constraints, whole_utterance_story_summary


def source_fixture(texts):
    segments = [{"id": f"s{index}", "start": index * 10.0, "end": index * 10.0 + 8,
                 "text": text} for index, text in enumerate(texts)]
    beats = [{"id": f"b{index}", "start": segment["start"], "end": segment["end"],
              "segment_ids": [segment["id"]], "text": segment["text"]}
             for index, segment in enumerate(segments)]
    catalog = build_story_evidence_catalog(beats, segments)
    return beats, segments, catalog


def slot(index, purpose, primary, *, context=None, witness=None):
    context = context or []
    return {"slot_index": index, "purpose": purpose,
            "primary_beat_ids": list(dict.fromkeys(row["beat_id"] for row in primary)),
            "context_beat_ids": list(dict.fromkeys(row["beat_id"] for row in context)),
            "primary_evidence_ids": [row["id"] for row in primary],
            "context_evidence_ids": [row["id"] for row in context],
            "temporal_witness_id": (witness or primary[0])["id"]}


def proof_for(texts):
    beats, segments, catalog = source_fixture(texts)
    row = slot(0, "result", catalog, witness=catalog[-1])
    proof = validate_story_evidence([row], beats, segments,
                                   selected_beat_ids=[beat["id"] for beat in beats])
    return proof, beats, segments, catalog


def test_summary_quotes_all_primary_and_qualifying_context_in_source_order():
    beats, segments, catalog = source_fixture([
        "So. We need to finish the bridge.",
        "The road looks stable.",
        "Are you certain? It has not passed the load test.",
        "I will not cross it. We must wait.",
    ])
    by_segment = {segment["id"]: [row for row in catalog if row["segment_id"] == segment["id"]]
                  for segment in segments}
    rows = [
        slot(0, "premise", by_segment["s0"], witness=by_segment["s0"][0]),
        slot(1, "setup", by_segment["s1"]),
        slot(2, "development", by_segment["s2"][:1], context=by_segment["s2"][1:]),
        slot(3, "result", by_segment["s3"][1:], context=by_segment["s3"][:1]),
    ]
    proof = validate_story_evidence(rows, beats, segments,
                                   selected_beat_ids=[beat["id"] for beat in beats])
    original = copy.deepcopy(proof)

    summary = extractive_story_summary(proof)

    assert summary == "Source excerpts:\n" + "\n".join(f"\u201c{row['text']}\u201d" for row in catalog)
    assert "We need to finish the bridge." in summary
    assert "It has not passed the load test." in summary
    assert summary.index("I will not cross it.") < summary.index("We must wait.")
    assert proof == original
    assert SUMMARY_SOURCE == "canonical_cited_source_excerpts"


def test_model_prose_and_rejected_unreferenced_source_do_not_supply_summary_words():
    beats, segments, catalog = source_fixture(["A question.", "We must wait.", "REJECTED PRIVATE OUTCOME."])
    rows = [slot(0, "premise", catalog[:1]), slot(1, "result", catalog[1:2])]
    proof = validate_story_evidence(rows, beats, segments, selected_beat_ids=["b0", "b1"],
                                   rejected_beat_ids=["b2"])
    proof["summary"] = "INVENTED VICTORY"
    proof["raw_transcript"] = segments
    proof["slot_map"][0]["role_evidence"] = "INVENTED VICTORY"

    summary = extractive_story_summary(proof)

    assert "REJECTED" not in summary and "PRIVATE" not in summary and "INVENTED" not in summary
    assert summary == "Source excerpts:\n\u201cA question.\u201d\n\u201cWe must wait.\u201d"


def test_shared_primary_and_context_reference_is_displayed_once():
    beats, segments, catalog = source_fixture(["The question.", "The measured result."])
    rows = [slot(0, "premise", catalog[:1]),
            slot(1, "result", catalog[1:], context=catalog)]
    proof = validate_story_evidence(rows, beats, segments, selected_beat_ids=["b0", "b1"])

    summary = extractive_story_summary(proof)

    assert summary.count("The question.") == 1
    assert summary.count("The measured result.") == 1


def test_repeated_words_and_identical_quotes_at_distinct_source_positions_are_preserved():
    proof, _, _, catalog = proof_for(["No, no, no.", "No, no, no."])

    summary = extractive_story_summary(proof)

    assert summary == "Source excerpts:\n" + "\n".join(f"\u201c{row['text']}\u201d" for row in catalog)
    assert summary.count("\u201cNo,\u201d") == 2
    assert summary.count("\u201cno,\u201d") == 2
    assert summary.count("\u201cno.\u201d") == 2


def test_long_output_preserves_every_complete_quote_and_late_qualifier():
    text = " ".join(f"measurement{index}" for index in range(100)) + "."
    proof, _, _, catalog = proof_for([text, "This does not prove it is safe."])

    summary = extractive_story_summary(proof)

    assert len(summary) > 500
    assert summary == "Source excerpts:\n" + "\n".join(f"\u201c{row['text']}\u201d" for row in catalog)
    assert summary.endswith("\u201cThis does not prove it is safe.\u201d")


def test_a_long_indivisible_source_token_is_not_cut_mid_quote():
    text = "measurement_" * 60 + "."
    proof, _, _, catalog = proof_for([text])

    summary = extractive_story_summary(proof)

    assert len(catalog) == 1
    assert summary == f"Source excerpts:\n\u201c{text}\u201d"


def test_unicode_quotes_and_offsets_remain_exact():
    proof, _, _, catalog = proof_for(["\u05d6\u05d4 \u05dc\u05d0 \u05de\u05d5\u05db\u05d9\u05d7 \u05e9\u05d4\u05de\u05d1\u05d7\u05df \u05d4\u05e6\u05dc\u05d9\u05d7. \u05e6\u05e8\u05d9\u05da \u05dc\u05d4\u05de\u05ea\u05d9\u05df."])

    assert extractive_story_summary(proof) == "Source excerpts:\n" + "\n".join(
        f"\u201c{row['text']}\u201d" for row in catalog)


@pytest.mark.parametrize("change", [
    lambda proof: proof.update(policy_version="old-policy"),
    lambda proof: proof.update(verification_scope="model_claims"),
    lambda proof: proof.update(catalog_fingerprint="not-a-proof-fingerprint"),
    lambda proof: proof["slot_map"][0].update(primary_beat_ids=["unselected"]),
    lambda proof: proof["slot_map"][0].update(primary_evidence_ids=["foreign-reference"]),
    lambda proof: proof["slot_map"][0]["source_evidence"].append(
        {**proof["slot_map"][0]["source_evidence"][0], "id": "uncited", "text": "REJECTED"}),
    lambda proof: proof["slot_map"][0]["source_evidence"][0].update(char_end=99999),
    lambda proof: proof["order_evidence"][0].update(text="A forged interpretation."),
])
def test_inconsistent_or_unreferenced_proof_data_is_rejected(change):
    proof, _, _, _ = proof_for(["The source outcome."])
    change(proof)

    with pytest.raises(ValueError):
        extractive_story_summary(proof)


def test_same_reference_cannot_change_its_words_between_roles():
    beats, segments, catalog = source_fixture(["The premise.", "The conclusion."])
    rows = [slot(0, "premise", catalog[:1]),
            slot(1, "result", catalog[1:], context=catalog[:1])]
    proof = validate_story_evidence(rows, beats, segments, selected_beat_ids=["b0", "b1"])
    duplicate = proof["slot_map"][1]["source_evidence"][1]
    duplicate["text"] = "BAD PREMISE."
    duplicate["char_end"] = len(duplicate["text"])

    with pytest.raises(ValueError, match="conflicting source text"):
        extractive_story_summary(proof)


def test_reference_aliases_or_overlapping_character_intervals_are_rejected():
    proof, _, _, _ = proof_for(["First sentence. Second sentence."])
    quotes = proof["slot_map"][0]["source_evidence"]
    quotes[0]["char_start"] = quotes[1]["char_start"]
    quotes[0]["char_end"] = quotes[0]["char_start"] + len(quotes[0]["text"])

    with pytest.raises(ValueError, match="overlap or alias"):
        extractive_story_summary(proof)


def reviewed_result(proof, beats, segments):
    return {"keep_beat_ids": [row["id"] for row in beats],
            "slot_map": copy.deepcopy(proof["slot_map"]),
            "evidence_policy_version": proof["policy_version"],
            "evidence_proof": copy.deepcopy(proof),
            "source_span_policy_version": SOURCE_SPAN_POLICY_VERSION,
            "source_span_constraints": build_source_span_constraints(beats, segments, selected_beat_ids=[row["id"] for row in beats]),
            "semantic_mapping_verified": True, "semantic_review_status": "model_reviewed",
            "summary": "FORGED SUCCESS FROM REJECTED MATERIAL",
            "summary_source": SUMMARY_SOURCE}


def test_current_proof_conversion_rebuilds_summary_instead_of_trusting_supplied_prose():
    from cutroom.intelligence import _story_decision_from_beats

    proof, beats, segments, _ = proof_for(["A recorded question.", "The answer remains uncertain."])
    result = reviewed_result(proof, beats, segments)
    original = copy.deepcopy(result)

    decision = _story_decision_from_beats(result, beats, segments)

    assert decision is not None
    assert decision["summary"] == whole_utterance_story_summary(result["source_span_constraints"])
    assert decision["summary_source"] == SOURCE_SPAN_SUMMARY_SOURCE
    assert "FORGED" not in decision["summary"] and "REJECTED" not in decision["summary"]
    assert result == original


def test_current_proof_conversion_keeps_complete_late_context_after_500_characters():
    from cutroom.intelligence import _story_decision_from_beats

    text = " ".join(f"measurement{index}" for index in range(100)) + "."
    beats, segments, catalog = source_fixture([text, "The apparent improvement is not yet confirmed."])
    row = slot(0, "result", catalog[-1:], context=catalog[:-1])
    proof = validate_story_evidence([row], beats, segments, selected_beat_ids=["b0", "b1"])

    result = reviewed_result(proof, beats, segments)
    decision = _story_decision_from_beats(result, beats, segments)

    assert decision is not None
    assert decision["summary"] == whole_utterance_story_summary(result["source_span_constraints"])
    assert len(decision["summary"]) > 500
    assert decision["summary"].endswith("\u201cThe apparent improvement is not yet confirmed.\u201d")


def test_whole_utterance_conversion_preserves_uncited_negation_without_changing_primary_quotes():
    from cutroom.intelligence import _story_decision_from_beats

    text = "The initial observation appears positive. It does not demonstrate a benefit."
    beats, segments, catalog = source_fixture([text])
    proof = validate_story_evidence([slot(0, "result", catalog[:1])], beats, segments, selected_beat_ids=["b0"])
    result = reviewed_result(proof, beats, segments)

    decision = _story_decision_from_beats(result, beats, segments)

    assert text in decision["summary"]
    assert decision["story_requirements"]["evidence_proof"] == proof
    assert decision["story_requirements"]["slot_map"][0]["primary_evidence_ids"] == [catalog[0]["id"]]
    assert decision["summary_source"] == SOURCE_SPAN_SUMMARY_SOURCE


@pytest.mark.parametrize("fault", ["missing", "wrong_policy", "forged_context"])
def test_current_conversion_cannot_downgrade_missing_or_forged_whole_source_context(fault):
    from cutroom.intelligence import _story_decision_from_beats

    proof, beats, segments, _ = proof_for(["A positive claim. It is not established."])
    result = reviewed_result(proof, beats, segments)
    if fault == "missing": result.pop("source_span_constraints")
    elif fault == "wrong_policy": result["source_span_policy_version"] = "old-policy"
    elif fault == "forged_context": result["source_span_constraints"]["utterances"][0]["text"] = "It is established."

    assert _story_decision_from_beats(result, beats, segments) is None


@pytest.mark.parametrize("change", [
    lambda result: result.update(keep_beat_ids=["b0"]),
    lambda result: result.update(critic={"requested_removed": ["b0"]}),
    lambda result: result["evidence_proof"].update(catalog_fingerprint="0" * 64),
    lambda result: result["evidence_proof"]["slot_map"][0]["source_evidence"][0].update(text="Forged."),
])
def test_current_proof_conversion_rejects_foreign_proof_after_selection_or_evidence_changes(change):
    from cutroom.intelligence import _story_decision_from_beats

    proof, beats, segments, _ = proof_for(["The source question.", "The source conclusion."])
    result = reviewed_result(proof, beats, segments)
    change(result)

    assert _story_decision_from_beats(result, beats, segments) is None
