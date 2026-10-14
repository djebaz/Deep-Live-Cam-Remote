export type Meta = Record<string, unknown>;
export interface Frame {
  meta: Meta;
  bytes: Uint8Array;
}
export const PACKET_LIMIT = 4 * 1024 * 1024;
/** Batching budget for one live frame's JSON header. The capture meta has seven
 * scalar keys (~200 bytes worst case); tests assert it stays well under this. */
export const FRAME_HEADER_RESERVE = 1024;
/** A capture clock moving back by more than this is a new epoch, not jitter. */
const EPOCH_RESET_SECONDS = 1;
const encoder = new TextEncoder(),
  decoder = new TextDecoder("utf-8", { fatal: true });
export interface EncodedFrame { header: Uint8Array; bytes: Uint8Array; }
export function encodeFrames(frames: Frame[]): EncodedFrame[] {
  return frames.map(frame => ({header: encoder.encode(JSON.stringify(frame.meta)), bytes: frame.bytes}));
}
export function packetSize(frames: EncodedFrame[]) {
  return 8 + frames.reduce((total, frame) => total + 8 + frame.header.length + frame.bytes.length, 0);
}
export function pack(frames: Frame[]): ArrayBuffer {
  if (!frames.length || frames.length > 256) throw new Error("Invalid frame count");
  const encoded = encodeFrames(frames);
  const length = packetSize(encoded);
  if (length > PACKET_LIMIT) throw new Error("Live packet exceeds 4 MiB");
  const buffer = new ArrayBuffer(length), view = new DataView(buffer), bytes = new Uint8Array(buffer);
  bytes.set([68, 76, 67, 82]);view.setUint16(4, 1);view.setUint16(6, frames.length);
  let offset = 8;
  for (const frame of encoded) {
    if (frame.header.length > 1000000 || frame.bytes.length > 50000000) throw new Error("Frame exceeds protocol limits");
    view.setUint32(offset, frame.header.length);view.setUint32(offset + 4, frame.bytes.length);offset += 8;
    bytes.set(frame.header, offset);offset += frame.header.length;
    bytes.set(frame.bytes, offset);offset += frame.bytes.length;
  }
  return buffer;
}
export function unpack(buffer: ArrayBuffer, fallback: Meta = {}): Frame[] {
  const bytes = new Uint8Array(buffer);
  if (
    bytes.length < 4 ||
    bytes[0] !== 68 ||
    bytes[1] !== 76 ||
    bytes[2] !== 67 ||
    bytes[3] !== 82
  )
    return [{ meta: fallback, bytes }];
  const v = new DataView(buffer);
  if (bytes.length < 8 || v.getUint16(4) !== 1)
    throw new Error("Invalid live packet version/header");
  const count = v.getUint16(6);
  if (count < 1 || count > 256) throw new Error("Invalid frame count");
  let offset = 8;
  const result: Frame[] = [];
  for (let i = 0; i < count; i++) {
    if (offset + 8 > bytes.length) throw new Error("Truncated frame header");
    const h = v.getUint32(offset),
      n = v.getUint32(offset + 4);
    offset += 8;
    if (h > 1000000 || n > 50000000 || offset + h + n > bytes.length)
      throw new Error("Invalid frame lengths");
    const meta = h
      ? JSON.parse(decoder.decode(bytes.subarray(offset, offset + h)))
      : {};
    if (!meta || typeof meta !== "object" || Array.isArray(meta))
      throw new Error("Invalid frame metadata");
    offset += h;
    result.push({ meta, bytes: bytes.slice(offset, offset + n) });
    offset += n;
  }
  if (offset !== bytes.length) throw new Error("Trailing packet bytes");
  return result;
}
interface Scheduled extends Frame {
  at: number;
  seq: number;
  order: number;
}
/** Source sequences are diagnostics; local arrival order and monotonic offsets govern playback. */
export class PreviewQueue {
  queue: Scheduled[] = [];
  dropped = 0;
  private firstCapture?: number;
  private anchor?: number;
  private last = -1;
  private synthetic = 0;
  private order = 0;
  private previousCapture?: number;
  private lastSourceSeq?: number;
  bytes = 0;
  constructor(
    public delay = 1,
    public capacity = 256,
    public maxBytes = 32 * 1024 * 1024,
  ) {}
  enqueue(frame: Frame, now: number) {
    const raw = frame.meta.capture_monotonic;
    const capture =
      typeof raw === "number" && Number.isFinite(raw) && raw >= 0
        ? raw
        : undefined;
    // A new capture epoch must not inherit deadlines from a previous counter.
    if(capture !== undefined && this.previousCapture !== undefined && capture < this.previousCapture - EPOCH_RESET_SECONDS) {
      this.dropped += this.queue.length;this.queue = [];this.bytes = 0;this.anchor = undefined;
    }
    if(capture !== undefined)this.previousCapture = capture;
    const sourceSeq = Number(frame.meta.seq);
    const hasSeq = frame.meta.seq !== "" && frame.meta.seq !== undefined && Number.isFinite(sourceSeq);
    // Only an immediate resend of the same source sequence is a duplicate; any
    // other sequence change (including a restarted counter) is accepted.
    if (hasSeq && sourceSeq === this.lastSourceSeq) {
      this.dropped++;
      return;
    }
    this.lastSourceSeq = hasSeq ? sourceSeq : undefined;
    if (this.anchor === undefined) {
      this.anchor = now + this.delay;
      this.firstCapture = capture;
    }
    const at =
      capture !== undefined && this.firstCapture !== undefined
        ? this.anchor + capture - this.firstCapture
        : now + this.delay;
    const rawSeq = Number(frame.meta.seq);
    const seq =
      frame.meta.seq !== "" &&
      frame.meta.seq !== undefined &&
      Number.isFinite(rawSeq)
        ? rawSeq
        : this.synthetic++;
    this.queue.push({ ...frame, at, seq, order: this.order++ });
    this.bytes += frame.bytes.length;
    while (this.queue.length > this.capacity || this.bytes > this.maxBytes) {
      this.bytes -= this.queue.shift()!.bytes.length;
      this.dropped++;
    }
  }
  take(now: number): Scheduled | undefined {
    let chosen: Scheduled | undefined;
    while (this.queue.length && this.queue[0].at <= now) {
      const f = this.queue.shift()!;
      this.bytes -= f.bytes.length;
      if (f.order <= this.last) {
        this.dropped++;
        continue;
      }
      if (chosen) this.dropped++;
      chosen = f;
    }
    if (chosen) this.last = chosen.order;
    return chosen;
  }
  setDelay(delay: number) {
    const delta = delay - this.delay;
    this.delay = delay;
    if (this.anchor !== undefined) this.anchor += delta;
    this.queue.forEach((f) => (f.at += delta));
  }
  clear() {
    this.queue = [];
    this.bytes = 0;
    this.anchor = undefined;
    this.firstCapture = undefined;
    this.last = -1;
    this.synthetic = 0;
    this.order = 0;
    this.previousCapture = undefined;
    this.lastSourceSeq = undefined;
    this.dropped = 0;
  }
}
