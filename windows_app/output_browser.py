from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage, QPixmap

from windows_app import output_tasks as output_tasks_base
from windows_app.api_client import format_size
from windows_app.window_core import WindowCore as MainWindow

OUTPUT_PHOTO_ZOOM_FACTORS = {
    "fit": None,
    "0.5x": 0.5,
    "0.8x": 0.8,
    "1x": 1.0,
    "1.5x": 1.5,
    "2x": 2.0,
}


def _ensure_prefetch_state(window: MainWindow) -> None:
    output_tasks_base._ensure_output_worker_state(window)
    if not hasattr(window, "output_prefetch_cache"):
        window.output_prefetch_cache = {}
    if not hasattr(window, "output_prefetching"):
        window.output_prefetching = set()


def _cache_key(item: dict[str, Any]) -> str:
    return str(item.get("download_path") or "")


def _video_cache_path(window: MainWindow, item: dict[str, Any]) -> Path:
    relative = str(item.get("relative_path") or item.get("name") or "output.mp4")
    safe_relative = relative.replace("/", "_").replace("\\", "_")
    return window.output_temp_dir / f"{item.get('source', 'output')}_{safe_relative}"


def _display_photo(window: MainWindow, item: dict[str, Any], data: bytes) -> None:
    if window.output_video is not None:
        window.output_video.hide()
    window.output_preview.show()
    image = QImage.fromData(data)
    if image.isNull():
        window.output_status.setText("preview failed: downloaded image could not be decoded")
        return
    window.output_photo_pixmap = QPixmap.fromImage(image)
    window.output_photo_item = dict(item)
    apply_output_photo_zoom(window)
    window.output_status.setText(f"Showing {item.get('relative_path')} from {item.get('source')}")


def apply_output_photo_zoom(window: MainWindow) -> None:
    pixmap = getattr(window, "output_photo_pixmap", None)
    if not isinstance(pixmap, QPixmap) or pixmap.isNull():
        return
    zoom = "fit"
    if hasattr(window, "outputs_photo_zoom"):
        zoom = str(window.outputs_photo_zoom.currentText()).lower()
    factor = OUTPUT_PHOTO_ZOOM_FACTORS.get(zoom)
    if factor is None:
        target = window.output_preview.size()
    else:
        original = pixmap.size()
        target = original
        target.setWidth(max(1, int(round(original.width() * factor))))
        target.setHeight(max(1, int(round(original.height() * factor))))
    window.output_preview.setPixmap(pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation))


def _display_video(window: MainWindow, item: dict[str, Any], local_path: Path) -> None:
    relative = str(item.get("relative_path") or item.get("name") or "output.mp4")
    window.output_photo_pixmap = None
    window.output_photo_item = None
    if window.output_player is None or window.output_video is None:
        window.output_preview.show()
        window.output_preview.setText(
            f"Video ready to download:\n{relative}\n\nInstall PySide6 multimedia support for inline playback."
        )
        window.output_status.setText(f"Selected video {relative}")
        return
    window.output_preview.hide()
    window.output_video.show()
    window.output_player.setSource(QUrl.fromLocalFile(str(local_path)))
    window.output_player.play()
    window.output_status.setText(f"Playing {relative}")


def _prefetch_output(window: MainWindow, index: int) -> None:
    _ensure_prefetch_state(window)
    if index < 0 or index >= len(window.output_files):
        return
    item = dict(window.output_files[index])
    key = _cache_key(item)
    if not key or key in window.output_prefetch_cache or key in window.output_prefetching:
        return
    kind = window.outputs_kind.currentText()
    window.output_prefetching.add(key)
    task_id = uuid.uuid4().hex

    def task() -> object:
        if kind == "photos":
            return window.client.download_bytes(key, timeout=30.0)
        local_path = _video_cache_path(window, item)
        if not local_path.exists() or local_path.stat().st_size != int(item.get("size") or -1):
            output_tasks_base._download_file_fast(window.client, key, local_path, timeout=900.0)
        return str(local_path)

    def succeeded(done_task_id: str, result: object) -> None:
        if done_task_id != task_id:
            return
        window.output_prefetching.discard(key)
        window.output_prefetch_cache[key] = Path(result) if kind == "videos" else result

    def failed(done_task_id: str, _error: str) -> None:
        if done_task_id == task_id:
            window.output_prefetching.discard(key)

    worker = output_tasks_base.OutputTaskWorker(task_id, task)
    window.output_workers[task_id] = worker
    worker.succeeded.connect(succeeded)
    worker.failed.connect(failed)
    worker.finished.connect(lambda task_id=task_id: window.output_workers.pop(task_id, None))
    worker.start()


def _prefetch_neighbors(window: MainWindow, index: int, count: int | None = None) -> None:
    if not window.output_files:
        return
    if count is None and window.outputs_kind.currentText() == "photos" and window.outputs_autoplay.isChecked():
        preload_control = getattr(window, "outputs_photo_preload_count", None)
        count = int(preload_control.value()) if preload_control is not None else 10
    count = count if count is not None else 2
    for offset in range(1, min(count, max(0, len(window.output_files) - 1)) + 1):
        _prefetch_output(window, (index + offset) % len(window.output_files))


def show_output_at(self: MainWindow, index: int) -> None:
    if index < 0 or index >= len(self.output_files):
        return
    self.output_timer.stop()
    self.output_current_loaded = False
    _ensure_prefetch_state(self)
    item = dict(self.output_files[index])
    key = _cache_key(item)
    kind = self.outputs_kind.currentText()
    file_size = int(item.get("size") or 0)
    if not key:
        self.output_status.setText("selected output has no download path")
        self.output_current_loaded = True
        self.schedule_outputs_autoplay()
        return
    self.stop_output_video()

    cached = self.output_prefetch_cache.get(key)
    if kind == "photos":
        self.output_photo_pixmap = None
        self.output_photo_item = None
        self.output_preview.setPixmap(QPixmap())
        if isinstance(cached, (bytes, bytearray)):
            _display_photo(self, item, bytes(cached))
            _prefetch_neighbors(self, index)
            self.output_current_loaded = True
            self.schedule_outputs_autoplay()
            return
        size_str = format_size(file_size) if file_size > 0 else ""
        self.output_preview.setText(f"Loading photo preview... {size_str}")
        # Show progress bar
        if hasattr(self, "outputs_progress"):
            self.outputs_progress.setMinimum(0)
            self.outputs_progress.setMaximum(100)
            self.outputs_progress.setValue(0)
            self.outputs_progress.show()

        from typing import Callable
        def fetch_photo(progress_cb: Callable[[int, int], None]) -> bytes:
            return output_tasks_base._download_bytes_with_progress(self.client, key, timeout=20.0, progress_callback=progress_cb)

        def photo_ready(task_id: str, data: object) -> None:
            if task_id != self.output_preview_task_id:
                return
            if hasattr(self, "outputs_progress"):
                self.outputs_progress.hide()
            if isinstance(data, (bytes, bytearray)):
                self.output_prefetch_cache[key] = bytes(data)
                _display_photo(self, item, bytes(data))
                _prefetch_neighbors(self, index)
            self.output_current_loaded = True
            self.schedule_outputs_autoplay()

        def photo_failed(task_id: str, error: str) -> None:
            if task_id != self.output_preview_task_id:
                return
            if hasattr(self, "outputs_progress"):
                self.outputs_progress.hide()
            self.output_status.setText(f"preview failed: {error}")
            self.log(f"output preview failed: {error}")
            self.output_current_loaded = True
            self.schedule_outputs_autoplay()

        self.output_preview_task_id = output_tasks_base._start_output_task_with_progress(
            self, "Loading photo preview...", fetch_photo, photo_ready, photo_failed
        )
        return

    if isinstance(cached, Path) and cached.exists():
        _display_video(self, item, cached)
        _prefetch_neighbors(self, index)
        self.output_current_loaded = True
        self.schedule_outputs_autoplay()
        return
    self.show_video_output(item)


def show_video_output(self: MainWindow, item: dict[str, Any]) -> None:
    _ensure_prefetch_state(self)
    key = _cache_key(item)
    file_size = int(item.get("size") or 0)
    relative = str(item.get("relative_path") or item.get("name") or "output.mp4")
    local_path = _video_cache_path(self, item)
    self.output_photo_pixmap = None
    self.output_photo_item = None
    self.output_preview.setPixmap(QPixmap())
    size_str = format_size(file_size) if file_size > 0 else ""
    self.output_preview.setText(f"Loading video preview:\n{relative}\n{size_str}")
    # Show progress bar
    if hasattr(self, "outputs_progress"):
        self.outputs_progress.setMinimum(0)
        self.outputs_progress.setMaximum(100)
        self.outputs_progress.setValue(0)
        self.outputs_progress.show()

    from typing import Callable
    def fetch_video(progress_cb: Callable[[int, int], None]) -> dict[str, str]:
        if not local_path.exists() or local_path.stat().st_size != file_size:
            output_tasks_base._download_file_fast(self.client, key, local_path, timeout=900.0, progress_callback=progress_cb)
        return {"relative": relative, "local_path": str(local_path), "key": key}

    def video_ready(task_id: str, result: object) -> None:
        if task_id != self.output_preview_task_id:
            return
        if hasattr(self, "outputs_progress"):
            self.outputs_progress.hide()
        payload = result if isinstance(result, dict) else {}
        ready_path = Path(str(payload.get("local_path") or local_path))
        self.output_prefetch_cache[str(payload.get("key") or key)] = ready_path
        _display_video(self, item, ready_path)
        _prefetch_neighbors(self, self.outputs_list.currentRow())
        self.output_current_loaded = True
        self.schedule_outputs_autoplay()

    def video_failed(task_id: str, error: str) -> None:
        if task_id != self.output_preview_task_id:
            return
        if hasattr(self, "outputs_progress"):
            self.outputs_progress.hide()
        self.output_status.setText(f"preview failed: {error}")
        self.log(f"output preview failed: {error}")
        self.output_current_loaded = True
        self.schedule_outputs_autoplay()

    self.output_preview_task_id = output_tasks_base._start_output_task_with_progress(
        self, f"Loading video preview: {relative}", fetch_video, video_ready, video_failed
    )
