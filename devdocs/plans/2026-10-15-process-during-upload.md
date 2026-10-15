# Plan: Process while remaining batch inputs upload

## Approved scope
- One declared, isolated batch job for local inputs, shared by web and Windows.
- Process the first fully uploaded input while later files upload.
- Keep uploads and processing separately visible; reuse the engine across files.
- Preserve relative output names, manifests, atomic outputs, cancellation, and no duplicate processing on repeated uploads/submission.
- Keep remote-directory jobs and older APIs on the existing path.

## Implementation
- [x] Backend: declared manifest, completed-file queue, idempotent creation/publication/completion, finite abandoned-upload wait.
- [x] Reuse the existing batch processor with a dynamic input iterator and fixed declared total.
- [x] Web: publish the job ID before continuing uploads, monitor concurrently, separate progress, abort/finalize failed uploads.
- [x] Windows: return the job before uploading inputs, start an upload worker alongside the poller, preserve relative paths and cooperative upload cancellation.
- [x] Gateway allowlist, docs, static review, and branch prepared for a new PR.

## Decisions
- Do not scan a growing directory. Publish a file only after its complete upload is renamed into place.
- Declare all names/sizes before starting, so item totals remain stable.
- Repeated uploads acknowledge completed files without overwriting or requeueing them.
- Require an explicit completion signal; failed/abandoned uploads fail the job instead of leaving it waiting indefinitely.
- Track incoming upload bytes before multipart parsing completes, so the 15-minute inactivity bound does not expire a healthy long upload.
- Wait for the first file before acquiring the engine lock; retain the engine for the batch once processing starts. This preserves process-wide model/global state isolation.
- Source validation and skip-processed preflight happen before batch creation.
- Capability-gate the feature; preserve existing upload-first behavior on older APIs.
- Serialize completion with upload publication. Preserve terminal backend errors when a client aborts remaining uploads automatically.
- Windows preflight uses full relative paths and the actual Colab output directory. The photo/video kind is explicit before a remote input path is assigned, preserving photo-specific controls.
- Retain an uncertain Windows declaration and reuse the original endpoint/options/files on Start; never generate a new batch identity while it is unresolved.

## Validation deferred by the user
- No tests, browser/Windows runs, builds or GPU jobs were run. Python `py_compile`, gateway `node --check`, and `git diff --check` passed. Type checking remains deferred.
- Isolated standards/spec static reviews completed; reported client preflight/uncertainty/refusal issues and completion/publication race were corrected and re-reviewed.
- Runtime checks needed: upload/processing overlap, retries/lost replies, stop during upload, rejected files, unfinished uploads, older APIs, and Windows progress.
