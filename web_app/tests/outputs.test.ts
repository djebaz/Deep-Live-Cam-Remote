import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Api, type Output } from "../src/api.ts";
import { defaults } from "../src/settings.ts";
import { PhotoCache } from "../src/gallery/photoCache.ts";
import { ServerThumbs } from "../src/gallery/serverThumbs.ts";
import {
  allSelected,
  dateCutoff,
  describeChange,
  describeLoad,
  filterAndSort,
  formatDuration,
  formatSize,
  indexOfId,
  pruneSelection,
  reconcile,
  sanitizeSort,
  sanitizeView,
  selectAll,
  selectionStats,
  stepIndex,
  thumbPx,
  toggleSelection,
} from "../src/gallery/model.ts";
import { ThumbUnsupported, ThumbnailCache } from "../src/gallery/thumbs.ts";
import { buildZip, crc32, zipEntryName } from "../src/gallery/zip.ts";

const out = (
  name: string,
  modified: number,
  size = 100,
  source = "drive",
  folder = "",
): Output => ({
  name,
  relative_path: folder ? `${folder}/${name}` : name,
  source,
  size,
  modified,
  download_path: `/outputs/photos/file/${source}/${folder ? folder + "/" : ""}${name}`,
});
const q = (o: Partial<Parameters<typeof filterAndSort>[1]> = {}) => ({
  text: "",
  source: "all" as const,
  range: "all" as const,
  sort: "newest" as const,
  ...o,
});

test("filter, search, date range and every sort order", () => {
  const now = 1_000_000;
  const files = [
    out("b_2.png", now - 100, 30),
    out("a_10.png", now - 3 * 86400, 10, "local", "day1"),
    out("a_2.png", now - 40 * 86400, 20, "drive", "day1"),
  ];
  assert.deepEqual(filterAndSort(files, q(), now).map((f) => f.name), ["b_2.png", "a_10.png", "a_2.png"]);
  assert.deepEqual(filterAndSort(files, q({ sort: "oldest" }), now).map((f) => f.name), ["a_2.png", "a_10.png", "b_2.png"]);
  assert.deepEqual(filterAndSort(files, q({ sort: "name" }), now).map((f) => f.name), ["a_2.png", "a_10.png", "b_2.png"]); // by file name; natural order: 2 before 10
  assert.deepEqual(filterAndSort(files, q({ sort: "name_desc" }), now).map((f) => f.name), ["b_2.png", "a_10.png", "a_2.png"]);
  assert.deepEqual(filterAndSort(files, q({ sort: "largest" }), now).map((f) => f.size), [30, 20, 10]);
  assert.deepEqual(filterAndSort(files, q({ sort: "smallest" }), now).map((f) => f.size), [10, 20, 30]);
  assert.deepEqual(filterAndSort(files, q({ source: "local" }), now).map((f) => f.name), ["a_10.png"]);
  assert.deepEqual(filterAndSort(files, q({ range: "week" }), now).map((f) => f.name), ["b_2.png", "a_10.png"]);
  assert.deepEqual(filterAndSort(files, q({ range: "month" }), now).length, 2);
  // every search token must match, case-insensitively, across folder and file name
  assert.deepEqual(filterAndSort(files, q({ text: "DAY1 a_2" }), now).map((f) => f.name), ["a_2.png"]);
  assert.deepEqual(filterAndSort(files, q({ text: "nothing" }), now), []);
  // input is never mutated
  assert.equal(files[0].name, "b_2.png");
  assert.equal(dateCutoff("all", now), 0);
});

test("reconcile keeps identity for unchanged outputs and is a no-op when identical", () => {
  const a = out("a.png", 3);
  const b = out("b.png", 2);
  const prev = [a, b];
  assert.equal(reconcile(prev, [{ ...a }, { ...b }]), prev); // identical listing: same array
  const c = out("c.png", 4);
  const next = reconcile(prev, [c, { ...a }, { ...b }]);
  assert.notEqual(next, prev);
  assert.equal(next[1], a); // kept object identity
  assert.equal(next[2], b);
  assert.equal(next[0], c);
  const changed = reconcile(prev, [{ ...a, size: 999 }, b]);
  assert.notEqual(changed[0], a); // size changed => new object
  assert.equal(changed[1], b);
  assert.deepEqual(reconcile(prev, []), []);
});

test("selection helpers survive refreshes", () => {
  const files = [out("a.png", 1, 10), out("b.png", 2, 20), out("c.png", 3, 30)];
  let sel = toggleSelection(new Set(), files[0].download_path);
  sel = toggleSelection(sel, files[1].download_path);
  assert.deepEqual(selectionStats(files, sel), { count: 2, bytes: 30 });
  assert.equal(allSelected(files, sel), false);
  assert.equal(allSelected(files, selectAll(files)), true);
  assert.equal(allSelected([], new Set()), false);
  assert.equal(toggleSelection(sel, files[0].download_path).has(files[0].download_path), false);
  const kept = pruneSelection(sel, [files[1], files[2]]);
  assert.deepEqual([...kept], [files[1].download_path]);
  assert.equal(pruneSelection(sel, files), sel); // nothing removed: same set
  assert.equal(indexOfId(files, files[2].download_path), 2);
  assert.equal(indexOfId(files, null), -1);
  assert.equal(stepIndex(0, -1, 3), 2);
  assert.equal(stepIndex(2, 1, 3), 0);
  assert.equal(stepIndex(0, 1, 0), 0);
});

test("formatting and sanitising", () => {
  assert.equal(formatSize(512), "512 B");
  assert.equal(formatSize(2048), "2 KB");
  assert.equal(formatSize(5 * 1048576), "5.0 MB");
  assert.equal(formatSize(-1), "Unknown");
  assert.equal(formatDuration(65), "1:05");
  assert.equal(formatDuration(3725), "1:02:05");
  assert.equal(thumbPx(100), 160);
  assert.equal(thumbPx(1000), 400);
  assert.equal(thumbPx(Number.NaN), 160);
  assert.equal(sanitizeView("bogus"), "grid");
  assert.equal(sanitizeView("detail"), "detail");
  assert.equal(sanitizeSort("bogus"), "newest");
  assert.equal(sanitizeSort("name"), "name");
});

const wait = () => new Promise((r) => setImmediate(r));

test("thumbnail cache bounds concurrency, loads newest request first, cancels released tiles", async () => {
  const started: string[] = [];
  const gates = new Map<string, { resolve: () => void; signal: AbortSignal }>();
  const cache = new ThumbnailCache(
    (item, signal) =>
      new Promise((resolve, reject) => {
        started.push(item.name);
        signal.addEventListener("abort", () => reject(new DOMException("x", "AbortError")), { once: true });
        gates.set(item.name, { resolve: () => resolve(new Blob(["x"])), signal });
      }),
    async () => ({ blob: new Blob(["thumb"]), width: 800, height: 600 }),
    { concurrency: 2 },
  );
  const items = ["a", "b", "c", "d"].map((n) => out(`${n}.png`, 1));
  const leases = items.map((i) => cache.acquire(i));
  await wait();
  assert.deepEqual(started, ["d.png", "c.png"]); // newest requests first, max 2 at once
  leases[3].release(); // tile d scrolled away: in-flight fetch is aborted
  await wait();
  assert.equal(gates.get("d.png")!.signal.aborted, true);
  assert.deepEqual(started, ["d.png", "c.png", "b.png"]); // slot freed, next newest starts
  leases[0].release(); // a never started: just removed from the queue
  gates.get("c.png")!.resolve();
  const thumb = await leases[2].promise;
  assert.equal(thumb.width, 800);
  assert.match(thumb.url, /^blob:/);
  await wait();
  gates.get("b.png")!.resolve();
  await leases[1].promise;
  assert.ok(!started.includes("a.png"));
  await assert.rejects(leases[3].promise, { name: "AbortError" });
  cache.dispose();
});

test("thumbnail cache dedupes, hits the cache, and only evicts thumbnails nobody holds", async () => {
  let fetches = 0;
  const cache = new ThumbnailCache(
    async () => {
      fetches++;
      return new Blob(["x"]);
    },
    async () => ({ blob: new Blob(["12345"]), width: 10, height: 10 }),
    { maxEntries: 2, concurrency: 4 },
  );
  const [a, b, c] = ["a", "b", "c"].map((n) => out(`${n}.png`, 1));
  const l1 = cache.acquire(a);
  const l2 = cache.acquire(a); // same item: one fetch, two holders
  await Promise.all([l1.promise, l2.promise]);
  assert.equal(fetches, 1);
  const lb = cache.acquire(b);
  await lb.promise;
  const lc = cache.acquire(c);
  await lc.promise;
  assert.equal(cache.size, 3); // everything is held, nothing may be evicted
  lb.release();
  await wait();
  assert.equal(cache.size, 2); // b no longer held: evicted to honour maxEntries
  assert.ok(cache.peek(a.download_path));
  assert.equal(cache.peek(b.download_path), undefined);
  const again = cache.acquire(a);
  assert.equal((await again.promise).width, 10);
  assert.equal(fetches, 3); // a served from cache
  cache.dispose();
  assert.equal(cache.size, 0);
});

test("thumbnail cache refuses oversized originals and reports decode errors", async () => {
  const cache = new ThumbnailCache(
    async () => new Blob(["x"]),
    async () => {
      throw new Error("bad image");
    },
    { maxSourceBytes: 50 },
  );
  await assert.rejects(cache.acquire(out("huge.png", 1, 51)).promise, /Too large/);
  await assert.rejects(cache.acquire(out("bad.png", 1, 10)).promise, /bad image/);
  cache.dispose();
});

test("client ZIP is valid: structure, CRC32, UTF-8 names, and Python can read it", async () => {
  assert.equal(crc32(new TextEncoder().encode("123456789")), 0xcbf43926);
  const files = [
    { name: zipEntryName(out("a.png", 1, 3, "drive", "x")), data: new Uint8Array([1, 2, 3]), modified: 1_700_000_000 },
    { name: "local/é ü.png", data: new Uint8Array(0) },
    { name: "drive/big.bin", data: Uint8Array.from({ length: 70000 }, (_, i) => i % 251) },
  ];
  assert.equal(files[0].name, "drive/x/a.png");
  const blob = buildZip(files);
  const bytes = new Uint8Array(await blob.arrayBuffer());
  const view = new DataView(bytes.buffer);
  const eocd = bytes.length - 22;
  assert.equal(view.getUint32(eocd, true), 0x06054b50);
  assert.equal(view.getUint16(eocd + 10, true), 3);
  let p = view.getUint32(eocd + 16, true);
  const names: string[] = [];
  for (let i = 0; i < 3; i++) {
    assert.equal(view.getUint32(p, true), 0x02014b50);
    const crc = view.getUint32(p + 16, true);
    const size = view.getUint32(p + 24, true);
    const nameLen = view.getUint16(p + 28, true);
    const localAt = view.getUint32(p + 42, true);
    assert.equal(crc, crc32(files[i].data));
    assert.equal(size, files[i].data.length);
    assert.equal(view.getUint32(localAt, true), 0x04034b50);
    names.push(new TextDecoder().decode(bytes.subarray(p + 46, p + 46 + nameLen)));
    p += 46 + nameLen;
  }
  assert.deepEqual(names, files.map((f) => f.name));

  const dir = mkdtempSync(join(tmpdir(), "zip-"));
  const file = join(dir, "t.zip");
  writeFileSync(file, bytes);
  const py = spawnSync("python3", [
    "-c",
    "import sys,zipfile;z=zipfile.ZipFile(sys.argv[1]);assert z.testzip() is None;print(sorted(z.namelist()))",
    file,
  ]);
  if (py.error) return; // python not available: the structural checks above still ran
  assert.equal(py.status, 0, String(py.stderr));
  assert.match(String(py.stdout), /drive\/x\/a\.png/);
});

test("activity-log messages describe loads and changes, and stay silent when nothing changed", () => {
  const a = out("a.png", 3, 1048576, "drive");
  const b = out("b.png", 2, 1048576, "local", "day1");
  assert.equal(describeLoad("photos", []), "No photos found in the Drive and Colab output folders.");
  assert.equal(
    describeLoad("photos", [a, b]),
    "Loaded 2 photos (1 on Google Drive, 1 on Colab disk, 2.0 MB in total).",
  );
  assert.match(describeLoad("videos", [a]), /^Loaded 1 video \(1 on Google Drive/);
  assert.equal(describeChange("photos", [a, b], [{ ...a }, { ...b }]), null);
  assert.equal(describeChange("photos", [a], [b, a]), "1 new photo: day1/b.png.");
  assert.equal(
    describeChange("photos", [a, b], [a]),
    "1 photo no longer on the backend: day1/b.png.",
  );
  const many = ["1", "2", "3", "4", "5"].map((n) => out(`n${n}.png`, 9));
  assert.equal(
    describeChange("photos", [], many),
    "5 new photos: n1.png, n2.png, n3.png and 2 more.",
  );
  assert.equal(
    describeChange("videos", [a], [b]),
    "1 new video: day1/b.png; 1 video no longer on the backend: a.png.",
  );
});

const withFetch = async (impl: typeof fetch, run: () => Promise<void>) => {
  const original = globalThis.fetch;
  globalThis.fetch = impl;
  try {
    await run();
  } finally {
    globalThis.fetch = original;
  }
};
const fakeApi = {
  thumbUrl: (item: Output, size: number) => `http://gw/thumb${item.download_path}?size=${size}`,
  headers: () => ({ Authorization: "Bearer t" }),
} as unknown as Api;
const jpegResponse = () =>
  new Response(new Uint8Array([1, 2, 3]), {
    headers: {
      "Content-Type": "image/jpeg",
      "X-Source-Width": "1600",
      "X-Source-Height": "2400",
      "X-Source-Duration": "3.5",
    },
  });

test("thumbnail URLs are encoded, sized and versioned by the file's modified time", () => {
  const api = new Api({ ...defaults, gateway: "https://gw.example" }, "tok");
  const item = out("a b#1.png", 1700000000.123456, 1, "drive", "ünï/x y");
  const u = new URL(api.thumbUrl(item, 320));
  assert.equal(u.origin, "https://gw.example");
  assert.equal(u.pathname, "/outputs/photos/thumb/drive/%C3%BCn%C3%AF/x%20y/a%20b%231.png");
  assert.equal(u.searchParams.get("size"), "320");
  assert.equal(u.searchParams.get("v"), "1700000000123");
});

test("server thumbnails: bearer fetch, source size kept, support detected from the first answer", async () => {
  const calls: { url: string; auth?: string }[] = [];
  await withFetch(async (url, init) => {
    calls.push({ url: String(url), auth: (init?.headers as Record<string, string>)?.Authorization });
    return jpegResponse();
  }, async () => {
    const server = new ServerThumbs(fakeApi);
    const item = out("a.jpg", 5);
    const blob = await server.blob(item, 320, new AbortController().signal);
    assert.equal(server.mode, "yes");
    assert.deepEqual(server.dims.get(item.download_path), { width: 1600, height: 2400, duration: 3.5 });
    assert.deepEqual(server.blobMeta.get(blob), { width: 1600, height: 2400, duration: 3.5 });
    assert.deepEqual(calls, [{ url: `http://gw/thumb${item.download_path}?size=320`, auth: "Bearer t" }]);
  });
});

test("server thumbnails: an old Colab (route missing) or old gateway (app page) means 'unsupported', once", async () => {
  for (const reply of [
    () => new Response('{"detail":"Not Found"}', { status: 404, headers: { "Content-Type": "application/json" } }),
    () => new Response("<!doctype html>", { status: 200, headers: { "Content-Type": "text/html" } }),
  ]) {
    let n = 0;
    await withFetch(async () => (n++, reply()), async () => {
      const server = new ServerThumbs(fakeApi);
      const signal = new AbortController().signal;
      await assert.rejects(server.fetch(out("a.jpg", 1), 320, signal), ThumbUnsupported);
      assert.equal(server.mode, "no");
      await assert.rejects(server.fetch(out("b.jpg", 1), 320, signal), ThumbUnsupported);
      assert.equal(n, 1, "no further requests once known to be unsupported");
    });
  }
});

test("server thumbnails: a missing or unreadable file is that file's problem, not 'unsupported'", async () => {
  const replies = [
    new Response('{"detail":"output file not found"}', { status: 404 }),
    new Response('{"detail":"cannot create a thumbnail: unreadable image"}', { status: 422 }),
  ];
  await withFetch(async () => replies.shift()!, async () => {
    const server = new ServerThumbs(fakeApi);
    const signal = new AbortController().signal;
    await assert.rejects(server.fetch(out("a.jpg", 1), 320, signal), (e: Error) => !(e instanceof ThumbUnsupported) && /not found/.test(e.message));
    await assert.rejects(server.fetch(out("b.jpg", 1), 320, signal), (e: Error) => !(e instanceof ThumbUnsupported) && /unreadable image/.test(e.message));
    assert.equal(server.mode, "unknown");
  });
});

test("thumbnail cache concurrency can adapt, and the decoder's duration reaches the tile", async () => {
  let limit = 1;
  let running = 0;
  let peak = 0;
  const cache = new ThumbnailCache(
    async () => {
      running++;
      peak = Math.max(peak, running);
      await wait();
      running--;
      return new Blob(["x"]);
    },
    async () => ({ blob: new Blob(["t"]), width: 640, height: 360, duration: 12.5 }),
    { concurrency: () => limit },
  );
  const items = ["a", "b", "c", "d"].map((n) => out(`${n}.mp4`, 1));
  const first = await Promise.all(items.slice(0, 2).map((i) => cache.acquire(i).promise));
  assert.equal(peak, 1);
  assert.equal(first[0].duration, 12.5);
  limit = 3;
  await Promise.all(items.slice(2).map((i) => cache.acquire(i).promise));
  assert.ok(peak >= 2, `peak ${peak} should use the raised limit`);
  cache.dispose();
});

test("preview cache uses its own fetcher: no media ticket, no original-size limit", async () => {
  let ticket = 0;
  const api = { media: async () => (ticket++, "http://never") } as unknown as Api;
  const requested: string[] = [];
  const cache = new PhotoCache(api, 64, async (item) => {
    requested.push(item.name);
    return new Response(new Uint8Array([1, 2, 3]), { headers: { "Content-Type": "image/jpeg" } });
  });
  const huge = out("huge.png", 1, 500 * 1024 * 1024); // far above the 64-byte budget
  cache.trim(new Set([huge.download_path]));
  assert.match(await cache.load(huge), /^blob:/);
  assert.deepEqual(requested, ["huge.png"]);
  assert.equal(ticket, 0);
  cache.dispose();
});
