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
