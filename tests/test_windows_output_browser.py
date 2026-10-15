"""Windows app Outputs browser: bounded photo cache, thumbnail URLs and preview fallback."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

from windows_app.api_client import ApiClient
from windows_app.output_cache import ByteLRU, fetch_photo, thumb_path


def test_byte_lru_evicts_least_recently_used_and_skips_oversize():
    cache = ByteLRU(max_bytes=10)
    cache.put("a", b"1234")
    cache.put("b", b"1234")
    assert cache.get("a") == b"1234"  # a is now newest
    cache.put("c", b"1234")  # 12 bytes > 10: evicts b
    assert "b" not in cache and "a" in cache and "c" in cache
    cache.put("big", b"x" * 11)
    assert "big" not in cache
    cache.put("a", b"12")  # replacing adjusts the total
    assert cache.total == 6
    cache.clear()
    assert len(cache) == 0 and cache.total == 0


def test_thumb_path_encodes_segments_and_version():
    item = {"download_path": "/outputs/photos/file/local/a b/ü#1.png", "modified": 12.5}
    assert thumb_path(item, 800) == "/outputs/photos/thumb/local/a%20b/%C3%BC%231.png?size=800&v=12500"
    assert thumb_path({"download_path": ""}) is None
    assert thumb_path({"download_path": "/something/else"}) is None


class _Backend:
    def __init__(self, with_thumbs: bool):
        outer = self
        self.requests: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                outer.requests.append(self.path)
                if "/thumb/" in self.path and with_thumbs:
                    body = b"PREVIEW"
                elif "/file/" in self.path:
                    body = b"ORIGINAL-BYTES"
                else:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()


def _client(base: str) -> ApiClient:
    return ApiClient(SimpleNamespace(base_url=base))


ITEM = {"download_path": "/outputs/photos/file/local/a.png", "modified": 1.0}


def test_preview_is_used_when_backend_has_thumbnails():
    backend = _Backend(with_thumbs=True)
    try:
        client = _client(backend.base)
        data, is_preview = fetch_photo(client, ITEM, preview=True)
        assert (data, is_preview) == (b"PREVIEW", True)
        assert backend.requests == ["/outputs/photos/thumb/local/a.png?size=1600&v=1000"]
    finally:
        backend.close()


def test_falls_back_to_original_on_old_backend_and_remembers():
    backend = _Backend(with_thumbs=False)
    try:
        client = _client(backend.base)
        data, is_preview = fetch_photo(client, ITEM, preview=True)
        assert (data, is_preview) == (b"ORIGINAL-BYTES", False)
        assert client.thumbs_supported is False
    finally:
        backend.close()


def test_fixed_zoom_downloads_original_directly():
    backend = _Backend(with_thumbs=True)
    try:
        client = _client(backend.base)
        data, is_preview = fetch_photo(client, ITEM, preview=False)
        assert (data, is_preview) == (b"ORIGINAL-BYTES", False)
        assert backend.requests == ["/outputs/photos/file/local/a.png"]
    finally:
        backend.close()
