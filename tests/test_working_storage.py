"""Small synthetic files and capacity mocks: no transcoding or huge allocation."""
from pathlib import Path
from types import SimpleNamespace
import copy
import pytest

import server
from cutroom import working_storage as budget
from cutroom import render
from cutroom.upload_storage import UploadStorage
from test_asset_preparation_cache import setup, prepare, asset, generations, context, ASSET

GiB=1024**3


def test_same_volume_combines_work_and_one_reserve_without_creating_directories(tmp_path,monkeypatch):
    monkeypatch.setattr(budget,'filesystem_id',lambda path:'same')
    monkeypatch.setattr(budget.shutil,'disk_usage',lambda path:SimpleNamespace(free=4*GiB))
    p=budget.require_working_space([('preview',tmp_path/'cache',GiB),('metadata',tmp_path/'project',GiB)],operation='prepare')
    row=p['filesystems'][0]
    assert row['required_bytes']==2*GiB and row['reserve_bytes']==GiB
    assert row['locations']==[str((tmp_path/'cache').resolve()),str((tmp_path/'project').resolve())]
    assert list(tmp_path.iterdir())==[]


def test_insufficient_temp_or_destination_is_not_hidden_by_another_drive(tmp_path,monkeypatch):
    monkeypatch.setattr(budget,'filesystem_id',lambda p:str(p))
    a=tmp_path/'project';b=tmp_path/'temp';a.mkdir();b.mkdir()
    monkeypatch.setattr(budget.shutil,'disk_usage',lambda p:SimpleNamespace(free=20*GiB if Path(p)==a else GiB))
    with pytest.raises(budget.WorkingStorageError) as e:
        budget.require_working_space([('project',a,GiB),('temp',b,GiB)],operation='processing')
    assert str(b) in str(e.value) and 'original is preserved' in str(e.value)
    assert e.value.storage_plan['filesystems'][0]['disk_free_bytes']==GiB


def test_duration_and_preview_dimensions_increase_conservative_estimate_without_buffers():
    meta=dict(kind='video',duration=3600.,width=1920,height=1080)
    size=budget.preparation_bytes(meta,transcode=True)
    assert 6*GiB<size<8*GiB  # 16 Mbps is decimal; do not confuse GB and GiB.
    assert budget.preparation_bytes({**meta,'duration':7200.},transcode=True)>size
    assert budget.preparation_bytes(meta,transcode=True,height=1080)>size
    assert budget.preparation_bytes(meta,transcode=False)==16*1024**2


def test_asset_low_space_blocks_before_stage_or_transcode_and_preserves_original(setup,monkeypatch):
    original=setup[4].read_bytes()
    monkeypatch.setattr(budget.shutil,'disk_usage',lambda p:SimpleNamespace(free=100))
    with pytest.raises(budget.WorkingStorageError) as e:prepare(setup)
    assert str(setup[3].resolve()) in str(e.value) and 'transfer may be complete' in str(e.value)
    assert setup[-1]['encode']==[] and generations(setup)==[]
    assert setup[4].read_bytes()==original and asset(setup)['status']=='failed'


def test_asset_success_uses_existing_atomic_cache_without_recopying_original(setup,monkeypatch):
    monkeypatch.setattr(budget.shutil,'disk_usage',lambda p:SimpleNamespace(free=20*GiB))
    assert prepare(setup)['preparation_reused'] is False
    original=setup[4].read_bytes();ready=copy.deepcopy(asset(setup))
    assert prepare(setup)['preparation_reused'] is True
    assert setup[4].read_bytes()==original and asset(setup)['preview_path']==ready['preview_path']


def test_source_capacity_gate_precedes_vision_audio_or_proxy(setup,monkeypatch):
    settings,store,pid,folder,original,calls=setup
    store.update(pid,lambda p:p['sources'].update(A={'generation':'g','duration':3600.,'browser_ready':False,'relative_path':original.relative_to(store.project_dir(pid)).as_posix(),'width':1920,'height':1080}))
    monkeypatch.setattr(budget.shutil,'disk_usage',lambda p:SimpleNamespace(free=100))
    for name in ['analyze_faces_and_embedded_camera','analyze_audio','create_proxy']:
        monkeypatch.setattr(server,name,lambda *a,**k:pytest.fail('Expensive stage started'))
    with pytest.raises(budget.WorkingStorageError):server._prepare_source_impl(context(),pid,'A','g',store,settings)
    assert original.read_bytes()==b'SYNTHETIC-ORIGINAL'


def test_import_receipt_names_real_data_and_temp_paths_and_transfer_scope(tmp_path,monkeypatch):
    monkeypatch.setattr(budget.shutil,'disk_usage',lambda p:SimpleNamespace(free=20*GiB))
    storage=UploadStorage(tmp_path)
    try:
        facts=storage.plan(100,data_path=tmp_path/'different-projects')
        assert facts['storage_plan']['scope']=='transfer_only_processing_checked_after_metadata'
        paths=[p for row in facts['storage_plan']['filesystems'] for p in row['locations']]
        assert str((tmp_path/'different-projects').resolve()) in paths
        assert str(storage.temp_dir.resolve()) in paths
    finally:storage.close()


def test_render_failure_names_path_capacity_and_actionable_recovery(tmp_path):
    error=render.InsufficientStorageError(required_bytes=4*GiB,free_bytes=GiB,location=tmp_path)
    assert str(tmp_path) in str(error) and '4.00 GiB' in str(error) and '1.00 GiB' in str(error)
    assert 'originals and edit are preserved' in str(error)
