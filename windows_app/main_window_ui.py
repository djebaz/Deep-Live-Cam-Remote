from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
except Exception:
    QAudioOutput = None
    QMediaPlayer = None
    QVideoWidget = None

from windows_app.window_core import WindowCore as MainWindow


def _link_source_fields(window: MainWindow) -> None:
    if getattr(window, "_source_fields_linked", False):
        return
    if not hasattr(window, "source_face") or not hasattr(window, "video_source_face"):
        return

    def mirror(target: QLineEdit, text: str) -> None:
        if target.text() == text:
            return
        target.blockSignals(True)
        target.setText(text)
        target.blockSignals(False)

    window.source_face.textChanged.connect(lambda text: mirror(window.video_source_face, text))
    window.video_source_face.textChanged.connect(lambda text: mirror(window.source_face, text))
    window._source_fields_linked = True


def _status_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("statusLabel")
    label.setWordWrap(True)
    return label


def _set_process_status(window: MainWindow, kind: str, text: str) -> None:
    names = {
        "setup": "setup_status",
        "photos": "photos_status",
        "videos": "videos_status",
        "outputs": "output_status",
        "live": "live_status",
    }
    label = getattr(window, names.get(kind, ""), None)
    if label is not None:
        label.setText(text)
    if kind != "outputs" and hasattr(window, "output_status"):
        # Keep the Outputs footer useful for background tasks started elsewhere.
        window.output_status.setText(text)


def _set_batch_button_running(window: MainWindow, kind: str) -> None:
    """Set the batch button to 'Stop' state (danger style)."""
    btn = getattr(window, f"{kind}_start_btn", None)
    if btn is None:
        return
    btn.setText(f"Stop {kind} batch")
    btn.setObjectName("dangerButton")
    btn.setStyle(btn.style())  # Force style refresh


def _set_batch_button_idle(window: MainWindow, kind: str) -> None:
    """Set the batch button to 'Start' state (primary style)."""
    btn = getattr(window, f"{kind}_start_btn", None)
    if btn is None:
        return
    btn.setText(f"Start {kind[:-1] if kind.endswith('s') else kind} batch")
    btn.setObjectName("primaryButton")
    btn.setStyle(btn.style())  # Force style refresh


def _is_batch_running(window: MainWindow) -> bool:
    """Check if a batch job is currently active."""
    return bool(window.active_job_id)


def _toggle_photos_batch(window: MainWindow) -> None:
    """Toggle between starting and stopping photo batch."""
    if _is_batch_running(window):
        window.cancel_job()
    else:
        window.start_photos()


def _toggle_videos_batch(window: MainWindow) -> None:
    """Toggle between starting and stopping video batch."""
    if _is_batch_running(window):
        window.cancel_job()
    else:
        window.start_videos()


def _save_settings_from_setup(window: MainWindow) -> None:
    window.sync_settings()
    window.log("settings saved")
    _set_process_status(window, "setup", "Settings saved")


def _build_setup_tab(self: MainWindow) -> None:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    form = QFormLayout()
    self.host = QLineEdit(self.settings.host)
    self.port = QSpinBox()
    self.port.setRange(1, 65535)
    self.port.setValue(self.settings.port)
    self.drive_root = QLineEdit(self.settings.drive_root)
    form.addRow("Tailscale host/IP", self.host)
    form.addRow("API port", self.port)
    form.addRow("Drive root", self.drive_root)
    layout.addLayout(form)

    self.setup_help = QTextEdit(readOnly=True)
    self.setup_help.setObjectName("helpText")
    self.setup_help.setPlainText(
        "Colab setup checklist:\n"
        "1. Open google-colab/Deep_Live_Cam_Remote_Batch.ipynb.\n"
        "2. Run Install and initialize.\n"
        "3. Mount Drive and use /content/drive/MyDrive/DeepLiveCamRemote.\n"
        "4. Run the Remote API server cell.\n"
        "5. Start Tailscale in Colab and copy the Tailscale IP here.\n"
    )
    layout.addWidget(self.setup_help)

    row = QHBoxLayout()
    btn = QPushButton("Check connection")
    btn.setObjectName("primaryButton")
    btn.clicked.connect(self.check_connection)
    save = QPushButton("Save settings")
    save.setObjectName("successButton")
    save.clicked.connect(lambda: _save_settings_from_setup(self))
    row.addWidget(btn)
    row.addWidget(save)
    row.addStretch(1)
    layout.addLayout(row)

    self.setup_status = _status_label("Idle")
    layout.addWidget(self.setup_status)
    self.tabs.addTab(tab, "Setup")


def _build_photos_tab(self: MainWindow) -> None:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.addWidget(self._common_group())

    form = QFormLayout()
    self.photos_input = QLineEdit(self.settings.photos_input)
    self.photos_output = QLineEdit(self.settings.photos_output)
    photos_input_row = self._path_row(
        self.photos_input,
        lambda: self._browse_folder(self.photos_input, "Select photos input folder"),
    )
    form.addRow("Photos input path", photos_input_row)
    form.addRow("Photos output path", self.photos_output)
    layout.addLayout(form)

    advanced_box = QGroupBox("Photo processing limits")
    advanced_form = QFormLayout(advanced_box)
    self.photos_max_width = QSpinBox()
    self.photos_max_width.setRange(0, 8192)
    self.photos_max_width.setSpecialValueText("Original")
    self.photos_max_width.setValue(int(getattr(self.settings, "photo_max_width", 0)))
    self.photos_quality = QSpinBox()
    self.photos_quality.setRange(1, 100)
    self.photos_quality.setValue(int(getattr(self.settings, "photo_quality", 95)))
    self.photos_detector_size = QSpinBox()
    self.photos_detector_size.setRange(160, 1280)
    self.photos_detector_size.setSingleStep(32)
    self.photos_detector_size.setValue(int(getattr(self.settings, "photo_detector_size", 640)))
    self.photos_face_model_pack = QComboBox()
    self.photos_face_model_pack.addItems(["buffalo_l", "buffalo_m", "buffalo_s"])
    self.photos_face_model_pack.setCurrentText(str(getattr(self.settings, "photo_face_model_pack", "buffalo_l")))
    self.photos_swapper_precision = QComboBox()
    self.photos_swapper_precision.addItems(["fp32", "fp16"])
    self.photos_swapper_precision.setCurrentText(str(getattr(self.settings, "photo_swapper_precision", "fp32")))
    advanced_form.addRow("Max width", self.photos_max_width)
    advanced_form.addRow("Image quality", self.photos_quality)
    advanced_form.addRow("Detector size", self.photos_detector_size)
    advanced_form.addRow("Face model pack", self.photos_face_model_pack)
    advanced_form.addRow("Swapper precision", self.photos_swapper_precision)
    layout.addWidget(advanced_box)

    self.photos_start_btn = QPushButton("Start photo batch")
    self.photos_start_btn.setObjectName("primaryButton")
    self.photos_start_btn.clicked.connect(lambda: _toggle_photos_batch(self))
    layout.addWidget(self.photos_start_btn)
    self.photos_status = _status_label("Idle")
    layout.addWidget(self.photos_status)
    layout.addStretch(1)
    self.tabs.addTab(tab, "Photos")


def _build_videos_tab(self: MainWindow) -> None:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    form = QFormLayout()

    self.video_source_face = QLineEdit(self.settings.source_face)
    source_row = self._path_row(
        self.video_source_face,
        lambda: self._browse_file(self.video_source_face, "Select source face image"),
    )
    _link_source_fields(self)

    self.videos_input = QLineEdit(self.settings.videos_input)
    self.videos_output = QLineEdit(self.settings.videos_output)
    self.max_fps = QDoubleSpinBox()
    self.max_fps.setRange(1, 120)
    self.max_fps.setValue(self.settings.max_fps)
    self.max_width = QSpinBox()
    self.max_width.setRange(64, 4096)
    self.max_width.setValue(self.settings.max_width)
    self.quality = QSpinBox()
    self.quality.setRange(0, 51)
    self.quality.setValue(self.settings.quality)

    # Video segment range (percentage)
    self.start_pct = QDoubleSpinBox()
    self.start_pct.setRange(0, 99)
    self.start_pct.setValue(self.settings.start_pct)
    self.start_pct.setSuffix("%")
    self.start_pct.setDecimals(1)
    self.end_pct = QDoubleSpinBox()
    self.end_pct.setRange(1, 100)
    self.end_pct.setValue(self.settings.end_pct)
    self.end_pct.setSuffix("%")
    self.end_pct.setDecimals(1)
    range_row = QHBoxLayout()
    range_row.addWidget(self.start_pct)
    range_row.addWidget(QLabel("to"))
    range_row.addWidget(self.end_pct)
    range_row.addStretch(1)

    videos_input_row = self._path_row(
        self.videos_input,
        lambda: self._browse_folder(self.videos_input, "Select videos input folder"),
    )

    form.addRow("Source face path", source_row)
    form.addRow("Videos input path", videos_input_row)
    form.addRow("Videos output path", self.videos_output)
    form.addRow("Process range", range_row)
    form.addRow("Max FPS", self.max_fps)
    form.addRow("Max width", self.max_width)
    form.addRow("Quality", self.quality)
    layout.addLayout(form)

    # Common processing options (shared with Photos via linked widgets)
    options_box = QGroupBox("Processing options")
    options_form = QFormLayout(options_box)

    # Link to Photos tab widgets - changes sync automatically via sync_settings
    self.v_recursive = QCheckBox()
    self.v_recursive.setChecked(self.settings.recursive)
    self.v_overwrite = QCheckBox()
    self.v_overwrite.setChecked(self.settings.overwrite)
    self.v_skip_processed = QCheckBox()
    self.v_skip_processed.setChecked(self.settings.skip_processed)
    self.v_many_faces = QCheckBox()
    self.v_many_faces.setChecked(self.settings.many_faces)
    self.v_enhancer = QComboBox()
    self.v_enhancer.addItems(["none", "gfpgan", "gpen256", "gpen512"])
    self.v_enhancer.setCurrentText(self.settings.enhancer)
    self.v_opacity = QDoubleSpinBox()
    self.v_opacity.setRange(0.0, 1.0)
    self.v_opacity.setSingleStep(0.1)
    self.v_opacity.setValue(self.settings.opacity)
    self.v_sharpness = QDoubleSpinBox()
    self.v_sharpness.setRange(0.0, 1.0)
    self.v_sharpness.setSingleStep(0.1)
    self.v_sharpness.setValue(self.settings.sharpness)
    self.v_mouth_mask_size = QDoubleSpinBox()
    self.v_mouth_mask_size.setRange(0.0, 10.0)
    self.v_mouth_mask_size.setSingleStep(0.5)
    self.v_mouth_mask_size.setValue(self.settings.mouth_mask_size)
    self.v_interpolation_weight = QDoubleSpinBox()
    self.v_interpolation_weight.setRange(0.0, 1.0)
    self.v_interpolation_weight.setSingleStep(0.1)
    self.v_interpolation_weight.setValue(self.settings.interpolation_weight)
    self.v_poisson_blend = QCheckBox()
    self.v_poisson_blend.setChecked(self.settings.poisson_blend)
    self.v_color_correction = QCheckBox()
    self.v_color_correction.setChecked(self.settings.color_correction)

    options_form.addRow("Recursive", self.v_recursive)
    options_form.addRow("Overwrite", self.v_overwrite)
    options_form.addRow("Skip processed", self.v_skip_processed)
    options_form.addRow("Many faces", self.v_many_faces)
    options_form.addRow("Enhancer", self.v_enhancer)
    options_form.addRow("Opacity (1=full)", self.v_opacity)
    options_form.addRow("Sharpness (0=off)", self.v_sharpness)
    options_form.addRow("Mouth mask (0=off)", self.v_mouth_mask_size)
    options_form.addRow("Interpolation (0=off)", self.v_interpolation_weight)
    options_form.addRow("Poisson blend", self.v_poisson_blend)
    options_form.addRow("Color correction", self.v_color_correction)
    layout.addWidget(options_box)

    self.videos_start_btn = QPushButton("Start video batch")
    self.videos_start_btn.setObjectName("primaryButton")
    self.videos_start_btn.clicked.connect(lambda: _toggle_videos_batch(self))
    layout.addWidget(self.videos_start_btn)
    self.videos_status = _status_label("Idle")
    layout.addWidget(self.videos_status)
    layout.addStretch(1)
    self.tabs.addTab(tab, "Videos")


def _build_outputs_tab(self: MainWindow) -> None:
    tab = QWidget()
    layout = QVBoxLayout(tab)

    controls = QHBoxLayout()
    self.outputs_kind = QComboBox()
    self.outputs_kind.addItems(["photos", "videos"])
    refresh = QPushButton("Refresh")
    previous = QPushButton("Previous")
    next_button = QPushButton("Next")
    self.outputs_autoplay = QCheckBox("Auto-play")
    self.outputs_photo_seconds = QDoubleSpinBox()
    self.outputs_photo_seconds.setRange(0.25, 60.0)
    self.outputs_photo_seconds.setSingleStep(0.25)
    self.outputs_photo_seconds.setDecimals(2)
    self.outputs_photo_seconds.setValue(3.5)
    self.outputs_photo_seconds.setSuffix(" s")
    self.outputs_photo_seconds.setToolTip("Seconds each loaded photo remains visible during output auto-play.")
    self.outputs_photo_preload_count = QSpinBox()
    self.outputs_photo_preload_count.setRange(1, 50)
    self.outputs_photo_preload_count.setValue(10)
    self.outputs_photo_preload_count.setToolTip("How many upcoming photos to preload while output auto-play is enabled.")
    self.outputs_photo_zoom = QComboBox()
    self.outputs_photo_zoom.addItems(["fit", "0.5x", "0.8x", "1x", "1.5x", "2x"])
    self.outputs_photo_zoom.setToolTip("Photo preview zoom. Fit scales to the preview panel; fixed zooms use original image pixels.")
    download_current = QPushButton("Download current")
    download_all = QPushButton("Download all")
    refresh.clicked.connect(self.refresh_outputs)
    previous.clicked.connect(self.previous_output)
    next_button.clicked.connect(self.next_output)
    self.outputs_autoplay.stateChanged.connect(self.toggle_outputs_autoplay)
    self.outputs_photo_seconds.valueChanged.connect(lambda _value: self.schedule_outputs_autoplay())
    self.outputs_photo_preload_count.valueChanged.connect(
        lambda _value: __import__("windows_app.output_browser", fromlist=["_prefetch_neighbors"])._prefetch_neighbors(
            self, self.outputs_list.currentRow(), count=int(self.outputs_photo_preload_count.value())
        )
        if self.outputs_autoplay.isChecked() and self.outputs_kind.currentText() == "photos"
        else None
    )
    self.outputs_photo_zoom.currentTextChanged.connect(
        lambda _text: __import__("windows_app.output_browser", fromlist=["apply_output_photo_zoom"]).apply_output_photo_zoom(self)
    )
    self.outputs_kind.currentTextChanged.connect(lambda _text: self.refresh_outputs())
    download_current.clicked.connect(self.download_current_output)
    download_all.clicked.connect(self.download_all_outputs)
    controls.addWidget(QLabel("Kind"))
    controls.addWidget(self.outputs_kind)
    controls.addWidget(refresh)
    controls.addWidget(previous)
    controls.addWidget(next_button)
    controls.addWidget(self.outputs_autoplay)
    controls.addWidget(QLabel("Photo seconds"))
    controls.addWidget(self.outputs_photo_seconds)
    controls.addWidget(QLabel("Preload"))
    controls.addWidget(self.outputs_photo_preload_count)
    controls.addWidget(QLabel("Photo zoom"))
    controls.addWidget(self.outputs_photo_zoom)
    controls.addWidget(download_current)
    controls.addWidget(download_all)
    controls.addStretch(1)
    layout.addLayout(controls)

    self.outputs_progress = QProgressBar()
    self.outputs_progress.setMaximum(100)
    self.outputs_progress.setFixedHeight(20)
    self.outputs_progress.setTextVisible(True)
    self.outputs_progress.hide()
    layout.addWidget(self.outputs_progress)

    splitter = QSplitter(Qt.Horizontal)
    self.outputs_list = QListWidget()
    self.outputs_list.setMinimumWidth(180)
    self.outputs_list.currentRowChanged.connect(self.show_output_at)
    splitter.addWidget(self.outputs_list)

    preview_panel = QWidget()
    preview_layout = QVBoxLayout(preview_panel)
    self.output_preview = QLabel("Refresh outputs to preview remote media")
    self.output_preview.setAlignment(Qt.AlignCenter)
    self.output_preview.setMinimumHeight(340)
    self.output_preview.setWordWrap(True)
    preview_layout.addWidget(self.output_preview, 1)

    self.output_video = None
    self.output_audio = None
    self.output_player = None
    if QMediaPlayer is not None and QVideoWidget is not None and QAudioOutput is not None:
        self.output_video = QVideoWidget()
        self.output_video.setMinimumHeight(340)
        self.output_audio = QAudioOutput(self)
        self.output_player = QMediaPlayer(self)
        self.output_player.setAudioOutput(self.output_audio)
        self.output_player.setVideoOutput(self.output_video)
        preview_layout.addWidget(self.output_video, 1)
        self.output_video.hide()

    self.output_status = QLabel("")
    self.output_status.setObjectName("statusLabel")
    self.output_status.setWordWrap(True)
    preview_layout.addWidget(self.output_status)

    splitter.addWidget(preview_panel)
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)
    splitter.setSizes([300, 820])
    layout.addWidget(splitter, 1)
    self.tabs.addTab(tab, "Outputs")


def _build_live_tab(self: MainWindow) -> None:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    form = QFormLayout()
    self.camera_index = QSpinBox()
    self.camera_index.setRange(0, 20)
    self.camera_index.setValue(self.settings.camera_index)
    self.virtual_camera = QLineEdit(self.settings.virtual_camera)
    form.addRow("Camera index", self.camera_index)
    form.addRow("Virtual camera", self.virtual_camera)
    layout.addLayout(form)

    self.live_note = _status_label(
        "Live sends webcam JPEG frames to ws://HOST:PORT/ws/live, previews returned frames, "
        "and opens the configured virtual camera when pyvirtualcam can find it."
    )
    layout.addWidget(self.live_note)
    self.live_preview = QLabel("Live preview")
    self.live_preview.setAlignment(Qt.AlignCenter)
    self.live_preview.setMinimumHeight(360)
    layout.addWidget(self.live_preview)

    row = QHBoxLayout()
    start = QPushButton("Start live")
    start.setObjectName("successButton")
    stop = QPushButton("Stop live")
    stop.setObjectName("dangerButton")
    start.clicked.connect(self.start_live)
    stop.clicked.connect(self.stop_live)
    row.addWidget(start)
    row.addWidget(stop)
    row.addStretch(1)
    layout.addLayout(row)

    self.live_status = _status_label("Idle")
    layout.addWidget(self.live_status)
    layout.addStretch(1)
    self.tabs.addTab(tab, "Live")


def _poll_message(window: MainWindow, kind: str, text: str) -> None:
    window.log(text)
    _set_process_status(window, kind, text)
