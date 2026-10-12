# PR #9 upstream integration

Source: https://github.com/djebaz/Deep-Live-Cam-Remote/pull/9
Base: 867d7e5fe9df20f5b46049ab3b1ba5da8f556028
Upstream: a92427518a8bf89fee2432a9fccd0a61fb4c2654
Branch: integrate/pr-9-upstream

## Scope and components

Import upstream shared modules, local camera UI, dependencies and regression tests. Preserve remote controls, batch/API behavior and downstream documentation. Update notebook certifi installation and rebuild its artifact.

## Actions and decisions

- [x] Inspect repo guidance and reconstruct both sides of seven conflicts.
- [x] Preserve model-pack and precision selection; share detector size setting.
- [x] Retain enhancer helper APIs and incomplete-file thresholds with central TLS/resumable downloads and GPEN mirrors.
- [x] Keep Colab NumPy 1 / ORT 1.23.2 profile, add certifi.
- [x] Keep scikit-learn; add a Keras backend dependency for fresh root installs.
- [x] Rebuild notebook with `python scripts/py_to_ipynb.py google-colab/Deep_Live_Cam_Remote_Batch.py google-colab/Deep_Live_Cam_Remote_Batch.ipynb --eol lf`.
- [x] Compile 22 changed Python sources; check whitespace and conflict markers.
- [x] User smoke test: Tailscale health, 19 photos completed without failure, latest desktop build skipped all 19 on repeat before job creation.
- [ ] Broader validation: dependency installation, test suite, Colab videos/Live/cancellation, GPU execution and local camera compatibility.
- [x] User explicitly authorized committing and pushing the prepared integration on 2026-10-12; tests remain deferred. Committed as `af2f4ea` and published as draft PR #10 from the fork-owned branch because PR #9 uses upstream main as its source.

- [x] Expand README, contributor guidance and release notes; add the integration guide and update PR #10 description.

## Blockers and limits

Repository AGENTS.md reserves tests/builds for an explicit validation request. The user subsequently explicitly authorized committing and pushing this prepared result, overriding the skill test gate for this commit. Tests remain deferred and are not claimed to pass. Syntax compilation does not establish dependency or runtime compatibility. Use Python 3.11 as the documented baseline; upgraded pins and Python 3.14 backend remain unverified.

## Finalization

PR #10 is ready for review and conflict-free as observed on 2026-10-12. The GitHub compilation workflow passed for `2fa7bb2`. User smoke testing establishes photo processing and skip preflight behavior; it does not establish CUDA execution. No PR merge has been performed by this session.

Ruff 0.15.7 validation: the repository-wide run reports 83 pre-existing findings, also present on the downstream base `867d7e5`. The one additional finding introduced by this PR (the certifi readiness import) was annotated as intentional. Existing lint debt remains; the Ruff workflow is not green.

## CUDA repair

- [x] User's direct ONNX swapper probe reproduces CUDA initialization failure: missing `libcublasLt.so.12`, active providers CPU only.
- [x] Ensure CUDA/cuDNN extras in both notebook setup flows even when other imports are ready; preload in the shared batch/Live engine and log actual swapper session providers.
- [x] Correct mini notebook clone default to main and add certifi; regenerate both notebooks with LF.
- [x] Compile changed batch engine and check whitespace; no automated tests run.
- [x] User GPU smoke evidence after cuDNN 9.26 downgrade: CUDA graph initialized; active CUDA swapping/GFPGAN; 37 photos completed in the supplied excerpt without cuDNN errors/fallback; sustained T4 utilization and about 6.1 GiB VRAM.
- [x] Pin tested cuDNN 9.26.0.51 in both notebooks and document the 9.27 runtime regression.
- [ ] Final completion summary for the 90-photo job; other GPU/runtime workflows remain unverified.

## Remote GUI rollback

The user reported preview freezes with the build containing `15799c1` and requested returning to the previously working behavior. Reverted that GUI commit, including capture presets and its shutdown changes, while retaining the CUDA preload/cuDNN pin. `windows_app/live_webcam.py` again matches `25c5228`. The preview renderer had not changed in `15799c1`; this rollback is a controlled comparison, not a verified fix for the freeze. Syntax/whitespace checks passed. Rebuild the Full EXE and compare with the same OBS/source/FPS settings before further preview changes.
