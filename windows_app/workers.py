from __future__ import annotations

import asyncio
import json
import time

from PySide6.QtCore import QThread, Signal

from windows_app.api_client import ApiClient
from windows_app.settings import AppSettings


class LiveWorker(QThread):
    message = Signal(str)
    frame = Signal(bytes)

    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            asyncio.run(self._run_live())
        except Exception as exc:
            self.message.emit(f"live stopped: {exc}")

    async def _run_live(self) -> None:
        import cv2
        import websockets

        uri = self.settings.base_url.replace("http://", "ws://") + "/ws/live"
        self.message.emit(f"connecting live websocket: {uri}")
        cap = cv2.VideoCapture(self.settings.camera_index)
        if not cap.isOpened():
            raise RuntimeError(f"could not open camera index {self.settings.camera_index}")
        virtual_cam = None
        try:
            async with websockets.connect(uri, max_size=8 * 1024 * 1024) as websocket:
                await websocket.send(
                    json.dumps(
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
                    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    if not ok:
                        continue
                    await websocket.send(encoded.tobytes())
                    reply = await websocket.recv()
                    if isinstance(reply, str):
                        self.message.emit(reply)
                        continue
                    self.frame.emit(reply)
                    if virtual_cam is None:
                        try:
                            import pyvirtualcam

                            decoded = cv2.imdecode(
                                __import__("numpy").frombuffer(reply, dtype=__import__("numpy").uint8),
                                cv2.IMREAD_COLOR,
                            )
                            h, w = decoded.shape[:2]
                            virtual_cam = pyvirtualcam.Camera(
                                width=w,
                                height=h,
                                fps=20,
                                device=self.settings.virtual_camera or None,
                            )
                            self.message.emit(f"virtual camera opened: {virtual_cam.device}")
                        except Exception as exc:
                            self.message.emit(f"virtual camera unavailable: {exc}")
                            virtual_cam = False
                    if virtual_cam:
                        import numpy as np

                        decoded = cv2.imdecode(np.frombuffer(reply, dtype=np.uint8), cv2.IMREAD_COLOR)
                        rgb = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
                        virtual_cam.send(rgb)
                        virtual_cam.sleep_until_next_frame()
        finally:
            cap.release()
            if virtual_cam and hasattr(virtual_cam, "close"):
                virtual_cam.close()
            self.message.emit("live worker stopped")


class PollWorker(QThread):
    message = Signal(str)
    finished_status = Signal(str)

    def __init__(self, client: ApiClient, job_id: str):
        super().__init__()
        self.client = client
        self.job_id = job_id
        self._seen = 0
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        while not self._stop:
            try:
                payload = self.client.request_json("GET", f"/jobs/{self.job_id}", timeout=5)
                logs = payload.get("logs") or []
                for line in logs[self._seen:]:
                    self.message.emit(str(line))
                self._seen = len(logs)
                status = payload.get("status", "unknown")
                if status not in {"queued", "running"}:
                    self.finished_status.emit(status)
                    return
            except Exception as exc:
                self.message.emit(f"poll error: {exc}")
            time.sleep(1.0)


__all__ = ["LiveWorker", "PollWorker"]
