"""Lexical role guesses must not become authority in exact-source selection."""
from __future__ import annotations

import copy
import json

import pytest

from cutroom import intelligence
from cutroom.edit_styles import enrich_brief_with_style


@pytest.mark.parametrize('language,texts,instruction', [
    ('en', ['I missed my bus because I left late.',
            'The next day I left ten minutes earlier and arrived on time.'],
     'Choose one coherent self-contained short of about20 seconds. Keep complete sentences and meaning.'),
    ('he', ['פספסתי את האוטובוס כי יצאתי מאוחר.',
            'למחרת יצאתי עשר דקות מוקדם יותר והגעתי בזמן.'],
     'בחר קטע אחד ברור ועצמאי באורך של כעשרים שניות. שמור על משפטים שלמים ועל המשמעות.')])
@pytest.mark.parametrize('purpose', ['self_contained_passage', 'result'])
def test_precision_uses_source_and_plan_independently_of_lexical_role_hint(language, texts, instruction, purpose):
    segments = intelligence.enrich_segments([
        {'id': 's1', 'start': 0., 'end': 10., 'text': texts[0]},
        {'id': 's2', 'start': 10., 'end': 20., 'text': texts[1]},
    ], language)
    beats = intelligence.build_story_beats(segments, language, target_seconds=20)
    assert len(beats) == 2
    chapters = intelligence.build_story_chapters(beats)
    brief = enrich_brief_with_style({'instruction': instruction, 'goal': 'short',
                                    'target_duration': 20, 'duration_mode': 'target'})
    plan = {'slots': [{'purpose': purpose, 'chapter_ids': [chapters[0]['id']],
                      'required_context_chapter_ids': [], 'desired_seconds': 20}]}
    def build(rows):
        return intelligence._precision_story_payload(rows, segments, chapters, [], {}, plan,
                                                      brief, 'fixture', 'balanced', 20)
    baseline, baseline_catalog = build(beats)
    hinted = copy.deepcopy(beats)
    hinted[-1]['role_hint'] = 'hook'
    changed, changed_catalog = build(hinted)
    # Removing the heuristic must leave authoritative source, exact schema,
    # instruction, plan and duration costs identical to the neutral request.
    assert changed == baseline
    assert changed_catalog == baseline_catalog
    content = json.loads(changed['messages'][-1]['content'])
    assert content['plan'] == plan
    assert content['brief']['instruction'] == instruction
    assert all('role' not in row and 'role_hint' not in row for row in content['candidate_beats'])
    assert [row['text'] for row in content['source_utterances']] == texts
    choices = list(intelligence._story_evidence_choice_catalog(changed_catalog))
    positive = {'verdict': 'fit', 'role_selections': {purpose: {
        'primary_anchor_choice': choices[-1], 'additional_primary_evidence_choices': [choices[0]],
        'context_evidence_choices_by_chapter': {}}}, 'highlight_beat_ids': [],
        'title': 'Fixture', 'summary': 'Unverified interpretation'}
    clean = intelligence._decode_precision_story_selection(positive, changed_catalog, hinted,
        segments, chapters, plan, brief)
    # The source producer owns stable IDs; the decoder must preserve their
    # identity and chronology rather than invent legacy sequential labels.
    assert clean['keep_beat_ids'] == [beat['id'] for beat in beats]
    selected = {beat['id']: beat for beat in beats}
    assert [(selected[key]['start'], selected[key]['end'])
            for key in clean['keep_beat_ids']] == [(0., 10.), (10., 20.)]
    assert clean['semantic_mapping_verified'] is False
    # Exact copying and latest anchor protections remain mandatory.
    forged = copy.deepcopy(positive)
    forged['role_selections'][purpose]['primary_anchor_choice'] = choices[-1].replace(texts[-1], 'invented quotation')
    with pytest.raises(intelligence.StoryPlanningError):
        intelligence._decode_precision_story_selection(forged, changed_catalog, hinted,
            segments, chapters, plan, brief)
    early = copy.deepcopy(positive)
    early['role_selections'][purpose]['primary_anchor_choice'] = choices[0]
    early['role_selections'][purpose]['additional_primary_evidence_choices'] = [choices[-1]]
    with pytest.raises(intelligence.StoryPlanningError):
        intelligence._decode_precision_story_selection(early, changed_catalog, hinted,
            segments, chapters, plan, brief)
