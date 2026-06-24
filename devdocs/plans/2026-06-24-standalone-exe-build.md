# Plan: Standalone desktop app EXE build

## Scope
- In:
  - Add an isolated build environment workflow using `.venv_build/`.
  - Add `requirements-build.txt` for PyInstaller/build-only dependencies.
  - Add a repeatable PowerShell build script for the current desktop remote app.
  - Document the build workflow in README and release notes.
- Out:
  - No build execution by Codex.
  - No tests or validation by Codex.
  - No installer/MSIX/signing pipeline yet.
  - No cross-platform packaging yet.

## GUI Components Affected
- [ ] Main window
- [ ] Panels/widgets
- [ ] Dialogs
- [x] Assets (icons, qss, etc.)
- [x] Config/build files
- [x] PyInstaller build script

## Action items
- [x] Create feature branch `feature/standalone-exe-build`.
- [x] Add `requirements-build.txt` with desktop-controller-only runtime requirements plus PyInstaller.
- [x] Add `.venv_build/` ignore rule.
- [x] Add `scripts/build_remote_app.ps1` for repeatable PyInstaller builds, including `-RecreateVenv` for failed/stale build environments.
- [x] Include desktop app assets (`windows_app/icon.ico`, `windows_app/dark_theme.qss`) in the build command.
- [x] Document build usage in README.
- [x] Update unreleased notes.

## Decisions
- Use `.venv_build/` instead of `.venv` so PyInstaller bundles from a clean build environment; keep it desktop-client-only instead of installing Colab/server/model packages.
- Start with `--onedir` as the default because it is easier to inspect and debug than `--onefile`.
- Provide `-OneFile` as an opt-in build script switch for later release experiments.
- Keep output under `dist/` and PyInstaller scratch files under `build/`; both are ignored.

## Open questions
- Whether the eventual release artifact should be onedir zip, onefile exe, or installer.
- Whether to rename `windows_app/` and launchers to neutral `remote_app/` names before the first public release.

## Validation
- [ ] Build on Windows: USER
- [ ] Launch packaged app: USER
- [ ] Connect to Colab API from packaged app: USER
- [ ] Verify icon/QSS/media playback assets: USER
