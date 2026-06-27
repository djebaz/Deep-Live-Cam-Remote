# Plan: Faster Stop Handling

## Scope
- In: Make Live Stop tear down sender/receiver tasks faster; make photo/video batch cancel react inside current item where practical; update docs and unreleased notes.
- Out: New tests, smoke tests, packaging, release/tag work, and broad processing rewrites.

## Action items
- [x] Inspect current live and batch stop paths.
- [x] Implement faster Live websocket task cancellation.
- [x] Add cooperative in-item cancel checks for video/photo batch processing.
- [x] Sync README, AGENTS, and unreleased notes.
- [x] Address PR review findings for OBS auto-FPS preview cadence and README Send scale labels.
- [x] Correct README and PR body Send scale list to match `LIVE_CAPTURE_SCALES`.
- [x] Add a client-side live transport packet byte cap for batched websocket sends.
- [x] Review diff, commit, push, and open PR to main.

## Decisions and Design Changes
- 2026-06-27 Use the existing branch `feature/live-drop-stale-work` per user request.
- 2026-06-27 Keep validation deferred under `$fast-implement`; no tests or smoke tests will be run.
- 2026-06-27 For Live, treat either sender or receiver task completion as enough to cancel the peer task so Stop is not blocked waiting for another websocket packet.
- 2026-06-27 For batches, keep API cancel semantics but add cooperative checks inside current photo/video processing so cancel does not only wait for the next file boundary.
- 2026-06-27 When OBS FPS is auto-detected after Live starts, update the preview timer interval to match the new FPS setting.
- 2026-06-27 Limit live transport batches by estimated packet bytes as well as frame count; single frames may still send alone, but large candidates no longer make an already-started batch exceed the cap.

## Open questions
- None.

## Validation
- [x] Syntax check run: `.\.venv\Scripts\python.exe -m py_compile .\colab_batch.py .\windows_app\live_webcam.py`.
- [x] Tests were not run.
- [x] Smoke tests were not run.
- [x] Final tests and smoke tests deferred to user.
- [x] `git diff --check` passed.

