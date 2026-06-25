# Live InsightFace Pack Selection Plan

Date: 2026-06-25
Branch: live-webcam-stability

## Scope
- Add a Live tab setting for InsightFace model pack selection: `buffalo_l`, `buffalo_m`, and `buffalo_s`.
- Send the selected pack to the Colab `/ws/live` session config.
- Load the selected pack in the Colab live engine by resetting the cached `FaceAnalysis` instance when the pack changes.
- Keep live source face embedding cached once per live engine/session.

## Decisions
- Default remains `buffalo_l` because InsightFace documents it as the safest embedding source for `inswapper_128`.
- `buffalo_m` and `buffalo_s` are exposed as experimental speed options.
- The source face is detected once during `ModernEngine` initialization and reused via `engine.default_source` for all live frames.

## Deferred validation
- User-owned live Colab/webcam validation for pack download latency, speed, and swap quality.
