"""Well-formed nomination fixtures; never adapt recorded malformed responses."""
from cutroom.passage_binding import NOMINATION_REASON,quote_reference

def nominate(option, data):
    rows={r["id"]:r for r in data["source_utterances"]}
    identifier=option["segment_ids"][0]
    return {"verdict":"fit","candidate_id":option["id"],"semantic_reason":NOMINATION_REASON,
        "refusal_category":"none","cited_segment_ids":[],
        "reason_evidence":[quote_reference(rows[identifier])]}


def refuse(option, data):
    """Well-attributed model rejection; its interpretation remains unverified."""
    identifier=option['segment_ids'][0]
    assert identifier in {r['id'] for r in data['source_utterances']}
    return {'verdict':'no_fit','candidate_id':None,
            'semantic_reason':'Fixture model rejects the cited selected-source context.',
            'refusal_category':'semantic_rejection','cited_segment_ids':[identifier],
            'reason_evidence':[]}
