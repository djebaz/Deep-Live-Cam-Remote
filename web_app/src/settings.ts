export type Values = Record<string, string | number | boolean>;
export type Kind = "photos" | "videos";
export const root = "/content/drive/MyDrive/DeepLiveCamRemote";
export const shared: Values = {
  recursive: true,
  overwrite: false,
  skip_processed: true,
  many_faces: false,
  enhancer: "none",
  opacity: 1,
  sharpness: 0,
  mouth_mask_size: 0,
  interpolation_weight: 0,
  poisson_blend: false,
  color_correction: false,
};
export const photoDefaults: Values = {
  ...shared,
  output_max_width: 0,
  quality: 95,
  detector_size: 640,
  face_model_pack: "buffalo_l",
  swapper_precision: "fp32",
};
export const videoDefaults: Values = {
  ...shared,
  max_fps: 30,
  max_width: 420,
  quality: 18,
  start_pct: 0,
  end_pct: 100,
};
export const liveDefaults: Values = {
  ...shared,
  max_width: 420,
  frame_codec: "jpeg",
  output_codec: "jpeg",
  jpeg_quality: 80,
  detector_size: 320,
  detect_every_n: 1,
  face_model_pack: "buffalo_l",
  swapper_precision: "fp32",
  cache_source_face: true,
  capture_mode: "auto",
  capture_width: 1280,
  capture_height: 720,
  capture_scale: "auto",
  fps: 30,
  pipeline_frames: 16,
  transport_batch_size: 1,
  preview_buffer_seconds: 1,
  preview_scale: "fit",
  camera: "",
};
export interface Preferences {
  gateway: string;
  host: string;
  port: number;
  drive_root: string;
  source_face: string;
  photos_input: string;
  photos_output: string;
  videos_input: string;
  videos_output: string;
  photos: Values;
  videos: Values;
  live: Values;
  output: Values;
}
export const defaults: Preferences = {
  gateway: "",
  host: "",
  port: 7860,
  drive_root: root,
  source_face: "/content/inputs/source/source.png",
  photos_input: "/content/inputs/photos",
  photos_output: "/content/outputs/photos",
  videos_input: "/content/inputs/videos",
  videos_output: "/content/outputs/videos",
  photos: photoDefaults,
  videos: videoDefaults,
  live: liveDefaults,
  output: {
    kind: "photos",
    view: "grid",
    thumb: 100,
    sort: "newest",
    autorefresh: true,
    autoplay: false,
    seconds: 3.5,
    prefetch: 10,
  },
};
export function restore(): Preferences {
  try {
    const v = JSON.parse(localStorage.getItem("dlcr.web.v1") || "{}");
    return {
      ...defaults,
      ...v,
      photos: { ...photoDefaults, ...v.photos },
      videos: { ...videoDefaults, ...v.videos },
      live: { ...liveDefaults, ...v.live },
      output: { ...defaults.output, ...v.output },
    };
  } catch {
    return structuredClone(defaults);
  }
}
export const HOT = new Set([
  "many_faces",
  "opacity",
  "sharpness",
  "mouth_mask_size",
  "interpolation_weight",
  "poisson_blend",
  "color_correction",
  "max_width",
  "frame_codec",
  "output_codec",
  "jpeg_quality",
  "detector_size",
  "detect_every_n",
]);
export const LOCAL_HOT = new Set([
  "capture_scale",
  "pipeline_frames",
  "transport_batch_size",
  "preview_buffer_seconds",
  "preview_scale",
]);
export interface Control {
  key: string;
  label: string;
  min?: number;
  max?: number;
  step?: number;
  choices?: string[];
  hint?: string;
}
export const commonControls: Control[] = [
  { key: "recursive", label: "Recursive folders" },
  { key: "overwrite", label: "Overwrite outputs" },
  { key: "skip_processed", label: "Skip processed" },
  { key: "many_faces", label: "Many faces" },
  {
    key: "enhancer",
    label: "Enhancer",
    choices: ["none", "gfpgan", "gpen256", "gpen512"],
  },
  { key: "opacity", label: "Opacity", min: 0, max: 1, step: 0.1 },
  { key: "sharpness", label: "Sharpness", min: 0, max: 1, step: 0.1 },
  { key: "mouth_mask_size", label: "Mouth mask", min: 0, max: 10, step: 0.5 },
  {
    key: "interpolation_weight",
    label: "Interpolation",
    min: 0,
    max: 1,
    step: 0.1,
  },
  { key: "poisson_blend", label: "Poisson blend" },
  { key: "color_correction", label: "Color correction" },
];
export const photoControls: Control[] = [
  {
    key: "output_max_width",
    label: "Max output width",
    min: 0,
    max: 8192,
    hint: "0 preserves original dimensions",
  },
  {
    key: "quality",
    label: "Image quality",
    min: 1,
    max: 100,
    hint: "JPEG / WebP only; PNG and BMP are lossless",
  },
  {
    key: "detector_size",
    label: "Detector size",
    min: 160,
    max: 1280,
    step: 32,
  },
  {
    key: "face_model_pack",
    label: "InsightFace pack",
    choices: ["buffalo_l", "buffalo_m", "buffalo_s"],
  },
  {
    key: "swapper_precision",
    label: "Swapper precision",
    choices: ["fp32", "fp16"],
    hint: "buffalo_l / fp32 is the baseline; others are experimental",
  },
];
export const videoControls: Control[] = [
  { key: "start_pct", label: "Start %", min: 0, max: 99, step: 0.1 },
  { key: "end_pct", label: "End %", min: 1, max: 100, step: 0.1 },
  { key: "max_fps", label: "Max FPS", min: 1, max: 120, step: 0.1 },
  { key: "max_width", label: "Max width", min: 64, max: 4096 },
  {
    key: "quality",
    label: "Encoder quality",
    min: 0,
    max: 51,
    hint: "Lower values produce higher quality",
  },
];
export const liveControls: Control[] = [
  {
    key: "capture_mode",
    label: "Capture size mode",
    choices: ["auto", "custom"],
    hint: "Auto lets the browser negotiate; OBS profile reading requires native access",
  },
  {
    key: "capture_width",
    label: "Requested width",
    min: 2,
    max: 4096,
    step: 2,
  },
  {
    key: "capture_height",
    label: "Requested height",
    min: 2,
    max: 4096,
    step: 2,
  },
  { key: "fps", label: "Requested FPS", min: 1, max: 120 },
  {
    key: "capture_scale",
    label: "Send scale",
    choices: [
      "auto",
      "100%",
      "95%",
      "90%",
      "80%",
      "75%",
      "70%",
      "50%",
      "30%",
      "25%",
    ],
  },
  { key: "pipeline_frames", label: "Pipeline frames", min: 8, max: 512 },
  {
    key: "transport_batch_size",
    label: "Transport batch size",
    min: 1,
    max: 32,
    hint: "Maximum frames per packet; 4 MiB / 50 ms flush limits",
  },
  ...commonControls.filter(
    (x) => !["recursive", "overwrite", "skip_processed"].includes(x.key),
  ),
  { key: "max_width", label: "Process width", min: 64, max: 4096 },
  { key: "frame_codec", label: "Send codec", choices: ["jpeg", "webp"] },
  { key: "output_codec", label: "Return codec", choices: ["jpeg", "webp"] },
  { key: "jpeg_quality", label: "Frame quality", min: 20, max: 95 },
  {
    key: "detector_size",
    label: "Detector size",
    min: 160,
    max: 640,
    step: 32,
  },
  { key: "detect_every_n", label: "Detect every N frames", min: 1, max: 30 },
  ...photoControls.filter((x) =>
    ["face_model_pack", "swapper_precision"].includes(x.key),
  ),
  { key: "cache_source_face", label: "Cache source face" },
  {
    key: "preview_buffer_seconds",
    label: "Preview buffer (s)",
    min: 0,
    max: 5,
    step: 0.25,
    hint: "Adds playback delay; does not increase processing throughput",
  },
  {
    key: "preview_scale",
    label: "Preview scale",
    choices: ["fit", "1x", "1.5x", "2x"],
  },
];
export function jobPayload(
  p: Preferences,
  kind: Kind,
  source: string,
  input: string,
) {
  const options = { ...p[kind] };
  if (kind === "photos" && Number(options.output_max_width) === 0)
    delete options.output_max_width;
  return {
    ...options,
    source_face: source,
    input_dir: input,
    output_dir: p[`${kind}_output`],
  };
}
