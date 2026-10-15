import type { ReactNode } from "react";

/** One monochrome icon family (24px grid, 1.6 stroke, round caps), after DTFlow. */
const PATHS: Record<string, ReactNode> = {
  grid: (
    <>
      <rect x="3" y="3" width="7.5" height="7.5" rx="1.6" />
      <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.6" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.6" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.6" />
    </>
  ),
  list: (
    <path d="M8.5 6h12.5M8.5 12h12.5M8.5 18h12.5M3.5 6h.01M3.5 12h.01M3.5 18h.01" />
  ),
  detail: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2.4" />
      <circle cx="9" cy="9" r="1.6" />
      <path d="m21 15.5-5-5L5 21" />
    </>
  ),
  video: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2.4" />
      <path d="m10.5 9.5 4 2.5-4 2.5z" />
    </>
  ),
  refresh: <path d="M21 12a9 9 0 1 1-2.64-6.36M21 4v5h-5" />,
  fullscreen: (
    <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3" />
  ),
  exitFullscreen: (
    <path d="M8 3v3a2 2 0 0 1-2 2H3M21 8h-3a2 2 0 0 1-2-2V3M3 16h3a2 2 0 0 1 2 2v3M16 21v-3a2 2 0 0 1 2-2h3" />
  ),
  left: <path d="m15 18-6-6 6-6" />,
  right: <path d="m9 18 6-6-6-6" />,
  download: <path d="M12 3v12m-5-5 5 5 5-5M5 21h14" />,
  archive: (
    <>
      <path d="M3 4h18v4H3zM5 8v12h14V8M10 12h4" />
    </>
  ),
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  close: <path d="M18 6 6 18M6 6l12 12" />,
  play: <path d="M7 4.5v15l12.5-7.5z" />,
  pause: <path d="M8 5v14M16 5v14" />,
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </>
  ),
  folder: (
    <path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4l2 2.5h9A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z" />
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2.4" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </>
  ),
  file: (
    <>
      <path d="M6 3h8l5 5v13H6z" />
      <path d="M14 3v5h5" />
    </>
  ),
  drive: (
    <>
      <path d="M3 15h18v5H3z" />
      <path d="M5 15 7.5 5h9L19 15M7 17.5h.01" />
    </>
  ),
  weight: (
    <>
      <path d="M6 20h12l2-11H4z" />
      <path d="M12 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" />
    </>
  ),
  ruler: <path d="M4 16 16 4l4 4L8 20zM8 12l2 2M11 9l2 2M14 6l2 2" />,
  chevron: <path d="m6 9 6 6 6-6" />,
};

export type IconName = keyof typeof PATHS;
export function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return (
    <svg
      className="og-icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
