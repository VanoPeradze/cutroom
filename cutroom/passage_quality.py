"""Language-neutral source repetition prior, never a grammar or meaning gate.

Only existing whole-unit text is indexed. No phrase is created across an edit
join. A repeated phrase can be intentional: these counts affect retrieval only,
never authorize deleting it or accepting/rejecting a candidate semantically.
"""
from __future__ import annotations

import re
from .cache_keys import stable_fingerprint
from .structured_schema import complete_object_union


QUALITY_POLICY = "source-phrase-repetition-2026-10-21-v1"
PHRASE_WORDS = 6
MAX_INDEXED_WORDS_PER_UNIT = 4096
SOURCE_REVIEW_POLICY = "bounded-source-unit-quality-2026-10-21-v1"


def source_review_identity(candidates):
    return stable_fingerprint(SOURCE_REVIEW_POLICY, [{k:r.get(k) for k in
        ("id","start","end","text","segment_ids","candidate_source_fingerprint")} for r in candidates])


def source_review_schema(candidates):
    fields = {}
    for row in candidates:
        props = {"status":{"enum":["clear","context","uncertain"]},
                 "context_direction":{"enum":["none","previous","next","both"]},
                 "source_segment_ids":{"type":"array","minItems":1,"maxItems":3,"uniqueItems":True,
                                       "items":{"enum":row["segment_ids"]}},
                 "reason":{"type":"string","minLength":1,"maxLength":180}}
        fields[row["id"]] = complete_object_union({"type":"object","additionalProperties":False,
            "properties":props,"required":list(props),"anyOf":[
                {"properties":{"status":{"const":status},"context_direction":{"const":"none"}}} for status in ("clear","uncertain")]+[
                {"properties":{"status":{"const":"context"},"context_direction":{"enum":["previous","next","both"]}}}]})
    return {"type":"object","additionalProperties":False,"properties":fields,"required":list(fields)}


def validate_source_review(reply, candidates, model):
    if not isinstance(reply,dict) or set(reply)!={r["id"] for r in candidates}:
        raise ValueError("Source quality assessment must cover exactly its bounded unit domain")
    for unit in candidates:
        row=reply[unit["id"]]
        if (not isinstance(row,dict) or set(row)!={"status","context_direction","source_segment_ids","reason"}
                or row["status"] not in {"clear","context","uncertain"}
                or row["context_direction"] not in {"none","previous","next","both"}
                or (row["status"]=="context") != (row["context_direction"]!="none")
                or not isinstance(row["reason"],str) or not row["reason"].strip() or len(row["reason"])>180
                or not isinstance(row["source_segment_ids"],list) or not 1<=len(row["source_segment_ids"])<=3
                or any(not isinstance(s,str) or s not in unit["segment_ids"] for s in row["source_segment_ids"])
                or len(set(row["source_segment_ids"]))!=len(row["source_segment_ids"])):
            raise ValueError("Invalid source quality attribution or context direction")
    return {"policy":SOURCE_REVIEW_POLICY,"source_identity":source_review_identity(candidates),
            "model":model,"units":reply,"interpretation_verified":False,"authority":"retrieval_advice_only"}


def source_review_prior(review, candidates, indices, full_positions):
    """Caller validates source identity and record shape once before enumeration."""
    if review is None:return 0.,0
    selected=set(indices);uncertain=0.;missing=0
    for i in indices:
        row=review["units"][candidates[i]["id"]]
        if row["status"]=="uncertain":uncertain+=candidates[i]["end"]-candidates[i]["start"]
        if row["status"]=="context":
            direction=row["context_direction"]
            previous=i-1 in selected and full_positions[i]-full_positions[i-1]==1
            following=i+1 in selected and full_positions[i+1]-full_positions[i]==1
            missing+=int(direction in {"previous","both"} and not previous)
            missing+=int(direction in {"next","both"} and not following)
    duration=sum(candidates[i]["end"]-candidates[i]["start"] for i in indices)
    return uncertain/max(duration,1e-9),missing


class SourcePhraseIndex:
    def __init__(self, candidates):
        phrases = {}
        self.units = []
        for candidate in candidates:
            words = []
            for match in re.finditer(r"[^\W_]+", candidate["text"].casefold()):
                words.append(match.group())
                if len(words) > MAX_INDEXED_WORDS_PER_UNIT:
                    break
            if len(words) > MAX_INDEXED_WORDS_PER_UNIT:
                # No first-N quality claim; the canonical source is untouched.
                self.units.append(None)
                continue
            windows = [tuple(words[i:i+PHRASE_WORDS]) for i in range(len(words)-PHRASE_WORDS+1)]
            mask = 0
            for phrase in windows:
                position = phrases.setdefault(phrase, len(phrases))
                mask |= 1 << position
            self.units.append((mask, len(windows)))

    def measure(self, indices):
        seen = total = duplicates = unavailable = 0
        for index in indices:
            unit = self.units[index]
            if unit is None:
                unavailable += 1
                continue
            mask, count = unit
            duplicates += count-mask.bit_count() + (seen & mask).bit_count()
            total += count
            seen |= mask
        return {"policy": QUALITY_POLICY, "phrase_words": PHRASE_WORDS,
                "duplicate_phrase_windows": duplicates, "source_phrase_windows": total,
                "duplicate_fraction": duplicates / max(total, 1),
                "unavailable_units": unavailable, "semantic_quality_verified": False,
                "scope": "phrases inside whole source units only; no words altered; intentional repetition may be valid"}
