"""Preview scheduling regressions; packet timing requires no camera or models."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from windows_app import live_preview as preview
from windows_app.settings import AppSettings


class PreviewClockTest(unittest.TestCase):
    def setUp(self):
        self.window = SimpleNamespace(
            settings=AppSettings(),
            _live_preview_buffer=preview.create_live_preview_buffer(),
            _live_preview_buffer_seconds=1.0,
            _live_preview_clock_started_at=None,
            _live_preview_current_seq=None,
        )
        self.window.settings.live_fps = 20

    def enqueue(self, now, seq, capture_monotonic, capture_time=1000.0):
        with patch.object(preview.time, 'monotonic', return_value=now):
            preview.enqueue_live_preview_frame_packet(
                self.window, {
                    'seq': seq,
                    'capture_monotonic': capture_monotonic,
                    'capture_time': capture_time,
                }, str(seq).encode()
            )

    def render(self, now):
        with patch.object(preview.time, 'monotonic', return_value=now), \
                patch.object(preview, 'update_live_preview') as display:
            preview.render_live_preview_frame(self.window)
            return display

    def test_actual_25_fps_with_requested_20_keeps_advancing(self):
        self.enqueue(100.0, 0, 1000.0)
        self.assertFalse(self.render(100.99).called)
        self.assertEqual(self.render(101.01).call_args.args[1], b'0')
        # A completed frame after 40 seconds of 25 FPS capture. The old
        # sequence clock only reaches 800 and refuses to display sequence 1000.
        self.enqueue(140.0, 1000, 1040.0)
        self.assertEqual(self.render(141.01).call_args.args[1], b'1000')

    def test_late_frames_after_gap_recover_immediately(self):
        self.enqueue(100.0, 0, 1000.0)
        self.render(101.01)
        self.enqueue(110.0, 200, 1008.0)
        self.enqueue(110.0, 225, 1009.0)
        self.assertEqual(self.render(110.01).call_args.args[1], b'225')
        self.assertFalse(self.window._live_preview_buffer)

    def test_missing_or_invalid_timestamps_use_arrival_buffer(self):
        for stamp in ('', None, 'NaN', 'inf', -1):
            with self.subTest(stamp=stamp):
                self.setUp()
                self.enqueue(100.0, 500, stamp)
                self.assertFalse(self.render(100.99).called)
                self.assertEqual(self.render(101.01).call_args.args[1], b'500')

    def test_duplicate_sequence_zero_is_not_displayed_twice(self):
        self.enqueue(100.0, 0, 1000.0)
        self.render(101.01)
        self.enqueue(101.02, 0, 1000.0)
        self.assertFalse(self.render(101.03).called)

    def test_wall_clock_changes_do_not_shift_playback_deadlines(self):
        for adjustment in (3600.0, -3600.0):
            with self.subTest(adjustment=adjustment):
                self.setUp()
                self.enqueue(100.0, 0, 50.0, capture_time=10000.0)
                self.render(101.01)
                self.enqueue(102.0, 50, 52.0, capture_time=10002.0 + adjustment)
                self.assertFalse(self.render(102.99).called)
                self.assertEqual(self.render(103.01).call_args.args[1], b'50')

    def test_legacy_wall_clock_only_packets_use_arrival_buffer(self):
        for wall_time in (1000.0, 4600.0, -2600.0):
            with self.subTest(wall_time=wall_time):
                self.setUp()
                self.enqueue(100.0, 0, None)
                self.render(101.01)
                with patch.object(preview.time, 'monotonic', return_value=102.0):
                    preview.enqueue_live_preview_frame_packet(
                        self.window, {'seq': 50, 'capture_time': wall_time}, b'50'
                    )
                self.assertFalse(self.render(102.99).called)
                self.assertEqual(self.render(103.01).call_args.args[1], b'50')

    def test_zero_monotonic_timestamp_is_valid(self):
        self.enqueue(100.0, 0, 0.0)
        self.render(101.01)
        self.enqueue(102.0, 50, 0.5)
        self.assertEqual(self.render(102.01).call_args.args[1], b'50')


if __name__ == '__main__':
    unittest.main()
