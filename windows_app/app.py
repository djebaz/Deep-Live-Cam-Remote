from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication as QtApplication

from windows_app.live_webcam import LiveWebcamMixin
from windows_app.main_window_ui import MainWindowUiMixin
from windows_app.output_tasks import OutputTasksMixin
from windows_app.processing_options import ProcessingOptionsMixin
from windows_app.window_core import WindowCore

# Re-export common application symbols for lightweight compatibility with callers.
QApplication = QtApplication


class MainWindow(LiveWebcamMixin, ProcessingOptionsMixin, MainWindowUiMixin, OutputTasksMixin, WindowCore):
    """Canonical Windows remote controller window.

    The mixins replace the former runtime patch stack with normal class
    composition while preserving the same method resolution order as the old
    import chain: async outputs -> UI -> processing options -> live webcam.
    """


def main() -> int:
    app = QtApplication([])

    qss_path = Path(__file__).parent / "dark_theme.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
