from __future__ import annotations

import json
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import QFileDialog, QListWidgetItem

from windows_app.api_client import ApiClient, format_size, is_local_path, job_payload, local_files
from windows_app.task_runner import (
    OutputTaskWorker,
    _download_bytes_with_progress,
    _download_file_fast,
    _ensure_output_worker_state,
    _start_output_task,
    _start_output_task_with_progress,
)
from windows_app.settings import AppSettings, PHOTO_EXTENSIONS, VIDEO_EXTENSIONS
from windows_app.window_core import WindowCore as MainWindow
from windows_app.workers import PollWorker


def _copy_settings(settings: AppSettings) -> AppSettings:
    return AppSettings(**asdict(settings))


def _source_upload_path(path: Path) -> tuple[Path, str | None]:
    if path.suffix.lower() not in PHOTO_EXTENSIONS:
        return path, None
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        return path, None
    output_dir = Path(tempfile.gettempdir()) / "deep_live_cam_remote_sources"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{path.stem}_{uuid.uuid4().hex[:8]}.png"
    if image.save(str(output), "PNG"):
        return output, f"normalized source image orientation for upload: {output}"
    return path, None


def _prepare_and_start_batch(settings: AppSettings, kind: str) -> dict[str, Any]:
    client = ApiClient(settings)
    logs: list[str] = ["checking Colab API before starting batch"]
    client.request_json("GET", "/health", timeout=5.0)

    source_face = settings.source_face
    if is_local_path(source_face):
        source_path = Path(source_face)
        if not source_path.is_file():
            raise FileNotFoundError(f"Local source face does not exist: {source_face}")
        upload_path, normalization_log = _source_upload_path(source_path)
        if normalization_log:
            logs.append(normalization_log)
        logs.append(f"uploading local source face: {source_path}")
        response = client.upload_file("/upload/file?kind=source", upload_path, timeout=30.0)
        source_face = str(response.get("path") or source_face)
        logs.append(f"source uploaded to: {source_face}")

    input_path = settings.photos_input if kind == "photos" else settings.videos_input
    output_path = settings.photos_output if kind == "photos" else settings.videos_output
    input_dir = input_path
    output_dir = output_path
    if is_local_path(input_path):
        extensions = PHOTO_EXTENSIONS if kind == "photos" else VIDEO_EXTENSIONS
        files = local_files(input_path, extensions, settings.recursive)
        if not files:
            raise FileNotFoundError(f"No supported {kind} files found in local path: {input_path}")
        logs.append(f"uploading {len(files)} local {kind} file(s)")
        response = client.upload_files(f"/upload/{kind}", files, timeout=600.0)
        input_dir = str(response.get("input_dir") or input_path)
        if is_local_path(output_path):
            output_dir = str(response.get("output_dir") or output_path)
            logs.append(f"local output path is not reachable from Colab; using: {output_dir}")
        logs.append(f"{kind} uploaded to: {input_dir}")

    endpoint = "/jobs/photos" if kind == "photos" else "/jobs/videos"
    payload = job_payload(settings, input_dir, output_dir, source_face)
    response = client.request_json("POST", endpoint, payload, timeout=10.0)
    logs.append(f"started {endpoint}: {response}")
    return {"endpoint": endpoint, "response": response, "logs": logs}


def _start_batch(self: MainWindow, kind: str) -> None:
    self.sync_settings()
    self.tabs.setCurrentWidget(self.log_box)
    _ensure_output_worker_state(self)
    settings = _copy_settings(self.settings)
    self.log(f"starting {kind} batch...")

    def task() -> dict[str, Any]:
        return _prepare_and_start_batch(settings, kind)

    def succeeded(task_id: str, result: object) -> None:
        if task_id != self.output_batch_task_id:
            return
        payload = result if isinstance(result, dict) else {}
        for line in payload.get("logs") or []:
            self.log(str(line))
        response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
        self.active_job_id = response.get("job_id")
        if self.active_job_id:
            if self.poller:
                self.poller.stop()
            self.poller = PollWorker(self.client, self.active_job_id)
            self.poller.message.connect(self.log)
            self.poller.finished_status.connect(lambda status: self.log(f"job finished: {status}"))
            self.poller.start()
        self.output_status.setText(f"{kind} batch started")

    def failed(task_id: str, error: str) -> None:
        if task_id != self.output_batch_task_id:
            return
        self.output_status.setText(f"{kind} batch failed before start: {error}")
        self.log(f"{kind} batch failed before start: {error}")

    self.output_batch_task_id = _start_output_task(self, f"Starting {kind} batch...", task, succeeded, failed)


def start_photos(self: MainWindow) -> None:
    _start_batch(self, "photos")


def start_videos(self: MainWindow) -> None:
    _start_batch(self, "videos")


def refresh_outputs(self: MainWindow) -> None:
    self.sync_settings()
    _ensure_output_worker_state(self)
    kind = self.outputs_kind.currentText()
    self.outputs_list.clear()
    self.outputs_list.setEnabled(False)
    self.output_files = []
    self.output_current_loaded = False
    self.stop_output_video()
    self.output_preview.setText("Loading outputs...")
    # Indeterminate progress bar during network fetch (min=max=0)
    if hasattr(self, "outputs_progress"):
        self.outputs_progress.setMinimum(0)
        self.outputs_progress.setMaximum(0)
        self.outputs_progress.show()
        self.outputs_progress.repaint()
        QApplication.processEvents()

    def fetch() -> dict[str, Any]:
        return self.client.request_json("GET", f"/outputs/{kind}", timeout=30.0)

    def succeeded(task_id: str, payload: object) -> None:
        if task_id != self.output_refresh_task_id:
            return
        self.outputs_list.setEnabled(True)
        self.output_files = list((payload if isinstance(payload, dict) else {}).get("files") or [])
        total = len(self.output_files)
        has_progress = hasattr(self, "outputs_progress")
        # Switch to determinate mode for list population
        if has_progress:
            self.outputs_progress.setMaximum(100)
            self.outputs_progress.setValue(0)
            self.outputs_progress.repaint()
        for idx, item in enumerate(self.output_files):
            label = f"[{item.get('source')}] {item.get('relative_path')} ({format_size(item.get('size'))})"
            self.outputs_list.addItem(QListWidgetItem(label))
            if has_progress:
                progress = int((idx + 1) / total * 100) if total > 0 else 0
                self.outputs_progress.setValue(progress)
            self.output_status.setText(f"Loading... {idx + 1}/{total}")
            # Update UI every 10 items or on last item
            if idx % 10 == 0 or idx == total - 1:
                if has_progress:
                    self.outputs_progress.repaint()
                QApplication.processEvents()
        if has_progress:
            self.outputs_progress.hide()
        self.output_status.setText(f"{len(self.output_files)} {kind} output file(s)")
        if self.output_files:
            self.outputs_list.setCurrentRow(0)
        else:
            self.output_preview.setPixmap(QPixmap())
            self.output_preview.setText("No remote outputs found")

    def failed(task_id: str, error: str) -> None:
        if task_id != self.output_refresh_task_id:
            return
        self.outputs_list.setEnabled(True)
        if hasattr(self, "outputs_progress"):
            self.outputs_progress.hide()
        self.output_status.setText(f"refresh failed: {error}")
        self.log(f"outputs refresh failed: {error}")

    self.output_refresh_task_id = _start_output_task(self, "Refreshing outputs...", fetch, succeeded, failed)


def cancel_job(self: MainWindow) -> None:
    self.sync_settings()
    if not self.active_job_id:
        self.log("no active job")
        if hasattr(self, "photos_status"):
            self.photos_status.setText("No active job")
        if hasattr(self, "videos_status"):
            self.videos_status.setText("No active job")
        return
    try:
        payload = self.client.request_json("POST", "/jobs/cancel", {"job_id": self.active_job_id})
        text = "cancel: " + json.dumps(payload)
        self.log(text)
        if hasattr(self, "photos_status"):
            self.photos_status.setText("Cancel requested")
        if hasattr(self, "videos_status"):
            self.videos_status.setText("Cancel requested")
    except Exception as exc:
        text = f"cancel failed: {exc}"
        self.log(text)
        if hasattr(self, "photos_status"):
            self.photos_status.setText(text)
        if hasattr(self, "videos_status"):
            self.videos_status.setText(text)


def show_output_at(self: MainWindow, index: int) -> None:
    from windows_app import output_browser

    return output_browser.show_output_at(self, index)


def show_video_output(self: MainWindow, item: dict[str, Any]) -> None:
    from windows_app import output_browser

    return output_browser.show_video_output(self, item)


def download_current_output(self: MainWindow) -> None:
    item = self.current_output()
    if not item:
        self.output_status.setText("No output selected")
        return
    folder = QFileDialog.getExistingDirectory(self, "Download selected output to folder")
    if not folder:
        return
    item = dict(item)
    destination = Path(folder) / str(item.get("name") or Path(str(item.get("relative_path"))).name)

    def download() -> str:
        return str(_download_file_fast(self.client, str(item.get("download_path")), destination))

    def succeeded(task_id: str, result: object) -> None:
        if task_id != self.output_download_task_id:
            return
        self.output_status.setText(f"Downloaded to {result}")
        self.log(f"downloaded output: {result}")

    def failed(task_id: str, error: str) -> None:
        if task_id != self.output_download_task_id:
            return
        self.output_status.setText(f"download failed: {error}")
        self.log(f"download failed: {error}")

    self.output_download_task_id = _start_output_task(self, f"Downloading {destination.name}...", download, succeeded, failed)


def download_all_outputs(self: MainWindow) -> None:
    if not self.output_files:
        self.output_status.setText("No outputs to download")
        return
    folder = QFileDialog.getExistingDirectory(self, "Download all listed outputs to folder")
    if not folder:
        return
    kind = self.outputs_kind.currentText()
    destination = Path(folder) / f"{kind}_outputs.zip"

    def download_all() -> str:
        return str(_download_file_fast(self.client, f"/outputs/{kind}/zip", destination, timeout=1800.0))

    def succeeded(task_id: str, result: object) -> None:
        if task_id != self.output_download_task_id:
            return
        self.output_status.setText(f"Downloaded ZIP to {result}")
        self.log(f"downloaded {kind} outputs ZIP to {result}")

    def failed(task_id: str, error: str) -> None:
        if task_id != self.output_download_task_id:
            return
        self.output_status.setText(f"download all failed: {error}")
        self.log(f"download all failed: {error}")

    self.output_download_task_id = _start_output_task(self, f"Downloading {kind} ZIP...", download_all, succeeded, failed)


def check_connection(self: MainWindow) -> None:
    self.sync_settings()
    self.tabs.setCurrentWidget(self.log_box)
    _ensure_output_worker_state(self)
    self.log("checking connection...")

    def fetch_health() -> dict[str, Any]:
        return self.client.request_json("GET", "/health", timeout=5.0)

    def succeeded(task_id: str, payload: object) -> None:
        if task_id != self.output_health_task_id:
            return
        self.log("health: " + json.dumps(payload, indent=2))

    def failed(task_id: str, error: str) -> None:
        if task_id != self.output_health_task_id:
            return
        self.log(f"health failed: {error}")

    self.output_health_task_id = _start_output_task(self, "Checking connection...", fetch_health, succeeded, failed)


def main() -> int:
    from windows_app.app import main as app_main

    return app_main()
