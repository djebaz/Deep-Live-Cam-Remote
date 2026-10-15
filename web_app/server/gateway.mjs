import http from "node:http";
import https from "node:https";
import { timingSafeEqual, randomBytes } from "node:crypto";
import { createReadStream, existsSync, statSync } from "node:fs";
import { resolve, dirname, extname, relative, isAbsolute, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { WebSocket, WebSocketServer } from "ws";
import { relayWebSockets } from "./relay.mjs";
const HERE = dirname(fileURLToPath(import.meta.url));
export function createGateway({
  backends,
  token,
  origins = [],
  dist = resolve(HERE, "../dist"),
} = {}) {
  if (!token || token.length < 24)
    throw new Error("DLCR_GATEWAY_TOKEN must contain at least 24 characters.");
  const targets = (backends || []).map((raw) => {
    const u = new URL(raw);
    if (
      !["http:", "https:"].includes(u.protocol) ||
      u.username ||
      u.password ||
      u.pathname !== "/" ||
      u.search ||
      u.hash
    )
      throw new Error(
        "Backends must be HTTP(S) origins without credentials or paths.",
      );
    return u;
  });
  if (!targets.length)
    throw new Error(
      "Configure DLCR_BACKENDS with at least one private backend origin.",
    );
  const tickets = new Map(),
    sessions = new Set();
  const wss = new WebSocketServer({
    noServer: true,
    maxPayload: 4 * 1024 * 1024,
    perMessageDeflate: false,
  });
  const equal = (value) => {
    const a = Buffer.from(value || ""),
      b = Buffer.from(token);
    return a.length === b.length && timingSafeEqual(a, b);
  };
  const authenticated = (req) =>
    equal((req.headers.authorization || "").replace(/^Bearer /, ""));
  const originOK = (req) =>
    !req.headers.origin || origins.includes(req.headers.origin);
  const backend = (req) => {
    const host = req.headers["x-dlcr-backend"];
    const target = !host ? targets[0] : targets.find((u) => u.host === host);
    if (!target)
      throw new Error(
        "Backend address/port is not in DLCR_BACKENDS. Configure the gateway allowlist.",
      );
    return target;
  };
  const json = (res, code, value) => {
    res.writeHead(code, {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    });
    res.end(JSON.stringify(value));
  };
  const allowed = (path, method) => {
    if (method === "DELETE" && /^\/upload\/(photos|videos)\/batches\/[a-zA-Z0-9_-]{1,80}$/.test(path)) return true;
    if (
      method === "GET" &&
      (/^\/health$/.test(path) ||
        /^\/jobs\/[a-zA-Z0-9-]+$/.test(path) ||
        /^\/outputs\/(photos|videos)(\/zip|\/file\/(local|drive)\/.+|\/thumb\/(local|drive)\/.+)?$/.test(
          path,
        ) ||
        /^\/download-archive\/[a-zA-Z0-9-]+$/.test(path))
    )
      return true;
    return (
      method === "POST" &&
      (/^\/jobs\/(photos|videos|cancel)$/.test(path) ||
        /^\/upload\/(file|source|photos|videos)$/.test(path) ||
        /^\/outputs\/(photos|videos)\/(create-zip|preflight)$/.test(path))
    );
  };
  const mediaPath = (path) =>
    /^\/outputs\/(photos|videos)\/(zip|file\/(local|drive)\/.+)$/.test(path) ||
    /^\/download-archive\/[a-zA-Z0-9-]+$/.test(path);
  const wsPath = (path) => /^\/ws\/(live|jobs\/[a-zA-Z0-9-]+)$/.test(path);
  const readJSON = async (req) => {
    let text = "";
    for await (const chunk of req) {
      text += chunk;
      if (Buffer.byteLength(text) > 8192) throw new Error("Request too large");
    }
    return JSON.parse(text || "{}");
  };
  const takeTicket = (req, url, type) => {
    const id = url.searchParams.get("ticket"),
      t = tickets.get(id);
    if (
      !t ||
      t.type !== type ||
      t.path !== url.pathname ||
      t.expires < Date.now() ||
      !originOK(req)
    )
      return null;
    if (type === "ws") tickets.delete(id);
    return t.target;
  };
  const housekeeping = setInterval(() => {
    for (const [k, t] of tickets) if (t.expires < Date.now()) tickets.delete(k);
  }, 30000);
  housekeeping.unref();
  const server = http.createServer(async (req, res) => {
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader("Referrer-Policy", "no-referrer");
    if (!originOK(req)) {
      json(res, 403, {
        error:
          "Origin not allowed. Configure DLCR_ORIGINS with the exact HTTPS frontend origin.",
      });
      return;
    }
    const origin = req.headers.origin;
    if (origin) {
      res.setHeader("Access-Control-Allow-Origin", origin);
      res.setHeader("Vary", "Origin");
      res.setHeader("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS");
      res.setHeader(
        "Access-Control-Allow-Headers",
        "Authorization, Content-Type, X-DLCR-Backend, Range",
      );
      res.setHeader(
        "Access-Control-Expose-Headers",
        "Content-Length, Content-Range, Content-Disposition, X-Source-Width, X-Source-Height, X-Source-Duration",
      );
      if (req.headers["access-control-request-private-network"] === "true")
        res.setHeader("Access-Control-Allow-Private-Network", "true");
    }
    if (req.method === "OPTIONS") {
      res.writeHead(204);
      res.end();
      return;
    }
    try {
      const url = new URL(req.url, "http://gateway.local");
      const path = url.pathname;
      if (path.startsWith("/gateway/")) {
        if (!authenticated(req)) {
          json(res, 401, { error: "Enter the gateway access token." });
          return;
        }
        if (path === "/gateway/info" && req.method === "GET") {
          json(res, 200, {
            backends: targets.map((u) => ({
              host: u.hostname,
              port: Number(u.port || (u.protocol === "https:" ? 443 : 80)),
            })),
            default_backend: targets[0].host,
          });
          return;
        }
        if (
          req.method === "POST" &&
          ["/gateway/ticket", "/gateway/media-ticket"].includes(path)
        ) {
          const payload = await readJSON(req);
          const type = path === "/gateway/ticket" ? "ws" : "media";
          if (
            typeof payload.path !== "string" ||
            !(type === "ws" ? wsPath(payload.path) : mediaPath(payload.path))
          ) {
            json(res, 400, { error: "Invalid ticket path" });
            return;
          }
          if (tickets.size >= 4096) {
            json(res, 429, { error: "Too many pending tickets" });
            return;
          }
          const id = randomBytes(32).toString("base64url");
          tickets.set(id, {
            type,
            path: payload.path,
            target: backend(req),
            expires: Date.now() + (type === "ws" ? 30000 : 3600000),
          });
          json(res, 200, { ticket: id });
          return;
        }
        json(res, 404, { error: "Unknown gateway operation" });
        return;
      }
      if (allowed(path, req.method)) {
        const target = authenticated(req)
          ? backend(req)
          : req.method === "GET" && mediaPath(path)
            ? takeTicket(req, url, "media")
            : null;
        if (!target) {
          json(res, 401, { error: "Gateway authorization required" });
          return;
        }
        url.searchParams.delete("ticket");
        const headers = {};
        for (const k of [
          "content-type",
          "content-length",
          "range",
          "if-range",
          "accept",
        ])
          if (req.headers[k]) headers[k] = req.headers[k];
        const upstream = (target.protocol === "https:" ? https : http).request(
          {
            hostname: target.hostname,
            port: target.port || undefined,
            protocol: target.protocol,
            path: path + url.search,
            method: req.method,
            headers,
            timeout: 600000,
          },
          (reply) => {
            // Do not follow redirects; Location could bypass the destination restriction.
            if (reply.statusCode >= 300 && reply.statusCode < 400) {
              reply.resume();
              json(res, 502, { error: "Backend redirect refused" });
              return;
            }
            for (const k of [
              "content-type",
              "content-length",
              "content-range",
              "accept-ranges",
              "content-disposition",
              "etag",
              "last-modified",
              "x-source-width",
              "x-source-height",
              "x-source-duration",
            ])
              if (reply.headers[k]) res.setHeader(k, reply.headers[k]);
            // Everything is no-store except cacheable thumbnails, which the backend
            // marks private and keys by file modification time in the URL.
            const thumb = /^\/outputs\/(photos|videos)\/thumb\//.test(path);
            const cache = reply.headers["cache-control"];
            res.setHeader(
              "Cache-Control",
              thumb && reply.statusCode === 200 && /^private\b/.test(cache || "")
                ? cache
                : "no-store",
            );
            res.writeHead(reply.statusCode || 502);
            reply.pipe(res);
          },
        );
        upstream.on("timeout", () => upstream.destroy());
        upstream.on("error", () => {
          if (!res.headersSent)
            json(res, 502, {
              error:
                "Private backend unreachable. Check Tailscale and Colab API port.",
            });
          else res.destroy();
        });
        req.on("aborted", () => upstream.destroy());
        res.on("close", () => upstream.destroy());
        req.pipe(upstream);
        return;
      }
      if (req.method !== "GET") {
        json(res, 404, { error: "Unknown route" });
        return;
      }
      const decoded = decodeURIComponent(path),
        candidate = resolve(dist, "." + decoded);
      const rel = relative(resolve(dist), candidate);
      if (rel === ".." || rel.startsWith(".." + sep) || isAbsolute(rel)) {
        json(res, 403, { error: "Invalid path" });
        return;
      }
      const file =
        existsSync(candidate) && statSync(candidate).isFile()
          ? candidate
          : resolve(dist, "index.html");
      if (!existsSync(file)) {
        json(res, 503, {
          error: "Build the frontend with npm run build first.",
        });
        return;
      }
      const types = {
        ".html": "text/html",
        ".js": "application/javascript",
        ".css": "text/css",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
      };
      res.setHeader(
        "Content-Type",
        types[extname(file)] || "application/octet-stream",
      );
      res.setHeader(
        "Cache-Control",
        extname(file) === ".html" ? "no-store" : "public, max-age=3600",
      );
      createReadStream(file).pipe(res);
    } catch {
      if (!res.headersSent)
        json(res, 400, { error: "Invalid request or backend configuration" });
      else res.destroy();
    }
  });
  server.on("upgrade", (req, socket, head) => {
    const deny = () =>
      socket.end("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n");
    try {
      const url = new URL(req.url, "http://gateway.local");
      if (!originOK(req) || !wsPath(url.pathname)) return deny();
      const target = takeTicket(req, url, "ws");
      if (!target) return deny();
      // Connect upstream before accepting downstream so the browser cannot create an unbounded pre-open queue.
      const u = new URL(url.pathname, target);
      u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
      const remote = new WebSocket(u, {
        perMessageDeflate: false,
        maxPayload: 8 * 1024 * 1024,
        handshakeTimeout: 15000,
      });
      sessions.add(remote);
      socket.once("close", () => remote.terminate());
      remote.once("error", deny);
      remote.once("open", () =>
        wss.handleUpgrade(req, socket, head, (client) => {
          sessions.add(client);
          remote.removeListener("error", deny);
          relayWebSockets(client, remote, () => {
            sessions.delete(client);
            sessions.delete(remote);
          });
        }),
      );
      remote.on("close", () => sessions.delete(remote));
    } catch {
      deny();
    }
  });
  server.on("close", () => {
    clearInterval(housekeeping);
    for (const s of sessions) s.terminate();
    wss.close();
  });
  return server;
}
if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  try {
    const gateway = createGateway({
      backends: (process.env.DLCR_BACKENDS || "").split(",").filter(Boolean),
      token: process.env.DLCR_GATEWAY_TOKEN,
      origins: (process.env.DLCR_ORIGINS || "").split(",").filter(Boolean),
    });
    gateway.listen(Number(process.env.PORT || 8787), "127.0.0.1", () =>
      console.log(
        "Deep Live Cam gateway listening on 127.0.0.1. Use private HTTPS Tailscale Serve.",
      ),
    );
    const shutdown = () => {
      gateway.close();
      gateway.closeAllConnections();
    };
    process.on("SIGINT", shutdown);
    process.on("SIGTERM", shutdown);
  } catch (e) {
    console.error(e.message);
    process.exitCode = 1;
  }
}
