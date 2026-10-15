import { useEffect, useRef, useState } from "react";
import type { Api, Output } from "../api";
import { Icon } from "./icons";
import { ThumbUnsupported, type ThumbnailCache } from "./thumbs";

export interface Meta {
  width?: number;
  height?: number;
  duration?: number;
}
export type OnMeta = (id: string, m: Meta) => void;

function useVisible(rootMargin = "600px") {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => setVisible(entries.some((e) => e.isIntersecting)),
      { rootMargin },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [rootMargin]);
  return [ref, visible] as const;
}

/**
 * A tile image for one output. Photos are thumbnailed in the browser through the
 * shared cache; videos show the browser's own first frame. Nothing is requested
 * until the tile is near the viewport, and the request is cancelled when it
 * scrolls away.
 */
export function ThumbMedia({
  item,
  kind,
  api,
  cache,
  onMeta,
}: {
  item: Output;
  kind: "photos" | "videos";
  api: Api;
  cache: ThumbnailCache;
  onMeta: OnMeta;
}) {
  const [ref, visible] = useVisible();
  const [src, setSrc] = useState<string>(
    () => (kind === "photos" && cache.peek(item.download_path)?.url) || "",
  );
  const [failed, setFailed] = useState("");
  // Videos use the server's poster frame; only when the backend has none does the
  // tile fall back to letting the browser load the video's first frame.
  const [videoElement, setVideoElement] = useState(false);
  const id = item.download_path;

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    let release = () => {};
    setFailed("");
    if (kind === "photos" || !videoElement) {
      const lease = cache.acquire(item);
      release = lease.release;
      lease.promise.then(
        (t) => {
          if (cancelled) return;
          setSrc(t.url);
          onMeta(id, { width: t.width, height: t.height, duration: t.duration });
        },
        (e) => {
          if (cancelled) return;
          if (kind === "videos" && e instanceof ThumbUnsupported) setVideoElement(true);
          else if ((e as Error)?.name !== "AbortError")
            setFailed(String((e as Error)?.message || e));
        },
      );
    } else {
      api.media(item.download_path).then(
        (url) => !cancelled && setSrc(url),
        (e) => !cancelled && setFailed(String(e)),
      );
    }
    return () => {
      cancelled = true;
      release();
    };
  }, [visible, kind, id, item, api, cache, onMeta, videoElement]);

  return (
    <div className="og-media" ref={ref}>
      {src && (kind === "photos" || !videoElement) ? (
        <img src={src} alt="" draggable={false} decoding="async" />
      ) : src && kind === "videos" ? (
        <video
          src={src}
          muted
          playsInline
          preload="metadata"
          onLoadedMetadata={(e) =>
            onMeta(id, {
              width: e.currentTarget.videoWidth,
              height: e.currentTarget.videoHeight,
              duration: e.currentTarget.duration,
            })
          }
          onError={() => setFailed("This browser cannot show a preview.")}
        />
      ) : (
        <span className="og-placeholder" title={failed || undefined}>
          <Icon name={failed ? "file" : kind === "videos" ? "video" : "detail"} size={22} />
        </span>
      )}
      {kind === "videos" && src && (
        <span className="og-playmark" aria-hidden="true">
          <Icon name="play" size={18} />
        </span>
      )}
    </div>
  );
}
