# Plan: Windows App Refactor Quality Follow-up

## Goal

Turn the PR #5 transitional cleanup into a cleaner modular Windows app architecture while preserving the current GUI behavior and launcher commands.

## Scope

### In

- Reduce `windows_app/app_base.py` as the legacy monolithic base.
- Move core non-GUI ownership into focused modules.
- Replace broad `app_base as base` coupling with explicit imports.
- Rename stale aliases and remove remaining patch-era naming.
- Keep user-visible GUI behavior unchanged.
- Add a safe PR creation guard so GitHub CLI cannot target upstream accidentally.

### Out

- No GUI redesign.
- No new features.
- No dependency changes unless a missing import forces a minimal correction.
- No notebook changes unless the app launcher workflow changes.
- No broad PyInstaller/build workflow changes.

## Current Problems to Fix

- `app_base.py` still contains the old monolithic app implementation and risks becoming a dumping ground.
- `app.py` uses mixins mostly as a migration adapter rather than as a clean final architecture.
- `live_webcam.py` still captures previous function references at import time and depends on layered settings behavior.
- `processing_options.py` mixes settings persistence, widget reads/writes, and batch start behavior.
- `main_window_ui.py` mixes tab construction, status helpers, batch controls, output preview logic, and settings sync helpers.
- `output_tasks.py` mixes worker/task orchestration with UI callbacks and output preview/download behavior.
- Old names such as `async_base` no longer match their module purpose.
- The earlier accidental upstream PR showed that PR creation needs an explicit repository guard.

## PR #6 Status

PR #6 is a modularization pass for this plan. It completes the low-risk ownership extraction and migration-adapter cleanup, while leaving deeper behavior-sensitive decoupling for follow-up work after local GUI validation.

Done in PR #6:

- Created the planned branch `refactor/windows-app-modules-v2`.
- Added focused ownership modules for settings, API/client helpers, worker classes, and shared window lifecycle/state.
- Moved `AppSettings`, settings persistence, processing option migration, and live option migration into `windows_app/settings.py`.
- Moved `ApiClient`, local path helpers, upload/download helpers, archive helper calls, and `job_payload()` into `windows_app/api_client.py`.
- Added `LiveWorker`, `PollWorker`, and `OutputTaskWorker` to `windows_app/workers.py`.
- Extracted the real shared MainWindow base into `windows_app/window_core.py`.
- Reduced `windows_app/app_base.py` into a compatibility shim that aliases `WindowCore` and re-exports compatibility symbols.
- Rewired `windows_app/app.py` to import `WindowCore` and `QApplication` directly instead of routing through `app_base`.
- Replaced stale `async_base` aliases with `output_tasks_base` in `processing_options.py`, `main_window_ui.py`, and `live_webcam.py`.
- Converted the migration mixins in `output_tasks.py`, `main_window_ui.py`, `processing_options.py`, and `live_webcam.py` from assignment tables to explicit forwarding methods.
- Replaced broad `app_base as base` imports in the app and GUI helper modules with explicit imports from PySide6, `settings.py`, `api_client.py`, `workers.py`, and `window_core.py`.
- Added `scripts/create_downstream_pr.ps1`, which verifies the current repo and `origin`, refuses upstream, and calls `gh pr create --repo djebaz/Deep-Live-Cam-Remote`.
- Kept the launcher commands unchanged.

Still open after PR #6:

- `live_webcam.py` still contains import-time previous-function capture and still needs a behavior-sensitive pass.
- `main_window_ui.py`, `output_tasks.py`, and `live_webcam.py` still need deeper responsibility splitting.
- Syntax and GUI validation still need to be run in the Windows/PySide environment by the user or in a validation-specific pass.

## Implementation Plan

### 1. Branch and PR safety

- Work on branch `refactor/windows-app-modules-v2`.
- Add a guarded PR helper script, for example `scripts/create_downstream_pr.ps1`, that:
  - verifies `gh repo view --json nameWithOwner --jq .nameWithOwner` is `djebaz/Deep-Live-Cam-Remote`;
  - verifies `origin` points at `djebaz/Deep-Live-Cam-Remote`;
  - always calls `gh pr create --repo djebaz/Deep-Live-Cam-Remote`;
  - refuses to run if the resolved repo is `hacksider/Deep-Live-Cam`.

### 2. Extract core non-GUI modules

- Create or complete `windows_app/settings.py`:
  - own `AppSettings`;
  - own `load_settings()` / `save_settings()`;
  - own legacy migration for flat fields, `photos_options`, `videos_options`, and `live_options`.
- Create or complete `windows_app/api_client.py`:
  - own `ApiClient`;
  - own HTTP request, upload, download, and archive helpers;
  - keep this module free of Qt imports.
- Create or complete `windows_app/workers.py`:
  - own `PollWorker`;
  - own output task worker;
  - own Live webcam worker;
  - keep worker logic generic and keep UI-specific callbacks in UI/app modules.

### 3. Re-home GUI responsibilities

- Keep `windows_app/app.py` as the canonical entrypoint and `MainWindow` owner.
- Move setup, batch, outputs, and live tab construction into focused modules only where it reduces coupling.
- Keep shared UI helpers small and explicit.
- Remove import-time previous-function capture patterns.
- Replace function-assigned mixins with either direct `MainWindow` methods or cohesive helper classes with explicit dependencies.

### 4. Remove patch-era coupling and names

- Replace `from windows_app import app_base as base` with explicit imports from owning modules.
- Rename stale aliases:
  - `async_base` -> `output_tasks` or `output_task_helpers`;
  - any remaining patch-era names -> current module-purpose names.
- Decide whether old module names need compatibility shims:
  - if yes, add tiny documented shims that import from the new modules;
  - if no, document that the patch modules were internal and intentionally removed.

### 5. Documentation and release notes

- Update `README.md` only if module/launcher wording changes.
- Update `AGENTS.md` only if the Windows app workflow or PR guard workflow changes.
- Update `devdocs/releases/unreleased.md` with the refactor and PR guard changes.
- Keep this plan updated as implementation decisions change.

## Validation Plan

Unless the user explicitly forbids validation, run at least syntax checks for changed Python files:

```powershell
python -m py_compile .\run_windows_remote_app.py .\windows_app\*.py
```

User-owned manual validation:

- Launch the app with `python run_windows_remote_app.py` or `./run-windows-remote-app.bat`.
- Confirm Setup, Photos, Videos, Outputs, Live, and Logs tabs load.
- Confirm Photos/Videos options still sync and start/stop behavior still works.
- Confirm Outputs refresh, preview, prefetch, selected/all download, and Taildrop transfer still work.
- Confirm Live webcam source upload, live options, buffered preview, preview scaling, stop, and close cleanup still work.

## Acceptance Criteria

- `run_windows_remote_app.py` still launches through `windows_app.app.main`.
- `app_base.py` is removed or substantially reduced to a narrow compatibility layer.
- Core settings, API client, and workers have clear owning modules.
- No module depends broadly on `app_base as base` when explicit imports are possible.
- Stale aliases such as `async_base` are gone.
- No runtime monkey-patching or side-effect `install()` pattern returns.
- PR creation workflow includes an explicit downstream repo guard.
- README/release notes are synchronized with the final architecture.

## Risk Notes

- Functional risk is medium because import paths and class composition are being changed.
- Maintainability risk stays medium-high until `app_base.py` and global `base` coupling are removed.
- Process risk stays high unless the PR guard script is added and used.
- Security/privacy risk is low if no secrets are present, but any future accidental upstream PR should still be treated as a serious process incident.

## Bottom Line

PR #5 removed the worst monkey-patching problem, but it left a compatibility-oriented architecture. This follow-up should make module ownership explicit, reduce global coupling, remove patch-era names, and add PR tooling that prevents another upstream-targeting mistake.
