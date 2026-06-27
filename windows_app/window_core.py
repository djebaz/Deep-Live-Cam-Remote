from __future__ import annotations

import ctypes
import sys
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QTextEdit,
)

from windows_app.api_client import ApiClient
from windows_app.settings import AppSettings, load_settings, save_settings
from windows_app.workers import LiveWorker, PollWorker


def set_dark_title_bar(window: QMainWindow) -> None:
    """Enable dark title bar on Windows 10/11."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        pass


class WindowCore(QMainWindow):
    """Core window state and small shared helpers for the Windows controller.

    Feature-specific tab construction and actions live in focused feature modules. This
    class owns only process-wide widget state, shared browse/path helpers, and
    lifecycle primitives that every feature area needs.
    """

    def __init__(self) -> None:
        super().__init__()
        set_dark_title_bar(self)

        icon_path = Path(__file__).parent / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.settings = load_settings()
        self.client = ApiClient(self.settings)
        self.poller: PollWorker | None = None
        self.live_worker: LiveWorker | None = None
        self.active_job_id: str | None = None
        self.output_files: list[dict[str, Any]] = []
        self.output_current_loaded = False
        self.output_temp_dir = Path(tempfile.gettempdir()) / "deep_live_cam_remote_outputs"
        self.output_temp_dir.mkdir(parents=True, exist_ok=True)

        self.output_timer = QTimer(self)
        self.output_timer.setSingleShot(True)
        self.output_timer.timeout.connect(self.next_output)

        self.setWindowTitle("Deep-Live-Cam Remote Controller")
        self.resize(980, 760)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.log_box = QTextEdit(readOnly=True)

        self._build_setup_tab()
        self._build_photos_tab()
        self._build_videos_tab()
        self._build_outputs_tab()
        self._build_live_tab()
        self.tabs.addTab(self.log_box, "Logs")

    def log(self, text: str) -> None:
        self.log_box.append(text)

    def _browse_file(
        self,
        line_edit: QLineEdit,
        title: str,
        file_filter: str = "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
    ) -> None:
        path, _ = QFileDialog.getOpenFileName(self, title, "", file_filter)
        if path:
            line_edit.setText(path)

    def _browse_folder(self, line_edit: QLineEdit, title: str) -> None:
        path = QFileDialog.getExistingDirectory(self, title)
        if path:
            line_edit.setText(path)

    def _path_row(self, line_edit: QLineEdit, browse_callback: Any) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(line_edit)
        browse = QPushButton("Browse...")
        browse.clicked.connect(browse_callback)
        row.addWidget(browse)
        return row

    def _common_group(self) -> QGroupBox:
        box = QGroupBox("Common options")
        form = QFormLayout(box)
        self.source_face = QLineEdit(self.settings.source_face)
        source_row = self._path_row(
            self.source_face,
            lambda: self._browse_file(self.source_face, "Select source face image"),
        )
        self.recursive = QCheckBox()
        self.recursive.setChecked(self.settings.recursive)
        self.overwrite = QCheckBox()
        self.overwrite.setChecked(self.settings.overwrite)
        self.skip_processed = QCheckBox()
        self.skip_processed.setChecked(self.settings.skip_processed)
        self.many_faces = QCheckBox()
        self.many_faces.setChecked(self.settings.many_faces)
        self.enhancer = QComboBox()
        self.enhancer.addItems(["none", "gfpgan", "gpen256", "gpen512"])
        self.enhancer.setCurrentText(self.settings.enhancer)
        self.opacity = QDoubleSpinBox()
        self.opacity.setRange(0.0, 1.0)
        self.opacity.setSingleStep(0.1)
        self.opacity.setValue(self.settings.opacity)
        self.sharpness = QDoubleSpinBox()
        self.sharpness.setRange(0.0, 1.0)
        self.sharpness.setSingleStep(0.1)
        self.sharpness.setValue(self.settings.sharpness)
        self.mouth_mask_size = QDoubleSpinBox()
        self.mouth_mask_size.setRange(0.0, 10.0)
        self.mouth_mask_size.setSingleStep(0.5)
        self.mouth_mask_size.setValue(self.settings.mouth_mask_size)
        self.interpolation_weight = QDoubleSpinBox()
        self.interpolation_weight.setRange(0.0, 1.0)
        self.interpolation_weight.setSingleStep(0.1)
        self.interpolation_weight.setValue(self.settings.interpolation_weight)
        self.poisson_blend = QCheckBox()
        self.poisson_blend.setChecked(self.settings.poisson_blend)
        self.color_correction = QCheckBox()
        self.color_correction.setChecked(self.settings.color_correction)
        form.addRow("Source face path", source_row)
        form.addRow("Recursive", self.recursive)
        form.addRow("Overwrite", self.overwrite)
        form.addRow("Skip processed", self.skip_processed)
        form.addRow("Many faces", self.many_faces)
        form.addRow("Enhancer", self.enhancer)
        form.addRow("Opacity (1=full)", self.opacity)
        form.addRow("Sharpness (0=off)", self.sharpness)
        form.addRow("Mouth mask (0=off)", self.mouth_mask_size)
        form.addRow("Interpolation (0=off)", self.interpolation_weight)
        form.addRow("Poisson blend", self.poisson_blend)
        form.addRow("Color correction", self.color_correction)
        return box

    def stop_output_video(self) -> None:
        if getattr(self, "output_player", None) is not None:
            self.output_player.stop()
        if getattr(self, "output_video", None) is not None:
            self.output_video.hide()
        if hasattr(self, "output_preview"):
            self.output_preview.show()

    def current_output(self) -> dict[str, Any] | None:
        index = self.outputs_list.currentRow()
        if index < 0 or index >= len(self.output_files):
            return None
        return self.output_files[index]

    def previous_output(self) -> None:
        if not self.output_files:
            return
        index = self.outputs_list.currentRow()
        self.outputs_list.setCurrentRow((index - 1) % len(self.output_files))

    def next_output(self) -> None:
        if not self.output_files:
            return
        if self.outputs_autoplay.isChecked() and not self.output_current_loaded:
            return
        index = self.outputs_list.currentRow()
        self.outputs_list.setCurrentRow((index + 1) % len(self.output_files))

    def output_autoplay_interval_ms(self) -> int:
        if self.outputs_kind.currentText() == "videos":
            return 8000
        seconds_control = getattr(self, "outputs_photo_seconds", None)
        seconds = float(seconds_control.value()) if seconds_control is not None else 3.5
        return max(250, int(round(seconds * 1000.0)))

    def schedule_outputs_autoplay(self) -> None:
        self.output_timer.stop()
        if not self.outputs_autoplay.isChecked():
            return
        if not self.output_files or not self.output_current_loaded:
            return
        self.output_timer.start(self.output_autoplay_interval_ms())

    def toggle_outputs_autoplay(self) -> None:
        if self.outputs_autoplay.isChecked():
            if self.outputs_kind.currentText() == "photos":
                try:
                    from windows_app import output_browser

                    preload_control = getattr(self, "outputs_photo_preload_count", None)
                    count = int(preload_control.value()) if preload_control is not None else 10
                    output_browser._prefetch_neighbors(self, self.outputs_list.currentRow(), count=count)
                except Exception as exc:
                    self.log(f"photo autoplay prefetch failed: {exc}")
            self.schedule_outputs_autoplay()
        else:
            self.output_timer.stop()

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        try:
            self.sync_settings()
            save_settings(self.settings)
        except Exception as exc:
            self.log(f"settings save on close failed: {exc}")
        if self.poller:
            self.poller.stop()
        if self.live_worker:
            self.live_worker.stop()
        self.stop_output_video()
        super().closeEvent(event)
