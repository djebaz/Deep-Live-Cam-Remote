import type { Api, Output } from "../api";
import { ThumbUnsupported } from "./thumbs";

export interface SourceMeta {
  width: number;
  height: number;
  duration?: number;
}
export type ThumbMode = "unknown" | "yes" | "no";

const num = (v: string | null) => (v !== null && v !== "" && Number.isFinite(Number(v)) ? Number(v) : undefined);

/**
 * Client for the backend's cached thumbnail/preview route. It works out whether the
 * backend supports it from the first answer, so an older Colab API or gateway just
 * falls back to the previous behaviour. Requests use the bearer token directly (one
 * round trip, no media ticket) and the responses are cacheable by the browser.
 */
export class ServerThumbs {
  private _mode: ThumbMode = "unknown";
  /** Called once when the backend is first found to support (or lack) thumbnails. */
  onMode?: (mode: "yes" | "no") => void;
  get mode(): ThumbMode {
    return this._mode;
  }
  set mode(m: ThumbMode) {
    if (m === this._mode) return;
    const first = this._mode === "unknown";
    this._mode = m;
    if (first && m !== "unknown") this.onMode?.(m);
  }
  /** Source size/duration of every file a thumbnail was fetched for. */
  readonly dims = new Map<string, SourceMeta>();
  readonly blobMeta = new WeakMap<Blob, SourceMeta>();
  constructor(private api: Api) {}

  async fetch(item: Output, size: number, signal: AbortSignal): Promise<Response> {
    if (this.mode === "no") throw new ThumbUnsupported();
    const r = await fetch(this.api.thumbUrl(item, size), {
      headers: this.api.headers(),
      signal,
    });
    if (r.ok && (r.headers.get("content-type") || "").startsWith("image/")) {
      this.mode = "yes";
      const width = num(r.headers.get("x-source-width"));
      const height = num(r.headers.get("x-source-height"));
      if (width && height)
        this.dims.set(item.download_path, {
          width,
          height,
          duration: num(r.headers.get("x-source-duration")),
        });
      return r;
    }
    const body = await r.text().catch(() => "");
    // An old Colab API answers an unknown route with {"detail":"Not Found"}; an old
    // gateway falls back to the app page (HTML). Neither says anything about this file.
    if (r.ok || (r.status === 404 && /"detail"\s*:\s*"Not Found"/.test(body))) {
      this.mode = "no";
      throw new ThumbUnsupported();
    }
    let detail = body.slice(0, 200);
    try {
      detail = JSON.parse(body).detail ?? detail;
    } catch {
      /* keep the raw text */
    }
    throw new Error(`Thumbnail HTTP ${r.status}: ${detail}`);
  }

  async blob(item: Output, size: number, signal: AbortSignal): Promise<Blob> {
    const r = await this.fetch(item, size, signal);
    const blob = await r.blob();
    const meta = this.dims.get(item.download_path);
    if (meta) this.blobMeta.set(blob, meta);
    return blob;
  }
}
