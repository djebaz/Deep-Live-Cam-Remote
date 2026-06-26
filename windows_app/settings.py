from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_DRIVE_ROOT = "/content/drive/MyDrive/DeepLiveCamRemote"
APP_STATE = Path.home() / ".deep_live_cam_remote_windows_app.json"
REMOTE_PREFIXES = ("/content/", "/drive/")
PHOTO_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}

PROCESSING_OPTION_KEYS = (
    "recursive",
    "overwrite",
    "skip_processed",
    "many_faces",
    "enhancer",
    "opacity",
    "sharpness",
    "mouth_mask_size",
    "interpolation_weight",
    "poisson_blend",
    "color_correction",
)

DEFAULT_LIVE_WIDTH = 1280
DEFAULT_LIVE_HEIGHT = 720
DEFAULT_LIVE_CAPTURE_BACKEND = "directshow"
LIVE_CAPTURE_BACKENDS = ("auto", "directshow", "msmf")
DEFAULT_LIVE_CAPTURE_MODE = "auto"
LIVE_CAPTURE_MODES = ("auto", "custom")
DEFAULT_LIVE_CAPTURE_SCALE = "auto"
LIVE_CAPTURE_SCALES = ("auto", "1x", "3/4x", "2/3x", "1/2x", "1/3x", "1/4x")
LIVE_CAPTURE_SCALE_FACTORS = {
    "auto": None,
    "1x": 1.0,
    "3/4x": 3 / 4,
    "2/3x": 2 / 3,
    "1/2x": 1 / 2,
    "1/3x": 1 / 3,
    "1/4x": 1 / 4,
}
DEFAULT_LIVE_CAPTURE_WIDTH = 640
DEFAULT_LIVE_CAPTURE_HEIGHT = 360
DEFAULT_LIVE_FPS = 30
DEFAULT_LIVE_PIPELINE_FRAMES = 16
DEFAULT_LIVE_JPEG_QUALITY = 80
DEFAULT_LIVE_FRAME_CODEC = "jpeg"
DEFAULT_LIVE_OUTPUT_CODEC = "jpeg"
LIVE_FRAME_CODECS = ("jpeg", "webp")
DEFAULT_LIVE_DETECTOR_SIZE = 320
DEFAULT_LIVE_DETECT_EVERY_N = 1
DEFAULT_LIVE_FACE_MODEL_PACK = "buffalo_l"
LIVE_FACE_MODEL_PACKS = ("buffalo_l", "buffalo_m", "buffalo_s")
DEFAULT_LIVE_SWAPPER_PRECISION = "fp32"
LIVE_SWAPPER_PRECISIONS = ("fp32", "fp16")
DEFAULT_LIVE_PREVIEW_BUFFER_SECONDS = 1.0
DEFAULT_LIVE_PREVIEW_SCALE = "fit"
LIVE_PREVIEW_SCALES = ("fit", "1x", "1.5x", "2x")
LIVE_OPTION_KEYS = (
    "many_faces",
    "enhancer",
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
    "capture_backend",
    "capture_mode",
    "capture_scale",
    "capture_width",
    "capture_height",
    "face_model_pack",
    "swapper_precision",
    "cache_source_face",
    "preview_buffer_seconds",
    "preview_scale",
)


@dataclass
class AppSettings:
    host: str = ""
    port: int = 7860
    drive_root: str = DEFAULT_DRIVE_ROOT
    source_face: str = DEFAULT_DRIVE_ROOT + "/source/source.png"
    photos_input: str = DEFAULT_DRIVE_ROOT + "/photos"
    photos_output: str = DEFAULT_DRIVE_ROOT + "/outputs/photos"
    videos_input: str = DEFAULT_DRIVE_ROOT + "/videos"
    videos_output: str = DEFAULT_DRIVE_ROOT + "/outputs/videos"
    recursive: bool = True
    overwrite: bool = False
    skip_processed: bool = True
    many_faces: bool = False
    enhancer: str = "none"
    opacity: float = 1.0
    sharpness: float = 0.0
    mouth_mask_size: float = 0.0
    interpolation_weight: float = 0.0
    poisson_blend: bool = False
    color_correction: bool = False
    max_fps: float = 30.0
    max_width: int = 420
    quality: int = 18
    photo_max_width: int = 0
    photo_quality: int = 95
    photo_detector_size: int = 640
    photo_face_model_pack: str = DEFAULT_LIVE_FACE_MODEL_PACK
    photo_swapper_precision: str = DEFAULT_LIVE_SWAPPER_PRECISION
    start_pct: float = 0.0
    end_pct: float = 100.0
    camera_index: int = 0
    virtual_camera: str = "OBS Virtual Camera"

    @property
    def base_url(self) -> str:
        host = self.host.replace("http://", "").replace("https://", "").strip().strip("/")
        return f"http://{host}:{self.port}"


def _read_state() -> dict[str, Any]:
    if not APP_STATE.is_file():
        return {}
    try:
        loaded = json.loads(APP_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _app_settings_kwargs(data: dict[str, Any]) -> dict[str, Any]:
    defaults = asdict(AppSettings())
    valid_fields = set(AppSettings.__dataclass_fields__)
    return {key: data.get(key, defaults[key]) for key in valid_fields if key in defaults}


def default_processing_options() -> dict[str, Any]:
    defaults = AppSettings()
    return {key: getattr(defaults, key) for key in PROCESSING_OPTION_KEYS}


def legacy_processing_options(data: dict[str, Any] | None = None) -> dict[str, Any]:
    options = default_processing_options()
    if data:
        for key in PROCESSING_OPTION_KEYS:
            if key in data:
                options[key] = data[key]
    return options


def coerce_processing_options(value: object, fallback: dict[str, Any]) -> dict[str, Any]:
    options = dict(fallback)
    if isinstance(value, dict):
        for key in PROCESSING_OPTION_KEYS:
            if key in value:
                options[key] = value[key]
    return options


def settings_options(settings: AppSettings, kind: str) -> dict[str, Any]:
    return coerce_processing_options(
        getattr(settings, f"{kind}_options", None),
        legacy_processing_options(asdict(settings)),
    )


def apply_processing_options_to_settings(settings: AppSettings, kind: str) -> None:
    for key, value in settings_options(settings, kind).items():
        setattr(settings, key, value)


def _default_live_options() -> dict[str, Any]:
    defaults = AppSettings()
    return {
        "many_faces": False,
        "enhancer": "none",
        "opacity": 1.0,
        "sharpness": 0.0,
        "mouth_mask_size": 0.0,
        "interpolation_weight": 0.0,
        "poisson_blend": False,
        "color_correction": False,
        "max_width": defaults.max_width,
        "frame_codec": DEFAULT_LIVE_FRAME_CODEC,
        "output_codec": DEFAULT_LIVE_OUTPUT_CODEC,
        "jpeg_quality": DEFAULT_LIVE_JPEG_QUALITY,
        "detector_size": DEFAULT_LIVE_DETECTOR_SIZE,
        "detect_every_n": DEFAULT_LIVE_DETECT_EVERY_N,
        "capture_backend": DEFAULT_LIVE_CAPTURE_BACKEND,
        "capture_mode": DEFAULT_LIVE_CAPTURE_MODE,
        "capture_scale": DEFAULT_LIVE_CAPTURE_SCALE,
        "capture_width": DEFAULT_LIVE_CAPTURE_WIDTH,
        "capture_height": DEFAULT_LIVE_CAPTURE_HEIGHT,
        "face_model_pack": DEFAULT_LIVE_FACE_MODEL_PACK,
        "swapper_precision": DEFAULT_LIVE_SWAPPER_PRECISION,
        "cache_source_face": True,
        "preview_buffer_seconds": DEFAULT_LIVE_PREVIEW_BUFFER_SECONDS,
        "preview_scale": DEFAULT_LIVE_PREVIEW_SCALE,
    }


def coerce_live_options(value: object) -> dict[str, Any]:
    options = _default_live_options()
    if isinstance(value, dict):
        for key in LIVE_OPTION_KEYS:
            if key in value:
                options[key] = value[key]
    options["many_faces"] = bool(options["many_faces"])
    options["enhancer"] = str(options["enhancer"])
    options["opacity"] = float(options["opacity"])
    options["sharpness"] = float(options["sharpness"])
    options["mouth_mask_size"] = float(options["mouth_mask_size"])
    options["interpolation_weight"] = float(options["interpolation_weight"])
    options["poisson_blend"] = bool(options["poisson_blend"])
    options["color_correction"] = bool(options["color_correction"])
    options["max_width"] = max(64, int(options["max_width"]))
    options["frame_codec"] = str(options["frame_codec"]).lower()
    if options["frame_codec"] not in LIVE_FRAME_CODECS:
        options["frame_codec"] = DEFAULT_LIVE_FRAME_CODEC
    options["output_codec"] = str(options["output_codec"]).lower()
    if options["output_codec"] not in LIVE_FRAME_CODECS:
        options["output_codec"] = DEFAULT_LIVE_OUTPUT_CODEC
    options["jpeg_quality"] = max(20, min(95, int(options["jpeg_quality"])))
    options["detector_size"] = max(160, min(640, int(options["detector_size"])))
    options["detector_size"] = max(32, int(options["detector_size"]) // 32 * 32)
    options["detect_every_n"] = max(1, min(30, int(options["detect_every_n"])))
    options["capture_backend"] = str(options["capture_backend"]).lower()
    if options["capture_backend"] not in LIVE_CAPTURE_BACKENDS:
        options["capture_backend"] = DEFAULT_LIVE_CAPTURE_BACKEND
    options["capture_mode"] = str(options["capture_mode"]).lower()
    if options["capture_mode"] not in LIVE_CAPTURE_MODES:
        options["capture_mode"] = DEFAULT_LIVE_CAPTURE_MODE
    options["capture_scale"] = str(options["capture_scale"]).lower()
    if options["capture_scale"] not in LIVE_CAPTURE_SCALES:
        options["capture_scale"] = DEFAULT_LIVE_CAPTURE_SCALE
    options["capture_width"] = max(2, min(4096, int(options["capture_width"])))
    options["capture_height"] = max(2, min(4096, int(options["capture_height"])))
    options["face_model_pack"] = str(options["face_model_pack"])
    if options["face_model_pack"] not in LIVE_FACE_MODEL_PACKS:
        options["face_model_pack"] = DEFAULT_LIVE_FACE_MODEL_PACK
    options["cache_source_face"] = bool(options["cache_source_face"])
    options["preview_buffer_seconds"] = max(0.0, min(5.0, float(options["preview_buffer_seconds"])))
    options["preview_scale"] = str(options["preview_scale"]).lower()
    if options["preview_scale"] not in LIVE_PREVIEW_SCALES:
        options["preview_scale"] = DEFAULT_LIVE_PREVIEW_SCALE
    options["swapper_precision"] = str(options["swapper_precision"]).lower()
    if options["swapper_precision"] not in LIVE_SWAPPER_PRECISIONS:
        options["swapper_precision"] = DEFAULT_LIVE_SWAPPER_PRECISION
    return options


def live_options(settings: AppSettings) -> dict[str, Any]:
    return coerce_live_options(getattr(settings, "live_options", None))


def live_setting(settings: AppSettings, name: str, default: int) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(1, value)


def load_settings() -> AppSettings:
    data = _read_state()
    settings = AppSettings(**_app_settings_kwargs(data))

    legacy = legacy_processing_options(data)
    settings.photos_options = coerce_processing_options(data.get("photos_options"), legacy)
    settings.videos_options = coerce_processing_options(data.get("videos_options"), legacy)
    apply_processing_options_to_settings(settings, "photos")

    settings.live_width = int(data.get("live_width") or DEFAULT_LIVE_WIDTH)
    settings.live_height = int(data.get("live_height") or DEFAULT_LIVE_HEIGHT)
    settings.live_fps = int(data.get("live_fps") or DEFAULT_LIVE_FPS)
    settings.live_pipeline_frames = int(data.get("live_pipeline_frames") or DEFAULT_LIVE_PIPELINE_FRAMES)
    settings.live_options = coerce_live_options(data.get("live_options"))
    return settings


def save_settings(settings: AppSettings) -> None:
    data = asdict(settings)
    legacy = legacy_processing_options(data)
    data["photos_options"] = coerce_processing_options(getattr(settings, "photos_options", None), legacy)
    data["videos_options"] = coerce_processing_options(getattr(settings, "videos_options", None), legacy)
    data["live_width"] = live_setting(settings, "live_width", DEFAULT_LIVE_WIDTH)
    data["live_height"] = live_setting(settings, "live_height", DEFAULT_LIVE_HEIGHT)
    data["live_fps"] = live_setting(settings, "live_fps", DEFAULT_LIVE_FPS)
    data["live_pipeline_frames"] = live_setting(settings, "live_pipeline_frames", DEFAULT_LIVE_PIPELINE_FRAMES)
    data["live_options"] = live_options(settings)
    APP_STATE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
