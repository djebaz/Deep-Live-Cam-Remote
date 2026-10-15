# Browser remote controller

React/TypeScript remote controller for the existing Colab GPU backend. The Windows
app is retained. This release has no native companion implementation.

## One-command launch on your PC

After a one-time `tailscale` sign-in (MagicDNS and HTTPS enabled; Tailscale Serve
enabled once from the link it prints), start everything with:

```powershell
.\start-web-controller.bat          # or: python scripts/start_web_controller.py
```

It checks Node 22.12+ and Tailscale, finds your online `colab*` machine, runs
`npm ci`/`npm run build` only when needed, creates a per-user gateway token (kept in
your profile, DPAPI-protected on Windows, never in the repository), starts the
gateway in the background, runs `tailscale serve`, copies the token to the clipboard
and prints the HTTPS address. In Connection, leave the gateway URL blank, paste the
token and press Check connection. Useful options:

| Option | Effect |
| --- | --- |
| `--backend 100.x.y.z[:port]` | Use this Colab address instead of auto-detecting |
| `--status` / `--stop` | Show state / stop the gateway and remove the Serve entry |
| `--rotate-token` | Generate a new token |
| `--foreground` | Run the gateway in this window (Ctrl+C stops it) |
| `--no-browser`, `--no-serve`, `--rebuild`, `--port N` | As named |
| `--install-autostart` / `--remove-autostart` | Start at Windows login (Startup folder) |

Re-run it after restarting Colab: the Colab Tailscale address can change, and the
gateway allowlist is rebuilt from the machine it finds. State and logs live in
`%LOCALAPPDATA%\DeepLiveCamRemote`. The manual steps below remain valid.

Troubleshooting: `401 Enter the gateway access token` means the token field is empty
(the browser never saves it); a `.ts.net` address that "can't be reached" is usually
DNS - check `nslookup <name> 100.100.100.100` and turn on "Use Tailscale DNS settings"
in Tailscale on the PC; `tailscale serve` asks you to enable Serve once from a link it
prints.

## Private production setup

Use Node 22.12+ or Node 24, and the existing Colab setup. On a machine connected
to the same Tailscale network as Colab, from the repository root:

```bash
npm --prefix web_app ci
npm --prefix web_app run build
export DLCR_BACKENDS='http://YOUR_COLAB_TAILSCALE_IP:7860'
export DLCR_ORIGINS='https://YOUR_GATEWAY.YOUR_TAILNET.ts.net'
# Set DLCR_GATEWAY_TOKEN to a random secret of at least 24 characters via your
# environment/secret manager. Never put it in frontend source or Git.
npm --prefix web_app start
```

In another terminal on the gateway machine:

```bash
tailscale serve --bg http://127.0.0.1:8787
```

Enable MagicDNS and HTTPS certificates in Tailscale if prompted. Serve stays
private to your tailnet; do not use Funnel. Open the HTTPS URL in your browser.
In Connection, leave the gateway URL blank for same-origin operation, enter the
access token, and leave backend host blank to use the gateway default (or enter
an exact allowlisted host and port). Check connection. Grant camera access for Live.
Restart the updated Colab API for relative uploads and connected photo controls.
Before merge, check out this PR branch in Colab; notebook setup normally pulls main.

The gateway binds only 127.0.0.1:8787. Its operator-configured DLCR_BACKENDS is an
exact comma-separated HTTP(S) origin allowlist, never a browser-supplied arbitrary
URL. DLCR_ORIGINS contains exact frontend origins, including its own HTTPS origin.
REST uses a bearer secret held only in memory. WebSockets use one-use 30-second
path/backend-bound tickets; media uses read-only one-hour path/backend-bound
tickets so video Range requests stream without buffering entire videos in memory.
Keep proxy access logs disabled or redact ticket query parameters.

The gateway serves the built app and relays real HTTP and binary WebSocket
messages. It adds no face processing. Its API route allowlist blocks unrelated
upstream paths; redirects are refused and upstream requests do not receive gateway
credentials. Connection errors point to Tailscale, HTTPS, origin permissions and
backend availability. This is the production server, not a development Vite proxy.

## Sites frontend

Sites can host the same static `dist` frontend. Its server cannot join a private
tailnet. Configure your private gateway URL in Connection and add the exact Site
origin to DLCR_ORIGINS. The device running the browser must be connected to
Tailscale. CORS and private-network preflights are handled for allowed origins,
but browsers may require local-network permission or disallow cross-origin private
network access. In that case use the same-origin gateway URL above. No public
backend is required; private same-origin deployment is the supported baseline.

## Workflows and limitations

Photos/Videos support source normalization, local file/folder uploads, remote
paths, independent processing options, progress/logs, cancellation and recovery.
Preflight checks exact output names in the requested output directory under the
known Drive/local layout roots (including subfolders);
all-processed selection creates no upload and no job. It intentionally checks
output existence like desktop preflight, not processing-config equivalence.
Uploads preserve paths relative to the selected folder; remote output naming
follows the real CLI through a shared output-path helper. Preparation cancellation
cleans the isolated input batch; an ambiguous job submission retains inputs.
Source and local selections must be reselected after reload,
while preferences and known active job IDs persist. The access token does not.

After a successful connection check, health monitoring and active-job polling
automatically retry temporary network failures, timeouts, HTTP 5xx, 408 and 429.
Requests have a 15-second deadline; retry delays increase from 1 to 2, 4, 8 and
then at most 15 seconds. During an outage the header shows **Reconnecting** and a
notice explains that the job may still be running on Colab. The current job ID
is retained and polling resumes automatically; uploads and job submissions are
never automatically repeated. The notice clears on recovery, and Activity logs
one interruption and one recovery per outage. Authentication/configuration errors
still require fixing the connection settings. If Colab no longer knows the job,
check Outputs before starting another batch. Reconnection cannot restore jobs
lost when the Colab runtime or API restarts.

Live uses browser cameras, including OBS Virtual Camera when exposed as an input,
DLCR v1 binary packets, hot configuration messages, bounded transport and preview
queues, monotonic timing and separate capture/send/receive/display FPS. Restart-only
controls are disabled during a run. Stop releases browser resources. A prolonged
15-second acknowledgement gap stops the session instead of filling memory.
The gateway pauses socket reads above 8 MiB queued writes, resumes below 4 MiB,
and terminates a persistent 30-second write stall. Source sequence resets or
missing sequence metadata cannot lock preview playback.

Outputs is a media library for the backend's fixed Drive and Colab output folders
(styled after the DTFlow Images viewer; see the screenshots in `docs/screenshots/`):

- **Grid / List / Detail** views and a Photos/Videos switch. The view, thumbnail size
  (25-250 %), sort order and auto-refresh are remembered per browser.
- **Auto-refresh** (on by default) checks for new outputs every few seconds while the
  tab is visible, and keeps your selection and position. **Refresh now** is always
  available.
- **Search, source, date and sort** filters; list headers sort by name, size and date.
- **Selection**: checkboxes, Select all / Unselect all (across the filtered list), and
  **Download selected (ZIP)**, built in the browser (up to 5,000 files / 512 MB; larger
  selections use **Download all** or **Create archive**, which are backend ZIPs).
- **Detail viewer**: preview that fills the viewer at Fit (original loaded on zoom), previous/next, filmstrip, Fit/zoom with
  drag-to-pan and Ctrl/Cmd+wheel, double-click for 100 %, swipe on touch screens,
  slideshow (with a broken file skipped, not a dead end), full screen, file details
  with video duration immediately to the right of Dimensions (`m:ss` or `h:mm:ss`;
  `—` until known).
  Keys: arrows (previous/next), `+`/`-`/`0` (zoom), Space (slideshow), `F` (full
  screen), Esc (leave full screen, then back to the library), `/` (search).
- **Activity log**: the page's Activity log records, prefixed `Outputs:`, each load (counts
  and size), new or removed files found by refreshes, manual refreshes with nothing new,
  every download (single file, selected ZIP with progress and result, backend ZIP,
  retained archive), files skipped by the slideshow or that the browser cannot decode or
  play, and refresh failures (logged once per outage, then once when it recovers).
- Videos show the browser's own first frame as the tile and play in the viewer; formats
  the browser cannot play stay downloadable.

Opening a video in Detail (including previous/next navigation) starts playback
muted, independently of the slideshow setting. Enable sound using the player
controls. Slideshow still controls whether playback advances to the next file
when the video ends. The viewer explicitly requests playback once approximately
two seconds are buffered (or the rest of a shorter clip), allowing native autoplay
to start sooner if the browser is already ready. This is buffered media time, not
a guaranteed two-second loading delay; network speed and decoding still affect
startup. Browser autoplay restrictions can still require pressing Play.

**Speed**: the Colab API makes small cached JPEG thumbnails (320 px) and video poster
frames, and 1600 px previews for the viewer, so the gallery downloads kilobytes instead
of full originals; the viewer loads the original only when you zoom beyond Fit. They are
requested only when a tile is near the screen, with bounded concurrency and memory.
Restart the Colab API to get this; against an older API the browser falls back to making
thumbnails itself from the full files (slower, costs bandwidth). Arbitrary processing output paths are not indexed.
Retained archives use the existing backend retention behavior. There is no delete.

Explicit DirectShow/MSMF, OBS profile filesystem reads, OS virtual-camera output,
unselected filesystem paths and Taildrop CLI are omitted. Ordinary workflows do
not depend on a companion. See [parity audit](docs/parity.md) for exact controls,
defaults, ranges, source differences and future optional native design.

## Live tuning notes

Measured from the browser over Tailscale with the Colab live engine (`live_perf`
lines in the log). Treat these as starting points, not guarantees.

- **The GPU sets the ceiling.** On a Colab Tesla T4, an `fp32` swap took about 75 ms
  (about 13 fps maximum, with frames queuing and being dropped); `fp16` took about
  28 ms. A faster GPU swapped in about 5 ms even with `fp32`. Check `swap_ms`,
  `server_queue_ms` and `latest_drop_count`: a growing queue and drops mean the server
  is the limit; `wait_ms` of tens of milliseconds with an empty queue means the
  browser or camera is.
- **Frame size is the usual browser-side limit.** Frame rate fell from about 20 to
  about 10-14 fps whenever `in_kb` rose from about 6-8 KB to 12-17 KB (more motion or
  detail, larger send scale, higher JPEG quality). Quality 55-65 at a send scale near
  210x294 held 18-20 fps; 300x420 at quality 63-66 gave 16-17 fps; quality 80 at
  300x420 dropped to 10-11 fps.
- **The camera caps the rate.** The negotiated rate is logged (for example
  `Negotiated camera: 300 x 420 - 25.0 FPS`); the server cannot exceed it, and cameras
  often fall back to 15-20 fps in dim light.
- **Detection is cheap on a GPU.** Detector 160 costs about 1 ms, so detect every 1-2
  frames improves face tracking at no visible cost; detect every 7-8 saves almost
  nothing.
- **Codecs.** Keep JPEG input and WebP output as the default. In the same session,
  WebP output was faster end to end (16-17 fps) than JPEG output (9-13 fps) even
  though the server encodes JPEG faster, and WebP input added 10-20 ms of delay without
  a gain. Re-test on your own setup; short samples vary.
- **Stalls.** Occasional one-to-two-second gaps with a large `reader_receive_ms` and an
  idle server come from the network or a paused browser tab, not from processing.
- **Source image.** Live needs a source face on the backend; select one in the Live tab
  (a runtime restart removes the uploaded copy, and the default Drive path
  `.../source/source.png` may not exist).

## Local verification

```bash
npm --prefix web_app test
npm --prefix web_app run build
python -m py_compile colab_api.py colab_batch.py
python -m pytest tests/test_web_controller_api.py tests/test_colab_batch.py -q
```

Python tests need FastAPI, python-multipart, httpx, pytest, NumPy and OpenCV. They
use temporary files and an identity engine: no GPU/model quality verification.
Web tests check the real production gateway against a local protocol fixture.
Real Colab, Tailscale, camera/OBS and browser visual/runtime validation remain
unverified until run on the user's equipment.
