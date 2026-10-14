import type { Preferences } from "./settings";
export interface Output {
  name: string;
  relative_path: string;
  source: string;
  size: number;
  download_path: string;
  modified: number;
}
export interface Health {
  ok: boolean;
  api_version: string;
  paths: Record<string, string>;
  local_paths: Record<string, string>;
  web_capabilities?: Record<string, boolean>;
  active_jobs: Job[];
}
export interface Job {
  job_id: string;
  kind: "photos" | "videos";
  status: string;
  logs?: string[];
  error?: string;
}
export class Api {
  constructor(
    public preferences: Preferences,
    public token: string,
  ) {}
  base() {
    const raw = this.preferences.gateway.trim();
    if (!raw) return location.origin;
    const u = new URL(raw);
    if (u.username || u.password || u.search || u.hash || u.pathname !== "/")
      throw new Error(
        "Gateway must be an origin without credentials, query, or path.",
      );
    if (
      u.protocol !== "https:" &&
      !(
        u.protocol === "http:" &&
        ["localhost", "127.0.0.1", "[::1]"].includes(u.hostname) &&
        location.protocol !== "https:"
      )
    )
      throw new Error(
        "Use an HTTPS gateway. HTTP is supported only on localhost from an HTTP page.",
      );
    return u.origin;
  }
  headers() {
    return {
      Authorization: `Bearer ${this.token}`,
      "X-DLCR-Backend": this.preferences.host
        ? `${this.preferences.host}:${this.preferences.port}`
        : "",
    };
  }
  url(path: string) {
    if (!path.startsWith("/") || path.startsWith("//"))
      throw new Error("Invalid API path");
    return this.base() + path;
  }
  async request<T>(
    path: string,
    method = "GET",
    body?: unknown,
    signal?: AbortSignal,
  ): Promise<T> {
    let response: Response;
    try {
      response = await fetch(this.url(path), {
        method,
        headers: {
          ...this.headers(),
          ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: signal || AbortSignal.timeout(30000),
      });
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") throw e;
      throw new Error(
        "Gateway unreachable. Check Tailscale, HTTPS, allowed origin, browser local-network permission, and gateway service.",
      );
    }
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status}: ${text.slice(0, 600)}`);
    }
    const result = await response.json();
    if (result.error) throw new Error(String(result.error));
    return result;
  }
  async socket(path: string) {
    const { ticket } = await this.request<{ ticket: string }>(
      "/gateway/ticket",
      "POST",
      { path },
    );
    const u = new URL(this.url(path));
    u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
    u.searchParams.set("ticket", ticket);
    return new WebSocket(u);
  }
  async media(path: string) {
    const u = new URL(
      this.url(path.split("/").map(encodeURIComponent).join("/")),
    );
    const { ticket } = await this.request<{ ticket: string }>(
      "/gateway/media-ticket",
      "POST",
      { path: u.pathname },
    );
    u.searchParams.set("ticket", ticket);
    return u.toString();
  }
  upload<T>(
    path: string,
    body: FormData,
    signal: AbortSignal,
    progress: (loaded: number, total: number) => void,
  ): Promise<T> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const abort = () => xhr.abort();
      signal.addEventListener("abort", abort, { once: true });
      xhr.open("POST", this.url(path));
      xhr.timeout = 600000;
      Object.entries(this.headers()).forEach(([k, v]) =>
        xhr.setRequestHeader(k, v),
      );
      xhr.upload.onprogress = (e) =>
        progress(e.loaded, e.lengthComputable ? e.total : 0);
      const clean = () => signal.removeEventListener("abort", abort);
      xhr.onload = () => {
        clean();
        try {
          if (xhr.status < 200 || xhr.status >= 300)
            throw new Error(
              `Upload HTTP ${xhr.status}: ${xhr.responseText.slice(0, 500)}`,
            );
          resolve(JSON.parse(xhr.responseText));
        } catch (e) {
          reject(e);
        }
      };
      xhr.onerror = () => {
        clean();
        reject(
          new Error("Upload connection failed. Check gateway / Tailscale."),
        );
      };
      xhr.ontimeout = () => {
        clean();
        reject(new Error("Upload timed out"));
      };
      xhr.onabort = () => {
        clean();
        reject(new DOMException("Upload cancelled", "AbortError"));
      };
      if (signal.aborted) {
        clean();
        reject(new DOMException("Cancelled", "AbortError"));
      } else xhr.send(body);
    });
  }
}
export function sanitizeLog(text: string) {
  return text
    .replace(
      /(Bearer\s+|(?:token|password|secret|ticket|auth_key)[=:]\s*)[^\s",]+/gi,
      "$1[redacted]",
    )
    .replace(/https?:\/\/[^\s/@]+:[^\s/@]+@/g, "https://[redacted]@");
}
export async function normalizeSource(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file, {
    imageOrientation: "from-image",
  });
  try {
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    canvas.getContext("2d")!.drawImage(bitmap, 0, 0);
    return await new Promise((resolve, reject) =>
      canvas.toBlob(
        (b) =>
          b
            ? resolve(b)
            : reject(new Error("Source image could not be normalized")),
        "image/png",
      ),
    );
  } finally {
    bitmap.close();
  }
}
export async function uploadSource(
  api: Api,
  file: File | undefined,
  remote: string,
  signal: AbortSignal,
  progress: (l: number, t: number) => void,
) {
  if (!file) return remote;
  const blob = await normalizeSource(file);
  signal.throwIfAborted();
  const form = new FormData();
  form.append("file", blob, `source_${crypto.randomUUID()}.png`);
  const result = await api.upload<{ path: string }>(
    "/upload/file?kind=source",
    form,
    signal,
    progress,
  );
  if (!result.path) throw new Error("Backend did not return a source path");
  return result.path;
}
