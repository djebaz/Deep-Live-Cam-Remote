# Unreleased

## Added
- Add an isolated standalone desktop app build workflow with `.venv_build/`, `requirements-build.txt`, and `scripts/build_remote_app.ps1` for PyInstaller packaging.
- Add a Lite PyInstaller build mode that excludes Live webcam dependencies (`cv2`, `numpy`, `pyvirtualcam`) for a smaller desktop controller executable.
- **Windows Remote App**: PySide6 desktop app for controlling Colab batch processing over Tailscale
  - Dark title bar and custom app icon on Windows 10/11
  - Photos and Videos tabs with full processing options (recursive, overwrite, skip processed, many faces, enhancer, opacity, sharpness, mouth mask, interpolation, poisson blend, color correction)
  - Video percentage range (start/end %) to process only portions of videos
  - Start/Stop toggle buttons with graceful cancel
  - Outputs tab with resizable split view, preview/player, and autoplay with prefetch
  - Local file upload support for source faces and input folders
  - Settings sync between Photos and Videos tabs
- **Colab Notebook Enhancements**:
  - Resumable cells: Clone/install, Tailscale install, and auth cells skip completed steps
  - Auto-update on re-run: setup cell runs `git pull` when repo exists
  - Local input/output directories for Windows app uploads
  - Sample data cleanup and nvtop installation

## Changed
- Notebook now clones from GitHub instead of embedding Python source as a bundle
- Setup cell is idempotent and pulls latest changes on re-run

## Release audit

- PRs: #1, #2, #3, #4
- Scope: PR #1 added Colab/remote/batch face-swap workflows; PR #2 added modern Colab batch processor with FFmpeg pipeline; PR #3 added Windows remote app with PySide6 UI, Colab FastAPI controller, resumable notebook cells, full processing options, and standalone app build scaffolding

