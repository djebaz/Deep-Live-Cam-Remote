"""Outputs still being written must stay invisible until they are complete."""
import pytest
from fastapi.testclient import TestClient

import colab_api as api
import colab_batch as batch

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


def test_partial_path_is_hidden_and_keeps_the_extension(tmp_path):
    partial = batch.partial_output_path(tmp_path / 'a' / 'clip_face_swapped.mp4')
    assert partial.parent == tmp_path / 'a'
    assert partial.name == '.clip_face_swapped.partial.mp4'


def test_publish_appears_only_after_the_writer_finished(tmp_path):
    final = tmp_path / 'out' / 'clip.mp4'
    seen = {}

    def writer(partial):
        partial.write_bytes(b'half')
        seen['final_exists'] = final.exists()
        seen['partial'] = partial.name
        return {'size_mb': 0.0}

    assert batch._publish_atomically(writer, final) == {'size_mb': 0.0}
    assert seen == {'final_exists': False, 'partial': '.clip.partial.mp4'}
    assert final.read_bytes() == b'half'
    assert not batch.partial_output_path(final).exists()


@pytest.mark.parametrize('error', [RuntimeError('ffmpeg died'), batch.BatchCancelled('cancel')])
def test_failed_or_cancelled_write_leaves_nothing(tmp_path, error):
    final = tmp_path / 'clip.mp4'

    def writer(partial):
        partial.write_bytes(b'half')
        raise error

    with pytest.raises(type(error)):
        batch._publish_atomically(writer, final)
    assert list(tmp_path.iterdir()) == []


def test_failed_write_keeps_a_previous_complete_output(tmp_path):
    final = tmp_path / 'clip.mp4'
    final.write_bytes(b'old complete')

    def writer(partial):
        partial.write_bytes(b'half')
        raise RuntimeError('boom')

    with pytest.raises(RuntimeError):
        batch._publish_atomically(writer, final)
    assert final.read_bytes() == b'old complete'


def test_api_hides_and_refuses_partial_outputs(client):
    videos = api.LOCAL_OUTPUT_VIDEOS_DIR
    (videos / 'done.mp4').write_bytes(b'x' * 10)
    (videos / '.busy_face_swapped.partial.mp4').write_bytes(b'y' * 10)
    names = [f['name'] for f in client.get('/outputs/videos').json()['files']]
    assert names == ['done.mp4']
    response = client.get('/outputs/videos/file/local/.busy_face_swapped.partial.mp4')
    assert response.status_code == 404
