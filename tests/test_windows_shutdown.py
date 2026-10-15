"""Closing the Windows app must not leave a running QThread behind (Qt aborts the process)."""
import pytest

pytest.importorskip("PySide6.QtCore")

from windows_app.workers import stop_thread  # noqa: E402


class FakeSignal:
    def __init__(self):
        self.disconnected = False

    def disconnect(self):
        self.disconnected = True


class FakeThread:
    def __init__(self, finishes: bool):
        self.finishes = finishes
        self.running = True
        self.terminated = False
        self.waits = []
        self.succeeded = FakeSignal()
        self.finished = FakeSignal()

    def isRunning(self):
        return self.running

    def wait(self, ms):
        self.waits.append(ms)
        if self.finishes or self.terminated:
            self.running = False
            return True
        return False

    def terminate(self):
        self.terminated = True


def test_none_is_ignored():
    stop_thread(None)


def test_finishing_thread_is_waited_for_not_terminated():
    thread = FakeThread(finishes=True)
    stop_thread(thread, grace_ms=50)
    assert thread.waits == [50] and not thread.terminated
    assert thread.succeeded.disconnected and thread.finished.disconnected


def test_stuck_thread_is_terminated_after_the_grace_period():
    thread = FakeThread(finishes=False)
    stop_thread(thread, grace_ms=50)
    assert thread.terminated and not thread.running
    assert thread.waits == [50, 1000]


def test_real_qthread_that_already_finished_is_fine():
    from PySide6.QtCore import QThread

    thread = QThread()
    stop_thread(thread)
    assert not thread.isRunning()
