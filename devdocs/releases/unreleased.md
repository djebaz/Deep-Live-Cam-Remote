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
- Keep remote Live preview playback deadlines independent of system-clock adjustments by carrying a separate monotonic capture timestamp through the Colab API. Preserve wall-clock latency diagnostics and use arrival-time buffering with older backends.
- Fix remote Live preview freezes when actual capture FPS differs from requested FPS: schedule buffered frames by capture timestamps, recover after sequence gaps, and measure buffer duration from playback deadlines.
- Keep the Live preview timer cadence aligned when OBS auto-detects a different capture FPS after startup.
- Cap Live transport packet batching client-side so large frames flush the current batch before oversized multi-frame websocket messages are built.
- Make Live Stop tear down the paired websocket sender/receiver tasks as soon as either side exits, so stopping is not held open waiting for another backend frame.
- Make remote photo/video batch cancel checks run during the active item where practical, including the video frame loop, so cancellation is not limited to the next file boundary.

## Changed
- Continue Windows app modularization by extracting settings, API client, Qt worker, and shared window core ownership from the PR #5 compatibility layer, then replacing broad `app_base as base` GUI imports with explicit module imports, removing Live webcam previous-function capture, removing migration mixin composition, and splitting task running, output browsing, live options, and live preview responsibilities into focused modules.
- Consolidate the Windows remote app runtime patch layers into normal imported modules and a canonical launcher entrypoint.
- Notebook now clones from GitHub instead of embedding Python source as a bundle
- Setup cell is idempotent and pulls latest changes on re-run

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

### Remote GUI rollback

- Revert the capture preset and shutdown changes from `15799c1` at the user's request after a reported preview freeze. Restore the earlier remote Live implementation while preserving the Colab GPU fixes.
- The preview renderer itself was unchanged; freeze resolution is not verified. A rebuilt Full EXE needs comparison under the same capture settings.

### Colab installation progress

- Add a six-stage display to both Clone and install cells, including elapsed-time/output updates while pip/git/apt subprocesses run, model-download byte progress, and clear completion/failure/interruption states.
- Capture subprocess output in the cell display instead of leaving it only in Colab's server log; preserve useful failure tails, redact clone credentials, and stop child process groups on interruption.
- Remove PySide6 and local camera enumeration from notebook installation by separating processor status reporting from the local GUI import path and explicitly selecting headless mode before Colab processor imports. Preserve GUI status routing and the tested CUDA/cuDNN dependencies. Already-installed packages are not removed.
- Correct the full notebook source clone branch to the documented main default. Rebuild both artifacts with LF and preserve cell IDs/metadata.
- Setup-cell syntax, metadata and whitespace checks passed. Colab fresh/re-run, failure and interrupt smoke checks are pending; automated tests were not run under repository guidance.

### Detailed Colab install substeps

- Print numbered dependency activities and package names from actual pip output: resolution, reused packages, downloads/cache hits, metadata/build preparation, wheel compilation and installation.
- Add visible import-readiness substeps and a persistent heartbeat every 10 seconds with current activity, command elapsed time and time since new output. Updates remain visible even if the HTML display is unavailable or collapsed.
- Separate model-download update timing from text-fallback timing and avoid duplicate stage/heartbeat messages.
- Both notebook setup cells parse and artifacts are regenerated with preserved metadata/cell IDs; runtime Colab checks remain pending.

### Colab NumPy wheel compatibility

- Select NumPy <2 for Python through 3.12, and NumPy >=2.1,<3 for Python 3.13+. Require a binary NumPy wheel so setup does not spend minutes preparing an unsupported NumPy 1.26 source build on Python 3.13.
- Check installed NumPy's version when deciding whether dependencies are ready, display the selected profile, and request a session restart if pip changed a NumPy version already loaded in the kernel.
- PyPI inspection confirmed no Python 3.13 Linux wheels for NumPy 1.26.4 and available wheels for 2.1.0. Fresh Colab/InsightFace compatibility testing remains pending.

## Release audit

- PRs: #1, #2, #3, #4, #5, #6, #7, #8, #10, #11, #12, #13, #14 (source proposal: #9)
- Scope: PR #1 added Colab/remote/batch face-swap workflows; PR #2 adds standalone desktop app build scaffolding, versioned artifacts, Lite packaging, and manual build/release GitHub Actions; PR #3 separates photo and video processing options; PR #4 fixes Live webcam source upload and frame geometry; PR #5 consolidates Windows app patch layers; PR #6 extracts Windows app settings, API client, worker, and window core ownership; shrinks `app_base.py` into a compatibility shim; converts migration mixins to explicit methods; removes stale `async_base` aliases; replaces broad `app_base as base` imports; removes Live webcam previous-function capture; replaces migration mixin composition with explicit `MainWindow` delegates; splits output browsing, task running, live options, and live preview modules; and adds a downstream PR guard; PR #7 adds Live hot-change controls with runtime tuning over websocket, OBS profile auto-detection, capture backend/mode/scale configuration, strict input validation, capture threading with performance metrics, perf test CSV export, and virtual camera resize handling; PR #8 speeds up Stop handling by cancelling paired Live websocket tasks promptly and adding cooperative in-item cancel checks for photo/video batches. PR #10 integrates upstream and Colab GPU fixes; PR #11 records upstream ancestry; PR #12 improves headless Colab installation progress and NumPy wheel selection; PR #13 fixes capture-FPS preview drift. The monotonic follow-up preserves that scheduling while removing wall-clock dependence and retaining legacy arrival-time buffering.

## Browser remote controller

- Add a separate React/TypeScript Photos, Videos, Live and Outputs controller,
  with local preferences and a private production HTTPS gateway deployment path.
- Preserve PR #14 monotonic preview scheduling and existing DLCR packet protocols.
- Add optional relative upload manifests and exact output preflight, without changing
  Windows upload requests. Wire photo quality/detector/model/precision to processing.
- Native virtual-camera output and other Windows-only features remain omitted;
  future companion requirements are documented. Real GPU/camera/tailnet checks pending.

## Web controller review follow-up
- Forward video detector/model/precision controls and share CLI/preflight segment naming.
- Preserve remote POSIX filenames within confined preflight roots.
- Pause/resume binary WebSocket relay under temporary backpressure; prevent preview freezes from missing/reset sequences and encode packet headers once.
- Clean cancelled unsubmitted upload batches while retaining potentially submitted inputs.
- Preserve the user's detector reset, Windows static path guard and root confinement fixes.
- Keep video manifests valid by forwarding detector size only when set; honor overwrite over skip-processed preflight.
- Keep Live preview playing under frame/byte bounds, and attach to the backend's active job when a saved job is stale.
- Guard batch cleanup against ancestor-rooted active jobs and use per-batch upload locks.
- Fix all repository-wide `ruff check` errors (unused imports, one-line compound statements) and exclude the generated Colab notebook sources (`google-colab/`) from linting.

## Web controller launcher
- Add `scripts/start_web_controller.py` and `start-web-controller.bat`: one command that checks Node/Tailscale, auto-detects the online Colab machine, builds only when stale, keeps a per-user gateway token, starts the gateway in the background, publishes it with `tailscale serve`, and supports `--status`, `--stop`, `--rotate-token`, `--foreground` and Windows login autostart.

## Web Outputs library
- Rebuild the web Outputs tab as a media library styled after the DTFlow Images viewer: Grid/List/Detail views, in-browser thumbnails, search/source/date/sort filters, multi-select with client-side ZIP download, auto-refresh that keeps the selection, a viewer with zoom/pan/swipe/keyboard/slideshow/full screen, and a phone layout.
- Fix slideshow stalls on a broken file, muted video autoplay, and stale option handling in the old viewer. Delete is intentionally not included.
- Write Outputs activity to the Activity log: loads, new/removed files, downloads and ZIP progress, skipped or undecodable files, and refresh failures/recovery (once per outage).
- Fast Outputs gallery: the Colab API serves cached JPEG thumbnails, video posters and 1600 px previews (`GET /outputs/{kind}/thumb/...`, `web_capabilities.output_thumbs`) with a short listing cache; the web app uses them with a fallback to browser thumbnails on older APIs. Restart the Colab API to enable.
- Outputs viewer: Fit now fills the viewer; the original loads only when zooming beyond Fit.

## Partial outputs
- Batch jobs now write each photo/video to a hidden `.name.partial.ext` sibling and rename it into place only when it is complete, so the web gallery and Windows app never try to load or play a file that is still being generated. Failed or cancelled items leave nothing behind; the Outputs listing and file/thumbnail routes ignore hidden partial files.

## Batch progress
- Jobs now report structured progress (`progress` in `GET /jobs/{id}`): item N of M, file name, frames done/expected, fps, file and overall percent, and ETA for the current video. The web app and Windows app show it as a progress bar with "Item 2 / 4 · clip.mp4 · 45% · 8.3 fps · ~1m 20s left" instead of only the item counter. When a video's length is unknown the bar shows frames and fps only.

## Windows app Outputs
- Photo previews use the Colab API's 1600 px server previews (`/outputs/photos/thumb/...`) when zoom is Fit and load the original only for fixed zooms; older Colab APIs fall back to full files automatically.
- The prefetch cache is now byte-bounded (96 MB LRU, was unbounded) and prefetching runs at most 3 downloads at a time; refreshing the list clears stale cached pictures.
- Large output lists are inserted in one batch instead of repainting per item.
- Windows app: closing the window now stops and waits for its worker threads (output downloads/prefetch, job poller, live worker) so Qt no longer aborts with "QThread: Destroyed while thread is still running".
- Fix video jobs freezing mid-file: ffmpeg's error output is now drained continuously (last 16 KB kept for error messages) instead of filling an unread pipe, which blocked ffmpeg on damaged or unusual source videos.
- A stalled video job now reports where it is stuck in the job log (queue sizes, ffmpeg exit state and the stack of the job, decoder and encoder threads) after 20 s without a finished frame, and the per-frame `\r` progress lines reach the log immediately instead of arriving in a batch.
- Fix video jobs hanging forever when the ffmpeg encoder dies mid-file: the job now fails immediately with ffmpeg's own error message, and when the encoder was auto-selected NVENC the video is redone once with libx264.
- After an NVENC failure the libx264 fallback is used for the remaining videos of the run, and ffmpeg's error text is printed in the job log.
- Reprocessing a file that fails or is cancelled no longer deletes its previous complete output (only the hidden partial is removed).
- Windows app shutdown no longer terminates threads: workers are asked to stop (downloads check for it), and if one is still blocked in a network call the process exits directly after the window closes. Downloads started before a list refresh can no longer repopulate the photo cache with stale bytes.
