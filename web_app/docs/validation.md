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

Latest results: **13 web tests passed; 9 Python tests passed**. The Python run
reported one Starlette/httpx deprecation warning. Production build, syntax and
whitespace checks passed.

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
