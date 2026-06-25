from __future__ import annotations

import math
import time
from collections import deque

from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt

from windows_app import main_window_ui as ui_base
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
    self._live_preview_started = self._live_preview_buffer_seconds <= 0
    self._live_preview_frames = 0
    self._live_preview_last_frame = None
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
    buffer = getattr(self, "_live_preview_buffer", None)
    if buffer is not None:
        buffer.clear()


def enqueue_live_preview_frame(self: MainWindow, frame_bytes: bytes) -> None:
    # Buffer by arrival time so the QTimer can render frames at an even cadence
    # after a small delay. Do not coalesce during normal playback; render one
    # queued frame per timer tick. Drop only if the backlog exceeds a safety cap.
    buffer = getattr(self, "_live_preview_buffer", None)
    if buffer is None:
        buffer = create_live_preview_buffer()
        self._live_preview_buffer = buffer
    now = time.monotonic()
    buffer.append((now, bytes(frame_bytes)))
    buffer_seconds = float(getattr(self, "_live_preview_buffer_seconds", DEFAULT_LIVE_PREVIEW_BUFFER_SECONDS))
    fps = _live_setting(self.settings, "live_fps", DEFAULT_LIVE_FPS)
    max_frames = max(3, int(math.ceil((buffer_seconds + 2.0) * fps)))
    while len(buffer) > max_frames:
        buffer.popleft()


def render_live_preview_frame(self: MainWindow) -> None:
    buffer = getattr(self, "_live_preview_buffer", None)
    if not buffer:
        return
    buffer_seconds = float(getattr(self, "_live_preview_buffer_seconds", DEFAULT_LIVE_PREVIEW_BUFFER_SECONDS))
    if not getattr(self, "_live_preview_started", False):
        if time.monotonic() - buffer[0][0] < buffer_seconds:
            return
        self._live_preview_started = True
    _timestamp, frame_bytes = buffer.popleft()
    if buffer_seconds > 0:
        fps = _live_setting(self.settings, "live_fps", DEFAULT_LIVE_FPS)
        # If the producer outruns the preview for a while, keep the stream near
        # the target delay by dropping only the oldest excess frames.
        target_frames = max(1, int(round(buffer_seconds * fps)))
        max_frames = max(target_frames + fps, target_frames * 2)
        while len(buffer) > max_frames:
            buffer.popleft()
    if not frame_bytes:
        return
    update_live_preview(self, frame_bytes)


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
    if self._live_preview_frames == 1 or self._live_preview_frames % max(1, _live_setting(self.settings, "live_fps", DEFAULT_LIVE_FPS)) == 0:
        ui_base._set_process_status(
            self,
            "live",
            (
                f"Live buffered preview ({image.width()}x{image.height()} -> {pixmap.width()}x{pixmap.height()}, "
                f"size {getattr(getattr(self, 'live_preview_scale', None), 'currentText', lambda: DEFAULT_LIVE_PREVIEW_SCALE)()}, "
                f"buffer {float(getattr(self, '_live_preview_buffer_seconds', DEFAULT_LIVE_PREVIEW_BUFFER_SECONDS)):.2f}s, "
                f"rendered {self._live_preview_frames})"
            ),
        )
