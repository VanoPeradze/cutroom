"""Actual-entry/diagnostic producer parity; no semantic or audio truth claims."""
import copy
import importlib.util
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import intelligence as story
from cutroom.edit_windows import EditWindowError,SourceDescriptor,build_canonical_source
from cutroom.window_evidence import WindowSourceState
from cutroom.window_retrieval import (WindowRetrievalPolicy,WindowRetrievalRequest,build_speech_unit_index,
    produce_speech_window_candidates,retrieve_windows,retrieval_policy_record)
from tests.test_speech_unit_search import no_inference_or_network

ROOT=Path(__file__).resolve().parents[1]
from tests.portable_support import shared_candidate as diagnostic
from tests.portable_support.source_fixture import source_fixture

def brief(language='en'):
    return {'goal':'short','target_duration':60.,'duration_mode':'target','language':language,
        'instruction':'Make one video without cuts. Aim for45-60seconds. Preserve meaning.' if language=='en' else
        'צור סרטון אחד בלי חיתוכים. כוון ל45-60 שניות ושמור על המשמעות.'}

def source(rows,origin=120.):
    desc=SourceDescriptor('primary:A','saved-generation','transcript',1000.,origin)
    src=build_canonical_source(rows,desc);state=WindowSourceState('project_0123456789ab',3,desc)
    return src,state

def sample(language='en'):
    texts=(['A thought ends. Then an unfinished subject','More severe than it was before.',
        'A separate complete account begins here.','We tested the actual result.','The evidence stayed intact.',
        'This is the conclusion.','Another point is complete.'] if language=='en' else
        ['המשפט הקודם נגמר. ואז תיאור לא גמור','שלא היה לי בחיים אף פעם.',
         'כאן מתחיל סיפור עצמאי חדש.','בדקנו את התוצאה בפועל.','הראיות נשמרו בלי שינוי.',
         'זו המסקנה של הסיפור.','נקודה אחרת מסתיימת כאן.'])
    return [{'id':f's{i}','start':i*10.,'end':(i+1)*10.,'text':t} for i,t in enumerate(texts)]

def build(rows,language='en',defer=True,reader=None,cancel=None):
    src,state=source(rows)
    value=diagnostic.prepare_diagnostic_candidates(src,state,brief(language),SimpleNamespace(ai={}),
        reader or (lambda:state),defer_recovery_only_starts=defer,cancel_check=cancel)
    return value,src,state

@pytest.mark.parametrize('language',['en','he'])
def test_recovery_only_start_is_deferred_without_deleting_or_rewriting_source(language):
    rows=sample(language);before=copy.deepcopy(rows)
    allowed,src,state=build(rows,language,False);strict,_,_=build(rows,language,True)
    a=json.loads(allowed.preview_json);b=json.loads(strict.preview_json)
    assert a['canonical_evidence']==b['canonical_evidence']
    assert a['canonical_ownership']==b['canonical_ownership'] and rows==before
    coverage=b['retrieval']['entry_boundary_coverage']
    assert coverage['deferred_start_row_ids']==['s1'] and coverage['source_rows_removed']==0
    assert coverage['deferred_numeric_pairs']>0 and coverage['semantic_truth_verified'] is False
    assert any(c['first_row_id']=='s1' for c in allowed.candidates())
    assert all(c['first_row_id']!='s1' for c in strict.candidates())
    assert b['selection'] is None and 'decision' not in b
    assert allowed.fingerprint!=strict.fingerprint

@pytest.mark.parametrize('hint',['gap','speaker'])
def test_additional_structural_cue_keeps_recovery_start_but_never_verifies_meaning(hint):
    rows=sample()
    if hint=='gap':
        for r in rows[1:]:r['start']+=1.;r['end']+=1.
    else:rows[0]['speaker']='a';rows[1]['speaker']='b'
    strict,_,_=build(rows)
    report=json.loads(strict.preview_json)['retrieval']['entry_boundary_coverage']
    assert 's1' not in report['deferred_start_row_ids']
    assert any(c['first_row_id']=='s1' for c in strict.candidates())
    assert report['semantic_truth_verified'] is False

def test_actual_entry_and_diagnostic_use_the_same_guarded_producer(monkeypatch):
    import cutroom.window_retrieval as module
    calls=[];original=module.produce_speech_window_candidates
    def observed(*a,**k):
        result=original(*a,**k);calls.append(result[1].fingerprint);return result
    monkeypatch.setattr(module,'produce_speech_window_candidates',observed)
    production,src,state=build(sample())
    policy=production.request.policy
    preview,engine=story.plan_edit(src.transcript(),SimpleNamespace(ai={}),brief(),
        source_window_request=WindowRetrievalRequest(src,state,policy),source_window_state=lambda:state)
    assert engine=='source_window_retrieval_preview' and len(calls)==2 and calls[0]==calls[1]
    assert preview['ranked_candidates']==json.loads(production.preview_json)['ranked_candidates']

def test_guarded_producer_refuses_raw_policy_and_default_cache_record_is_unchanged():
    rows=sample();src,_=source(rows)
    with pytest.raises(EditWindowError):
        produce_speech_window_candidates(src,[],{'minimum_seconds':45,'maximum_seconds':60},WindowRetrievalPolicy())
    old={'max_source_starts':2048,'max_pairs':16384,'max_endpoints_per_start':8,'shortlist_size':16,
        'max_view_row_references':4096,'max_view_text_characters':250000}
    assert retrieval_policy_record(WindowRetrievalPolicy())==old
    assert retrieval_policy_record(WindowRetrievalPolicy(speech_units=True))=={**old,'speech_units':True}
    with pytest.raises(EditWindowError):WindowRetrievalPolicy(defer_recovery_only_starts=True)
    with pytest.raises(EditWindowError):WindowRetrievalPolicy(speech_units=True,defer_recovery_only_starts='yes')

def test_resolver_retains_exact_source_offset_text_and_rejects_unknown_selection():
    production,src,state=build(sample());candidate=production.candidates()[0]
    result=diagnostic.resolve_diagnostic_selection(production,candidate['id'],lambda:state)
    rows=src.rows[candidate['first']-1:candidate['last']]
    assert result['full_text']==' '.join(r.text for r in rows)
    assert result['clip_map'][0]['source_start']==rows[0].start+120.
    assert result['semantic_approved'] is False and result['audio_verified'] is False
    with pytest.raises(EditWindowError):diagnostic.resolve_diagnostic_selection(production,'not-offered',lambda:state)
    assert diagnostic.resolve_diagnostic_selection(production,None,lambda:state)['status']=='abstain_unverified_not_source_no_fit'

def test_source_revision_change_and_cancellation_do_not_return_a_selection():
    production,src,state=build(sample())
    with pytest.raises(EditWindowError):
        diagnostic.resolve_diagnostic_selection(production,production.candidates()[0]['id'],lambda:replace(state,revision=4))
    def cancel():raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError,match='cancelled'):build(sample(),cancel=cancel)


def test_original_request_is_preserved_and_fixture_edits_are_rejected():
    production,src,state=build(sample())
    assert production.model_input()['original_request']==brief()
    candidates=production.candidates();candidates[0]['last_row_id']='s0'
    with pytest.raises(EditWindowError,match='identity'):
        diagnostic.resolve_diagnostic_selection(replace(production,candidates_json=json.dumps(candidates)),
            'd001',lambda:state)
    with pytest.raises(EditWindowError,match='original request'):
        replace(production,brief_json=json.dumps({**brief(),'instruction':'different'})).model_input()
    rebound=replace(state,revision=4)
    with pytest.raises(EditWindowError,match='request binding'):
        diagnostic.resolve_diagnostic_selection(replace(production,request=replace(production.request,state=rebound)),
            'd001',lambda:rebound)
    readings=iter([state,replace(state,revision=4)])
    with pytest.raises(EditWindowError):
        diagnostic.resolve_diagnostic_selection(production,'d001',lambda:next(readings))


def test_all_feasible_starts_deferred_means_context_review_not_source_no_fit():
    rows=[{'id':'s0','start':0.,'end':20.,'text':'A thought ends. Then an unfinished subject'},
          {'id':'s1','start':20.,'end':70.,'text':'More severe than it ever was before.'}]
    strict,src,state=build(rows)
    assert strict.candidates()==[]
    receipt=json.loads(strict.preview_json)['retrieval']
    assert receipt['status']=='entry_context_review_needed'
    assert receipt['entry_boundary_coverage']['deferred_numeric_pairs']==1
    assert diagnostic.resolve_diagnostic_selection(strict,None,lambda:state)['semantic_approved'] is False


@pytest.mark.parametrize('resumable',[False,True])
def test_strict_entry_policy_reaches_actual_composition_and_resumable_components(tmp_path,resumable):
    from cutroom.window_composition import WindowCompositionPolicy,WindowCompositionRequest
    from cutroom.window_search import SearchStore,ResumableSearchRequest
    rows=sample();src,state=source(rows)
    windows=WindowCompositionPolicy().windows
    policy=WindowCompositionPolicy(windows=replace(windows,speech_units=True,defer_recovery_only_starts=True))
    request=WindowCompositionRequest(src,state,policy,
        ResumableSearchRequest(SearchStore(tmp_path)) if resumable else None)
    intent={**brief(),'instruction':'Make one video. Aim for45-60seconds. Preserve meaning.'}
    result,engine=story.plan_edit(src.transcript(),SimpleNamespace(ai={}),intent,
        source_window_request=request,source_window_state=lambda:state)
    assert result['selection'] is None and 'decision' not in result
    assert result['composition']['entry_boundary_coverage']['deferred_start_row_ids']==['s1']
    assert all(v['row_ids'][0]!='s1' for v in result['views'])


@pytest.mark.parametrize('speech',[False,True])
def test_default_durable_search_binding_retains_preexisting_serialized_shape(tmp_path,monkeypatch,speech):
    from dataclasses import asdict
    import cutroom.window_search as search
    from cutroom.edit_windows import _identity
    from tests.test_resumable_window_search import setup
    rows,req,src,units,cursor=setup(tmp_path)
    policy=replace(req.policy,windows=replace(req.policy.windows,speech_units=speech))
    observed=[]
    def capture(kind,data):
        if kind=='resumable-search-input':observed.append(data)
        return _identity(kind,data)
    monkeypatch.setattr(search,'_identity',capture)
    search.discover_page(src,{'minimum_seconds':3.,'maximum_seconds':9.},policy,cursor,['legacy'],
        units=units if speech else None)
    expected=asdict(policy);expected['windows'].pop('defer_recovery_only_starts')
    assert observed[0][6]==expected and observed[0][6]['windows']['speech_units'] is speech
    record=cursor.store.read(tmp_path/(cursor.run_id+'.json'))
    assert record['identity']==_identity('resumable-search-input',observed[0])

def test_portable_regressions_use_the_same_evaluation_producer():
    english,_,_=build(source_fixture()["segments"])
    for first,last in [('s0001','s0009'),('s0014','s0029')]:
        with pytest.raises(EditWindowError,match='not offered'):
            diagnostic.offered_candidate_for_range(english,first,last)
    rows=source_fixture('he')['segments']
    permissive,_,_=build(rows,'he',False);strict,_,state=build(rows,'he',True)
    assert diagnostic.offered_candidate_for_range(permissive,'s0006','s0021')
    with pytest.raises(EditWindowError,match='not offered'):
        diagnostic.offered_candidate_for_range(strict,'s0006','s0021')
    candidate=diagnostic.offered_candidate_for_range(strict,'s0001','s0016')
    result=diagnostic.resolve_diagnostic_selection(strict,candidate,lambda:state)
    assert result['raw_seconds']==pytest.approx(54.49)
    assert result['full_text'].startswith('רגע, נבדוק את החיבור.')
