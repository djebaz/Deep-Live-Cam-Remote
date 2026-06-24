from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from windows_app import processing_options_patches as _processing_options_patches
from windows_app import app as base
from windows_app import async_outputs as async_base
from windows_app import ui_patches as ui_base

DEFAULT_LIVE_WIDTH = 1280
DEFAULT_LIVE_HEIGHT = 720
DEFAULT_LIVE_JPEG_QUALITY = 80
LIVE_OPTION_KEYS = (
    "many_faces",
    "enhancer",
    "opacity",
    "sharpness",
    "mouth_mask_size",
    "interpolation_weight",
    "poisson_blend",
    "color_correction",
    "max_width",
    "jpeg_quality",
)

_previous_load_settings = base.load_settings
_previous_save_settings = base.save_settings
_original_build_live_tab = base.MainWindow._build_live_tab
_original_sync_settings = base.MainWindow.sync_settings
_original_close_event = base.MainWindow.closeEvent


def _live_setting(settings: base.AppSettings, name: str, default: int) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(1, value)


def _json_payload(text: object) -> dict[str, Any]:
    if not isinstance(text, str):
        return {}
    try:
        payload = base.json.loads(text)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _default_live_options() -> dict[str, Any]:
    defaults = base.AppSettings()
    return {
        "many_faces": False,
        "enhancer": "none",
        "opacity": 1.0,
        "sharpness": 0.0,
        "mouth_mask_size": 0.0,
        "interpolation_weight": 0.0,
        "poisson_blend": False,
        "color_correction": False,
        "max_width": defaults.max_width,
        "jpeg_quality": DEFAULT_LIVE_JPEG_QUALITY,
    }


def _coerce_live_options(value: object) -> dict[str, Any]:
    options = _default_live_options()
    if isinstance(value, dict):
        for key in LIVE_OPTION_KEYS:
            if key in value:
                options[key] = value[key]
    options["many_faces"] = bool(options["many_faces"])
    options["enhancer"] = str(options["enhancer"])
    options["opacity"] = float(options["opacity"])
    options["sharpness"] = float(options["sharpness"])
    options["mouth_mask_size"] = float(options["mouth_mask_size"])
    options["interpolation_weight"] = float(options["interpolation_weight"])
    options["poisson_blend"] = bool(options["poisson_blend"])
    options["color_correction"] = bool(options["color_correction"])
    options["max_width"] = max(64, int(options["max_width"]))
    options["jpeg_quality"] = max(20, min(95, int(options["jpeg_quality"])))
    return options


def _live_options(settings: base.AppSettings) -> dict[str, Any]:
    return _coerce_live_options(getattr(settings, "live_options", None))


def _apply_live_options_to_settings(settings: base.AppSettings) -> None:
    options = _live_options(settings)
    settings.live_options = options
    for key in LIVE_OPTION_KEYS:
        if key != "jpeg_quality":
            setattr(settings, key, options[key])
    settings.live_jpeg_quality = options["jpeg_quality"]


def _read_live_options(window: base.MainWindow) -> dict[str, Any]:
    if not hasattr(window, "live_max_width"):
        return _live_options(window.settings)
    return _coerce_live_options(
        {
            "many_faces": window.live_many_faces.isChecked(),
            "enhancer": window.live_enhancer.currentText(),
            "opacity": float(window.live_opacity.value()),
            "sharpness": float(window.live_sharpness.value()),
            "mouth_mask_size": float(window.live_mouth_mask_size.value()),
            "interpolation_weight": float(window.live_interpolation_weight.value()),
            "poisson_blend": window.live_poisson_blend.isChecked(),
            "color_correction": window.live_color_correction.isChecked(),
            "max_width": int(window.live_max_width.value()),
            "jpeg_quality": int(window.live_jpeg_quality.value()),
        }
    )


def _apply_live_options_to_widgets(window: base.MainWindow) -> None:
    if not hasattr(window, "live_max_width"):
        return
    options = _live_options(window.settings)
    window.live_many_faces.setChecked(bool(options["many_faces"]))
    window.live_enhancer.setCurrentText(str(options["enhancer"]))
    window.live_opacity.setValue(float(options["opacity"]))
    window.live_sharpness.setValue(float(options["sharpness"]))
    window.live_mouth_mask_size.setValue(float(options["mouth_mask_size"]))
    window.live_interpolation_weight.setValue(float(options["interpolation_weight"]))
    window.live_poisson_blend.setChecked(bool(options["poisson_blend"]))
    window.live_color_correction.setChecked(bool(options["color_correction"]))
    window.live_max_width.setValue(int(options["max_width"]))
    window.live_jpeg_quality.setValue(int(options["jpeg_quality"]))


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
    settings.live_options = _coerce_live_options(data.get("live_options"))
    return settings


def save_settings(settings: base.AppSettings) -> None:
    _previous_save_settings(settings)
    try:
        data = base.json.loads(base.APP_STATE.read_text(encoding="utf-8")) if base.APP_STATE.is_file() else {}
        if not isinstance(data, dict):
            data = {}
        data["live_width"] = _live_setting(settings, "live_width", DEFAULT_LIVE_WIDTH)
        data["live_height"] = _live_setting(settings, "live_height", DEFAULT_LIVE_HEIGHT)
        data["live_options"] = _live_options(settings)
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

    options_box = base.QGroupBox("Live processing options")
    options_form = base.QFormLayout(options_box)
    self.live_many_faces = base.QCheckBox()
    self.live_enhancer = base.QComboBox()
    self.live_enhancer.addItems(["none", "gfpgan", "gpen256", "gpen512"])
    self.live_opacity = base.QDoubleSpinBox()
    self.live_opacity.setRange(0.0, 1.0)
    self.live_opacity.setSingleStep(0.1)
    self.live_sharpness = base.QDoubleSpinBox()
    self.live_sharpness.setRange(0.0, 1.0)
    self.live_sharpness.setSingleStep(0.1)
    self.live_mouth_mask_size = base.QDoubleSpinBox()
    self.live_mouth_mask_size.setRange(0.0, 10.0)
    self.live_mouth_mask_size.setSingleStep(0.5)
    self.live_interpolation_weight = base.QDoubleSpinBox()
    self.live_interpolation_weight.setRange(0.0, 1.0)
    self.live_interpolation_weight.setSingleStep(0.1)
    self.live_poisson_blend = base.QCheckBox()
    self.live_color_correction = base.QCheckBox()
    self.live_max_width = base.QSpinBox()
    self.live_max_width.setRange(64, 4096)
    self.live_jpeg_quality = base.QSpinBox()
    self.live_jpeg_quality.setRange(20, 95)

    options_form.addRow("Many faces", self.live_many_faces)
    options_form.addRow("Enhancer", self.live_enhancer)
    options_form.addRow("Opacity (1=full)", self.live_opacity)
    options_form.addRow("Sharpness (0=off)", self.live_sharpness)
    options_form.addRow("Mouth mask (0=off)", self.live_mouth_mask_size)
    options_form.addRow("Interpolation (0=off)", self.live_interpolation_weight)
    options_form.addRow("Poisson blend", self.live_poisson_blend)
    options_form.addRow("Color correction", self.live_color_correction)
    options_form.addRow("Process max width", self.live_max_width)
    options_form.addRow("JPEG quality", self.live_jpeg_quality)
    _apply_live_options_to_widgets(self)
    layout.insertWidget(1, options_box)

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
    self.settings.live_options = _read_live_options(self)
    base.save_settings(self.settings)


def closeEvent(self: base.MainWindow, event: Any) -> None:
    try:
        self.sync_settings()
    except Exception as exc:
        self.log(f"settings save on close failed: {exc}")
    _original_close_event(self, event)


def _prepare_live_settings(settings: base.AppSettings) -> dict[str, Any]:
    client = base.ApiClient(settings)
    logs: list[str] = ["checking Colab API before starting live"]
    client.request_json("GET", "/health", timeout=5.0)

    live_settings = async_base._copy_settings(settings)
    live_settings.live_width = _live_setting(settings, "live_width", DEFAULT_LIVE_WIDTH)
    live_settings.live_height = _live_setting(settings, "live_height", DEFAULT_LIVE_HEIGHT)
    live_settings.live_options = _live_options(settings)
    _apply_live_options_to_settings(live_settings)
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
                            "jpeg_quality": getattr(self.settings, "live_jpeg_quality", DEFAULT_LIVE_JPEG_QUALITY),
                        }
                    )
                )
                ready = await websocket.recv()
                self.message.emit(f"live backend: {ready}")
                ready_payload = _json_payload(ready)
                if "error" in ready_payload:
                    raise RuntimeError(str(ready_payload["error"]))
                while not self._stop:
                    ok, frame = cap.read()
                    if not ok:
                        await asyncio.sleep(0.03)
                        continue
                    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(getattr(self.settings, "live_jpeg_quality", DEFAULT_LIVE_JPEG_QUALITY))])
                    if not ok:
                        continue
                    await websocket.send(encoded.tobytes())
                    reply = await websocket.recv()
                    if isinstance(reply, str):
                        self.message.emit(reply)
                        payload = _json_payload(reply)
                        if "error" in payload:
                            raise RuntimeError(str(payload["error"]))
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
    self.settings.live_options = _read_live_options(self)
    base.save_settings(self.settings)
    settings = async_base._copy_settings(self.settings)
    settings.live_width = _live_setting(self.settings, "live_width", DEFAULT_LIVE_WIDTH)
    settings.live_height = _live_setting(self.settings, "live_height", DEFAULT_LIVE_HEIGHT)
    settings.live_options = _live_options(self.settings)
    _apply_live_options_to_settings(settings)
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
    base.MainWindow.closeEvent = closeEvent
    base.MainWindow.start_live = start_live
    base.MainWindow.update_live_preview = update_live_preview


install()
main = base.main
