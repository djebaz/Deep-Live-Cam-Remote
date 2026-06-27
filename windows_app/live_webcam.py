from __future__ import annotations

import asyncio
import configparser
import csv
import datetime as dt
import json
import os
import queue
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from windows_app import main_window_ui as ui_base
from windows_app import live_preview
from windows_app import output_tasks as output_tasks_base
from windows_app import processing_options as processing_options_base
from windows_app.api_client import ApiClient, is_local_path
from windows_app.settings import APP_STATE, AppSettings
from windows_app.live_options import (
    DEFAULT_LIVE_CAPTURE_BACKEND,
    DEFAULT_LIVE_CAPTURE_MODE,
    DEFAULT_LIVE_CAPTURE_SCALE,
    DEFAULT_LIVE_CAPTURE_HEIGHT,
    DEFAULT_LIVE_CAPTURE_WIDTH,
    DEFAULT_LIVE_DETECT_EVERY_N,
    DEFAULT_LIVE_DETECTOR_SIZE,
    DEFAULT_LIVE_FACE_MODEL_PACK,
    DEFAULT_LIVE_FPS,
    DEFAULT_LIVE_FRAME_CODEC,
    DEFAULT_LIVE_HEIGHT,
    DEFAULT_LIVE_JPEG_QUALITY,
    DEFAULT_LIVE_OUTPUT_CODEC,
    DEFAULT_LIVE_PIPELINE_FRAMES,
    DEFAULT_LIVE_PREVIEW_BUFFER_SECONDS,
    DEFAULT_LIVE_PREVIEW_SCALE,
    DEFAULT_LIVE_SWAPPER_PRECISION,
    DEFAULT_LIVE_WIDTH,
    LIVE_CAPTURE_BACKENDS,
    LIVE_CAPTURE_MODES,
    LIVE_CAPTURE_SCALE_FACTORS,
    LIVE_CAPTURE_SCALES,
    LIVE_FACE_MODEL_PACKS,
    LIVE_FRAME_CODECS,
    LIVE_PREVIEW_SCALES,
    LIVE_SWAPPER_PRECISIONS,
    _apply_live_options_to_settings,
    _coerce_live_options,
    _live_options,
    _live_setting,
)
from windows_app.window_core import WindowCore as MainWindow
from windows_app.workers import LiveWorker as BaseLiveWorker

LIVE_HOT_CHANGE_KEYS = (
    "many_faces",
    "opacity",
    "sharpness",
    "mouth_mask_size",
    "interpolation_weight",
    "poisson_blend",
    "color_correction",
    "max_width",
    "frame_codec",
    "output_codec",
    "jpeg_quality",
    "detector_size",
    "detect_every_n",
)
LIVE_LOCAL_HOT_CHANGE_KEYS = (
    "capture_scale",
    "live_pipeline_frames",
)
LIVE_PERF_CASE_SECONDS = 12.0
LIVE_PERF_WARMUP_SECONDS = 3.0
LIVE_PERF_CAPTURE_SCALE = "1/2x"
LIVE_PERF_JPEG_QUALITY = 70
LIVE_PERF_DETECT_EVERY_N = 3
LIVE_PERF_DETECTOR_SIZE = 256
LIVE_PERF_PIPELINE_FRAMES = 64
LIVE_PERF_CSV_COLUMNS = (
    "timestamp",
    "case_id",
    "case_total",
    "case_elapsed_s",
    "warmup",
    "status",
    "api_version",
    "capture_scale",
    "frame_codec",
    "output_codec",
    "encoded_codec",
    "jpeg_quality",
    "frame_quality",
    "detector_size",
    "detect_every_n",
    "face_model_pack",
    "swapper_precision",
    "swapper_loaded_precision",
    "cache_source_face",
    "pipeline_frames",
    "max_width",
    "input",
    "processing",
    "frame_seq",
    "server_queue_ms",
    "client_to_server_ms",
    "capture_to_server_ms",
    "receive_to_send_ms",
    "latest_drop_count",
    "frames_dropped_before_process",
    "server_decode_to_process_ms",
    "server_process_to_encode_ms",
    "server_fps",
    "wait_ms",
    "decode_ms",
    "resize_ms",
    "process_ms",
    "detect_ms",
    "landmarks_ms",
    "swap_ms",
    "source_refresh_ms",
    "face_swap_ms",
    "post_ms",
    "enhance_ms",
    "encode_ms",
    "in_kb",
    "out_kb",
    "detect_reuse_pct",
    "faces",
    "client_fps",
    "capture_read_ms",
    "capture_wait_ms",
    "capture_grab_ms",
    "capture_retrieve_ms",
    "capture_age_ms",
    "capture_thread_fps",
    "dropped_capture_frames",
    "duplicate_sender_frames",
    "capture_seq",
    "client_resize_ms",
    "client_encode_ms",
    "send_ms",
    "backpressure_ms",
    "sent_kb",
    "client_frame_width",
    "client_frame_height",
    "client_in_flight",
    "client_pipeline_frames",
    "client_frame_codec",
    "client_jpeg_quality",
    "client_capture_scale",
    "receiver_fps",
    "receiver_decode_ms",
    "virtual_send_ms",
    "backend_json",
    "client_json",
    "receiver_json",
)


def _json_payload(text: object) -> dict[str, Any]:
    if not isinstance(text, str):
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _status_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("statusLabel")
    label.setWordWrap(True)
    return label


def _even_dimension(value: float | int) -> int:
    return max(2, int(value) // 2 * 2)


def _capture_scale_factor(scale: str) -> float | None:
    normalized = str(scale or DEFAULT_LIVE_CAPTURE_SCALE).lower()
    return LIVE_CAPTURE_SCALE_FACTORS.get(normalized)


def _scaled_frame_size(frame: Any, scale: str) -> tuple[int, int]:
    height, width = frame.shape[:2]
    factor = _capture_scale_factor(scale)
    if factor is None:
        return width, height
    return _even_dimension(width * factor), _even_dimension(height * factor)


def _capture_target_size(frame: Any, config: dict[str, Any] | None = None) -> tuple[int, int]:
    options = config or {}
    scale = str(options.get("capture_scale", DEFAULT_LIVE_CAPTURE_SCALE)).lower()
    return _scaled_frame_size(frame, scale)


def _resize_for_capture_config(frame: Any, config: dict[str, Any], cv2_module: Any) -> Any:
    target_width, target_height = _capture_target_size(frame, config)
    height, width = frame.shape[:2]
    if (target_width, target_height) == (width, height):
        return frame
    return cv2_module.resize(frame, (target_width, target_height), interpolation=cv2_module.INTER_AREA)


def _read_warm_camera_frame(cap: Any, attempts: int = 10) -> Any:
    last = None
    for _ in range(attempts):
        ok, frame = cap.read()
        if ok and frame is not None:
            last = frame
    if last is None:
        raise RuntimeError("could not read webcam frame")
    return last


def _open_video_capture(cv2_module: Any, camera_index: int, backend: str) -> Any:
    normalized = str(backend or DEFAULT_LIVE_CAPTURE_BACKEND).lower()
    if normalized in {"directshow", "dshow"}:
        return cv2_module.VideoCapture(camera_index, cv2_module.CAP_DSHOW)
    if normalized == "msmf":
        return cv2_module.VideoCapture(camera_index, cv2_module.CAP_MSMF)
    return cv2_module.VideoCapture(camera_index)


def _read_ini(path: Path) -> configparser.ConfigParser | None:
    parser = configparser.ConfigParser()
    parser.optionxform = str
    try:
        read = parser.read(path, encoding="utf-8-sig")
    except Exception:
        return None
    return parser if read else None


def _obs_active_profile_paths(profiles_root: Path) -> list[Path]:
    obs_root = profiles_root.parents[1]
    paths: list[Path] = []
    global_ini = obs_root / "global.ini"
    parser = _read_ini(global_ini)
    if parser is not None and parser.has_section("Basic"):
        basic = parser["Basic"]
        for key in ("ProfileDir", "Profile"):
            profile = str(basic.get(key, "")).strip()
            if profile:
                paths.append(profiles_root / profile / "basic.ini")
    return [path for path in paths if path.is_file()]


def _obs_profile_candidates(profiles_root: Path) -> list[Path]:
    active = _obs_active_profile_paths(profiles_root)
    if active:
        return active
    return sorted(
        profiles_root.glob("*/basic.ini"),
        key=lambda path: path.stat().st_mtime if path.is_file() else 0,
        reverse=True,
    )


def _detect_obs_profile_resolution() -> tuple[int, int, str] | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    profiles_root = Path(appdata) / "obs-studio" / "basic" / "profiles"
    if not profiles_root.is_dir():
        return None
    for path in _obs_profile_candidates(profiles_root):
        parser = _read_ini(path)
        if parser is None:
            continue
        if not parser.has_section("Video"):
            continue
        video = parser["Video"]
        for width_key, height_key, label in (
            ("BaseCX", "BaseCY", "OBS base canvas"),
            ("OutputCX", "OutputCY", "OBS output"),
        ):
            try:
                width = int(video.get(width_key, "0"))
                height = int(video.get(height_key, "0"))
            except ValueError:
                continue
            if width > 0 and height > 0:
                profile = path.parent.name
                return width, height, f"{label} from profile {profile}"
    return None


def _source_fields(window: MainWindow) -> list[Any]:
    fields = []
    for name in ("source_face", "video_source_face", "live_source_face"):
        field = getattr(window, name, None)
        if field is not None:
            fields.append(field)
    return fields


def _link_live_source_fields(window: MainWindow) -> None:
    if getattr(window, "_live_source_fields_linked", False):
        return
    fields = _source_fields(window)
    if len(fields) < 2:
        return

    def mirror(origin: Any, text: str) -> None:
        window.settings.source_face = text.strip()
        for target in _source_fields(window):
            if target is origin or target.text() == text:
                continue
            target.blockSignals(True)
            target.setText(text)
            target.blockSignals(False)

    for field in fields:
        field.textChanged.connect(lambda text, origin=field: mirror(origin, text))
    window._live_source_fields_linked = True


def _read_live_options(window: MainWindow) -> dict[str, Any]:
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
            "frame_codec": window.live_frame_codec.currentText(),
            "output_codec": window.live_output_codec.currentText(),
            "jpeg_quality": int(window.live_jpeg_quality.value()),
            "detector_size": int(window.live_detector_size.value()),
            "detect_every_n": int(window.live_detect_every_n.value()),
            "capture_backend": window.live_capture_backend.currentText(),
            "capture_mode": window.live_capture_mode.currentText(),
            "capture_scale": window.live_capture_scale.currentText(),
            "capture_width": int(window.live_capture_width.value()),
            "capture_height": int(window.live_capture_height.value()),
            "face_model_pack": window.live_face_model_pack.currentText(),
            "swapper_precision": window.live_swapper_precision.currentText(),
            "cache_source_face": window.live_cache_source_face.isChecked(),
            "preview_buffer_seconds": float(window.live_preview_buffer_seconds.value()),
            "preview_scale": window.live_preview_scale.currentText() if hasattr(window, "live_preview_scale") else DEFAULT_LIVE_PREVIEW_SCALE,
        }
    )


def _apply_live_options_to_widgets(window: MainWindow) -> None:
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
    window.live_frame_codec.setCurrentText(str(options["frame_codec"]))
    window.live_output_codec.setCurrentText(str(options["output_codec"]))
    window.live_jpeg_quality.setValue(int(options["jpeg_quality"]))
    window.live_detector_size.setValue(int(options["detector_size"]))
    window.live_detect_every_n.setValue(int(options["detect_every_n"]))
    window.live_capture_backend.setCurrentText(str(options["capture_backend"]))
    window.live_capture_mode.setCurrentText(str(options["capture_mode"]))
    window.live_capture_scale.setCurrentText(str(options["capture_scale"]))
    window.live_capture_width.setValue(int(options["capture_width"]))
    window.live_capture_height.setValue(int(options["capture_height"]))
    window.live_face_model_pack.setCurrentText(str(options["face_model_pack"]))
    window.live_swapper_precision.setCurrentText(str(options["swapper_precision"]))
    window.live_cache_source_face.setChecked(bool(options["cache_source_face"]))
    window.live_preview_buffer_seconds.setValue(float(options["preview_buffer_seconds"]))
    if hasattr(window, "live_preview_scale"):
        window.live_preview_scale.setCurrentText(str(options["preview_scale"]))


def _live_hot_change_payload(window: MainWindow) -> dict[str, Any]:
    options = _read_live_options(window)
    payload = {key: options[key] for key in LIVE_HOT_CHANGE_KEYS}
    payload.update({key: options[key] for key in LIVE_LOCAL_HOT_CHANGE_KEYS if key in options})
    payload["live_pipeline_frames"] = int(window.live_pipeline_frames.value())
    return payload


def _live_hot_change_payload_from_settings(settings: AppSettings) -> dict[str, Any]:
    options = _live_options(settings)
    payload = {key: options[key] for key in LIVE_HOT_CHANGE_KEYS}
    payload.update({key: options[key] for key in LIVE_LOCAL_HOT_CHANGE_KEYS if key in options})
    payload["live_pipeline_frames"] = _live_setting(settings, "live_pipeline_frames", DEFAULT_LIVE_PIPELINE_FRAMES)
    return payload


def _live_restart_only_widgets(window: MainWindow) -> list[Any]:
    return [
        widget
        for widget in (
            getattr(window, "camera_index", None),
            getattr(window, "virtual_camera", None),
            getattr(window, "live_source_face", None),
            getattr(window, "live_source_browse", None),
            getattr(window, "live_capture_backend", None),
            getattr(window, "live_capture_mode", None),
            getattr(window, "live_capture_width", None),
            getattr(window, "live_capture_height", None),
            getattr(window, "live_width", None),
            getattr(window, "live_height", None),
            getattr(window, "live_fps", None),
            getattr(window, "live_enhancer", None),
            getattr(window, "live_face_model_pack", None),
            getattr(window, "live_swapper_precision", None),
            getattr(window, "live_cache_source_face", None),
        )
        if widget is not None
    ]


def _set_live_controls_running(window: MainWindow, running: bool) -> None:
    window._live_controls_running = running
    for widget in _live_restart_only_widgets(window):
        widget.setEnabled(not running)
    start_button = getattr(window, "live_start_btn", None)
    if start_button is not None:
        start_button.setEnabled(not running)
    stop_button = getattr(window, "live_stop_btn", None)
    if stop_button is not None:
        stop_button.setEnabled(running)
    perf_button = getattr(window, "live_perf_test_btn", None)
    if perf_button is not None:
        perf_button.setEnabled(running)
    note = getattr(window, "live_restart_note", None)
    if note is not None:
        note.setVisible(running)
    _update_capture_custom_controls(window)


def _update_capture_custom_controls(window: MainWindow) -> None:
    is_custom = getattr(window, "live_capture_mode", None) is not None and window.live_capture_mode.currentText() == "custom"
    enabled = is_custom and not getattr(window, "_live_controls_running", False)
    for widget_name in ("live_capture_width", "live_capture_height"):
        widget = getattr(window, widget_name, None)
        if widget is not None:
            widget.setEnabled(enabled)


def _set_combo_text(widget: QComboBox, value: str) -> None:
    index = widget.findText(value)
    if index >= 0:
        widget.setCurrentIndex(index)


def _live_perf_cases() -> list[dict[str, Any]]:
    cases = []
    for frame_codec in ("jpeg", "webp"):
        for output_codec in ("jpeg", "webp"):
            cases.append(
                {
                    "capture_scale": LIVE_PERF_CAPTURE_SCALE,
                    "frame_codec": frame_codec,
                    "output_codec": output_codec,
                    "jpeg_quality": LIVE_PERF_JPEG_QUALITY,
                    "detector_size": LIVE_PERF_DETECTOR_SIZE,
                    "detect_every_n": LIVE_PERF_DETECT_EVERY_N,
                    "live_pipeline_frames": LIVE_PERF_PIPELINE_FRAMES,
                }
            )
    return cases


def _live_perf_output_path() -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path.home() / f"deep_live_cam_remote_live_perf_{stamp}.csv"


def _set_live_perf_button(window: MainWindow, running: bool) -> None:
    button = getattr(window, "live_perf_test_btn", None)
    if button is not None:
        button.setText("Stop perf test" if running else "Run perf test")


def _set_live_perf_case_widgets(window: MainWindow, case: dict[str, Any]) -> None:
    widgets = (
        window.live_capture_scale,
        window.live_frame_codec,
        window.live_output_codec,
        window.live_jpeg_quality,
        window.live_detector_size,
        window.live_detect_every_n,
        window.live_pipeline_frames,
    )
    for widget in widgets:
        widget.blockSignals(True)
    try:
        _set_combo_text(window.live_capture_scale, str(case["capture_scale"]))
        _set_combo_text(window.live_frame_codec, str(case["frame_codec"]))
        _set_combo_text(window.live_output_codec, str(case["output_codec"]))
        window.live_jpeg_quality.setValue(int(case["jpeg_quality"]))
        window.live_detector_size.setValue(int(case["detector_size"]))
        window.live_detect_every_n.setValue(int(case["detect_every_n"]))
        window.live_pipeline_frames.setValue(int(case["live_pipeline_frames"]))
    finally:
        for widget in widgets:
            widget.blockSignals(False)
    _apply_live_hot_change(window)


def _start_live_perf_test(window: MainWindow) -> None:
    worker = getattr(window, "live_worker", None)
    if worker is None or not worker.isRunning():
        ui_base._set_process_status(window, "live", "Start Live before running the perf test.")
        window.log("live perf test skipped: Live is not running")
        return
    if getattr(window, "_live_perf_test_running", False):
        return
    window._live_perf_test_running = True
    window._live_perf_cases = _live_perf_cases()
    window._live_perf_case_index = -1
    window._live_perf_case_started = 0.0
    window._live_perf_original_options = _read_live_options(window)
    window._live_perf_original_pipeline_frames = int(window.live_pipeline_frames.value())
    window._live_perf_output_path = _live_perf_output_path()
    window._live_perf_csv_initialized = False
    window._live_latest_client_perf = {}
    window._live_latest_receiver_perf = {}
    timer = getattr(window, "_live_perf_test_timer", None)
    if timer is None:
        timer = QTimer(window)
        timer.timeout.connect(lambda: _advance_live_perf_test(window))
        window._live_perf_test_timer = timer
    timer.setInterval(int(LIVE_PERF_CASE_SECONDS * 1000))
    _set_live_perf_button(window, True)
    window.log(
        f"live perf test started: {len(window._live_perf_cases)} cases, "
        f"{LIVE_PERF_CASE_SECONDS:g}s each, fixed quality={LIVE_PERF_JPEG_QUALITY}, "
        f"scale={LIVE_PERF_CAPTURE_SCALE}, detect_every_n={LIVE_PERF_DETECT_EVERY_N}, "
        f"detector_size={LIVE_PERF_DETECTOR_SIZE}, pipeline_frames={LIVE_PERF_PIPELINE_FRAMES}, "
        f"csv {window._live_perf_output_path}"
    )
    _advance_live_perf_test(window)
    timer.start()


def _stop_live_perf_test(window: MainWindow, restore: bool = True) -> None:
    timer = getattr(window, "_live_perf_test_timer", None)
    if timer is not None:
        timer.stop()
    if not getattr(window, "_live_perf_test_running", False):
        _set_live_perf_button(window, False)
        return
    window._live_perf_test_running = False
    if restore and hasattr(window, "_live_perf_original_options"):
        original = dict(window._live_perf_original_options)
        restore_case = {
            "capture_scale": original.get("capture_scale", DEFAULT_LIVE_CAPTURE_SCALE),
            "frame_codec": original.get("frame_codec", DEFAULT_LIVE_FRAME_CODEC),
            "output_codec": original.get("output_codec", DEFAULT_LIVE_OUTPUT_CODEC),
            "jpeg_quality": original.get("jpeg_quality", DEFAULT_LIVE_JPEG_QUALITY),
            "detector_size": original.get("detector_size", DEFAULT_LIVE_DETECTOR_SIZE),
            "detect_every_n": original.get("detect_every_n", DEFAULT_LIVE_DETECT_EVERY_N),
            "live_pipeline_frames": getattr(window, "_live_perf_original_pipeline_frames", DEFAULT_LIVE_PIPELINE_FRAMES),
        }
        _set_live_perf_case_widgets(window, restore_case)
    _set_live_perf_button(window, False)
    output_path = getattr(window, "_live_perf_output_path", None)
    if output_path:
        window.log(f"live perf test stopped: {output_path}")


def _toggle_live_perf_test(window: MainWindow) -> None:
    if getattr(window, "_live_perf_test_running", False):
        _stop_live_perf_test(window)
    else:
        _start_live_perf_test(window)


def _advance_live_perf_test(window: MainWindow) -> None:
    if not getattr(window, "_live_perf_test_running", False):
        return
    cases = getattr(window, "_live_perf_cases", [])
    next_index = int(getattr(window, "_live_perf_case_index", -1)) + 1
    if next_index >= len(cases):
        window.log(f"live perf test completed: {getattr(window, '_live_perf_output_path', '')}")
        _stop_live_perf_test(window)
        return
    window._live_perf_case_index = next_index
    window._live_perf_case_started = time.monotonic()
    case = cases[next_index]
    _set_live_perf_case_widgets(window, case)
    ui_base._set_process_status(
        window,
        "live",
        f"Live perf test case {next_index + 1}/{len(cases)}: {case}",
    )


def _live_perf_csv_row(window: MainWindow, payload: dict[str, Any]) -> dict[str, Any]:
    case_index = int(getattr(window, "_live_perf_case_index", -1))
    case_total = len(getattr(window, "_live_perf_cases", []))
    started = float(getattr(window, "_live_perf_case_started", 0.0) or 0.0)
    elapsed = max(0.0, time.monotonic() - started) if started else 0.0
    options = _read_live_options(window)
    client_payload = getattr(window, "_live_latest_client_perf", {})
    if not isinstance(client_payload, dict):
        client_payload = {}
    receiver_payload = getattr(window, "_live_latest_receiver_perf", {})
    if not isinstance(receiver_payload, dict):
        receiver_payload = {}
    row: dict[str, Any] = {column: "" for column in LIVE_PERF_CSV_COLUMNS}
    row.update(
        {
            "timestamp": dt.datetime.now().isoformat(timespec="milliseconds"),
            "case_id": case_index + 1 if case_index >= 0 else "",
            "case_total": case_total or "",
            "case_elapsed_s": f"{elapsed:.3f}",
            "warmup": elapsed < LIVE_PERF_WARMUP_SECONDS,
            "status": payload.get("status", ""),
            "api_version": payload.get("api_version", ""),
            "capture_scale": options.get("capture_scale", ""),
            "frame_codec": payload.get("frame_codec", options.get("frame_codec", "")),
            "output_codec": payload.get("output_codec", options.get("output_codec", "")),
            "encoded_codec": payload.get("encoded_codec", ""),
            "jpeg_quality": payload.get("jpeg_quality", options.get("jpeg_quality", "")),
            "frame_quality": payload.get("frame_quality", ""),
            "detector_size": payload.get("detector_size", options.get("detector_size", "")),
            "detect_every_n": payload.get("detect_every_n", options.get("detect_every_n", "")),
            "face_model_pack": payload.get("face_model_pack", ""),
            "swapper_precision": payload.get("swapper_precision", ""),
            "swapper_loaded_precision": payload.get("swapper_loaded_precision", ""),
            "cache_source_face": payload.get("cache_source_face", ""),
            "pipeline_frames": int(window.live_pipeline_frames.value()) if hasattr(window, "live_pipeline_frames") else "",
            "max_width": options.get("max_width", ""),
            "input": payload.get("input", ""),
            "processing": payload.get("processing", ""),
            "frame_seq": payload.get("frame_seq", ""),
            "server_queue_ms": payload.get("server_queue_ms", ""),
            "client_to_server_ms": payload.get("client_to_server_ms", ""),
            "capture_to_server_ms": payload.get("capture_to_server_ms", ""),
            "receive_to_send_ms": payload.get("receive_to_send_ms", ""),
            "latest_drop_count": payload.get("latest_drop_count", ""),
            "frames_dropped_before_process": payload.get("frames_dropped_before_process", ""),
            "server_decode_to_process_ms": payload.get("server_decode_to_process_ms", ""),
            "server_process_to_encode_ms": payload.get("server_process_to_encode_ms", ""),
            "backend_json": json.dumps(payload, sort_keys=True),
            "client_json": json.dumps(client_payload, sort_keys=True) if client_payload else "",
            "receiver_json": json.dumps(receiver_payload, sort_keys=True) if receiver_payload else "",
        }
    )
    backend_keys = (
        "server_fps",
        "wait_ms",
        "decode_ms",
        "resize_ms",
        "process_ms",
        "detect_ms",
        "landmarks_ms",
        "swap_ms",
        "source_refresh_ms",
        "face_swap_ms",
        "post_ms",
        "enhance_ms",
        "encode_ms",
        "in_kb",
        "out_kb",
        "detect_reuse_pct",
        "faces",
    )
    for key in backend_keys:
        if key in payload:
            row[key] = payload[key]
    client_map = {
        "client_fps": "client_fps",
        "capture_read_ms": "capture_read_ms",
        "capture_wait_ms": "capture_wait_ms",
        "capture_grab_ms": "capture_grab_ms",
        "capture_retrieve_ms": "capture_retrieve_ms",
        "capture_age_ms": "capture_age_ms",
        "capture_thread_fps": "capture_thread_fps",
        "dropped_capture_frames": "dropped_capture_frames",
        "duplicate_sender_frames": "duplicate_sender_frames",
        "capture_seq": "capture_seq",
        "resize_ms": "client_resize_ms",
        "encode_ms": "client_encode_ms",
        "send_ms": "send_ms",
        "backpressure_ms": "backpressure_ms",
        "sent_kb": "sent_kb",
        "frame_width": "client_frame_width",
        "frame_height": "client_frame_height",
        "in_flight": "client_in_flight",
        "pipeline_frames": "client_pipeline_frames",
        "frame_codec": "client_frame_codec",
        "jpeg_quality": "client_jpeg_quality",
        "capture_scale": "client_capture_scale",
    }
    for source, target in client_map.items():
        if source in client_payload:
            row[target] = client_payload[source]
    receiver_map = {
        "receiver_fps": "receiver_fps",
        "decode_ms": "receiver_decode_ms",
        "virtual_send_ms": "virtual_send_ms",
    }
    for source, target in receiver_map.items():
        if source in receiver_payload:
            row[target] = receiver_payload[source]
    return row


def _record_live_perf_sample(window: MainWindow, payload: dict[str, Any]) -> None:
    if not getattr(window, "_live_perf_test_running", False):
        return
    output_path = getattr(window, "_live_perf_output_path", None)
    if not output_path:
        return
    row = _live_perf_csv_row(window, payload)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not bool(getattr(window, "_live_perf_csv_initialized", False)) or not output_path.exists()
    with output_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(LIVE_PERF_CSV_COLUMNS))
        if write_header:
            writer.writeheader()
            window._live_perf_csv_initialized = True
        writer.writerow(row)


def _handle_live_worker_message(window: MainWindow, text: str) -> None:
    ui_base._poll_message(window, "live", text)
    payload = _json_payload(text)
    status = payload.get("status")
    if status == "live_perf":
        _record_live_perf_sample(window, payload)
    elif status == "live_client_perf":
        window._live_latest_client_perf = payload
    elif status == "live_receiver_perf":
        window._live_latest_receiver_perf = payload


def _apply_live_hot_change(self: MainWindow) -> None:
    if not hasattr(self, "live_preview_buffer_seconds"):
        return
    self.settings.live_pipeline_frames = int(self.live_pipeline_frames.value())
    self.settings.live_options = _read_live_options(self)
    processing_options_base.save_settings(self.settings)
    self._live_preview_buffer_seconds = float(self.settings.live_options["preview_buffer_seconds"])
    worker = getattr(self, "live_worker", None)
    if worker is None or not worker.isRunning():
        return
    payload = _live_hot_change_payload(self)
    updater = getattr(worker, "update_live_config", None)
    if callable(updater):
        updater(payload)
        ui_base._set_process_status(self, "live", "Live settings update queued")


def _connect_live_hot_change_controls(window: MainWindow) -> None:
    if getattr(window, "_live_hot_change_controls_connected", False):
        return

    def changed(*_args: object) -> None:
        timer = getattr(window, "_live_hot_change_timer", None)
        if timer is not None:
            timer.start()
        else:
            _apply_live_hot_change(window)

    def mode_changed(*_args: object) -> None:
        _update_capture_custom_controls(window)

    for widget in (
        window.live_many_faces,
        window.live_poisson_blend,
        window.live_color_correction,
    ):
        widget.stateChanged.connect(changed)
    for widget in (
        window.live_frame_codec,
        window.live_output_codec,
    ):
        widget.currentTextChanged.connect(changed)
    window.live_capture_scale.currentTextChanged.connect(changed)
    window.live_capture_mode.currentTextChanged.connect(mode_changed)
    for widget in (
        window.live_opacity,
        window.live_sharpness,
        window.live_mouth_mask_size,
        window.live_interpolation_weight,
        window.live_max_width,
        window.live_jpeg_quality,
        window.live_detector_size,
        window.live_detect_every_n,
        window.live_preview_buffer_seconds,
        window.live_pipeline_frames,
    ):
        widget.valueChanged.connect(changed)
    window._live_hot_change_controls_connected = True


def load_settings() -> AppSettings:
    settings = processing_options_base.load_settings()
    data: dict[str, Any] = {}
    if APP_STATE.is_file():
        try:
            loaded = json.loads(APP_STATE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}
    settings.live_width = int(data.get("live_width") or DEFAULT_LIVE_WIDTH)
    settings.live_height = int(data.get("live_height") or DEFAULT_LIVE_HEIGHT)
    settings.live_fps = int(data.get("live_fps") or DEFAULT_LIVE_FPS)
    settings.live_pipeline_frames = int(data.get("live_pipeline_frames") or DEFAULT_LIVE_PIPELINE_FRAMES)
    settings.live_options = _coerce_live_options(data.get("live_options"))
    # Migrate the short-lived auto + half-send default that let OBS/OpenCV negotiate
    # 640x480 and then sent 320x240. Auto now requests the OBS profile size when
    # it is available, while Send scale should preserve the received frame.
    if isinstance(data.get("live_options"), dict):
        raw_options = data["live_options"]
        if raw_options.get("capture_mode") == "auto" and raw_options.get("capture_scale") == "1/2x":
            settings.live_options["capture_backend"] = DEFAULT_LIVE_CAPTURE_BACKEND
            settings.live_options["capture_scale"] = DEFAULT_LIVE_CAPTURE_SCALE
    return settings


def save_settings(settings: AppSettings) -> None:
    processing_options_base.save_settings(settings)
    try:
        data = json.loads(APP_STATE.read_text(encoding="utf-8")) if APP_STATE.is_file() else {}
        if not isinstance(data, dict):
            data = {}
        data["live_width"] = _live_setting(settings, "live_width", DEFAULT_LIVE_WIDTH)
        data["live_height"] = _live_setting(settings, "live_height", DEFAULT_LIVE_HEIGHT)
        data["live_fps"] = _live_setting(settings, "live_fps", DEFAULT_LIVE_FPS)
        data["live_pipeline_frames"] = _live_setting(settings, "live_pipeline_frames", DEFAULT_LIVE_PIPELINE_FRAMES)
        data["live_options"] = _live_options(settings)
        APP_STATE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def _build_live_tab(self: MainWindow) -> None:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    splitter = QSplitter(Qt.Horizontal)

    controls_panel = QWidget()
    controls_layout = QVBoxLayout(controls_panel)
    form = QFormLayout()

    self.camera_index = QSpinBox()
    self.camera_index.setRange(0, 20)
    self.camera_index.setValue(self.settings.camera_index)
    self.virtual_camera = QLineEdit(self.settings.virtual_camera)
    self.live_source_face = QLineEdit(self.settings.source_face)
    live_source_row = QHBoxLayout()
    live_source_row.addWidget(self.live_source_face)
    self.live_source_browse = QPushButton("Browse...")
    self.live_source_browse.clicked.connect(lambda: self._browse_file(self.live_source_face, "Select source face image"))
    live_source_row.addWidget(self.live_source_browse)
    self.live_capture_backend = QComboBox()
    self.live_capture_backend.addItems(list(LIVE_CAPTURE_BACKENDS))
    self.live_capture_backend.setToolTip(
        "OpenCV capture backend. DirectShow is recommended for OBS Virtual Camera custom resolutions on Windows."
    )
    self.live_capture_mode = QComboBox()
    self.live_capture_mode.addItems(list(LIVE_CAPTURE_MODES))
    self.live_capture_mode.setToolTip(
        "Auto requests the current OBS profile canvas size when available, opencv_auto lets OpenCV negotiate, and custom forces the width/height below."
    )
    self.live_capture_width = QSpinBox()
    self.live_capture_width.setRange(2, 4096)
    self.live_capture_width.setSingleStep(2)
    self.live_capture_height = QSpinBox()
    self.live_capture_height.setRange(2, 4096)
    self.live_capture_height.setSingleStep(2)
    self.live_capture_scale = QComboBox()
    self.live_capture_scale.addItems(list(LIVE_CAPTURE_SCALES))
    self.live_capture_scale.setToolTip(
        "Resize the actual decoded webcam frame before sending it. Auto/1x send the actual frame size."
    )
    self.live_fps = QSpinBox()
    self.live_fps.setRange(1, 120)
    self.live_fps.setValue(_live_setting(self.settings, "live_fps", DEFAULT_LIVE_FPS))
    self.live_pipeline_frames = QSpinBox()
    self.live_pipeline_frames.setRange(8, 512)
    self.live_pipeline_frames.setValue(_live_setting(self.settings, "live_pipeline_frames", DEFAULT_LIVE_PIPELINE_FRAMES))

    form.addRow("Camera index", self.camera_index)
    form.addRow("Virtual camera", self.virtual_camera)
    form.addRow("Source face path", live_source_row)
    form.addRow("Capture backend", self.live_capture_backend)
    form.addRow("Capture mode", self.live_capture_mode)
    form.addRow("Custom capture width", self.live_capture_width)
    form.addRow("Custom capture height", self.live_capture_height)
    form.addRow("Send scale", self.live_capture_scale)
    form.addRow("Capture FPS", self.live_fps)
    form.addRow("Pipeline frames", self.live_pipeline_frames)
    controls_layout.addLayout(form)
    _link_live_source_fields(self)

    options_box = QGroupBox("Live processing options")
    options_form = QFormLayout(options_box)
    self.live_many_faces = QCheckBox()
    self.live_enhancer = QComboBox()
    self.live_enhancer.addItems(["none", "gfpgan", "gpen256", "gpen512"])
    self.live_opacity = QDoubleSpinBox()
    self.live_opacity.setRange(0.0, 1.0)
    self.live_opacity.setSingleStep(0.1)
    self.live_sharpness = QDoubleSpinBox()
    self.live_sharpness.setRange(0.0, 1.0)
    self.live_sharpness.setSingleStep(0.1)
    self.live_mouth_mask_size = QDoubleSpinBox()
    self.live_mouth_mask_size.setRange(0.0, 10.0)
    self.live_mouth_mask_size.setSingleStep(0.5)
    self.live_interpolation_weight = QDoubleSpinBox()
    self.live_interpolation_weight.setRange(0.0, 1.0)
    self.live_interpolation_weight.setSingleStep(0.1)
    self.live_poisson_blend = QCheckBox()
    self.live_color_correction = QCheckBox()
    self.live_max_width = QSpinBox()
    self.live_max_width.setRange(64, 4096)
    self.live_frame_codec = QComboBox()
    self.live_frame_codec.addItems(list(LIVE_FRAME_CODECS))
    self.live_frame_codec.setToolTip("Codec used for webcam frames sent to the Colab live websocket. WebP can reduce in_kb when OpenCV supports it.")
    self.live_output_codec = QComboBox()
    self.live_output_codec.addItems(list(LIVE_FRAME_CODECS))
    self.live_output_codec.setToolTip("Codec used by the Colab server for frames returned to preview/virtual camera. JPEG is safest; WebP may reduce out_kb.")
    self.live_jpeg_quality = QSpinBox()
    self.live_jpeg_quality.setRange(20, 95)
    self.live_detector_size = QSpinBox()
    self.live_detector_size.setRange(160, 640)
    self.live_detector_size.setSingleStep(32)
    self.live_detect_every_n = QSpinBox()
    self.live_detect_every_n.setRange(1, 30)
    self.live_face_model_pack = QComboBox()
    self.live_face_model_pack.addItems(list(LIVE_FACE_MODEL_PACKS))
    self.live_face_model_pack.setToolTip(
        "buffalo_l is safest for inswapper_128; buffalo_m/s are experimental speed options. "
        "Use Swapper precision to compare fp32 vs fp16 swap_ms."
    )
    self.live_swapper_precision = QComboBox()
    self.live_swapper_precision.addItems(list(LIVE_SWAPPER_PRECISIONS))
    self.live_swapper_precision.setToolTip("Use fp32 as baseline; choose fp16 to test T4/RTX swap_ms.")
    self.live_cache_source_face = QCheckBox()
    self.live_cache_source_face.setToolTip("Keep on for speed. Turn off to re-read/re-analyze the source face each frame if a source swap looks stale.")
    self.live_preview_buffer_seconds = QDoubleSpinBox()
    self.live_preview_buffer_seconds.setRange(0.0, 5.0)
    self.live_preview_buffer_seconds.setSingleStep(0.25)
    self.live_preview_buffer_seconds.setDecimals(2)
    self.live_preview_buffer_seconds.setToolTip("Delay preview by this many seconds so frames can render at an even cadence.")
    self._live_hot_change_timer = QTimer(self)
    self._live_hot_change_timer.setSingleShot(True)
    self._live_hot_change_timer.setInterval(200)
    self._live_hot_change_timer.timeout.connect(lambda: _apply_live_hot_change(self))

    options_form.addRow("Many faces", self.live_many_faces)
    options_form.addRow("Enhancer", self.live_enhancer)
    options_form.addRow("Opacity (1=full)", self.live_opacity)
    options_form.addRow("Sharpness (0=off)", self.live_sharpness)
    options_form.addRow("Mouth mask (0=off)", self.live_mouth_mask_size)
    options_form.addRow("Interpolation (0=off)", self.live_interpolation_weight)
    options_form.addRow("Poisson blend", self.live_poisson_blend)
    options_form.addRow("Color correction", self.live_color_correction)
    options_form.addRow("Process max width", self.live_max_width)
    options_form.addRow("Send codec", self.live_frame_codec)
    options_form.addRow("Return codec", self.live_output_codec)
    options_form.addRow("Frame quality", self.live_jpeg_quality)
    options_form.addRow("Detector size", self.live_detector_size)
    options_form.addRow("Detect every N frames", self.live_detect_every_n)
    options_form.addRow("InsightFace pack", self.live_face_model_pack)
    options_form.addRow("Swapper precision", self.live_swapper_precision)
    options_form.addRow("Cache source face", self.live_cache_source_face)
    options_form.addRow("Preview buffer seconds", self.live_preview_buffer_seconds)
    _apply_live_options_to_widgets(self)
    _update_capture_custom_controls(self)
    _connect_live_hot_change_controls(self)
    controls_layout.addWidget(options_box)

    row = QHBoxLayout()
    self.live_start_btn = QPushButton("Start live")
    self.live_start_btn.setObjectName("successButton")
    self.live_stop_btn = QPushButton("Stop live")
    self.live_stop_btn.setObjectName("dangerButton")
    self.live_start_btn.clicked.connect(self.start_live)
    self.live_stop_btn.clicked.connect(self.stop_live)
    self.live_stop_btn.setEnabled(False)
    self.live_perf_test_btn = QPushButton("Run perf test")
    self.live_perf_test_btn.clicked.connect(lambda: _toggle_live_perf_test(self))
    self.live_perf_test_btn.setEnabled(False)
    row.addWidget(self.live_start_btn)
    row.addWidget(self.live_stop_btn)
    row.addWidget(self.live_perf_test_btn)
    row.addStretch(1)
    controls_layout.addLayout(row)

    self.live_status = _status_label("Idle")
    controls_layout.addWidget(self.live_status)
    self.live_note = _status_label(
        "Live sends webcam JPEG/WebP frames to ws://HOST:PORT/ws/live and previews returned frames. "
        "buffalo_l is safest for inswapper_128; buffalo_m/s are experimental speed options. "
        "Use Swapper precision to compare fp32 vs fp16 swap_ms."
    )
    controls_layout.addWidget(self.live_note)
    self.live_restart_note = _status_label(
        "Live is running: camera, source, capture backend/size/FPS, enhancer, InsightFace pack, swapper precision, "
        "and source-cache controls are restart-only and temporarily disabled."
    )
    self.live_restart_note.setVisible(False)
    controls_layout.addWidget(self.live_restart_note)
    controls_layout.addStretch(1)

    controls_scroll = QScrollArea()
    controls_scroll.setWidgetResizable(True)
    controls_scroll.setMinimumWidth(260)
    controls_scroll.setWidget(controls_panel)
    splitter.addWidget(controls_scroll)

    preview_panel = QWidget()
    preview_layout = QVBoxLayout(preview_panel)
    preview_controls = QHBoxLayout()
    preview_controls.addWidget(QLabel("Preview size"))
    self.live_preview_scale = QComboBox()
    self.live_preview_scale.addItems(list(LIVE_PREVIEW_SCALES))
    self.live_preview_scale.setCurrentText(str(_live_options(self.settings)["preview_scale"]))
    self.live_preview_scale.setToolTip("Fit fills the panel. 1x/1.5x/2x use that pixel scale only when it fits; otherwise they fall back to fit.")
    self.live_preview_scale.currentTextChanged.connect(
        lambda _text: (self.update_live_preview_from_last_frame(), _apply_live_hot_change(self))
    )
    preview_controls.addWidget(self.live_preview_scale)
    preview_controls.addStretch(1)
    preview_layout.addLayout(preview_controls)
    self.live_preview = QLabel("Live preview")
    self.live_preview.setAlignment(Qt.AlignCenter)
    self.live_preview.setMinimumSize(320, 240)
    self.live_preview.setWordWrap(True)
    preview_layout.addWidget(self.live_preview, 1)
    self._live_latest_jpeg = None
    self._live_preview_buffer = deque()
    self._live_preview_buffer_seconds = DEFAULT_LIVE_PREVIEW_BUFFER_SECONDS
    self._live_preview_frames = 0
    self._live_preview_last_frame = None
    self._live_preview_timer = QTimer(self)
    self._live_preview_timer.timeout.connect(lambda: live_preview.render_live_preview_frame(self))
    splitter.addWidget(preview_panel)

    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)
    splitter.setSizes([360, 900])
    layout.addWidget(splitter, 1)
    self.tabs.addTab(tab, "Live")


def sync_settings(self: MainWindow) -> None:
    processing_options_base.sync_settings(self)
    if hasattr(self, "live_source_face"):
        self.settings.source_face = self.live_source_face.text().strip()
    if hasattr(self, "live_width"):
        self.settings.live_width = int(self.live_width.value())
    else:
        self.settings.live_width = _live_setting(self.settings, "live_width", DEFAULT_LIVE_WIDTH)
    if hasattr(self, "live_height"):
        self.settings.live_height = int(self.live_height.value())
    else:
        self.settings.live_height = _live_setting(self.settings, "live_height", DEFAULT_LIVE_HEIGHT)
    if hasattr(self, "live_fps"):
        self.settings.live_fps = int(self.live_fps.value())
    else:
        self.settings.live_fps = _live_setting(self.settings, "live_fps", DEFAULT_LIVE_FPS)
    if hasattr(self, "live_pipeline_frames"):
        self.settings.live_pipeline_frames = int(self.live_pipeline_frames.value())
    else:
        self.settings.live_pipeline_frames = _live_setting(self.settings, "live_pipeline_frames", DEFAULT_LIVE_PIPELINE_FRAMES)
    self.settings.live_options = _read_live_options(self)
    processing_options_base.save_settings(self.settings)


def closeEvent(self: MainWindow, event: Any) -> None:
    try:
        self.sync_settings()
    except Exception as exc:
        self.log(f"settings save on close failed: {exc}")
    live_preview.stop_live_preview_timer(self)
    MainWindow.closeEvent(self, event)


def _prepare_live_settings(settings: AppSettings) -> dict[str, Any]:
    client = ApiClient(settings)
    logs: list[str] = ["checking Colab API before starting live"]
    client.request_json("GET", "/health", timeout=5.0)

    live_settings = output_tasks_base._copy_settings(settings)
    live_settings.live_width = _live_setting(settings, "live_width", DEFAULT_LIVE_WIDTH)
    live_settings.live_height = _live_setting(settings, "live_height", DEFAULT_LIVE_HEIGHT)
    live_settings.live_fps = _live_setting(settings, "live_fps", DEFAULT_LIVE_FPS)
    live_settings.live_pipeline_frames = _live_setting(settings, "live_pipeline_frames", DEFAULT_LIVE_PIPELINE_FRAMES)
    live_settings.live_options = _live_options(settings)
    _apply_live_options_to_settings(live_settings)
    source_face = live_settings.source_face
    logs.append(f"live source face path: {source_face or '(empty)'}")
    if is_local_path(source_face):
        source_path = Path(source_face)
        if not source_path.is_file():
            raise FileNotFoundError(f"Local source face does not exist: {source_face}")
        upload_path, normalization_log = output_tasks_base._source_upload_path(source_path)
        if normalization_log:
            logs.append(normalization_log)
        logs.append(f"uploading local source face for live: {source_path}")
        response = client.upload_file("/upload/file?kind=source", upload_path, timeout=30.0)
        live_settings.source_face = str(response.get("path") or source_face)
        logs.append(f"live source uploaded to: {live_settings.source_face}")
    else:
        logs.append(f"using remote source face for live: {source_face}")

    return {"settings": live_settings, "logs": logs}


class LiveWorker(BaseLiveWorker):
    def __init__(self, settings: AppSettings):
        super().__init__(settings)
        self._live_config_updates: queue.Queue[dict[str, Any]] = queue.Queue()
        self._runtime_config_lock = threading.Lock()
        live_options = _live_options(settings)
        self._runtime_config = {
            **_live_hot_change_payload_from_settings(settings),
            "capture_backend": live_options["capture_backend"],
            "capture_mode": live_options["capture_mode"],
            "capture_width": live_options["capture_width"],
            "capture_height": live_options["capture_height"],
            "live_pipeline_frames": _live_setting(settings, "live_pipeline_frames", DEFAULT_LIVE_PIPELINE_FRAMES),
        }

    def update_live_config(self, payload: dict[str, Any]) -> None:
        next_payload = dict(payload)
        with self._runtime_config_lock:
            self._runtime_config.update(next_payload)
        self._live_config_updates.put(next_payload)

    def _runtime_value(self, name: str, default: Any) -> Any:
        with self._runtime_config_lock:
            return self._runtime_config.get(name, default)

    def _drain_live_config_updates(self) -> list[dict[str, Any]]:
        updates = []
        while True:
            try:
                payload = self._live_config_updates.get_nowait()
            except queue.Empty:
                break
            with self._runtime_config_lock:
                self._runtime_config.update(payload)
                updates.append(dict(payload))
        return updates

    async def _run_live(self) -> None:
        import cv2
        import websockets

        uri = self.settings.base_url.replace("http://", "ws://") + "/ws/live"
        self.message.emit(f"connecting live websocket: {uri}")
        capture_backend = str(self._runtime_value("capture_backend", DEFAULT_LIVE_CAPTURE_BACKEND)).lower()
        if capture_backend not in LIVE_CAPTURE_BACKENDS:
            capture_backend = DEFAULT_LIVE_CAPTURE_BACKEND
        cap = _open_video_capture(cv2, self.settings.camera_index, capture_backend)
        if not cap.isOpened():
            raise RuntimeError(f"could not open camera index {self.settings.camera_index} with backend {capture_backend}")
        try:
            buffer_set = bool(cap.set(cv2.CAP_PROP_BUFFERSIZE, 1))
            buffer_size = cap.get(cv2.CAP_PROP_BUFFERSIZE)
            self.message.emit(f"capture buffer request: set=1 accepted={buffer_set}, actual={buffer_size:g}")
        except Exception:
            pass
        requested_width = int(self._runtime_value("capture_width", DEFAULT_LIVE_CAPTURE_WIDTH))
        requested_height = int(self._runtime_value("capture_height", DEFAULT_LIVE_CAPTURE_HEIGHT))
        capture_mode = str(self._runtime_value("capture_mode", DEFAULT_LIVE_CAPTURE_MODE)).lower()
        if capture_mode not in LIVE_CAPTURE_MODES:
            capture_mode = DEFAULT_LIVE_CAPTURE_MODE
        requested_fps = _live_setting(self.settings, "live_fps", DEFAULT_LIVE_FPS)
        pipeline_frames = _live_setting(self.settings, "live_pipeline_frames", DEFAULT_LIVE_PIPELINE_FRAMES)
        capture_scale = str(self._runtime_value("capture_scale", DEFAULT_LIVE_CAPTURE_SCALE)).lower()
        if capture_scale not in LIVE_CAPTURE_SCALES:
            capture_scale = DEFAULT_LIVE_CAPTURE_SCALE
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        auto_capture_source = ""
        if capture_mode == "custom":
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, requested_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, requested_height)
        elif capture_mode == "auto":
            detected = _detect_obs_profile_resolution()
            if detected is not None:
                requested_width, requested_height, auto_capture_source = detected
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, requested_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, requested_height)
                self.message.emit(
                    f"capture auto requested {requested_width}x{requested_height} from {auto_capture_source}"
                )
        cap.set(cv2.CAP_PROP_FPS, requested_fps)
        first_frame = _read_warm_camera_frame(cap, attempts=20)
        actual_height, actual_width = first_frame.shape[:2]
        if capture_mode == "auto" and auto_capture_source:
            if (actual_width, actual_height) != (requested_width, requested_height):
                self.message.emit(
                    f"warning: OBS profile says {requested_width}x{requested_height}, "
                    f"but OpenCV received {actual_width}x{actual_height}; check OBS Virtual Camera backend/settings"
                )
        elif capture_mode == "auto":
            self.message.emit(
                f"capture auto negotiated {actual_width}x{actual_height}; "
                "OBS profile size was not found; use Capture mode=custom if OBS canvas is different"
            )
        if capture_mode == "custom" and (actual_width, actual_height) != (requested_width, requested_height):
            self.message.emit(
                f"warning: requested OBS capture {requested_width}x{requested_height} with {capture_backend}, "
                f"but OpenCV received {actual_width}x{actual_height}; try DirectShow backend or check OBS output/canvas"
            )
        actual_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        with self._runtime_config_lock:
            initial_capture_config = dict(self._runtime_config)
        send_width, send_height = _capture_target_size(first_frame, initial_capture_config)
        preferred = (
            f"{requested_width}x{requested_height}"
            if capture_mode == "custom" or auto_capture_source
            else "auto"
        )
        self.message.emit(
            f"webcam capture: backend {capture_backend}, preferred {preferred}@{requested_fps}, "
            f"actual {actual_width}x{actual_height}@{actual_fps:.1f}, "
            f"send {send_width}x{send_height} ({capture_scale}), pipeline {pipeline_frames}"
        )
        virtual_cam = None
        virtual_cam_size: tuple[int, int] | None = None
        frame_codec = str(self._runtime_value("frame_codec", DEFAULT_LIVE_FRAME_CODEC)).lower()
        if frame_codec not in LIVE_FRAME_CODECS:
            frame_codec = DEFAULT_LIVE_FRAME_CODEC
        output_codec = str(self._runtime_value("output_codec", DEFAULT_LIVE_OUTPUT_CODEC)).lower()
        if output_codec not in LIVE_FRAME_CODECS:
            output_codec = DEFAULT_LIVE_OUTPUT_CODEC
        frame_quality = int(self._runtime_value("jpeg_quality", DEFAULT_LIVE_JPEG_QUALITY))
        self.message.emit(f"live frame codec: send={frame_codec}, return={output_codec}, quality={frame_quality}")
        clock = asyncio.get_running_loop().time
        stats_started = clock()
        stats_frames = 0
        receiver_decode_ms = 0.0
        virtual_send_ms = 0.0
        in_flight = 0
        condition = asyncio.Condition()
        capture_stop = threading.Event()
        capture_lock = threading.Lock()
        capture_condition = threading.Condition(capture_lock)
        capture_error: BaseException | None = None
        latest_capture: dict[str, Any] = {
            "frame": first_frame,
            "seq": 0,
            "captured_at": time.perf_counter(),
            "captured_wall_time": time.time(),
            "grab_ms": 0.0,
            "retrieve_ms": 0.0,
        }
        capture_stats: dict[str, Any] = {
            "started": time.perf_counter(),
            "frames": 0,
            "grab_ms": 0.0,
            "retrieve_ms": 0.0,
        }
        client_stats: dict[str, Any] = {
            "started": clock(),
            "frames": 0,
            "capture_read_ms": 0.0,
            "capture_wait_ms": 0.0,
            "capture_grab_ms": 0.0,
            "capture_retrieve_ms": 0.0,
            "capture_age_ms": 0.0,
            "dropped_capture_frames": 0,
            "duplicate_sender_frames": 0,
            "capture_seq": 0,
            "resize_ms": 0.0,
            "encode_ms": 0.0,
            "send_ms": 0.0,
            "backpressure_ms": 0.0,
            "sent_kb": 0.0,
            "frame_width": send_width,
            "frame_height": send_height,
            "frame_codec": frame_codec,
            "jpeg_quality": frame_quality,
            "capture_scale": capture_scale,
        }

        def capture_loop() -> None:
            nonlocal capture_error
            seq = 0
            while not self._stop and not capture_stop.is_set():
                try:
                    grab_started = time.perf_counter()
                    ok = cap.grab()
                    grab_ms = (time.perf_counter() - grab_started) * 1000.0
                    if not ok:
                        time.sleep(0.005)
                        continue
                    retrieve_started = time.perf_counter()
                    ok, frame = cap.retrieve()
                    retrieve_ms = (time.perf_counter() - retrieve_started) * 1000.0
                    if not ok or frame is None:
                        time.sleep(0.005)
                        continue
                    captured_at = time.perf_counter()
                    captured_wall_time = time.time()
                    with capture_condition:
                        seq += 1
                        latest_capture.update(
                            {
                                "frame": frame,
                                "seq": seq,
                                "captured_at": captured_at,
                                "captured_wall_time": captured_wall_time,
                                "grab_ms": grab_ms,
                                "retrieve_ms": retrieve_ms,
                            }
                        )
                        capture_stats["frames"] = int(capture_stats["frames"]) + 1
                        capture_stats["grab_ms"] = float(capture_stats["grab_ms"]) + grab_ms
                        capture_stats["retrieve_ms"] = float(capture_stats["retrieve_ms"]) + retrieve_ms
                        capture_condition.notify_all()
                except BaseException as exc:
                    capture_error = exc
                    with capture_condition:
                        capture_condition.notify_all()
                    return

        capture_thread = threading.Thread(target=capture_loop, name="LiveCaptureReader", daemon=True)
        capture_thread.start()

        def add_client_stat(name: str, value: float) -> None:
            client_stats[name] = float(client_stats.get(name, 0.0)) + float(value)

        def add_client_count(name: str, value: int) -> None:
            client_stats[name] = int(client_stats.get(name, 0)) + int(value)

        def capture_thread_perf() -> dict[str, Any]:
            now = time.perf_counter()
            with capture_condition:
                elapsed = max(0.001, now - float(capture_stats["started"]))
                frames = int(capture_stats["frames"])
                payload = {
                    "capture_thread_fps": round(frames / elapsed, 2),
                    "capture_grab_ms": round(float(capture_stats["grab_ms"]) / max(1, frames), 2),
                    "capture_retrieve_ms": round(float(capture_stats["retrieve_ms"]) / max(1, frames), 2),
                }
                capture_stats.update(
                    {
                        "started": now,
                        "frames": 0,
                        "grab_ms": 0.0,
                        "retrieve_ms": 0.0,
                    }
                )
                return payload

        def emit_client_perf(now: float, current_pipeline_frames: int, current_in_flight: int) -> None:
            elapsed = max(0.001, now - float(client_stats["started"]))
            frames = max(1, int(client_stats["frames"]))
            payload = {
                "status": "live_client_perf",
                "client_fps": round(float(client_stats["frames"]) / elapsed, 2),
                "capture_read_ms": round(float(client_stats["capture_read_ms"]) / frames, 2),
                "capture_wait_ms": round(float(client_stats["capture_wait_ms"]) / frames, 2),
                "capture_grab_ms": round(float(client_stats["capture_grab_ms"]) / frames, 2),
                "capture_retrieve_ms": round(float(client_stats["capture_retrieve_ms"]) / frames, 2),
                "capture_age_ms": round(float(client_stats["capture_age_ms"]) / frames, 2),
                "resize_ms": round(float(client_stats["resize_ms"]) / frames, 2),
                "encode_ms": round(float(client_stats["encode_ms"]) / frames, 2),
                "send_ms": round(float(client_stats["send_ms"]) / frames, 2),
                "backpressure_ms": round(float(client_stats["backpressure_ms"]) / frames, 2),
                "sent_kb": round(float(client_stats["sent_kb"]) / frames, 2),
                "dropped_capture_frames": int(client_stats.get("dropped_capture_frames") or 0),
                "duplicate_sender_frames": int(client_stats.get("duplicate_sender_frames") or 0),
                "capture_seq": int(client_stats.get("capture_seq") or 0),
                "frame_width": int(client_stats.get("frame_width") or 0),
                "frame_height": int(client_stats.get("frame_height") or 0),
                "frame_codec": client_stats.get("frame_codec", ""),
                "jpeg_quality": int(client_stats.get("jpeg_quality") or 0),
                "capture_scale": client_stats.get("capture_scale", ""),
                "pipeline_frames": int(current_pipeline_frames),
                "in_flight": int(current_in_flight),
            }
            payload.update(capture_thread_perf())
            self.message.emit(json.dumps(payload))
            client_stats.update(
                {
                    "started": now,
                    "frames": 0,
                    "capture_read_ms": 0.0,
                    "capture_wait_ms": 0.0,
                    "capture_grab_ms": 0.0,
                    "capture_retrieve_ms": 0.0,
                    "capture_age_ms": 0.0,
                    "dropped_capture_frames": 0,
                    "duplicate_sender_frames": 0,
                    "resize_ms": 0.0,
                    "encode_ms": 0.0,
                    "send_ms": 0.0,
                    "backpressure_ms": 0.0,
                    "sent_kb": 0.0,
                }
            )

        async def sender(websocket: Any) -> None:
            nonlocal in_flight
            last_sent_capture_seq = -1
            while not self._stop:
                for update in self._drain_live_config_updates():
                    server_update = {key: update[key] for key in LIVE_HOT_CHANGE_KEYS if key in update}
                    if server_update:
                        await websocket.send(json.dumps({"type": "live_config_update", "config": server_update}))
                backpressure_started = clock()
                async with condition:
                    current_pipeline_frames = max(1, int(self._runtime_value("live_pipeline_frames", pipeline_frames)))
                    while in_flight >= current_pipeline_frames and not self._stop:
                        try:
                            await asyncio.wait_for(condition.wait(), timeout=0.1)
                        except asyncio.TimeoutError:
                            pass
                        current_pipeline_frames = max(1, int(self._runtime_value("live_pipeline_frames", pipeline_frames)))
                    if self._stop:
                        break
                    in_flight += 1
                add_client_stat("backpressure_ms", (clock() - backpressure_started) * 1000.0)
                try:
                    capture_wait_started = time.perf_counter()
                    with capture_condition:
                        while latest_capture["seq"] == last_sent_capture_seq and not self._stop and capture_error is None:
                            capture_condition.wait(timeout=0.1)
                        if capture_error is not None:
                            raise RuntimeError(f"live capture reader failed: {capture_error}") from capture_error
                        if self._stop:
                            break
                        frame = latest_capture["frame"]
                        capture_seq = int(latest_capture["seq"])
                        captured_at = float(latest_capture["captured_at"])
                        captured_wall_time = float(latest_capture.get("captured_wall_time") or 0.0)
                        capture_grab_ms = float(latest_capture["grab_ms"])
                        capture_retrieve_ms = float(latest_capture["retrieve_ms"])
                    if frame is None:
                        async with condition:
                            in_flight = max(0, in_flight - 1)
                            condition.notify_all()
                        await asyncio.sleep(0.03)
                        continue
                    capture_wait_ms = (time.perf_counter() - capture_wait_started) * 1000.0
                    duplicate_sender_frames = 1 if capture_seq == last_sent_capture_seq else 0
                    dropped_capture_frames = (
                        max(0, capture_seq - last_sent_capture_seq - 1)
                        if last_sent_capture_seq >= 0 and duplicate_sender_frames == 0
                        else 0
                    )
                    last_sent_capture_seq = capture_seq
                    capture_age_ms = max(0.0, (time.perf_counter() - captured_at) * 1000.0)
                    add_client_stat("capture_read_ms", capture_wait_ms)
                    add_client_stat("capture_wait_ms", capture_wait_ms)
                    add_client_stat("capture_grab_ms", capture_grab_ms)
                    add_client_stat("capture_retrieve_ms", capture_retrieve_ms)
                    add_client_stat("capture_age_ms", capture_age_ms)
                    add_client_count("dropped_capture_frames", dropped_capture_frames)
                    add_client_count("duplicate_sender_frames", duplicate_sender_frames)
                    client_stats["capture_seq"] = capture_seq
                    with self._runtime_config_lock:
                        capture_config = dict(self._runtime_config)
                    current_capture_scale = str(capture_config.get("capture_scale", capture_scale)).lower()
                    if current_capture_scale not in LIVE_CAPTURE_SCALES:
                        capture_config["capture_scale"] = DEFAULT_LIVE_CAPTURE_SCALE
                    resize_started = clock()
                    frame = _resize_for_capture_config(frame, capture_config, cv2)
                    add_client_stat("resize_ms", (clock() - resize_started) * 1000.0)
                    current_frame_codec = str(self._runtime_value("frame_codec", frame_codec)).lower()
                    if current_frame_codec not in LIVE_FRAME_CODECS:
                        current_frame_codec = DEFAULT_LIVE_FRAME_CODEC
                    current_frame_quality = int(self._runtime_value("jpeg_quality", frame_quality))
                    encode_ext = ".webp" if current_frame_codec == "webp" else ".jpg"
                    encode_flag = int(getattr(cv2, "IMWRITE_WEBP_QUALITY", cv2.IMWRITE_JPEG_QUALITY)) if current_frame_codec == "webp" else int(cv2.IMWRITE_JPEG_QUALITY)
                    encode_started = clock()
                    try:
                        ok, encoded = cv2.imencode(encode_ext, frame, [encode_flag, current_frame_quality])
                    except Exception:
                        if current_frame_codec != "webp":
                            raise
                        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), current_frame_quality])
                    add_client_stat("encode_ms", (clock() - encode_started) * 1000.0)
                    if not ok:
                        async with condition:
                            in_flight = max(0, in_flight - 1)
                            condition.notify_all()
                        continue
                    frame_height, frame_width = frame.shape[:2]
                    payload_bytes = encoded.tobytes()
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "live_frame_meta",
                                "seq": capture_seq,
                                "capture_time": captured_wall_time,
                                "send_time": time.time(),
                                "codec": current_frame_codec,
                                "width": frame_width,
                                "height": frame_height,
                                "quality": current_frame_quality,
                                "payload_bytes": len(payload_bytes),
                            }
                        )
                    )
                    send_started = clock()
                    await websocket.send(payload_bytes)
                    add_client_stat("send_ms", (clock() - send_started) * 1000.0)
                    client_stats["frames"] = int(client_stats["frames"]) + 1
                    add_client_stat("sent_kb", len(payload_bytes) / 1024.0)
                    client_stats["frame_width"] = frame_width
                    client_stats["frame_height"] = frame_height
                    client_stats["frame_codec"] = current_frame_codec
                    client_stats["jpeg_quality"] = current_frame_quality
                    client_stats["capture_scale"] = current_capture_scale
                    now = clock()
                    if now - float(client_stats["started"]) >= 5.0:
                        emit_client_perf(now, current_pipeline_frames, in_flight)
                except Exception:
                    async with condition:
                        in_flight = max(0, in_flight - 1)
                        condition.notify_all()
                    raise

        async def receiver(websocket: Any) -> None:
            nonlocal in_flight, stats_started, stats_frames, receiver_decode_ms, virtual_send_ms, virtual_cam, virtual_cam_size
            while not self._stop:
                reply = await websocket.recv()
                if isinstance(reply, str):
                    self.message.emit(reply)
                    payload = _json_payload(reply)
                    if "error" in payload:
                        raise RuntimeError(str(payload["error"]))
                    if payload.get("status") == "live_config_update_rejected":
                        ui_message = payload.get("message", "live config update rejected")
                        self.message.emit(f"live config update rejected: {ui_message}")
                    continue
                async with condition:
                    in_flight = max(0, in_flight - 1)
                    condition.notify_all()
                self.frame.emit(reply)
                stats_frames += 1
                now = clock()
                if now - stats_started >= 5.0:
                    elapsed = max(0.001, now - stats_started)
                    receiver_fps = stats_frames / elapsed
                    frames = max(1, stats_frames)
                    self.message.emit(f"live throughput: {receiver_fps:.1f} fps")
                    self.message.emit(
                        json.dumps(
                            {
                                "status": "live_receiver_perf",
                                "receiver_fps": round(receiver_fps, 2),
                                "decode_ms": round(receiver_decode_ms / frames, 2),
                                "virtual_send_ms": round(virtual_send_ms / frames, 2),
                            }
                        )
                    )
                    stats_started = now
                    stats_frames = 0
                    receiver_decode_ms = 0.0
                    virtual_send_ms = 0.0
                if virtual_cam is not False:
                    import numpy as np

                    decode_started = clock()
                    decoded = cv2.imdecode(np.frombuffer(reply, dtype=np.uint8), cv2.IMREAD_COLOR)
                    receiver_decode_ms += (clock() - decode_started) * 1000.0
                    h, w = decoded.shape[:2]
                    if virtual_cam and virtual_cam_size != (w, h):
                        try:
                            virtual_cam.close()
                        except Exception:
                            pass
                        self.message.emit(f"virtual camera frame size changed: reopening at {w}x{h}")
                        virtual_cam = None
                        virtual_cam_size = None
                    if virtual_cam is None:
                        try:
                            import pyvirtualcam

                            virtual_cam = pyvirtualcam.Camera(width=w, height=h, fps=requested_fps, device=self.settings.virtual_camera or None)
                            virtual_cam_size = (w, h)
                            self.message.emit(f"virtual camera opened: {virtual_cam.device} at {w}x{h} {requested_fps} fps")
                        except Exception as exc:
                            self.message.emit(f"virtual camera unavailable: {exc}")
                            virtual_cam = False
                            virtual_cam_size = None
                    if virtual_cam:
                        virtual_started = clock()
                        rgb = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
                        virtual_cam.send(rgb)
                        virtual_cam.sleep_until_next_frame()
                        virtual_send_ms += (clock() - virtual_started) * 1000.0

        try:
            async with websockets.connect(uri, max_size=8 * 1024 * 1024) as websocket:
                await websocket.send(
                    json.dumps(
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
                            "frame_codec": frame_codec,
                            "output_codec": output_codec,
                            "jpeg_quality": frame_quality,
                            "frame_quality": frame_quality,
                            "detector_size": getattr(self.settings, "detector_size", DEFAULT_LIVE_DETECTOR_SIZE),
                            "detect_every_n": getattr(self.settings, "detect_every_n", DEFAULT_LIVE_DETECT_EVERY_N),
                            "face_model_pack": getattr(self.settings, "face_model_pack", DEFAULT_LIVE_FACE_MODEL_PACK),
                            "swapper_precision": getattr(self.settings, "swapper_precision", DEFAULT_LIVE_SWAPPER_PRECISION),
                            "cache_source_face": getattr(self.settings, "cache_source_face", True),
                        }
                    )
                )
                ready = await websocket.recv()
                self.message.emit(f"live backend: {ready}")
                ready_payload = _json_payload(ready)
                if "error" in ready_payload:
                    raise RuntimeError(str(ready_payload["error"]))

                sender_task = asyncio.create_task(sender(websocket))
                receiver_task = asyncio.create_task(receiver(websocket))
                done, pending = await asyncio.wait(
                    {sender_task, receiver_task},
                    return_when=asyncio.FIRST_EXCEPTION,
                )
                for task in done:
                    error = task.exception()
                    if error is not None:
                        raise error
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
        finally:
            capture_stop.set()
            with capture_condition:
                capture_condition.notify_all()
            capture_thread.join(timeout=1.0)
            cap.release()
            if virtual_cam and hasattr(virtual_cam, "close"):
                virtual_cam.close()
            self.message.emit("live worker stopped")


def start_live(self: MainWindow) -> None:
    self.sync_settings()
    if self.live_worker and self.live_worker.isRunning():
        self.log("live already running")
        ui_base._set_process_status(self, "live", "Live already running")
        return

    output_tasks_base._ensure_output_worker_state(self)
    self.settings.live_options = _read_live_options(self)
    processing_options_base.save_settings(self.settings)
    _set_live_controls_running(self, True)
    settings = output_tasks_base._copy_settings(self.settings)
    settings.live_width = _live_setting(self.settings, "live_width", DEFAULT_LIVE_WIDTH)
    settings.live_height = _live_setting(self.settings, "live_height", DEFAULT_LIVE_HEIGHT)
    settings.live_fps = _live_setting(self.settings, "live_fps", DEFAULT_LIVE_FPS)
    settings.live_pipeline_frames = _live_setting(self.settings, "live_pipeline_frames", DEFAULT_LIVE_PIPELINE_FRAMES)
    settings.live_options = _live_options(self.settings)
    _apply_live_options_to_settings(settings)
    self.log("starting live...")
    ui_base._set_process_status(self, "live", "Preparing live...")
    prepare_token = object()
    self._live_prepare_token = prepare_token

    def task() -> dict[str, Any]:
        return _prepare_live_settings(settings)

    def succeeded(task_id: str, result: object) -> None:
        if task_id != getattr(self, "output_live_task_id", "") or getattr(self, "_live_prepare_token", None) is not prepare_token:
            return
        payload = result if isinstance(result, dict) else {}
        for line in payload.get("logs") or []:
            line_text = str(line)
            self.log(line_text)
            ui_base._set_process_status(self, "live", line_text)
        live_settings = payload.get("settings")
        if not isinstance(live_settings, AppSettings):
            text = "live failed before start: invalid prepared settings"
            self.log(text)
            ui_base._set_process_status(self, "live", text)
            _set_live_controls_running(self, False)
            return
        self.live_worker = LiveWorker(live_settings)
        self.live_worker.message.connect(lambda text: _handle_live_worker_message(self, text))
        self.live_worker.frame.connect(self.enqueue_live_preview_frame)
        self.live_worker.finished.connect(lambda: (_stop_live_perf_test(self, restore=False), _set_live_controls_running(self, False)))
        live_preview.start_live_preview_timer(self, live_settings)
        self.live_worker.start()
        ui_base._set_process_status(self, "live", f"Starting live on camera index {live_settings.camera_index}...")

    def failed(task_id: str, error: str) -> None:
        if task_id != getattr(self, "output_live_task_id", "") or getattr(self, "_live_prepare_token", None) is not prepare_token:
            return
        text = f"live failed before start: {error}"
        self.log(text)
        ui_base._set_process_status(self, "live", text)
        _set_live_controls_running(self, False)

    self.output_live_task_id = output_tasks_base._start_output_task(
        self,
        "Preparing live...",
        task,
        succeeded,
        failed,
    )


def stop_live(self: MainWindow) -> None:
    self._live_prepare_token = None
    self.output_live_task_id = ""
    _stop_live_perf_test(self, restore=False)
    live_preview.stop_live_preview_timer(self)
    if self.live_worker:
        self.live_worker.stop()
        self.log("live stop requested")
        ui_base._set_process_status(self, "live", "Live stop requested")
    else:
        _set_live_controls_running(self, False)
