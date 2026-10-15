import type { JobProgress } from "./api";

export function formatEta(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}

/** One status line plus bar value (0-100, or null when unknown) for the running batch. */
export const STALL_SECONDS = 20;

export function describeProgress(
  p: JobProgress | null | undefined,
  serverTime?: number,
): {
  text: string;
  percent: number | null;
} | null {
  if (!p || !p.items) return null;
  const parts = [`Item ${p.item} / ${p.items}`];
  if (p.name) parts.push(p.name.split("/").at(-1)!);
  if (p.state === "processing") {
    if (p.file_percent != null) parts.push(`${Math.round(p.file_percent)}%`);
    else if (p.frames) parts.push(`${p.frames} frames`);
    if (p.fps && p.fps > 0) parts.push(`${p.fps.toFixed(1)} fps`);
    if (p.eta_seconds != null) parts.push(`~${formatEta(p.eta_seconds)} left`);
  } else if (p.state === "skipped") parts.push("skipped");
  else if (p.state === "failed") parts.push("failed");
  // Both stamps come from the server's clock, so browser clock skew does not matter.
  if (p.state === "processing" && serverTime != null && p.updated_at != null) {
    const quiet = serverTime - p.updated_at;
    if (quiet >= STALL_SECONDS) parts.push(`⚠ no progress for ${formatEta(quiet)}`);
  }
  return { text: parts.join(" · "), percent: p.overall_percent ?? null };
}
