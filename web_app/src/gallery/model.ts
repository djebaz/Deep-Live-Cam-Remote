import type { Output } from "../api";

export type View = "grid" | "list" | "detail";
export type SortKey =
  | "newest"
  | "oldest"
  | "name"
  | "name_desc"
  | "largest"
  | "smallest";
export type DateRange = "all" | "today" | "week" | "month";
export type SourceFilter = "all" | "drive" | "local";
export interface Query {
  text: string;
  source: SourceFilter;
  range: DateRange;
  sort: SortKey;
}

export const VIEWS: View[] = ["grid", "list", "detail"];
export const SORT_LABELS: Record<SortKey, string> = {
  newest: "Newest first",
  oldest: "Oldest first",
  name: "Name A–Z",
  name_desc: "Name Z–A",
  largest: "Largest first",
  smallest: "Smallest first",
};
export const RANGE_LABELS: Record<DateRange, string> = {
  all: "All time",
  today: "Today",
  week: "Last 7 days",
  month: "Last 30 days",
};
export const SOURCE_LABELS: Record<SourceFilter, string> = {
  all: "All sources",
  drive: "Google Drive",
  local: "Colab disk",
};
export const THUMB_MIN = 25;
export const THUMB_MAX = 250;
/** 100% is the baseline tile edge; the slider scales presentation only. */
export const THUMB_BASE_PX = 160;

export const outputId = (o: Output) => o.download_path;
export const clamp = (v: number, lo: number, hi: number) =>
  Math.min(hi, Math.max(lo, v));

export function sanitizeView(v: unknown): View {
  return VIEWS.includes(v as View) ? (v as View) : "grid";
}
export function sanitizeSort(v: unknown): SortKey {
  return typeof v === "string" && v in SORT_LABELS ? (v as SortKey) : "newest";
}
export function thumbPx(percent: number): number {
  const p = Number.isFinite(percent) ? percent : 100;
  return Math.round((clamp(p, THUMB_MIN, THUMB_MAX) / 100) * THUMB_BASE_PX);
}

export function formatSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "Unknown";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`;
  return `${(bytes / 1073741824).toFixed(2)} GB`;
}
export function formatDate(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "Not recorded";
  return new Date(seconds * 1000).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = String(total % 60).padStart(2, "0");
  return m >= 60
    ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}:${s}`
    : `${m}:${s}`;
}
export function folderOf(relativePath: string): string {
  const i = relativePath.lastIndexOf("/");
  return i < 0 ? "" : relativePath.slice(0, i);
}
export function sourceLabel(source: string): string {
  return source === "drive"
    ? "Google Drive"
    : source === "local"
      ? "Colab disk"
      : source;
}

/** Seconds-since-epoch lower bound for a date range (0 = no bound). */
export function dateCutoff(range: DateRange, nowSeconds: number): number {
  if (range === "today") {
    const d = new Date(nowSeconds * 1000);
    d.setHours(0, 0, 0, 0);
    return d.getTime() / 1000;
  }
  if (range === "week") return nowSeconds - 7 * 86400;
  if (range === "month") return nowSeconds - 30 * 86400;
  return 0;
}

const natural = (a: string, b: string) =>
  a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
/** By file name (what the grid shows), then folder as the tie-break. */
const byName = (a: Output, b: Output) =>
  natural(a.name, b.name) || natural(a.relative_path, b.relative_path);

export function filterAndSort(
  files: readonly Output[],
  q: Query,
  nowSeconds = Date.now() / 1000,
): Output[] {
  const tokens = q.text.toLowerCase().split(/\s+/).filter(Boolean);
  const cutoff = dateCutoff(q.range, nowSeconds);
  const out = files.filter((f) => {
    if (q.source !== "all" && f.source !== q.source) return false;
    if (cutoff && f.modified < cutoff) return false;
    if (!tokens.length) return true;
    const hay = `${f.relative_path} ${sourceLabel(f.source)}`.toLowerCase();
    return tokens.every((t) => hay.includes(t));
  });
  const sorters: Record<SortKey, (a: Output, b: Output) => number> = {
    newest: (a, b) => b.modified - a.modified || byName(a, b),
    oldest: (a, b) => a.modified - b.modified || byName(a, b),
    name: byName,
    name_desc: (a, b) => byName(b, a),
    largest: (a, b) => b.size - a.size || byName(a, b),
    smallest: (a, b) => a.size - b.size || byName(a, b),
  };
  return out.sort(sorters[q.sort]);
}

const same = (a: Output, b: Output) =>
  a.download_path === b.download_path &&
  a.size === b.size &&
  a.modified === b.modified &&
  a.source === b.source;

/**
 * Reconcile a refreshed listing with the previous one by stable identity.
 * Unchanged entries keep their object identity (so memoised tiles do not
 * re-render) and an identical listing returns the previous array itself.
 */
export function reconcile(
  prev: readonly Output[],
  next: readonly Output[],
): Output[] {
  const old = new Map(prev.map((o) => [outputId(o), o]));
  let identical = prev.length === next.length;
  const merged = next.map((o, i) => {
    const before = old.get(outputId(o));
    const kept = before && same(before, o) ? before : o;
    if (identical && prev[i] !== kept) identical = false;
    return kept;
  });
  return identical ? (prev as Output[]) : merged;
}

export function indexOfId(list: readonly Output[], id: string | null): number {
  return id === null ? -1 : list.findIndex((o) => outputId(o) === id);
}
export function stepIndex(i: number, delta: number, length: number): number {
  return length ? (((i + delta) % length) + length) % length : 0;
}

export type Selection = ReadonlySet<string>;
export function toggleSelection(sel: Selection, id: string): Set<string> {
  const next = new Set(sel);
  if (!next.delete(id)) next.add(id);
  return next;
}
export function selectAll(list: readonly Output[]): Set<string> {
  return new Set(list.map(outputId));
}
export function allSelected(list: readonly Output[], sel: Selection): boolean {
  return list.length > 0 && list.every((o) => sel.has(outputId(o)));
}
/** Keep only ids that still exist (e.g. after a refresh). */
export function pruneSelection(
  sel: Selection,
  files: readonly Output[],
): Selection {
  if (!sel.size) return sel;
  const live = new Set(files.map(outputId));
  const kept = [...sel].filter((id) => live.has(id));
  return kept.length === sel.size ? sel : new Set(kept);
}
export function selectionStats(files: readonly Output[], sel: Selection) {
  let count = 0;
  let bytes = 0;
  for (const f of files)
    if (sel.has(outputId(f))) {
      count++;
      bytes += f.size;
    }
  return { count, bytes };
}

// ---- Activity-log messages (pure, so they can be tested)
const noun = (kind: string, n: number) =>
  n === 1 ? kind.replace(/s$/, "") : kind;
const nameList = (files: readonly Output[], max = 3) => {
  const names = files.slice(0, max).map((f) => f.relative_path);
  return files.length > max
    ? `${names.join(", ")} and ${files.length - max} more`
    : names.join(", ");
};

/** Message for the first listing after the tab opens (or the kind changes). */
export function describeLoad(kind: string, files: readonly Output[]): string {
  if (!files.length)
    return `No ${kind} found in the Drive and Colab output folders.`;
  const drive = files.filter((f) => f.source === "drive").length;
  const local = files.filter((f) => f.source === "local").length;
  const bytes = files.reduce((n, f) => n + f.size, 0);
  const parts = [
    drive ? `${drive} on Google Drive` : "",
    local ? `${local} on Colab disk` : "",
  ].filter(Boolean);
  return `Loaded ${files.length} ${noun(kind, files.length)} (${parts.join(", ")}, ${formatSize(bytes)} in total).`;
}

/** Message for what changed between two listings, or null when nothing did. */
export function describeChange(
  kind: string,
  prev: readonly Output[],
  next: readonly Output[],
): string | null {
  const before = new Set(prev.map(outputId));
  const after = new Set(next.map(outputId));
  const added = next.filter((f) => !before.has(outputId(f)));
  const removed = prev.filter((f) => !after.has(outputId(f)));
  const parts: string[] = [];
  if (added.length)
    parts.push(
      `${added.length} new ${noun(kind, added.length)}: ${nameList(added)}`,
    );
  if (removed.length)
    parts.push(
      `${removed.length} ${noun(kind, removed.length)} no longer on the backend: ${nameList(removed)}`,
    );
  return parts.length ? `${parts.join("; ")}.` : null;
}
