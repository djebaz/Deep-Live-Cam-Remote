import type { Output } from "../api";

/** Minimal "stored" (no compression) ZIP writer. Images and videos are already
 * compressed, so storing keeps it fast and tiny. Limits: < 65,535 entries and
 * < 4 GiB total (no ZIP64), enforced by the caller via MAX_ZIP_BYTES. */
export const MAX_ZIP_BYTES = 512 * 1024 * 1024;
export const MAX_ZIP_ENTRIES = 5000;

export interface ZipEntry {
  name: string;
  data: Uint8Array;
  /** Seconds since epoch, used for the DOS timestamp. */
  modified?: number;
}

let table: Uint32Array | undefined;
export function crc32(data: Uint8Array): number {
  if (!table) {
    table = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c >>> 0;
    }
  }
  let crc = 0xffffffff;
  for (let i = 0; i < data.length; i++)
    crc = table[(crc ^ data[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function dosDateTime(seconds?: number): { time: number; date: number } {
  const d = new Date((seconds && seconds > 0 ? seconds : Date.now() / 1000) * 1000);
  const year = Math.max(1980, d.getFullYear());
  return {
    time:
      (d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() >> 1),
    date: ((year - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate(),
  };
}

/** `drive/folder/a.png`; keeps the source folder so equal names cannot collide. */
export function zipEntryName(o: Output): string {
  return `${o.source}/${o.relative_path}`.replace(/^\/+/, "");
}

export function buildZip(entries: ZipEntry[]): Blob {
  if (entries.length >= 0xffff) throw new Error("Too many files for one ZIP.");
  const encoder = new TextEncoder();
  const parts: BlobPart[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;
  for (const entry of entries) {
    const name = encoder.encode(entry.name);
    const crc = crc32(entry.data);
    const { time, date } = dosDateTime(entry.modified);
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);
    local.setUint16(4, 20, true);
    local.setUint16(6, 0x0800, true); // UTF-8 names
    local.setUint16(8, 0, true); // stored
    local.setUint16(10, time, true);
    local.setUint16(12, date, true);
    local.setUint32(14, crc, true);
    local.setUint32(18, entry.data.length, true);
    local.setUint32(22, entry.data.length, true);
    local.setUint16(26, name.length, true);
    local.setUint16(28, 0, true);
    parts.push(local.buffer as ArrayBuffer, name, entry.data as BlobPart);

    const dir = new DataView(new ArrayBuffer(46));
    dir.setUint32(0, 0x02014b50, true);
    dir.setUint16(4, 20, true);
    dir.setUint16(6, 20, true);
    dir.setUint16(8, 0x0800, true);
    dir.setUint16(10, 0, true);
    dir.setUint16(12, time, true);
    dir.setUint16(14, date, true);
    dir.setUint32(16, crc, true);
    dir.setUint32(20, entry.data.length, true);
    dir.setUint32(24, entry.data.length, true);
    dir.setUint16(28, name.length, true);
    dir.setUint32(42, offset, true);
    const head = new Uint8Array(46 + name.length);
    head.set(new Uint8Array(dir.buffer), 0);
    head.set(name, 46);
    central.push(head);
    offset += 30 + name.length + entry.data.length;
  }
  const dirSize = central.reduce((n, c) => n + c.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, entries.length, true);
  end.setUint16(10, entries.length, true);
  end.setUint32(12, dirSize, true);
  end.setUint32(16, offset, true);
  parts.push(...(central as BlobPart[]), end.buffer as ArrayBuffer);
  return new Blob(parts, { type: "application/zip" });
}
