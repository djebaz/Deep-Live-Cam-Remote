import { useEffect, useRef, useState } from "react";
import { Api, type Output } from "./api";
import type { Values } from "./settings";
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
  private controllers = new Set<AbortController>();
  private bytes = 0;
  private disposed = false;
  constructor(
    private api: Api,
    private maxBytes = 64 * 1024 * 1024,
  ) {}
  async load(
    item: Output,
    progress?: (l: number, t: number) => void,
  ): Promise<string> {
    const key = item.download_path;
    const found = this.entries.get(key);
    if (found) return found.url;
    if (this.pending.has(key)) return this.pending.get(key)!;
    const controller = new AbortController();
    this.controllers.add(controller);
    const promise = (async () => {
      if (item.size > this.maxBytes)
        throw new Error(
          "Photo exceeds the 64 MiB preview limit; download instead.",
        );
      const url = await this.api.media(key);
      controller.signal.throwIfAborted();
      const response = await fetch(url, {
        signal: controller.signal,
        cache: "no-store",
      });
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
        if (k !== key) {
          URL.revokeObjectURL(v.url);
          this.entries.delete(k);
          this.bytes -= v.size;
        }
      }
      return object;
    })().finally(() => {
      this.controllers.delete(controller);
      this.pending.delete(key);
    });
    this.pending.set(key, promise);
    return promise;
  }
  trim(keep: Set<string>) {
    for (const [key, value] of this.entries)
      if (!keep.has(key)) {
        URL.revokeObjectURL(value.url);
        this.bytes -= value.size;
        this.entries.delete(key);
      }
  }
  dispose() {
    this.disposed = true;
    for (const c of this.controllers) c.abort();
    for (const e of this.entries.values()) URL.revokeObjectURL(e.url);
    this.entries.clear();
    this.pending.clear();
    this.bytes = 0;
  }
}
export function Outputs({
  api,
  options,
  change,
  log,
}: {
  api: Api;
  options: Values;
  change: (k: string, v: string | number | boolean) => void;
  log: (s: string) => void;
}) {
  const [files, setFiles] = useState<Output[]>([]),
    [index, setIndex] = useState(0),
    [media, setMedia] = useState(""),
    [status, setStatus] = useState("Refresh to browse backend outputs."),
    [loaded, setLoaded] = useState(false),
    [size, setSize] = useState({ w: 0, h: 0 }),
    [progress, setProgress] = useState<number | null>(null),
    [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const cache = useRef<PhotoCache | null>(null);
  const kind = String(options.kind),
    current = files[index];
  useEffect(() => {
    cache.current = new PhotoCache(api);
    return () => {
      generation.current++;
      cache.current?.dispose();
    };
  }, [api]);
  useEffect(() => {
    generation.current++;
    setFiles([]);
    setMedia("");
    setLoaded(false);
    setStatus("Refresh to browse backend outputs.");
  }, [api, kind]);
  const next = (delta = 1) => {
    setLoaded(false);
    setIndex((i) => (i + delta + files.length) % Math.max(1, files.length));
  };
  async function refresh() {
    const g = ++generation.current;
    setBusy(true);
    setLoaded(false);
    setMedia("");
    try {
      const r = await api.request<{ files: Output[] }>(`/outputs/${kind}`);
      if (g !== generation.current) return;
      setFiles(r.files);
      setIndex(0);
      setStatus(`${r.files.length} ${kind} from Drive and local output roots.`);
    } catch (e) {
      if (g === generation.current) setStatus(String(e));
      log(String(e));
    } finally {
      if (g === generation.current) setBusy(false);
    }
  }
  useEffect(() => {
    const g = ++generation.current;
    setMedia("");
    setLoaded(false);
    setProgress(null);
    if (!current) return;
    setStatus(`Loading ${current.relative_path}`);
    let cancelled = false;
    const load = async () => {
      try {
        const url =
          kind === "photos"
            ? await cache.current!.load(current, (l, t) => {
                if (!cancelled) setProgress(t ? (l / t) * 100 : null);
              })
            : await api.media(current.download_path);
        if (cancelled || g !== generation.current) return;
        setMedia(url);
        setStatus(`Showing ${current.relative_path} · ${current.source}`);
        setProgress(null);
      } catch (e) {
        if (!cancelled) {
          setStatus(
            `Preview failed: ${String(e)}. Download remains available.`,
          );
          setProgress(null);
          log(String(e));
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [current, kind, api]);
  useEffect(() => {
    if (!loaded || kind !== "photos" || !current) return;
    let cancelled = false;
    const count = options.autoplay ? Number(options.prefetch) : 2;
    const upcoming = Array.from(
      { length: Math.min(count, files.length - 1) },
      (_, i) => files[(index + i + 1) % files.length],
    );
    const keep = new Set([
      current.download_path,
      ...upcoming.map((x) => x.download_path),
    ]);
    cache.current?.trim(keep);
    const prefetch = async () => {
      for (let i = 0; i < upcoming.length && !cancelled; i += 2) {
        await Promise.allSettled(
          upcoming.slice(i, i + 2).map((x) => cache.current!.load(x)),
        );
        if (!cancelled) cache.current?.trim(keep);
      }
    };
    void prefetch();
    return () => {
      cancelled = true;
    };
  }, [loaded, current, index, kind, files, options.autoplay, options.prefetch]);
  useEffect(() => {
    if (!options.autoplay || !loaded || kind !== "photos" || files.length < 2)
      return;
    const t = setTimeout(() => next(), Number(options.seconds) * 1000);
    return () => clearTimeout(t);
  }, [loaded, index, options.autoplay, options.seconds, kind, files.length]);
  async function download(all = false, archive = false) {
    setBusy(true);
    try {
      let path = current?.download_path;
      if (all) path = `/outputs/${kind}/zip`;
      if (archive) {
        const r = await api.request<{ zip_id: string; size_bytes: number }>(
          `/outputs/${kind}/create-zip`,
          "POST",
        );
        path = `/download-archive/${r.zip_id}`;
        setStatus(
          `Archive prepared: ${(r.size_bytes / 1048576).toFixed(1)} MiB. Retained on backend.`,
        );
      }
      if (!path) return;
      const url = await api.media(path);
      const a = document.createElement("a");
      a.href = url;
      a.download = all ? `${kind}_outputs.zip` : current.name;
      a.rel = "noreferrer";
      a.click();
    } catch (e) {
      setStatus(String(e));
      log(String(e));
    } finally {
      setBusy(false);
    }
  }
  const zoom = options.zoom === "fit" ? null : parseFloat(String(options.zoom));
  return (
    <div className="workspace">
      <aside className="controls">
        <fieldset>
          <legend>Output library</legend>
          <label>
            Media type
            <select
              value={kind}
              onChange={(e) => change("kind", e.target.value)}
            >
              <option>photos</option>
              <option>videos</option>
            </select>
          </label>
          <button onClick={refresh} disabled={busy}>
            Refresh outputs
          </button>
          <p className="hint">
            Fixed Drive and local roots. Custom processing paths are not
            indexed.
          </p>
        </fieldset>
        <fieldset>
          <legend>Playback</legend>
          <label className="check">
            <input
              type="checkbox"
              checked={Boolean(options.autoplay)}
              onChange={(e) => change("autoplay", e.target.checked)}
            />
            Auto-play
          </label>
          <label>
            Visible seconds
            <input
              type="number"
              min="0.25"
              max="60"
              step="0.25"
              value={Number(options.seconds)}
              onChange={(e) =>
                change(
                  "seconds",
                  Math.max(0.25, Math.min(60, Number(e.target.value))),
                )
              }
            />
          </label>
          <label>
            Prefetch photos
            <input
              type="number"
              min="1"
              max="50"
              value={Number(options.prefetch)}
              onChange={(e) =>
                change(
                  "prefetch",
                  Math.max(1, Math.min(50, Number(e.target.value))),
                )
              }
            />
          </label>
          <label>
            Photo zoom
            <select
              value={String(options.zoom)}
              onChange={(e) => change("zoom", e.target.value)}
            >
              {["fit", "0.5x", "0.8x", "1x", "1.5x", "2x"].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
        </fieldset>
        <div className="actions">
          <button disabled={!current} onClick={() => next(-1)}>
            Previous
          </button>
          <button disabled={!current} onClick={() => next()}>
            Next
          </button>
        </div>
        <div className="output-list" aria-label="Remote output files">
          {files.map((f, i) => (
            <button
              key={f.download_path}
              aria-pressed={i === index}
              className={i === index ? "selected" : ""}
              onClick={() => {
                setLoaded(false);
                setIndex(i);
              }}
            >
              <strong>{f.relative_path}</strong>
              <small>
                {f.source} · {(f.size / 1048576).toFixed(2)} MiB
              </small>
            </button>
          ))}
        </div>
      </aside>
      <section className="stage">
        <div className="stage-heading">
          <span>OUTPUT PREVIEW</span>
          <span>
            {files.length ? `${index + 1} / ${files.length}` : "No selection"}
          </span>
        </div>
        <div className="media-stage">
          {!media ? (
            <div className="empty">
              <h2>Your processed media</h2>
              <p>{status}</p>
            </div>
          ) : kind === "photos" ? (
            <img
              src={media}
              alt={current?.relative_path}
              style={
                zoom
                  ? {
                      width: size.w * zoom,
                      height: size.h * zoom,
                      maxWidth: "none",
                      maxHeight: "none",
                    }
                  : {}
              }
              onLoad={(e) => {
                setSize({
                  w: e.currentTarget.naturalWidth,
                  h: e.currentTarget.naturalHeight,
                });
                setLoaded(true);
              }}
              onError={() => {
                setLoaded(false);
                setStatus(
                  "Image could not be decoded. Download to open locally.",
                );
              }}
            />
          ) : (
            <video
              src={media}
              controls
              autoPlay={Boolean(options.autoplay)}
              onLoadedData={() => setLoaded(true)}
              onEnded={() => {
                if (options.autoplay) next();
              }}
              onError={() => {
                setLoaded(false);
                setStatus(
                  "This browser cannot play the video format. Download with a compatible player.",
                );
              }}
            />
          )}
        </div>
        <div className="stage-footer">
          <p role="status">{status}</p>
          {progress !== null && <progress max="100" value={progress} />}
          <div className="actions">
            <button disabled={!current || busy} onClick={() => download()}>
              Download current
            </button>
            <button
              disabled={!files.length || busy}
              onClick={() => download(true)}
            >
              Download all ZIP
            </button>
            <button
              disabled={!files.length || busy}
              onClick={() => download(true, true)}
            >
              Create retained archive
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
