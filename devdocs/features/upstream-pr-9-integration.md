# Upstream update in PR #10

[PR #10](https://github.com/djebaz/Deep-Live-Cam-Remote/pull/10) integrates the update proposed in [PR #9](https://github.com/djebaz/Deep-Live-Cam-Remote/pull/9) into this fork. The source is `hacksider/Deep-Live-Cam` at `a92427518a8bf89fee2432a9fccd0a61fb4c2654`; the downstream base is `867d7e5fe9df20f5b46049ab3b1ba5da8f556028`.

PR #9 contains 48 upstream commits. PR #10 uses the fork-owned branch `integrate/pr-9-upstream` to resolve its seven conflicts and preserve remote/Colab behavior. It is ready for review following the user-run Colab photo smoke test; broader runtime validation remains pending.

## Imported changes

| Area | Change |
| --- | --- |
| Dependencies | Root requirements move to NumPy 2, OpenCV 4.14, ONNX 1.22, newer platform-specific ONNX Runtime, Keras 3 and OpenNSFW2 0.18. |
| Models | Central downloader uses verified TLS with certifi, per-target locks, resumable `.part` transfers and expected download sizes. Automatic provisioning includes the default `buffalo_l` pack. |
| Local camera UI | Persisted capture resolution and detection input size selectors; detection sizes are 160, 320 and 640. The local CLI also accepts `--det-size`. |
| Local preview | Workers are joined on close, including slow shutdown; failed camera startup can close safely. Failed source changes can recover when the working source is selected again. |
| Random source | Failed or invalid random-face downloads preserve the existing image; successful downloads replace it after staging. |
| Video | Face-mapping disk fallback creates and extracts frames; frame seeking clamps to valid indices; FPS detection falls back to 30 on command or parsing failures. |
| Compatibility | Shared OpenVINO provider configuration and Windows DLL setup; CoreML optimization caches include detection input shape; shared image extension handling includes WebP. |
| Maintenance | Turkish translations, Dependabot configuration, Python compilation workflow and upstream regression tests. |

Camera selectors and worker changes above belong to the local `run.py` application. The remote controller retains its existing OBS capture, send-scale and Live controls. Shared modules affect the Colab API and batch processor and batch engine; the GPU follow-up also updates `colab_batch.py` initialization.

## Fork-specific additions and conflict resolutions

- Preserve explicit remote InsightFace pack selection (`buffalo_l`, `buffalo_m`, `buffalo_s`) and swapper precision (`fp32`, `fp16`). Defaults remain `buffalo_l` and fp32; CUDA availability does not override the precision selection.
- Route the remote detector-size setter through `modules.globals.det_size`, matching the local UI and CLI. Publish the analyser only after initialization completes, retaining upstream's safe initialization behavior.
- Preserve enhancer helper APIs and existing minimum-size checks while delegating transfers to the centralized downloader. Retain the fork's GPEN sources and upstream GitHub mirrors, plus the fork's fp16 fallback source. Partial files are discarded before trying another source.
- Retain scikit-learn in root requirements for clustering. Add TensorFlow for Python below 3.14 and Torch for Python 3.14+ so a fresh root installation declares a Keras backend. Installation and backend compatibility are still unverified.
- Add certifi to both Colab notebooks. Install ONNX Runtime GPU with its CUDA/cuDNN extras even on re-runs where the import readiness check passes, preload NVIDIA pip libraries before model sessions, and report active swapper providers. Rebuild both notebooks from their markerized sources.
- Preserve the downstream README and document dependency profiles, migration and validation limits.

## Dependency profiles

| Workflow | Dependency source | NumPy / OpenCV / ONNX Runtime |
| --- | --- | --- |
| Full local processing and root installation | `requirements.txt` | NumPy 2; OpenCV 4.14.0.94; ORT GPU 1.26.0 outside macOS; official ORT 1.28.0 on macOS arm64 and 1.23.0 on other macOS architectures. |
| Colab API and batch runtime | Explicit install list in the notebook source | NumPy below 2; OpenCV 4.10.0.84; ORT GPU 1.23.2. Includes certifi without adopting root's dependency upgrade. |
| Packaged remote desktop controller | `requirements-build.txt` | NumPy below 2 and OpenCV 4.10.0.84; no inference-server/model stack. |

Python 3.11 remains the documented fork baseline. Root dependency markers for newer Python versions do not establish that those versions have been validated.

### Existing installations

Create a fresh virtual environment for the root upgrade. Reusing a NumPy 1 environment can leave binary extensions compiled against the previous NumPy ABI. On macOS, remove the old `onnxruntime-silicon` package before installing official ONNX Runtime. Preserve model files and settings outside the old environment.

Colab continues using the notebook's explicit install list. Successful readiness imports do not verify every installed version. Both notebooks now explicitly ensure `onnxruntime-gpu[cuda,cudnn]==1.23.2` and certifi after that check, so missing CUDA 12/cuDNN 9 libraries are repaired even in an existing runtime. The mini notebook default clone branch is corrected to `main`; before merge, select `integrate/pr-9-upstream` manually to try this fix. Restart the Colab runtime if package replacement leaves already imported libraries stale.

For OpenVINO, install matching OpenVINO and ONNX Runtime OpenVINO versions using the [upstream provider documentation](https://onnxruntime.ai/docs/execution-providers/OpenVINO-ExecutionProvider.html#requirements). Root requirements do not select that optional provider distribution.

Model transfers need access to Hugging Face and, for fallback sources, GitHub release downloads. An interrupted transfer can leave a `.part` file for resumption. Completed new downloads are checked against expected byte sizes; existing files use presence/minimum-size checks, not cryptographic integrity checks. Experimental `buffalo_m` and `buffalo_s` provisioning continues through InsightFace when the central manifest has no matching members.

## Validation status

Completed during integration:

- Syntax compilation of 22 changed Python sources.
- Whitespace checks and removal of all merge-conflict markers.
- Notebook regeneration with `python scripts/py_to_ipynb.py google-colab/Deep_Live_Cam_Remote_Batch.py google-colab/Deep_Live_Cam_Remote_Batch.ipynb --eol lf`.

User-run smoke test on 2026-10-12:

- Colab API health check succeeded over Tailscale from Windows.
- A 19-photo batch completed: 19 completed, 0 skipped, 0 failed.
- Using the latest desktop build with Skip processed checked and Overwrite unchecked, repeating the folder skipped all 19 photos during preflight; no processing job started.
- The initial photo smoke test ran before the CUDA repair; its successful output did not establish GPU execution. Later GPU evidence is recorded below.

The imported regression tests cover face-mapping fallback, TLS verification, local preview teardown/source changes/random downloads and FPS handling. They have not been executed in this session.

Still pending, when validation is explicitly requested under repository guidance:

- Fresh root dependency installation and NumPy/InsightFace/backend import checks.
- Test suite execution, including the offscreen Qt preview tests.
- Colab video processing, cancellation and remote Live with fp32/fp16 and model-pack selections.
- Local camera resolution/detection changes and shutdown behavior.
- Broader CUDA configurations, CoreML and OpenVINO checks on applicable hardware; desktop packaging with the separate build profile.

Ruff 0.15.7 validation: the repository-wide run reports 83 pre-existing findings, also present on the downstream base `867d7e5`. The one additional finding introduced by this PR (the certifi readiness import) was annotated as intentional. Existing lint debt remains; the Ruff workflow is not green.

## CUDA follow-up after smoke testing

A direct swapper session probe on the user's Colab T4 failed to find `libcublasLt.so.12` and returned only `CPUExecutionProvider`. This confirms CUDA initialization failure for that probe; successful photo output alone did not verify GPU execution.

Both notebooks now install ONNX Runtime's CUDA/cuDNN extras, including on setup re-runs. `ModernEngine` calls `onnxruntime.preload_dlls(directory="")` before processor imports and ONNX session creation, covering photo/video batches and remote Live. It logs active swapper session providers and warns when a requested CUDA provider falls back to CPU. Detection/enhancer provider execution is not asserted by this log.

Keep Colab's Latest runtime; an older image is not required by this repair. The missing-library probe reproduces the failure on the user's runtime. The updated code passed syntax and whitespace checks, and both notebooks were regenerated with `--eol lf`; the user subsequently validated the cuDNN 9.26 repair as described below. Confirm the active swapper session includes CUDA and monitor utilization during a non-skipped job. Restart the API after updating code or installing libraries so cached CPU sessions are replaced.

### Tested cuDNN version

The user-run batch initially initialized CUDA but then failed inference with cuDNN 9.27.0 (`HEURISTIC_QUERY_FAILED` and `GRAPH_EXECUTION_FAILED`), causing ONNX CPU fallback and failed GFPGAN enhancement. Session creation alone was therefore insufficient validation.

After installing `nvidia-cudnn-cu12==9.26.0.51` and restarting the API, the supplied run excerpt shows successful CUDA graph initialization, active CUDA swapper/GFPGAN providers, and 37 photos completed with photo 38 starting, without cuDNN errors or CPU fallback messages. The accompanying T4 monitor shows sustained GPU utilization, often around 50–90%, and about 6.1 GiB VRAM allocated. The excerpt does not include the final summary for the 90-photo job.

Both notebooks now pin that tested cuDNN version in fresh-install and re-run setup commands. This prevents the dependency repair from selecting the observed failing 9.27 release. Other hardware and root dependency profiles remain outside this smoke test. A related report is documented in [ONNX Runtime issue #26274](https://github.com/microsoft/onnxruntime/issues/26274#issuecomment-6080148695).
