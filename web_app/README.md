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

Live uses browser cameras, including OBS Virtual Camera when exposed as an input,
DLCR v1 binary packets, hot configuration messages, bounded transport and preview
queues, monotonic timing and separate capture/send/receive/display FPS. Restart-only
controls are disabled during a run. Stop releases browser resources. A prolonged
15-second acknowledgement gap stops the session instead of filling memory.
The gateway pauses socket reads above 8 MiB queued writes, resumes below 4 MiB,
and terminates a persistent 30-second write stall. Source sequence resets or
missing sequence metadata cannot lock preview playback.

Outputs browse only fixed Drive/local roots, support WebP/photo zoom/autoplay,
load-based visible duration, bounded prefetch/cache, streamed video, downloads and
ZIP/archive creation. Arbitrary processing output paths are not indexed. Native
video codecs unsupported by the browser remain downloadable. Retained archives
use the existing backend retention behavior.

Explicit DirectShow/MSMF, OBS profile filesystem reads, OS virtual-camera output,
unselected filesystem paths and Taildrop CLI are omitted. Ordinary workflows do
not depend on a companion. See [parity audit](docs/parity.md) for exact controls,
defaults, ranges, source differences and future optional native design.

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
