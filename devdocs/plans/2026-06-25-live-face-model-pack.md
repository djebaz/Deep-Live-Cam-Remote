# Live InsightFace Pack Selection Plan

Date: 2026-06-25
Branch: live-webcam-stability

## Scope
- Add Live tab settings for InsightFace model pack selection (`buffalo_l`, `buffalo_m`, `buffalo_s`) and swapper precision (`fp32`, `fp16`).
- Send the selected pack to the Colab `/ws/live` session config.
- Load the selected pack and selected swapper precision in the Colab live engine by resetting cached models when settings change.
- Keep live source face embedding cached once per live engine/session.

## Decisions
- Provision `inswapper_128_fp16.onnx` from the FaceFusion model-pack mirror and keep model binaries ignored by git.
- Default remains `buffalo_l` because InsightFace documents it as the safest embedding source for `inswapper_128`.
- `buffalo_m` and `buffalo_s` are exposed as experimental speed options.
- The source face is detected once during `ModernEngine` initialization and reused via `engine.default_source` for all live frames.

## Deferred validation
- User-owned live Colab/webcam validation for pack download latency, speed, and swap quality.
