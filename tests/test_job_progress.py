"""Structured per-file progress for batch jobs."""
import colab_api as api
import colab_batch as batch


def test_merge_progress_derives_percentages_and_eta():
    p = api.merge_progress(None, {"item": 2, "items": 4, "name": "a.mp4", "state": "processing",
                                  "frames": 50, "total": 200, "fps": 10.0})
    assert p["file_percent"] == 25.0
    assert abs(p["overall_percent"] - 31.25) < 0.1  # (1 + .25) / 4
    assert p["eta_seconds"] == 15.0


def test_new_item_resets_per_file_fields_and_done_counts_as_complete():
    first = api.merge_progress(None, {"item": 1, "items": 2, "frames": 10, "total": 10, "fps": 5.0, "state": "processing"})
    second = api.merge_progress(first, {"item": 2, "items": 2, "state": "processing"})
    assert "frames" not in second and second["file_percent"] is None and second["overall_percent"] == 50.0
    done = api.merge_progress(second, {"item": 2, "items": 2, "state": "done"})
    assert done["file_percent"] == 100.0 and done["overall_percent"] == 100.0 and done["eta_seconds"] is None


def test_unknown_total_has_no_file_percent():
    p = api.merge_progress(None, {"item": 1, "items": 1, "frames": 30, "total": None, "fps": 6.0, "state": "processing"})
    assert p["file_percent"] is None and p["eta_seconds"] is None and p["overall_percent"] == 0.0


def test_job_snapshot_exposes_progress():
    job = api.JobState(job_id="j", kind="videos")
    assert job.snapshot()["progress"] is None
    job.set_progress({"item": 1, "items": 1, "frames": 1, "total": 2, "fps": 1.0})
    assert job.snapshot()["progress"]["file_percent"] == 50.0


def test_batch_reports_item_progress_through_the_sink(tmp_path, monkeypatch):
    inp, out = tmp_path / "in", tmp_path / "out"
    inp.mkdir()
    for name in ("a.mp4", "b.mp4"):
        (inp / name).write_bytes(b"x")
    args = batch.build_parser().parse_args(["process", "--input-dir", str(inp), "--output-dir", str(out)])
    seen = []
    args.progress_cb = seen.append

    class Engine:
        def __init__(self, config):
            pass

    def fake_one(_video, output, relative, _config, engine, _cancel):
        batch.report_progress(engine, frames=5, total=10, fps=2.0)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"ok")
        return {"size_mb": 0.0}

    monkeypatch.setattr(batch, "ModernEngine", Engine)
    monkeypatch.setattr(batch, "process_one", fake_one)
    assert batch.process_batch(args) == 0
    names = [(p["item"], p["name"], p["state"], p.get("frames")) for p in seen]
    assert names == [(1, "a.mp4", "processing", None), (1, "a.mp4", "processing", 5), (1, "a.mp4", "done", None),
                     (2, "b.mp4", "processing", None), (2, "b.mp4", "processing", 5), (2, "b.mp4", "done", None)]


def test_report_progress_never_raises():
    class Bad:
        def progress(self, fields):
            raise RuntimeError("boom")

    batch.report_progress(Bad(), frames=1)
    batch.report_progress(object(), frames=1)
