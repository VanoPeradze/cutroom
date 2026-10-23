"""Exact candidate identity and quote attribution, never semantic entailment."""
from __future__ import annotations
import copy
from .cache_keys import stable_fingerprint
from .story_passage_options import _diverse_shortlist

PASSAGE_REASON_CONTRACT="fixed-passage-reason-2026-10-23-v2.refusal-citations"
MAX_PRESENTED_PASSAGES=8
MAX_PASSAGE_ASSESSMENTS=3
NOMINATION_REASON="Provisional source nomination; independent semantic review required."

def source_binding(option, segments):
    wanted=option["segment_ids"]
    rows=[{k:r[k] for k in ("id","start","end","text")} for r in segments if r["id"] in set(wanted)]
    if not wanted or [r["id"] for r in rows]!=wanted:raise ValueError("Candidate source membership changed.")
    facts={"candidate_id":option["id"],"source_fingerprint":option["source_fingerprint"],
        "selected_source":rows,"playback_ranges":copy.deepcopy(option["playback_ranges"])}
    return {**facts,"fingerprint":stable_fingerprint(PASSAGE_REASON_CONTRACT,facts),
        "selected_text":" ".join(r["text"] for r in rows),"semantic_entailment_verified":False}

def validate_binding(selection, segments):
    selected=selection["passage_option_selection"]
    option=selected["option"]
    actual=source_binding(option,segments)
    if selected.get("candidate_id",option["id"])!=option["id"] or selection["keep_beat_ids"]!=option["beat_ids"]:
        raise ValueError("Candidate ID or retained units changed.")
    if "source_binding" in selected and selected["source_binding"]!=actual:
        raise ValueError("Candidate source fingerprint changed.")
    return actual

def review_source_scope(candidates, segments):
    """Reuse the retrieved domain plus explicitly retrieved context neighbors.

    Never refill a bounded review with the rest of a long canonical transcript.
    Out-of-domain prerequisites remain unknown, not automatically unnecessary.
    """
    ids={v for unit in candidates for field in ("segment_ids","context_neighbor_segment_ids") for v in unit.get(field,[])}
    return [r for r in segments if r["id"] in ids]

def presented_options(options, candidate_ids):
    """Bound one comparison call; retain the full retrieval receipt separately.

    Preserve the existing order as retrieval priority, with half the slots for
    membership diversity. Omitted choices remain unreviewed, never no-fit.
    """
    if len(options)<=MAX_PRESENTED_PASSAGES:return list(options)
    # A few intact windows preserve context that lexical/disjoint retrieval can
    # suppress. This is a generic cut-count preference, never semantic approval.
    if all("retrieval_quality" in o for o in options):
        # Keep a context-preserving window only when its observed repetition is
        # no worse than the leading retrieval prior. No four-slot override that
        # promotes known repetition ahead of the quality-aware list.
        best=options[0]["retrieval_quality"]["duplicate_fraction"]
        intact=[o for o in options if len(o["selected_source_groups"])==1
                and o["retrieval_quality"]["duplicate_fraction"]<=best][:1]
    else:
        intact=[o for o in options if len(o["selected_source_groups"])==1][:MAX_PRESENTED_PASSAGES//2]
    seed_ids={o["id"] for o in intact}
    ordered=[*intact,*[o for o in options if o["id"] not in seed_ids]]
    ranked=[((len(ordered)-i,),o) for i,o in enumerate(ordered)]
    return _diverse_shortlist(ranked,{},candidate_ids,maximum=MAX_PRESENTED_PASSAGES)

def quote_schema(ids, segments):
    rows={r["id"]:r for r in segments}
    return {"type":"array","minItems":1,"maxItems":3,"uniqueItems":True,
        "items":{"enum":[quote_reference(rows[v]) for v in ids]}}


def assessment_options(shortlist, candidate_ids):
    """Spend the finite assessment budget on different source compositions."""
    if len(shortlist)<=MAX_PASSAGE_ASSESSMENTS:return list(shortlist)
    ranked=[((len(shortlist)-i,),option) for i,option in enumerate(shortlist)]
    return _diverse_shortlist(ranked,{},candidate_ids,maximum=MAX_PASSAGE_ASSESSMENTS)

def quote_reference(row):
    return "quote_"+stable_fingerprint(PASSAGE_REASON_CONTRACT,{k:row[k] for k in ("id","start","end","text")})[:24]

def validate_reason_quotes(records, option, segments, cited):
    rows={quote_reference(r):r for r in segments if r["id"] in option["segment_ids"]}
    if not isinstance(records,list) or not 1<=len(records)<=3:raise ValueError("Selection needs bounded exact rationale quotes.")
    seen=[]
    resolved=[]
    for reference in records:
        if not isinstance(reference,str) or reference not in rows or rows[reference]["id"] in seen:
            raise ValueError("Rationale quote belongs to another candidate or rewrites source.")
        row=rows[reference]
        seen.append(row["id"])
        resolved.append({"segment_id":row["id"],"quote":row["text"],"quote_id":reference})
    if cited!=seen:raise ValueError("Rationale citations and exact quotes disagree.")
    return {"policy":PASSAGE_REASON_CONTRACT,"source_binding":source_binding(option,segments),
        "source_quotes":resolved,"attribution_verified":True,"interpretation_verified":False}
