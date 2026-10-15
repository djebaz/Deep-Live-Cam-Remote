import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { once } from "node:events";
import { WebSocket, WebSocketServer } from "ws";
import { createGateway } from "../server/gateway.mjs";
import { pack } from "../src/protocol.ts";
const token = "local-check-token-32-characters-long";
test("production gateway: auth, origins, target restriction, media Range and binary/text WebSocket relay", async () => {
  const received: any[] = [];
  const upstream = http.createServer((req, res) => {
    received.push({
      path: req.url,
      auth: req.headers.authorization,
      range: req.headers.range,
    });
    if (req.url === "/health") {
      res.setHeader("Content-Type", "application/json");
      res.end('{"ok":true}');
    } else {
      res.writeHead(req.headers.range ? 206 : 200, {
        "Content-Type": "image/webp",
        "Content-Length": 3,
        "Accept-Ranges": "bytes",
      });
      res.end("abc");
    }
  });
  upstream.listen(0, "127.0.0.1");
  await once(upstream, "listening");
  const u = `http://127.0.0.1:${(upstream.address() as any).port}`;
  const wsServer = new WebSocketServer({ server: upstream });
  wsServer.on("connection", (ws) =>
    ws.on("message", (b, binary) => ws.send(b, { binary })),
  );
  const gateway = createGateway({
    backends: [u],
    token,
    origins: ["https://controller.example"],
  });
  gateway.listen(0, "127.0.0.1");
  await once(gateway, "listening");
  const base = `http://127.0.0.1:${(gateway.address() as any).port}`;
  const headers = {
    Authorization: `Bearer ${token}`,
    Origin: "https://controller.example",
  };
  try {
    assert.equal((await fetch(base + "/health")).status, 401);
    assert.equal(
      (
        await fetch(base + "/health", {
          headers: { ...headers, Origin: "https://evil.example" },
        })
      ).status,
      403,
    );
    assert.equal(
      (
        await fetch(base + "/health", {
          headers: { ...headers, "X-DLCR-Backend": "169.254.169.254:80" },
        })
      ).status,
      400,
    );
    const health = await fetch(base + "/health", { headers });
    assert.deepEqual(await health.json(), { ok: true });
    assert.equal(
      health.headers.get("Access-Control-Allow-Origin"),
      "https://controller.example",
    );
    assert.equal(received[0].auth, undefined);
    const preflight = await fetch(base + "/health", {
      method: "OPTIONS",
      headers: {
        Origin: headers.Origin,
        "Access-Control-Request-Private-Network": "true",
      },
    });
    assert.equal(preflight.status, 204);
    assert.equal(
      preflight.headers.get("Access-Control-Allow-Private-Network"),
      "true",
    );
    const ticket = async (path: string, media = false) => {
      const r = await fetch(
        base + (media ? "/gateway/media-ticket" : "/gateway/ticket"),
        {
          method: "POST",
          headers: { ...headers, "Content-Type": "application/json" },
          body: JSON.stringify({ path }),
        },
      );
      assert.equal(r.status, 200);
      return (await r.json()).ticket;
    };
    const media = await ticket(
      "/outputs/photos/file/local/nested/a.webp",
      true,
    );
    const download = await fetch(
      base + "/outputs/photos/file/local/nested/a.webp?ticket=" + media,
      { headers: { Range: "bytes=0-2" } },
    );
    assert.equal(download.status, 206);
    assert.equal(await download.text(), "abc");
    assert.equal(
      received.at(-1).path,
      "/outputs/photos/file/local/nested/a.webp",
    );
    assert.equal(received.at(-1).range, "bytes=0-2");
    assert.equal(
      (
        await fetch(
          base + "/outputs/photos/file/local/other.webp?ticket=" + media,
        )
      ).status,
      401,
    );
    const wsTicket = await ticket("/ws/live");
    const ws = new WebSocket(
      base.replace("http:", "ws:") + "/ws/live?ticket=" + wsTicket,
      { headers: { Origin: headers.Origin } },
    );
    await once(ws, "open");
    let message = once(ws, "message");
    ws.send('{"type":"live_config_update","config":{"opacity":0.5}}');
    const [text, isBinary] = await message;
    assert.equal(isBinary, false);
    assert.match(text.toString(), /opacity/);
    const packet = pack([
      {
        meta: { seq: 1, capture_monotonic: 0 },
        bytes: new Uint8Array([255, 216, 255]),
      },
    ]);
    message = once(ws, "message");
    ws.send(packet);
    const [binary, binaryFlag] = await message;
    assert.equal(binaryFlag, true);
    assert.deepEqual(Buffer.from(packet), binary);
    ws.close();
    await once(ws, "close");
    const bad = new WebSocket(
      base.replace("http:", "ws:") + "/ws/live?ticket=" + wsTicket,
      { headers: { Origin: headers.Origin } },
    );
    const [err] = await once(bad, "error");
    assert.match(String(err), /403/);
  } finally {
    gateway.closeAllConnections();
    await new Promise<void>((r) => gateway.close(() => r()));
    wsServer.clients.forEach((ws) => ws.terminate());
    await new Promise<void>((r) => wsServer.close(() => r()));
    await new Promise<void>((r) => upstream.close(() => r()));
  }
});

test("gateway serves thumbnails over bearer auth, passes the source size, caches only thumbnails, and still refuses other routes", async () => {
  const seen: string[] = [];
  const upstream = http.createServer((req, res) => {
    seen.push(String(req.url));
    if (req.url?.startsWith("/outputs/photos/thumb/drive/")) {
      res.writeHead(200, {
        "Content-Type": "image/jpeg",
        "Content-Length": 3,
        "X-Source-Width": "1600",
        "X-Source-Height": "2400",
        "X-Source-Duration": "3.5",
        "Cache-Control": req.url.includes("v=") ? "private, max-age=31536000, immutable" : "public, max-age=99999",
      });
      res.end("jpg");
    } else {
      res.writeHead(200, { "Content-Type": "application/json", "Cache-Control": "private, max-age=600" });
      res.end("{}");
    }
  });
  upstream.listen(0, "127.0.0.1");
  await once(upstream, "listening");
  const gateway = createGateway({
    backends: [`http://127.0.0.1:${(upstream.address() as any).port}`],
    token,
    origins: ["https://controller.example"],
  });
  gateway.listen(0, "127.0.0.1");
  await once(gateway, "listening");
  const base = `http://127.0.0.1:${(gateway.address() as any).port}`;
  const headers = { Authorization: `Bearer ${token}`, Origin: "https://controller.example" };
  try {
    const url = "/outputs/photos/thumb/drive/nested/a%20b.jpg?size=320";
    assert.equal((await fetch(base + url)).status, 401);
    const hit = await fetch(base + url + "&v=123", { headers });
    assert.equal(hit.status, 200);
    assert.equal(await hit.text(), "jpg");
    assert.equal(hit.headers.get("x-source-width"), "1600");
    assert.equal(hit.headers.get("x-source-duration"), "3.5");
    assert.match(hit.headers.get("access-control-expose-headers") || "", /X-Source-Width/);
    assert.equal(hit.headers.get("cache-control"), "private, max-age=31536000, immutable");
    // a backend that says "public" for a thumbnail is not trusted to widen caching
    assert.equal((await fetch(base + url, { headers })).headers.get("cache-control"), "no-store");
    // every other route stays no-store even if the backend asks for caching
    assert.equal((await fetch(base + "/health", { headers })).headers.get("cache-control"), "no-store");
    // unknown thumbnail shapes are never proxied (GET falls back to the app page; other methods 404)
    const before = seen.length;
    for (const bad of ["/outputs/photos/thumb/nowhere/a.jpg", "/outputs/music/thumb/drive/a.jpg", "/outputs/photos/thumb/drive"]) {
      const r = await fetch(base + bad, { headers });
      assert.match(r.headers.get("content-type") || "", /text\/html|application\/json/);
      assert.notEqual(r.headers.get("content-type"), "image/jpeg");
    }
    assert.equal((await fetch(base + "/outputs/photos/thumb/drive/a.jpg", { method: "POST", headers })).status, 404);
    assert.equal(seen.length, before, "no unknown route reached the backend");
  } finally {
    gateway.closeAllConnections();
    upstream.closeAllConnections();
    await new Promise<void>((r) => gateway.close(() => r()));
    await new Promise<void>((r) => upstream.close(() => r()));
  }
});
