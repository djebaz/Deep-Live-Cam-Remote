from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication as QtApplication

from windows_app import live_preview, live_webcam, main_window_ui, output_browser, output_tasks, processing_options
from windows_app.window_core import WindowCore

# Re-export common application symbols for lightweight compatibility with callers.
QApplication = QtApplication


class MainWindow(WindowCore):
    """Canonical Windows remote controller window with explicit feature delegates."""

    def _build_setup_tab(self) -> None:
        return main_window_ui._build_setup_tab(self)

    def _build_photos_tab(self) -> None:
        return processing_options._build_photos_tab(self)

    def _build_videos_tab(self) -> None:
        return processing_options._build_videos_tab(self)

    def _build_outputs_tab(self) -> None:
        return main_window_ui._build_outputs_tab(self)

    def _build_live_tab(self) -> None:
        return live_webcam._build_live_tab(self)

    def check_connection(self) -> None:
        return output_tasks.check_connection(self)

    def sync_settings(self) -> None:
        return live_webcam.sync_settings(self)

    def start_photos(self) -> None:
        return processing_options.start_photos(self)

    def start_videos(self) -> None:
        return processing_options.start_videos(self)

    def cancel_job(self) -> None:
        return output_tasks.cancel_job(self)

    def refresh_outputs(self) -> None:
        return output_tasks.refresh_outputs(self)

    def show_output_at(self, index: int) -> None:
        return output_browser.show_output_at(self, index)

    def show_video_output(self, item: dict[str, Any]) -> None:
        return output_browser.show_video_output(self, item)

    def download_current_output(self) -> None:
        return output_tasks.download_current_output(self)

    def download_all_outputs(self) -> None:
        return output_tasks.download_all_outputs(self)

    def start_live(self) -> None:
        return live_webcam.start_live(self)

    def stop_live(self) -> None:
        return live_webcam.stop_live(self)

    def enqueue_live_preview_frame(self, frame_bytes: bytes) -> None:
        return live_preview.enqueue_live_preview_frame(self, frame_bytes)

    def update_live_preview(self, frame_bytes: bytes, remember: bool = True) -> None:
        return live_preview.update_live_preview(self, frame_bytes, remember)

    def update_live_preview_from_last_frame(self) -> None:
        return live_preview.update_live_preview_from_last_frame(self)

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        return live_webcam.closeEvent(self, event)


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
