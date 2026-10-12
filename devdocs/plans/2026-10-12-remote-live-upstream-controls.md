# Remote Live controls and shutdown parity

## Scope

Bring useful upstream local GUI behavior to the remote Windows app in PR #10. Preserve OBS Auto capture, custom portrait sizes, hot-change detector controls and the current settings format.

## Components

`windows_app/live_webcam.py`, README, AGENTS.md, unreleased notes, integration documentation and PR description.

## Actions and decisions

- [x] Compare upstream selectors and worker shutdown with existing remote equivalents.
- [x] Keep the existing persisted Detector size spinbox and capture mode/width/height settings.
- [x] Add 640x480, 960x540, 1280x720 and 1920x1080 capture presets in custom mode, with arbitrary widths/heights retained. Infer the preset from stored dimensions; no settings migration needed.
- [x] Lock capture presets during Live, like other restart-only capture settings.
- [x] Defer app close until active Live/polling workers finish, without blocking the Qt event loop. Invalidate pending Live preparation and disable the window while closing.
- [x] Join the capture thread before releasing OpenCV capture; release failed camera-open handles.
- [x] Syntax and whitespace checks; compare Ruff with the known 83-finding baseline.
- [ ] User-owned Full EXE rebuild and manual validation: preset persistence, custom 300x480 preservation, Auto behavior, restart-only locks, Stop/restart, close during Live, close while polling, failed camera start.

## Limits

No runtime GUI tests or build run in this session under repository guidance. Waiting for worker cleanup may prolong closing if a camera/backend call does not return; keeping the window alive avoids destroying a running QThread. Detector size already supports a broader set of 32-pixel increments than upstream's three presets, so it is retained.
