import test from "node:test";
import assert from "node:assert/strict";
import { describeProgress, formatEta } from "../src/progress.ts";

test("formatEta", () => {
  assert.equal(formatEta(42), "42s");
  assert.equal(formatEta(80), "1m 20s");
  assert.equal(formatEta(3725), "1h 02m");
  assert.equal(formatEta(-5), "0s");
});

test("describeProgress shows item, file, percent, fps and ETA", () => {
  const d = describeProgress({
    item: 2,
    items: 4,
    name: "nested/clip.mp4",
    state: "processing",
    frames: 50,
    total: 200,
    fps: 8.25,
    file_percent: 25,
    overall_percent: 31.3,
    eta_seconds: 75,
  });
  assert.equal(d?.text, "Item 2 / 4 · clip.mp4 · 25% · 8.3 fps · ~1m 15s left");
  assert.equal(d?.percent, 31.3);
});

test("describeProgress copes with unknown totals, skips and missing progress", () => {
  assert.equal(describeProgress(null), null);
  assert.equal(describeProgress(undefined), null);
  const unknown = describeProgress({ item: 1, items: 1, state: "processing", frames: 30, fps: 6, file_percent: null });
  assert.equal(unknown?.text, "Item 1 / 1 · 30 frames · 6.0 fps");
  assert.equal(describeProgress({ item: 3, items: 3, name: "a.png", state: "skipped" })?.text, "Item 3 / 3 · a.png · skipped");
});

test("describeProgress warns when the backend stopped reporting", () => {
  const base = { item: 1, items: 1, name: "a.mp4", state: "processing", file_percent: 1, fps: 39.5, updated_at: 1000 };
  assert.ok(!describeProgress(base, 1010)?.text.includes("no progress"));
  assert.ok(describeProgress(base, 1065)?.text.endsWith("⚠ no progress for 1m 05s"));
  assert.ok(!describeProgress({ ...base, state: "done" }, 5000)?.text.includes("no progress"));
});
