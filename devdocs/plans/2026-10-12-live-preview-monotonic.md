# Monotonic Live preview capture timing

## Scope and components

Fix the PR #13 review finding: preview deadlines currently depend on wall-clock
capture offsets and can freeze or lose buffering when the Windows clock changes.
Keep capture-based scheduling, FPS drift recovery, duplicate rejection and the
existing preview UI. No changes to models, processing or notebooks.

Components: `windows_app/live_webcam.py`, `colab_api.py`,
`windows_app/live_preview.py`, focused preview tests, README and unreleased notes.

## Decisions

- Send the existing monotonic `perf_counter()` capture stamp as
  `capture_monotonic`; the backend echoes it unchanged. Only relative client
  offsets are used, never comparisons against the server clock.
- Preserve `capture_time` as wall time for existing latency diagnostics.
- Schedule only from valid monotonic metadata. Missing/invalid metadata uses
  arrival-time buffering, including responses from older backends. Do not fall
  back to wall time or mix clock domains in the capture baseline.
- Restart the updated Colab API to enable the new metadata echo. Existing clients
  remain compatible with the unchanged wall-clock field.

## Actions

- [x] Inspect the capture, transport echo and preview scheduling path.
- [x] Add monotonic metadata and remove wall time from playback scheduling.
- [x] Extend regression coverage for forward/backward wall-clock adjustments,
  older-backend fallback and a zero monotonic stamp; preserve existing cases.
- [x] Sync README and unreleased notes.
- [ ] Open a downstream PR against `main`; do not merge.
- [ ] User validation: run preview regressions, build the Full app, restart the
  updated Colab API, and verify Live buffering during system-clock adjustments.

## Validation and blockers

No implementation blockers. Tests, syntax checks, builds and runtime validation
are deferred to the user per repository guidance. Regression cases are added but
not executed. Diff inspection is not runtime acceptance.
