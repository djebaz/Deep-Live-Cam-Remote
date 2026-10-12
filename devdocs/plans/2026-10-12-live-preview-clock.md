# Live preview clock recovery

Scope: fix Windows remote preview scheduling without altering capture controls,
transport, processing, or notebook setup (PR #12 remains separate).

Evidence: user log reports requested 20 FPS, actual capture about 25 FPS, and
continued processed frame arrivals at 6–9 FPS. The old clock derives deadlines
from sequence / requested FPS, so its target increasingly trails arriving frames.

Components: windows_app/live_preview.py; live_webcam.py reset state; README;
unreleased notes; focused regression coverage.

Decisions: map relative capture timestamps to a monotonic presentation clock;
use arrival-time deadlines for packets lacking valid timestamps. Coalesce overdue
frames rather than waiting for missing sequences. Preserve preview buffer delay.

Actions:
- [x] Inspect packet metadata and preview clock against the reported log.
- [x] Replace sequence-derived deadlines and retain duplicate rejection.
- [x] Update reset state, buffer gauge, and documentation.
- [ ] User validation: rebuild Full Windows app; repeat 20 FPS requested / 25 FPS
  actual capture, sequence drops, and preview buffer changes during Live.

Validation: syntax and whitespace checks only; tests/builds are user-owned per
AGENTS.md. Live Windows/Colab replay remains pending. No merge authorized.
