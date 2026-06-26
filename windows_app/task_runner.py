from __future__ import annotations

import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from windows_app.api_client import ApiClient, format_size
from windows_app.window_core import WindowCore as MainWindow
from windows_app.workers import OutputTaskWorker

DOWNLOAD_CHUNK_SIZE = 64 * 1024  # 64KB for smooth progress updates


def _download_file_fast(
    client: ApiClient,
    path: str,
    destination: Path,
    timeout: float = 900.0,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(client.url(path), timeout=timeout) as response, destination.open("wb") as handle:
        total_size = int(response.headers.get("Content-Length", 0))
        downloaded = 0
        while True:
            chunk = response.read(DOWNLOAD_CHUNK_SIZE)
            if not chunk:
                break
            handle.write(chunk)
            downloaded += len(chunk)
            if progress_callback and total_size > 0:
                progress_callback(downloaded, total_size)
    return destination


def _download_bytes_with_progress(
    client: ApiClient,
    path: str,
    timeout: float = 20.0,
    progress_callback: Callable[[int, int], None] | None = None,
) -> bytes:
    with urllib.request.urlopen(client.url(path), timeout=timeout) as response:
        total_size = int(response.headers.get("Content-Length", 0))
        chunks = []
        downloaded = 0
        while True:
            chunk = response.read(DOWNLOAD_CHUNK_SIZE)
            if not chunk:
                break
            chunks.append(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(downloaded, total_size)
        return b"".join(chunks)


def _ensure_output_worker_state(window: MainWindow) -> None:
    if not hasattr(window, "output_workers"):
        window.output_workers = {}
    if not hasattr(window, "output_refresh_task_id"):
        window.output_refresh_task_id = ""
    if not hasattr(window, "output_preview_task_id"):
        window.output_preview_task_id = ""
    if not hasattr(window, "output_download_task_id"):
        window.output_download_task_id = ""
    if not hasattr(window, "output_health_task_id"):
        window.output_health_task_id = ""
    if not hasattr(window, "output_batch_task_id"):
        window.output_batch_task_id = ""


def _start_output_task(
    window: MainWindow,
    status: str,
    task: Callable[[], object],
    on_success: Callable[[str, object], None],
    on_failure: Callable[[str, str], None],
    on_progress: Callable[[str, int, int], None] | None = None,
) -> str:
    _ensure_output_worker_state(window)
    task_id = uuid.uuid4().hex
    worker = OutputTaskWorker(task_id, task)
    window.output_workers[task_id] = worker
    window.output_status.setText(status)
    worker.succeeded.connect(on_success)
    worker.failed.connect(on_failure)
    if on_progress:
        worker.progress.connect(on_progress)
    worker.finished.connect(lambda task_id=task_id: window.output_workers.pop(task_id, None))
    worker.start()
    return task_id


def _start_output_task_with_progress(
    window: MainWindow,
    status: str,
    task_factory: Callable[[Callable[[int, int], None]], object],
    on_success: Callable[[str, object], None],
    on_failure: Callable[[str, str], None],
) -> str:
    """Start a task that can report progress via a callback."""
    _ensure_output_worker_state(window)
    task_id = uuid.uuid4().hex

    def on_progress(_tid: str, current: int, total: int) -> None:
        if not hasattr(window, "outputs_progress"):
            return
        window.outputs_progress.show()
        if total > 0:
            pct = int(current / total * 100)
            window.outputs_progress.setMaximum(100)
            window.outputs_progress.setValue(pct)
            window.output_status.setText(f"Loading... {pct}%")
        else:
            # Unknown total size - show indeterminate with bytes downloaded
            window.outputs_progress.setMaximum(0)
            window.output_status.setText(f"Loading... {format_size(current)}")
        window.outputs_progress.repaint()
        QApplication.processEvents()

    # Create a mutable container for worker reference
    worker_holder: list[OutputTaskWorker] = []

    def progress_callback(current: int, total: int) -> None:
        if worker_holder:
            worker_holder[0].report_progress(current, total)

    def wrapped_task() -> object:
        return task_factory(progress_callback)

    worker = OutputTaskWorker(task_id, wrapped_task)
    worker_holder.append(worker)
    window.output_workers[task_id] = worker
    window.output_status.setText(status)
    worker.succeeded.connect(on_success)
    worker.failed.connect(on_failure)
    # Use QueuedConnection to ensure signal is processed in main thread
    worker.progress.connect(on_progress, Qt.QueuedConnection)
    worker.finished.connect(lambda task_id=task_id: window.output_workers.pop(task_id, None))
    worker.start()
    return task_id

