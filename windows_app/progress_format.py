"""Qt-free formatting of the Colab API's structured batch progress."""

from __future__ import annotations

from typing import Any


def format_eta(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    if s < 60:
        return f"{s}s"
    minutes, sec = divmod(s, 60)
    if minutes < 60:
        return f"{minutes}m {sec:02d}s"
    return f"{minutes // 60}h {minutes % 60:02d}m"


def describe_progress(progress: Any) -> tuple[str, float | None] | None:
    """(status text, overall percent or None) for a job's `progress` payload, or None."""
    if not isinstance(progress, dict) or not progress.get("items"):
        return None
    parts = [f"Item {progress.get('item')} / {progress.get('items')}"]
    name = str(progress.get("name") or "")
    if name:
        parts.append(name.rsplit("/", 1)[-1])
    state = progress.get("state") or "processing"
    if state == "processing":
        if progress.get("file_percent") is not None:
            parts.append(f"{round(float(progress['file_percent']))}%")
        elif progress.get("frames"):
            parts.append(f"{progress['frames']} frames")
        fps = progress.get("fps") or 0
        if fps and float(fps) > 0:
            parts.append(f"{float(fps):.1f} fps")
        if progress.get("eta_seconds") is not None:
            parts.append(f"~{format_eta(float(progress['eta_seconds']))} left")
    elif state in {"skipped", "failed"}:
        parts.append(str(state))
    overall = progress.get("overall_percent")
    return " · ".join(parts), (float(overall) if overall is not None else None)
