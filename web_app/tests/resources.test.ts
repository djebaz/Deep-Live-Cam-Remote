import { test } from "node:test";
import assert from "node:assert/strict";
import { PhotoCache } from "../src/Outputs.tsx";
import { LiveSession } from "../src/live.ts";
import { Api, type Output } from "../src/api.ts";
import { defaults, liveDefaults, restore } from "../src/settings.ts";
const item = (name: string): Output => ({
  name,
  relative_path: name,
  source: "local",
  size: 2,
  modified: 0,
  download_path: `/outputs/photos/file/local/${name}`,
});
test("photo cache bounds concurrent requests, aborts obsolete fetches, and releases object URLs", async () => {
  const original = globalThis.fetch;
  let concurrent = 0,
    max = 0;
  const holders: { resolve: (r: Response) => void; signal: AbortSignal }[] = [];
  globalThis.fetch = async (_url, init) =>
    new Promise<Response>((resolve, reject) => {
      concurrent++;
      max = Math.max(max, concurrent);
      const signal = init!.signal as AbortSignal;
      const abort = () => {
        concurrent--;
        reject(new DOMException("Cancelled", "AbortError"));
      };
      signal.addEventListener("abort", abort, { once: true });
      holders.push({
        signal,
        resolve: (r) => {
          signal.removeEventListener("abort", abort);
          concurrent--;
          resolve(r);
        },
      });
    });
  const api = { media: async () => "http://test/media" } as unknown as Api;
  const cache = new PhotoCache(api, 4);
  try {
    cache.trim(
      new Set([
        item("a.webp").download_path,
        item("b.webp").download_path,
        item("c.webp").download_path,
      ]),
    );
    const first = cache.load(item("a.webp")).catch((e) => e);
    const second = cache.load(item("b.webp")).catch((e) => e);
    const third = cache.load(item("c.webp")).catch((e) => e);
    await new Promise((r) => setImmediate(r));
    assert.equal(holders.length, 2);
    cache.trim(new Set([item("c.webp").download_path]));
    await new Promise((r) => setImmediate(r));
    assert.equal(holders.length, 3);
    assert.ok(max <= 2);
    holders[2].resolve(
      new Response(new Uint8Array([1, 2]), {
        headers: { "Content-Type": "image/webp" },
      }),
    );
    const [a, b, c] = await Promise.all([first, second, third]);
    assert.equal(a.name, "AbortError");
    assert.equal(b.name, "AbortError");
    assert.equal(typeof c, "string");
    assert.equal((await original(c)).status, 200);
    cache.dispose();
    globalThis.fetch = original;
    await assert.rejects(() => fetch(c));
  } finally {
    cache.dispose();
    globalThis.fetch = original;
  }
});
test("stopping while browser camera permission is pending releases late tracks and never opens socket", async () => {
  const oldDocument = Object.getOwnPropertyDescriptor(globalThis, "document"),
    oldNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator"),
    oldWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  let resolveCamera!: (s: any) => void;
  let trackStops = 0,
    sockets = 0;
  const video = { pause() {}, srcObject: null, play: async () => {} };
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: { createElement: () => video },
  });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { isSecureContext: true },
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: {
      mediaDevices: {
        getUserMedia: () =>
          new Promise((r) => {
            resolveCamera = r;
          }),
      },
    },
  });
  try {
    const api = {
      preferences: defaults,
      socket: async () => {
        sockets++;
      },
    } as unknown as Api;
    const session = new LiveSession(
      api,
      { ...liveDefaults },
      {} as HTMLCanvasElement,
      () => {},
      () => {},
      () => {},
    );
    const starting = session.start(undefined);
    await new Promise((r) => setImmediate(r));
    session.stop();
    resolveCamera({ getTracks: () => [{ stop: () => trackStops++ }] });
    await starting;
    assert.equal(trackStops, 1);
    assert.equal(sockets, 0);
    session.stop();
    assert.equal(trackStops, 1);
  } finally {
    for (const [key, d] of [
      ["document", oldDocument],
      ["navigator", oldNavigator],
      ["window", oldWindow],
    ] as const) {
      if (d) Object.defineProperty(globalThis, key, d);
      else Reflect.deleteProperty(globalThis, key);
    }
  }
});
test("preferences restore independent workflow settings without credentials", () => {
  const old = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const stored = {
    ...defaults,
    photos: { ...defaults.photos, opacity: 0.4 },
    videos: { ...defaults.videos, opacity: 0.8 },
    live: { ...defaults.live, preview_buffer_seconds: 2 },
  };
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: { getItem: () => JSON.stringify(stored) },
  });
  try {
    const p = restore();
    assert.equal(p.photos.opacity, 0.4);
    assert.equal(p.videos.opacity, 0.8);
    assert.equal(p.live.preview_buffer_seconds, 2);
    assert.equal("token" in p, false);
  } finally {
    if (old) Object.defineProperty(globalThis, "localStorage", old);
    else Reflect.deleteProperty(globalThis, "localStorage");
  }
});
