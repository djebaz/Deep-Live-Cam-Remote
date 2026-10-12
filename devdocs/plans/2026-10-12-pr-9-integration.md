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
- [ ] User-owned dependency installation, test suite, desktop build, and Colab/GPU/manual local camera validation.
- [x] User explicitly authorized committing and pushing the prepared integration on 2026-10-12; tests remain deferred. Committed as `af2f4ea` and published as draft PR #10 from the fork-owned branch because PR #9 uses upstream main as its source.

- [x] Expand README, contributor guidance and release notes; add the integration guide and update PR #10 description.

## Blockers and limits

Repository AGENTS.md reserves tests/builds for an explicit validation request. The user subsequently explicitly authorized committing and pushing this prepared result, overriding the skill test gate for this commit. Tests remain deferred and are not claimed to pass. Syntax compilation does not establish dependency or runtime compatibility. Use Python 3.11 as the documented baseline; upgraded pins and Python 3.14 backend remain unverified.
