# Plan: Live Capture Scale From Actual Webcam Frames

## Goal

Replace raw Live capture width/height inputs with a safer **Capture scale** control based on the actual frame size read from the webcam. The app should detect the real camera frame dimensions from `cap.read()`, preserve the true aspect ratio, and resize locally before websocket encoding when a fractional scale is selected.

This keeps camera setup simple while still giving speed/quality control.

## Scope

In:

- Add Live capture scale options: `auto`, `1x`, `3/4x`, `2/3x`, `1/2x`, `1/3x`, `1/4x`.
- Detect real frame dimensions from actual decoded webcam frames.
- Resize locally before encoding/sending frames.
- Show/log actual camera size and sent frame size.
- Persist the selected scale in Live options.

Out:

- Hot-changing physical camera device, FPS, or virtual camera device.
- Backend changes: backend already reads actual received frame dimensions.
- Enumerating all camera-supported modes.

## UX

Replace:

```text
Capture width
Capture height
```

With:

```text
Capture scale: Auto / 1x / 3/4x / 2/3x / 1/2x / 1/3x / 1/4x
```

Keep:

```text
Capture FPS
Process max width
Preview size
```

Show status like:

```text
webcam capture: actual 1280x720@30.0, send 640x360 (1/2x), pipeline 42
```

## Option Model

Update `windows_app/live_options.py`.

```python
DEFAULT_LIVE_CAPTURE_SCALE = "auto"
LIVE_CAPTURE_SCALES = ("auto", "1x", "3/4x", "2/3x", "1/2x", "1/3x", "1/4x")
LIVE_CAPTURE_SCALE_FACTORS = {
    "auto": None,
    "1x": 1.0,
    "3/4x": 3 / 4,
    "2/3x": 2 / 3,
    "1/2x": 1 / 2,
    "1/3x": 1 / 3,
    "1/4x": 1 / 4,
}
```

Add to `LIVE_OPTION_KEYS`:

```python
"capture_scale",
```

Add to `_default_live_options()`:

```python
"capture_scale": DEFAULT_LIVE_CAPTURE_SCALE,
```

Add to `_coerce_live_options()`:

```python
options["capture_scale"] = str(options["capture_scale"]).lower()
if options["capture_scale"] not in LIVE_CAPTURE_SCALES:
    options["capture_scale"] = DEFAULT_LIVE_CAPTURE_SCALE
```

## UI Changes

Update `windows_app/live_webcam.py` imports:

```python
DEFAULT_LIVE_CAPTURE_SCALE,
LIVE_CAPTURE_SCALES,
LIVE_CAPTURE_SCALE_FACTORS,
```

Remove or hide raw capture width/height controls from the Live tab.

Add:

```python
self.live_capture_scale = QComboBox()
self.live_capture_scale.addItems(list(LIVE_CAPTURE_SCALES))
self.live_capture_scale.setToolTip(
    "Scale the actual webcam frame before sending it. The real camera ratio is preserved."
)
```

In `_read_live_options()`:

```python
"capture_scale": self.live_capture_scale.currentText(),
```

In `_apply_live_options_to_widgets()`:

```python
window.live_capture_scale.setCurrentText(str(options["capture_scale"]))
```

In the form:

```python
form.addRow("Capture scale", self.live_capture_scale)
```

Remove:

```python
form.addRow("Capture width", self.live_width)
form.addRow("Capture height", self.live_height)
```

Or leave them only under a later `Custom` mode.

## Actual Frame Detection

Do not trust only:

```python
cap.get(cv2.CAP_PROP_FRAME_WIDTH)
cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
```

Trust the decoded frame:

```python
def _read_warm_camera_frame(cap: Any, attempts: int = 10) -> Any:
    last = None
    for _ in range(attempts):
        ok, frame = cap.read()
        if ok and frame is not None:
            last = frame
    if last is None:
        raise RuntimeError("could not read webcam frame")
    return last
```

Use it after opening/configuring the camera:

```python
first_frame = _read_warm_camera_frame(cap)
actual_height, actual_width = first_frame.shape[:2]
```

## Scale Helpers

Add helpers in `windows_app/live_webcam.py`.

```python
def _even_dimension(value: int) -> int:
    return max(2, int(value) // 2 * 2)


def _capture_scale_factor(scale: str) -> float | None:
    normalized = str(scale or DEFAULT_LIVE_CAPTURE_SCALE).lower()
    return LIVE_CAPTURE_SCALE_FACTORS.get(normalized)


def _scaled_frame_size(frame: Any, scale: str) -> tuple[int, int]:
    height, width = frame.shape[:2]
    factor = _capture_scale_factor(scale)
    if factor is None:
        return width, height
    return _even_dimension(width * factor), _even_dimension(height * factor)


def _resize_for_capture_scale(frame: Any, scale: str) -> Any:
    target_width, target_height = _scaled_frame_size(frame, scale)
    height, width = frame.shape[:2]
    if (target_width, target_height) == (width, height):
        return frame
    return cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
```

If avoiding a module-level `cv2` import, pass `cv2` into `_resize_for_capture_scale()`.

## Worker Startup

Current code requests width/height:

```python
requested_width = _live_setting(self.settings, "live_width", DEFAULT_LIVE_WIDTH)
requested_height = _live_setting(self.settings, "live_height", DEFAULT_LIVE_HEIGHT)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, requested_width)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, requested_height)
```

Replace width/height request with detected actual size plus scale:

```python
requested_fps = _live_setting(self.settings, "live_fps", DEFAULT_LIVE_FPS)
capture_scale = str(getattr(self.settings, "capture_scale", DEFAULT_LIVE_CAPTURE_SCALE)).lower()

cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FPS, requested_fps)

first_frame = _read_warm_camera_frame(cap)
actual_height, actual_width = first_frame.shape[:2]
actual_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
send_width, send_height = _scaled_frame_size(first_frame, capture_scale)

self.message.emit(
    f"webcam capture: actual {actual_width}x{actual_height}@{actual_fps:.1f}, "
    f"send {send_width}x{send_height} ({capture_scale}), pipeline {pipeline_frames}"
)
```

Important: the first warmed frame can be reused as the first frame to avoid wasting it, but this is optional.

## Sender Resize

Before encoding each frame:

```python
current_capture_scale = str(self._runtime_value("capture_scale", capture_scale)).lower()
frame = _resize_for_capture_scale(frame, current_capture_scale)
```

Then existing encoding continues:

```python
ok, encoded = cv2.imencode(encode_ext, frame, [encode_flag, current_frame_quality])
```

## Hot Change

Add `capture_scale` to local hot-change keys because it is client-only and does not need a backend update.

Do not include it in the backend `LIVE_HOT_CHANGE_KEYS`.

Client payload:

```python
LIVE_LOCAL_HOT_CHANGE_KEYS = (
    "capture_scale",
    "live_pipeline_frames",
)
```

Runtime update still works:

```python
with self._runtime_config_lock:
    self._runtime_config.update(next_payload)
```

When sending backend updates, filter only backend keys:

```python
server_update = {key: update[key] for key in LIVE_HOT_CHANGE_KEYS if key in update}
```

That means `capture_scale` changes immediately on the Windows sender without touching Colab.

## Debounce Hot-Change UI

Avoid sending one update per spinbox tick.

In `_build_live_tab()`:

```python
self._live_hot_change_timer = QTimer(self)
self._live_hot_change_timer.setSingleShot(True)
self._live_hot_change_timer.setInterval(200)
self._live_hot_change_timer.timeout.connect(lambda: _apply_live_hot_change(self))
```

In `_connect_live_hot_change_controls()`:

```python
def changed(*_args: object) -> None:
    timer = getattr(window, "_live_hot_change_timer", None)
    if timer is not None:
        timer.start()
    else:
        _apply_live_hot_change(window)
```

For checkboxes/combos you can either use the same debounce or apply immediately. Same debounce is simpler.

## Geometry Log Noise

Backend currently re-logs geometry after every config update if `geometry_logged = False`.

Only reset geometry logging for real geometry/diagnostic changes:

```python
GEOMETRY_LOG_KEYS = {
    "max_width",
    "detector_size",
    "detect_every_n",
    "frame_codec",
    "output_codec",
}

if GEOMETRY_LOG_KEYS.intersection(update):
    geometry_logged = False
```

Do not reset geometry logging for plain quality changes unless you really want a visible backend confirmation. The `live_config_updated` ack is enough.

## Settings Migration

Keep reading old `live_width` and `live_height` from app state for backward compatibility, but do not expose them by default.

Suggested default:

```python
"capture_scale": "1/2x"
```

If you prefer least surprise:

```python
"capture_scale": "auto"
```

For your current Live performance work, `1/2x` is probably the best default.

## Validation

Run:

```powershell
python -m py_compile .\windows_app\live_webcam.py .\windows_app\live_options.py .\windows_app\live_preview.py .\colab_api.py
```

Manual checks:

1. Start Live with `Capture scale = auto`.
2. Confirm log shows actual camera frame and send size.
3. Switch to `1/2x` while Live runs.
4. Confirm no reconnect happens.
5. Confirm `in_kb` drops in `live_perf`.
6. Switch back to `1x`.
7. Confirm frame size and preview update.
8. Change `Frame quality` quickly and confirm updates are debounced.
9. Confirm no repeated `live_geometry` spam for every quality tick.

## Expected Outcome

The user no longer has to guess capture width/height. Live detects the true webcam frame size from the actual decoded frame, preserves the camera ratio, and sends a scaled version that is predictable and easy to tune.

## Implementation Status

- [x] Added persisted `capture_scale` live option with `auto`, `1x`, `3/4x`, `2/3x`, `1/2x`, `1/3x`, `1/4x`, and `custom`; default is `auto` with Send scale `auto`; Auto attempts to read the current OBS profile canvas size and request it before warm frame verification.
- [x] Replaced visible raw capture width/height controls with Capture mode plus Send scale controls while preserving legacy width/height settings for backward-compatible state reads.
- [x] LiveWorker now opens the selected capture backend, requests the detected OBS profile canvas size in Auto mode when available, requests custom capture dimensions from OBS/OpenCV in Custom mode, warms the camera from decoded frames, warns when actual frame shape does not match the requested OBS/custom size, logs backend/preferred/actual/send sizes, and applies hot-change Send scale before encoding.
- [x] Made custom capture width/height restart-only so sizes such as `120x720` or `1400x200` are requested from OBS/OpenCV before the warm frame read instead of being send-side distortion.
- [x] Reopen the local virtual camera if returned frame dimensions change after a hot Send scale update.
- [x] Added Capture backend selector (`auto`, `directshow`, `msmf`) with `directshow` as the default for OBS Virtual Camera custom-resolution negotiation on Windows.
- [x] Added OBS profile `basic.ini` probing so Auto capture mode can request the current OBS canvas size before reading the warm frame.
- [x] Changed OBS-oriented migration to keep Capture mode `auto`, set Send scale `auto`, and let Auto request the OBS profile canvas size instead of allowing `auto + 1/2x` to negotiate/send 640x480-derived frames.
- [x] Debounced Live hot-change UI updates with a 200 ms timer.
- [x] Limited backend geometry re-log resets to geometry/codec/detection changes, added strict integer hot-change validation, and bumped the Live API version to `live-hot-change-v11`.
- [x] Updated README, AGENTS, and unreleased notes.
- [x] Ran `python -m py_compile .\windows_app\live_webcam.py .\windows_app\live_options.py .\windows_app\live_preview.py .\colab_api.py` using `.venv_build`.

## Deferred Validation

- [ ] Final tests and smoke tests deferred to user.
- [ ] Manual webcam checks from the original plan deferred to user.

