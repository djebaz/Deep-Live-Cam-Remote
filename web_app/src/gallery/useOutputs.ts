import { useCallback, useEffect, useRef, useState } from "react";
import type { Api, Output } from "../api";
import { reconcile } from "./model";

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
        setFiles((prev) => reconcile(prev, r.files));
        setState("ready");
        setError("");
        setUpdatedAt(Date.now());
      } catch (e) {
        if (g !== generation.current) return;
        setError(String(e));
        setState((s) => (s === "ready" && !manual ? s : "error"));
        if (manual) logRef.current(String(e));
      } finally {
        if (g === generation.current) inFlight.current = false;
      }
    },
    [api],
  );

  useEffect(() => {
    generation.current++;
    inFlight.current = false;
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
