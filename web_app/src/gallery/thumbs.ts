import type { Output } from "../api";
import { outputId } from "./model";

export interface Thumb {
  url: string;
  /** Natural size of the original image. */
  width: number;
  height: number;
  duration?: number;
  bytes: number;
}
/** The backend (or an older gateway/Colab in between) cannot make thumbnails. */
export class ThumbUnsupported extends Error {
  constructor() {
    super("Server thumbnails are not available.");
    this.name = "ThumbUnsupported";
  }
}
export type FetchBlob = (item: Output, signal: AbortSignal) => Promise<Blob>;
export type Decoder = (
  blob: Blob,
  maxSide: number,
) => Promise<{ blob: Blob; width: number; height: number; duration?: number }>;
export interface ThumbOptions {
  maxSide?: number;
  /** A number, or a function so it can adapt (server thumbnails are tiny; full files are not). */
  concurrency?: number | (() => number);
  maxEntries?: number;
  maxBytes?: number;
  /** Originals above this size are not fetched just for a thumbnail. */
  maxSourceBytes?: number;
}
export interface Lease {
  promise: Promise<Thumb>;
  release: () => void;
}

interface Job {
  item: Output;
  holders: number;
  controller: AbortController;
  promise: Promise<Thumb>;
  resolve: (t: Thumb) => void;
  reject: (e: unknown) => void;
  started: boolean;
}

const abortError = () => new DOMException("Thumbnail cancelled", "AbortError");

/**
 * Browser-side thumbnails built from the full file (the backend has no
 * thumbnail endpoint): bounded concurrency, newest-request-first queue,
 * cancellation when a tile leaves the screen, and a byte/entry-bounded LRU
 * that never evicts a thumbnail a mounted tile still holds.
 */
export class ThumbnailCache {
  private entries = new Map<string, Thumb>();
  private jobs = new Map<string, Job>();
  private held = new Map<string, number>();
  private queue: Job[] = [];
  private active = 0;
  private bytes = 0;
  private disposed = false;
  private o: Required<ThumbOptions>;
  private limit() {
    const c = this.o.concurrency;
    return typeof c === "function" ? c() : c;
  }

  constructor(
    private fetchBlob: FetchBlob,
    private decode: Decoder,
    options: ThumbOptions = {},
  ) {
    this.o = {
      maxSide: 640,
      concurrency: 3,
      maxEntries: 400,
      maxBytes: 48 * 1024 * 1024,
      maxSourceBytes: 40 * 1024 * 1024,
      ...options,
    };
  }

  peek(id: string): Thumb | undefined {
    return this.entries.get(id);
  }

  /** Ask for a thumbnail; call `release` when the tile no longer needs it. */
  acquire(item: Output): Lease {
    const id = outputId(item);
    this.held.set(id, (this.held.get(id) ?? 0) + 1);
    let released = false;
    const release = () => {
      if (released) return;
      released = true;
      const n = (this.held.get(id) ?? 1) - 1;
      if (n > 0) this.held.set(id, n);
      else this.held.delete(id);
      this.dropJob(id);
      this.evict();
    };
    const hit = this.entries.get(id);
    if (hit) {
      this.entries.delete(id);
      this.entries.set(id, hit);
      return { promise: Promise.resolve(hit), release };
    }
    if (this.disposed) {
      return { promise: Promise.reject(abortError()), release };
    }
    let job = this.jobs.get(id);
    if (!job) {
      let resolve!: (t: Thumb) => void;
      let reject!: (e: unknown) => void;
      const promise = new Promise<Thumb>((res, rej) => {
        resolve = res;
        reject = rej;
      });
      promise.catch(() => undefined);
      job = {
        item,
        holders: 0,
        controller: new AbortController(),
        promise,
        resolve,
        reject,
        started: false,
      };
      this.jobs.set(id, job);
      this.queue.push(job);
    }
    job.holders++;
    queueMicrotask(() => this.pump());
    return { promise: job.promise, release };
  }

  private dropJob(id: string) {
    const job = this.jobs.get(id);
    if (!job) return;
    job.holders--;
    if (job.holders > 0) return;
    this.jobs.delete(id);
    this.queue = this.queue.filter((j) => j !== job);
    job.controller.abort();
    job.reject(abortError());
  }

  private pump() {
    while (!this.disposed && this.active < this.limit()) {
      const job = this.queue.pop(); // newest request first
      if (!job) return;
      this.active++;
      job.started = true;
      void this.run(job).finally(() => {
        this.active--;
        this.pump();
      });
    }
  }

  private async run(job: Job) {
    const id = outputId(job.item);
    try {
      if (job.item.size > this.o.maxSourceBytes)
        throw new Error("Too large to thumbnail; open it instead.");
      const blob = await this.fetchBlob(job.item, job.controller.signal);
      job.controller.signal.throwIfAborted();
      const out = await this.decode(blob, this.o.maxSide);
      job.controller.signal.throwIfAborted();
      if (this.disposed) throw abortError();
      const thumb: Thumb = {
        url: URL.createObjectURL(out.blob),
        width: out.width,
        height: out.height,
        duration: out.duration,
        bytes: out.blob.size,
      };
      this.entries.set(id, thumb);
      this.bytes += thumb.bytes;
      this.jobs.delete(id);
      job.resolve(thumb);
      this.evict();
    } catch (e) {
      this.jobs.delete(id);
      job.reject(e);
    }
  }

  private evict() {
    for (const [id, thumb] of this.entries) {
      if (
        this.entries.size <= this.o.maxEntries &&
        this.bytes <= this.o.maxBytes
      )
        break;
      if (this.held.has(id)) continue;
      URL.revokeObjectURL(thumb.url);
      this.entries.delete(id);
      this.bytes -= thumb.bytes;
    }
  }

  dispose() {
    this.disposed = true;
    for (const job of this.jobs.values()) {
      job.controller.abort();
      job.reject(abortError());
    }
    this.jobs.clear();
    this.queue = [];
    for (const t of this.entries.values()) URL.revokeObjectURL(t.url);
    this.entries.clear();
    this.held.clear();
    this.bytes = 0;
  }

  get size() {
    return this.entries.size;
  }
}

/** Real decoder: bitmap -> downscaled JPEG (universal browser support). */
export const browserDecode: Decoder = async (blob, maxSide) => {
  const bitmap = await createImageBitmap(blob);
  try {
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const w = Math.max(1, Math.round(bitmap.width * scale));
    const h = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas is not available.");
    ctx.fillStyle = "#151515";
    ctx.fillRect(0, 0, w, h);
    ctx.drawImage(bitmap, 0, 0, w, h);
    const out = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.82),
    );
    if (!out) throw new Error("Could not encode the thumbnail.");
    return { blob: out, width: bitmap.width, height: bitmap.height };
  } finally {
    bitmap.close();
  }
};
