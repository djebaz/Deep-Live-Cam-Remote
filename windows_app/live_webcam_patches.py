from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from windows_app import app as base
from windows_app import async_outputs as async_base
from windows_app import processing_options_patches as processing_base
from windows_app import ui_patches as ui_base


def _prepare_live_settings(settings: base.AppSettings) -> dict[str, Any]:
    client = base.ApiClient(settings)
    logs: list[str] = ["checking Colab API before starting live"]
    client.request_json("GET", "/health", timeout=5.0)

    live_settings = async_base._copy_settings(settings)
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


class RatioPreservingLiveWorker(base.LiveWorker):
    async def _run_live(self) -> None:
        import cv2
        import numpy as np
        import websockets

        uri = self.settings.base_url.replace("http://", "ws://") + "/ws/live"
        cap = cv2.VideoCapture(self.settings.camera_index)
        if not cap.isOpened():
            raise RuntimeError(f"could not open camera index {self.settings.camera_index}")

        virtual_cam = None
        logged_resize = False
        try:
            self.message.emit(f"connecting live websocket: {uri}")
            async with websockets.connect(uri, max_size=8 * 1024 * 1024) as websocket:
                await websocket.send(
                    base.json.dumps(
                        {
                            "source_face": self.settings.source_face,
                            "enhancer": self.settings.enhancer,
                            "many_faces": self.settings.many_faces,
                            "jpeg_quality": 80,
                        }
                    )
                )
                ready = await websocket.recv()
                self.message.emit(f"live backend: {ready}")
                while not self._stop:
                    ok, frame = cap.read()
                    if not ok:
                        await asyncio.sleep(0.03)
                        continue

                    frame_h, frame_w = frame.shape[:2]
                    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    if not ok:
                        continue
                    await websocket.send(encoded.tobytes())
                    reply = await websocket.recv()
                    if isinstance(reply, str):
                        self.message.emit(reply)
                        continue

                    decoded = cv2.imdecode(np.frombuffer(reply, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if decoded is None:
                        self.message.emit("live backend returned an invalid frame")
                        continue
                    out_h, out_w = decoded.shape[:2]
                    if (out_w, out_h) != (frame_w, frame_h):
                        interpolation = cv2.INTER_AREA if out_w > frame_w or out_h > frame_h else cv2.INTER_LINEAR
                        decoded = cv2.resize(decoded, (frame_w, frame_h), interpolation=interpolation)
                        if not logged_resize:
                            self.message.emit(f"live output resized from {out_w}x{out_h} to webcam frame {frame_w}x{frame_h}")
                            logged_resize = True

                    ok, normalized_reply = cv2.imencode(".jpg", decoded, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    if not ok:
                        continue
                    normalized_bytes = normalized_reply.tobytes()
                    self.frame.emit(normalized_bytes)

                    if virtual_cam is None:
                        try:
                            import pyvirtualcam

                            virtual_cam = pyvirtualcam.Camera(
                                width=frame_w,
                                height=frame_h,
                                fps=20,
                                device=self.settings.virtual_camera or None,
                            )
                            self.message.emit(f"virtual camera opened: {virtual_cam.device}")
                        except Exception as exc:
                            self.message.emit(f"virtual camera unavailable: {exc}")
                            virtual_cam = False
                    if virtual_cam:
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
    if hasattr(processing_base, "_apply_processing_options_to_settings"):
        # Live processes image frames, so use the Photos processing profile.
        processing_base._apply_processing_options_to_settings(self.settings, "photos")
        base.save_settings(self.settings)
    settings = async_base._copy_settings(self.settings)
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
        self.live_worker = RatioPreservingLiveWorker(live_settings)
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


def install() -> None:
    base.MainWindow.start_live = start_live


install()
main = base.main
