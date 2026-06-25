# Audit Report: PR #5 Merge, Accidental Upstream PR, Branch State, and Release Notes

Date: 2026-06-25
Repository path: `C:\Users\dje\Documents\GitHub\Deep-Live-Cam-Remote`

## Executive summary

This audit reviewed the repository state after the Windows app patch-layer integration, the accidental upstream PR, the squash merge of the correct downstream PR, and the later release-note correction.

Current confirmed state:

- Local checkout is on `main`.
- `main` tracks `origin/main`.
- Correct downstream PR `djebaz/Deep-Live-Cam-Remote#5` is merged.
- Accidental upstream PR `hacksider/Deep-Live-Cam#1865` is closed and retitled `Accidental PR - please ignore`.
- The old feature branch was deleted remotely after PR #5 was merged.
- A stale local branch named `pr-5` remains and points at the pre-squash feature commit.
- `devdocs/releases/unreleased.md` currently has an uncommitted local edit to include PR #3 and PR #4 in the release audit.

No tests, GUI smoke checks, or builds were run as part of this audit.

## Commands and evidence gathered

### PowerShell and repo startup

The audit was performed from PowerShell 7 in the repository root, following repo guidance in `AGENTS.md`.

Relevant environment facts:

- Repo path: `C:\Users\dje\Documents\GitHub\Deep-Live-Cam-Remote`
- Active branch after user switched back: `main`
- Status at audit time:

```text
## main...origin/main
 M devdocs/releases/unreleased.md
```

### Git remotes

```text
origin   https://github.com/djebaz/Deep-Live-Cam-Remote.git (fetch)
origin   https://github.com/djebaz/Deep-Live-Cam-Remote.git (push)
upstream https://github.com/hacksider/Deep-Live-Cam.git (fetch)
upstream DISABLED (push)
```

Interpretation:

- Normal work should target `origin`, the downstream fork.
- `upstream` is configured for fetch only and has push disabled.
- Disabling upstream push does not prevent GitHub from opening a cross-repository PR from a fork branch to upstream.

### GitHub CLI repository context

At the time of the final audit, `gh repo view` reported:

```json
{"nameWithOwner":"djebaz/Deep-Live-Cam-Remote","url":"https://github.com/djebaz/Deep-Live-Cam-Remote"}
```

Interpretation:

- The GitHub CLI default repo is now correct.
- Earlier, during the erroneous PR creation, `gh repo view` resolved to `hacksider/Deep-Live-Cam`; that mismatch caused plain `gh pr create` to target upstream.

## PR audit

### Correct downstream PR

PR:

```text
https://github.com/djebaz/Deep-Live-Cam-Remote/pull/5
```

Current state:

```json
{
  "number": 5,
  "state": "MERGED",
  "title": "refactor(gui): integrate windows app patch modules",
  "baseRefName": "main",
  "headRefName": "feature/integrate-windows-app-patches",
  "mergedAt": "2026-06-25T08:54:34Z"
}
```

Actions performed:

- PR #5 was squash-merged into `main`.
- The remote feature branch `feature/integrate-windows-app-patches` was deleted by the merge command.
- Local `main` was refreshed with `git pull --ff-only origin main`.

Main after merge:

```text
main 2799dc4 [origin/main] refactor(gui): integrate windows app patch modules (#5)
```

### Accidental upstream PR

PR:

```text
https://github.com/hacksider/Deep-Live-Cam/pull/1865
```

Current state:

```json
{
  "number": 1865,
  "state": "CLOSED",
  "title": "Accidental PR - please ignore",
  "baseRefName": "main",
  "headRefName": "feature/integrate-windows-app-patches"
}
```

Cause:

- The plain `gh pr create` command used the GitHub CLI default repo context.
- That context was incorrectly resolving to `hacksider/Deep-Live-Cam` at the time.
- Because the branch existed in the fork, GitHub allowed creating a cross-repo PR from `djebaz:feature/integrate-windows-app-patches` to `hacksider:main`.

Cleanup performed:

- The upstream PR was closed.
- The upstream PR title/body were edited by the user to clarify it was accidental.
- The correct downstream PR was opened and merged.
- The feature branch was deleted after merge.

Remaining limitation:

- GitHub does not normally allow users to delete a PR page, its conversation, or its historical diff/commit record.
- Closing, retitling, and deleting the source branch is the normal cleanup path unless sensitive information was exposed.

## Branch audit

Current local branch list:

```text
feature/standalone-exe-build 9c7ea26 [origin/feature/standalone-exe-build] Add desktop app build release workflows
import/aiswap-remote         5f801f1 [origin/import/aiswap-remote: gone] Make Ruff workflow manual only
live-webcam-stability        19b8860 [origin/live-webcam-stability: gone] origress bar
main                         2799dc4 [origin/main] refactor(gui): integrate windows app patch modules (#5)
pr-5                         a3990db refactor(gui): integrate windows app patch modules
separate-processing-options  a8adabf [origin/separate-processing-options] Use separated processing options patch
test-brokenlive              74cd35d [origin/test-brokenlive] Improve outputs tab UX: better selection visibility, refresh progress, and load-aware autoplay
upstream-main                834092c [origin/upstream-main] Update Quick Start section to v2.7 RC6
```

Important branch findings:

- `main` is the correct active branch and is aligned with `origin/main`.
- `pr-5` is stale local-only branch state. It points to pre-squash commit `a3990db`, not the final squash commit `2799dc4` on `main`.
- The remote branch `origin/feature/integrate-windows-app-patches` is gone.
- Several unrelated local branches also show gone remote tracking branches; those were not changed by this audit.

Reflog evidence around the relevant branch activity:

```text
2799dc4 HEAD@{2026-06-25 11:07:59 +0200}: checkout: moving from pr-5 to main
a3990db HEAD@{2026-06-25 11:01:07 +0200}: checkout: moving from main to pr-5
2799dc4 HEAD@{2026-06-25 10:54:42 +0200}: pull --ff-only origin main: Fast-forward
5481d00 HEAD@{2026-06-25 10:54:36 +0200}: checkout: moving from feature/integrate-windows-app-patches to main
a3990db HEAD@{2026-06-25 10:48:06 +0200}: commit (amend): refactor(gui): integrate windows app patch modules
5ad9a42 HEAD@{2026-06-25 10:46:14 +0200}: commit (amend): refactor(gui): integrate windows app patch modules
5ec50ed HEAD@{2026-06-25 10:44:08 +0200}: commit: refactor(gui): integrate windows app patch modules
5481d00 HEAD@{2026-06-25 10:39:47 +0200}: checkout: moving from main to feature/integrate-windows-app-patches
```

Interpretation:

- The branch used for PR #5 was `feature/integrate-windows-app-patches`.
- The later `pr-5` branch is not the merged main branch; it is a local stale branch at the PR commit.
- The audit did not find evidence that `pr-5` was needed after PR #5 was squash-merged.

Recommended cleanup for stale local branch:

```powershell
git switch main
git branch -D pr-5
```

Do this only after preserving any local file changes you want to keep.

## Release notes audit

File reviewed:

```text
devdocs/releases/unreleased.md
```

Before correction, the release audit listed:

```text
- PRs: #1, #2, #5
```

The user reported that PR #3 and PR #4 should be included. Those PRs were checked with GitHub CLI:

```json
{"number":3,"state":"MERGED","title":"Separate photo and video processing options","url":"https://github.com/djebaz/Deep-Live-Cam-Remote/pull/3"}
{"number":4,"state":"MERGED","title":"Fix live webcam source upload and frame geometry","url":"https://github.com/djebaz/Deep-Live-Cam-Remote/pull/4"}
```

The file was updated locally to:

```text
- PRs: #1, #2, #3, #4, #5
- Scope: PR #1 added Colab/remote/batch face-swap workflows; PR #2 adds standalone desktop app build scaffolding, versioned artifacts, Lite packaging, and manual build/release GitHub Actions; PR #3 separates photo and video processing options; PR #4 fixes Live webcam source upload and frame geometry; PR #5 consolidates Windows app patch layers.
```

Current state:

- The release-note correction is present in the working tree.
- It is not committed yet.

Recommended next step:

```powershell
git switch -c docs/update-unreleased-pr-audit
git add .\devdocs\releases\unreleased.md
git commit -m "docs: update unreleased PR audit"
git push -u origin docs/update-unreleased-pr-audit
gh pr create --repo djebaz/Deep-Live-Cam-Remote --base main --head docs/update-unreleased-pr-audit --title "docs: update unreleased PR audit" --body "Updates the release audit to include merged PRs #3 and #4."
```

Alternatively, if direct commits to `main` are acceptable for this documentation-only fix, commit it directly on `main`; however, repo guidance prefers PR-based changes.

## Root cause analysis: accidental upstream PR

Primary root cause:

- `gh pr create` was run without an explicit `--repo` argument.

Contributing factors:

- The local repository has both `origin` and `upstream` GitHub remotes.
- GitHub CLI default repo resolution was pointed at `hacksider/Deep-Live-Cam` during the failed PR creation.
- `upstream` push was disabled, but GitHub still accepts cross-repo pull requests from fork branches.
- I did not run a preflight guard before creating the PR.

Impact:

- A visible upstream PR was created against `hacksider/Deep-Live-Cam`.
- It was closed and relabeled as accidental.
- No branch deletion or local cleanup can fully remove the PR page from GitHub history.

## Preventive controls

### Mandatory `gh` repo preflight

Before any PR operation in this repository:

```powershell
$repo = gh repo view --json nameWithOwner --jq .nameWithOwner
if ($repo -ne "djebaz/Deep-Live-Cam-Remote") {
  throw "Wrong gh repo: $repo"
}
```

### Always pass explicit `--repo`

Use this pattern for PR creation:

```powershell
gh pr create `
  --repo djebaz/Deep-Live-Cam-Remote `
  --base main `
  --head <branch-name> `
  --title "..." `
  --body-file .\tmp\pr-body.md
```

Use this pattern for PR viewing/editing/merging:

```powershell
gh pr view <number> --repo djebaz/Deep-Live-Cam-Remote
gh pr edit <number> --repo djebaz/Deep-Live-Cam-Remote
gh pr merge <number> --repo djebaz/Deep-Live-Cam-Remote --squash --delete-branch
```

### Set the default repo

The current `gh repo view` result is correct, but this command makes the intent explicit:

```powershell
gh repo set-default djebaz/Deep-Live-Cam-Remote
```

### Optional PowerShell wrapper

Add a guarded helper to your PowerShell profile:

```powershell
function New-DLCRPr {
  $repo = gh repo view --json nameWithOwner --jq .nameWithOwner
  if ($repo -ne "djebaz/Deep-Live-Cam-Remote") {
    throw "Blocked: gh is targeting $repo, expected djebaz/Deep-Live-Cam-Remote"
  }

  gh pr create --repo djebaz/Deep-Live-Cam-Remote @args
}
```

Then create PRs with:

```powershell
New-DLCRPr --base main --head <branch-name> --title "..." --body-file .\tmp\pr-body.md
```

### Optional Git alias guard

A repository-local script could enforce the same check before calling `gh pr create`. This is safer than relying on memory or manual discipline.

Recommended script path:

```text
scripts/create_downstream_pr.ps1
```

Recommended behavior:

- Verify current repo default is `djebaz/Deep-Live-Cam-Remote`.
- Verify `git remote get-url origin` contains `djebaz/Deep-Live-Cam-Remote`.
- Reject if `--repo` is not `djebaz/Deep-Live-Cam-Remote`.
- Call `gh pr create --repo djebaz/Deep-Live-Cam-Remote`.

## Recommended immediate next steps

1. Keep the current checkout on `main`.
2. Commit the release-audit correction on a docs branch or direct to `main`, depending on desired process.
3. Delete stale local `pr-5` after preserving any needed changes:

```powershell
git switch main
git branch -D pr-5
```

4. Keep using explicit `--repo djebaz/Deep-Live-Cam-Remote` for all `gh pr` commands.
5. Avoid plain `gh pr create` in this fork.

## Final status at time of report

- Correct downstream PR #5: merged.
- Accidental upstream PR #1865: closed and edited as accidental.
- Remote feature branch for PR #5: deleted.
- Local stale branch `pr-5`: still present.
- Working tree: one uncommitted docs change in `devdocs/releases/unreleased.md`.
- GitHub CLI default repo: `djebaz/Deep-Live-Cam-Remote`.

## Consequences and code quality review of PR #5

### Consequences of the accidental upstream PR

The upstream PR mistake had several consequences even though it was closed quickly:

- It created permanent public GitHub history on `hacksider/Deep-Live-Cam#1865` that cannot normally be deleted by the PR author.
- It exposed the downstream fork's implementation diff to the upstream project PR list, even though that work was intended only for `djebaz/Deep-Live-Cam-Remote`.
- It added review/notification noise for upstream maintainers.
- It created user trust risk because the operation targeted the wrong repository despite `upstream` push being disabled.
- It forced extra cleanup work: close upstream PR, edit its title/body, verify correct downstream PR, verify branch deletion, and audit the repository state.
- It showed that `gh` repository context is a high-risk hidden state and must be treated as unsafe unless explicitly checked.

### Consequences of the PR #5 refactor approach

PR #5 achieved the immediate goal of removing runtime `install()` monkey-patching from the launcher path, but the implementation still carries technical debt:

- It preserves behavior mostly by renaming and composing the old patch files rather than fully designing clean domain modules.
- `windows_app/app_base.py` is effectively a copy of the previous large `app.py`, so the codebase temporarily has an extra base layer instead of a fully flattened architecture.
- The new module names are clearer than `*_patches.py`, but several internal aliases still use old names such as `async_base`, which can confuse future maintainers.
- Mixin composition replaces import-order monkey-patching, but method resolution order still encodes the old patch ordering implicitly.
- The canonical `MainWindow` is thin, but behavior is now spread across multiple files with cross-module helper calls; this improves file size but not necessarily cohesion.
- Settings load/save behavior is still assembled through layered functions from processing and live modules rather than a single purpose-built settings service.
- The refactor was not validated by automated or manual execution during implementation due to the requested fast GUI workflow, which increased regression risk.

### Coding best-practice review

Positive practices in PR #5:

- Removed side-effect `install()` calls that mutated `base.MainWindow` at import time.
- Changed the launcher to target a canonical `windows_app.app.main` entrypoint.
- Preserved the old patch ordering through explicit class composition instead of relying on import order.
- Renamed patch files to purpose-oriented helper module names.
- Kept the user-facing launcher command unchanged.
- Updated README, release notes, and a live plan file.

Best-practice gaps in PR #5:

- The refactor was too mechanical: it renamed old patch modules instead of reducing coupling or redesigning responsibilities.
- `app_base.py` is a large legacy base module and should not become a long-term dumping ground.
- The code still has broad module-level functions assigned into mixins, rather than cohesive classes with explicit dependencies.
- Helper modules still depend heavily on `app_base as base`, which keeps a global namespace dependency instead of narrow imports.
- Some names are misleading after the refactor, especially `async_base` pointing at `output_tasks`.
- No small compatibility shim or deprecation path was documented for imports that may have referenced the old patch module names.
- The accidental `IndentationError` in `app_base.py` showed that the transformation process introduced syntax risk and should have included at least a syntax-only check if not prohibited by the fast workflow.
- The PR body noted no validation, which is honest, but the absence of syntax validation is still a code-quality risk for a refactor that rewrote module structure.

### Non-quality code left behind by PR #5

The following areas should be considered non-final or lower-quality architecture after PR #5:

- `windows_app/app_base.py`: contains the old monolithic app implementation and should be progressively split or folded into cleaner modules.
- `windows_app/app.py`: uses mixins primarily as a migration adapter, not as a clean final design.
- `windows_app/live_webcam.py`: still captures previous function references at import time and depends on layered settings behavior.
- `windows_app/processing_options.py`: mixes settings persistence, widget reads/writes, and batch start behavior.
- `windows_app/main_window_ui.py`: contains tab construction, status helpers, batch controls, output preview logic, and settings sync helpers in one module.
- `windows_app/output_tasks.py`: includes worker/task orchestration plus UI callbacks and output preview/download behavior.

These are acceptable as an intermediate cleanup from monkey-patching, but they are not a high-quality final modular architecture.

### Recommended follow-up quality plan

A follow-up cleanup should be planned separately from urgent GUI feature work:

1. Create a dedicated branch such as `refactor/windows-app-modules-v2`.
2. Move `AppSettings`, settings load/save, option coercion, and migration into a real `settings.py` module.
3. Move `ApiClient` and upload/download helpers into `api_client.py` without Qt dependencies.
4. Keep Qt workers in `workers.py` and remove UI-specific callbacks from generic worker helpers.
5. Split GUI tab construction by feature area only if it reduces coupling:
   - setup tab
   - batch tabs
   - outputs tab
   - live tab
6. Replace `app_base as base` global coupling with explicit imports from the modules that own each type/function.
7. Rename stale aliases such as `async_base` to match the new module purpose.
8. Add at least syntax validation expectations for future refactors, even when full tests/builds are user-owned.
9. Add a GitHub CLI PR guard script before any more release/PR automation work.

### Risk rating

- Functional risk: Medium. Behavior was intended to be preserved, but the implementation touched import paths and class composition and initially produced an `IndentationError`.
- Maintainability risk: Medium-high. Runtime monkey-patching is gone, but the replacement is still a compatibility-oriented mixin layer over a monolithic base.
- Process risk: High until guarded. The accidental upstream PR demonstrated that PR creation can target the wrong repository without explicit `--repo` checks.
- Security/privacy risk: Low if no secrets or private data were present in the accidental upstream PR; high if any sensitive information was ever included.

### Bottom line

PR #5 should be treated as a useful transitional refactor, not the final Windows app architecture. It removed the most dangerous runtime monkey-patching pattern and made the launcher cleaner, but it preserved much of the old coupling under new module names. The next quality pass should reduce `app_base.py`, remove global `base` coupling, clarify module boundaries, and add guarded PR tooling so this kind of repository-targeting mistake cannot recur.
