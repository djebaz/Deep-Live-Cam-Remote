import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Api, sanitizeLog, type Health, type Job } from "./api";
import { startBatch, selectedInputs, SubmissionRejected } from "./batch";
import {
  restore,
  commonControls,
  photoControls,
  videoControls,
  liveControls,
  HOT,
  LOCAL_HOT,
  type Values,
  type Preferences,
  type Kind,
  type Control,
} from "./settings";
import { chooseJob } from "./recover";
import { describeProgress } from "./progress";
import { pollRead } from "./polling";
import { LiveSession, type LiveStats } from "./live";
import "./style.css";
import { Outputs, saveBlob } from "./Outputs";
function Fields({
  controls,
  values,
  change,
  running = false,
  live = false,
}: {
  controls: Control[];
  values: Values;
  change: (k: string, v: string | number | boolean) => void;
  running?: boolean;
  live?: boolean;
}) {
  return (
    <>
      {controls.map((c) => {
        const value = values[c.key],
          disabled =
            running && (!live || (!HOT.has(c.key) && !LOCAL_HOT.has(c.key)));
        return (
          <label
            key={c.key}
            className={typeof value === "boolean" ? "check" : ""}
            title={
              disabled ? "Stop the session to change this control." : c.hint
            }
          >
            {typeof value === "boolean" ? (
              <>
                <input
                  disabled={disabled}
                  type="checkbox"
                  checked={value}
                  onChange={(e) => change(c.key, e.target.checked)}
                />
                <span>{c.label}</span>
              </>
            ) : (
              <>
                <span>
                  {c.label}
                  {live && disabled && <small> · restart required</small>}
                </span>
                {c.choices ? (
                  <select
                    disabled={disabled}
                    value={String(value)}
                    onChange={(e) => change(c.key, e.target.value)}
                  >
                    {c.choices.map((v) => (
                      <option key={v}>{v}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    disabled={disabled}
                    type="number"
                    value={Number(value)}
                    min={c.min}
                    max={c.max}
                    step={c.step || 1}
                    onChange={(e) => {
                      const n = Number(e.target.value);
                      if (Number.isFinite(n)) change(c.key, n);
                    }}
                    onBlur={(e) => {
                      let n = Number(e.target.value);
                      n = Math.max(c.min ?? n, Math.min(c.max ?? n, n));
                      if (c.key === "detector_size")
                        n = Math.floor(n / 32) * 32;
                      change(c.key, n);
                    }}
                  />
                )}
                {c.hint && <small className="hint">{c.hint}</small>}
              </>
            )}
          </label>
        );
      })}
    </>
  );
}
function App() {
  const [p, setP] = useState<Preferences>(restore),
    [tab, setTab] = useState("Photos"),
    [token, setToken] = useState(""),
    [connected, setConnected] = useState(false),
    [monitoringApi, setMonitoringApi] = useState<Api | null>(null),
    [connectionNotice, setConnectionNotice] = useState(""),
    [health, setHealth] = useState<Health | null>(null),
    [logs, setLogs] = useState<string[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [job, setJob] = useState<Job | null>(null),
    [status, setStatus] = useState("Ready when connected"),
    [progress, setProgress] = useState<{ l: number; t: number } | null>(null),
    [source, setSource] = useState<File>(),
    [inputs, setInputs] = useState<Record<Kind, File[] | null>>({
      photos: null,
      videos: null,
    }),
    [sourcePreview, setSourcePreview] = useState(""),
    [inputPreview, setInputPreview] = useState(""),
    [liveRunning, setLiveRunning] = useState(false),
    [devices, setDevices] = useState<MediaDeviceInfo[]>([]),
    [liveStats, setLiveStats] = useState<LiveStats | null>(null),
    [perf, setPerf] = useState(false),
    [uncertain, setUncertain] = useState(false);
  const operation = useRef<AbortController | null>(null),
    stopRequested = useRef(false),
    submitStarted = useRef(false),
    submittedJob = useRef<Job | null>(null),
    live = useRef<LiveSession | null>(null),
    canvas = useRef<HTMLCanvasElement>(null),
    perfTimer = useRef<number | undefined>(undefined),
    perfOriginal = useRef<Values | null>(null),
    operationLock = useRef(false);
  const api = useMemo(
    () => new Api(p, token),
    [p.gateway, p.host, p.port, token],
  );
  api.preferences = p;
  const currentApi = useRef(api);
  currentApi.current = api;
  const reconnecting = useRef(false);
  const batchRunning = Boolean(
    job && ["queued", "running"].includes(job.status),
  );
  const log = (text: string) =>
    setLogs((v) =>
      [...v, `${new Date().toLocaleTimeString()}  ${sanitizeLog(text)}`].slice(
        -500,
      ),
    );
  const update = (key: keyof Preferences, value: unknown) =>
    setP((old) => ({ ...old, [key]: value }));
  const options = (
    kind: "photos" | "videos" | "live" | "output",
    k: string,
    v: string | number | boolean,
  ) => setP((old) => ({ ...old, [kind]: { ...old[kind], [k]: v } }));
  useEffect(() => {
    try {
      localStorage.setItem("dlcr.web.v1", JSON.stringify(p));
    } catch {
      setError("Preferences could not be saved: browser storage unavailable.");
    }
  }, [p]);
  useEffect(() => {
    setConnected(false);
    setHealth(null);
    setMonitoringApi(null);
    setConnectionNotice("");
    reconnecting.current = false;
  }, [api]);
  useEffect(() => {
    if (!source) {
      setSourcePreview("");
      return;
    }
    const u = URL.createObjectURL(source);
    setSourcePreview(u);
    return () => URL.revokeObjectURL(u);
  }, [source]);
  const kind: Kind = tab === "Videos" ? "videos" : "photos";
  useEffect(() => {
    const f = inputs[kind]?.[0];
    if (!f) {
      setInputPreview("");
      return;
    }
    const u = URL.createObjectURL(f);
    setInputPreview(u);
    return () => URL.revokeObjectURL(u);
  }, [inputs, kind]);
  useEffect(() => {
    live.current?.update(p.live);
  }, [p.live]);
  const stopPerf = () => {
    clearTimeout(perfTimer.current);
    setPerf(false);
    if (perfOriginal.current) {
      const saved = perfOriginal.current;
      setP((old) => ({ ...old, live: saved }));
      perfOriginal.current = null;
    }
  };
  const stopLive = () => {
    stopPerf();
    live.current?.stop();
    setLiveRunning(false);
    operationLock.current = false;
    setStatus("Live stopped. Camera and transport released.");
  };
  useEffect(() => {
    const shutdown = () => {
      operation.current?.abort();
      live.current?.stop();
      clearTimeout(perfTimer.current);
    };
    window.addEventListener("pagehide", shutdown);
    return () => {
      window.removeEventListener("pagehide", shutdown);
      shutdown();
    };
  }, []);
  function connectionLost(cause: unknown) {
    setConnected(false);
    setConnectionNotice(
      "Connection to Colab interrupted. Reconnecting automatically. " +
      (batchRunning
        ? "Your job may still be running; it will not be submitted again."
        : "Check Tailscale and the Colab API if the interruption continues."),
    );
    if (!reconnecting.current)
      log(`Connection interrupted; reconnecting automatically. ${String(cause)}`);
    reconnecting.current = true;
  }
  function connectionRestored() {
    setConnected(true);
    setConnectionNotice("");
    if (reconnecting.current) {
      log(batchRunning
        ? "Connection restored; resumed monitoring the existing job."
        : "Connection restored.");
    }
    reconnecting.current = false;
  }
  function monitoringFailed(cause: unknown) {
    setConnected(false);
    setMonitoringApi(null);
    setConnectionNotice("");
    reconnecting.current = false;
    setError(String(cause));
    log(`Monitoring stopped. Check connection settings. ${String(cause)}`);
  }
  useEffect(() => {
    // The job endpoint itself checks connectivity while a batch is active. Keeping
    // one monitor avoids a healthy response racing a failed health check.
    if (monitoringApi !== api || batchRunning) return;
    return pollRead<Health>(api, "/health", {
      intervalMs: 15000,
      initialDelayMs: 15000,
      onValue: (h) => {
        setHealth(h);
        connectionRestored();
      },
      onRetry: connectionLost,
      onError: monitoringFailed,
    });
  }, [api, monitoringApi, batchRunning]);
  async function check() {
    setError("");
    setStatus("Checking private gateway…");
    try {
      const info = await api.request<{
        backends: { host: string; port: number }[];
      }>("/gateway/info");
      const h = await api.request<Health>("/health");
      if (currentApi.current !== api) return;
      setHealth(h);
      setMonitoringApi(api);
      connectionRestored();
      setStatus(`Connected · ${h.api_version}`);
      log(`Connected: ${h.api_version}`);
      setUncertain(false);
      if (!p.host && info.backends[0])
        log(
          `Gateway default backend: ${info.backends[0].host}:${info.backends[0].port}`,
        );
      let saved: Job | null = null;
      try {
        const record = JSON.parse(
          localStorage.getItem("dlcr.activeJob") || "null",
        );
        if (record?.backend === `${p.gateway}|${p.host}:${p.port}`)
          saved = record.job;
      } catch {}
      let existing: Job | null = null;
      if (saved) {
        try {
          existing = await api.request<Job>(`/jobs/${saved.job_id}`);
        } catch (e) {
          log(`Saved job unavailable: ${String(e)}`);
        }
        if (currentApi.current !== api) return;
        if (!existing || !["queued", "running"].includes(existing.status))
          localStorage.removeItem("dlcr.activeJob");
      }
      const choice = chooseJob(existing, h.active_jobs);
      if (choice.job) {
        setJob(choice.job);
        if (choice.attachedActive)
          log(`Attached to active ${choice.job.kind} job ${choice.job.job_id}`);
      }
    } catch (e) {
      if (currentApi.current !== api) return;
      setConnected(false);
      setError(String(e));
      setStatus("Connection failed");
      log(String(e));
    }
  }
  useEffect(() => {
    if (!job?.job_id || !batchRunning || monitoringApi !== api) return;
    try {
      localStorage.setItem(
        "dlcr.activeJob",
        JSON.stringify({ backend: `${p.gateway}|${p.host}:${p.port}`, job }),
      );
    } catch {}
    return pollRead<Job>(api, `/jobs/${job.job_id}`, {
      intervalMs: 1000,
      onValue: (r) => {
        connectionRestored();
        setJob(r);
        setStatus(`${r.kind}: ${r.status}`);
        if (!["running", "queued"].includes(r.status)) {
          // Stop sending more inputs if the backend fails or cancels during upload.
          operation.current?.abort("job-ended");
          localStorage.removeItem("dlcr.activeJob");
          setProgress(null);
          setBusy(false);
          if (r.error) setError(r.error);
          log(`Job ${r.status}`);
          return false;
        }
      },
      onRetry: connectionLost,
      onError: (e) => {
        if (String(e).includes("unknown job")) {
          connectionRestored();
          setJob({ ...job, status: "unavailable" });
          localStorage.removeItem("dlcr.activeJob");
          setStatus(
            "Job no longer exists on backend. Check Outputs before starting another job.",
          );
          setError(String(e));
          return;
        }
        monitoringFailed(e);
      },
    });
  }, [job?.job_id, api, job?.status, monitoringApi]);
  async function stopBatch() {
    stopRequested.current = true;
    operation.current?.abort();
    if (job && ["queued", "running"].includes(job.status)) {
      try {
        await api.request("/jobs/cancel", "POST", { job_id: job.job_id });
        setStatus(
          "Cancellation requested; waiting for the backend safe boundary.",
        );
        log("Cancellation requested");
      } catch (e) {
        setError(String(e));
      }
    } else {
      operation.current?.abort();
      setStatus("Stopping preparation…");
    }
  }
  async function run(kind: Kind) {
    if (
      operationLock.current ||
      busy ||
      liveRunning ||
      (job && ["queued", "running"].includes(job.status))
    )
      return;
    operationLock.current = true;
    setBusy(true);
    setError("");
    setProgress(null);
    setJob(null);
    stopRequested.current = false;
    submitStarted.current = false;
    submittedJob.current = null;
    const abort = new AbortController();
    operation.current = abort;
    try {
      const r = await startBatch(
        api,
        p,
        kind,
        inputs[kind],
        source,
        abort.signal,
        (s) => {
          log(s);
          setStatus(s);
          if (s.startsWith("Submitting")) submitStarted.current = true;
        },
        (l, t) => setProgress({ l, t }),
        (active) => {
          submittedJob.current = active;
          setJob(active);
        },
      );
      if (r) {
        const active: Job = { ...r, kind };
        setJob((previous) => previous?.job_id === active.job_id ? previous : active);
        if (stopRequested.current)
          await api.request("/jobs/cancel", "POST", { job_id: r.job_id });
      } else setStatus("Everything already processed. No job started.");
    } catch (e) {
      if (abort.signal.aborted && abort.signal.reason === "job-ended") {
        // Polling owns the terminal status and its useful backend error message.
      } else if (e instanceof DOMException && e.name === "AbortError") {
        if (!submittedJob.current) setStatus("Preparation cancelled. No job submitted.");
        else if (stopRequested.current) setStatus("Uploads stopped; cancellation requested for the batch.");
      } else {
        setError(String(e));
        log(String(e));
        if (submitStarted.current && !submittedJob.current && !(e instanceof SubmissionRejected)) {
          setUncertain(true);
          setStatus(
            "Submission response uncertain. Check connection / active jobs before starting again.",
          );
        }
      }
    } finally {
      operation.current = null;
      operationLock.current = false;
      setBusy(false);
      setProgress(null);
    }
  }
  async function cameras() {
    try {
      if (!navigator.mediaDevices)
        throw new Error("Camera access requires HTTPS or localhost.");
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: false,
      });
      stream.getTracks().forEach((t) => t.stop());
      setDevices(
        (await navigator.mediaDevices.enumerateDevices()).filter(
          (d) => d.kind === "videoinput",
        ),
      );
    } catch (e) {
      setError(String(e));
    }
  }
  async function startLive() {
    if (!canvas.current || liveRunning || operationLock.current) return;
    operationLock.current = true;
    setError("");
    setLiveRunning(true);
    setStatus("Opening camera and Live backend…");
    const session = new LiveSession(
      api,
      { ...p.live },
      canvas.current,
      log,
      setLiveStats,
      () => {
        stopPerf();
        setLiveRunning(false);
        operationLock.current = false;
        setStatus("Live ended; see activity log.");
      },
    );
    live.current = session;
    await session.start(source);
  }
  function perfTest() {
    if (perf) {
      stopPerf();
      return;
    }
    if (!liveRunning) return;
    setPerf(true);
    perfOriginal.current = { ...p.live };
    const cases: Values[] = [];
    for (const codec of ["jpeg", "webp"])
      for (const output of ["jpeg", "webp"])
        for (const batch of [1, 8, 16, 32])
          cases.push({
            capture_scale: "50%",
            frame_codec: codec,
            output_codec: output,
            jpeg_quality: 70,
            detector_size: 256,
            detect_every_n: 3,
            pipeline_frames: 64,
            transport_batch_size: batch,
          });
    let index = 0;
    const advance = () => {
      if (index >= cases.length) {
        stopPerf();
        log("Performance sweep completed. Export CSV.");
        return;
      }
      const c = cases[index++];
      setP((old) => ({ ...old, live: { ...old.live, ...c } }));
      log(
        `Performance case ${index}/${cases.length}: ${c.frame_codec} → ${c.output_codec}, batch ${c.transport_batch_size}`,
      );
      perfTimer.current = window.setTimeout(() => {
        live.current?.recordPerformance(
          `${c.frame_codec}_${c.output_codec}_batch${c.transport_batch_size}`,
          9,
        );
        perfTimer.current = window.setTimeout(advance, 9000);
      }, 3000);
    };
    advance();
  }
  const locked = busy || batchRunning || liveRunning;
  const allLogs = [...logs, ...(job?.logs || []).map((s) => sanitizeLog(s))];
  const itemProgress = (job?.logs || [])
    .map((s) => s.match(/\[(\d+)\/(\d+)\]/))
    .filter(Boolean)
    .at(-1);
  const batchProgress = batchRunning && connected
    ? describeProgress(job?.progress, job?.server_time) : null;
  let selected = 0;
  try {
    selected = inputs[kind]
      ? selectedInputs(inputs[kind]!, kind, Boolean(p[kind].recursive)).length
      : 0;
  } catch {}
  const sourceField = (
    <fieldset>
      <legend>
        Source face <small>Shared across workflows</small>
      </legend>
      <label>
        Remote source path
        <input
          disabled={locked}
          value={p.source_face}
          onChange={(e) => update("source_face", e.target.value)}
        />
      </label>
      <label>
        Select source image
        <input
          disabled={locked}
          type="file"
          accept=".bmp,.jpeg,.jpg,.png,.webp"
          onChange={(e) => setSource(e.target.files?.[0])}
        />
      </label>
      {source && (
        <div className="source-selected">
          <img src={sourcePreview} alt="Selected source face" />
          <span>
            {source.name}
            <small>EXIF orientation normalized on upload</small>
          </span>
          <button disabled={locked} onClick={() => setSource(undefined)}>
            Use remote
          </button>
        </div>
      )}
    </fieldset>
  );
  return (
    <>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">D</span>
          <div>
            Deep Live Cam<small>REMOTE CONTROLLER</small>
          </div>
        </div>
        <div className="connection-pill">
          <span className={connected ? "dot online" : "dot"} />
          {connected ? "Connected" : connectionNotice ? "Reconnecting" : "Offline"}
          <span className="connection-address">
            {p.host ? `${p.host}:${p.port}` : "Configure private gateway"}
          </span>
          <button
            disabled={liveRunning}
            aria-label="Connection settings"
            onClick={() => setTab("Connection")}
          >
            Settings
          </button>
        </div>
      </header>
      <nav className="tabs" aria-label="Workflows">
        {["Photos", "Videos", "Live", "Outputs", "Connection"].map((t) => (
          <button
            disabled={liveRunning && t !== "Live"}
            title={
              liveRunning && t !== "Live"
                ? "Stop Live before leaving its preview"
                : undefined
            }
            aria-current={tab === t ? "page" : undefined}
            className={tab === t ? "active" : ""}
            key={t}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
        <span className="nav-note">Processing runs on Colab</span>
      </nav>
      <main>
        <div className="page-heading">
          <div>
            <p className="eyebrow">PRIVATE WORKSPACE</p>
            <h1>
              {tab === "Connection"
                ? "Connection & preferences"
                : tab === "Live"
                  ? "Live camera"
                  : tab === "Outputs"
                    ? "Output library"
                    : `${tab} processing`}
            </h1>
          </div>
          <span className="session-state">
            {liveRunning
              ? "LIVE SESSION"
              : batchRunning
                ? "BATCH ACTIVE"
                : busy
                  ? "PREPARING"
                  : "IDLE"}
          </span>
        </div>
        {connectionNotice && (
          <div role="status" className="connection-notice">
            {connectionNotice}
          </div>
        )}
        {error && (
          <div role="alert" className="error">
            {error}
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              ×
            </button>
          </div>
        )}
        {tab === "Connection" ? (
          <div className="connection-layout">
            <section className="connection-form">
              <fieldset disabled={locked}>
                <legend>Private connection</legend>
                <label>
                  HTTPS gateway URL
                  <input
                    placeholder="Blank when served by your gateway"
                    value={p.gateway}
                    onChange={(e) => update("gateway", e.target.value)}
                  />
                </label>
                <label>
                  Gateway access token
                  <input
                    type="password"
                    autoComplete="off"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                  />
                  <small className="hint">
                    Held in memory; never saved in preferences.
                  </small>
                </label>
                <div className="two">
                  <label>
                    Tailscale backend host / IP
                    <input
                      placeholder="Blank selects gateway default"
                      value={p.host}
                      onChange={(e) => update("host", e.target.value.trim())}
                    />
                  </label>
                  <label>
                    API port
                    <input
                      type="number"
                      min="1"
                      max="65535"
                      value={p.port}
                      onChange={(e) => update("port", Number(e.target.value))}
                    />
                  </label>
                </div>
                <label>
                  Drive root
                  <input
                    value={p.drive_root}
                    onChange={(e) => update("drive_root", e.target.value)}
                  />
                  <small className="hint">
                    A preference only; Colab owns its output roots.
                  </small>
                </label>
                <div className="actions">
                  <button onClick={check} className="primary">
                    Check connection
                  </button>
                  <button
                    onClick={() => {
                      try {
                        localStorage.setItem("dlcr.web.v1", JSON.stringify(p));
                        setStatus("Preferences saved");
                      } catch (e) {
                        setError(String(e));
                      }
                    }}
                  >
                    Save preferences
                  </button>
                </div>
              </fieldset>
              {health && (
                <fieldset>
                  <legend>Backend output roots</legend>
                  {Object.entries({
                    ...health.paths,
                    ...Object.fromEntries(
                      Object.entries(health.local_paths).map(([k, v]) => [
                        "local_" + k,
                        v,
                      ]),
                    ),
                  }).map(([k, v]) => (
                    <p key={k}>
                      <small>{k}</small>
                      <code>{v}</code>
                    </p>
                  ))}
                </fieldset>
              )}
            </section>
            <section className="setup-guide">
              <h2>Connect through your private gateway</h2>
              <ol>
                <li>
                  Start the Colab notebook, mount Drive, and start the updated
                  API.
                </li>
                <li>Connect Colab and the gateway machine to Tailscale.</li>
                <li>
                  Install this repo’s web app and configure its backend and
                  origin allowlists.
                </li>
                <li>Serve the gateway over HTTPS with Tailscale Serve.</li>
                <li>
                  Enter its URL and access token, then check the connection.
                </li>
              </ol>
              <p>
                For same-origin hosting, open the controller at the gateway’s
                HTTPS address and leave its URL blank. For Sites hosting, allow
                this exact Site origin and grant local-network permission if
                requested.
              </p>
              <p>
                Browser camera inputs include OBS Virtual Camera when exposed.
                Explicit DirectShow/MSMF, OBS profile reads, arbitrary
                unselected local paths, and OS virtual-camera output are
                native-only features omitted from this browser release.
              </p>
              <a
                href="https://github.com/djebaz/Deep-Live-Cam-Remote"
                target="_blank"
                rel="noreferrer"
              >
                Repository & setup documentation ↗
              </a>
            </section>
          </div>
        ) : tab === "Outputs" ? (
          <Outputs
            api={api}
            options={p.output}
            change={(k, v) => options("output", k, v)}
            log={log}
          />
        ) : (
          <div className="workspace">
            <aside className="controls">
              {sourceField}
              {tab === "Live" ? (
                <>
                  <fieldset>
                    <legend>Camera input</legend>
                    <button disabled={liveRunning} onClick={cameras}>
                      Find cameras / grant permission
                    </button>
                    <label>
                      Camera
                      <select
                        disabled={liveRunning}
                        value={String(p.live.camera)}
                        onChange={(e) =>
                          options("live", "camera", e.target.value)
                        }
                      >
                        <option value="">Browser default</option>
                        {devices.map((d, i) => (
                          <option value={d.deviceId} key={d.deviceId}>
                            {d.label || `Camera ${i + 1}`}
                          </option>
                        ))}
                      </select>
                    </label>
                    <p className="hint">
                      Select OBS Virtual Camera if exposed as an input.
                      Processed output is previewed here.
                    </p>
                  </fieldset>
                  <fieldset disabled={perf}>
                    <legend>Live controls</legend>
                    <Fields
                      controls={liveControls}
                      values={p.live}
                      change={(k, v) => options("live", k, v)}
                      running={liveRunning}
                      live
                    />
                  </fieldset>
                </>
              ) : (
                <>
                  <fieldset disabled={locked}>
                    <legend>Input & destination</legend>
                    <label>
                      Input workflow
                      <select
                        value={inputs[kind] === null ? "remote" : "local"}
                        onChange={(e) =>
                          setInputs((v) => ({
                            ...v,
                            [kind]: e.target.value === "remote" ? null : [],
                          }))
                        }
                      >
                        <option value="remote">Remote path</option>
                        <option value="local">
                          Selected local files / folder
                        </option>
                      </select>
                    </label>
                    {inputs[kind] === null ? (
                      <label>
                        Remote input folder
                        <input
                          value={p[`${kind}_input`]}
                          onChange={(e) =>
                            update(`${kind}_input`, e.target.value)
                          }
                        />
                      </label>
                    ) : (
                      <>
                        <label>
                          Select files
                          <input
                            type="file"
                            multiple
                            accept={
                              kind === "photos"
                                ? ".bmp,.jpeg,.jpg,.png,.webp"
                                : ".avi,.m4v,.mkv,.mov,.mp4,.webm"
                            }
                            onChange={(e) =>
                              setInputs((v) => ({
                                ...v,
                                [kind]: Array.from(e.target.files || []),
                              }))
                            }
                          />
                        </label>
                        <label>
                          Select folder
                          <input
                            type="file"
                            multiple
                            {...{ webkitdirectory: "" }}
                            onChange={(e) =>
                              setInputs((v) => ({
                                ...v,
                                [kind]: Array.from(e.target.files || []),
                              }))
                            }
                          />
                        </label>
                        <p className="hint">
                          {selected} supported files selected. Folder-relative
                          paths are preserved. Re-select files after reload.
                        </p>
                      </>
                    )}
                    <label>
                      Remote output path
                      <input
                        value={p[`${kind}_output`]}
                        onChange={(e) =>
                          update(`${kind}_output`, e.target.value)
                        }
                      />
                    </label>
                  </fieldset>
                  <fieldset>
                    <legend>Processing options</legend>
                    <Fields
                      controls={commonControls}
                      values={p[kind]}
                      change={(k, v) => options(kind, k, v)}
                      running={locked}
                    />
                  </fieldset>
                  <fieldset>
                    <legend>
                      {kind === "photos"
                        ? "Photo limits & models"
                        : "Video range & encoding"}
                    </legend>
                    <Fields
                      controls={
                        kind === "photos" ? photoControls : videoControls
                      }
                      values={p[kind]}
                      change={(k, v) => options(kind, k, v)}
                      running={locked}
                    />
                  </fieldset>
                </>
              )}
            </aside>
            <section className="stage">
              <div className="stage-heading">
                <span>
                  {tab === "Live" ? "PROCESSED LIVE PREVIEW" : "INPUT PREVIEW"}
                </span>
                <span>
                  {tab === "Live"
                    ? liveStats?.negotiated || "No camera active"
                    : "Local selection"}
                </span>
              </div>
              <div className="media-stage">
                {tab === "Live" ? (
                  <>
                    <canvas
                      ref={canvas}
                      style={{
                        display: liveRunning || liveStats ? "block" : "none",
                      }}
                    />
                    {!liveRunning && !liveStats && (
                      <div className="empty">
                        <span className="empty-icon">◉</span>
                        <h2>Your camera, processed remotely</h2>
                        <p>
                          Select a source, connect to Colab, and start Live.
                        </p>
                      </div>
                    )}
                  </>
                ) : inputPreview ? (
                  kind === "photos" ? (
                    <img src={inputPreview} alt="Selected input preview" />
                  ) : (
                    <video
                      src={inputPreview}
                      controls
                      onError={() =>
                        log(
                          "Local preview codec unsupported; upload remains available.",
                        )
                      }
                    />
                  )
                ) : (
                  <div className="empty">
                    <span className="empty-icon">
                      {kind === "photos" ? "▧" : "▷"}
                    </span>
                    <h2>
                      Prepare your {kind === "photos" ? "photo" : "video"} batch
                    </h2>
                    <p>
                      Choose local media or a remote input folder.
                      <br />
                      Generated files appear in Outputs.
                    </p>
                  </div>
                )}
              </div>
              {tab === "Live" && liveStats && (
                <div className="metrics">
                  {(
                    [
                      "capture_fps",
                      "send_fps",
                      "receive_fps",
                      "display_fps",
                    ] as const
                  ).map((k, i) => (
                    <div key={k}>
                      <strong>{liveStats[k].toFixed(1)}</strong>
                      <span>
                        {["Capture", "Send", "Receive", "Display"][i]} FPS
                      </span>
                    </div>
                  ))}
                  <div>
                    <strong>{liveStats.in_flight}</strong>
                    <span>In flight</span>
                  </div>
                  <div>
                    <strong>{liveStats.buffer_seconds.toFixed(2)}s</strong>
                    <span>Preview buffer</span>
                  </div>
                </div>
              )}
              <div className="stage-footer">
                <p role="status">
                  {connectionNotice ? "Reconnecting to Colab…" : status}
                  {job?.upload && ` · Uploads: ${job.upload.uploaded} / ${job.upload.total}${job.upload.complete ? job.upload.error ? " (stopped)" : " (finished)" : ""}`}
                  {!batchProgress &&
                    itemProgress &&
                    ` · Item ${itemProgress[1]} / ${itemProgress[2]}`}
                  {batchProgress && ` · ${batchProgress.text}`}
                  {!connectionNotice && batchRunning && job?.stage && ` · ${job.stage}`}
                  {batchRunning && job?.cancel_requested && " · cancelling: stops at the next safe point"}
                </p>
                {batchProgress && (
                  <progress
                    aria-label="Processing progress"
                    max={100}
                    value={batchProgress.percent ?? undefined}
                  />
                )}
                {progress && (
                  <progress
                    aria-label="Upload progress"
                    max={progress.t || 1}
                    value={progress.t ? progress.l : undefined}
                  />
                )}
                <div className="actions">
                  {tab === "Live" ? (
                    <>
                      <button
                        className={liveRunning ? "danger" : "primary"}
                        disabled={
                          !liveRunning && (!connected || busy || batchRunning)
                        }
                        title={
                          !connected
                            ? "Connect to the gateway first"
                            : undefined
                        }
                        onClick={liveRunning ? stopLive : startLive}
                      >
                        {liveRunning ? "Stop Live" : "Start Live"}
                      </button>
                      <button disabled={!liveRunning} onClick={perfTest}>
                        {perf
                          ? "Stop performance sweep"
                          : "Run performance sweep"}
                      </button>
                      <button
                        disabled={!live.current}
                        onClick={() => {
                          if (live.current)
                            saveBlob(
                              live.current.exportCSV(),
                              "live-performance.csv",
                            );
                        }}
                      >
                        Export CSV
                      </button>
                    </>
                  ) : (
                    <button
                      className={busy || batchRunning ? "danger" : "primary"}
                      disabled={
                        !busy &&
                        !batchRunning &&
                        (!connected || liveRunning || uncertain)
                      }
                      title={
                        !connected
                          ? "Check connection first"
                          : liveRunning
                            ? "Stop Live first"
                            : undefined
                      }
                      onClick={
                        busy || batchRunning ? stopBatch : () => run(kind)
                      }
                    >
                      {busy || batchRunning
                        ? "Stop batch"
                        : `Start ${kind === "photos" ? "photo" : "video"} batch`}
                    </button>
                  )}
                  <button
                    disabled={liveRunning}
                    onClick={() => {
                      // Open Outputs on the kind of the page the button was clicked on.
                      if (tab === "Photos" || tab === "Videos")
                        options("output", "kind", tab.toLowerCase());
                      setTab("Outputs");
                    }}
                  >
                    Browse outputs →
                  </button>
                </div>
              </div>
            </section>
          </div>
        )}
        <details className="activity" open>
          <summary>
            Activity log <span>{allLogs.length} entries</span>
          </summary>
          <div className="log-toolbar">
            <button
              onClick={() =>
                saveBlob(
                  new Blob([allLogs.join("\n")], { type: "text/plain" }),
                  "remote-controller.log",
                )
              }
            >
              Export log
            </button>
            <button onClick={() => setLogs([])}>Clear local log</button>
          </div>
          <pre aria-label="Activity log">
            {allLogs.join("\n") || "No activity yet."}
          </pre>
          {liveStats && (
            <details>
              <summary>Backend performance diagnostics</summary>
              <pre>{JSON.stringify(liveStats.backend, null, 2)}</pre>
              <p>
                Preview dropped: {liveStats.preview_dropped} · Capture dropped:{" "}
                {liveStats.capture_dropped} · Queued: {liveStats.queued}
              </p>
            </details>
          )}
        </details>
      </main>
      <footer>
        Deep Live Cam Remote · Private Colab controller{" "}
        <span>Preferences saved on this device</span>
      </footer>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
