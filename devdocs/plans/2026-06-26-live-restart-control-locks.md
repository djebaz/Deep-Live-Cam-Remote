# Plan: Live hot-change controls

## Scope
- In: Hot-change Live codec/quality, return codec, process max width, detector size, detect cadence, blend/mask/tuning options, many-faces with cache reset, pipeline frames, preview buffer, and preview size.
- Out: Camera index, capture width/height/FPS, virtual camera device, source face path, InsightFace pack, swapper precision, and enhancer changes remain restart-only.

## Action items
- [x] Inspect branch, repo guidance, current Live tab implementation, backend websocket loop, and release notes.
- [x] Create feature branch for Live hot-change work.
- [x] Create the live plan file and expand it from restart-only locking to full hot-change scope.
- [x] Add a `live_config_update` JSON message type for `/ws/live`; accept it alongside frame bytes and merge validated low-risk options into active config.
- [x] Refactor `LiveWorker` to keep a thread-safe mutable runtime config snapshot and send config-update messages when relevant Live controls change during an active worker.
- [x] Wire UI signals for in-scope controls so changes call an `apply_live_hot_change` path, persist settings, and log update status.
- [x] Apply backend hot changes safely: update geometry/codec/quality/detect options directly; update `modules.globals` for opacity, sharpness, mouth mask, interpolation, poisson/color, and many-faces; clear live detection caches when face-detection behavior changes.
- [x] Make pipeline frames hot-change local-only by reading the mutable runtime value in the sender backpressure loop instead of capturing it once at worker startup.
- [x] Keep preview size immediate as-is, and make preview buffer seconds hot-change by updating `_live_preview_buffer_seconds` without restarting the preview timer.
- [x] Disable restart-only Live controls during live preparation/streaming so they cannot be edited mid-run.
- [x] Update README and unreleased notes to state which Live controls are hot-change and which require restart.
- [x] Run minimal syntax validation only: `python -m py_compile .\windows_app\live_webcam.py .\windows_app\live_preview.py .\colab_api.py`.
- [x] Commit and push the feature branch. Downstream PR is deferred until requested.

## Decisions and Design Changes
- 2026-06-26 Hot changes prioritize responsiveness over exact frame ordering; a change may take effect over the next few frames.
- 2026-06-26 Invalid hot-change payloads should return a websocket JSON error and leave the current Live config unchanged.
- 2026-06-26 Heavy capture/source/model options remain restart-only to avoid stream stalls and model/session reload risk.
- 2026-06-26 Restart-only Live controls are disabled while Live is preparing or running; hot-change candidate controls remain editable.
- 2026-06-26 Tests and smoke tests are deferred to the user per fast-implement.

## Open questions
- None.

## Validation
- [x] `python -m py_compile .\windows_app\live_webcam.py .\windows_app\live_preview.py .\colab_api.py`
- [x] Final tests and smoke tests deferred to user
