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

## Dependency-install substeps

User feedback: one Install Python dependencies stage can stay active for minutes and needs more console detail. Added numbered activities based on real pip output (including package names and build stages), import-readiness messages and a persistent 10-second heartbeat that reports command duration and time since last output. Pip may revisit activities; substep numbering counts observed activities rather than a fabricated fixed number of packages or completion percentage. Keep these messages visible independently of the HTML display. Runtime quiet-command/build validation remains user-owned.

## NumPy source-build finding

User smoke output showed NumPy <2 selecting the 1.26.4 source archive and spending minutes in metadata preparation. Earlier user runtime logs established Python 3.13. PyPI metadata confirms 1.26.4 has no Python 3.13 Linux wheels, while 2.1.0 has them; NumPy's 2.1 release notes document Python 3.13 support.

Use a Python-dependent NumPy requirement, require binary NumPy wheels, include the installed NumPy version in readiness checks, and prevent starting with a changed version still loaded in the kernel. This changes the Python 3.13+ notebook profile and needs fresh Colab/InsightFace smoke validation; other dependency pins and the CUDA/cuDNN fix are preserved. The user was advised to stop the current source-build attempt.
