# Plan: Web job reconnection and detail video autoplay

## Scope
- Recover established browser connections and active-job monitoring after temporary network/gateway/backend failures.
- Replace transient raw HTTP errors with a reconnecting notice that clears on recovery.
- Autoplay videos muted on entering the Outputs detail viewer, independently of slideshow.
- Preserve job identity, upload/submission safety, and existing controls.

## Action items
- [x] Inspect connection health, polling, API errors, and detail playback.
- [x] Add read-only polling with bounded requests, capped retry delays, and cleanup.
- [x] Show connection recovery and retain the current job through outages.
- [x] Enable muted detail video autoplay.
- [x] Request startup once about two seconds are buffered, without restarting paused videos.
- [x] Add video duration immediately to the right of Dimensions in detail metadata, including duration updates and an unknown-value placeholder.
- [x] Sync user documentation and release notes.
- [x] Review the complete diff and prepare the branch for a PR to main.

## Decisions
- Only monitoring GET requests retry. Job submission and uploads retain their existing semantics.
- Keep one monitor active: the job endpoint during an active batch, otherwise health.
- Retry network/timeouts and HTTP 5xx/408/429; surface other errors for user action.
- Use 15-second request deadlines and retry delays of 1, 2, 4, 8, then 15 seconds.
- Keep raw diagnostic details in Activity; show a contextual notice during recovery.
- Do not show stale FPS/ETA as current while reconnecting.
- Autoplay starts muted for browser compatibility; slideshow remains independently controlled.
- Follow-up: request playback at a two-second buffered-media threshold (or a complete shorter clip), leaving earlier native autoplay intact. No fixed five-second application buffer existed; wall-clock startup remains browser/network dependent.

## User-deferred validation
- No tests, builds, or browser runs requested; leave them to the user under repository guidance and the session's no-tests instruction.
- Real Colab/Tailscale interruption and recovery, authentication failures, missing jobs, and browser video autoplay remain unverified at runtime.

## Blockers
- None identified.
