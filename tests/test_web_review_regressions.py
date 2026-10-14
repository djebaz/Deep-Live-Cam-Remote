"""Review regressions at API and engine setup seams; no GPU initialization."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
import colab_api as api
import colab_batch as batch

@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in ('LOCAL_ROOT', 'LOCAL_SOURCE_DIR', 'LOCAL_PHOTOS_DIR', 'LOCAL_VIDEOS_DIR',
                 'LOCAL_OUTPUT_PHOTOS_DIR', 'LOCAL_OUTPUT_VIDEOS_DIR', 'DRIVE_ROOT',
                 'SOURCE_DIR', 'PHOTOS_DIR', 'VIDEOS_DIR', 'OUTPUT_PHOTOS_DIR', 'OUTPUT_VIDEOS_DIR'):
        monkeypatch.setattr(api, name, tmp_path / name.lower())
    # Match the real nesting: local input folders sit under LOCAL_ROOT.
    for name, folder in [('LOCAL_SOURCE_DIR', 'source'), ('LOCAL_PHOTOS_DIR', 'photos'), ('LOCAL_VIDEOS_DIR', 'videos')]:
        monkeypatch.setattr(api, name, api.LOCAL_ROOT / folder)
    return TestClient(api.app)

def test_engine_setup_resets_default_detector_after_another_job(monkeypatch,tmp_path):
    import modules.processors.frame as frame
    sizes=[]
    monkeypatch.setitem(sys.modules,'onnxruntime',SimpleNamespace(get_available_providers=lambda:['CPUExecutionProvider']))
    monkeypatch.setitem(sys.modules,'modules.face_analyser',SimpleNamespace(
        get_many_faces=lambda *_:None,get_one_face=lambda *_:None,
        set_face_analyser_model_pack=lambda *_:None,set_face_analyser_detector_size=sizes.append))
    # Deliberately stop just after engine selection, before loading any model.
    monkeypatch.setattr(frame,'face_swapper',SimpleNamespace(set_face_swapper_precision=lambda *_:None,pre_check=lambda:False),raising=False)
    for size in (1280,None):
        with pytest.raises(RuntimeError,match='provision'):
            batch.ModernEngine(batch.ProcessConfig(tmp_path,tmp_path,None,None,detector_size=size))
    assert sizes==[1280,None]  # The real setter maps None to the baseline 640.

def test_preflight_denies_unscoped_paths_uniformly(client,tmp_path):
    outside=tmp_path/'private';outside.mkdir();(outside/'secret.mp4').write_bytes(b'private')
    for probe in (outside,tmp_path/'private-missing'):
        r=client.post('/outputs/videos/preflight',json={'input_dir':str(probe),'output_dir':str(api.LOCAL_OUTPUT_VIDEOS_DIR)})
        assert r.status_code==400
        assert r.json()=={'detail':'input_dir is outside the allowed folders'}
        r=client.post('/outputs/videos/preflight',json={'output_dir':str(probe),'relative_paths':['secret.mp4']})
        assert r.status_code==400
        assert r.json()=={'detail':'output_dir is outside the allowed folders'}

def test_preflight_preserves_existing_posix_filename_characters(client):
    api.ensure_local_layout()
    names=['clip 12:30.mp4','clip\\one.mp4']
    for name in names:
        (api.LOCAL_VIDEOS_DIR/name).write_bytes(b'input')
        (api.LOCAL_OUTPUT_VIDEOS_DIR/f'{Path(name).stem}_face_swapped.mp4').write_bytes(b'output')
    r=client.post('/outputs/videos/preflight',json={'input_dir':str(api.LOCAL_VIDEOS_DIR),'output_dir':str(api.LOCAL_OUTPUT_VIDEOS_DIR)})
    assert r.status_code==200
    assert set(r.json()['processed'])==set(names)

def test_video_model_options_are_forwarded_and_validated(client,monkeypatch):
    captured=[]
    monkeypatch.setattr(api,'start_job',lambda kind,argv: captured.append(argv) or SimpleNamespace(job_id='id',status='queued'))
    r=client.post('/jobs/videos',json={'detector_size':1280,'face_model_pack':'buffalo_s','swapper_precision':'fp16'})
    assert r.status_code==200
    args=batch.build_parser().parse_args(captured[0])
    assert (args.detector_size,args.face_model_pack,args.swapper_precision)==(1280,'buffalo_s','fp16')
    for patch in ({'detector_size':333},{'face_model_pack':'invalid'},{'swapper_precision':'invalid'}):
        assert client.post('/jobs/videos',json=patch).status_code==400

def test_segment_preflight_matches_cli_naming_and_does_not_skip_full_video(client):
    api.ensure_local_layout()
    out=api.LOCAL_OUTPUT_VIDEOS_DIR
    (out/'clip_face_swapped_ss2.5_dur3.mp4').write_bytes(b'output')
    payload={'output_dir':str(out),'relative_paths':['clip.MOV'],'ss':2.5,'duration':3}
    assert client.post('/outputs/videos/preflight',json=payload).json()['processed']==['clip.MOV']
    payload.pop('ss');payload.pop('duration')
    assert client.post('/outputs/videos/preflight',json=payload).json()['processed']==[]

def test_cleanup_deletes_only_unsubmitted_isolated_batch(client,monkeypatch,tmp_path):
    api.ensure_local_layout();batch_id='cancelled-selection'
    root=api.LOCAL_PHOTOS_DIR/'batches'/batch_id
    (root/'nested').mkdir(parents=True);(root/'nested/x.webp').write_bytes(b'partial')
    r=client.delete(f'/upload/photos/batches/{batch_id}')
    assert r.status_code==200
    assert not root.exists()
    assert client.delete(f'/upload/photos/batches/{batch_id}').status_code==200
    root.mkdir();(root/'x.webp').write_bytes(b'active')
    monkeypatch.setitem(api.JOBS,'active-upload-job',SimpleNamespace(status='running',input_dir=str(root)))
    assert client.delete(f'/upload/photos/batches/{batch_id}').status_code==409
    assert (root/'x.webp').exists()
    outside=tmp_path/'outside';outside.mkdir();(outside/'keep.webp').write_bytes(b'private')
    (api.LOCAL_PHOTOS_DIR/'batches'/'link').symlink_to(outside,target_is_directory=True)
    assert client.delete('/upload/photos/batches/link').status_code==400
    assert (outside/'keep.webp').exists()


def test_cli_segment_output_and_video_model_config_reach_processor(tmp_path, monkeypatch):
    inp = tmp_path / 'video-in'
    (inp / 'nested').mkdir(parents=True)
    (inp / 'nested/clip.MOV').write_bytes(b'video fixture')
    out = tmp_path / 'video-out'
    args = batch.build_parser().parse_args([
        'process', '--input-dir', str(inp), '--output-dir', str(out),
        '--ss', '2.5', '--duration', '3', '--detector-size', '1280',
        '--face-model-pack', 'buffalo_s', '--swapper-precision', 'fp16'])
    configs = []
    outputs = []

    class Identity:
        def __init__(self, config):
            configs.append(config)

    def process_one(_video, output, _relative, _config, _engine, _cancel):
        outputs.append(output)
        output.parent.mkdir(parents=True)
        output.write_bytes(b'processed fixture')
        return {'size_mb': 0.0}

    monkeypatch.setattr(batch, 'ModernEngine', Identity)
    monkeypatch.setattr(batch, 'process_one', process_one)
    assert batch.process_batch(args) == 0
    assert outputs == [out / 'nested/clip_face_swapped_ss2.5_dur3.mp4']
    assert (configs[0].detector_size, configs[0].face_model_pack,
            configs[0].swapper_precision) == (1280, 'buffalo_s', 'fp16')


def test_video_job_omits_unset_detector_size_but_photo_keeps_it(client,monkeypatch):
    captured=[]
    monkeypatch.setattr(api,'start_job',lambda kind,argv: captured.append(argv) or SimpleNamespace(job_id='id',status='queued'))
    assert client.post('/jobs/videos',json={}).status_code==200
    assert client.post('/jobs/photos',json={}).status_code==200
    assert '--detector-size' not in captured[0]
    assert batch.build_parser().parse_args(captured[0]).detector_size is None
    assert captured[1][captured[1].index('--detector-size')+1]=='640'


def test_upload_locks_are_per_batch_and_released():
    import asyncio
    async def run():
        async with api.upload_lock(api.LOCAL_PHOTOS_DIR, 'a'):
            async with asyncio.timeout(1):
                async with api.upload_lock(api.LOCAL_PHOTOS_DIR, 'b'):
                    pass
            assert len(api.UPLOAD_LOCKS) == 1
    asyncio.run(run())
    assert api.UPLOAD_LOCKS == {}


def test_cleanup_blocks_job_registration_until_delete_finishes(client, monkeypatch):
    api.ensure_local_layout()
    root = api.LOCAL_PHOTOS_DIR / 'batches' / 'racy'
    root.mkdir(parents=True)
    (root / 'x.webp').write_bytes(b'x')
    assert not api.JOBS_LOCK.locked()
    seen = []
    real = api.shutil.rmtree
    monkeypatch.setattr(api.shutil, 'rmtree', lambda p: seen.append(api.JOBS_LOCK.locked()) or real(p))
    assert client.delete('/upload/photos/batches/racy').status_code == 200
    assert seen == [True]
