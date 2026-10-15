# Validation record

Source baseline main `04c118b`, merged PR #14. User explicitly selected local
validation and requested a browser-only first PR without a companion.

## Executed

- `npm install --no-audit --no-fund` in web_app for initial dependency setup.
- `npm --prefix web_app run build`: TypeScript strict check and Vite production build.
- `npm --prefix web_app test`: Node test runner with tsx import. Initial tsx CLI
  command failed on an IPC pipe permission; script now uses `node --import tsx`.
- `python -m py_compile colab_api.py colab_batch.py`.
- `python -m pytest tests/test_web_controller_api.py tests/test_colab_batch.py -q`
  in an isolated Python 3.12 environment with FastAPI, python-multipart, httpx,
  pytest, NumPy and headless OpenCV. Repository recommends Python 3.11;
  GPU dependencies were not installed or modified.
- `git diff --check`.

The gateway integration test runs the actual production gateway against a local
HTTP/WebSocket fixture. It verifies auth, exact origins and backend allowlist,
private-network preflight, Range relay, media ticket scope, binary/text relay and
single-use WebSocket tickets. Resource tests cover bounded/cancelled photo fetches,
object URL release, camera permission resolving after Stop, and preference restore.
It does not contact Colab or Tailscale.

Python checks exercise actual API handlers/parser with temporary media and an
identity engine. They verify folder paths, traversal rejection, legacy flat
uploads, exact nested preflight, video MP4 naming/range, photo option plumbing,
WebP quality and output dimensions, listing/download, cancellation flag and remote
preflight. Existing geometry/manifest tests also run. No GPU quality is inferred.

Latest results at `4e51d24` (final combined commit): **25 web tests passed;
34 Python tests passed**; `npm --prefix web_app run build` (strict TypeScript check
and Vite production build) passed; `python -m py_compile colab_api.py colab_batch.py`
and `git diff --check` passed. The Python run reported one Starlette/httpx
deprecation warning. `tests/test_ui_live_preview.py` and
`tests/test_remote_live_preview.py` were excluded because they need PySide6, which
is not installed in the validation environment; they cover the Windows app, which
this PR does not change.

## Acceptance still unverified

| Scenario | Local evidence | User equipment check |
| --- | --- | --- |
| Real private Colab connection | Gateway auth/relay integration | Start gateway + Tailscale Serve + updated API; check health |
| Photo batch/repeat skip | API/CLI plumbing + zero-submit controller check | Real source and selected nested photos, repeat without new job |
| Video range/cancel | Range payload and cancel flag API test | Process a video 20–60%, cancel during active frames |
| Outputs WebP/video/download | WebP HTTP + Range gateway | Browser preview, supported video playback, current/all/archive download |
| Camera/OBS Live | Protocol and resource scheduling code | Grant camera, verify negotiated dimensions/FPS and OBS input |
| Hot changes | Real message shape and backend key inventory | Change scale/quality/blends/cadence and observe acknowledged config |
| Actual FPS/gaps/clock changes | Monotonic queue cases with sequence gaps and wall jumps | Vary camera FPS, disconnect briefly, change system wall clock |
| Stop/restart | Cleanup implementation | Repeated sessions; inspect tracks, socket and memory after stop |
| Preference reload | Local persistence implementation | Reload, restore settings, re-enter token/reselect local files, recover job |

Browser visual/runtime QA was not run: the required managed control-browser
capability is unavailable. Real GPU processing, Tailscale HTTPS deployment, camera
permissions, OBS device enumeration and live resource profiling remain unverified.
Private-network permission policies vary; same-origin gateway hosting is the
primary production setup. Sites publication verifies frontend hosting only.

## PR #15 review follow-up

The follow-up commits (`aaf6de1`, `17795e5`, `c628a28`, `bbad51d`, `95fc01c`,
`4e51d24`) were validated as above on the final commit. Each fix has a regression
test; the starvation test for bounded preview eviction was confirmed to fail on the
previous code. See [review resolutions](review-15.md) for the per-finding outcomes.

Ruff: errors that predated this PR were fixed in a follow-up PR (see
`devdocs/releases/unreleased.md`). Hardware gaps above still apply.

## Launcher (`scripts/start_web_controller.py`)

Unit tests (16) cover backend detection, Node version parsing, install/build staleness,
token create/keep/rotate/replace, gateway environment, stale-PID safety, port check and
arguments; the full Python suite passed (50) with ruff and the path-leak check clean.
A Linux end-to-end run with a stub `tailscale` and real Node verified build, start,
authenticated requests, token reuse across restarts, `serve`, `--status` and `--stop`.
The maintainer then ran it on their Windows PC against a real Tailscale tailnet and Colab
backend and reported that it works; Live and photo/video batch sessions were run through
it. Windows DPAPI, autostart and `taskkill` specifics were not separately inspected.
Live tuning observations from those sessions are summarized in the web README.

## Outputs library

Unit tests (`tests/outputs.test.ts`, 8) cover filtering/search/date ranges and every sort
order, list reconciliation by stable identity (an identical refresh keeps the same
array), selection helpers, formatting, the thumbnail cache (bounded concurrency,
newest-first queue, cancellation of tiles that leave the screen, de-duplication,
eviction that never drops a held thumbnail, oversize/decoder errors) and the client
ZIP writer (CRC32 vector, central directory, UTF-8 names, and read back by Python's
`zipfile`). The full web suite passes (33) with `tsc --noEmit` and the Vite build.

Browser checks were run in headless Chromium against the **real** Colab API (generated
sample outputs, no GPU) behind the **real** gateway: 44 photos in Drive/local roots and
nested folders, 4 WebM videos. 19 behaviour checks passed: search, empty state, clear
filters, source filter, sort by name, valid ZIP of selected files (verified with Python),
keyboard navigation, zoom, double-click Fit/100 %, slideshow, full screen and Esc, video
listing/badges/playback, and auto-refresh picking up and dropping files on disk. A touch
context verified the phone layout and swipe navigation. This testing found and fixed a
bug: a parent callback re-created every render re-ran the loader, so changing a view,
size or sort cleared the selection and reloaded the list; a regression check confirms
those changes now cause no new listing requests and keep the selection. Screenshots are
in `docs/screenshots/`.

Not verified: Safari/iOS and Firefox (Chromium only; full screen falls back to a CSS
overlay where the Fullscreen API is missing), a real Colab/Drive with thousands of
files or large originals over Tailscale/mobile data, pinch-to-zoom (double-click and
buttons only), and H.264 video (headless Chromium has no H.264 codec, so playback was
checked with WebM).

