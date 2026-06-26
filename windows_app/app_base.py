from __future__ import annotations

"""Legacy compatibility shim for the Windows controller app.

The old `app_base.py` contained the monolithic Windows GUI implementation. Core
ownership now lives in focused modules:

- `windows_app.settings` for persistent settings and option migration.
- `windows_app.api_client` for non-Qt API and file-transfer helpers.
- `windows_app.workers` for Qt worker classes.
- `windows_app.window_core` for shared `MainWindow` state and lifecycle.

This module intentionally remains as a narrow re-export layer while the remaining
GUI modules are migrated away from broad `app_base as base` imports.
"""

import json
import urllib.parse
import urllib.request
from dataclasses import asdict

from PySide6.QtCore import QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
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

from windows_app.api_client import (
    ApiClient,
    check_tailscale_cli,
    format_size,
    is_local_path,
    job_payload,
    local_files,
    taildrop_receive_file,
)
from windows_app.settings import (
    APP_STATE,
    DEFAULT_DRIVE_ROOT,
    PHOTO_EXTENSIONS,
    REMOTE_PREFIXES,
    VIDEO_EXTENSIONS,
    AppSettings,
    load_settings,
    save_settings,
)
from windows_app.window_core import WindowCore, set_dark_title_bar
from windows_app.workers import LiveWorker, OutputTaskWorker, PollWorker

MainWindow = WindowCore


def main() -> int:
    from windows_app.app import main as app_main

    return app_main()


__all__ = [
    "APP_STATE",
    "DEFAULT_DRIVE_ROOT",
    "PHOTO_EXTENSIONS",
    "REMOTE_PREFIXES",
    "VIDEO_EXTENSIONS",
    "ApiClient",
    "AppSettings",
    "LiveWorker",
    "MainWindow",
    "OutputTaskWorker",
    "PollWorker",
    "WindowCore",
    "asdict",
    "check_tailscale_cli",
    "format_size",
    "is_local_path",
    "job_payload",
    "json",
    "load_settings",
    "local_files",
    "main",
    "save_settings",
    "set_dark_title_bar",
    "taildrop_receive_file",
    "urllib",
    "QApplication",
    "QAudioOutput",
    "QCheckBox",
    "QComboBox",
    "QDoubleSpinBox",
    "QFileDialog",
    "QFormLayout",
    "QGroupBox",
    "QHBoxLayout",
    "QIcon",
    "QImage",
    "QLabel",
    "QLineEdit",
    "QListWidget",
    "QListWidgetItem",
    "QMainWindow",
    "QMediaPlayer",
    "QPixmap",
    "QProgressBar",
    "QPushButton",
    "QSpinBox",
    "QTabWidget",
    "QTextEdit",
    "QThread",
    "QTimer",
    "Qt",
    "QUrl",
    "QVBoxLayout",
    "QVideoWidget",
    "QWidget",
    "Signal",
]
