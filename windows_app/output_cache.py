"""Qt-free helpers for the Outputs browser: bounded photo cache and thumbnail URLs."""

from __future__ import annotations

import urllib.error
import urllib.parse
from collections import OrderedDict
from typing import Any, Callable

from windows_app.api_client import ApiClient, _download_bytes_with_progress

PREVIEW_PX = 1600
PHOTO_CACHE_BYTES = 96 * 1024 * 1024
MAX_PREFETCH_WORKERS = 3


class ByteLRU:
    """Least-recently-used cache bounded by total bytes (oversize values are not stored)."""

    def __init__(self, max_bytes: int = PHOTO_CACHE_BYTES):
        self.max_bytes = max_bytes
        self.total = 0
        self._items: OrderedDict[Any, bytes] = OrderedDict()

    def __contains__(self, key: Any) -> bool:
        return key in self._items

    def __len__(self) -> int:
        return len(self._items)

    def get(self, key: Any) -> bytes | None:
        value = self._items.get(key)
        if value is not None:
            self._items.move_to_end(key)
        return value

    def put(self, key: Any, value: bytes) -> None:
        if len(value) > self.max_bytes:
            return
        old = self._items.pop(key, None)
        if old is not None:
            self.total -= len(old)
        self._items[key] = value
        self.total += len(value)
        while self.total > self.max_bytes and self._items:
            _, evicted = self._items.popitem(last=False)
            self.total -= len(evicted)

    def clear(self) -> None:
        self._items.clear()
        self.total = 0


def thumb_path(item: dict[str, Any], size: int = PREVIEW_PX) -> str | None:
    """Backend thumbnail route for an output item, or None if it has no download path."""
    download = str(item.get("download_path") or "")
    if "/file/" not in download:
        return None
    head, tail = download.split("/file/", 1)
    segments = "/".join(urllib.parse.quote(part, safe="") for part in tail.split("/"))
    version = int(float(item.get("modified") or 0) * 1000)
    return f"{head}/thumb/{segments}?size={int(size)}&v={version}"


def fetch_photo(
    client: ApiClient,
    item: dict[str, Any],
    preview: bool,
    progress_cb: Callable[[int, int], None] | None = None,
) -> tuple[bytes, bool]:
    """Download a photo; returns (data, is_preview). Falls back to the original on old backends."""
    key = str(item.get("download_path") or "")
    path = thumb_path(item, PREVIEW_PX) if preview and client.thumbs_supported else None
    if path:
        try:
            return _download_bytes_with_progress(client, path, timeout=30.0, progress_callback=progress_cb), True
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        # 404: an older Colab API has no thumbnail route; use the original.
        data = _download_bytes_with_progress(client, key, timeout=60.0, progress_callback=progress_cb)
        client.thumbs_supported = False
        return data, False
    return _download_bytes_with_progress(client, key, timeout=60.0, progress_callback=progress_cb), False
