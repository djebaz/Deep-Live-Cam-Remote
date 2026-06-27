# Plan: Output Photo Autoplay Controls

## Scope
- In: Add a photo zoom selector, a photo auto-play visible-duration control, restart auto-play timing only after output load completes, and prefetch a configurable number of upcoming photos while photo auto-play is active.
- Out: New tests, smoke tests, packaging, and video playback behavior changes beyond preserving the existing video interval.

## Action items
- [x] Inspect output auto-play and prefetch code paths.
- [x] Add photo visible-duration control to the Outputs tab.
- [x] Add photo zoom selector with fit, 0.5x, 0.8x, 1x, 1.5x, and 2x.
- [x] Add configurable photo preload count with default 10.
- [x] Change auto-play scheduling to count from completed output load.
- [x] Prefetch a configurable number of upcoming photos during photo auto-play.
- [x] Sync README, AGENTS, and unreleased notes.

## Decisions and Design Changes
- 2026-06-27 Use a single-shot output timer so auto-play advances after the configured interval from the current output becoming loaded.
- 2026-06-27 Keep the existing 8 second video auto-play interval; the new control applies to photo visibility.
- 2026-06-27 Keep normal neighbor prefetch at 2 items, but increase photo prefetch to the configured count when auto-play is enabled.
- 2026-06-27 Store the original loaded photo pixmap so zoom changes can re-render without another download.
- 2026-06-27 Default output photo autoplay preload count to 10 and expose it as a 1-50 control.

## Open questions
- None.

## Validation
- [x] Syntax check run: `.\.venv\Scripts\python.exe -m py_compile .\windows_app\main_window_ui.py .\windows_app\output_browser.py .\windows_app\window_core.py`.
- [x] Tests were not run.
- [x] Smoke tests were not run.
- [x] Final tests and smoke tests deferred to user.

