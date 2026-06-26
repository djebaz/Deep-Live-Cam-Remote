from __future__ import annotations

from typing import Any

from windows_app.settings import AppSettings

DEFAULT_LIVE_WIDTH = 1280
DEFAULT_LIVE_HEIGHT = 720
DEFAULT_LIVE_CAPTURE_BACKEND = "directshow"
LIVE_CAPTURE_BACKENDS = ("auto", "directshow", "msmf")
DEFAULT_LIVE_CAPTURE_MODE = "custom"
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
DEFAULT_LIVE_CAPTURE_WIDTH = DEFAULT_LIVE_WIDTH
DEFAULT_LIVE_CAPTURE_HEIGHT = DEFAULT_LIVE_HEIGHT
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


def _live_setting(settings: AppSettings, name: str, default: int) -> int:
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        value = default
    return max(1, value)


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


def _coerce_live_options(value: object) -> dict[str, Any]:
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


def _live_options(settings: AppSettings) -> dict[str, Any]:
    return _coerce_live_options(getattr(settings, "live_options", None))


def _apply_live_options_to_settings(settings: AppSettings) -> None:
    options = _live_options(settings)
    settings.live_options = options
    for key in LIVE_OPTION_KEYS:
        if key != "jpeg_quality":
            setattr(settings, key, options[key])
    settings.live_jpeg_quality = options["jpeg_quality"]

