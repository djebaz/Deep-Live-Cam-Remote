import { useCallback, useEffect, useRef, useState } from "react";
import type { Api, Output } from "../api";
import { describeChange, describeLoad, reconcile } from "./model";

export type LoadState = "idle" | "loading" | "ready" | "error";
export const REFRESH_MS = 8000;

/**
 * Loads the output listing when the tab opens or the kind changes, and
 * (optionally) polls it while the page is visible. Refreshes reconcile by
 * stable identity, so an unchanged listing is a render no-op and nothing the
 * viewer is looking at moves.
 */
export function useOutputs(
  api: Api,
  kind: "photos" | "videos",
  autoRefresh: boolean,
  log: (s: string) => void,
) {
  const [files, setFiles] = useState<Output[]>([]);
  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState(0);
  const generation = useRef(0);
  const inFlight = useRef(false);
  const kindRef = useRef(kind);
  kindRef.current = kind;
  // `log` is a fresh function on every parent render; keep it out of the
  // dependency lists so unrelated re-renders never reload the listing.
  const logRef = useRef(log);
  logRef.current = log;
  const filesRef = useRef<Output[]>([]);
  const loadedOnce = useRef(false);
  const failing = useRef(false);
  const say = (text: string) => logRef.current(`Outputs: ${text}`);

  const load = useCallback(
    async (manual: boolean) => {
      if (inFlight.current && !manual) return;
      const g = generation.current;
      inFlight.current = true;
      if (manual) setState((s) => (s === "ready" ? s : "loading"));
      try {
        const r = await api.request<{ files: Output[] }>(
          `/outputs/${kindRef.current}`,
        );
        if (g !== generation.current) return;
        const prev = filesRef.current;
        const merged = reconcile(prev, r.files);
        filesRef.current = merged;
        setFiles(merged);
        if (!loadedOnce.current) {
          loadedOnce.current = true;
          say(describeLoad(kindRef.current, merged));
        } else {
          const change = describeChange(kindRef.current, prev, merged);
          if (change) say(change);
          else if (manual)
            say(`Refreshed: nothing new (${merged.length} ${kindRef.current}).`);
        }
        if (failing.current) {
          failing.current = false;
          say("Backend reachable again; auto-refresh resumed.");
        }
        setState("ready");
        setError("");
        setUpdatedAt(Date.now());
      } catch (e) {
        if (g !== generation.current) return;
        setError(String(e));
        setState((s) => (s === "ready" && !manual ? s : "error"));
        // A flaky link would otherwise log every poll: say it once, then again on recovery.
        if (manual || !failing.current)
          say(`${manual ? "Refresh" : "Auto-refresh"} failed: ${String(e)}`);
        failing.current = true;
      } finally {
        if (g === generation.current) inFlight.current = false;
      }
    },
    [api],
  );

  useEffect(() => {
    generation.current++;
    inFlight.current = false;
    filesRef.current = [];
    loadedOnce.current = false;
    failing.current = false;
    setFiles([]);
    setState("loading");
    setError("");
    void load(true);
    return () => {
      generation.current++;
    };
  }, [api, kind, load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const tick = () => {
      if (document.visibilityState === "visible") void load(false);
    };
    const t = window.setInterval(tick, REFRESH_MS);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(t);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [autoRefresh, load]);

  return {
    files,
    state,
    error,
    updatedAt,
    refresh: () => load(true),
  };
}
