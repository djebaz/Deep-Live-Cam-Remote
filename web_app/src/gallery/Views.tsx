import { memo } from "react";
import type { Api, Output } from "../api";
import { Icon } from "./icons";
import {
  formatDate,
  formatDuration,
  formatSize,
  outputId,
  sourceLabel,
  type Selection,
  type SortKey,
} from "./model";
import { ThumbMedia, type Meta, type OnMeta } from "./ThumbMedia";
import type { ThumbnailCache } from "./thumbs";

export interface BrowseProps {
  files: Output[];
  kind: "photos" | "videos";
  api: Api;
  cache: ThumbnailCache;
  /** Tile edge in CSS pixels (from the thumbnail-size percentage). */
  size: number;
  selected: Selection;
  meta: Record<string, Meta>;
  onMeta: OnMeta;
  onOpen: (id: string) => void;
  onToggle: (id: string) => void;
}

export function dimensionsText(m?: Meta): string {
  return m?.width && m?.height ? `${m.width} × ${m.height}` : "—";
}

function Check({
  checked,
  label,
  onChange,
}: {
  checked: boolean;
  label: string;
  onChange: () => void;
}) {
  return (
    <label className={"og-check" + (checked ? " on" : "")}>
      <input
        type="checkbox"
        checked={checked}
        aria-label={label}
        onChange={onChange}
        onClick={(e) => e.stopPropagation()}
      />
      <span className="og-checkbox">
        <Icon name="check" size={12} />
      </span>
    </label>
  );
}

interface ItemProps {
  item: Output;
  kind: "photos" | "videos";
  api: Api;
  cache: ThumbnailCache;
  selected: boolean;
  selecting: boolean;
  meta?: Meta;
  onMeta: OnMeta;
  onOpen: (id: string) => void;
  onToggle: (id: string) => void;
}

const Card = memo(function Card(p: ItemProps) {
  const id = outputId(p.item);
  const badge = p.meta?.duration
    ? formatDuration(p.meta.duration)
    : p.meta?.width && p.meta?.height
      ? `${p.meta.width}×${p.meta.height}`
      : "";
  return (
    <div
      role="listitem"
      className={
        "og-card" + (p.selected ? " is-selected" : "") + (p.selecting ? " selecting" : "")
      }
    >
      <button
        type="button"
        className="og-tile"
        onClick={() => p.onOpen(id)}
        aria-label={`Open ${p.item.relative_path}`}
      >
        <ThumbMedia
          item={p.item}
          kind={p.kind}
          api={p.api}
          cache={p.cache}
          onMeta={p.onMeta}
        />
        {badge && <span className="og-badge">{badge}</span>}
      </button>
      <Check
        checked={p.selected}
        label={`Select ${p.item.relative_path}`}
        onChange={() => p.onToggle(id)}
      />
      <span className="og-name" title={p.item.relative_path}>
        {p.item.name}
      </span>
      <span className="og-sub">
        {formatSize(p.item.size)} · {sourceLabel(p.item.source)}
      </span>
    </div>
  );
});

export function GridView(props: BrowseProps) {
  const selecting = props.selected.size > 0;
  return (
    <div
      className="og-grid"
      role="list"
      aria-label={`Output ${props.kind}`}
      style={{
        gridTemplateColumns: `repeat(auto-fill, minmax(${props.size}px, 1fr))`,
      }}
    >
      {props.files.map((f) => (
        <Card
          key={outputId(f)}
          item={f}
          kind={props.kind}
          api={props.api}
          cache={props.cache}
          selected={props.selected.has(outputId(f))}
          selecting={selecting}
          meta={props.meta[outputId(f)]}
          onMeta={props.onMeta}
          onOpen={props.onOpen}
          onToggle={props.onToggle}
        />
      ))}
    </div>
  );
}

const Row = memo(function Row(p: ItemProps & { thumb: number }) {
  const id = outputId(p.item);
  return (
    <div
      role="row"
      className={"og-row" + (p.selected ? " is-selected" : "")}
      onClick={() => p.onOpen(id)}
    >
      <span role="cell" className="og-cell-check">
        <Check
          checked={p.selected}
          label={`Select ${p.item.relative_path}`}
          onChange={() => p.onToggle(id)}
        />
      </span>
      <span role="cell" className="og-cell-thumb">
        <span
          className="og-rowthumb"
          style={{ width: Math.round(p.thumb * 1.4), height: p.thumb }}
        >
          <ThumbMedia
            item={p.item}
            kind={p.kind}
            api={p.api}
            cache={p.cache}
            onMeta={p.onMeta}
          />
        </span>
      </span>
      <span role="cell" className="og-cell-name" title={p.item.relative_path}>
        <button
          type="button"
          className="og-link"
          onClick={(e) => {
            e.stopPropagation();
            p.onOpen(id);
          }}
        >
          {p.item.relative_path}
        </button>
      </span>
      <span role="cell" className="og-cell-source">
        {sourceLabel(p.item.source)}
      </span>
      <span role="cell" className="og-cell-dim">
        {dimensionsText(p.meta)}
        {p.meta?.duration ? ` · ${formatDuration(p.meta.duration)}` : ""}
      </span>
      <span role="cell" className="og-cell-size">
        {formatSize(p.item.size)}
      </span>
      <span role="cell" className="og-cell-date">
        {formatDate(p.item.modified)}
      </span>
    </div>
  );
});

const COLUMNS: { key: string; label: string; asc?: SortKey; desc?: SortKey; cls: string }[] = [
  { key: "name", label: "Filename", asc: "name", desc: "name_desc", cls: "og-cell-name" },
  { key: "source", label: "Source", cls: "og-cell-source" },
  { key: "dim", label: "Dimensions", cls: "og-cell-dim" },
  { key: "size", label: "Size", asc: "smallest", desc: "largest", cls: "og-cell-size" },
  { key: "date", label: "Modified", asc: "oldest", desc: "newest", cls: "og-cell-date" },
];

export function ListView(
  props: BrowseProps & {
    sort: SortKey;
    onSort: (s: SortKey) => void;
    allChecked: boolean;
    onToggleAll: () => void;
  },
) {
  const thumb = Math.max(32, Math.round(props.size / 2.6));
  return (
    <div
      className="og-list"
      role="table"
      aria-label={`Output ${props.kind}`}
      style={{ "--thumb-col": `${Math.round(thumb * 1.4) + 16}px` } as React.CSSProperties}
    >
      <div className="og-row og-head" role="row">
        <span role="columnheader" className="og-cell-check">
          <Check
            checked={props.allChecked}
            label="Select all shown"
            onChange={props.onToggleAll}
          />
        </span>
        <span role="columnheader" className="og-cell-thumb">
          Preview
        </span>
        {COLUMNS.map((c) => (
          <span key={c.key} role="columnheader" className={c.cls}>
            {c.asc && c.desc ? (
              <button
                type="button"
                className="og-sorthead"
                onClick={() =>
                  props.onSort(props.sort === c.asc ? c.desc! : c.asc!)
                }
              >
                {c.label}
                {props.sort === c.asc ? " ▲" : props.sort === c.desc ? " ▼" : ""}
              </button>
            ) : (
              c.label
            )}
          </span>
        ))}
      </div>
      {props.files.map((f) => (
        <Row
          key={outputId(f)}
          item={f}
          kind={props.kind}
          api={props.api}
          cache={props.cache}
          thumb={thumb}
          selected={props.selected.has(outputId(f))}
          selecting={props.selected.size > 0}
          meta={props.meta[outputId(f)]}
          onMeta={props.onMeta}
          onOpen={props.onOpen}
          onToggle={props.onToggle}
        />
      ))}
    </div>
  );
}
