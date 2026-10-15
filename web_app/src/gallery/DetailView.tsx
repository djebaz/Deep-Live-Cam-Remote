import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import type { Api, Output } from "../api";
import { Icon } from "./icons";
import {
  clamp,
  folderOf,
  formatDate,
  formatDuration,
  formatSize,
  outputId,
  sourceLabel,
  type Selection,
} from "./model";
import type { PhotoCache } from "./photoCache";
import { ThumbMedia, type Meta, type OnMeta } from "./ThumbMedia";
import type { SourceMeta } from "./serverThumbs";
import { ThumbUnsupported, type ThumbnailCache } from "./thumbs";
import { dimensionsText } from "./Views";

const ZOOMS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4];
const SECONDS = [1, 2, 3.5, 5, 10, 20, 30];
const VIDEO_STARTUP_BUFFER_SECONDS = 2;

export interface DetailProps {
  files: Output[];
  index: number;
  kind: "photos" | "videos";
  /** Saved thumbnail-size percentage, shared with the gallery size slider. */
  thumb: number;
  api: Api;
  thumbs: ThumbnailCache;
  /** Full-size originals. */
  photos: PhotoCache;
  /** Server-made previews: shown first, so a big file does not block the viewer. */
  previews: PhotoCache;
  /** Original dimensions reported by the backend (the preview is smaller). */
  dims: (id: string) => SourceMeta | undefined;
  meta: Record<string, Meta>;
  onMeta: OnMeta;
  selected: Selection;
  onToggle: (id: string) => void;
  onStep: (delta: number) => void;
  onPick: (index: number) => void;
  onBack: () => void;
  autoplay: boolean;
  seconds: number;
  prefetch: number;
  onAutoplay: (on: boolean) => void;
  onSeconds: (s: number) => void;
  fullscreen: boolean;
  onFullscreen: () => void;
  onDownload: () => void;
  busy: boolean;
  log: (s: string) => void;
}

export function DetailView(p: DetailProps) {
  const current = p.files[p.index];
  const id = current ? outputId(current) : "";
  // Per-file state is keyed by id so a render that follows a step never shows
  // (or blames) the previous file's image: the URL and "loaded" flag are only
  // valid for the id they were recorded for.
  const [mediaFor, setMediaFor] = useState<{ id: string; url: string; preview: boolean } | null>(null);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  // A failure belongs to one file; deriving `failed` from the id means a stale
  // failure can never be attributed to the next file for a render.
  const [failure, setFailure] = useState<{ id: string; message: string } | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [zoom, setZoom] = useState<"fit" | number>("fit");
  const [natural, setNatural] = useState({ w: 0, h: 0 });
  const canvas = useRef<HTMLDivElement>(null);
  const filmstrip = useRef<HTMLDivElement>(null);
  const videoStartup = useRef<HTMLVideoElement | null>(null);
  const media = mediaFor && mediaFor.id === id ? mediaFor.url : "";
  const loaded = loadedFor === id;
  const isPreview = Boolean(mediaFor && mediaFor.id === id && mediaFor.preview);
  const setLoaded = (on: boolean) => setLoadedFor(on ? id : null);
  const failed = failure && failure.id === id ? failure.message : "";
  const setFailed = (message: string) =>
    setFailure(message ? { id, message } : null);
  const generation = useRef(0);
  const latest = useRef(p);
  latest.current = p;

  // Native autoplay may wait for a large safety buffer. Ask to play once two
  // seconds are available, but never restart a video the user has already paused.
  const startBufferedVideo = (video: HTMLVideoElement) => {
    if (videoStartup.current === video || !video.paused || video.ended ||
        video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
    const remaining = Number.isFinite(video.duration)
      ? Math.max(0, video.duration - video.currentTime) : Infinity;
    const target = Math.min(VIDEO_STARTUP_BUFFER_SECONDS, remaining);
    for (let i = 0; i < video.buffered.length; i++) {
      if (video.buffered.start(i) <= video.currentTime &&
          video.buffered.end(i) - video.currentTime + 0.05 >= target) {
        videoStartup.current = video;
        // Some browser policies still require a gesture; keep native controls usable.
        void video.play().catch(() => {});
        return;
      }
    }
  };

  // Server preview first; an older backend without previews falls back to the original.
  const usingPreviews = useRef(true);
  const loadView = async (item: Output, progress?: (l: number, t: number) => void) => {
    if (usingPreviews.current) {
      try {
        return { url: await p.previews.load(item, progress), preview: true };
      } catch (e) {
        if (!(e instanceof ThumbUnsupported)) throw e;
        usingPreviews.current = false;
      }
    }
    return { url: await p.photos.load(item, progress), preview: false };
  };

  // ---- load the current item (+ bounded prefetch of the next photos)
  useEffect(() => {
    const g = ++generation.current;
    setMediaFor(null);
    setLoaded(false);
    setFailed("");
    setProgress(null);
    setZoom("fit");
    setNatural({ w: 0, h: 0 });
    if (!current) return;
    let cancelled = false;
    const count = p.autoplay ? p.prefetch : 2;
    const upcoming = Array.from(
      { length: Math.min(count, p.files.length - 1) },
      (_, i) => p.files[(p.index + i + 1) % p.files.length],
    );
    if (p.kind === "photos") {
      const keep = new Set([id, ...upcoming.map(outputId)]);
      p.previews.trim(keep);
      p.photos.trim(usingPreviews.current ? new Set([id]) : keep);
    }
    const run = async () => {
      try {
        let url: string;
        let preview = false;
        if (p.kind === "photos") {
          const view = await loadView(current, (l, t) => {
            if (!cancelled) setProgress(t ? (l / t) * 100 : null);
          });
          url = view.url;
          preview = view.preview;
        } else url = await p.api.media(current.download_path);
        if (cancelled || g !== generation.current) return;
        setMediaFor({ id, url, preview });
        setProgress(null);
      } catch (e) {
        if (cancelled || (e as Error)?.name === "AbortError") return;
        setFailed(String((e as Error)?.message || e));
        setProgress(null);
        p.log(`Outputs: preview of ${current.relative_path} failed: ${String((e as Error)?.message || e)}`);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, p.kind, p.api]);

  useEffect(() => {
    if (!loaded || p.kind !== "photos" || !current) return;
    let cancelled = false;
    const count = p.autoplay ? p.prefetch : 2;
    const upcoming = Array.from(
      { length: Math.min(count, p.files.length - 1) },
      (_, i) => p.files[(p.index + i + 1) % p.files.length],
    );
    const keep = new Set([id, ...upcoming.map(outputId)]);
    const settle = () => {
      p.previews.trim(keep);
      p.photos.trim(usingPreviews.current ? new Set([id]) : keep);
    };
    settle();
    (async () => {
      for (let i = 0; i < upcoming.length && !cancelled; i += 2) {
        await Promise.allSettled(upcoming.slice(i, i + 2).map((x) => loadView(x)));
        if (!cancelled) settle();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loaded, id, p.index, p.files, p.kind, p.autoplay, p.prefetch, p.photos, current]);

  // ---- zooming past Fit needs real pixels: swap the preview for the original
  useEffect(() => {
    if (p.kind !== "photos" || zoom === "fit" || !current || !isPreview) return;
    let cancelled = false;
    p.photos.trim(new Set([id]));
    p.photos.load(current).then(
      (url) => !cancelled && setMediaFor({ id, url, preview: false }),
      (e) => {
        if (!cancelled && (e as Error)?.name !== "AbortError")
          p.log(`Outputs: full-size ${current.relative_path} failed to load: ${String((e as Error)?.message || e)}`);
      },
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoom, id, isPreview]);

  // ---- slideshow: advance after load; a broken item is skipped, not a dead end
  useEffect(() => {
    if (!p.autoplay || p.files.length < 2 || !current) return;
    if (p.kind !== "photos") return; // videos advance on `ended`
    if (!loaded && !failed) return;
    if (failed) latest.current.log(`Outputs: skipped ${current.relative_path} in the slideshow (${failed})`);
    const t = window.setTimeout(
      () => p.onStep(1),
      failed ? 1200 : Math.max(250, p.seconds * 1000),
    );
    return () => window.clearTimeout(t);
  }, [p.autoplay, p.seconds, p.kind, loaded, failed, id, p.files.length]);

  // ---- keep the filmstrip selection in view
  useEffect(() => {
    filmstrip.current
      ?.querySelector<HTMLElement>("[aria-current='true']")
      ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [id, p.thumb]);

  // ---- zoom helpers
  const fitScale = () => {
    const el = canvas.current;
    if (!el || !natural.w) return 1;
    return Math.min(el.clientWidth / natural.w, el.clientHeight / natural.h);
  };
  const displayed = () => (zoom === "fit" ? fitScale() : zoom);
  const setZoomAround = (next: number, cx?: number, cy?: number) => {
    const el = canvas.current;
    const clamped = clamp(next, 0.1, 6);
    if (!el || !natural.w) {
      setZoom(clamped);
      return;
    }
    const before = displayed();
    const x = cx ?? el.clientWidth / 2;
    const y = cy ?? el.clientHeight / 2;
    const px = (el.scrollLeft + x) / before;
    const py = (el.scrollTop + y) / before;
    setZoom(clamped);
    requestAnimationFrame(() => {
      el.scrollLeft = px * clamped - x;
      el.scrollTop = py * clamped - y;
    });
  };
  const stepZoom = (dir: 1 | -1) => {
    const cur = displayed();
    const next =
      dir > 0
        ? ZOOMS.find((z) => z > cur + 0.001)
        : [...ZOOMS].reverse().find((z) => z < cur - 0.001);
    if (next !== undefined) setZoomAround(next);
  };
  const toggleFit = () => (zoom === "fit" ? setZoomAround(1) : setZoom("fit"));

  // ---- Ctrl/⌘ + wheel zoom anchored at the pointer (non-passive listener)
  useEffect(() => {
    const el = canvas.current;
    if (!el || p.kind !== "photos") return;
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      setZoomAround(displayed() * factor, e.clientX - rect.left, e.clientY - rect.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  });

  // ---- keyboard
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName)) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const cur = latest.current;
      switch (e.key) {
        case "ArrowLeft":
          cur.onStep(-1);
          break;
        case "ArrowRight":
          cur.onStep(1);
          break;
        case "Escape":
          if (cur.fullscreen) cur.onFullscreen();
          else cur.onBack();
          break;
        case "f":
        case "F":
          cur.onFullscreen();
          break;
        case "+":
        case "=":
          stepZoom(1);
          break;
        case "-":
          stepZoom(-1);
          break;
        case "0":
          setZoom("fit");
          break;
        case " ":
          if (cur.kind === "photos") {
            e.preventDefault();
            cur.onAutoplay(!cur.autoplay);
          }
          break;
        default:
          return;
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  // ---- drag to pan (mouse/pen) when zoomed; swipe to navigate (touch) when fitted
  const drag = useRef<{ x: number; y: number; sl: number; st: number; type: string } | null>(null);
  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = canvas.current;
    if (!el || p.kind !== "photos") return;
    drag.current = {
      x: e.clientX,
      y: e.clientY,
      sl: el.scrollLeft,
      st: el.scrollTop,
      type: e.pointerType,
    };
    if (zoom !== "fit") el.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    const el = canvas.current;
    if (!d || !el || zoom === "fit") return;
    el.scrollLeft = d.sl - (e.clientX - d.x);
    el.scrollTop = d.st - (e.clientY - d.y);
  };
  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    drag.current = null;
    if (!d || zoom !== "fit" || d.type === "mouse") return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (Math.abs(dx) > 60 && Math.abs(dy) < 50) p.onStep(dx < 0 ? 1 : -1);
  };

  const m = p.meta[id];
  const dims = useMemo(
    () =>
      natural.w
        ? dimensionsText({ width: natural.w, height: natural.h })
        : dimensionsText(m),
    [natural, m],
  );
  if (!current) {
    return (
      <div className="og-empty">
        <h2>Nothing to show</h2>
        <p>No output matches the current filters.</p>
      </div>
    );
  }
  const isSelected = p.selected.has(id);
  const shownZoom = zoom === "fit" ? "Fit" : `${Math.round(zoom * 100)}%`;
  const imgStyle =
    zoom === "fit" || !natural.w
      ? undefined
      : { width: natural.w * zoom, height: natural.h * zoom, maxWidth: "none", maxHeight: "none" };

  return (
    <div
      className="og-detail"
      style={{ "--og-film-scale": p.thumb / 100 } as CSSProperties}
    >
      <div className="og-detail-main">
        <div className="og-preview">
          <div
            ref={canvas}
            className={"og-canvas" + (zoom !== "fit" ? " zoomed" : "")}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={() => (drag.current = null)}
            onDoubleClick={() => p.kind === "photos" && toggleFit()}
          >
            {failed ? (
              <div className="og-empty inline" role="alert">
                <h2>Preview failed</h2>
                <p>{failed}</p>
                <p>Download remains available.</p>
              </div>
            ) : !media ? (
              <div className="og-empty inline">
                <h2>Loading…</h2>
                {progress !== null && <progress max="100" value={progress} />}
              </div>
            ) : p.kind === "photos" ? (
              <img
                src={media}
                alt={current.relative_path}
                draggable={false}
                style={imgStyle}
                className={zoom === "fit" ? "fit" : ""}
                onLoad={(e) => {
                  // The preview is smaller than the file: use the original's size.
                  const d = p.dims(id);
                  const w = d?.width ?? e.currentTarget.naturalWidth;
                  const h = d?.height ?? e.currentTarget.naturalHeight;
                  setNatural({ w, h });
                  setLoaded(true);
                  p.onMeta(id, { width: w, height: h });
                }}
                onError={() => {
                  setLoaded(false);
                  setFailed("The image could not be decoded. Download it to open locally.");
                  p.log(`Outputs: ${current.relative_path} could not be decoded by this browser.`);
                }}
              />
            ) : (
              <video
                key={id}
                src={media}
                controls
                playsInline
                preload="auto"
                autoPlay
                muted
                onLoadedData={(e) => startBufferedVideo(e.currentTarget)}
                onCanPlay={(e) => startBufferedVideo(e.currentTarget)}
                onProgress={(e) => startBufferedVideo(e.currentTarget)}
                onPlay={(e) => { videoStartup.current = e.currentTarget; }}
                onDurationChange={(e) => p.onMeta(id, { duration: e.currentTarget.duration })}
                onLoadedMetadata={(e) => {
                  setLoaded(true);
                  p.onMeta(id, {
                    width: e.currentTarget.videoWidth,
                    height: e.currentTarget.videoHeight,
                    duration: e.currentTarget.duration,
                  });
                }}
                onEnded={() => p.autoplay && p.onStep(1)}
                onError={() => {
                  setFailed(
                    "This browser cannot play the video format. Download it to use a compatible player.",
                  );
                  p.log(`Outputs: ${current.relative_path} cannot be played in this browser; download it instead.`);
                }}
              />
            )}
          </div>
          <div className="og-overlay tl">
            <span className="og-chip">
              {p.index + 1} / {p.files.length}
            </span>
            <span className="og-chip">{dims}</span>
            <span className="og-chip muted">{sourceLabel(current.source)}</span>
          </div>
          <div className="og-overlay tr">
            <button
              type="button"
              className="og-round small"
              onClick={p.onFullscreen}
              aria-label={p.fullscreen ? "Exit full screen" : "Full screen"}
              title={p.fullscreen ? "Exit full screen (Esc)" : "Full screen (F)"}
            >
              <Icon name={p.fullscreen ? "exitFullscreen" : "fullscreen"} size={16} />
            </button>
          </div>
          {p.files.length > 1 && (
            <>
              <button
                type="button"
                className="og-round prev"
                aria-label="Previous"
                onClick={() => p.onStep(-1)}
              >
                <Icon name="left" size={20} />
              </button>
              <button
                type="button"
                className="og-round next"
                aria-label="Next"
                onClick={() => p.onStep(1)}
              >
                <Icon name="right" size={20} />
              </button>
            </>
          )}
          <div className="og-pill" role="toolbar" aria-label="Viewer controls">
            {p.kind === "photos" && (
              <>
                <button type="button" onClick={() => stepZoom(-1)} aria-label="Zoom out" title="Zoom out (−)">
                  <Icon name="minus" size={14} />
                </button>
                <button type="button" className="og-zoomlabel" onClick={toggleFit} title="Toggle Fit / 100% (double-click)">
                  {shownZoom}
                </button>
                <button type="button" onClick={() => stepZoom(1)} aria-label="Zoom in" title="Zoom in (+)">
                  <Icon name="plus" size={14} />
                </button>
                <span className="og-sep" />
              </>
            )}
            <button
              type="button"
              className={p.autoplay ? "on" : ""}
              aria-pressed={p.autoplay}
              onClick={() => p.onAutoplay(!p.autoplay)}
              title={p.kind === "photos" ? "Slideshow (Space)" : "Auto-play next video"}
            >
              <Icon name={p.autoplay ? "pause" : "play"} size={14} />
              <span className="og-pill-text">{p.autoplay ? "Pause" : "Slideshow"}</span>
            </button>
            {p.kind === "photos" && (
              <select
                aria-label="Seconds per photo"
                value={p.seconds}
                onChange={(e) => p.onSeconds(Number(e.target.value))}
              >
                {[...new Set([...SECONDS, p.seconds])]
                  .sort((a, b) => a - b)
                  .map((s) => (
                    <option key={s} value={s}>
                      {s}s
                    </option>
                  ))}
              </select>
            )}
          </div>
        </div>
        <div className="og-meta" aria-label="File details">
          <Block icon="file" label="File">
            <span title={current.name}>{current.name}</span>
          </Block>
          <Block icon="folder" label="Folder">
            {folderOf(current.relative_path) || "—"}
          </Block>
          <Block icon="drive" label="Source">
            {sourceLabel(current.source)}
          </Block>
          <Block icon="weight" label="Size">
            {formatSize(current.size)}
          </Block>
          <Block icon="ruler" label="Dimensions">
            {dims}
          </Block>
          {p.kind === "videos" && (
            <Block icon="clock" label="Duration">
              {formatDuration(m?.duration ?? NaN) || "—"}
            </Block>
          )}
          <Block icon="calendar" label="Modified">
            {formatDate(current.modified)}
          </Block>
        </div>
        <div className="og-actions">
          <button type="button" className="og-btn" onClick={p.onBack}>
            <Icon name="grid" size={14} /> Back to library
          </button>
          <button
            type="button"
            className={"og-btn" + (isSelected ? " active" : "")}
            aria-pressed={isSelected}
            onClick={() => p.onToggle(id)}
          >
            <Icon name="check" size={14} /> {isSelected ? "Selected" : "Select"}
          </button>
          <button type="button" className="og-btn primary" disabled={p.busy} onClick={p.onDownload}>
            <Icon name="download" size={14} /> Download this file
          </button>
          {progress !== null && <progress max="100" value={progress} />}
        </div>
      </div>
      <div className="og-film" ref={filmstrip} aria-label="Filmstrip">
        {p.files.map((f, i) => (
          <button
            key={outputId(f)}
            type="button"
            className={"og-thumb" + (i === p.index ? " on" : "")}
            aria-current={i === p.index ? "true" : undefined}
            aria-label={`Show ${f.relative_path}`}
            onClick={() => p.onPick(i)}
          >
            <ThumbMedia item={f} kind={p.kind} api={p.api} cache={p.thumbs} onMeta={p.onMeta} />
          </button>
        ))}
      </div>
    </div>
  );
}

function Block({
  icon,
  label,
  children,
}: {
  icon: Parameters<typeof Icon>[0]["name"];
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="og-mblock">
      <span className="og-mlabel">
        <Icon name={icon} size={12} />
        {label}
      </span>
      <span className="og-mvalue">{children}</span>
    </div>
  );
}
