from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from windows_app import app as base
from windows_app import async_outputs as async_base
from windows_app import processing_options_patches as processing_base
from windows_app import ui_patches as ui_base

DEFAULT_LIVE_WIDTH = 1280
DEFAULT_LIVE_HEIGHT = 720

_previous_load_settings = base.load_settings
_previous_save_settings = base.save_settings
_original_build_live_tab = base.MainWindow._build_live_tab
_original_sync_settings = base.MainWindow.sync_settings


def _live_setting(settings: base.AppSettings, name: str, default: int) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(1, value)


def load_settings() -> base.AppSettings:
    settings = _previous_load_settings()
    data: dict[str, Any] = {}
    if base.APP_STATE.is_file():
        try:
            loaded = base.json.loads(base.APP_STATE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}
    settings.live_width = int(data.get("live_width") or DEFAULT_LIVE_WIDTH)
    settings.live_height = int(data.get("live_height") or DEFAULT_LIVE_HEIGHT)
    return settings


def save_settings(settings: base.AppSettings) -> None:
    _previous_save_settings(settings)
    try:
        data = base.json.loads(base.APP_STATE.read_text(encoding="utf-8")) if base.APP_STATE.is_file() else {}
        if not isinstance(data, dict):
            data = {}
        data["live_width"] = _live_setting(settings, "live_width", DEFAULT_LIVE_WIDTH)
        data["live_height"] = _live_setting(settings, "live_height", DEFAULT_LIVE_HEIGHT)
        base.APP_STATE.write_text(base.json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def _build_live_tab(self: base.MainWindow) -> None:
    _original_build_live_tab(self)
    live_tab = self.tabs.widget(self.tabs.count() - 1)
    layout = live_tab.layout() if live_tab is not None else None
    form_item = layout.itemAt(0) if layout is not None and layout.count() else None
    form = form_item.layout() if form_item is not None else None
    if form is None:
        return

    self.live_width = base.QSpinBox()
    self.live_width.setRange(160, 4096)
    self.live_width.setValue(_live_setting(self.settings, "live_width", DEFAULT_LIVE_WIDTH))
    self.live_height = base.QSpinBox()
    self.live_height.setRange(120, 2160)
    self.live_height.setValue(_live_setting(self.settings, "live_height", DEFAULT_LIVE_HEIGHT))
    form.addRow("Capture width", self.live_width)
    form.addRow("Capture height", self.live_height)

    if hasattr(self, "live_preview"):
        self.live_preview.setMinimumHeight(180)
        self.live_preview.setMaximumHeight(720)


def sync_settings(self: base.MainWindow) -> None:
    _original_sync_settings(self)
    if hasattr(self, "live_width"):
        self.settings.live_width = int(self.live_width.value())
    else:
        self.settings.live_width = _live_setting(self.settings, "live_width", DEFAULT_LIVE_WIDTH)
    if hasattr(self, "live_height"):
        self.settings.live_height = int(self.live_height.value())
    else:
        self.settings.live_height = _live_setting(self.settings, "live_height", DEFAULT_LIVE_HEIGHT)
    base.save_settings(self.settings)


def _prepare_live_settings(settings: base.AppSettings) -> dict[str, Any]:
    client = base.ApiClient(settings)
    logs: list[str] = ["checking Colab API before starting live"]
    client.request_json("GET", "/health", timeout=5.0)

    live_settings = async_base._copy_settings(settings)
    live_settings.live_width = _live_setting(settings, "live_width", DEFAULT_LIVE_WIDTH)
    live_settings.live_height = _live_setting(settings, "live_height", DEFAULT_LIVE_HEIGHT)
    source_face = live_settings.source_face
    if base.is_local_path(source_face):
        source_path = Path(source_face)
        if not source_path.is_file():
            raise FileNotFoundError(f"Local source face does not exist: {source_face}")
        upload_path, normalization_log = async_base._source_upload_path(source_path)
        if normalization_log:
            logs.append(normalization_log)
        logs.append(f"uploading local source face for live: {source_path}")
        response = client.upload_file("/upload/file?kind=source", upload_path, timeout=30.0)
        live_settings.source_face = str(response.get("path") or source_face)
        logs.append(f"live source uploaded to: {live_settings.source_face}")

    return {"settings": live_settings, "logs": logs}


class LiveWorker(base.LiveWorker):
    async def _run_live(self) -> None:
        import cv2
        import websockets

        uri = self.settings.base_url.replace("http://", "ws://") + "/ws/live"
        self.message.emit(f"connecting live websocket: {uri}")
        cap = cv2.VideoCapture(self.settings.camera_index)
        if not cap.isOpened():
            raise RuntimeError(f"could not open camera index {self.settings.camera_index}")
        requested_width = _live_setting(self.settings, "live_width", DEFAULT_LIVE_WIDTH)
        requested_height = _live_setting(self.settings, "live_height", DEFAULT_LIVE_HEIGHT)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, requested_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, requested_height)
        actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        self.message.emit(
            f"webcam capture: requested {requested_width}x{requested_height}, actual {actual_width}x{actual_height}"
        )
        virtual_cam = None
        try:
            async with websockets.connect(uri, max_size=8 * 1024 * 1024) as websocket:
                await websocket.send(
                    base.json.dumps(
                        {
                            "source_face": self.settings.source_face,
                            "many_faces": self.settings.many_faces,
                            "enhancer": self.settings.enhancer,
                            "opacity": self.settings.opacity,
                            "sharpness": self.settings.sharpness,
                            "mouth_mask_size": self.settings.mouth_mask_size,
                            "interpolation_weight": self.settings.interpolation_weight,
                            "poisson_blend": self.settings.poisson_blend,
                            "color_correction": self.settings.color_correction,
                            "max_width": self.settings.max_width,
                            "jpeg_quality": 80,
                        }
                    )
                )
                ready = await websocket.recv()
                self.message.emit(f"live backend: {ready}")
                while not self._stop:
                    ok, frame = cap.read()
                    if not ok:
                        await asyncio.sleep(0.03)
                        continue
                    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    if not ok:
                        continue
                    await websocket.send(encoded.tobytes())
                    reply = await websocket.recv()
                    if isinstance(reply, str):
                        self.message.emit(reply)
                        continue
                    self.frame.emit(reply)
                    if virtual_cam is None:
                        try:
                            import numpy as np
                            import pyvirtualcam

                            decoded = cv2.imdecode(np.frombuffer(reply, dtype=np.uint8), cv2.IMREAD_COLOR)
                            h, w = decoded.shape[:2]
                            virtual_cam = pyvirtualcam.Camera(width=w, height=h, fps=20, device=self.settings.virtual_camera or None)
                            self.message.emit(f"virtual camera opened: {virtual_cam.device}")
                        except Exception as exc:
                            self.message.emit(f"virtual camera unavailable: {exc}")
                            virtual_cam = False
                    if virtual_cam:
                        import numpy as np

                        decoded = cv2.imdecode(np.frombuffer(reply, dtype=np.uint8), cv2.IMREAD_COLOR)
                        rgb = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
                        virtual_cam.send(rgb)
                        virtual_cam.sleep_until_next_frame()
        finally:
            cap.release()
            if virtual_cam and hasattr(virtual_cam, "close"):
                virtual_cam.close()
            self.message.emit("live worker stopped")


def start_live(self: base.MainWindow) -> None:
    self.sync_settings()
    if self.live_worker and self.live_worker.isRunning():
        self.log("live already running")
        ui_base._set_process_status(self, "live", "Live already running")
        return

    async_base._ensure_output_worker_state(self)
    if hasattr(processing_base, "_apply_processing_options_to_settings"):
        # Live processes image frames, so use the Photos processing profile.
        processing_base._apply_processing_options_to_settings(self.settings, "photos")
        base.save_settings(self.settings)
    settings = async_base._copy_settings(self.settings)
    settings.live_width = _live_setting(self.settings, "live_width", DEFAULT_LIVE_WIDTH)
    settings.live_height = _live_setting(self.settings, "live_height", DEFAULT_LIVE_HEIGHT)
    self.log("starting live...")
    ui_base._set_process_status(self, "live", "Preparing live...")

    def task() -> dict[str, Any]:
        return _prepare_live_settings(settings)

    def succeeded(task_id: str, result: object) -> None:
        if task_id != getattr(self, "output_live_task_id", ""):
            return
        payload = result if isinstance(result, dict) else {}
        for line in payload.get("logs") or []:
            line_text = str(line)
            self.log(line_text)
            ui_base._set_process_status(self, "live", line_text)
        live_settings = payload.get("settings")
        if not isinstance(live_settings, base.AppSettings):
            text = "live failed before start: invalid prepared settings"
            self.log(text)
            ui_base._set_process_status(self, "live", text)
            return
        self.live_worker = LiveWorker(live_settings)
        self.live_worker.message.connect(lambda text: ui_base._poll_message(self, "live", text))
        self.live_worker.frame.connect(self.update_live_preview)
        self.live_worker.start()
        ui_base._set_process_status(self, "live", f"Starting live on camera index {live_settings.camera_index}...")

    def failed(task_id: str, error: str) -> None:
        if task_id != getattr(self, "output_live_task_id", ""):
            return
        text = f"live failed before start: {error}"
        self.log(text)
        ui_base._set_process_status(self, "live", text)

    self.output_live_task_id = async_base._start_output_task(
        self,
        "Preparing live...",
        task,
        succeeded,
        failed,
    )


def update_live_preview(self: base.MainWindow, jpeg_bytes: bytes) -> None:
    image = base.QImage.fromData(jpeg_bytes, "JPG")
    if image.isNull():
        return
    if image.width() > 0 and hasattr(self, "live_preview"):
        preview_width = max(1, self.live_preview.width())
        target_height = int(round(preview_width * image.height() / image.width()))
        target_height = max(160, min(720, target_height))
        if getattr(self, "_live_preview_height", None) != target_height:
            self.live_preview.setMinimumHeight(target_height)
            self.live_preview.setMaximumHeight(target_height)
            self._live_preview_height = target_height
    pixmap = base.QPixmap.fromImage(image).scaled(self.live_preview.size(), base.Qt.KeepAspectRatio, base.Qt.SmoothTransformation)
    self.live_preview.setPixmap(pixmap)
    ui_base._set_process_status(self, "live", f"Live receiving frames ({image.width()}x{image.height()})")


def install() -> None:
    base.load_settings = load_settings
    base.save_settings = save_settings
    base.MainWindow._build_live_tab = _build_live_tab
    base.MainWindow.sync_settings = sync_settings
    base.MainWindow.start_live = start_live
    base.MainWindow.update_live_preview = update_live_preview


install()
main = base.main
