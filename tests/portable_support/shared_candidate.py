"""Data-only diagnostic adapter through the actual guarded planner entry.

No independent all-row-pairs enumerator, inference, editorial approval or media.
Historical v1 trial payloads remain frozen as evidence of the diagnostic bypass.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import copy
import json

from cutroom import intelligence as story
from cutroom.edit_windows import CanonicalSource, EditWindowError, build_edit_window, compile_selected_spans, _identity, _json
from cutroom.window_evidence import WindowSourceState, check_source_state
from cutroom.window_retrieval import WindowRetrievalPolicy, WindowRetrievalRequest, retrieval_policy_record

DIAGNOSTIC_PRODUCER = "actual-planner-speech-window-diagnostic-v1"

@dataclass(frozen=True)
class DiagnosticCandidateSet:
    request: WindowRetrievalRequest
    brief_json: str
    preview_json: str
    candidates_json: str
    fingerprint: str

    def candidates(self):
        return json.loads(self.candidates_json)

    def model_input(self):
        _validate_production(self)
        rows=self.request.source.rows
        return {"producer":DIAGNOSTIC_PRODUCER,"fixture_fingerprint":self.fingerprint,
            "original_request":json.loads(self.brief_json),
            "candidate_form":"contiguous diagnostic proposals; one output alone does not require continuity",
            "source_text_units":[{"n":i+1,"text":r.text} for i,r in enumerate(rows)],
            "allowed_contiguous_spans":[[c['id'],c['first'],c['last'],c['raw_seconds']] for c in self.candidates()],
            "boundary_status":"source speech hints only, not verified meaning or audio",
            "semantic_approved":False}


def _validate_production(production):
    """Detect inconsistent local fixture serialization; never ingest model-owned maps."""
    if not isinstance(production,DiagnosticCandidateSet):
        raise EditWindowError("Expected an in-memory guarded diagnostic fixture")
    source=production.request.source
    preview=json.loads(production.preview_json)
    candidates=production.candidates()
    if (preview['source_fingerprint']!=source.fingerprint
            or preview['source_descriptor']!=asdict(source.descriptor)
            or preview['project_source_state']!=asdict(production.request.state)
            or preview['retrieval']['budget']!=retrieval_policy_record(production.request.policy)):
        raise EditWindowError("Inconsistent diagnostic request binding")
    expected=_identity('diagnostic-candidate-set',[DIAGNOSTIC_PRODUCER,source.fingerprint,
        preview['cache_key'],candidates])
    if expected!=production.fingerprint or json.loads(production.brief_json)!=preview['original_request']:
        raise EditWindowError("Inconsistent diagnostic fixture identity or original request")
    offered={c['window_id'] for c in preview['ranked_candidates']}
    for i,c in enumerate(candidates):
        window=build_edit_window(source,c['first_row_id'],c['last_row_id'])
        if (c['id']!=f'd{i+1:03}' or c['window_id']!=window.id or window.id not in offered
                or source.rows[c['first']-1].id!=c['first_row_id']
                or source.rows[c['last']-1].id!=c['last_row_id']
                or abs(window.source_end-window.source_start-c['raw_seconds'])>1e-7):
            raise EditWindowError("Inconsistent diagnostic canonical mapping")


def prepare_diagnostic_candidates(source:CanonicalSource, state:WindowSourceState, brief, settings, read_current,
                                 *,defer_recovery_only_starts=True,cancel_check=None):
    if type(defer_recovery_only_starts) is not bool:
        raise EditWindowError("Diagnostic entry policy must be explicit boolean")
    policy=WindowRetrievalPolicy(speech_units=True,defer_recovery_only_starts=defer_recovery_only_starts,
        max_endpoints_per_start=64,shortlist_size=32)
    request=WindowRetrievalRequest(source,state,policy)
    original=copy.deepcopy(brief)
    preview,engine=story.plan_edit(source.transcript(),settings,original,
        source_window_request=request,source_window_state=read_current,cancel_check=cancel_check)
    if engine!='source_window_retrieval_preview' or 'decision' in preview or preview['selection'] is not None:
        raise EditWindowError("Diagnostic producer returned an unexpected authority")
    positions={r.id:i+1 for i,r in enumerate(source.rows)}
    views={v['window_id']:v for v in preview['views']}
    candidates=[]
    for item in preview['ranked_candidates']:
        view=views[item['window_id']]
        candidates.append({'id':f'd{len(candidates)+1:03}','window_id':item['window_id'],
            'first':positions[view['row_ids'][0]],'last':positions[view['row_ids'][-1]],
            'first_row_id':view['row_ids'][0],'last_row_id':view['row_ids'][-1],
            'raw_seconds':item['raw_seconds']})
    fingerprint=_identity('diagnostic-candidate-set',[DIAGNOSTIC_PRODUCER,source.fingerprint,preview['cache_key'],candidates])
    check_source_state(state,read_current,cancel_check)
    return DiagnosticCandidateSet(request,_json(brief),_json(preview),_json(candidates),fingerprint)


def offered_candidate_for_range(production,first_row_id,last_row_id):
    """Replay old selections against this producer; never add a missing window."""
    _validate_production(production)
    window=build_edit_window(production.request.source,first_row_id,last_row_id)
    match=next((c for c in production.candidates() if c['window_id']==window.id),None)
    if match is None:
        raise EditWindowError("Range was not offered by the current guarded candidate producer")
    return match['id']


def resolve_diagnostic_selection(production,candidate_id,read_current,*,cancel_check=None):
    check_source_state(production.request.state,read_current,cancel_check)
    _validate_production(production)
    if candidate_id is None:
        return {'status':'abstain_unverified_not_source_no_fit','semantic_approved':False}
    match=next((c for c in production.candidates() if c['id']==candidate_id),None)
    if match is None:
        raise EditWindowError("Unknown or unoffered diagnostic candidate ID")
    source=production.request.source
    window=build_edit_window(source,match['first_row_id'],match['last_row_id'])
    plan=compile_selected_spans(source,[window],brief=json.loads(production.brief_json))
    rows={r.id:r for r in source.rows}
    result={'status':'unreviewed_model_choice','producer':DIAGNOSTIC_PRODUCER,
        'fixture_fingerprint':production.fingerprint,'source_fingerprint':source.fingerprint,
        'window_id':window.id,'raw_seconds':plan.duration,'clip_map':plan.clip_map(),
        'row_ids':list(window.row_ids),'full_text':' '.join(rows[i].text for i in window.row_ids),
        'semantic_approved':False,'audio_verified':False}
    check_source_state(production.request.state,read_current,cancel_check)
    return result
