# Desktop-to-web parity audit

Audited source baseline: `main` at `04c118b` (2026-10-14 checkout). PR #14 is already merged as **Fix Live preview scheduling during system-clock changes (#14)**. Its monotonic scheduling in `windows_app/live_preview.py` and echoed `capture_monotonic` metadata in `colab_api.py` must remain intact. PR #13 gap recovery is also present. This document records source behavior and implementation requirements, not a claim that hardware acceptance scenarios have passed.

Sources inspected: `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `windows_app/main_window_ui.py`, `settings.py`, `processing_options.py`, `api_client.py`, `task_runner.py`, `output_tasks.py`, `output_browser.py`, `live_options.py`, `live_webcam.py`, `live_preview.py`, `window_core.py`, `colab_api.py`, and `colab_batch.py`. No `HOWTO.md` exists in this checkout.

## Feature checklist

Status: backend-connected implementation is present for the browser workflows below. Local protocol/API tests and build checks are recorded in validation.md; real hardware acceptance remains unverified. A represented control is not complete until its value reaches processing.

| Desktop behavior | Required web implementation | Native companion | Status |
| --- | --- | --- | --- |
| Setup host, port, Drive paths; health; save settings; logs | Persistent connection area, constrained configured backend, actionable health errors, local preferences, credential-redacted bounded logs | No | Connected implementation; hardware unverified |
| Shared source path linked across tabs | One shared source face; browser-selected file or remote source path | No | Connected implementation; hardware unverified |
| Separate Photos/Videos processing dictionaries; Live dictionary | Persist workflow-specific controls independently; shared connection/source/path settings | No | Connected implementation; hardware unverified |
| Local source auto-transformed through QImageReader to PNG | Normalize EXIF orientation before multipart source upload | No | Connected implementation; hardware unverified |
| Local folder enumeration recursive/nonrecursive | Browser file/folder selection, supported-extension filter, preserve selected folder-relative paths | No for selected files; yes for arbitrary paths | Connected implementation; hardware unverified |
| Remote photo/video paths | Send backend-visible paths directly without local upload | No | Connected implementation; hardware unverified |
| Skip-processed local preflight before input upload | Compare actual output relative names; all matched means zero input upload and zero job creation | No | Connected implementation; hardware unverified |
| Isolated batch upload UUID; 1000-file client cap | Use existing upload endpoints with batch_id and verify returned input directory | No | Connected implementation; hardware unverified |
| Full photo controls including advanced controls | API-to-engine plumbing for every displayed control, not silently ignored fields | No | Connected implementation; hardware unverified |
| Video controls and percentage range | Real jobs/videos payload, backend progress/logs, output naming, cancellation | No | Connected implementation; hardware unverified |
| Start button turns into Stop | Prevent duplicate submits; cancel preparation/upload or cooperative active backend job | No | Connected implementation; hardware unverified |
| Logs/polling/status | Real queued/running/completed/failed/cancelled states; explain unknown/missing jobs | No | Connected implementation; hardware unverified |
| Webcam/OBS input camera | Browser camera enumeration after permission, actual negotiated capture dimensions/FPS | No if device is exposed to browser | Connected implementation; hardware unverified |
| DirectShow/MSMF/Auto capture backend | Explain browser-managed capture; omit unusable native selectors | Yes for explicit backend choice | Native limitation |
| Auto reads OBS profile canvas size | Browser constraints/manual dimensions; no claim to read OBS profile | Yes | Native limitation |
| pyvirtualcam processed output | Browser preview only ordinarily; companion required for OS virtual-camera output | Yes | Native limitation |
| Hot-change tuning and restart-only controls | Runtime config_update message for server hot keys; local hot keys stay local; disable restart-only controls while running | No | Connected implementation; hardware unverified |
| DLCR binary live input/output batches | Existing big-endian packet framing, metadata echo, drop acknowledgements | No | Connected implementation; hardware unverified |
| Pipeline bounds, packet limit | Cap in-flight frames, pending capture/decode/preview resources; packet cap and batch timeout | No | Connected implementation; hardware unverified |
| Buffered monotonic playback | Relative monotonic capture timestamps, arrival fallback, overdue coalescing, last image retained | No | Connected implementation; hardware unverified |
| Prompt Live Stop | Close socket/tracks, cancel timers/animation callbacks, invalidate asynchronous work, release images/resources | No | Connected implementation; hardware unverified |
| Live perf text and CSV; automatic perf sweep | Backend diagnostics plus separate measurable capture/send/receive/display FPS; CSV export; document sweep gap if absent | No | Connected implementation; hardware unverified |
| Outputs fixed remote roots; Refresh/select/previous/next | Use actual backend listing/download links; do not treat custom output paths as indexed roots | No | Connected implementation; hardware unverified |
| Photo WebP/zoom/autoplay/prefetch | Browser WebP decode; all zoom choices; visible timer starts after load; bounded cache | No | Connected implementation; hardware unverified |
| Video preview/player/download | Browser player, explicit codec compatibility errors, real download | No | Connected implementation; hardware unverified |
| Download current/all ZIP; Taildrop fallback support | Browser download plus existing ZIP/archive API; native Taildrop optional | Only Taildrop/local destination access | Connected implementation; hardware unverified |
| Persistent Windows geometry/theme | Responsive familiar dark UI; browser layout/preferences instead of DWM/Qt geometry | No | Browser equivalent |

## Connection and settings source values

`D = /content/drive/MyDrive/DeepLiveCamRemote`.

| Control | Default | Range/options and semantics |
| --- | --- | --- |
| Tailscale host/IP | Empty | Desktop strips http/https and builds HTTP URL; browser should use same-origin HTTPS proxy |
| API port | 7860 | 1–65535 |
| Drive root | D | Text; backend output roots are fixed independently of this field |
| Shared source face | D/source/source.png | Local selected face or backend path |
| Photos input/output | D/photos; D/outputs/photos | Backend paths or desktop local input folder |
| Videos input/output | D/videos; D/outputs/videos | Same distinction |
| Save settings / Check connection | Explicit actions | Settings saved on save/start/close; GET /health |

Actual settings code saves `photos_options` and `videos_options` independently. The active workflow also copies its options into legacy shared fields; it does **not** continually synchronize all photo and video controls despite the simplified README wording. Live has its own options and uses the shared source fields. Web preferences must preserve that distinction. OS paths are never browser-readable just because they are entered in a text field.

## Shared processing controls (Photos and Videos)

| Control / payload key | Default | Desktop range/options |
| --- | --- | --- |
| Recursive / recursive | true | Boolean |
| Overwrite / overwrite | false | Boolean |
| Skip processed / skip_processed | true | Boolean |
| Many faces / many_faces | false | Boolean |
| Enhancer / enhancer | none | none, gfpgan, gpen256, gpen512 |
| Opacity / opacity | 1.0 | 0–1, step 0.1 |
| Sharpness / sharpness | 0.0 | 0–1, step 0.1 |
| Mouth mask / mouth_mask_size | 0.0 | 0–10, step 0.5 |
| Interpolation / interpolation_weight | 0.0 | 0–1, step 0.1 |
| Poisson blend / poisson_blend | false | Boolean |
| Color correction / color_correction | false | Boolean |

Supported desktop photo extensions: `.bmp`, `.jpeg`, `.jpg`, `.png`, `.webp`. Video extensions: `.avi`, `.m4v`, `.mkv`, `.mov`, `.mp4`, `.webm`. Batch CLI additionally discovers `.mpeg` and `.mpg` from remote video directories, but desktop uploader and output browser do not expose them.

## Workflow-specific controls

| Workflow/control | Default | Desktop range/options | Backend source caveat |
| --- | --- | --- | --- |
| Photo max width / output_max_width | 0 = Original | 0–8192 | Omitted at 0; downscale only |
| Photo image quality / quality | 95 | 1–100 | Baseline API/CLI ignores this for photos; requires additive fix |
| Photo detector size / detector_size | 640 | 160–1280, step 32; floored to multiple of 32 | Baseline JobRequest ignores it; requires additive fix |
| Photo InsightFace pack / face_model_pack | buffalo_l | buffalo_l, buffalo_m, buffalo_s | Baseline JobRequest ignores it; requires additive fix |
| Photo precision / swapper_precision | fp32 | fp32, fp16 | Baseline JobRequest ignores it; requires additive fix |
| Video max FPS / max_fps | 30 | 1–120 | Caps source FPS |
| Video max width / max_width | 420 | 64–4096 | Processing geometry preserves aspect ratio |
| Video quality / quality | 18 | 0–51 | FFmpeg CQ/CRF, lower means higher quality |
| Video start / start_pct | 0 | 0–99 | Validate start < end |
| Video end / end_pct | 100 | 1–100 | Percentage of source duration |

Baseline desktop `job_payload` heuristically identifies photo settings from `"/photos"` in input_dir. Web must use the selected workflow explicitly so arbitrary remote photo paths do not accidentally receive video settings. `max_fps`, `max_width`, quality/model/detector and percentage keys are sent by the desktop payload even when irrelevant; photo output_max_width is included only when positive. API encoder exists (`auto` default) but has no desktop selector; CLI also supports h264_nvenc/libx264, p4 preset, queues and seek/duration which are not desktop controls.

Batch flow: health → optional normalized source upload → supported local inputs → skip preflight → isolated input upload → POST job → poll or job WebSocket → terminal status. Baseline preflight checks `_face_swapped` output basenames case-insensitively and can incorrectly conflate equal basenames in different directories. It also assumes original video extension, whereas video processor actually writes `.mp4`. Web should preserve relative paths and compare real output naming. Baseline source upload happens before all-processed preflight; improve ordering so an all-skipped repeat avoids unnecessary uploads.

Backend photo naming: `relative/parent/stem_face_swapped.<lowercase-original-extension>`. Video naming: `relative/parent/stem_face_swapped.mp4` for desktop percentage jobs. CLI absolute seek/duration optionally inserts `_ss..._dur...`. Backend skip behavior uses a manifest key including input/source/model/config and existing artifact, separate from filename-only upload preflight. Backend cancellation checks before each item and within video processing; photo inference is cooperative at boundaries and not forcibly interrupted. Incomplete active output is deleted. Batch report records completed/skipped/failed; job terminal success alone does not imply every input generated an output.

## Live control matrix

| Control / key | Default | Range/options | Change behavior |
| --- | --- | --- | --- |
| Camera | index 0 | Desktop 0–20; browser deviceId/label | Restart |
| Native virtual-camera output name | OBS Virtual Camera | Text | Companion only |
| Source face | Shared source | Selected upload or remote path | Restart |
| Capture backend | directshow | auto, directshow, msmf | Native only; restart |
| Capture mode | auto | auto (OBS canvas), opencv_auto, custom | Browser auto/manual equivalent; restart |
| Capture width/height | 1280×720 | 2–4096 each, step 2 | Restart |
| Capture FPS | 30 | 1–120 | Restart; negotiated FPS may differ |
| Send scale / capture_scale | auto | auto, 100%, 95%, 90%, 80%, 75%, 70%, 50%, 30%, 25% | Client hot; auto/100% actual capture size |
| Pipeline frames / live_pipeline_frames | 16 | 8–512 | Client hot |
| Transport batch size | 1 | 1–32 | Client hot; processing remains sequential |
| Many faces | false | Boolean | Server hot |
| Enhancer | none | none, gfpgan, gpen256, gpen512 | Restart |
| Opacity / sharpness / mouth mask / interpolation | 1 / 0 / 0 / 0 | Shared ranges above | Server hot |
| Poisson blend / color correction | false / false | Boolean | Server hot |
| Process max width / max_width | 420 | 64–4096 | Server hot |
| Send codec / frame_codec | jpeg | jpeg, webp | Client + server hot |
| Return codec / output_codec | jpeg | jpeg, webp | Server hot |
| Frame quality / jpeg_quality | 80 | 20–95 | Client + server hot; applies to either codec |
| Detector size | 320 | 160–640, step 32 | Server hot |
| Detect every N frames | 1 | 1–30 | Server hot |
| InsightFace pack | buffalo_l | buffalo_l, buffalo_m, buffalo_s | Restart; m/s experimental |
| Swapper precision | fp32 | fp32, fp16 | Restart; fp32 safest baseline |
| Cache source face | true | Boolean | Restart |
| Preview buffer seconds | 1.0 | 0–5, step 0.25 | Local hot |
| Preview scale | fit | fit, 1x, 1.5x, 2x | Local hot; fit fallback when larger than panel |

Send scale, transport batch size, pipeline limit, preview buffer/scale are local controls, not allowed server config keys. Server hot message is `{"type":"live_config_update","config":{...}}`; unsupported keys are rejected as restart-required. Desktop debounce is 200 ms. Server also accepts `frame_quality` alias. Initial /ws/live text message is the plain full configuration object; server replies ready or error before frame transport starts.

Binary packet layout is unchanged in both directions: 8-byte packet header `[ASCII DLCR (4), uint16 version=1, uint16 frame_count]`, then each frame `[uint32 JSON byte length, uint32 encoded-image byte length, UTF-8 JSON, JPEG/WebP bytes]`. All integers are network/big-endian. Header max 1,000,000 bytes, image max 50,000,000 bytes, protocol frame count 1–256. Desktop batching separately caps packets at 4 MiB with 64-byte margin and flushes at 50 ms; single oversize frames must not create unlimited batches. Legacy raw image packets are decoded with empty metadata.

Frame input metadata includes seq, capture_time (wall-clock diagnostic), capture_monotonic (relative monotonic scheduling) and send_time (wall-clock diagnostic). Output echoes seq/capture metadata and reports client_send_time, server_receive_time, server_send_time, codec, width, height, payload_bytes. `live_frame_dropped` text messages contain dropped count and frame_seq; subtract dropped count from in-flight reservations. Each returned output frame releases one reservation. Server pending queue is bounded at 16 and drops oldest frames, acknowledging them.

Preview scheduling uses local monotonic now + buffer for first presentation, then first-presentation + (capture_monotonic − first-capture_monotonic). Never use wall clock or seq/requested-FPS to schedule. Missing/nonfinite/negative monotonic values use arrival+buffer. Pop all due frames and display newest valid sequence, retain previous displayed image if none is due. Desktop queue cap is max(3, ceil((buffer+2)*requested-FPS)); web should add practical byte/resource bounds. Buffer gauge measures deadline span, not frame count/FPS. Stop releases everything promptly and start establishes a fresh timing origin.

Desktop automatic perf sweep includes batch sizes 1/8/16/32, 12-second cases, 3-second warmup, send scale 50%, quality 70, cadence 3, detector 256, pipeline 64. CSV exposes server detect/landmark/swap/post/enhance/encode/queue/drop/transport metrics and client capture/resize/encode/send/backpressure/in-flight/receive/decode metrics plus raw JSON. Native capture-grab/retrieve and virtual_send_ms have no direct browser equivalent. Wall-clock one-way latency values can be invalid after clock changes; timing deadlines must stay monotonic. Buffered preview improves pacing at additional latency, not GPU throughput.

## Outputs

The web Outputs tab intentionally goes beyond the desktop browser (Grid/List/Detail,
search and filters, multi-select, auto-refresh, mobile viewer), following the DTFlow
Images viewer. Desktop behaviors are all kept.

| Control | Default | Range/options |
| --- | --- | --- |
| Kind | photos | photos, videos |
| View | grid | grid, list, detail (remembered) |
| Thumbnail / row / filmstrip size | 100 % | 25-250 % of a 160 px tile (remembered) |
| Auto-refresh | on | Poll the listing every 8 s while the tab is visible (remembered) |
| Refresh / previous / next | Actions | Load actual backend list; wrap navigation |
| Search / source / date / sort | none / all / all time / newest | Client-side on the loaded listing; sort remembered |
| Select / Select all / Download selected | Actions | Client-side ZIP, 5,000 files / 512 MB limit |
| Auto-play (slideshow) | false | Boolean; videos advance when they end (muted) |
| Photo visible seconds | 3.5 | 0.25-60; starts only after load; failed items are skipped |
| Photo preload | 10 | 1-50 upcoming photos |
| Zoom | Fit | Fit, 25-400 % steps, wheel, pan; double-click toggles Fit/100 % |
| Download current / all / archive | Actions | Actual item / backend kind ZIP / retained archive |

Not implemented: delete or rename (no backend route; intentionally omitted), indexing of custom output folders, side-by-side source/output comparison.

GET /outputs/{kind} returns files sorted by modified descending, then name descending, from Drive and local roots only. Each entry contains name, relative_path, source (`drive`/`local`), size, modified and download_path. Fixed roots: D/outputs/photos, D/outputs/videos, /content/outputs/photos, /content/outputs/videos. Custom processing output paths remain valid processing destinations but are not automatically indexed. Preview/download use the returned path, not a newly invented arbitrary filesystem endpoint. Browser video codec support may differ from Qt/OpenCV; offer download with clear errors. Bound photo cache by count and bytes, evict unused object URLs/bitmaps, ignore stale selection responses, abort obsolete fetches; desktop prefetch cache itself lacks an eviction bound and should not be copied unchanged.

## Existing API inventory

| Method/path | Real contract |
| --- | --- |
| GET /health | ok, api_version, Drive/local layout and server diagnostics |
| POST /upload/file?kind=source | multipart `file`; returns path,size,ok,kind |
| POST /upload/source | multipart `file`; returns path,size,ok |
| POST /upload/photos or /upload/videos?batch_id=UUID | multipart repeated `files`; returns count,files,input_dir,output_dir,batch_id,ok |
| POST /jobs/photos or /jobs/videos | JobRequest JSON; returns job_id,status |
| GET /jobs/{job_id} | job_id,kind,status,started_at,finished_at,exit_code,error,latest 300 logs; unknown job is error JSON |
| POST /jobs/cancel | {job_id}; returns cancel_requested and current status |
| WS /ws/jobs/{job_id} | Initial snapshot, then status/log objects; closes on terminal |
| WS /ws/live | Initial config text, config updates, diagnostic/drop text, DLCR binary frames |
| GET /outputs/{kind} | {files:[...]} |
| GET /outputs/{kind}/file/{source}/{relative_path} | Validated artifact file |
| GET /outputs/{kind}/thumb/{source}/{relative_path}?size=&v= | Cached JPEG thumbnail/preview (sizes 160/320/640/1600) or video poster; `X-Source-Width/Height/Duration` headers; advertised as `web_capabilities.output_thumbs` |
| GET /outputs/{kind}/zip | Streamed kind archive |
| POST /outputs/{kind}/create-zip | zip_path,zip_id,size_bytes,timestamp,tailscale_hostname |
| GET /download-archive/{archive_id} | Precreated archive download |
| DELETE /upload/clear | Existing destructive upload cleanup; no desktop UI requirement |

Baseline uploads flatten names through Path.name. Add safe optional relative-path handling in these same endpoints to preserve folder selection; reject traversal/absolute paths and duplicate destination collisions. Do not replace protocols. Baseline API has no auth layer and no browser CORS middleware; keep it private and put browser traffic through a constrained same-origin deployment. Public static Sites hosting alone cannot reach the user's tailnet and is not a complete live deployment.

## Optional local companion design (not implemented)

Ordinary browser-selected file uploads, remote paths, camera inputs, backend jobs, previews and downloads do not require a companion. Explicit DirectShow/MSMF selection, automatic OBS profile inspection, arbitrary unselected local paths, Taildrop CLI, and writing processed frames into an OS virtual camera do.

Proposed installation: optional Python 3.11 desktop dependency profile in an isolated environment, using existing windows_app live capture helpers, OBS INI discovery, source normalization and pyvirtualcam output implementation. OBS virtual-camera components/drivers must be installed by the user. Run under the current user without administrator privileges or an autostart service; explicitly select capture and output devices and grant folders in a native window.

Connection/security requirements: bind loopback only; serve a local same-origin controller or use a trusted HTTPS loopback endpoint; require explicit pairing with a short-lived token and exact controller-origin allowlist for HTTP and WebSocket Origin; protect against cross-site/CSRF calls; reject wildcard origins, arbitrary upstream URLs, ungranted local paths and command strings. Require user approval per selected folder/device, show a persistent active indicator, expose Stop, and release device access on disconnect. Route backend traffic only to the preconfigured tailnet address. Do not send pairing credentials to logs or persist them in browser preferences. An HTTPS remote page calling insecure loopback directly is not a viable default; local same-origin hosting avoids mixed-content/private-network restrictions.

The companion would expose a narrow capture/output capability interface, not face processing. No companion installation package or native web integration is claimed in this audit; native features remain explicit gaps until separately implemented and tested.


## Implementation evidence and intentional differences

- `src/settings.ts` provides workflow-specific dictionaries and control schema;
  connection/source settings are shared. Access tokens remain in memory.
- `src/batch.ts` calls real health, source/upload/job endpoints. Additive
  `relative_paths` manifests preserve folders; `/outputs/{kind}/preflight` checks
  exact expected paths in the requested output directory, including remote scans.
  It does not treat two equal basenames in different folders as the same output.
- `colab_api.py` now accepts photo detector/model/precision and forwards them to
  `colab_batch.py`; explicit photo quality affects JPEG/WebP writes. PNG/BMP stay
  lossless. Legacy CLI image encoding defaults remain unchanged when omitted.
- `src/live.ts` implements capture, encoding, packet transport, hot changes,
  drop acknowledgements, bounded processing reservations, preview and cleanup.
  Native OpenCV grab/retrieve and virtual-camera timings are unavailable; browser
  encode/decode, transport sizes, four measured FPS rates, and backend metrics are
  exported instead. Performance sweep: 16 codec/batch cases, 3s warmup + 9s sample.
- `src/Outputs.tsx` uses real listings, scoped streamed media and actual ZIP APIs.
  Photo cache caps count/bytes, cancels obsolete requests and limits fetch concurrency.
- `server/gateway.mjs` is a production HTTP/binary-WebSocket gateway. Sites hosts
  the frontend only; the browser device and gateway must be on the tailnet.
- Browser managed capture replaces `auto`/`opencv_auto`; manual requested dimensions
  replace custom OpenCV sizing. No inert DirectShow/MSMF or OS virtual-camera controls.
- Live navigation is disabled while active to keep its canvas attached. Stop before
  changing workflow. Brief transport gaps recover by overdue coalescing; a 15s
  acknowledgement stall closes the session and requires restart. Socket closure
  is explicit rather than silently creating a new GPU session.
- No native companion code/package was built in this PR, as requested. The design
  above is a future option only.
