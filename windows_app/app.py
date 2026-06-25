from __future__ import annotations

from pathlib import Path

from windows_app import app_base as base
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
from windows_app.workers import LiveWorker, PollWorker

# Keep the legacy app_base namespace aligned for migration helpers that still
# intentionally access common symbols through `base`.
base.APP_STATE = APP_STATE
base.DEFAULT_DRIVE_ROOT = DEFAULT_DRIVE_ROOT
base.REMOTE_PREFIXES = REMOTE_PREFIXES
base.PHOTO_EXTENSIONS = PHOTO_EXTENSIONS
base.VIDEO_EXTENSIONS = VIDEO_EXTENSIONS
base.AppSettings = AppSettings
base.ApiClient = ApiClient
base.PollWorker = PollWorker
base.LiveWorker = LiveWorker
base.load_settings = load_settings
base.save_settings = save_settings
base.is_local_path = is_local_path
base.local_files = local_files
base.format_size = format_size
base.check_tailscale_cli = check_tailscale_cli
base.taildrop_receive_file = taildrop_receive_file
base.job_payload = job_payload

from windows_app.live_webcam import LiveWebcamMixin  # noqa: E402
from windows_app.main_window_ui import MainWindowUiMixin  # noqa: E402
from windows_app.output_tasks import OutputTasksMixin  # noqa: E402
from windows_app.processing_options import ProcessingOptionsMixin  # noqa: E402

# Re-export common application symbols for lightweight compatibility with callers.
QApplication = base.QApplication


class MainWindow(LiveWebcamMixin, ProcessingOptionsMixin, MainWindowUiMixin, OutputTasksMixin, base.MainWindow):
    """Canonical Windows remote controller window.

    The mixins replace the former runtime patch stack with normal class
    composition while preserving the same method resolution order as the old
    import chain: async outputs -> UI -> processing options -> live webcam.
    """


# Ensure workers/helpers that instantiate base.MainWindow-compatible behavior
# see the canonical class when they intentionally reference this module.
base.MainWindow = MainWindow


def main() -> int:
    app = base.QApplication([])

    qss_path = Path(__file__).parent / "dark_theme.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
