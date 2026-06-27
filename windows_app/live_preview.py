from __future__ import annotations

import math
import time
from collections import deque

from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt

from windows_app.settings import AppSettings
from windows_app.live_options import (
    DEFAULT_LIVE_FPS,
    DEFAULT_LIVE_PREVIEW_BUFFER_SECONDS,
    DEFAULT_LIVE_PREVIEW_SCALE,
    LIVE_PREVIEW_SCALES,
    _live_options,
    _live_setting,
)
from windows_app.window_core import WindowCore as MainWindow


def create_live_preview_buffer() -> deque:
    return deque()


def start_live_preview_timer(self: MainWindow, settings: AppSettings) -> None:
    timer = getattr(self, "_live_preview_timer", None)
    if timer is None:
        return
    self._live_latest_jpeg = None
    self._live_preview_buffer = create_live_preview_buffer()
    self._live_preview_buffer_seconds = float(_live_options(settings)["preview_buffer_seconds"])
    self._live_preview_started = False
    self._live_preview_clock_started_at = None
    self._live_preview_first_seq = None
    self._live_preview_current_seq = None
    self._live_preview_synthetic_seq = 0
    self._live_preview_frames = 0
    self._live_preview_last_frame = None
    self._live_preview_dropped_frames = 0
    fps = _live_setting(settings, "live_fps", DEFAULT_LIVE_FPS)
    interval_ms = max(1, int(round(1000.0 / max(1, fps))))
    timer.setInterval(interval_ms)
    timer.start()


def stop_live_preview_timer(self: MainWindow) -> None:
    timer = getattr(self, "_live_preview_timer", None)
    if timer is not None:
        timer.stop()
    self._live_latest_jpeg = None
    self._live_preview_last_frame = None
    self._live_preview_clock_started_at = None
    self._live_preview_first_seq = None
    self._live_preview_current_seq = None
    buffer = getattr(self, "_live_preview_buffer", None)
    if buffer is not None:
        buffer.clear()


def enqueue_live_preview_frame(self: MainWindow, frame_bytes: bytes) -> None:
    enqueue_live_preview_frame_packet(self, {}, frame_bytes)


def _preview_frame_seq(self: MainWindow, meta: dict[str, object]) -> int:
    try:
        return int(meta.get("seq", ""))
    except (TypeError, ValueError):
        seq = int(getattr(self, "_live_preview_synthetic_seq", 0))
        self._live_preview_synthetic_seq = seq + 1
        return seq


def enqueue_live_preview_frame_packet(self: MainWindow, meta: dict[str, object], frame_bytes: bytes) -> None:
    # The timer is the presentation clock. The queue keeps completed backend
    # frames; render_live_preview_frame repeats the last displayed frame when a
    # sequence number is missing.
    buffer = getattr(self, "_live_preview_buffer", None)
    if buffer is None:
        buffer = create_live_preview_buffer()
        self._live_preview_buffer = buffer
    now = time.monotonic()
    seq = _preview_frame_seq(self, meta if isinstance(meta, dict) else {})
    buffer.append(
        {
            "seq": seq,
            "received_at": now,
            "meta": dict(meta) if isinstance(meta, dict) else {},
            "payload": bytes(frame_bytes),
        }
    )
    buffer_seconds = float(getattr(self, "_live_preview_buffer_seconds", DEFAULT_LIVE_PREVIEW_BUFFER_SECONDS))
    fps = _live_setting(self.settings, "live_fps", DEFAULT_LIVE_FPS)
    max_frames = max(3, int(math.ceil((buffer_seconds + 2.0) * fps)))
    while len(buffer) > max_frames:
        buffer.popleft()


def render_live_preview_frame(self: MainWindow) -> None:
    buffer = getattr(self, "_live_preview_buffer", None)
    if not buffer:
        return
    now = time.monotonic()
    buffer_seconds = float(getattr(self, "_live_preview_buffer_seconds", DEFAULT_LIVE_PREVIEW_BUFFER_SECONDS))
    fps = _live_setting(self.settings, "live_fps", DEFAULT_LIVE_FPS)
    if getattr(self, "_live_preview_clock_started_at", None) is None:
        first = buffer[0]
        self._live_preview_first_seq = int(first["seq"])
        self._live_preview_clock_started_at = float(first["received_at"]) + max(0.0, buffer_seconds)
        self._live_preview_started = False

    clock_started_at = float(getattr(self, "_live_preview_clock_started_at", now) or now)
    if now < clock_started_at:
        return
    self._live_preview_started = True
    first_seq = int(getattr(self, "_live_preview_first_seq", 0) or 0)
    target_seq = first_seq + int((now - clock_started_at) * fps)
    frame_item = None
    dropped = 0
    while buffer and int(buffer[0]["seq"]) <= target_seq:
        candidate = buffer.popleft()
        if int(candidate["seq"]) <= int(getattr(self, "_live_preview_current_seq", -1) or -1):
            dropped += 1
            continue
        frame_item = candidate
        if buffer and int(buffer[0]["seq"]) <= target_seq:
            dropped += 1
    if dropped:
        self._live_preview_dropped_frames = int(getattr(self, "_live_preview_dropped_frames", 0)) + dropped
    if frame_item is None:
        return
    self._live_preview_current_seq = int(frame_item["seq"])
    update_live_preview(self, frame_item["payload"])


def _preview_scale_factor(scale: str) -> float | None:
    normalized = str(scale or DEFAULT_LIVE_PREVIEW_SCALE).lower()
    if normalized == "fit":
        return None
    try:
        return float(normalized.rstrip("x"))
    except ValueError:
        return None


def _preview_target_size(self: MainWindow, image: QImage) -> tuple[int, int]:
    panel_size = self.live_preview.size()
    panel_width = max(1, int(panel_size.width()))
    panel_height = max(1, int(panel_size.height()))
    factor = _preview_scale_factor(getattr(getattr(self, "live_preview_scale", None), "currentText", lambda: DEFAULT_LIVE_PREVIEW_SCALE)())
    if factor is not None:
        target_width = max(1, int(round(image.width() * factor)))
        target_height = max(1, int(round(image.height() * factor)))
        if target_width <= panel_width and target_height <= panel_height:
            return target_width, target_height
    image_ratio = image.width() / max(1, image.height())
    panel_ratio = panel_width / max(1, panel_height)
    if image_ratio >= panel_ratio:
        return panel_width, max(1, int(round(panel_width / image_ratio)))
    return max(1, int(round(panel_height * image_ratio))), panel_height


def update_live_preview_from_last_frame(self: MainWindow) -> None:
    frame = getattr(self, "_live_preview_last_frame", None)
    if frame:
        update_live_preview(self, frame, remember=False)


def update_live_preview(self: MainWindow, frame_bytes: bytes, remember: bool = True) -> None:
    image = QImage.fromData(frame_bytes)
    if image.isNull():
        try:
            import cv2
            import numpy as np

            decoded = cv2.imdecode(np.frombuffer(frame_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if decoded is None:
                return
            rgb = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
            height, width, channels = rgb.shape
            image = QImage(rgb.data, width, height, channels * width, QImage.Format_RGB888).copy()
        except Exception:
            return
    if remember:
        self._live_preview_last_frame = bytes(frame_bytes)
    target_width, target_height = _preview_target_size(self, image)
    pixmap = QPixmap.fromImage(image).scaled(
        target_width,
        target_height,
        Qt.KeepAspectRatio,
        Qt.FastTransformation,
    )
    self.live_preview.setPixmap(pixmap)
    self._live_preview_frames = int(getattr(self, "_live_preview_frames", 0)) + 1
