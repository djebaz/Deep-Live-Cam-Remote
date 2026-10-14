# Web remote controller

Base: main 04c118bc41b53613a03ee34255741f9be5e1853e (PR #14 merged).

Scope: separate React/TypeScript controller; retain Windows client and Colab GPU
execution. Audit controls and protocols from implementation; private production
HTTP/binary-WebSocket gateway; local file selection, jobs, Live, Outputs.

Decisions: deploy gateway on a Tailscale member and expose through Tailscale Serve
HTTPS. Same-origin deployment is primary. Sites can host the same static frontend
with an explicitly allowed origin and private HTTPS gateway; cloud hosting cannot
join the user's tailnet. Gateway destinations are operator allowlisted; browser
cannot create arbitrary upstream destinations. No public tunnel/Funnel required.

Native limitations: browser-managed camera backend; selected files only; no OBS
profile filesystem read or OS virtual-camera output. Companion requirements in
web_app/docs/parity.md. Ordinary browser workflows independent of companion.

Action items: audit, implement vertical workflows and additive backend plumbing,
run focused protocol/gateway/backend tests and production build, update docs,
publish frontend, open downstream PR without merging.

Validation: user selected local validation. Real Colab GPU, Tailscale, webcam/OBS,
system-clock changes in a real browser, and native companion remain user-owned.
No backend address or credentials were supplied.


Progress: implementation pushed and draft PR #15 opened for early review. Browser
workflows, gateway and additive backend changes are present. Windows files and
notebooks remain unchanged. Final local checks and publication proceed in the same
PR; native companion implementation excluded by user instruction.

Review follow-up: pulled user commit aaf6de1 and retained its three priority fixes.
Reconciled video option plumbing, shared segment naming, POSIX preflight names,
relay backpressure, sequence-independent preview, one-pass packet encoding and
cancelled preparation cleanup. Review table: web_app/docs/review-15.md.
Final tests/validation stopped at explicit user request; push only, no merge.
