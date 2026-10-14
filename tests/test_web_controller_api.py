"""API/CLI integration checks using temporary media and an identity engine, no GPU."""
import io
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
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
    return TestClient(api.app)

def test_relative_upload_and_exact_preflight(client, tmp_path):
    response = client.post('/upload/photos?batch_id=check-1',
        files=[('files', ('x.webp', b'photo', 'image/webp'))], data={'relative_paths': 'nested/x.webp'})
    assert response.status_code == 200
    upload = response.json()
    assert Path(upload['input_dir'], 'nested/x.webp').read_bytes() == b'photo'
    out = tmp_path / 'drive_root' / 'custom'
    (out / 'nested').mkdir(parents=True)
    (out / 'nested/x_face_swapped.webp').write_bytes(b'output')
    r = client.post('/outputs/photos/preflight', json={'output_dir': str(out), 'relative_paths':['nested/x.webp','other/x.webp']})
    assert r.json() == {'processed': ['nested/x.webp']}
    assert client.get('/health').json()['web_capabilities']['relative_uploads']
    for unsafe in ('../outside.webp','/outside.webp','a/../outside.webp','C:/outside.webp'):
        r=client.post('/upload/photos?batch_id=bad',files=[('files',('x.webp',b'x'))],data={'relative_paths':unsafe})
        assert r.status_code == 400
    # Existing Windows uploads remain flat and require no new form fields.
    r=client.post('/upload/photos?batch_id=legacy', files=[('files', ('x.webp', b'legacy'))])
    assert r.status_code == 200
    assert Path(r.json()['input_dir'], 'x.webp').read_bytes() == b'legacy'

def test_video_preflight_matches_mp4_output_and_range(client,tmp_path,monkeypatch):
    out=tmp_path/'drive_root'/'video-out';out.mkdir(parents=True);(out/'clip_face_swapped.mp4').write_bytes(b'v')
    assert client.post('/outputs/videos/preflight',json={'output_dir':str(out),'relative_paths':['clip.MOV']}).json()['processed']==['clip.MOV']
    captured=[]
    monkeypatch.setattr(api,'start_job',lambda kind,argv: captured.append(argv) or SimpleNamespace(job_id='id',status='queued'))
    assert client.post('/jobs/videos',json={'start_pct':20,'end_pct':60}).status_code==200
    argv=captured[0];assert argv[argv.index('--start-pct')+1]=='20.0';assert argv[argv.index('--end-pct')+1]=='60.0'
    assert client.post('/jobs/videos',json={'start_pct':60,'end_pct':20}).status_code==400

def test_photo_options_reach_cli_and_lossy_output_encoding(client,tmp_path,monkeypatch):
    captured=[]
    monkeypatch.setattr(api,'start_job',lambda kind,argv: captured.append(argv) or SimpleNamespace(job_id='id',status='queued'))
    payload={'quality':73,'detector_size':352,'face_model_pack':'buffalo_s','swapper_precision':'fp16','output_max_width':16}
    assert client.post('/jobs/photos',json=payload).status_code==200
    args=batch.build_parser().parse_args(captured[0]);assert (args.image_quality,args.detector_size,args.face_model_pack,args.swapper_precision)==(73,352,'buffalo_s','fp16')
    inp=tmp_path/'in';inp.mkdir();source=inp/'x.webp';cv2.imwrite(str(source),np.full((24,32,3),100,np.uint8));out=tmp_path/'out';configs=[]
    class Identity:
        def __init__(self,config): configs.append(config)
        def reset_video_state(self): pass
        def process(self,frame,relative): return frame
    monkeypatch.setattr(batch,'ModernEngine',Identity)
    args.input_dir=str(inp);args.output_dir=str(out);args.source_face=None
    calls=[];original=cv2.imwrite
    def write(path,image,params):
        calls.append(params)
        return original(path,image,params)
    monkeypatch.setattr(cv2,'imwrite',write)
    assert batch.process_photos(args)==0
    assert (configs[0].face_model_pack,configs[0].swapper_precision,configs[0].detector_size)==('buffalo_s','fp16',352)
    assert calls==[[cv2.IMWRITE_WEBP_QUALITY,73]]
    assert cv2.imread(str(out/'x_face_swapped.webp')).shape[:2]==(12,16)

def test_output_webp_listing_download_and_cancel(client,monkeypatch):
    api.ensure_local_layout();(api.LOCAL_OUTPUT_PHOTOS_DIR/'x.webp').write_bytes(b'webp')
    files=client.get('/outputs/photos').json()['files'];assert files[0]['download_path'].endswith('x.webp')
    response=client.get(files[0]['download_path']);assert response.content==b'webp';assert response.headers['content-type']=='image/webp'
    job=api.JobState(job_id='cancel-me',kind='videos');monkeypatch.setitem(api.JOBS,job.job_id,job)
    assert client.post('/jobs/cancel',json={'job_id':job.job_id}).json()['cancel_requested']
    assert job.cancel_event.is_set()


def test_remote_preflight_counts_all_processed_without_starting_job(client,tmp_path):
    inp=tmp_path/'drive_root'/'remote-in';out=tmp_path/'drive_root'/'remote-out'
    (inp/'nested').mkdir(parents=True);(out/'nested').mkdir(parents=True)
    (inp/'nested/x.webp').write_bytes(b'input');(out/'nested/x_face_swapped.webp').write_bytes(b'output')
    response=client.post('/outputs/photos/preflight',json={'input_dir':str(inp),'output_dir':str(out),'recursive':True})
    assert response.json()=={'processed':['nested/x.webp'],'total':1,'remaining':0}


def test_preflight_rejects_dirs_outside_layout_roots(client, tmp_path):
    for body in ({'output_dir': '/etc'}, {'output_dir': str(tmp_path / 'drive_root'), 'input_dir': '/root'},
                 {'output_dir': str(tmp_path / 'drive_root' / '..' / 'elsewhere')}):
        assert client.post('/outputs/photos/preflight', json=body).status_code == 400
