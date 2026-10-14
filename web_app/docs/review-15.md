# PR #15 review resolutions

The follow-up builds on user commit `aaf6de1` (retained). The final commit
`4e51d24` was validated: 25 web tests, 34 Python tests and the production build
passed (details in [validation.md](validation.md)). Hardware acceptance remains
unverified.

| Finding | Result |
| --- | --- |
| 1. Sticky detector size | User commit retained: always call setter; its None default resets to 640. |
| 2. Segment output naming | Percentage flow has no mismatch. CLI explicit start/duration naming and preflight now share `video_output_path`; optional ss/duration preflight fields check CLI segments. |
| 3. Windows static traversal guard | User's `path.relative`/separator implementation retained. Windows path fixture covers a real gateway asset request; native Windows remains unverified. |
| 4. Video detector/model/precision | Shared photo/video validation and CLI forwarding; video ProcessConfig receives these options. |
| 5. Remote POSIX filenames | Preflight preserves existing colons and literal backslashes instead of invoking upload filename normalization; traversal and resolved-path confinement remain. |
| 6. Preflight scope | User's known-layout-root policy retained; output checks also stay within the selected output directory and remote scans exclude escaping symlinks. |
| 7. Relay backpressure | Pause/resume reads at 8/4 MiB instead of closing on brief write pressure; persistent stall timeout remains bounded. Binary/text framing unchanged. |
| 8. Preview sequence freeze | Source sequence is diagnostic; local arrival order governs coalescing/display. Capture epoch resets rebase monotonic timing. |
| 9. Header serialization | Encode each header once per packet and reuse its bytes for size calculation and framing. Capture batching reserves a conservative bounded header allowance. |
| Pending file cap | Confirmed applies with skip off; intentionally checked after skip filtering so large selections with <=1000 pending files remain usable. Extra preflight round-trips are a minor cost, not a correctness failure. |
| Manifest stability (follow-up) | Video jobs forward `--detector-size` only when the client set it, so existing manifests keep matching; photos keep always forwarding it. |
| Overwrite precedence (follow-up) | Local and remote preflight run only when skip-processed is on and overwrite is off, matching `colab_batch`. |
| Preview starvation (follow-up) | Queue cap follows `max(3, ceil((buffer+2)*fps))`; when bounds evict frames the schedule is pulled forward so playback always progresses. Epoch reset needs a >1 s backwards capture jump; an immediate resend of the same `seq` is dropped. |
| Cleanup guard (follow-up) | Cleanup refuses when an active job's root is the batch, inside it, or an ancestor; job registration and cleanup's check+delete share `JOBS_LOCK`. Upload locks are per batch, not a hashed pool. |
| Stale saved job (follow-up) | `check()` falls back to the backend's `active_jobs` when the saved job is missing or finished (`chooseJob`). |
| Cancelled upload directories | Scoped batch cleanup after preparation failure/cancellation; serialize with upload writes; refuse active-job directories and symlinks. Never clean after a possibly successful submission whose response was lost. |

Preflight accepts paths within DRIVE_ROOT, LOCAL_ROOT, and the two local output
roots, including custom subfolders. Arbitrary processing paths outside these
roots can still be submitted with skip-processed preflight disabled; Outputs
continues browsing only its fixed photo/video roots. No native companion added.
