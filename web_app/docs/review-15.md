# PR #15 review resolutions

The follow-up is based on user commit `aaf6de1`, pulled before committing.
Final validation was stopped at the user's request. Prior regression runs are
recorded in [validation.md](validation.md); final combined changes remain unverified.

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
| Cancelled upload directories | Scoped batch cleanup after preparation failure/cancellation; serialize with upload writes; refuse active-job directories and symlinks. Never clean after a possibly successful submission whose response was lost. |

Preflight accepts paths within DRIVE_ROOT, LOCAL_ROOT, and the two local output
roots, including custom subfolders. Arbitrary processing paths outside these
roots can still be submitted with skip-processed preflight disabled; Outputs
continues browsing only its fixed photo/video roots. No native companion added.
