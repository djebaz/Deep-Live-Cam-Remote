# Deep-Live-Cam Remote

Deep-Live-Cam Remote is a fork of [hacksider/Deep-Live-Cam](https://github.com/hacksider/Deep-Live-Cam) focused on Google Colab batch processing and a desktop remote controller app.

This variant keeps the upstream Deep-Live-Cam local pipeline, then adds:

- A Colab notebook workflow for resumable setup and batch jobs.
- A headless photo/video batch CLI for files already in Colab or Google Drive.
- A FastAPI/WebSocket controller API for remote jobs.
- A desktop controller app for managing Colab jobs over a private Tailscale connection.
- Output browsing, previews, cancel support, and shared processing options for photo/video jobs.

> Status: early downstream fork. The current desktop controller implementation is Windows-oriented, but the repo direction is cross-platform remote control.

## Project layout

| Path | Purpose |
| --- | --- |
| `google-colab/Deep_Live_Cam_Remote_Batch.ipynb` | Colab notebook users run directly. |
| `google-colab/Deep_Live_Cam_Remote_Batch.py` | Markerized source for the notebook. Edit this, then rebuild the `.ipynb`. |
| `colab_batch.py` | Standalone batch processor for photos/videos. |
| `colab_api.py` | FastAPI server used by the desktop remote app. |
| `windows_app/` | Current desktop controller implementation with the canonical app entrypoint plus focused helper modules for UI, outputs, options, and Live webcam. |
| `run_windows_remote_app.py` / `.ps1` | Local launcher for the current desktop app. |
| `scripts/` | Notebook round-trip helpers. |
| `devdocs/` | Planning and release notes for this fork. |

## Quick start: Google Colab batch processing

1. Open `google-colab/Deep_Live_Cam_Remote_Batch.ipynb` in Google Colab.
2. Run the setup cells.
3. Mount Google Drive when prompted.
4. Put your files under the default Drive layout:

```text
MyDrive/DeepLiveCamRemote/source/source.png
MyDrive/DeepLiveCamRemote/photos/
MyDrive/DeepLiveCamRemote/videos/
MyDrive/DeepLiveCamRemote/outputs/
```

5. Run the photo or video batch cells.

The notebook clones this repository from:

```text
https://github.com/djebaz/Deep-Live-Cam-Remote.git
```

### Setup progress

The Clone and install cell in both Colab notebooks shows six stages: runtime
preparation, repository update, Python dependencies, GPU dependencies, model
download and verification. During pip/git/apt commands, the display updates with
elapsed time and the latest subprocess output even when the command is quiet.
Dependency installs also print numbered activities for package resolution, reuse,
downloads, build preparation, wheel compilation and installation. A persistent
heartbeat every 10 seconds reports the current activity and time without new output.
The overall bar counts completed stages; it is not a pip download percentage.
Model transfers show byte progress when the server provides a total size.

Failures display the captured command-output tail; interrupting a command stops
its subprocess group. No extra progress-widget dependency is installed. Colab processing runs
headlessly and no longer installs PySide6 or local camera enumeration packages.
Setup selects a NumPy wheel compatible with the Python version. If installation
changes an already imported NumPy, restart the Colab session before running the API. Existing runtime packages are not automatically removed.
Windows and local GUI dependencies are unchanged.

## Batch CLI

From a Colab/runtime checkout:

```bash
python colab_batch.py process \
  --source-face /content/drive/MyDrive/DeepLiveCamRemote/source/source.png \
  --input-dir /content/drive/MyDrive/DeepLiveCamRemote/videos \
  --output-dir /content/drive/MyDrive/DeepLiveCamRemote/outputs/videos
```

Photo batch example:

```bash
python colab_batch.py photos \
  --source-face /content/drive/MyDrive/DeepLiveCamRemote/source/source.png \
  --input-dir /content/drive/MyDrive/DeepLiveCamRemote/photos \
  --output-dir /content/drive/MyDrive/DeepLiveCamRemote/outputs/photos
```

Face mapping workflow:

```bash
python colab_batch.py scan --input-dir /content/in --mapping-dir /content/mapping
python colab_batch.py process \
  --input-dir /content/in \
  --output-dir /content/out \
  --map-config /content/mapping/face_mapping.json
```

Useful processing options include many-face mode, mouth mask, opacity, sharpening, interpolation, Poisson blending, color correction, GFPGAN/GPEN enhancement, start/duration, output FPS, and max width. Run:

```bash
python colab_batch.py --help
python colab_batch.py process --help
```

## Browser remote controller

A separate React/TypeScript browser controller lives in [`web_app/`](web_app/README.md).
It connects to the existing Colab API through a private HTTPS Tailscale gateway
with binary WebSocket support. Photos, Videos, Live inputs and Outputs use the
real backend. The Windows application is unchanged. See the [parity audit](web_app/docs/parity.md)
for controls and native limitations; no companion is required for ordinary workflows.

## Desktop remote controller

The current controller app connects to `colab_api.py` running in Colab over Tailscale.

### In Colab

1. Open `google-colab/Deep_Live_Cam_Remote_Batch.ipynb`.
2. Run setup.
3. Install/connect Tailscale from the notebook cells.
4. Start the API server cell.
5. Copy the displayed Tailscale IP and use port `7860` in the desktop app.

### On Windows today

```powershell
git clone https://github.com/djebaz/Deep-Live-Cam-Remote.git
Set-Location .\Deep-Live-Cam-Remote
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\run_windows_remote_app.ps1
```

The app currently provides:

- Photos and Videos tabs with shared processing options.
- Recursive input scanning, overwrite/skip behavior, and quicker cooperative cancel checks during the active photo/video item.
- Video percentage range selection.
- Live webcam InsightFace pack selection (`buffalo_l`, `buffalo_m`, `buffalo_s`) with `buffalo_l` as the safest default, plus fp32/fp16 swapper precision selection for `swap_ms` comparison.
- Live webcam uses configurable buffered, fixed-cadence preview rendering so bursty backend frames are delayed briefly, evenly paced, and coalesced instead of repainting stale frame backlogs. Transport batching is capped by packet bytes so large frames flush before oversized multi-frame websocket messages are built. Stop cancels the paired websocket sender/receiver tasks promptly instead of waiting for the backend to send another packet.
- Live preview size can be switched between fit, real pixels, 1.5x, and 2x; scaled modes automatically fall back to fit when larger than the panel.
- Live preview uses monotonic capture timestamps to pace buffered playback, so camera FPS differences, skipped capture sequences and Windows system-clock changes do not make its playback clock fall behind. Wall-clock timestamps remain available for latency diagnostics. Frames without monotonic timestamps (including older backends) use arrival-time buffering. Restart the Colab API after updating it to enable capture-based timing with the updated client. Buffering adds delay; it does not increase processing FPS.
- Live webcam uses DirectShow by default for OBS on Windows; Auto capture mode requests the current OBS profile canvas size when available, while Custom mode can force a configured OBS/OpenCV capture size at startup before applying a hot-change Send scale (Auto, 100%, 95%, 90%, 80%, 75%, 70%, 50%, 30%, 25%) before sending JPEG/WebP frames with codec and quality values reported in backend diagnostics/perf logs. Low-risk Live tuning controls (send scale, codec/quality, process width, detection cadence, blending/mask options, many-faces, pipeline frames, and preview buffer/size) can be adjusted while Live is running; camera/source/capture-backend/capture-size/FPS/model controls remain restart-only and are disabled during a run.
- Output browser with preview/player support, photo preview zoom choices (fit, 0.5x, 0.8x, 1x, 1.5x, 2x), photo auto-play visible-duration control, and configurable photo prefetching while auto-play is enabled.
- Local source/input upload to the Colab API.
- Settings sync between photo and video workflows.

## Standalone desktop app build

Use an isolated build virtual environment so PyInstaller only bundles dependencies intended for the desktop remote controller. `requirements-build.txt` intentionally does not install Colab/server/model packages such as InsightFace, TensorFlow, ONNX Runtime GPU, or OpenNSFW.

```powershell
py -3.11 -m venv .venv_build
.\.venv_build\Scripts\python.exe -m pip install -r requirements-build.txt
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_remote_app.ps1
```

The default build is `--onedir` and writes versioned output under `dist/<version>/`. Artifact names include the resolved version and Python version, for example `Deep-Live-Cam-Remote-0.1.0-py3.11.exe`.

Optional switches:

```powershell
# Build with an explicit release version
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_remote_app.ps1 -Version 0.1.0

# Reinstall requirements and clean PyInstaller cache/build output
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_remote_app.ps1 -Clean

# Try a single-file executable
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_remote_app.ps1 -OneFile

# Build a smaller controller without Live webcam dependencies
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_remote_app.ps1 -OneFile -Lite

# Recreate a failed or stale build environment
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_remote_app.ps1 -RecreateVenv

# Reuse an already prepared .venv_build environment
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_remote_app.ps1 -SkipInstall
```

Build outputs and `.venv_build/` are intentionally ignored by git. If `-Version` is omitted, the script tries `pyproject.toml` and then `git describe --tags --always`. Lite builds exclude `cv2`, `numpy`, and `pyvirtualcam`, so the Live webcam workflow is not bundled.

### GitHub Actions packaging

Two manual workflows are available under the repository **Actions** tab:

- **Build Desktop App EXE** (`.github/workflows/build-desktop-app.yml`) builds Full, Lite, or both flavors and uploads the versioned `dist/<version>/` output as a short-retention Actions artifact.
- **Build and Release Desktop App** (`.github/workflows/build-and-release.yml`) builds from an existing release tag and uploads the generated `.exe` assets to that GitHub Release. For `onedir` builds, the workflow zips each bundle before uploading.

Both workflows use Python 3.11, call `scripts/build_remote_app.ps1`, keep UPX disabled, and expose the same Full/Lite plus `onefile`/`onedir` choices as the local build script.

## Notebook round-trip workflow

The Colab notebook is generated from the markerized Python source.

Edit:

```text
google-colab/Deep_Live_Cam_Remote_Batch.py
```

Then rebuild:

```powershell
python scripts/py_to_ipynb.py `
  .\google-colab\Deep_Live_Cam_Remote_Batch.py `
  .\google-colab\Deep_Live_Cam_Remote_Batch.ipynb `
  --eol lf
```

If editing the notebook in Colab, export back to markerized source:

```powershell
python scripts/ipynb_to_py.py `
  .\google-colab\Deep_Live_Cam_Remote_Batch.ipynb `
  .\google-colab\Deep_Live_Cam_Remote_Batch.py `
  --eol lf
```

Preserve cell IDs, marker lines, `meta_b64`, `NOTEBOOK_META_B64`, and markdown/raw sentinels.

## Dependency profiles and upstream integration

See the [PR #10 integration guide](devdocs/features/upstream-pr-9-integration.md)
for imported fixes, fork-specific additions, migration steps and pending validation.

Use Python 3.11 for this fork's documented desktop and Colab workflows.
`requirements.txt` now uses NumPy 2, newer OpenCV and ONNX Runtime, Keras 3,
and a declared TensorFlow backend on Python below 3.14 (Torch on 3.14+).
Create a fresh virtual environment when upgrading an existing installation;
NumPy 1 binary extensions may need rebuilding for NumPy 2. On macOS, remove
`onnxruntime-silicon` before installing the official `onnxruntime` package.
Other Python versions and the upgraded dependency stack still need runtime validation.

The Colab notebooks keep a separate OpenCV 4.10 / ONNX Runtime GPU 1.23.2
profile. They select NumPy <2 on Python through 3.12 and NumPy >=2.1,<3 on
Python 3.13+, where NumPy 1.26 has no matching wheels. NumPy must install from
a binary wheel; setup fails promptly rather than compiling it from source. Both notebooks install its CUDA/cuDNN runtime
extras with cuDNN pinned to the tested `9.26.0.51`, and the batch/Live engine
preloads NVIDIA pip libraries before inference. cuDNN 9.27 caused runtime
convolution failures and CPU fallback on the tested Colab T4.
The logs report active swapper providers and warn about CPU fallback. After
updating setup or libraries, restart the API to replace cached model sessions.
It does not install the root requirements.
Desktop packaging continues to use `requirements-build.txt`.

Shared model downloads use verified TLS and resumable transfers. Remote Live
keeps explicit InsightFace pack and fp32/fp16 selection, with `buffalo_l` and
fp32 as defaults. The local upstream UI adds persisted camera resolution and
detection size selectors. OpenVINO users must install matching OpenVINO and
ONNX Runtime OpenVINO packages as described in upstream's provider documentation.

## Relationship to upstream

This repository is an official GitHub fork of `hacksider/Deep-Live-Cam`, but it is maintained as a downstream remote/Colab variant.

Suggested branch roles:

- `main` - this fork's product/release branch.
- `upstream-main` - clean sync branch from `hacksider/main`.
- feature branches - focused changes or upstream PR candidates.

For upstream contributions, keep patches small and branch from `upstream-main`.

## Models and licenses

This project follows the upstream Deep-Live-Cam licensing and model constraints.

- Code license: see `LICENSE`.
- Upstream project: <https://github.com/hacksider/Deep-Live-Cam>
- InsightFace models may carry non-commercial research restrictions. Review upstream model and dependency licenses before distributing outputs or packaged builds.

Model files are not committed. The Colab/batch setup downloads and validates the required swapper model when needed.

## Responsible use

Use this software only with appropriate rights and consent. If using a real person's face, obtain permission and clearly label generated or altered media where appropriate. You are responsible for complying with applicable laws, platform rules, and ethical requirements.

The remote/Colab path in this fork intentionally focuses on workflow and does not add extra consent modals or content-gate UI beyond upstream behavior.

## Development notes

Common local commands:

```powershell
# Inspect status
git status --short

# Python syntax check for edited files
python -m py_compile .\colab_batch.py .\colab_api.py

# Focused tests, when intentionally requested
python -m pytest .\tests -q
```

Do not commit virtual environments, caches, downloaded models, local state, or generated temporary notebooks.
