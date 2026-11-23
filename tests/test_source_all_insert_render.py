"""Primary source all-layer Insert, independently constructed output reference."""
import copy
import uuid
import pytest
from cutroom.editing import apply_manual_edit
from cutroom.projects import ProjectStore
from cutroom.sequence import materialize_sequence
from test_media_render import media, samples, tone_level, pixel
from test_layer_tracks_render import decoded
from test_track_destination_render import prepared


def reference_insert(p,slot,at,source_start,length):
    """Independent slice/shift of saved rows, never calls an insertion helper."""
    p=copy.deepcopy(p);manual=p['manual'];old=manual['sequence']['duration']
    def cut(rows,kind):
        result=[]
        for row in rows:
            a,b=row['start'],row['end']
            if b<=at:result.append(copy.deepcopy(row));continue
            if a>=at:
                result.append({**row,'start':a+length,'end':b+length});continue
            left={**row,'end':at};right={**row,'start':at+length,'end':b+length}
            if 'id' in row:right['id']=('text_' if kind=='text' else 'media_' if kind=='media' else 'B:' if kind=='B' else 'A:')+uuid.uuid4().hex
            offset=at-a
            if kind in ('A','B'):
                right['source_start']=row['source_start']+offset
                if 'video_source_start' in row:right['video_source_start']=row['video_source_start']+offset*row.get('video_speed',1)
            elif kind=='media':
                asset=p['assets'][row['asset_id']]
                if asset['kind']!='image':right['source_start']=row['source_start']+offset
                if asset['kind']=='video':right['video_source_start']=row.get('video_source_start',row['source_start'])+offset*row.get('speed',1)
                left['fade_out']=0.;right['fade_in']=0.
            result.extend([left,right])
        return result
    for source in ('A','B'):
        rows=cut(manual['source_tracks'][source],source)
        if source==slot:rows.append({'id':source+':reference','start':at,'end':at+length,'source_start':source_start})
        manual['source_tracks'][source]=sorted(rows,key=lambda r:r['start'])
    plan=cut(manual['sequence']['camera_plan'],'camera')
    plan.append({'start':at,'end':at+length,'camera':slot})
    manual['sequence']['camera_plan']=sorted(plan,key=lambda r:r['start'])
    manual['sequence']['duration']=old+length
    for key,kind in [('media_clips','media'),('text_clips','text')]:manual[key]=cut(manual[key],kind)
    return p


def assembled(media,tmp_path,audio_slot):
    p,store,settings,encode,hashes_ok=prepared(media,tmp_path)
    # Distinct source gaps/order already in fixture. Explicit sequence is authoritative.
    p,_=materialize_sequence(p)
    p['manual']['source_mixer']['audio_slot']=audio_slot
    p['settings']['audio_source']=audio_slot
    p['analysis'].update(audio_source=audio_slot,audio_timeline_offset=0.)
    image=p['manual']['media_clips'][2]
    apply_manual_edit(p,{'action':'media_add','asset_id':image['asset_id'],'start':2.,'end':3.,
        'x':.7,'y':.65,'w':.2,'h':.3,'motion':'pan','fade_in':.1,'fade_out':.1})
    apply_manual_edit(p,{'action':'media_add','asset_id':image['asset_id'],'start':0.,'end':3.,'enabled':False})
    p['manual']['media_clips'][0].update(fade_in=.1,fade_out=.2)
    store.save(p);p=ProjectStore(settings).load(p['id'])
    return p,store,settings,encode,hashes_ok


@pytest.mark.parametrize('audio_slot',['A','B'])
def test_real_primary_insert_all_matches_independent_mixed_reference(media,tmp_path,audio_slot):
    p,store,settings,encode,hashes_ok=assembled(media,tmp_path,audio_slot)
    baseline=copy.deepcopy(p);reference=reference_insert(p,'B',1.5,1.,1.)
    expected=encode(reference,'source-all-reference-'+audio_slot)
    actual=copy.deepcopy(p)
    apply_manual_edit(actual,{'action':'sequence_insert_all','slot':'B','start':1.5,'source_start':1.,'source_end':2.})
    assert actual['manual']['source_mixer']==baseline['manual']['source_mixer']
    assert actual['manual']['layer_tracks']==baseline['manual']['layer_tracks']
    assert actual['manual']['sequence']['duration']==4.
    slow=baseline['manual']['media_clips'][0]
    right=next(c for c in actual['manual']['media_clips'] if c['asset_id']==slow['asset_id'] and c['start']==2.5)
    assert right['track_id']==slow['track_id'] and right['source_start']==1.5 and right['video_source_start']==1.
    out=encode(actual,'source-all-actual-'+audio_slot)
    assert decoded(media[1],out)==decoded(media[1],expected)
    assert decoded(media[1],out,False)==decoded(media[1],expected,False)
    red,green,blue=pixel(media[1],out,2.,5,5)
    assert red>200 and green>200 and blue<50  # Selected B yellow, no old overlay in opened time.
    sound=samples(media[1],out)
    if audio_slot=='B':assert tone_level(sound,2.,660)>.02
    else:assert tone_level(sound,2.,660)<.001 and tone_level(sound,2.,440)<.001
    # Crossing slow video and audio return after gap with their independent clocks.
    assert pixel(media[1],out,2.8,5,5)[1]>200
    assert tone_level(sound,2.8,440)>.015
    reopened=ProjectStore(settings).load(p['id'])
    assert reopened['manual']['sequence']==actual['manual']['sequence']
    assert reopened['manual']['media_clips']==actual['manual']['media_clips']
    apply_manual_edit(reopened,{'action':'undo'})
    for key in ('sequence','source_tracks','media_clips','text_clips','layer_tracks','source_mixer'):
        assert reopened['manual'][key]==baseline['manual'][key]
    original=encode(baseline,'source-all-baseline-'+audio_slot)
    undone=encode(reopened,'source-all-undone-'+audio_slot)
    assert decoded(media[1],original)==decoded(media[1],undone)
    assert decoded(media[1],original,False)==decoded(media[1],undone,False)
    hashes_ok()


@pytest.mark.parametrize('fault',['motion','fade'])
def test_primary_insert_all_refuses_phase_loss_without_mutation(media,tmp_path,fault):
    p,store,settings,encode,hashes_ok=assembled(media,tmp_path,'A')
    row=p['manual']['media_clips'][0]
    row.update(**({'motion':'pan'} if fault=='motion' else {'fade_in':2.}))
    before=copy.deepcopy(p)
    with pytest.raises(ValueError,match='animated|fade'):
        apply_manual_edit(p,{'action':'sequence_insert_all','slot':'B','start':1.5,'source_start':1.,'source_end':2.})
    assert p==before
    hashes_ok()
