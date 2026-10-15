"""A declared batch whose completed uploads become available to one processor."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Iterator


class UploadBatch:
    # Longer than the clients' ten-minute upload request timeout. An abandoned
    # browser must not leave a job (and the single engine) waiting indefinitely.
    IDLE_SECONDS = 15 * 60

    def __init__(self, files: list[tuple[Path, int]], signature: tuple[str, ...]):
        self.files = files
        self.signature = signature
        self.ready: set[Path] = set()
        self.complete = False
        self.error: str | None = None
        self.condition = threading.Condition()
        self.last_activity = time.monotonic()

    def __len__(self) -> int:
        return len(self.files)

    def snapshot(self) -> dict[str, object]:
        with self.condition:
            return {"uploaded": len(self.ready), "total": len(self),
                    "complete": self.complete, "error": self.error}

    def contains(self, path: Path) -> bool:
        with self.condition:
            return path in self.ready

    def touch(self) -> None:
        """A large upload is still alive even before multipart parsing completes."""
        with self.condition:
            self.last_activity = time.monotonic()

    def publish(self, path: Path, temporary: Path) -> None:
        with self.condition:
            if self.complete or self.error:
                raise RuntimeError("batch no longer accepts uploads")
            temporary.replace(path)
            self.ready.add(path)
            self.last_activity = time.monotonic()
            self.condition.notify_all()

    def finish(self, error: str | None = None) -> None:
        with self.condition:
            if self.complete:
                return  # safe to repeat a completion request after a lost reply
            self.error = error or (f"Upload ended with {len(self.ready)} of {len(self)} files received"
                                   if len(self.ready) != len(self) else None)
            self.complete = True
            self.condition.notify_all()

    def _wait(self, path: Path | None, cancel: threading.Event, waiting: Callable[[], None]) -> bool:
        since = time.monotonic()
        with self.condition:
            while True:
                if cancel.is_set():
                    return False
                if self.error:
                    raise RuntimeError(self.error)
                if (path is None and self.complete) or (path is not None and path in self.ready):
                    return True
                if self.complete:
                    raise RuntimeError("Upload finished before the declared file was received")
                if time.monotonic() - max(since, self.last_activity) >= self.IDLE_SECONDS:
                    self.error = "Upload interrupted: no upload activity or completion signal for 15 minutes"
                    self.complete = True
                    raise RuntimeError(self.error)
                waiting()
                self.condition.wait(timeout=0.5)

    def wait_first(self, cancel: threading.Event, waiting: Callable[[], None]) -> bool:
        return self._wait(self.files[0][0], cancel, waiting)

    def paths(self, cancel: threading.Event, waiting: Callable[[], None]) -> Iterator[Path]:
        for path, _size in self.files:
            if not self._wait(path, cancel, waiting):
                return
            yield path
        self._wait(None, cancel, waiting)
