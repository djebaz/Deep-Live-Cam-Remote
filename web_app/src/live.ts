import { Api, uploadSource } from "./api";
import { HOT, type Values } from "./settings";
import {
  pack,
  unpack,
  PACKET_LIMIT,
  FRAME_HEADER_RESERVE,
  PreviewQueue,
  type Frame,
  type Meta,
} from "./protocol";
export interface LiveStats {
  capture_fps: number;
  send_fps: number;
  receive_fps: number;
  display_fps: number;
  in_flight: number;
  queued: number;
  buffer_seconds: number;
  preview_dropped: number;
  capture_dropped: number;
  negotiated: string;
  backend: Meta;
}
export class LiveSession {
  private socket?: WebSocket;
  private stream?: MediaStream;
  private video = document.createElement("video");
  private captureCanvas = document.createElement("canvas");
  private stopped = true;
  private abort = new AbortController();
  private captureTimer?: number;
  private renderTimer?: number;
  private statsTimer?: number;
  private batchTimer?: number;
  private frameCallback?: number;
  private watchdog?: number;
  private encoding = false;
  private decoding = false;
  private batch: Frame[] = [];
  private batchBytes = 8;
  private inFlight = new Map<number, number>();
  private preview = new PreviewQueue();
  private seq = 0;
  private counts = [0, 0, 0, 0];
  private countAt = 0;
  private backend: Meta = {};
  private fallback: Meta = {};
  private lastImage?: ImageBitmap;
  private negotiated = "";
  private captureDropped = 0;
  private perfRows: Record<string, unknown>[] = [];
  private origin = 0;
  private lastCapturedAt = -1;
  private encodeMs = 0;
  private decodeMs = 0;
  private sentBytes = 0;
  private receivedBytes = 0;
  private record = false;
  private recordingCase = "manual";
  private recordingUntil = 0;
  constructor(
    private api: Api,
    private options: Values,
    private canvas: HTMLCanvasElement,
    private log: (s: string) => void,
    private stats: (s: LiveStats) => void,
    private ended: () => void,
  ) {}
  async start(source: File | undefined) {
    this.stopped = false;
    this.origin = performance.now();
    this.countAt = this.origin;
    try {
      if (!window.isSecureContext)
        throw new Error("Camera requires HTTPS or localhost.");
      if (!navigator.mediaDevices?.getUserMedia)
        throw new Error("Camera access is unavailable in this browser.");
      const sourcePath = await uploadSource(
        this.api,
        source,
        this.api.preferences.source_face,
        this.abort.signal,
        () => {},
      );
      if (this.stopped) return;
      const custom = this.options.capture_mode === "custom";
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          ...(this.options.camera
            ? { deviceId: { exact: String(this.options.camera) } }
            : {}),
          frameRate: { ideal: Number(this.options.fps) },
          ...(custom
            ? {
                width: { ideal: Number(this.options.capture_width) },
                height: { ideal: Number(this.options.capture_height) },
              }
            : {}),
        },
      });
      if (this.stopped) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      this.stream = stream;
      this.video.srcObject = stream;
      this.video.muted = true;
      this.video.playsInline = true;
      await this.video.play();
      if (this.stopped) return;
      const actual = stream.getVideoTracks()[0].getSettings();
      this.negotiated = `${actual.width} × ${actual.height} · ${actual.frameRate?.toFixed(1) || "?"} FPS`;
      this.log(`Negotiated camera: ${this.negotiated}`);
      stream.getVideoTracks()[0].onended = () =>
        this.fail("Camera disconnected or permission revoked.");
      const ws = await this.api.socket("/ws/live");
      if (this.stopped) {
        ws.close();
        return;
      }
      this.socket = ws;
      ws.binaryType = "arraybuffer";
      ws.onopen = () =>
        ws.send(
          JSON.stringify({
            ...Object.fromEntries(
              Object.entries(this.options).filter(
                ([k]) =>
                  HOT.has(k) ||
                  [
                    "enhancer",
                    "face_model_pack",
                    "swapper_precision",
                    "cache_source_face",
                  ].includes(k),
              ),
            ),
            source_face: sourcePath,
          }),
        );
      ws.onerror = () =>
        this.log(
          "Live transport error. Check gateway, Tailscale, and backend logs.",
        );
      ws.onclose = () => {
        if (!this.stopped)
          this.fail(
            "Live connection closed. Stop completed; reconnect and restart Live.",
          );
      };
      ws.onmessage = (e) => this.receive(e.data);
      this.watchdog = window.setTimeout(() => {
        if (!this.stopped && !this.renderTimer)
          this.fail(
            "Backend did not become ready within 90 seconds. Check GPU initialization or an active batch.",
          );
      }, 90000);
    } catch (e) {
      if (!this.stopped) this.fail(String(e));
    }
  }
  private ready() {
    if (this.renderTimer || this.stopped) return;
    clearTimeout(this.watchdog);
    this.preview.delay = Number(this.options.preview_buffer_seconds);
    this.preview.setCapacityFor(Number(this.options.fps));
    this.renderTimer = window.setInterval(() => this.render(), 8);
    this.statsTimer = window.setInterval(() => this.report(), 1000);
    if ("requestVideoFrameCallback" in this.video) {
      const next = () => {
        if (this.stopped) return;
        this.frameCallback = this.video.requestVideoFrameCallback(
          (_now, _meta) => {
            this.capture();
            next();
          },
        );
      };
      next();
    } else
      this.captureTimer = window.setInterval(
        () => {
          if (this.video.currentTime !== this.lastCapturedAt) {
            this.lastCapturedAt = this.video.currentTime;
            this.capture();
          }
        },
        1000 / Number(this.options.fps),
      );
  }
  private receive(data: string | ArrayBuffer) {
    if (this.stopped) return;
    try {
      if (typeof data === "string") {
        const m = JSON.parse(data);
        if (m.status === "ready") {
          this.backend = m;
          this.log("Live ready.");
          this.ready();
        } else if (m.status === "live_frame_dropped") {
          const n = Math.max(1, Number(m.dropped) || 1);
          const last = Number(m.frame_seq);
          const candidates = Array.from(this.inFlight.keys()).filter((seq) =>
            Number.isFinite(last) ? seq <= last : true,
          );
          for (const seq of candidates.slice(-n)) this.inFlight.delete(seq);
        } else if (m.type === "live_frame_meta") this.fallback = m;
        else if (m.error) {
          this.log(String(m.error));
          const first = this.inFlight.keys().next().value;
          if (first !== undefined) this.inFlight.delete(first);
          if (!this.renderTimer) this.fail(String(m.error));
        } else {
          if (m.status === "live_perf") this.backend = m;
          this.log(JSON.stringify(m));
        }
        return;
      }
      this.receivedBytes += data.byteLength;
      for (const f of unpack(data, this.fallback)) {
        this.counts[2]++;
        const seq = Number(f.meta.seq);
        if (Number.isFinite(seq) && f.meta.seq !== "")
          this.inFlight.delete(seq);
        else {
          const first = this.inFlight.keys().next().value;
          if (first !== undefined) this.inFlight.delete(first);
        }
        this.preview.enqueue(f, performance.now() / 1000);
      }
      this.fallback = {};
    } catch (e) {
      this.fail(`Invalid Live response: ${String(e)}`);
    }
  }
  private async capture() {
    if (this.stopped || this.socket?.readyState !== WebSocket.OPEN) return;
    this.counts[0]++;
    const seq = this.seq++;
    const limit = Number(this.options.pipeline_frames);
    if (
      this.encoding ||
      this.inFlight.size + this.batch.length >= limit ||
      this.socket.bufferedAmount > PACKET_LIMIT
    ) {
      this.captureDropped++;
      return;
    }
    this.encoding = true;
    const encodeStart = performance.now();
    const captureMono = (performance.now() - this.origin) / 1000;
    const wall = Date.now() / 1000;
    try {
      const scale =
        this.options.capture_scale === "auto"
          ? 1
          : parseFloat(String(this.options.capture_scale)) / 100;
      const w = Math.max(2, Math.round(this.video.videoWidth * scale)),
        h = Math.max(2, Math.round(this.video.videoHeight * scale));
      this.captureCanvas.width = w;
      this.captureCanvas.height = h;
      this.captureCanvas.getContext("2d")!.drawImage(this.video, 0, 0, w, h);
      const codec = String(this.options.frame_codec),
        type = codec === "webp" ? "image/webp" : "image/jpeg";
      const blob = await new Promise<Blob>((resolve, reject) =>
        this.captureCanvas.toBlob(
          (b) => (b ? resolve(b) : reject(new Error("Frame encoding failed"))),
          type,
          Number(this.options.jpeg_quality) / 100,
        ),
      );
      if (this.stopped) return;
      if (blob.type !== type)
        throw new Error(`Browser cannot encode ${codec}. Choose JPEG.`);
      const bytes = new Uint8Array(await blob.arrayBuffer());
      if (this.stopped) return;
      const f: Frame = {
        meta: {
          seq,
          capture_monotonic: captureMono,
          capture_time: wall,
          send_time: Date.now() / 1000,
          codec,
          width: w,
          height: h,
        },
        bytes,
      };
      // The capture metadata has a fixed set of scalar keys. Reserve a
      // conservative header budget while batching; serialize once at flush
      // after setting the actual send_time, then reuse those encoded bytes.
      const size = 8 + bytes.length + FRAME_HEADER_RESERVE;
      if (size + 8 > PACKET_LIMIT)
        throw new Error("Frame exceeds 4 MiB. Reduce Send scale or quality.");
      if (this.batchBytes + size > PACKET_LIMIT) this.flush();
      this.batch.push(f);
      this.batchBytes += size;
      this.encodeMs += performance.now() - encodeStart;
      if (
        this.batch.length >= Number(this.options.transport_batch_size) ||
        this.inFlight.size + this.batch.length >= limit
      )
        this.flush();
      else if (!this.batchTimer)
        this.batchTimer = window.setTimeout(() => {
          this.batchTimer = undefined;
          this.flush();
        }, 50);
    } catch (e) {
      if (!this.stopped) this.fail(String(e));
    } finally {
      this.encoding = false;
    }
  }
  private flush() {
    clearTimeout(this.batchTimer);
    this.batchTimer = undefined;
    if (!this.batch.length) return;
    if (this.stopped || this.socket?.readyState !== WebSocket.OPEN) {
      this.batch = [];
      this.batchBytes = 8;
      return;
    }
    if (this.socket.bufferedAmount > PACKET_LIMIT) {
      this.captureDropped += this.batch.length;
      this.batch = [];
      this.batchBytes = 8;
      return;
    }
    this.batch.forEach((f) => (f.meta.send_time = Date.now() / 1000));
    let packet: ArrayBuffer;
    try {
      packet = pack(this.batch);
      this.socket.send(packet);
    } catch (error) {
      this.fail(String(error));
      return;
    }
    this.sentBytes += packet.byteLength;
    const now = performance.now();
    for (const f of this.batch) this.inFlight.set(Number(f.meta.seq), now);
    this.counts[1] += this.batch.length;
    this.batch = [];
    this.batchBytes = 8;
  }
  private async render() {
    if (this.stopped || this.decoding) return;
    const f = this.preview.take(performance.now() / 1000);
    if (!f) return;
    this.decoding = true;
    const decodeStart = performance.now();
    try {
      const image = await createImageBitmap(new Blob([f.bytes as BlobPart]));
      if (this.stopped) {
        image.close();
        return;
      }
      this.lastImage?.close();
      this.lastImage = image;
      this.paint();
      this.counts[3]++;
      this.decodeMs += performance.now() - decodeStart;
    } catch (e) {
      this.log(`Preview decode failed: ${String(e)}`);
    } finally {
      this.decoding = false;
    }
  }
  private paint() {
    if (!this.lastImage) return;
    const i = this.lastImage;
    this.canvas.width = i.width;
    this.canvas.height = i.height;
    this.canvas.getContext("2d")!.drawImage(i, 0, 0);
    const scale =
      this.options.preview_scale === "fit"
        ? 1
        : parseFloat(String(this.options.preview_scale));
    this.canvas.style.width =
      this.options.preview_scale === "fit" ? "100%" : `${i.width * scale}px`;
    this.canvas.style.maxWidth = "100%";
    this.canvas.style.maxHeight = "100%";
  }
  update(options: Values) {
    const patch: Values = {};
    for (const k of HOT) {
      if (options[k] !== this.options[k]) patch[k] = options[k];
    }
    this.preview.setDelay(Number(options.preview_buffer_seconds));
    this.preview.setCapacityFor(Number(options.fps));
    this.options = { ...options };
    this.paint();
    if (Object.keys(patch).length && this.socket?.readyState === WebSocket.OPEN)
      this.socket.send(
        JSON.stringify({ type: "live_config_update", config: patch }),
      );
  }
  private report() {
    const now = performance.now(),
      dt = (now - this.countAt) / 1000;
    const s: LiveStats = {
      capture_fps: this.counts[0] / dt,
      send_fps: this.counts[1] / dt,
      receive_fps: this.counts[2] / dt,
      display_fps: this.counts[3] / dt,
      in_flight: this.inFlight.size,
      queued: this.preview.queue.length,
      buffer_seconds: this.preview.queue.length
        ? Math.max(0, this.preview.queue.at(-1)!.at - now / 1000)
        : 0,
      preview_dropped: this.preview.dropped,
      capture_dropped: this.captureDropped,
      negotiated: this.negotiated,
      backend: this.backend,
    };
    this.stats(s);
    if (this.record) {
      if (now > this.recordingUntil) {
        this.record = false;
        this.log("Performance sample completed.");
      } else {
        this.perfRows.push({
          case: this.recordingCase,
          elapsed_monotonic: (now - this.origin) / 1000,
          wall_time: new Date().toISOString(),
          ...s,
          send_kib: this.sentBytes / 1024,
          receive_kib: this.receivedBytes / 1024,
          encode_ms: this.encodeMs / Math.max(1, this.counts[1]),
          decode_ms: this.decodeMs / Math.max(1, this.counts[3]),
          ...Object.fromEntries(
            Object.entries(this.backend).map(([k, v]) => ["server_" + k, v]),
          ),
          backend: JSON.stringify(s.backend),
        });
        if (this.perfRows.length > 3600) this.perfRows.shift();
      }
    }
    this.counts = [0, 0, 0, 0];
    this.countAt = now;
    this.encodeMs = 0;
    this.decodeMs = 0;
    this.sentBytes = 0;
    this.receivedBytes = 0;
    const oldest = this.inFlight.values().next().value;
    if (oldest !== undefined && now - oldest > 15000) {
      this.fail(
        "No Live frame acknowledgement for 15 seconds. Session stopped to bound latency. Restart after checking the connection.",
      );
    }
  }
  recordPerformance(name = "manual", seconds = 12) {
    this.record = true;
    this.recordingCase = name;
    this.recordingUntil = performance.now() + seconds * 1000;
    this.log(`Recording performance: ${name}, ${seconds}s`);
  }
  exportCSV() {
    const cols = Array.from(
      new Set(this.perfRows.flatMap((r) => Object.keys(r))),
    );
    const quote = (v: unknown) => `"${String(v ?? "").replaceAll('"', '""')}"`;
    return new Blob(
      [
        cols.join(",") +
          "\n" +
          this.perfRows
            .map((r) => cols.map((c) => quote(r[c])).join(","))
            .join("\n"),
      ],
      { type: "text/csv" },
    );
  }
  private fail(message: string) {
    this.log(message);
    this.stop();
    this.ended();
  }
  stop() {
    if (this.stopped) return;
    this.stopped = true;
    this.abort.abort();
    [this.captureTimer, this.renderTimer, this.statsTimer].forEach((t) =>
      clearInterval(t),
    );
    [this.batchTimer, this.watchdog].forEach((t) => clearTimeout(t));
    if (this.frameCallback !== undefined)
      this.video.cancelVideoFrameCallback?.(this.frameCallback);
    this.socket?.close();
    if (this.socket) {
      this.socket.onmessage = null;
      this.socket.onclose = null;
      this.socket.onerror = null;
      this.socket.onopen = null;
    }
    this.stream?.getTracks().forEach((t) => {
      t.onended = null;
      t.stop();
    });
    this.video.pause();
    this.video.srcObject = null;
    this.preview.clear();
    this.batch = [];
    this.inFlight.clear();
    this.lastImage?.close();
    this.lastImage = undefined;
    this.record = false;
  }
}
