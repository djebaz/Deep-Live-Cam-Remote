export type Meta = Record<string, unknown>;
export interface Frame {
  meta: Meta;
  bytes: Uint8Array;
}
export const PACKET_LIMIT = 4 * 1024 * 1024;
const encoder = new TextEncoder(),
  decoder = new TextDecoder("utf-8", { fatal: true });
export function packetSize(frames: Frame[]) {
  return (
    8 +
    frames.reduce(
      (n, f) =>
        n + 8 + encoder.encode(JSON.stringify(f.meta)).length + f.bytes.length,
      0,
    )
  );
}
export function pack(frames: Frame[]): ArrayBuffer {
  if (!frames.length || frames.length > 256)
    throw new Error("Invalid frame count");
  const length = packetSize(frames);
  if (length > PACKET_LIMIT) throw new Error("Live packet exceeds 4 MiB");
  const buffer = new ArrayBuffer(length),
    view = new DataView(buffer),
    bytes = new Uint8Array(buffer);
  bytes.set(encoder.encode("DLCR"));
  view.setUint16(4, 1);
  view.setUint16(6, frames.length);
  let offset = 8;
  for (const f of frames) {
    const header = encoder.encode(JSON.stringify(f.meta));
    if (header.length > 1000000 || f.bytes.length > 50000000)
      throw new Error("Frame exceeds protocol limits");
    view.setUint32(offset, header.length);
    view.setUint32(offset + 4, f.bytes.length);
    offset += 8;
    bytes.set(header, offset);
    offset += header.length;
    bytes.set(f.bytes, offset);
    offset += f.bytes.length;
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
}
/** Sequence identifies frames. Only relative monotonic capture offsets schedule them. */
export class PreviewQueue {
  queue: Scheduled[] = [];
  dropped = 0;
  private firstCapture?: number;
  private anchor?: number;
  private last = -1;
  private synthetic = 0;
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
    if (seq <= this.last) {
      this.dropped++;
      return;
    }
    this.queue.push({ ...frame, at, seq });
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
      if (f.seq <= this.last) {
        this.dropped++;
        continue;
      }
      if (chosen) this.dropped++;
      chosen = f;
    }
    if (chosen) this.last = chosen.seq;
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
    this.dropped = 0;
  }
}
