import { forwardRef } from "react";
import { Icon, type IconName } from "./icons";
import {
  RANGE_LABELS,
  SORT_LABELS,
  SOURCE_LABELS,
  THUMB_MAX,
  THUMB_MIN,
  formatSize,
  type DateRange,
  type SortKey,
  type SourceFilter,
  type View,
} from "./model";

const VIEW_BUTTONS: { view: View; label: string; icon: IconName }[] = [
  { view: "grid", label: "Grid", icon: "grid" },
  { view: "list", label: "List", icon: "list" },
  { view: "detail", label: "Detail", icon: "detail" },
];

export interface HeaderProps {
  kind: "photos" | "videos";
  onKind: (k: "photos" | "videos") => void;
  view: View;
  onView: (v: View) => void;
  thumb: number;
  onThumb: (n: number) => void;
  autoRefresh: boolean;
  onAutoRefresh: (on: boolean) => void;
  onRefresh: () => void;
  refreshing: boolean;
  fullscreen: boolean;
  onFullscreen: () => void;
  text: string;
  onText: (t: string) => void;
  source: SourceFilter;
  onSource: (s: SourceFilter) => void;
  range: DateRange;
  onRange: (r: DateRange) => void;
  sort: SortKey;
  onSort: (s: SortKey) => void;
  shown: number;
  total: number;
}

export const FilterInput = forwardRef<HTMLInputElement, { value: string; onChange: (t: string) => void }>(
  function FilterInput({ value, onChange }, ref) {
    return (
      <label className="og-search">
        <Icon name="search" size={14} />
        <input
          ref={ref}
          type="search"
          value={value}
          placeholder="Search file names…"
          aria-label="Search file names"
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
    );
  },
);

export function Header(
  p: HeaderProps & { searchRef: React.Ref<HTMLInputElement> },
) {
  const sizeLabel = `${p.view === "list" ? "Row" : p.view === "detail" ? "Filmstrip" : "Thumbnail"} size`;
  return (
    <div className="og-header">
      <div className="og-bar og-bar-main">
        <div className="og-seg" role="group" aria-label="Media type">
          {(["photos", "videos"] as const).map((k) => (
            <button
              key={k}
              type="button"
              aria-pressed={p.kind === k}
              className={p.kind === k ? "on" : ""}
              onClick={() => p.onKind(k)}
            >
              <Icon name={k === "photos" ? "detail" : "video"} size={14} />
              {k === "photos" ? "Photos" : "Videos"}
            </button>
          ))}
        </div>
        <div className="og-seg" role="group" aria-label="View">
          {VIEW_BUTTONS.map((b) => (
            <button
              key={b.view}
              type="button"
              aria-pressed={p.view === b.view}
              className={p.view === b.view ? "on" : ""}
              onClick={() => p.onView(b.view)}
            >
              <Icon name={b.icon} size={14} />
              <span className="og-seg-text">{b.label}</span>
            </button>
          ))}
        </div>
        <label className="og-size">
          <span className="og-size-label">{sizeLabel}</span>
          <input
            type="range"
            min={THUMB_MIN}
            max={THUMB_MAX}
            step={5}
            value={p.thumb}
            aria-label={sizeLabel}
            onChange={(e) => p.onThumb(Number(e.target.value))}
          />
          <span className="og-size-value">{p.thumb}%</span>
        </label>
        <span className="og-grow" />
        <button
          type="button"
          className={"og-toggle" + (p.autoRefresh ? " on" : "")}
          aria-pressed={p.autoRefresh}
          onClick={() => p.onAutoRefresh(!p.autoRefresh)}
          title="Check the backend for new outputs every few seconds"
        >
          <span className="og-dot" />
          <span className="og-toggle-label">Auto-refresh:</span> {p.autoRefresh ? "On" : "Off"}
        </button>
        <button
          type="button"
          className={"og-iconbtn" + (p.refreshing ? " spin" : "")}
          aria-label="Refresh now"
          title="Refresh now"
          onClick={p.onRefresh}
        >
          <Icon name="refresh" size={18} />
        </button>
        <button
          type="button"
          className="og-iconbtn"
          aria-label={p.fullscreen ? "Exit full screen" : "Full screen"}
          title={p.fullscreen ? "Exit full screen (Esc)" : "Full screen (F)"}
          onClick={p.onFullscreen}
        >
          <Icon name={p.fullscreen ? "exitFullscreen" : "fullscreen"} size={18} />
        </button>
      </div>
      <div className="og-bar og-bar-filter">
        <FilterInput ref={p.searchRef} value={p.text} onChange={p.onText} />
        <Select label="Source" value={p.source} onChange={(v) => p.onSource(v as SourceFilter)} options={SOURCE_LABELS} />
        <Select label="Date" value={p.range} onChange={(v) => p.onRange(v as DateRange)} options={RANGE_LABELS} />
        <Select label="Sort" value={p.sort} onChange={(v) => p.onSort(v as SortKey)} options={SORT_LABELS} />
        <span className="og-count" role="status">
          {p.shown === p.total ? `${p.total}` : `${p.shown} of ${p.total}`}{" "}
          {p.kind}
        </span>
      </div>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: Record<string, string>;
}) {
  return (
    <label className="og-select">
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
        {Object.entries(options).map(([k, v]) => (
          <option key={k} value={k}>
            {v}
          </option>
        ))}
      </select>
      <Icon name="chevron" size={14} />
    </label>
  );
}

export interface SelectionBarProps {
  count: number;
  bytes: number;
  total: number;
  allChecked: boolean;
  onToggleAll: () => void;
  onClear: () => void;
  onDownloadSelected: () => void;
  onDownloadAll: () => void;
  onArchive: () => void;
  busy: boolean;
  progress: { done: number; total: number } | null;
  onCancel: () => void;
  note: string;
}

export function SelectionBar(p: SelectionBarProps) {
  return (
    <div className="og-selbar" role="toolbar" aria-label="Selection">
      <button
        type="button"
        className="og-btn"
        disabled={!p.total}
        onClick={p.onToggleAll}
      >
        <Icon name="check" size={14} />
        {p.allChecked ? "Unselect all" : "Select all"}
      </button>
      <span className="og-selcount" role="status">
        {p.count
          ? `${p.count} selected · ${formatSize(p.bytes)}`
          : "Nothing selected"}
      </span>
      {p.count > 0 && (
        <button type="button" className="og-btn quiet" onClick={p.onClear}>
          <Icon name="close" size={12} /> Clear
        </button>
      )}
      <span className="og-grow" />
      {p.progress ? (
        <>
          <progress max={p.progress.total} value={p.progress.done} />
          <span className="og-selcount">
            Preparing {p.progress.done}/{p.progress.total}
          </span>
          <button type="button" className="og-btn" onClick={p.onCancel}>
            Cancel
          </button>
        </>
      ) : (
        <>
          {p.note && <span className="og-note">{p.note}</span>}
          <button
            type="button"
            className="og-btn primary"
            disabled={!p.count || p.busy}
            onClick={p.onDownloadSelected}
          >
            <Icon name="download" size={14} /> Download selected (ZIP)
          </button>
          <button
            type="button"
            className="og-btn"
            disabled={!p.total || p.busy}
            onClick={p.onDownloadAll}
            title="Backend ZIP of every output of this type"
          >
            <Icon name="archive" size={14} />
            <span className="og-btn-text">Download all</span>
          </button>
          <button
            type="button"
            className="og-btn"
            disabled={!p.total || p.busy}
            onClick={p.onArchive}
            title="Create a ZIP that stays on the backend for Taildrop or later download"
          >
            <Icon name="drive" size={14} />
            <span className="og-btn-text">Create archive</span>
          </button>
        </>
      )}
    </div>
  );
}
