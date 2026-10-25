"""Output count differs from explicit cut policy; synthetic mechanics only."""
import copy
import socket
from types import SimpleNamespace
import urllib.request
import pytest

from cutroom import ai_runtime,cache_keys,director,intelligence as story
from cutroom import instruction_contract as contracts
from cutroom.story_budget import StoryBudgetError,StoryPlanningError
from tests.test_director_source_continuity import selected_span,SPAN,request as director_request
from test_director_rebuild_cache import semantic_project


@pytest.fixture(autouse=True)
def no_model_or_media(monkeypatch):
    def forbidden(*a,**kw):pytest.fail('Instruction qualification cannot use a model/network/media process')
    for module in (story,ai_runtime):monkeypatch.setattr(module,'open_ollama',forbidden)
    for name in ('_call_ollama_story_pass','_ollama_chat','story_ai_status'):
        monkeypatch.setattr(story,name,forbidden)
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(urllib.request,'urlopen',forbidden)


EN='Make one video without cuts.'
HE='צור סרטון אחד בלי חיתוכים.'

def brief(instruction,**kw):
    return {'goal':'short','target_duration':60.,'duration_mode':'target','instruction':instruction,**kw}


@pytest.mark.parametrize('instruction',[
    EN,'Make one video with no cuts.','Please create a single Short without any cuts.',
    'Produce one clip without internal cuts.','Deliver me one output with no internal cuts.',
    'Edit a video, without cuts.','I want one video without cuts.','I need a single clip with no cuts.',
    HE,'צור סרטון אחד ללא חיתוכים.','בבקשה תעשה לי וידאו אחד בלי חיתוכים.',
    'תכיני קליפ אחד ללא קאטים.','ערוך סרטון ללא חיתוכים פנימיים.',
    'אני רוצה סרטון אחד בלי חיתוכים.','אני צריכה קליפ אחד ללא חיתוכים.',
])
def test_explicit_output_cut_policy_has_exact_original_provenance(instruction):
    value=brief(instruction);before=copy.deepcopy(value)
    c=contracts.assert_instruction_contract(value)
    assert contracts.explicit_source_continuity_requested(value)
    assert c['selection_controls']['source_continuity']=='required'
    controls=[r for row in c['requirements'] for r in row['recognized_controls'] if r['kind']=='source_continuity']
    assert len(controls)==1
    control=controls[0]
    assert instruction[control['instruction_start']:control['instruction_end']]==control['text']
    assert control['mandatory'] and control['origin']=='explicit_user_instruction'
    assert control['verification']=='source_continuity_unverified'
    assert c['verification_status']=='unverified' and value==before and c['instruction']==instruction


@pytest.mark.parametrize('instruction',[
    'Make one video.','Create a single Short.','Deliver one output with several related cuts.',
    'צור סרטון אחד.','תעשה לי וידאו אחד.','צור סרטון אחד עם חיתוכים.',
    'Make one video without invented speech.','Make one video without jump cuts.',
    'Make one continuous video.','צור סרטון אחד בלי מוזיקה.','צור סרטון אחד בלי לחתוך את ההקשר.',
])
def test_output_count_or_other_without_object_does_not_forbid_source_cuts(instruction):
    c=contracts.build_instruction_contract(brief(instruction))
    assert c['selection_controls']['source_continuity']=='unspecified'
    assert not contracts.explicit_source_continuity_requested(brief(instruction))


@pytest.mark.parametrize('instruction',[
    'Do not make one video without cuts.','Never create one clip without cuts.',
    "Don't make one video without cuts.",'Make one video not without cuts.',
    'Make one video without cuts if possible.','If possible, make one video without cuts.',
    'Make one video without cuts, unless necessary.','Make one video without cuts or use a montage.',
    'Make one video without cuts for each speaker.','Make two videos without cuts.',
    '"Make one video without cuts."','For example\nMake one video without cuts.',
    'Make one video without cuts. "unmatched quotation',
    'אל תעשה סרטון אחד בלי חיתוכים.','לא ליצור סרטון אחד ללא חיתוכים.',
    'אני לא רוצה סרטון אחד בלי חיתוכים.','צור סרטון אחד בלי חיתוכים אם אפשר.',
    'אם אפשר, צור סרטון אחד בלי חיתוכים.','צור סרטון אחד בלי חיתוכים לכל דובר.',
    'צור שני סרטונים בלי חיתוכים.','״צור סרטון אחד בלי חיתוכים.״',
    'צור סרטון אחד בלי חיתוכים, אבל לא רציף.',
    'Make one video without cuts in the intro.','Make one video without cuts to the audio.',
    'Make one video without cuts, only in the intro.',
    'Make one video without cuts, but only in the intro.',
    'Make one video without cuts and do not preserve continuity.',
    'Make one video without cuts, but with cuts.',
    'צור סרטון בלי חיתוכים בפתיח.','צור סרטון בלי חיתוכים באודיו.',
    'צור סרטון בלי חיתוכים, אבל רק בפתיח.','צור סרטון בלי חיתוכים, אבל עם חיתוכים.',
    'Make one video with cuts, but preserve the selected source passage continuous only in the intro.',
    'Preserve the selected source passage continuous only in the intro, but make one video with cuts.',
    'צור סרטון אחד עם חיתוכים, אבל שמור על קטע המקור בלי חיתוכים בפתיח.',
    'שמור על קטע המקור בלי חיתוכים בפתיח, אבל צור סרטון אחד עם חיתוכים.',
])
def test_negation_conditions_quotes_alternatives_and_multiple_outputs_remain_unspecified(instruction):
    c=contracts.build_instruction_contract(brief(instruction))
    assert not contracts.explicit_source_continuity_requested(brief(instruction))
    assert c['selection_controls']['source_continuity']=='unspecified'


@pytest.mark.parametrize('instruction',[
    'Make one video without cuts. Allow internal cuts.',
    'Make one video without cuts, but related cuts are allowed.',
    'Make one video without cuts. Make one video with cuts.',
    'Create a single clip with cuts. Create a single clip without cuts.',
    'צור סרטון אחד בלי חיתוכים. מותר לבצע חיתוכים פנימיים.',
    'צור סרטון אחד בלי חיתוכים, אבל מותר לבצע חיתוכים פנימיים.',
    'צור סרטון אחד בלי חיתוכים. צור סרטון אחד עם חיתוכים.',
    'Make one video with cuts, but make one video without cuts.',
    'Make one video without cuts, but make one video with cuts.',
    'Allow internal cuts, but make one video without cuts.',
    'Make one video with cuts, but choose one continuous source passage.',
    'צור סרטון אחד עם חיתוכים, אבל צור סרטון אחד בלי חיתוכים.',
    'צור סרטון אחד בלי חיתוכים, אבל צור סרטון אחד עם חיתוכים.',
])
def test_opposed_explicit_cut_policies_block_before_planner_or_mutation(instruction,monkeypatch):
    value=brief(instruction);before=copy.deepcopy(value)
    assert contracts.build_instruction_contract(value)['selection_controls']['source_continuity']=='conflict'
    monkeypatch.setattr(story,'hierarchical_story_edit',lambda *a,**kw:pytest.fail('Known conflict must preflight'))
    with pytest.raises(StoryBudgetError) as caught:
        story.plan_edit([{'id':'s','start':0.,'end':60.,'text':'Unchanged complete source.'}],SimpleNamespace(ai={}),value)
    assert caught.value.diagnostic['reason']=='instruction_source_continuity_conflict'
    assert caught.value.diagnostic['applied_to_timeline'] is False and value==before


@pytest.mark.parametrize('instruction,required',[(EN,True),(HE,True),('Make one video.',False),('צור סרטון אחד.',False)])
def test_actual_default_plan_entry_receives_cut_policy_separate_from_output_count(monkeypatch,instruction,required):
    rows=[{'id':'s1','start':0.,'end':30.,'text':'First unchanged complete statement.'},
          {'id':'s2','start':31.,'end':61.,'text':'Second unchanged complete statement.'}]
    value=brief(instruction);before=copy.deepcopy((rows,value));seen=[]
    def planner(beats,segments,settings,enriched,*a,**kw):
        seen.append(copy.deepcopy(enriched))
        return {'keep_ids':['s1','s2'],'remove_ids':[],'highlight_ids':[]},{}
    monkeypatch.setattr(story,'hierarchical_story_edit',planner)
    editorial,engine=story.plan_edit(rows,SimpleNamespace(ai={}),value)
    assert engine=='ollama_hierarchical_story' and seen
    assert seen[0]['style_profile']['selection_policy']['preserve_source_continuity'] is required
    assert editorial['instruction_contract']['selection_controls']['source_continuity']==('required' if required else 'unspecified')
    assert contracts.single_output_requested(value) and (rows,value)==before
    assert editorial['instruction_contract']['verification_status']=='unverified'


@pytest.mark.parametrize('instruction',[EN,HE])
def test_director_preserves_pauses_persists_original_and_reuses_matching_cache(semantic_project,monkeypatch,instruction):
    store,settings,pid,calls,context=semantic_project;policies=selected_span(monkeypatch)
    def no_cleanup(*a,**kw):pytest.fail('Explicit no-cuts must not remove source pauses')
    for name in ('_short_cleanup_cuts_with_floor','_cut_dead_screens','_enforce_short_target',
                 '_drop_isolated_micro_keeps','_compact_story_pauses_to_target'):
        monkeypatch.setattr(director,name,no_cleanup)
    result=director.analyze_project(context(),pid,store,settings,director_request(instruction))
    saved=store.load(pid);report=saved['draft']['instruction_contract']
    assert saved['draft']['keep_ranges']==SPAN and policies and all(p['preserve_source_continuity'] for p in policies)
    assert report['instruction']==instruction==saved['settings']['instruction']
    assert report['version']==contracts.INSTRUCTION_CONTRACT_VERSION
    proof=report['source_continuity_proof'];assert proof['source_continuity_verified'] and proof['mechanical_only']
    assert not proof['semantic_coherence_verified'] and not proof['final_export_verified']
    count=copy.deepcopy(calls)
    director.analyze_project(context(),pid,store,settings)
    assert calls==count and store.load(pid)['draft']['instruction_contract']==report


@pytest.mark.parametrize('instruction',['Make one video.','צור סרטון אחד.'])
def test_director_one_output_still_permits_real_cleanup_ranges(semantic_project,monkeypatch,instruction):
    store,settings,pid,calls,context=semantic_project;policies=selected_span(monkeypatch)
    result=director.analyze_project(context(),pid,store,settings,director_request(instruction))
    assert policies and all(not p['preserve_source_continuity'] for p in policies)
    assert result['draft']['keep_ranges']==[{'start':30.,'end':38.1},{'start':39.9,'end':60.}]
    assert result['instruction_contract']['source_continuity_proof']['status']=='not_requested'


@pytest.mark.parametrize('instruction',[EN,HE])
def test_director_manual_cut_conflict_preserves_saved_project_and_history(semantic_project,monkeypatch,instruction):
    store,settings,pid,calls,context=semantic_project;selected_span(monkeypatch)
    def add_cut(project):
        project['manual']['cuts']=[{'start':43.,'end':45.}]
        project['manual']['_history']={'undo':[{'action':'saved-cut'}],'redo':[]}
    store.update(pid,add_cut);before=store.state_path(pid).read_bytes();job=context()
    with pytest.raises(StoryPlanningError) as caught:
        director.analyze_project(job,pid,store,settings,director_request(instruction))
    assert caught.value.diagnostic['reason']=='explicit_source_continuity_conflict'
    assert store.state_path(pid).read_bytes()==before and not job.committed


@pytest.mark.parametrize('base,range_instruction,exact',[
    (EN,'Aim for 45-60 seconds.','Make exactly 60 seconds.'),
    (HE,'כוון ל45-60 שניות.','צור סרטון של 60 שניות.'),
])
def test_cut_policy_does_not_change_explicit_duration_precedence(base,range_instruction,exact):
    ranged=brief(base+' '+range_instruction)
    bounds=contracts.effective_duration_bounds(ranged)
    assert (bounds['minimum_seconds'],bounds['maximum_seconds'])==(45.,60.)
    assert bounds['origin']=='explicit_user_range'
    exact_bounds=contracts.effective_duration_bounds(brief(base+' '+exact))
    assert (exact_bounds['minimum_seconds'],exact_bounds['maximum_seconds'])==(60.,60.)
    with pytest.raises(StoryBudgetError):contracts.assert_instruction_contract(brief(base+' '+exact,target_duration=30.))


def test_parser_upgrade_invalidates_story_caches_but_preserves_source_asr_identity(monkeypatch):
    rows=[{'id':'s','start':0.,'end':60.,'text':'Source identity does not change.'}]
    settings=SimpleNamespace(ai={},raw={});value=brief(EN)
    current=cache_keys.build_analysis_cache_fingerprints({},settings,value,{})
    current_story=story.story_cache_fingerprint(rows,value,'fixture-model')
    with monkeypatch.context() as legacy:
        legacy.setattr(cache_keys,'STORY_INPUT_POLICY','bounded-whole-index-canonical-domain-retrieval-v15.source-quality-retrieval')
        legacy.setattr(story,'STORY_CACHE_PIPELINE','hierarchical-story-2026-10-21.v26.source-quality-retrieval')
        prior=cache_keys.build_analysis_cache_fingerprints({},settings,value,{})
        prior_story=story.story_cache_fingerprint(rows,value,'fixture-model')
    assert current['story']!=prior['story'] and current_story!=prior_story
    assert all(current[k]==prior[k] for k in ('pipeline','source','transcript','scenes','vision'))
    assert not cache_keys.cache_fingerprints_match(prior,current,('story',))


@pytest.mark.parametrize('instruction',['Make one video with cuts.','צור סרטון אחד עם חיתוכים.'])
def test_permission_does_not_require_an_edit_or_one_semantic_unit(instruction):
    c=contracts.assert_instruction_contract(brief(instruction))
    assert c['selection_controls']['related_source_cuts_allowed'] is True
    assert c['selection_controls']['source_continuity']=='unspecified'
    assert c['selection_controls'].get('semantic_unit_count') is None
    controls=[v for r in c['requirements'] for v in r['recognized_controls'] if v['kind']=='source_cuts_allowed']
    assert len(controls)==1 and controls[0]['permission'] is True and controls[0]['mandatory'] is False


@pytest.mark.parametrize('instruction',[EN,HE])
def test_director_blocks_disjoint_planner_ranges_without_consuming_saved_edit(semantic_project,monkeypatch,instruction):
    store,settings,pid,calls,context=semantic_project;selected_span(monkeypatch)
    monkeypatch.setattr(director,'_select_short_story_ranges',lambda *a,**kw:[
        {'start':30.,'end':40.},{'start':50.,'end':60.}])
    before=store.state_path(pid).read_bytes();job=context()
    with pytest.raises(StoryPlanningError) as caught:
        director.analyze_project(job,pid,store,settings,director_request(instruction))
    assert caught.value.diagnostic['reason']=='explicit_source_continuity_conflict'
    assert not job.committed and store.state_path(pid).read_bytes()==before


def test_director_replans_legacy_story_key_without_retranscribing(semantic_project,monkeypatch):
    store,settings,pid,calls,context=semantic_project;selected_span(monkeypatch)
    # Seed a real persisted analysis under the preceding Story policy. Planner
    # and ASR are synthetic; all Director cache/save decisions remain real.
    with monkeypatch.context() as legacy:
        legacy.setattr(cache_keys,'STORY_INPUT_POLICY','bounded-whole-index-canonical-domain-retrieval-v15.source-quality-retrieval')
        legacy.setattr(story,'STORY_CACHE_PIPELINE','hierarchical-story-2026-10-21.v26.source-quality-retrieval')
        director.analyze_project(context(),pid,store,settings,director_request(EN))
    before=copy.deepcopy(calls);old=store.load(pid)['analysis']['cache_fingerprints']
    director.analyze_project(context(),pid,store,settings)
    after=store.load(pid)['analysis']['cache_fingerprints']
    assert calls['transcribe']==before['transcribe'] and calls['plan']==before['plan']+1
    assert old['story']!=after['story'] and old['transcript']==after['transcript']
    assert store.load(pid)['draft']['keep_ranges']==SPAN
