# Colab install-cell progress

## Scope

Both full and mini Clone and install cells. Visible feedback for subprocess steps and model transfer; retain resumable setup and dependency profiles.

## Decisions

- Stage completion bar for six steps; no fabricated pip percentage. Active command shows elapsed total setup time and latest captured output.
- Use Colab's existing IPython HTML display, with text fallback. Inline stdlib helpers work before cloning or installing dependencies.
- Drain merged stdout/stderr in a reader thread so quiet commands can still update their status. Capture the last 30 lines for failure details, redact authenticated clone URLs/tokens, and HTML-escape display text.
- Stop subprocess groups on interruption. Optional nvtop install warns instead of falsely reporting success.
- Show model bytes/percentage through urlretrieve reporthook. Preserve staging/minimum-size behavior.
- Remove PySide6 and local camera enumeration from Colab install lists. Add headless processor status reporting and set the Colab engine to headless before processor imports; retain GUI routing in local runs and the tested CUDA/cuDNN dependencies. Do not uninstall existing packages or change Windows/local GUI requirements.
- Correct full notebook source clone default to main.

## Status

- [x] Implement synchronized inline helpers and stage updates in both sources.
- [x] Regenerate notebooks with `scripts/py_to_ipynb.py ... --eol lf`.
- [x] Parse changed setup cells, check unchanged cell IDs/notebook metadata and whitespace; Ruff findings remain at the 83 baseline.
- [ ] User-owned Colab smoke checks: fresh install, re-run with packages/models present, visible heartbeat during quiet command, download progress, failed subprocess output, cancellation without orphaned pip/git processes.
- [ ] Verify batch/Live/enhancer processor imports on a fresh Colab runtime without PySide6.

No dependency installation, subprocess runtime tests, GPU tests or Windows build were performed in this session. Open a draft PR pending Colab smoke validation.
