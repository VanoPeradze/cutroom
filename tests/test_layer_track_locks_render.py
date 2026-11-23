"""Protection metadata never changes production picture/sound or rewinds via Undo."""
import copy
import pytest
from cutroom.editing import apply_manual_edit
from cutroom.projects import ProjectStore
from cutroom.render import _render_input_fingerprint
from cutroom.render_inventory import compile_render_inputs
from cutroom.composition import CHROMA_KEY_DEFAULTS
from test_media_render import media
from test_layer_tracks_render import decoded
from test_track_destination_render import prepared


def toggle(p,track,locked=True):
    apply_manual_edit(p,{'action':'layer_track_lock','track_id':track,'locked':locked})


def test_production_lock_parity_duplicate_and_current_protection_history(media,tmp_path):
    p,store,settings,encode,hashes=prepared(media,tmp_path)
    p['manual']['media_clips'][2]['motion']='pan'
    apply_manual_edit(p,{'action':'media_duplicate','clip_id':p['manual']['media_clips'][2]['id'],'start':0.})
    apply_manual_edit(p,{'action':'media_set_enabled','clip_id':p['manual']['media_clips'][-1]['id'],'enabled':False})
    before=copy.deepcopy(p);history=copy.deepcopy(p['manual'].get('_history'))
    original=encode(p,'track-locks-legacy')
    video=p['manual']['media_clips'][0];lane=video['track_id']
    identity=_render_input_fingerprint(p);inventory=compile_render_inputs(p)
    for track in list(p['manual']['layer_tracks']['tracks']):toggle(p,track['id'])
    assert p['manual']['layer_tracks']['version']==2
    assert p['manual'].get('_history')==history
    assert _render_input_fingerprint(p)==identity
    inventory.validate(p)
    protected=encode(p,'track-locks-all-protected')
    assert decoded(media[1],protected)==decoded(media[1],original)
    assert decoded(media[1],protected,False)==decoded(media[1],original,False)
    reopened=ProjectStore(settings).load(p['id'])
    assert all(t['locked'] for t in reopened['manual']['layer_tracks']['tracks'])
    # Reading a protected original is valid; copy is automatically put on a new unlocked lane.
    apply_manual_edit(reopened,{'action':'media_duplicate','clip_id':video['id'],'start':0.})
    copy_clip=reopened['manual']['media_clips'][-1]
    assert copy_clip['track_id']!=lane
    destination=next(t for t in reopened['manual']['layer_tracks']['tracks'] if t['id']==copy_clip['track_id'])
    assert destination['locked'] is False
    assert next(c for c in reopened['manual']['media_clips'] if c['id']==video['id'])==video
    copied=encode(reopened,'track-locks-allowed-copy')
    assert decoded(media[1],copied)!=decoded(media[1],original) or decoded(media[1],copied,False)!=decoded(media[1],original,False)
    apply_manual_edit(reopened,{'action':'undo'})
    restored=encode(reopened,'track-locks-copy-undone')
    assert decoded(media[1],restored)==decoded(media[1],original)
    assert decoded(media[1],restored,False)==decoded(media[1],original,False)
    assert all(t['locked'] for t in reopened['manual']['layer_tracks']['tracks'])
    # Lock after an edit cannot be silently removed by undoing that content edit.
    text=reopened['manual']['text_clips'][0];text_lane=text['track_id']
    toggle(reopened,text_lane,False)
    apply_manual_edit(reopened,{'action':'text_update','clip_id':text['id'],'text':'Changed while unlocked'})
    toggle(reopened,text_lane,True);saved=copy.deepcopy(reopened)
    with pytest.raises(ValueError,match='locked'):apply_manual_edit(reopened,{'action':'undo'})
    assert reopened==saved
    toggle(reopened,text_lane,False)
    apply_manual_edit(reopened,{'action':'undo'})
    assert next(t for t in reopened['manual']['layer_tracks']['tracks'] if t['id']==lane)['locked']
    assert not next(t for t in reopened['manual']['layer_tracks']['tracks'] if t['id']==text_lane)['locked']
    assert reopened['manual']['text_clips']==before['manual']['text_clips']
    hashes()


@pytest.mark.parametrize('action',['media_update','media_remove','sequence_ripple_delete','sequence_insert_all','set_chroma_key'])
def test_locked_production_fixture_refusal_preserves_saved_bytes(media,tmp_path,action):
    p,store,settings,encode,hashes=prepared(media,tmp_path)
    row=p['manual']['media_clips'][0];toggle(p,row['track_id']);store.save(p)
    payload={'action':action}
    if action=='media_update':payload.update(clip_id=row['id'],volume_db=-30)
    elif action=='media_remove':payload.update(clip_id=row['id'])
    if action=='sequence_ripple_delete':payload.update(start=.5,end=1.)
    elif action=='sequence_insert_all':payload.update(slot='A',start=1.5,source_start=0.,source_end=1.)
    elif action=='set_chroma_key':payload.update(slot=row['asset_id'],**CHROMA_KEY_DEFAULTS);payload['enabled']=True
    saved=store.state_path(p['id']).read_bytes()
    with pytest.raises(ValueError,match="locked"):store.update(p['id'],lambda current:apply_manual_edit(current,payload),expected_revision=store.load(p['id'])['revision'])
    assert store.state_path(p['id']).read_bytes()==saved
    hashes()
