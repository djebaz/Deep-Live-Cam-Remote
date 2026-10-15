import type { Api, Output } from "../api";
export function saveBlob(blob: Blob, name: string) {
  const u = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = u;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(u), 1000);
}
export class PhotoCache {
  private entries = new Map<string, { url: string; size: number }>();
  private pending = new Map<string, Promise<string>>();
  private controllers = new Map<string, AbortController>();
  private wanted = new Set<string>();
  private pinned?: string;
  private active = 0;
  private waiters: (() => void)[] = [];
  private bytes = 0;
  private disposed = false;
  constructor(
    private api: Api,
    private maxBytes = 64 * 1024 * 1024,
    /** Replaces the default "media ticket + full file" request (e.g. server previews). */
    private fetcher?: (item: Output, signal: AbortSignal) => Promise<Response>,
  ) {}
  async load(
    item: Output,
    progress?: (l: number, t: number) => void,
  ): Promise<string> {
    const key = item.download_path;
    if (this.disposed || (this.wanted.size && !this.wanted.has(key)))
      throw new DOMException("Obsolete preview", "AbortError");
    const found = this.entries.get(key);
    if (found) return found.url;
    if (this.pending.has(key)) return this.pending.get(key)!;
    const controller = new AbortController();
    this.controllers.set(key, controller);
    const promise = (async () => {
      if (this.active >= 2)
        await new Promise<void>((resolve, reject) => {
          const wake = () => {
            controller.signal.removeEventListener("abort", abort);
            resolve();
          };
          const abort = () => {
            this.waiters = this.waiters.filter((x) => x !== wake);
            reject(new DOMException("Cancelled", "AbortError"));
          };
          this.waiters.push(wake);
          controller.signal.addEventListener("abort", abort, { once: true });
        });
      if (controller.signal.aborted) {
        this.waiters.shift()?.();
        controller.signal.throwIfAborted();
      }
      this.active++;
      try {
        let response: Response;
        if (this.fetcher) {
          response = await this.fetcher(item, controller.signal);
        } else {
          if (item.size > this.maxBytes)
            throw new Error(
              "Photo exceeds the 64 MiB preview limit; download instead.",
            );
          const url = await this.api.media(key, controller.signal);
          controller.signal.throwIfAborted();
          response = await fetch(url, {
            signal: controller.signal,
            cache: "no-store",
          });
        }
        if (!response.ok) throw new Error(`Preview HTTP ${response.status}`);
        const reader = response.body!.getReader();
        const chunks: Uint8Array[] = [];
        let n = 0;
        while (true) {
          const next = await reader.read();
          if (next.done) break;
          n += next.value.length;
          if (n > this.maxBytes) {
            await reader.cancel();
            throw new Error("Preview too large; download instead.");
          }
          chunks.push(next.value);
          progress?.(n, item.size);
        }
        if (this.disposed) throw new DOMException("Disposed", "AbortError");
        const object = URL.createObjectURL(
          new Blob(chunks as BlobPart[], {
            type: response.headers.get("Content-Type") || "image/jpeg",
          }),
        );
        this.entries.set(key, { url: object, size: n });
        this.bytes += n;
        for (const [k, v] of this.entries) {
          if (this.bytes <= this.maxBytes && this.entries.size <= 52) break;
          if (k !== key && k !== this.pinned) {
            URL.revokeObjectURL(v.url);
            this.entries.delete(k);
            this.bytes -= v.size;
          }
        }
        if (this.bytes > this.maxBytes) {
          URL.revokeObjectURL(object);
          this.entries.delete(key);
          this.bytes -= n;
          throw new Error(
            "Preview cache budget exhausted; reduce prefetch or download this photo.",
          );
        }
        return object;
      } finally {
        this.active--;
        this.waiters.shift()?.();
      }
    })().finally(() => {
      if (this.controllers.get(key) === controller)
        this.controllers.delete(key);
      this.pending.delete(key);
    });
    this.pending.set(key, promise);
    return promise;
  }
  trim(keep: Set<string>) {
    this.wanted = keep;
    this.pinned = keep.values().next().value;
    for (const [key, controller] of this.controllers)
      if (!keep.has(key)) controller.abort();
    for (const [key, value] of this.entries)
      if (!keep.has(key)) {
        URL.revokeObjectURL(value.url);
        this.bytes -= value.size;
        this.entries.delete(key);
      }
  }
  dispose() {
    this.disposed = true;
    for (const c of this.controllers.values()) c.abort();
    for (const e of this.entries.values()) URL.revokeObjectURL(e.url);
    this.entries.clear();
    this.pending.clear();
    this.bytes = 0;
  }
}
