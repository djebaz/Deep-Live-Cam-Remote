from windows_app.progress_format import describe_progress, format_eta


def test_format_eta():
    assert format_eta(42) == "42s"
    assert format_eta(80) == "1m 20s"
    assert format_eta(3725) == "1h 02m"


def test_processing_line_has_item_file_percent_fps_and_eta():
    text, percent = describe_progress({
        "item": 2, "items": 4, "name": "nested/clip.mp4", "state": "processing", "frames": 50,
        "total": 200, "fps": 8.25, "file_percent": 25, "overall_percent": 31.3, "eta_seconds": 75,
    })
    assert text == "Item 2 / 4 · clip.mp4 · 25% · 8.2 fps · ~1m 15s left"
    assert percent == 31.3


def test_unknown_total_skipped_and_missing():
    text, percent = describe_progress({"item": 1, "items": 1, "state": "processing", "frames": 30, "fps": 6,
                                       "file_percent": None})
    assert text == "Item 1 / 1 · 30 frames · 6.0 fps" and percent is None
    assert describe_progress({"item": 3, "items": 3, "name": "a.png", "state": "skipped",
                              "overall_percent": 100})[0] == "Item 3 / 3 · a.png · skipped"
    assert describe_progress(None) is None
    assert describe_progress({}) is None
