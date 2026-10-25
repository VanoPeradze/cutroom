"""Actual planner/Director recovery; source mechanics, never editorial approval."""
import copy
from types import SimpleNamespace

import pytest

from cutroom import director, intelligence as story
from cutroom.edit_styles import enrich_brief_with_style
from cutroom.jobs import JobCancelled
from cutroom.story_budget import StoryPlanningError
from cutroom.story_candidates import source_identity_rows
from test_director_rebuild_cache import semantic_project


def request(language='en', **extra):
    text = ('Make one video without cuts. Aim for 45-60 seconds.' if language == 'en'
            else 'צור סרטון אחד בלי חיתוכים. כוון ל45-60 שניות.')
    return {'goal':'short','instruction':text,'output_count':1,'source_continuity':'required',
            'duration_mode':'target','target_duration':60.,'fps':30,'language':language,
            'allow_extractive_rough_cut':True,**extra}


def segments(language='en'):
    text = ('Participation is not required.' if language == 'en' else 'אין חובה להשתתף.')
    return [{'id':f's{i}','start':i*10.,'end':i*10.+8.,'text':text,'words':[]} for i in range(10)]


def failure(rows, *, reason='passage_verification_unfinished'):
    # Emulate the existing automatic native shortlist, never a supplied answer:
    # consecutive complete groups in source order, bounded at eight options.
    options=[]
    for i in range(len(rows)-5):
        group=rows[i:i+6]
        options.append({'id':f'automatic-{i}','segment_ids':[r['id'] for r in group],
                        'playback_ranges':[{'start':group[0]['start'],'end':group[-1]['end']}]})
    return StoryPlanningError('Saved model verification remained unfinished.',{
        'reason':reason,'outcome':'technical_error','source_wide_no_fit_proven':False,
        'passage_options':{'source_segments':source_identity_rows(rows),'review_candidates':options[:8]}})


def planner(monkeypatch, rows, brief, make_failure=failure, **kwargs):
    def stopped(_beats,current,*_args,**_kwargs):raise make_failure(current)
    monkeypatch.setattr(story,'hierarchical_story_edit',stopped)
    return story.plan_edit(rows,SimpleNamespace(ai={}),brief,**kwargs)


@pytest.mark.parametrize('language',['he','en'])
def test_actual_planner_recovers_automatically_and_director_accepts_exact_whole_source(monkeypatch,language):
    rows=segments(language);brief=request(language);before=copy.deepcopy((rows,brief))
    editorial,engine=planner(monkeypatch,rows,brief)
    assert engine==story.EXTRACTIVE_ROUGH_CUT_ENGINE
    decision=editorial['decision'];requirements=decision['extractive_requirements']
    assert requirements['recovery']['mode']=='automatic_ranked_source_recovery'
    assert requirements['recovery']['rank']==1 and decision['keep_ids']==[f's{i}' for i in range(6)]
    assert decision['generative_approved'] is False and decision['review_required'] is True
    assert decision['semantic_review_status']=='not_model_reviewed'
    assert decision['instruction_contract']['verification_status']=='unverified'
    ranges=[{'start':0.,'end':58.}]
    proof=director._validate_extractive_selection(decision,rows,98.,60.,fps=30,
        selection_policy={'preserve_source_continuity':True,'duration_mode':'target',
                          'duration_bounds':story.effective_duration_bounds(brief,98.)},keep_ranges=ranges)
    assert proof['reasons']==[]
    assert ('not required' if language=='en' else 'אין חובה') in decision['summary']
    assert (rows,brief)==before


@pytest.mark.parametrize('language',['he','en'])
@pytest.mark.parametrize('fault',['disabled','stale_words','stale_time','duration','cuts','missing_speech',
                                  'repeat','foreign','unsupported_count','source_conflict','manual_candidate',
                                  'roles','constraint_failure','unknown_failure'])
def test_unsafe_recovery_preserves_original_failure_and_inputs(monkeypatch,language,fault):
    rows=segments(language);brief=request(language)
    def broken(current):
        error=failure(current);receipt=error.diagnostic['passage_options']
        if fault=='disabled':brief['allow_extractive_rough_cut']=False
        if fault=='stale_words':receipt['source_segments'][0]['text']='Changed source words.'
        if fault=='stale_time':receipt['source_segments'][0]['start']=.1
        if fault=='duration':
            for r in receipt['review_candidates']:r['playback_ranges'][0]['end']-=10
        if fault=='cuts':
            for r in receipt['review_candidates']:
                a=r['playback_ranges'][0];r['playback_ranges']=[{'start':a['start'],'end':a['start']+28},
                                                            {'start':a['start']+30,'end':a['end']}]
        if fault=='missing_speech':
            for r in receipt['review_candidates']:r['segment_ids']=r['segment_ids'][:-1]
        if fault=='repeat':
            for r in receipt['review_candidates']:r['segment_ids'].append(r['segment_ids'][0])
        if fault=='foreign':
            for r in receipt['review_candidates']:r['segment_ids'][0]='foreign'
        if fault=='unsupported_count':brief['output_count']=2
        if fault=='source_conflict':error.diagnostic['source_wide_no_fit_proven']=True
        if fault=='manual_candidate':brief['source_candidate_segment_ids']=['s0']
        if fault=='roles':brief['instruction']='Make one video. Structure: context -> result.'
        if fault=='constraint_failure':error.diagnostic.update(reason='no_feasible_passage_options',outcome='constraint_conflict')
        if fault=='unknown_failure':error.diagnostic['reason']='unrecognized_error'
        return error
    # Call the adapter directly so mutated test requests do not bypass the
    # normal entry's earlier instruction guard. Any unsafe outcome is declined.
    error=broken(rows);before=copy.deepcopy((rows,brief,error.diagnostic))
    assert story._early_extractive_rough_cut(rows,enrich_brief_with_style(brief),error) is None
    assert (rows,brief,error.diagnostic)==before


def test_cancellation_never_becomes_a_rough_cut():
    rows=segments();brief=enrich_brief_with_style(request())
    def cancel():raise JobCancelled('Cancelled')
    with pytest.raises(JobCancelled):story._early_extractive_rough_cut(rows,brief,failure(rows),cancel)


@pytest.mark.parametrize('bad',[[],['invalid'],[None],['duplicate']])
def test_malformed_receipt_cannot_turn_into_recovery(bad):
    rows=segments();error=failure(rows)
    if bad==[]:error.diagnostic['passage_options']=['invalid']
    elif bad==['duplicate']:
        choices=error.diagnostic['passage_options']['review_candidates']
        choices[1]['id']=choices[0]['id']
    else:error.diagnostic['passage_options']['review_candidates']=bad
    assert story._early_extractive_rough_cut(rows,enrich_brief_with_style(request()),error) is None


def test_actual_planner_keeps_opt_out_as_suggestion_only_failure(monkeypatch):
    rows=segments();brief=request(allow_extractive_rough_cut=False)
    with pytest.raises(StoryPlanningError) as caught:planner(monkeypatch,rows,brief)
    assert caught.value.diagnostic['passage_options']['review_candidates']
    assert 'draft' not in caught.value.diagnostic


def test_actual_director_assembles_editable_rough_cut_instead_of_only_publishing_a_shelf(semantic_project,monkeypatch):
    store,settings,pid,_calls,context=semantic_project
    canonical=copy.deepcopy(store.load(pid)['analysis']['transcript'])
    def stopped(_beats,current,*_args,**_kwargs):raise failure(current)
    monkeypatch.setattr(story,'hierarchical_story_edit',stopped)
    monkeypatch.setattr(director,'_plan_edit_with_cancel',lambda c,s,settings,b,**k:
        story.plan_edit(s,settings,b,cancel_check=c.checkpoint))
    result=director.analyze_project(context(),pid,store,settings,request())
    p=store.load(pid)
    # Director may refresh detection/provenance/quality annotations; original
    # ASR words, IDs and source clocks must remain byte-for-byte equivalent.
    original=lambda t:[{k:r[k] for k in ('id','start','end','text','words')} for r in t['segments']]
    assert original(p['analysis']['transcript'])==original(canonical)
    assert p['analysis']['engine']==story.EXTRACTIVE_ROUGH_CUT_ENGINE
    assert p['draft']['keep_ranges']==[{'start':0.,'end':58.}]
    assert p['draft']['generative_approved'] is False
    assert p['draft']['editorial_authority']==story.EXTRACTIVE_ROUGH_CUT_AUTHORITY
    assert p['draft']['status']=='requires_review'
    assert p['draft']['cuts'] and p['draft']['camera_plan']


def test_actual_director_keeps_prior_edit_when_no_candidate_satisfies_constraints(semantic_project,monkeypatch):
    store,settings,pid,_calls,context=semantic_project;before=store.load(pid)
    def stopped(_beats,current,*_args,**_kwargs):
        error=failure(current)
        for row in error.diagnostic['passage_options']['review_candidates']:
            row['playback_ranges'][0]['end']-=10
        raise error
    monkeypatch.setattr(story,'hierarchical_story_edit',stopped)
    monkeypatch.setattr(director,'_plan_edit_with_cancel',lambda c,s,settings,b,**k:
        story.plan_edit(s,settings,b,cancel_check=c.checkpoint))
    with pytest.raises(StoryPlanningError):director.analyze_project(context(),pid,store,settings,request())
    after=store.load(pid)
    assert after['draft']==before['draft'] and after['manual']==before['manual']


def test_source_change_during_recovery_cannot_commit_over_current_project(semantic_project,monkeypatch):
    store,settings,pid,_calls,context=semantic_project;before=store.load(pid)
    def stopped(_beats,current,*_args,**_kwargs):
        store.update(pid,lambda p:p['sources']['A'].update(generation='new-source-generation'))
        raise failure(current)
    monkeypatch.setattr(story,'hierarchical_story_edit',stopped)
    monkeypatch.setattr(director,'_plan_edit_with_cancel',lambda c,s,settings,b,**k:
        story.plan_edit(s,settings,b,cancel_check=c.checkpoint))
    with pytest.raises((StoryPlanningError,ValueError,RuntimeError)):
        director.analyze_project(context(),pid,store,settings,request())
    after=store.load(pid)
    assert after['draft']==before['draft'] and after['manual']==before['manual']
    assert after['sources']['A']['generation']=='new-source-generation'


def split_entry_source(language):
    # The whole canonical row is immutable, even with punctuation inside it.
    text = (['The opening is complete. Participation is not',
             'required for the rest of this explanation.'] if language == 'en' else
            ['זאת פתיחה שלמה. ההשתתפות אינה', 'נדרשת בהמשך ההסבר המקורי הזה.'])
    return [{'id':f'entry{i}','start':start,'end':end,'text':value,'words':[]}
            for i,(start,end,value) in enumerate([(0.,15.,text[0]),(15.25,55.,text[1])])]


def split_entry_failure(current):
    from cutroom.story_candidates import project_short_source_units, expose_complete_asr_entries
    parents=[{'id':'source-parent','start':current[0]['start'],'end':current[-1]['end'],
              'segment_ids':[r['id'] for r in current]}]
    units=expose_complete_asr_entries(project_short_source_units(parents,current),current)
    assert len(units)==2 and units[0]['entry_owner_id']==units[1]['entry_owner_id']
    option={'id':'automatic-native-entry','segment_ids':[r['id'] for r in current],
            'playback_ranges':[{k:r[k] for k in ('start','end')} for r in units]}
    return StoryPlanningError('Recorded failed model nomination.',{
        'reason':'semantic_candidates_rejected','outcome':'editorial_no_fit',
        'source_wide_no_fit_proven':False,'passage_options':{'source_segments':source_identity_rows(current),
            'candidate_inventory':units,'review_candidates':[option]}})


@pytest.mark.parametrize('language',['he','en'])
def test_actual_planner_preserves_native_entry_continuation_across_playback_gap(monkeypatch,language):
    rows=split_entry_source(language)
    brief=request(language,instruction=('Make one 45-60 second video.' if language=='en' else
                                        'צור סרטון אחד של 45-60 שניות.'),source_continuity='cuts_allowed')
    before=copy.deepcopy(rows)
    editorial,engine=planner(monkeypatch,rows,brief,split_entry_failure)
    decision=editorial['decision'];ranges=[{'start':0.,'end':15.},{'start':15.25,'end':55.}]
    proof=decision['extractive_requirements']['source_span_constraints']
    assert engine==story.EXTRACTIVE_ROUGH_CUT_ENGINE and proof['approved_ranges']==ranges
    assert proof['segment_ids']==['entry0','entry1'] and rows==before
    assert len({r['entry_owner_id'] for r in decision['story_ranges']})==1
    assert ('not' if language=='en' else 'אינה') in decision['summary']
    assert decision['generative_approved'] is False and decision['review_required'] is True
    validated=director._validate_extractive_selection(decision,editorial['segments'],55.,60.,fps=30,
        selection_policy={'preserve_source_continuity':False,'duration_mode':'target',
                          'duration_bounds':story.effective_duration_bounds(brief,55.)},keep_ranges=ranges)
    assert validated['reasons']==[]


@pytest.mark.parametrize('language',['he','en'])
@pytest.mark.parametrize('fault',['missing_inventory','missing_continuation_owner','wrong_owner',
    'stale_text','stale_time','stale_binding','ambiguous_unit','unsupported_policy','no_cuts','missing_speech'])
def test_native_entry_recovery_never_invents_or_unbinds_a_continuation(language,fault):
    rows=split_entry_source(language)
    brief=request(language,instruction=('Make one 45-60 second video.' if language=='en' else
                                        'צור סרטון אחד של 45-60 שניות.'),source_continuity='cuts_allowed')
    error=split_entry_failure(rows);receipt=error.diagnostic['passage_options'];units=receipt['candidate_inventory']
    if fault=='missing_inventory':receipt.pop('candidate_inventory')
    if fault=='missing_continuation_owner':units[1].pop('entry_owner_id')
    if fault=='wrong_owner':units[1]['entry_owner_id']='another-source-unit'
    if fault=='stale_text':units[0]['text']+=' Changed.'
    if fault=='stale_time':units[0]['end']-=.01
    if fault=='stale_binding':units[0]['candidate_source_fingerprint']='stale-source'
    if fault=='ambiguous_unit':units.append(copy.deepcopy(units[0]))
    if fault=='unsupported_policy':units[0]['entry_policy']='unknown-policy'
    if fault=='no_cuts':brief=request(language)
    if fault=='missing_speech':receipt['review_candidates'][0]['segment_ids'].pop()
    before=copy.deepcopy((rows,brief,error.diagnostic))
    assert story._early_extractive_rough_cut(rows,enrich_brief_with_style(brief),error) is None
    assert (rows,brief,error.diagnostic)==before
