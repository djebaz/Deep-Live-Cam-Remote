# Unreleased

## Added
- Add an Outputs photo auto-play seconds control and prefetch a configurable number of upcoming photos while photo auto-play is enabled.
- Add Outputs photo preview zoom choices for fit, 0.5x, 0.8x, 1x, 1.5x, and 2x.
- Add a guarded GitHub CLI PR helper script to block accidental PR creation against upstream `hacksider/Deep-Live-Cam`.
- Add an isolated standalone desktop app build workflow with `.venv_build/`, `requirements-build.txt`, and `scripts/build_remote_app.ps1` for PyInstaller packaging.
- Add a Lite PyInstaller build mode that excludes Live webcam dependencies (`cv2`, `numpy`, `pyvirtualcam`) for a smaller desktop controller executable.
- Add versioned PyInstaller artifact naming, versioned `dist/<version>/` output folders, Python-version suffixes, final output checks, and build summary logging.
- Add manual GitHub Actions workflows for desktop app builds and existing-release asset uploads, without UPX support.
- Add Live webcam selectors for InsightFace model pack (`buffalo_l`, `buffalo_m`, `buffalo_s`) and swapper precision (`fp32`, `fp16`), with `buffalo_l`/`fp32` kept as the safest baseline for `inswapper_128`.
- Cache the live source face embedding once when the Colab live engine starts and reuse it across live frames.
- Report the requested and loaded live swapper precision plus model path in live backend diagnostics/perf events.
- Add configurable buffered, fixed-cadence live preview rendering that delays frames briefly, coalesces bursty WebSocket arrivals, and drops stale preview frames for smoother timing.
- Add experimental Live webcam frame codec controls for JPEG/WebP send and return frames, with frame quality and codec fields in live backend/perf diagnostics.
- Add a Live preview size control for fit, real pixels, 1.5x, and 2x, capped to the preview panel size.
- Add Live hot-change support for tuning controls (opacity, sharpness, mouth mask, many faces, codecs, detection settings, capture scale, pipeline frames) over websocket without restarting, with strict float/int validation that rejects invalid or out-of-range values without mutating active config.
- Replace raw Live capture width/height controls with Capture backend (DirectShow/MSMF/auto), Capture mode (auto/opencv_auto/custom), and Send scale: Auto mode reads the active OBS profile canvas size from global.ini/basic.ini on Windows, opencv_auto lets OpenCV negotiate, custom requests explicit dimensions at startup, and Send scale remains hot-change before websocket encoding.
- Add Live capture threading with separate grab/retrieve for continuous webcam reading, dropped/duplicate frame tracking, capture age metrics, and backpressure handling.
- Add Live performance testing with a perf test button that cycles through codec combinations and exports detailed CSV metrics (client/server/receiver FPS, timing breakdowns, frame stats) with warmup period handling.
- Reopen virtual camera automatically when returned frame size changes due to hot-change capture scale updates.
- **Windows Remote App**: PySide6 desktop app for controlling Colab batch processing over Tailscale
  - Dark title bar and custom app icon on Windows 10/11
  - Photos and Videos tabs with full processing options (recursive, overwrite, skip processed, many faces, enhancer, opacity, sharpness, mouth mask, interpolation, poisson blend, color correction)
  - Video percentage range (start/end %) to process only portions of videos
  - Start/Stop toggle buttons with graceful cancel
  - Outputs tab with resizable split view, preview/player, and autoplay with prefetch
  - Local file upload support for source faces and input folders
  - Settings sync between Photos and Videos tabs
- **Colab Notebook Enhancements**:
  - Resumable cells: Clone/install, Tailscale install, and auth cells skip completed steps
  - Auto-update on re-run: setup cell runs `git pull` when repo exists
  - Local input/output directories for Windows app uploads
  - Sample data cleanup and nvtop installation

## Fixed
- Keep the Live preview timer cadence aligned when OBS auto-detects a different capture FPS after startup.
- Cap Live transport packet batching client-side so large frames flush the current batch before oversized multi-frame websocket messages are built.
- Make Live Stop tear down the paired websocket sender/receiver tasks as soon as either side exits, so stopping is not held open waiting for another backend frame.
- Make remote photo/video batch cancel checks run during the active item where practical, including the video frame loop, so cancellation is not limited to the next file boundary.

## Changed
- Continue Windows app modularization by extracting settings, API client, Qt worker, and shared window core ownership from the PR #5 compatibility layer, then replacing broad `app_base as base` GUI imports with explicit module imports, removing Live webcam previous-function capture, removing migration mixin composition, and splitting task running, output browsing, live options, and live preview responsibilities into focused modules.
- Consolidate the Windows remote app runtime patch layers into normal imported modules and a canonical launcher entrypoint.
- Notebook now clones from GitHub instead of embedding Python source as a bundle
- Setup cell is idempotent and pulls latest changes on re-run

## Release audit

- PRs: #1, #2, #3, #4, #5, #6, #7, #8; upstream integration ready for review: #10 (source proposal: #9)
- Scope: PR #1 added Colab/remote/batch face-swap workflows; PR #2 adds standalone desktop app build scaffolding, versioned artifacts, Lite packaging, and manual build/release GitHub Actions; PR #3 separates photo and video processing options; PR #4 fixes Live webcam source upload and frame geometry; PR #5 consolidates Windows app patch layers; PR #6 extracts Windows app settings, API client, worker, and window core ownership; shrinks `app_base.py` into a compatibility shim; converts migration mixins to explicit methods; removes stale `async_base` aliases; replaces broad `app_base as base` imports; removes Live webcam previous-function capture; replaces migration mixin composition with explicit `MainWindow` delegates; splits output browsing, task running, live options, and live preview modules; and adds a downstream PR guard; PR #7 adds Live hot-change controls with runtime tuning over websocket, OBS profile auto-detection, capture backend/mode/scale configuration, strict input validation, capture threading with performance metrics, perf test CSV export, and virtual camera resize handling; PR #8 speeds up Stop handling by cancelling paired Live websocket tasks promptly and adding cooperative in-item cancel checks for photo/video batches.


### Upstream integration — PR #10

Source proposal: [PR #9](https://github.com/djebaz/Deep-Live-Cam-Remote/pull/9), 48 upstream commits through `a92427518a8bf89fee2432a9fccd0a61fb4c2654`. See the [integration guide](../features/upstream-pr-9-integration.md) for dependency profiles and migration steps.

Added:

- Persisted capture resolution and detection size selectors in the local app, plus CLI `--det-size`.
- Central TLS-verified resumable model downloads, default InsightFace pack provisioning, Turkish translations, Dependabot and a compilation workflow.
- Upstream regression tests for video fallback, TLS verification, local preview/source handling and FPS fallback.

Fixed:

- Local preview worker shutdown and failed-camera close handling; recovery after an unreadable source change.
- Random-face download staging so invalid downloads preserve the current source image.
- Face-mapping disk video fallback, frame seeking bounds and FPS fallback.
- CoreML detection cache reuse across different input shapes and shared OpenVINO configuration/Windows DLL registration.

Changed and preserved for this fork:

- Root requirements adopt NumPy 2, newer OpenCV/ONNX Runtime, Keras 3/OpenNSFW2 and declared backend dependencies; retain scikit-learn.
- Keep explicit remote model-pack and fp32/fp16 selection with `buffalo_l`/fp32 defaults; unify the detector-size setter with the local setting.
- Keep enhancer helper APIs, incomplete-model thresholds, GPEN fallback sources and the fp16 fallback source with the centralized downloader.
- Keep Colab's NumPy 1 / ORT GPU 1.23.2 profile and desktop packaging's separate build profile; add certifi to notebook installation/readiness and regenerate the notebook.
- Shared image extension handling includes WebP. The API, batch entry point and remote controller files are unchanged, but use updated shared modules.

Validation: syntax compilation passed for 22 changed Python sources; whitespace and conflict-marker checks passed; notebook rebuilt with `--eol lf`. Tests, dependency installation, desktop builds and Colab/GPU/manual camera checks remain pending. User smoke testing confirmed Tailscale API connectivity, a successful 19-photo batch (0 failed), and all 19 skipped on repeat with the latest desktop build. PR #10 is ready for review and has not been merged. GPU acceleration remains unverified.

Ruff 0.15.7 validation: the repository-wide run reports 83 pre-existing findings, also present on the downstream base `867d7e5`. The one additional finding introduced by this PR (the certifi readiness import) was annotated as intentional. Existing lint debt remains; the Ruff workflow is not green.

### Colab CUDA initialization follow-up

- Install ONNX Runtime GPU 1.23.2 with CUDA/cuDNN runtime extras in both notebooks, including on re-runs where packages already import successfully.
- Preload NVIDIA pip libraries before batch/Live ONNX initialization; log active swapper providers and explicitly warn about CPU fallback.
- Add certifi to the mini notebook and correct its stale clone branch to `main`; regenerate both notebook artifacts.
- User's direct swapper probe confirmed missing `libcublasLt.so.12` and CPU-only fallback. GPU validation of this repair is pending; syntax/whitespace checks passed.

### Tested Colab cuDNN pin

- Pin `nvidia-cudnn-cu12==9.26.0.51` in both notebook setup paths. The user observed cuDNN 9.27 runtime convolution failures, CPU fallback and failed GFPGAN enhancement despite successful CUDA session creation.
- After downgrade/restart, the supplied excerpt shows CUDA graph initialization and successful photo processing without cuDNN/fallback errors; monitoring confirms sustained T4 GPU work and about 6.1 GiB VRAM. The final 90-photo completion summary was not supplied.
