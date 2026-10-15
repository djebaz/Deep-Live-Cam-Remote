import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Api } from "./api";
import type { Values } from "./settings";
import { DetailView } from "./gallery/DetailView";
import { Header, SelectionBar } from "./gallery/Header";
import {
  allSelected,
  clamp,
  filterAndSort,
  indexOfId,
  outputId,
  pruneSelection,
  sanitizeSort,
  sanitizeView,
  selectAll,
  selectionStats,
  stepIndex,
  thumbPx,
  toggleSelection,
  type DateRange,
  type Selection,
  type SortKey,
  type SourceFilter,
  type View,
} from "./gallery/model";
import { PhotoCache, saveBlob } from "./gallery/photoCache";
import type { Meta } from "./gallery/ThumbMedia";
import { ThumbnailCache, browserDecode } from "./gallery/thumbs";
import { useOutputs } from "./gallery/useOutputs";
import { GridView, ListView } from "./gallery/Views";
import {
  MAX_ZIP_BYTES,
  MAX_ZIP_ENTRIES,
  buildZip,
  zipEntryName,
  type ZipEntry,
} from "./gallery/zip";
import "./gallery/gallery.css";

export { PhotoCache, saveBlob };

interface Caches {
  photos: PhotoCache;
  thumbs: ThumbnailCache;
}

export function Outputs({
  api,
  options,
  change,
  log,
}: {
  api: Api;
  options: Values;
  change: (k: string, v: string | number | boolean) => void;
  log: (s: string) => void;
}) {
  const kind = options.kind === "videos" ? "videos" : "photos";
  const view = sanitizeView(options.view);
  const sort = sanitizeSort(options.sort);
  const thumb = clamp(Number(options.thumb) || 100, 25, 250);
  const autoRefresh = options.autorefresh !== false;
  const autoplay = Boolean(options.autoplay);
  const seconds = clamp(Number(options.seconds) || 3.5, 0.25, 60);
  const prefetch = clamp(Math.round(Number(options.prefetch) || 10), 1, 50);

  const [text, setText] = useState("");
  const [source, setSource] = useState<SourceFilter>("all");
  const [range, setRange] = useState<DateRange>("all");
  const [selected, setSelected] = useState<Selection>(new Set());
  const [focusId, setFocusId] = useState<string | null>(null);
  const [meta, setMeta] = useState<Record<string, Meta>>({});
  const [full, setFull] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [zip, setZip] = useState<{ done: number; total: number } | null>(null);
  const [caches, setCaches] = useState<Caches | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const zipAbort = useRef<AbortController | null>(null);
  const browseView = useRef<View>(view === "list" ? "list" : "grid");
  // Parent callbacks are new functions every render; route them through refs so
  // the memoised tiles and effects below stay stable across preference changes.
  const changeRef = useRef(change);
  changeRef.current = change;
  const logRef = useRef(log);
  logRef.current = log;
  const stableLog = useCallback((s: string) => logRef.current(s), []);
  if (view !== "detail") browseView.current = view;

  const { files, state, error, updatedAt, refresh } = useOutputs(
    api,
    kind,
    autoRefresh,
    stableLog,
  );
  const shown = useMemo(
    () => filterAndSort(files, { text, source, range, sort }),
    [files, text, source, range, sort],
  );

  // Caches live in effects so React StrictMode's mount/unmount/mount is safe.
  useEffect(() => {
    const fetchBlob = async (item: { download_path: string }, signal: AbortSignal) => {
      const url = await api.media(item.download_path, signal);
      const r = await fetch(url, { signal, cache: "no-store" });
      if (!r.ok) throw new Error(`Preview HTTP ${r.status}`);
      return r.blob();
    };
    const c = {
      photos: new PhotoCache(api),
      thumbs: new ThumbnailCache(fetchBlob, browserDecode),
    };
    setCaches(c);
    return () => {
      c.photos.dispose();
      c.thumbs.dispose();
    };
  }, [api]);

  useEffect(() => {
    setSelected(new Set());
    setFocusId(null);
    setMeta({});
    setNote("");
  }, [api, kind]);
  useEffect(() => setSelected((s) => pruneSelection(s, files)), [files]);
  useEffect(() => setNote(""), [selected]);

  const onMeta = useCallback(
    (id: string, m: Meta) =>
      setMeta((prev) => {
        const old = prev[id];
        if (
          old &&
          old.width === (m.width ?? old.width) &&
          old.height === (m.height ?? old.height) &&
          old.duration === (m.duration ?? old.duration)
        )
          return prev;
        return { ...prev, [id]: { ...old, ...m } };
      }),
    [],
  );

  const index = Math.max(0, indexOfId(shown, focusId));
  const open = useCallback(
    (id: string) => {
      setFocusId(id);
      changeRef.current("view", "detail");
    },
    [],
  );
  const toggle = useCallback(
    (id: string) => setSelected((s) => toggleSelection(s, id)),
    [],
  );
  const step = useCallback(
    (delta: number) => {
      if (shown.length < 2) return;
      const i = Math.max(0, indexOfId(shown, focusId));
      setFocusId(outputId(shown[stepIndex(i, delta, shown.length)]));
    },
    [shown, focusId],
  );
  const back = () => change("view", browseView.current);

  // ---- full screen: real Fullscreen API where available, CSS fallback otherwise
  const toggleFull = useCallback(() => {
    setFull((on) => {
      const next = !on;
      const el = root.current;
      try {
        if (next && el?.requestFullscreen) void el.requestFullscreen().catch(() => {});
        if (!next && document.fullscreenElement) void document.exitFullscreen();
      } catch {
        /* CSS fallback still applies */
      }
      return next;
    });
  }, []);
  useEffect(() => {
    const sync = () => {
      if (!document.fullscreenElement) setFull(false);
    };
    document.addEventListener("fullscreenchange", sync);
    return () => {
      document.removeEventListener("fullscreenchange", sync);
      if (document.fullscreenElement) void document.exitFullscreen();
    };
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName)) return;
      if (e.ctrlKey || e.metaKey || e.altKey || view === "detail") return;
      if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
      } else if (e.key === "f" || e.key === "F") toggleFull();
      else if (e.key === "Escape" && full) toggleFull();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [view, full, toggleFull]);

  // ---- selection
  const checkedAll = allSelected(shown, selected);
  const toggleAll = () =>
    setSelected((s) => {
      const next = new Set(s);
      if (allSelected(shown, s)) for (const f of shown) next.delete(outputId(f));
      else for (const id of selectAll(shown)) next.add(id);
      return next;
    });
  const stats = selectionStats(files, selected);

  // ---- downloads
  async function downloadCurrent() {
    const item = shown[index];
    if (!item) return;
    setBusy(true);
    try {
      const a = document.createElement("a");
      a.href = await api.media(item.download_path);
      a.download = item.name;
      a.rel = "noreferrer";
      a.click();
    } catch (e) {
      setNote(String(e));
      log(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function downloadBackend(archive: boolean) {
    setBusy(true);
    setNote("");
    try {
      let path = `/outputs/${kind}/zip`;
      if (archive) {
        const r = await api.request<{ zip_id: string; size_bytes: number }>(
          `/outputs/${kind}/create-zip`,
          "POST",
        );
        path = `/download-archive/${r.zip_id}`;
        setNote(`Archive ready: ${(r.size_bytes / 1048576).toFixed(1)} MiB, kept on the backend.`);
      }
      const a = document.createElement("a");
      a.href = await api.media(path);
      a.download = `${kind}_outputs.zip`;
      a.rel = "noreferrer";
      a.click();
    } catch (e) {
      setNote(String(e));
      log(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function downloadSelected() {
    const items = files.filter((f) => selected.has(outputId(f)));
    if (!items.length) return;
    if (items.length > MAX_ZIP_ENTRIES || stats.bytes > MAX_ZIP_BYTES) {
      setNote(
        `Too large for the browser (limit ${MAX_ZIP_ENTRIES} files / ${MAX_ZIP_BYTES / 1048576} MB). Use Download all or Create archive.`,
      );
      return;
    }
    const controller = new AbortController();
    zipAbort.current = controller;
    setBusy(true);
    setNote("");
    setZip({ done: 0, total: items.length });
    try {
      const entries: ZipEntry[] = new Array(items.length);
      let next = 0;
      let done = 0;
      const worker = async () => {
        for (;;) {
          const i = next++;
          if (i >= items.length) return;
          const it = items[i];
          const url = await api.media(it.download_path, controller.signal);
          const r = await fetch(url, { signal: controller.signal, cache: "no-store" });
          if (!r.ok) throw new Error(`${it.relative_path}: HTTP ${r.status}`);
          entries[i] = {
            name: zipEntryName(it),
            data: new Uint8Array(await r.arrayBuffer()),
            modified: it.modified,
          };
          setZip({ done: ++done, total: items.length });
        }
      };
      await Promise.all([worker(), worker()]);
      saveBlob(buildZip(entries), `${kind}_selected_${items.length}.zip`);
      setNote(`Downloaded ${items.length} file${items.length === 1 ? "" : "s"}.`);
    } catch (e) {
      if ((e as Error)?.name === "AbortError") setNote("Cancelled.");
      else {
        setNote(String(e));
        log(String(e));
      }
    } finally {
      zipAbort.current = null;
      setZip(null);
      setBusy(false);
    }
  }
  useEffect(() => () => zipAbort.current?.abort(), []);

  const size = thumbPx(thumb);
  const filtered = text || source !== "all" || range !== "all";
  const clearFilters = () => {
    setText("");
    setSource("all");
    setRange("all");
  };

  let body: React.ReactNode;
  if (!caches || (state === "loading" && !files.length)) {
    body = (
      <div className="og-empty">
        <h2>Loading {kind}…</h2>
        <p>Reading the output folders on the backend.</p>
      </div>
    );
  } else if (state === "error" && !files.length) {
    body = (
      <div className="og-empty" role="alert">
        <h2>Could not load outputs</h2>
        <p>{error}</p>
        <button type="button" className="og-btn primary" onClick={refresh}>
          Try again
        </button>
      </div>
    );
  } else if (!files.length) {
    body = (
      <div className="og-empty">
        <h2>No {kind} yet</h2>
        <p>
          Processed {kind} from the Drive and Colab output folders appear here
          automatically{autoRefresh ? "" : " after you refresh"}. Custom output
          folders are not indexed.
        </p>
      </div>
    );
  } else if (!shown.length) {
    body = (
      <div className="og-empty">
        <h2>No {kind} match</h2>
        <p>Nothing matches the current search and filters.</p>
        <button type="button" className="og-btn" onClick={clearFilters}>
          Clear filters
        </button>
      </div>
    );
  } else if (view === "detail") {
    body = (
      <DetailView
        files={shown}
        index={index}
        kind={kind}
        api={api}
        thumbs={caches.thumbs}
        photos={caches.photos}
        meta={meta}
        onMeta={onMeta}
        selected={selected}
        onToggle={toggle}
        onStep={step}
        onPick={(i) => setFocusId(outputId(shown[i]))}
        onBack={back}
        autoplay={autoplay}
        seconds={seconds}
        prefetch={prefetch}
        onAutoplay={(on) => change("autoplay", on)}
        onSeconds={(s) => change("seconds", s)}
        fullscreen={full}
        onFullscreen={toggleFull}
        onDownload={downloadCurrent}
        busy={busy}
        log={stableLog}
      />
    );
  } else {
    const common = {
      files: shown,
      kind,
      api,
      cache: caches.thumbs,
      size,
      selected,
      meta,
      onMeta,
      onOpen: open,
      onToggle: toggle,
    } as const;
    body =
      view === "list" ? (
        <ListView
          {...common}
          sort={sort}
          onSort={(s: SortKey) => change("sort", s)}
          allChecked={checkedAll}
          onToggleAll={toggleAll}
        />
      ) : (
        <GridView {...common} />
      );
  }

  return (
    <div
      ref={root}
      className={`og view-${view}${full ? " og-full" : ""}`}
      aria-label="Output library"
    >
      <Header
        kind={kind}
        onKind={(k) => change("kind", k)}
        view={view}
        onView={(v) => {
          if (v === "detail" && !focusId && shown[0]) setFocusId(outputId(shown[0]));
          change("view", v);
        }}
        thumb={thumb}
        onThumb={(n) => change("thumb", n)}
        autoRefresh={autoRefresh}
        onAutoRefresh={(on) => change("autorefresh", on)}
        onRefresh={refresh}
        refreshing={state === "loading"}
        fullscreen={full}
        onFullscreen={toggleFull}
        text={text}
        onText={setText}
        source={source}
        onSource={setSource}
        range={range}
        onRange={setRange}
        sort={sort}
        onSort={(s) => change("sort", s)}
        shown={shown.length}
        total={files.length}
        searchRef={searchRef}
      />
      <SelectionBar
        count={stats.count}
        bytes={stats.bytes}
        total={shown.length}
        allChecked={checkedAll}
        onToggleAll={toggleAll}
        onClear={() => setSelected(new Set())}
        onDownloadSelected={downloadSelected}
        onDownloadAll={() => downloadBackend(false)}
        onArchive={() => downloadBackend(true)}
        busy={busy}
        progress={zip}
        onCancel={() => zipAbort.current?.abort()}
        note={note}
      />
      <div className="og-body">{body}</div>
      <div className="og-foot" role="status">
        {state === "error" && files.length
          ? `Refresh failed: ${error}`
          : updatedAt
            ? `Updated ${new Date(updatedAt).toLocaleTimeString()}${autoRefresh ? " · checking for new outputs automatically" : ""}${filtered ? " · filters active" : ""}`
            : ""}
      </div>
    </div>
  );
}
