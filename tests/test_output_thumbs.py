"""Cached thumbnails/previews for the web Outputs library, and the listing cache."""
import json
import os

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

import colab_api as api

NAMES = ('LOCAL_ROOT', 'LOCAL_SOURCE_DIR', 'LOCAL_PHOTOS_DIR', 'LOCAL_VIDEOS_DIR',
         'LOCAL_OUTPUT_PHOTOS_DIR', 'LOCAL_OUTPUT_VIDEOS_DIR', 'DRIVE_ROOT',
         'SOURCE_DIR', 'PHOTOS_DIR', 'VIDEOS_DIR', 'OUTPUT_PHOTOS_DIR', 'OUTPUT_VIDEOS_DIR')


@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in NAMES:
        monkeypatch.setattr(api, name, tmp_path / name.lower())
    monkeypatch.setattr(api, 'THUMB_DIR', tmp_path / 'thumbs')
    monkeypatch.setattr(api, 'OUTPUT_LIST_TTL', 0)
    api._OUTPUT_LIST_CACHE.clear()
    api.ensure_drive_layout()
    api.ensure_local_layout()
    return TestClient(api.app)


def write_image(path, width, height, ext=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = np.random.default_rng(1).integers(0, 255, (height, width, 3), dtype=np.uint8)
    assert cv2.imwrite(str(path), frame)
    return path


def jpeg_size(data):
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    return frame.shape[1], frame.shape[0]


@pytest.mark.parametrize('name', ['a.jpg', 'a.png', 'a.webp', 'a.bmp'])
def test_image_thumbnail_is_a_small_jpeg_with_source_size_headers(client, name):
    write_image(api.OUTPUT_PHOTOS_DIR / name, 1200, 800)
    r = client.get(f'/outputs/photos/thumb/drive/{name}?size=320&v=1')
    assert r.status_code == 200 and r.headers['content-type'] == 'image/jpeg'
    assert jpeg_size(r.content) == (320, 213)
    assert (r.headers['x-source-width'], r.headers['x-source-height']) == ('1200', '800')
    assert 'immutable' in r.headers['cache-control']
    assert len(r.content) < 40_000
    assert 'immutable' not in client.get(f'/outputs/photos/thumb/drive/{name}').headers['cache-control']


def test_small_images_are_never_enlarged_and_alpha_is_flattened(client):
    write_image(api.OUTPUT_PHOTOS_DIR / 'tiny.png', 100, 60)
    assert jpeg_size(client.get('/outputs/photos/thumb/drive/tiny.png?size=640').content) == (100, 60)
    rgba = np.zeros((50, 50, 4), np.uint8)
    cv2.imwrite(str(api.OUTPUT_PHOTOS_DIR / 'alpha.png'), rgba)
    assert client.get('/outputs/photos/thumb/drive/alpha.png').status_code == 200


def test_sizes_snap_to_the_fixed_set(client):
    write_image(api.OUTPUT_PHOTOS_DIR / 'big.jpg', 3000, 2000)
    for requested, expected in ((1, 160), (161, 320), (500, 640), (900, 1600), (99999, 1600)):
        assert max(jpeg_size(client.get(f'/outputs/photos/thumb/drive/big.jpg?size={requested}').content)) == expected
    assert api.snap_thumb_size(320) == 320


def test_thumbnails_are_generated_once_and_regenerated_when_the_file_changes(client, monkeypatch):
    path = write_image(api.OUTPUT_PHOTOS_DIR / 'x.jpg', 800, 600)
    calls = []
    real = api.make_image_thumb
    monkeypatch.setattr(api, 'make_image_thumb', lambda p, s: calls.append(s) or real(p, s))
    first = client.get('/outputs/photos/thumb/drive/x.jpg?size=320').content
    assert client.get('/outputs/photos/thumb/drive/x.jpg?size=320').content == first
    assert calls == [320]
    client.get('/outputs/photos/thumb/drive/x.jpg?size=640')
    assert calls == [320, 640]
    write_image(path, 400, 400)
    os.utime(path, (1_900_000_000, 1_900_000_000))
    assert jpeg_size(client.get('/outputs/photos/thumb/drive/x.jpg?size=320').content) == (320, 320)
    assert calls == [320, 640, 320]
    assert any(api.THUMB_DIR.rglob('*.jpg'))


def test_thumbnail_route_is_confined_and_validates_the_file(client):
    write_image(api.OUTPUT_PHOTOS_DIR / 'ok.jpg', 100, 100)
    (api.OUTPUT_PHOTOS_DIR / 'notes.txt').write_text('x')
    (api.OUTPUT_PHOTOS_DIR / 'broken.png').write_bytes(b'not an image')
    assert client.get('/outputs/photos/thumb/drive/../../../etc/passwd').status_code in (400, 404)
    assert client.get('/outputs/photos/thumb/drive/%2e%2e/%2e%2e/etc/passwd').status_code in (400, 404)
    assert client.get('/outputs/photos/thumb/drive/notes.txt').status_code == 400
    assert client.get('/outputs/photos/thumb/drive/missing.jpg').status_code == 404
    assert client.get('/outputs/photos/thumb/nowhere/ok.jpg').status_code == 404
    assert client.get('/outputs/music/thumb/drive/ok.jpg').status_code == 404
    r = client.get('/outputs/photos/thumb/drive/broken.png')
    assert r.status_code == 422 and 'cannot create a thumbnail' in r.json()['detail']
    assert not any(api.THUMB_DIR.rglob('*.jpg')) if api.THUMB_DIR.exists() else True


def test_video_thumbnail_has_a_frame_and_duration(client):
    path = api.OUTPUT_VIDEOS_DIR / 'clip.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (320, 240))
    for i in range(30):
        writer.write(np.full((240, 320, 3), i * 8, np.uint8))
    writer.release()
    r = client.get('/outputs/videos/thumb/drive/clip.avi?size=160&v=1')
    assert r.status_code == 200 and jpeg_size(r.content) == (160, 120)
    assert (r.headers['x-source-width'], r.headers['x-source-height']) == ('320', '240')
    assert float(r.headers['x-source-duration']) == pytest.approx(3.0, abs=0.2)
    (api.OUTPUT_VIDEOS_DIR / 'bad.mp4').write_bytes(b'nope')
    assert client.get('/outputs/videos/thumb/drive/bad.mp4').status_code == 422


def test_health_advertises_thumbnails(client):
    assert client.get('/health').json()['web_capabilities']['output_thumbs'] is True


def test_listing_is_cached_briefly_then_refreshed(client, monkeypatch):
    write_image(api.OUTPUT_PHOTOS_DIR / 'a.jpg', 50, 50)
    monkeypatch.setattr(api, 'OUTPUT_LIST_TTL', 60)
    assert client.get('/outputs/photos').json()['count'] == 1
    write_image(api.OUTPUT_PHOTOS_DIR / 'b.jpg', 50, 50)
    assert client.get('/outputs/photos').json()['count'] == 1   # still inside the TTL
    monkeypatch.setattr(api, 'OUTPUT_LIST_TTL', 0)
    assert client.get('/outputs/photos').json()['count'] == 2   # TTL off: always fresh
    # different roots never share a cache entry
    assert client.get('/outputs/videos').json()['count'] == 0
    json.dumps(client.get('/outputs/photos').json())
