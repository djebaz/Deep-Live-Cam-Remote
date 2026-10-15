import { Api, uploadSource, type Health } from "./api";
import { jobPayload, type Kind, type Preferences } from "./settings";
export interface Input {
  file: File;
  relative: string;
}
export function selectedInputs(
  files: File[],
  kind: Kind,
  recursive: boolean,
): Input[] {
  const extensions =
    kind === "photos"
      ? /\.(bmp|jpe?g|png|webp)$/i
      : /\.(avi|m4v|mkv|mov|mp4|webm)$/i;
  const result = files
    .map((file) => ({
      file,
      relative: file.webkitRelativePath
        ? file.webkitRelativePath.split("/").slice(1).join("/")
        : file.name,
    }))
    .filter(
      (x) =>
        extensions.test(x.relative) && (recursive || !x.relative.includes("/")),
    )
    .sort((a, b) => a.relative.localeCompare(b.relative));
  const names = new Set<string>();
  for (const x of result) {
    if (names.has(x.relative.toLowerCase()))
      throw new Error(`Duplicate path: ${x.relative}`);
    names.add(x.relative.toLowerCase());
  }
  return result;
}
export function expectedOutput(relative: string, kind: Kind) {
  const slash = relative.lastIndexOf("/");
  const dot = relative.lastIndexOf(".");
  return (
    relative.slice(0, Math.max(slash + 1, dot)) +
    "_face_swapped" +
    (kind === "photos" ? relative.slice(dot).toLowerCase() : ".mp4")
  );
}
export async function startBatch(
  api: Api,
  p: Preferences,
  kind: Kind,
  files: File[] | null,
  source: File | undefined,
  signal: AbortSignal,
  log: (s: string) => void,
  progress: (l: number, t: number) => void,
) {
  const health = await api.request<Health>("/health", "GET", undefined, signal);
  // Fail before any upload when the declared remote source image does not exist.
  if (!source && p.source_face && health.web_capabilities?.source_check) {
    const found = await api.request<{ exists: boolean }>(
      "/sources/check",
      "POST",
      { path: p.source_face },
      signal,
    );
    if (!found.exists)
      throw new Error(
        `Source face not found on Colab: ${p.source_face}. Select a local source image or fix the remote source path.`,
      );
  }
  let input = p[`${kind}_input`];
  let selected: Input[] = [];
  if (files !== null) {
    selected = selectedInputs(files, kind, Boolean(p[kind].recursive));
    if (!selected.length)
      throw new Error("No supported selected files. Choose files or a folder.");
    if (
      !health.web_capabilities?.relative_uploads ||
      !health.web_capabilities?.output_preflight
    )
      throw new Error(
        "Update and restart Colab API from this PR to enable relative uploads and exact preflight.",
      );
    // Overwrite takes precedence over skip, matching colab_batch.
    if (p[kind].skip_processed && !p[kind].overwrite) {
      log(`Checking ${selected.length} inputs against ${p[`${kind}_output`]}`);
      const skipped = new Set<string>();
      for (let i = 0; i < selected.length; i += 1000) {
        const r = await api.request<{ processed: string[] }>(
          `/outputs/${kind}/preflight`,
          "POST",
          {
            output_dir: p[`${kind}_output`],
            relative_paths: selected.slice(i, i + 1000).map((x) => x.relative),
          },
          signal,
        );
        r.processed.forEach((x) => skipped.add(x));
      }
      log(
        `Skipped ${skipped.size} already processed; ${selected.length - skipped.size} remain.`,
      );
      selected = selected.filter((x) => !skipped.has(x.relative));
      if (!selected.length) {
        log("Everything is already processed. No uploads or job started.");
        return null;
      }
    }
    if (selected.length > 1000)
      throw new Error(
        "Maximum 1000 pending files per batch. Select a smaller subset.",
      );
  }
  if (
    files === null &&
    p[kind].skip_processed &&
    !p[kind].overwrite &&
    health.web_capabilities?.output_preflight
  ) {
    const preflight = await api.request<{
      processed: string[];
      total: number;
      remaining: number;
    }>(
      `/outputs/${kind}/preflight`,
      "POST",
      {
        input_dir: input,
        output_dir: p[`${kind}_output`],
        recursive: p[kind].recursive,
      },
      signal,
    );
    log(
      `Remote preflight: ${preflight.processed.length} processed, ${preflight.remaining} remain.`,
    );
    if (!preflight.total)
      throw new Error("No supported files in the remote input directory.");
    if (!preflight.remaining) {
      log("Everything is already processed. No uploads or job started.");
      return null;
    }
  }
  if (kind === "photos" && !health.web_capabilities?.photo_options)
    throw new Error("Update Colab API to connect the advanced photo controls.");
  if (
    kind === "videos" &&
    Number(p.videos.start_pct) >= Number(p.videos.end_pct)
  )
    throw new Error("Start % must be lower than End %.");
  signal.throwIfAborted();
  const sourcePath = await uploadSource(
    api,
    source,
    p.source_face,
    signal,
    progress,
  );
  let batch: string | undefined;
  let submissionAttempted = false;
  try {
    if (files !== null) {
      batch = crypto.randomUUID();
      // Upload sequentially to bound memory and make preparation cancellation prompt.
      for (let i = 0; i < selected.length; i++) {
        signal.throwIfAborted();
        const x = selected[i];
        log(`Uploading ${i + 1}/${selected.length}: ${x.relative}`);
        const form = new FormData();
        form.append("files", x.file, x.file.name);
        form.append("relative_paths", x.relative);
        const r = await api.upload<{ input_dir: string }>(
          `/upload/${kind}?batch_id=${batch}`,
          form,
          signal,
          (l, t) => progress(i + (t ? l / t : 0), selected.length),
        );
        if (!r.input_dir?.endsWith("/" + batch))
          throw new Error("Backend did not return an isolated upload directory.");
        input = r.input_dir;
      }
    }
    signal.throwIfAborted();
    log(
      "Submitting job once. A lost response will not be automatically retried.",
    );
    // Do not abort a submission midway: cancellation is sent once the id is known.
    submissionAttempted = true;
    let job: { job_id: string; status: string };
    try {
      job = await api.request<{ job_id: string; status: string }>(
        `/jobs/${kind}`,
        "POST",
        jobPayload(p, kind, sourcePath, input),
      );
    } catch (e) {
      // The backend answered with a client error (for example a missing source path):
      // no job exists, so this is a definite rejection and the upload can be cleaned up.
      if (isRejection(e)) {
        submissionAttempted = false;
        throw new SubmissionRejected(e);
      }
      throw e;
    }
    if (!job.job_id)
      throw new Error("No job id returned. Check active jobs before retrying.");
    return job;
  } finally {
    // A lost submission response may hide a running job: retain its inputs.
    if (batch && !submissionAttempted && health.web_capabilities?.batch_cleanup) {
      try {
        await api.request(`/upload/${kind}/batches/${batch}`, "DELETE");
        log("Removed the unsubmitted upload batch.");
      } catch {
        log(`Upload cleanup could not be confirmed for batch ${batch}. Retry cleanup after reconnecting.`);
      }
    }
  }
}

/** True for an HTTP 4xx answer: the request reached the backend and was refused. */
export function isRejection(error: unknown): boolean {
  return /^(Error: )?HTTP 4\d\d\b/.test(String(error instanceof Error ? error.message : error));
}

/** A job submission the backend refused; nothing was started. */
export class SubmissionRejected extends Error {
  constructor(cause: unknown) {
    super(cause instanceof Error ? cause.message : String(cause));
    this.name = "SubmissionRejected";
  }
}
