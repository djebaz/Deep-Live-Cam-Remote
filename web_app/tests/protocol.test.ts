import { test } from "node:test";
import assert from "node:assert/strict";
import { pack, unpack, PreviewQueue, PACKET_LIMIT } from "../src/protocol.ts";
import { expectedOutput, selectedInputs, startBatch } from "../src/batch.ts";
import { defaults, jobPayload } from "../src/settings.ts";
import type { Api } from "../src/api.ts";
const frame = (seq: number, capture: unknown = seq / 25, wall = 1000) => ({
  meta: { seq, capture_monotonic: capture, capture_time: wall },
  bytes: new Uint8Array([seq % 256]),
});
test("DLCR network framing matches fixed protocol bytes and rejects truncation", () => {
  const f = { meta: { seq: 4 }, bytes: new Uint8Array([0xff, 0xd8, 0xff]) };
  const b = pack([f]);
  assert.deepEqual(
    Array.from(new Uint8Array(b).slice(0, 16)),
    [68, 76, 67, 82, 0, 1, 0, 1, 0, 0, 0, 9, 0, 0, 0, 3],
  );
  assert.deepEqual(unpack(b), [f]);
  assert.throws(() => unpack(b.slice(0, -1)), /length/);
  const trailing = new Uint8Array(b.byteLength + 1);
  trailing.set(new Uint8Array(b));
  assert.throws(() => unpack(trailing.buffer), /Trailing/);
  assert.throws(
    () => pack([{ meta: {}, bytes: new Uint8Array(PACKET_LIMIT) }]),
    /4 MiB/,
  );
});
test("legacy JPEG binary bytes are accepted without UTF-8 decoding", () => {
  assert.equal(
    unpack(new Uint8Array([255, 216, 255, 224]).buffer)[0].bytes.length,
    4,
  );
});
test("actual FPS, missing sequences, clock jumps, overdue coalescing and last-image retention", () => {
  const q = new PreviewQueue(1);
  q.enqueue(frame(0, 0, 1000), 100);
  assert.equal(q.take(100.9), undefined);
  assert.equal(q.take(101)?.seq, 0);
  q.enqueue(frame(1000, 40, 1000000), 140);
  assert.equal(q.take(141)?.seq, 1000);
  q.enqueue(frame(1200, 48, -1000000), 150);
  q.enqueue(frame(1225, 49, 9000000), 150);
  assert.equal(q.take(150.01)?.seq, 1225);
  assert.equal(q.take(150.02), undefined);
  assert.ok(q.dropped >= 1);
});
test("legacy absent/invalid capture metadata buffers by arrival and memory stays bounded", () => {
  for (const stamp of [undefined, null, "", NaN, Infinity, -1]) {
    const q = new PreviewQueue(0.5, 3, 4);
    q.enqueue(frame(0, stamp), 10);
    assert.equal(q.take(10.49), undefined);
    assert.equal(q.take(10.5)?.seq, 0);
  }
  const q = new PreviewQueue(1, 3, 2);
  for (let i = 0; i < 20; i++) q.enqueue(frame(i), 100 + i / 25);
  assert.ok(q.queue.length <= 2);
  assert.ok(q.bytes <= 2);
  assert.equal(q.dropped, 18);
});
test("preview hot delay changes and restart establish fresh timing origins", () => {
  const q = new PreviewQueue(1);
  q.enqueue(frame(1, 0), 10);
  q.setDelay(2);
  assert.equal(q.take(11.9), undefined);
  assert.equal(q.take(12)?.seq, 1);
  q.clear();
  q.enqueue(frame(0, 0), 50);
  assert.equal(q.take(52)?.seq, 0);
});
test("output naming follows real photo and video CLI, including nested paths", () => {
  assert.equal(
    expectedOutput("folder/clip.MOV", "videos"),
    "folder/clip_face_swapped.mp4",
  );
  assert.equal(
    expectedOutput("one/photo.WEBP", "photos"),
    "one/photo_face_swapped.webp",
  );
  const p = structuredClone(defaults);
  p.photos_input = "/content/custom";
  assert.equal(jobPayload(p, "photos", "face", "in").quality, 95);
  assert.equal(jobPayload(p, "videos", "face", "in").quality, 18);
});
test("recursive folder filtering preserves relative path and detects collisions", () => {
  const file = (name: string, path: string) =>
    ({ name, webkitRelativePath: path }) as File;
  const files = [
    file("x.webp", "root/a/x.webp"),
    file("y.png", "root/y.png"),
    file("z.txt", "root/z.txt"),
  ];
  assert.deepEqual(
    selectedInputs(files, "photos", true).map((x) => x.relative),
    ["a/x.webp", "y.png"],
  );
  assert.deepEqual(
    selectedInputs(files, "photos", false).map((x) => x.relative),
    ["y.png"],
  );
  assert.throws(
    () =>
      selectedInputs(
        [file("x.webp", "root/a/x.webp"), file("x.webp", "root/a/x.webp")],
        "photos",
        true,
      ),
    /Duplicate/,
  );
});
test("all-processed preflight issues no source upload, input upload or job creation", async () => {
  const calls: string[] = [];
  const api = {
    request: async (path: string) => {
      calls.push(path);
      if (path === "/health")
        return {
          web_capabilities: {
            relative_uploads: true,
            output_preflight: true,
            photo_options: true,
          },
        };
      return { processed: ["x.webp"] };
    },
    upload: () => {
      throw new Error("Unexpected upload");
    },
  } as unknown as Api;
  const result = await startBatch(
    api,
    defaults,
    "photos",
    [{ name: "x.webp", webkitRelativePath: "" } as File],
    undefined,
    new AbortController().signal,
    () => {},
    () => {},
  );
  assert.equal(result, null);
  assert.deepEqual(calls, ["/health", "/outputs/photos/preflight"]);
});
