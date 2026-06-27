from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import math
import mimetypes
import queue
import struct
import subprocess
import threading
import time
import uuid
import zipfile
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

import colab_batch

DRIVE_ROOT = Path("/content/drive/MyDrive/DeepLiveCamRemote")
SOURCE_DIR = DRIVE_ROOT / "source"
PHOTOS_DIR = DRIVE_ROOT / "photos"
VIDEOS_DIR = DRIVE_ROOT / "videos"
OUTPUT_PHOTOS_DIR = DRIVE_ROOT / "outputs" / "photos"
OUTPUT_VIDEOS_DIR = DRIVE_ROOT / "outputs" / "videos"

LOCAL_ROOT = Path("/content/inputs")
LOCAL_SOURCE_DIR = LOCAL_ROOT / "source"
LOCAL_PHOTOS_DIR = LOCAL_ROOT / "photos"
LOCAL_VIDEOS_DIR = LOCAL_ROOT / "videos"
LOCAL_OUTPUT_PHOTOS_DIR = Path("/content/outputs/photos")
LOCAL_OUTPUT_VIDEOS_DIR = Path("/content/outputs/videos")
ZIP_OUTPUT_DIR = Path("/content/outputs/downloads")
ARCHIVE_DIR = Path("/content/archive")

OUTPUT_IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".webp"}
OUTPUT_VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}
API_VERSION = "live-output-packet-v14"
LIVE_TRANSPORT_PACKET_MAGIC = b"DLCR"
LIVE_TRANSPORT_PACKET_VERSION = 1
LIVE_TRANSPORT_PACKET_HEADER = struct.Struct("!4sHH")
LIVE_TRANSPORT_FRAME_HEADER = struct.Struct("!II")
LIVE_PENDING_FRAME_QUEUE_LIMIT = 8
LIVE_FACE_MODEL_PACKS = {"buffalo_l", "buffalo_m", "buffalo_s"}
LIVE_SWAPPER_PRECISIONS = {"fp32", "fp16"}
LIVE_FRAME_CODECS = {"jpeg", "webp"}
LIVE_HOT_CHANGE_KEYS = {
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
    "frame_quality",
    "detector_size",
    "detect_every_n",
}
LIVE_GEOMETRY_LOG_KEYS = {
    "max_width",
    "detector_size",
    "detect_every_n",
    "frame_codec",
    "output_codec",
}


def bool_config(config: dict[str, Any], name: str, default: bool) -> bool:
    value = config.get(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


class JobRequest(BaseModel):
    source_face: str = Field(default=str(SOURCE_DIR / "source.png"))
    input_dir: str | None = None
    output_dir: str | None = None
    recursive: bool = True
    overwrite: bool = False
    skip_processed: bool = True
    many_faces: bool = False
    enhancer: str = "none"
    opacity: float = 1.0
    sharpness: float = 0.0
    mouth_mask_size: float = 0.0
    poisson_blend: bool = False
    color_correction: bool = False
    interpolation_weight: float = 0.0
    max_fps: float = 30.0
    max_width: int = 420
    output_max_width: int | None = None
    quality: int = 18
    encoder: str = "auto"
    start_pct: float = 0.0
    end_pct: float = 100.0


class CancelRequest(BaseModel):
    job_id: str


class CreateZipResponse(BaseModel):
    zip_path: str
    zip_id: str
    size_bytes: int
    timestamp: str
    tailscale_hostname: str | None


@dataclass
class JobState:
    job_id: str
    kind: str
    status: str = "queued"
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    exit_code: int | None = None
    error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    log_queue: "queue.Queue[str]" = field(default_factory=queue.Queue)
    logs: list[str] = field(default_factory=list)

    def append(self, text: str) -> None:
        if not text:
            return
        for line in text.splitlines():
            entry = line.rstrip()
            self.logs.append(entry)
            self.log_queue.put(entry)

    def snapshot(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "error": self.error,
            "logs": self.logs[-300:],
        }


class JobWriter(io.TextIOBase):
    def __init__(self, job: JobState):
        self.job = job
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self.job.append(line)
        return len(text)

    def flush(self) -> None:
        if self._buffer:
            self.job.append(self._buffer)
            self._buffer = ""


JOBS: dict[str, JobState] = {}
CREATED_ARCHIVES: dict[str, Path] = {}
ENGINE_LOCK = threading.Lock()
app = FastAPI(title="Deep-Live-Cam Remote API", version="1.0")


def ensure_drive_layout() -> dict[str, str]:
    for path in (SOURCE_DIR, PHOTOS_DIR, VIDEOS_DIR, OUTPUT_PHOTOS_DIR, OUTPUT_VIDEOS_DIR):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "drive_root": str(DRIVE_ROOT),
        "source_dir": str(SOURCE_DIR),
        "photos_dir": str(PHOTOS_DIR),
        "videos_dir": str(VIDEOS_DIR),
        "output_photos_dir": str(OUTPUT_PHOTOS_DIR),
        "output_videos_dir": str(OUTPUT_VIDEOS_DIR),
    }


def ensure_local_layout() -> dict[str, str]:
    for path in (LOCAL_SOURCE_DIR, LOCAL_PHOTOS_DIR, LOCAL_VIDEOS_DIR, LOCAL_OUTPUT_PHOTOS_DIR, LOCAL_OUTPUT_VIDEOS_DIR):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "source_dir": str(LOCAL_SOURCE_DIR),
        "photos_dir": str(LOCAL_PHOTOS_DIR),
        "videos_dir": str(LOCAL_VIDEOS_DIR),
        "output_photos_dir": str(LOCAL_OUTPUT_PHOTOS_DIR),
        "output_videos_dir": str(LOCAL_OUTPUT_VIDEOS_DIR),
    }


def safe_upload_name(filename: str | None, fallback: str) -> str:
    name = Path(filename or fallback).name
    return name or fallback


def safe_batch_id(batch_id: str | None) -> str | None:
    if not batch_id:
        return None
    normalized = "".join(char for char in batch_id if char.isalnum() or char in {"-", "_"})
    if not normalized:
        raise HTTPException(status_code=400, detail="invalid batch_id")
    return normalized[:80]


def batch_upload_dir(base_dir: Path, batch_id: str | None) -> Path:
    normalized = safe_batch_id(batch_id)
    if not normalized:
        return base_dir
    destination = base_dir / "batches" / normalized
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def upload_destination(kind: str, filename: str | None) -> tuple[Path, dict[str, str]]:
    paths = ensure_local_layout()
    normalized_kind = kind.lower()
    if normalized_kind == "source":
        return LOCAL_SOURCE_DIR / safe_upload_name(filename, "source.png"), paths
    if normalized_kind in {"photo", "photos"}:
        return LOCAL_PHOTOS_DIR / safe_upload_name(filename, "photo.jpg"), paths
    if normalized_kind in {"video", "videos"}:
        return LOCAL_VIDEOS_DIR / safe_upload_name(filename, "video.mp4"), paths
    raise ValueError(f"unknown upload kind: {kind}")


def output_roots(kind: str) -> tuple[list[tuple[str, Path]], set[str]]:
    normalized = kind.lower()
    if normalized == "photos":
        return [("drive", OUTPUT_PHOTOS_DIR), ("local", LOCAL_OUTPUT_PHOTOS_DIR)], OUTPUT_IMAGE_EXTENSIONS
    if normalized == "videos":
        return [("drive", OUTPUT_VIDEOS_DIR), ("local", LOCAL_OUTPUT_VIDEOS_DIR)], OUTPUT_VIDEO_EXTENSIONS
    raise HTTPException(status_code=404, detail=f"unknown output kind: {kind}")


def output_root(kind: str, source: str) -> tuple[Path, set[str]]:
    roots, extensions = output_roots(kind)
    for root_source, root in roots:
        if root_source == source:
            return root, extensions
    raise HTTPException(status_code=404, detail=f"unknown output source: {source}")


def output_file_entries(kind: str) -> list[dict[str, Any]]:
    ensure_drive_layout()
    ensure_local_layout()
    roots, extensions = output_roots(kind)
    files: list[dict[str, Any]] = []
    for source, root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in extensions:
                continue
            stat = path.stat()
            relative_path = path.relative_to(root).as_posix()
            files.append({
                "name": path.name,
                "relative_path": relative_path,
                "source": source,
                "path": path,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "download_path": f"/outputs/{kind}/file/{source}/{relative_path}",
            })
    files.sort(key=lambda item: (item["modified"], item["name"]), reverse=True)
    return files


def safe_output_path(kind: str, source: str, relative_path: str) -> Path:
    root, extensions = output_root(kind, source)
    candidate = (root / relative_path).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise HTTPException(status_code=400, detail="invalid output path")
    if candidate.suffix.lower() not in extensions:
        raise HTTPException(status_code=400, detail="unsupported output file type")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="output file not found")
    return candidate


def remove_file(path: str) -> None:
    Path(path).unlink(missing_ok=True)


def get_tailscale_hostname() -> str | None:
    """Returns Tailscale hostname if tailscale CLI available and connected."""
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
        if result.returncode == 0:
            status_data = json.loads(result.stdout)
            return status_data.get("Self", {}).get("HostName")
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return None


async def write_upload(file: UploadFile, dest: Path) -> int:
    content = await file.read()
    dest.write_bytes(content)
    return len(content)


def bool_arg(name: str, value: bool) -> list[str]:
    return [f"--{name}" if value else f"--no-{name}"]


def common_args(request: JobRequest, input_default: Path, output_default: Path) -> list[str]:
    args = [
        "--source-face", request.source_face,
        "--input-dir", request.input_dir or str(input_default),
        "--output-dir", request.output_dir or str(output_default),
        *bool_arg("recursive", request.recursive),
        *bool_arg("overwrite", request.overwrite),
        *bool_arg("skip-processed", request.skip_processed),
        *bool_arg("many-faces", request.many_faces),
        "--opacity", str(request.opacity),
        "--sharpness", str(request.sharpness),
        "--mouth-mask-size", str(request.mouth_mask_size),
        "--interpolation-weight", str(request.interpolation_weight),
        "--enhancer", request.enhancer,
    ]
    if request.poisson_blend:
        args.append("--poisson-blend")
    if request.color_correction:
        args.append("--color-correction")
    return args


def run_job(job: JobState, argv: list[str]) -> None:
    job.status = "running"
    writer = JobWriter(job)
    try:
        with ENGINE_LOCK:
            parser = colab_batch.build_parser()
            args = parser.parse_args(argv)
            args.cancel_event = job.cancel_event
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                job.exit_code = args.func(args)
        job.status = "cancelled" if job.cancel_event.is_set() else ("completed" if job.exit_code == 0 else "failed")
    except BaseException as exc:
        job.error = str(exc)
        job.status = "cancelled" if job.cancel_event.is_set() else "failed"
        job.append(f"ERROR: {exc}")
    finally:
        writer.flush()
        job.finished_at = time.time()


def start_job(kind: str, argv: list[str]) -> JobState:
    job = JobState(job_id=uuid.uuid4().hex, kind=kind)
    JOBS[job.job_id] = job
    threading.Thread(target=run_job, args=(job, argv), daemon=True).start()
    return job


def int_config(config: dict[str, Any], name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(config.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def float_config(config: dict[str, Any], name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(config.get(name, default))
    except (TypeError, ValueError):
        value = default
    if not math.isfinite(value):
        value = default
    return max(minimum, min(maximum, value))


def strict_float_config(config: dict[str, Any], name: str, minimum: float, maximum: float) -> float:
    if name not in config:
        raise ValueError(f"{name} is required")
    try:
        value = float(config[name])
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number") from None
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return value


def strict_int_config(config: dict[str, Any], name: str, minimum: int, maximum: int, step: int | None = None) -> int:
    if name not in config:
        raise ValueError(f"{name} is required")
    raw = config[name]
    if isinstance(raw, bool):
        raise ValueError(f"{name} must be an integer")
    if isinstance(raw, float) and not raw.is_integer():
        raise ValueError(f"{name} must be an integer")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer") from None
    if isinstance(raw, str) and raw.strip() != str(value):
        raise ValueError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    if step and value % step != 0:
        raise ValueError(f"{name} must be a multiple of {step}")
    return value


def live_processing_geometry(frame: np.ndarray, config: dict[str, Any]) -> tuple[int, int]:
    height, width = frame.shape[:2]
    configured = config.get("max_width")
    try:
        max_width = int(configured) if configured else width
    except (TypeError, ValueError):
        max_width = width
    max_width = max(2, min(width, max_width))
    process_width, process_height, _fps = colab_batch.processing_geometry(width, height, 30.0, max_width, 30.0)
    return process_width, process_height


def live_detection_size(config: dict[str, Any]) -> int:
    detector_size = int_config(config, "detector_size", 320, 160, 640)
    return max(32, detector_size // 32 * 32)


def live_jpeg_quality(config: dict[str, Any]) -> int:
    return int_config(config, "jpeg_quality", 80, 20, 95)


def live_frame_codec(config: dict[str, Any]) -> str:
    codec = str(config.get("frame_codec") or "jpeg").lower()
    if codec not in LIVE_FRAME_CODECS:
        return "jpeg"
    return codec


def live_output_codec(config: dict[str, Any]) -> str:
    codec = str(config.get("output_codec") or live_frame_codec(config)).lower()
    if codec not in LIVE_FRAME_CODECS:
        return "jpeg"
    return codec


def live_encode_frame(frame: np.ndarray, config: dict[str, Any]) -> tuple[bool, Any, str]:
    quality = live_jpeg_quality(config)
    requested = live_output_codec(config)
    if requested == "webp":
        try:
            ok, encoded = cv2.imencode(".webp", frame, [int(getattr(cv2, "IMWRITE_WEBP_QUALITY", cv2.IMWRITE_JPEG_QUALITY)), quality])
        except Exception:
            ok, encoded = False, None
        if ok:
            return True, encoded, "webp"
    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return bool(ok), encoded, "jpeg"


def pack_live_frame_packet(frames: list[tuple[dict[str, Any], bytes]]) -> bytes:
    packet = bytearray()
    packet.extend(LIVE_TRANSPORT_PACKET_HEADER.pack(LIVE_TRANSPORT_PACKET_MAGIC, LIVE_TRANSPORT_PACKET_VERSION, len(frames)))
    for header, payload in frames:
        header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
        packet.extend(LIVE_TRANSPORT_FRAME_HEADER.pack(len(header_bytes), len(payload)))
        packet.extend(header_bytes)
        packet.extend(payload)
    return bytes(packet)


def unpack_live_frame_packet(payload: bytes, fallback_meta: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], float]:
    unpack_started = time.monotonic()
    if not payload.startswith(LIVE_TRANSPORT_PACKET_MAGIC):
        return [
            {
                "payload": payload,
                "meta": dict(fallback_meta or {}),
            }
        ], (time.monotonic() - unpack_started) * 1000.0
    if len(payload) < LIVE_TRANSPORT_PACKET_HEADER.size:
        raise ValueError("live frame packet is truncated")
    magic, version, frame_count = LIVE_TRANSPORT_PACKET_HEADER.unpack_from(payload, 0)
    if magic != LIVE_TRANSPORT_PACKET_MAGIC:
        raise ValueError("invalid live frame packet magic")
    if version != LIVE_TRANSPORT_PACKET_VERSION:
        raise ValueError(f"unsupported live frame packet version {version}")
    offset = LIVE_TRANSPORT_PACKET_HEADER.size
    frames: list[dict[str, Any]] = []
    for _index in range(frame_count):
        if offset + LIVE_TRANSPORT_FRAME_HEADER.size > len(payload):
            raise ValueError("live frame packet frame header is truncated")
        header_len, payload_len = LIVE_TRANSPORT_FRAME_HEADER.unpack_from(payload, offset)
        offset += LIVE_TRANSPORT_FRAME_HEADER.size
        if header_len < 0 or payload_len < 0 or offset + header_len + payload_len > len(payload):
            raise ValueError("live frame packet has invalid frame lengths")
        header_bytes = payload[offset: offset + header_len]
        offset += header_len
        frame_payload = payload[offset: offset + payload_len]
        offset += payload_len
        try:
            header = json.loads(header_bytes.decode("utf-8")) if header_bytes else {}
        except Exception as exc:
            raise ValueError(f"invalid live frame packet header: {exc}") from None
        if not isinstance(header, dict):
            raise ValueError("live frame packet header must be an object")
        frames.append({"payload": frame_payload, "meta": header})
    if offset != len(payload):
        raise ValueError("live frame packet has trailing bytes")
    return frames, (time.monotonic() - unpack_started) * 1000.0


def live_face_model_pack(config: dict[str, Any]) -> str:
    model_pack = str(config.get("face_model_pack") or "buffalo_l")
    if model_pack not in LIVE_FACE_MODEL_PACKS:
        return "buffalo_l"
    return model_pack


def live_swapper_precision(config: dict[str, Any]) -> str:
    precision = str(config.get("swapper_precision") or "fp32").lower()
    if precision not in LIVE_SWAPPER_PRECISIONS:
        return "fp32"
    return precision


def live_swapper_diagnostics(engine: colab_batch.ModernEngine) -> dict[str, str]:
    diagnostics = {}
    getter = getattr(engine.swapper, "get_face_swapper_diagnostics", None)
    if callable(getter):
        loaded = getter()
        if isinstance(loaded, dict):
            diagnostics.update({str(key): str(value) for key, value in loaded.items()})
    diagnostics.setdefault("requested_precision", live_swapper_precision({}))
    diagnostics.setdefault("loaded_precision", "")
    diagnostics.setdefault("model_path", "")
    return diagnostics


def live_hot_change_config(current: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    unknown = set(update) - LIVE_HOT_CHANGE_KEYS
    if unknown:
        raise ValueError(f"restart required for: {', '.join(sorted(unknown))}")
    merged = dict(current)
    if "many_faces" in update:
        merged["many_faces"] = bool_config(update, "many_faces", bool(current.get("many_faces", False)))
    for name, default, minimum, maximum in (
        ("opacity", 1.0, 0.0, 1.0),
        ("sharpness", 0.0, 0.0, 1.0),
        ("mouth_mask_size", 0.0, 0.0, 10.0),
        ("interpolation_weight", 0.0, 0.0, 1.0),
    ):
        if name in update:
            merged[name] = strict_float_config(update, name, minimum, maximum)
    for name in ("poisson_blend", "color_correction"):
        if name in update:
            merged[name] = bool_config(update, name, bool(current.get(name, False)))
    if "max_width" in update:
        merged["max_width"] = strict_int_config(update, "max_width", 64, 4096)
    for name in ("frame_codec", "output_codec"):
        if name in update:
            codec = str(update.get(name) or "jpeg").lower()
            if codec not in LIVE_FRAME_CODECS:
                raise ValueError(f"unsupported {name}: {codec}")
            merged[name] = codec
    quality_key = "jpeg_quality" if "jpeg_quality" in update else "frame_quality"
    if quality_key in update:
        merged["jpeg_quality"] = strict_int_config(update, quality_key, 20, 95)
        merged["frame_quality"] = merged["jpeg_quality"]
    if "detector_size" in update:
        merged["detector_size"] = strict_int_config(update, "detector_size", 160, 640, step=32)
    if "detect_every_n" in update:
        merged["detect_every_n"] = strict_int_config(update, "detect_every_n", 1, 30)
    return merged


def apply_live_hot_change(engine: colab_batch.ModernEngine, current: dict[str, Any], update: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    next_config = live_hot_change_config(current, update)
    detection_keys = {"many_faces", "detector_size", "detect_every_n"}
    if any(next_config.get(key) != current.get(key) for key in detection_keys):
        state.clear()
        if hasattr(engine.swapper, "FACE_DETECTION_CACHE"):
            engine.swapper.FACE_DETECTION_CACHE.clear()
    engine.globals.many_faces = bool(next_config.get("many_faces", False)) and not engine.mapping
    engine.globals.opacity = float(next_config.get("opacity", 1.0))
    engine.globals.sharpness = float(next_config.get("sharpness", 0.0))
    engine.globals.mouth_mask_size = float(next_config.get("mouth_mask_size", 0.0))
    engine.globals.mouth_mask = engine.globals.mouth_mask_size > 0
    engine.globals.poisson_blend = bool(next_config.get("poisson_blend", False))
    engine.globals.color_correction = bool(next_config.get("color_correction", False))
    interpolation_weight = float(next_config.get("interpolation_weight", 0.0))
    engine.globals.enable_interpolation = 0 < interpolation_weight < 1
    engine.globals.interpolation_weight = interpolation_weight
    return next_config


def live_detect_faces(frame: np.ndarray, many_faces: bool, detector_size: int) -> Any:
    from insightface.app.common import Face
    from modules.face_analyser import get_face_analyser

    fa = get_face_analyser()
    input_size = (detector_size, detector_size)
    max_num = 0 if many_faces else 1
    bboxes, kpss = fa.det_model.detect(frame, input_size=input_size, max_num=max_num, metric="default")
    if bboxes.shape[0] == 0:
        return [] if many_faces else None
    faces = [Face(bbox=bboxes[i, :4], kps=kpss[i], det_score=bboxes[i, 4]) for i in range(bboxes.shape[0])]
    if many_faces:
        return faces
    return min(faces, key=lambda face: face.bbox[0])


def live_process_frame(engine: colab_batch.ModernEngine, frame: np.ndarray, config: dict[str, Any], state: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    timings: dict[str, Any] = {
        "detect": 0.0,
        "landmarks": 0.0,
        "swap": 0.0,
        "source_refresh": 0.0,
        "face_swap": 0.0,
        "post": 0.0,
        "enhance": 0.0,
        "detect_reused": False,
        "faces": 0,
    }
    if engine.mapping:
        started = time.monotonic()
        return engine.process(frame, "live"), {**timings, "swap": time.monotonic() - started}

    detector_size = live_detection_size(config)
    detect_every_n = int_config(config, "detect_every_n", 1, 1, 30)
    many_faces = bool(engine.globals.many_faces)
    needs_landmarks = bool(engine.enhancer) or bool(getattr(engine.globals, "mouth_mask", False))
    frame_index = int(state.get("frame_index", 0))
    cache_key = "many_faces" if many_faces else "single_face"
    should_detect = frame_index % detect_every_n == 0 or state.get(cache_key) is None
    state["frame_index"] = frame_index + 1

    detect_started = time.monotonic()
    if should_detect:
        detected = live_detect_faces(frame, many_faces, detector_size)
        state[cache_key] = detected
    else:
        detected = state.get(cache_key)
        timings["detect_reused"] = True
    timings["detect"] = time.monotonic() - detect_started

    landmark_started = time.monotonic()
    if needs_landmarks:
        from modules.face_analyser import ensure_landmarks
        ensure_landmarks(frame, detected)
    timings["landmarks"] = time.monotonic() - landmark_started

    if getattr(engine.globals, "opacity", 1.0) == 0:
        if hasattr(engine.swapper, "PREVIOUS_FRAME_RESULT"):
            engine.swapper.PREVIOUS_FRAME_RESULT = None
        return frame, timings

    swap_started = time.monotonic()
    if not getattr(engine, "cache_source_face", True):
        source_refresh_started = time.monotonic()
        engine.refresh_default_source()
        timings["source_refresh"] += time.monotonic() - source_refresh_started
    bboxes = []
    if many_faces:
        faces = detected or []
        output = frame.copy()
        for face in faces:
            face_swap_started = time.monotonic()
            output = engine.swapper.swap_face(engine.default_source, face, output)
            timings["face_swap"] += time.monotonic() - face_swap_started
            if face is not None and hasattr(face, "bbox") and face.bbox is not None:
                bboxes.append(face.bbox.astype(int))
        detected_for_enhancer = faces
    else:
        face = detected
        output = frame
        if face is not None:
            face_swap_started = time.monotonic()
            output = engine.swapper.swap_face(engine.default_source, face, output)
            timings["face_swap"] += time.monotonic() - face_swap_started
            if hasattr(face, "bbox") and face.bbox is not None:
                bboxes.append(face.bbox.astype(int))
        detected_for_enhancer = [face] if face is not None else []
    timings["swap"] = time.monotonic() - swap_started
    timings["faces"] = len(detected_for_enhancer)

    post_started = time.monotonic()
    output = engine.swapper.apply_post_processing(output, bboxes)
    timings["post"] = time.monotonic() - post_started

    enhance_started = time.monotonic()
    if engine.enhancer:
        output = engine.enhancer.process_frame(None, output, detected_faces=detected_for_enhancer)
    timings["enhance"] = time.monotonic() - enhance_started
    return output, timings


@app.get("/health")
def health() -> dict[str, Any]:
    paths = ensure_drive_layout()
    return {
        "ok": True,
        "api_version": API_VERSION,
        "paths": paths,
        "local_paths": ensure_local_layout(),
        "active_jobs": [job.snapshot() for job in JOBS.values() if job.status in {"queued", "running"}],
    }


@app.get("/outputs/{kind}")
def list_outputs(kind: str) -> dict[str, Any]:
    files = output_file_entries(kind)
    public_files = [{key: value for key, value in item.items() if key != "path"} for item in files]
    return {"ok": True, "kind": kind, "count": len(public_files), "files": public_files}


@app.get("/outputs/{kind}/zip")
def get_output_zip(kind: str) -> FileResponse:
    files = output_file_entries(kind)
    if not files:
        raise HTTPException(status_code=404, detail=f"no {kind} outputs found")
    ZIP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = ZIP_OUTPUT_DIR / f"{kind}_outputs_{uuid.uuid4().hex}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for item in files:
            archive.write(item["path"], f"{item['source']}/{item['relative_path']}")
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{kind}_outputs.zip",
        background=BackgroundTask(remove_file, str(zip_path)),
    )


@app.post("/outputs/{kind}/create-zip")
def create_output_zip(kind: str) -> CreateZipResponse:
    """
    Creates a zip archive of outputs in /content/archive/ for Taildrop or HTTP download.
    Does NOT auto-cleanup (user manages retention).
    """
    files = output_file_entries(kind)
    if not files:
        raise HTTPException(status_code=404, detail=f"no {kind} outputs found")

    # Create archive directory
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # Generate timestamped filename
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    zip_id = uuid.uuid4().hex
    zip_filename = f"{kind}_outputs_{timestamp}.zip"
    zip_path = ARCHIVE_DIR / zip_filename

    # Create ZIP
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for item in files:
            archive.write(item["path"], f"{item['source']}/{item['relative_path']}")

    # Store for HTTP fallback
    CREATED_ARCHIVES[zip_id] = zip_path

    # Get Tailscale info
    tailscale_hostname = get_tailscale_hostname()

    return CreateZipResponse(
        zip_path=str(zip_path),
        zip_id=zip_id,
        size_bytes=zip_path.stat().st_size,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        tailscale_hostname=tailscale_hostname,
    )


@app.get("/download-archive/{archive_id}")
def download_archive(archive_id: str) -> FileResponse:
    """
    HTTP fallback download for archives created via /create-zip.
    Used when Taildrop transfer fails.
    """
    zip_path = CREATED_ARCHIVES.get(archive_id)
    if not zip_path or not zip_path.is_file():
        raise HTTPException(status_code=404, detail="archive not found or expired")

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=zip_path.name,
    )


@app.get("/outputs/{kind}/file/{source}/{relative_path:path}")
def get_output_file(kind: str, source: str, relative_path: str) -> FileResponse:
    path = safe_output_path(kind, source, relative_path)
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=path.name)


@app.post("/upload/file")
async def upload_file(kind: str = "photos", file: UploadFile = File(...)) -> dict[str, Any]:
    dest, paths = upload_destination(kind, file.filename)
    size = await write_upload(file, dest)
    response = {"ok": True, "kind": kind, "path": str(dest), "size": size}
    if kind.lower() in {"photo", "photos"}:
        response.update({"input_dir": paths["photos_dir"], "output_dir": paths["output_photos_dir"]})
    elif kind.lower() in {"video", "videos"}:
        response.update({"input_dir": paths["videos_dir"], "output_dir": paths["output_videos_dir"]})
    return response


@app.post("/upload/source")
async def upload_source(file: UploadFile = File(...)) -> dict[str, Any]:
    dest, _ = upload_destination("source", file.filename)
    size = await write_upload(file, dest)
    return {"ok": True, "path": str(dest), "size": size}


@app.post("/upload/photos")
async def upload_photos(files: list[UploadFile] = File(...), batch_id: str | None = None) -> dict[str, Any]:
    paths = ensure_local_layout()
    upload_dir = batch_upload_dir(LOCAL_PHOTOS_DIR, batch_id)
    uploaded = []
    for file in files:
        dest = upload_dir / safe_upload_name(file.filename, f"photo_{len(uploaded)}.jpg")
        size = await write_upload(file, dest)
        uploaded.append({"path": str(dest), "size": size})
    return {"ok": True, "count": len(uploaded), "files": uploaded, "input_dir": str(upload_dir), "output_dir": paths["output_photos_dir"], "batch_id": safe_batch_id(batch_id)}


@app.post("/upload/videos")
async def upload_videos(files: list[UploadFile] = File(...), batch_id: str | None = None) -> dict[str, Any]:
    paths = ensure_local_layout()
    upload_dir = batch_upload_dir(LOCAL_VIDEOS_DIR, batch_id)
    uploaded = []
    for file in files:
        dest = upload_dir / safe_upload_name(file.filename, f"video_{len(uploaded)}.mp4")
        size = await write_upload(file, dest)
        uploaded.append({"path": str(dest), "size": size})
    return {"ok": True, "count": len(uploaded), "files": uploaded, "input_dir": str(upload_dir), "output_dir": paths["output_videos_dir"], "batch_id": safe_batch_id(batch_id)}


@app.delete("/upload/clear")
def clear_uploads() -> dict[str, Any]:
    cleared = []
    for directory in (LOCAL_SOURCE_DIR, LOCAL_PHOTOS_DIR, LOCAL_VIDEOS_DIR, LOCAL_OUTPUT_PHOTOS_DIR, LOCAL_OUTPUT_VIDEOS_DIR):
        if directory.exists():
            for path in directory.iterdir():
                if path.is_file():
                    path.unlink()
                    cleared.append(str(path))
    return {"ok": True, "cleared": len(cleared)}


@app.post("/jobs/photos")
def start_photos(request: JobRequest) -> dict[str, Any]:
    ensure_drive_layout()
    argv = ["photos", *common_args(request, PHOTOS_DIR, OUTPUT_PHOTOS_DIR)]
    if request.output_max_width is not None:
        argv.extend(["--output-max-width", str(request.output_max_width)])
    job = start_job("photos", argv)
    return {"job_id": job.job_id, "status": job.status}


@app.post("/jobs/videos")
def start_videos(request: JobRequest) -> dict[str, Any]:
    ensure_drive_layout()
    argv = [
        "process",
        *common_args(request, VIDEOS_DIR, OUTPUT_VIDEOS_DIR),
        "--max-fps", str(request.max_fps),
        "--max-width", str(request.max_width),
        "--quality", str(request.quality),
        "--encoder", request.encoder,
        "--start-pct", str(request.start_pct),
        "--end-pct", str(request.end_pct),
    ]
    job = start_job("videos", argv)
    return {"job_id": job.job_id, "status": job.status}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = JOBS.get(job_id)
    if job is None:
        return {"error": "unknown job", "job_id": job_id}
    return job.snapshot()


@app.post("/jobs/cancel")
def cancel_job(request: CancelRequest) -> dict[str, Any]:
    job = JOBS.get(request.job_id)
    if job is None:
        return {"error": "unknown job", "job_id": request.job_id}
    job.cancel_event.set()
    job.append("cancel requested")
    return {"job_id": job.job_id, "status": job.status, "cancel_requested": True}


@app.websocket("/ws/jobs/{job_id}")
async def job_socket(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    job = JOBS.get(job_id)
    if job is None:
        await websocket.send_json({"error": "unknown job", "job_id": job_id})
        await websocket.close()
        return
    await websocket.send_json(job.snapshot())
    try:
        while True:
            try:
                line = job.log_queue.get_nowait()
                await websocket.send_json({"job_id": job_id, "log": line, "status": job.status})
            except queue.Empty:
                await websocket.send_json({"job_id": job_id, "status": job.status})
                if job.status not in {"queued", "running"}:
                    break
                await asyncio.sleep(1.0)
    finally:
        await websocket.close()


@app.websocket("/ws/live")
async def live_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        config_payload = await websocket.receive_text()
        config = json.loads(config_payload)
        process_config = colab_batch.ProcessConfig(
            input_dir=PHOTOS_DIR,
            output_dir=OUTPUT_PHOTOS_DIR,
            source_face=Path(config.get("source_face") or SOURCE_DIR / "source.png"),
            map_config=None,
            many_faces=bool(config.get("many_faces", False)),
            opacity=float_config(config, "opacity", 1.0, 0.0, 1.0),
            sharpness=float_config(config, "sharpness", 0.0, 0.0, 1.0),
            mouth_mask_size=float_config(config, "mouth_mask_size", 0.0, 0.0, 10.0),
            poisson_blend=bool(config.get("poisson_blend", False)),
            color_correction=bool(config.get("color_correction", False)),
            interpolation_weight=float_config(config, "interpolation_weight", 0.0, 0.0, 1.0),
            enhancer=config.get("enhancer", "none"),
            face_model_pack=live_face_model_pack(config),
            swapper_precision=live_swapper_precision(config),
            cache_source_face=bool_config(config, "cache_source_face", True),
        )
        with ENGINE_LOCK:
            engine = colab_batch.ModernEngine(process_config)
    except Exception as exc:
        await websocket.send_json({"error": f"live init failed: {exc}"})
        await websocket.close(code=1011)
        return

    swapper_diagnostics = live_swapper_diagnostics(engine)
    await websocket.send_json({
        "status": "ready",
        "api_version": API_VERSION,
        "live_fast_detection": True,
        "detector_size": live_detection_size(config),
        "detect_every_n": int_config(config, "detect_every_n", 1, 1, 30),
        "face_model_pack": live_face_model_pack(config),
        "swapper_precision": live_swapper_precision(config),
        "swapper_loaded_precision": swapper_diagnostics.get("loaded_precision", ""),
        "swapper_model_path": swapper_diagnostics.get("model_path", ""),
        "source_embedding_cached": engine.default_source is not None and engine.cache_source_face,
        "cache_source_face": engine.cache_source_face,
        "frame_codec": live_frame_codec(config),
        "output_codec": live_output_codec(config),
        "frame_quality": live_jpeg_quality(config),
        "jpeg_quality": live_jpeg_quality(config),
    })
    geometry_logged = False
    live_state: dict[str, Any] = {}
    perf_started = time.monotonic()
    perf_frames = 0
    perf_wait = 0.0
    perf_decode = 0.0
    perf_resize = 0.0
    perf_process = 0.0
    perf_detect = 0.0
    perf_landmarks = 0.0
    perf_swap = 0.0
    perf_source_refresh = 0.0
    perf_face_swap = 0.0
    perf_post = 0.0
    perf_enhance = 0.0
    perf_detect_reused = 0
    perf_faces = 0
    perf_encode = 0.0
    perf_in_bytes = 0
    perf_out_bytes = 0
    perf_server_queue = 0.0
    perf_client_to_server = 0.0
    perf_capture_to_server = 0.0
    perf_receive_to_send = 0.0
    perf_decode_to_process = 0.0
    perf_process_to_encode = 0.0
    perf_transport_unpack = 0.0
    perf_transport_batch_frames = 0
    perf_transport_batch_bytes = 0
    perf_transport_messages = 0
    perf_reader_receive = 0.0
    perf_reader_messages = 0
    perf_drop_ack_send = 0.0
    perf_drop_ack_messages = 0
    perf_pending_queue_depth = 0
    perf_pending_queue_samples = 0
    perf_frames_with_send_time = 0
    perf_frames_with_capture_time = 0
    perf_dropped_before_process = 0
    latest_drop_count = 0
    processed_drop_cursor = 0
    pending_frames: deque[dict[str, Any]] = deque()
    pending_frame_meta: dict[str, Any] | None = None
    reader_done = False
    reader_error: BaseException | None = None
    latest_condition = asyncio.Condition()
    send_lock = asyncio.Lock()

    async def locked_send_json(payload: dict[str, Any]) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    async def locked_send_bytes(payload: bytes) -> None:
        async with send_lock:
            await websocket.send_bytes(payload)

    async def receive_latest_frames() -> None:
        nonlocal config, geometry_logged, latest_drop_count
        nonlocal pending_frame_meta, reader_done, reader_error
        nonlocal perf_transport_unpack, perf_transport_batch_frames, perf_transport_batch_bytes, perf_transport_messages
        nonlocal perf_reader_receive, perf_reader_messages, perf_drop_ack_send, perf_drop_ack_messages
        nonlocal perf_pending_queue_depth, perf_pending_queue_samples
        try:
            while True:
                receive_started = time.monotonic()
                message = await websocket.receive()
                perf_reader_receive += time.monotonic() - receive_started
                perf_reader_messages += 1
                if message.get("type") == "websocket.disconnect":
                    reader_done = True
                    async with latest_condition:
                        latest_condition.notify_all()
                    return

                text_payload = message.get("text")
                if text_payload is not None:
                    try:
                        control = json.loads(text_payload)
                        if not isinstance(control, dict):
                            raise ValueError("unknown live control message")
                        control_type = control.get("type")
                        if control_type == "live_frame_meta":
                            pending_frame_meta = control
                        elif control_type == "live_config_update":
                            update = control.get("config")
                            if not isinstance(update, dict):
                                raise ValueError("live_config_update requires config object")
                            with ENGINE_LOCK:
                                config = apply_live_hot_change(engine, config, update, live_state)
                            if LIVE_GEOMETRY_LOG_KEYS.intersection(update):
                                geometry_logged = False
                            await locked_send_json({
                                "status": "live_config_updated",
                                "detector_size": live_detection_size(config),
                                "detect_every_n": int_config(config, "detect_every_n", 1, 1, 30),
                                "frame_codec": live_frame_codec(config),
                                "output_codec": live_output_codec(config),
                                "frame_quality": live_jpeg_quality(config),
                                "jpeg_quality": live_jpeg_quality(config),
                                "many_faces": bool(config.get("many_faces", False)),
                            })
                        else:
                            raise ValueError("unknown live control message")
                    except Exception as exc:
                        await locked_send_json({"status": "live_config_update_rejected", "message": str(exc)})
                    continue

                payload = message.get("bytes")
                if payload is None:
                    await locked_send_json({"error": "invalid live websocket message"})
                    continue

                received_at = time.monotonic()
                receive_wall_time = time.time()
                meta = pending_frame_meta if isinstance(pending_frame_meta, dict) else {}
                pending_frame_meta = None
                try:
                    frame_packets, transport_unpack_ms = unpack_live_frame_packet(payload, meta)
                except Exception as exc:
                    await locked_send_json({"error": f"invalid live frame packet: {exc}"})
                    continue
                perf_transport_unpack += transport_unpack_ms / 1000.0
                perf_transport_batch_frames += len(frame_packets)
                perf_transport_batch_bytes += len(payload)
                perf_transport_messages += 1
                dropped_count = 0
                last_dropped_seq: Any = ""
                async with latest_condition:
                    for frame_packet in frame_packets:
                        while len(pending_frames) >= LIVE_PENDING_FRAME_QUEUE_LIMIT:
                            dropped_frame = pending_frames.popleft()
                            latest_drop_count += 1
                            dropped_count += 1
                            dropped_meta = dropped_frame.get("meta") or {}
                            last_dropped_seq = dropped_meta.get("seq", "")
                        pending_frames.append({
                            "payload": frame_packet["payload"],
                            "meta": dict(frame_packet.get("meta") or {}),
                            "received_at": received_at,
                            "receive_wall_time": receive_wall_time,
                            "drop_count": latest_drop_count,
                        })
                    perf_pending_queue_depth += len(pending_frames)
                    perf_pending_queue_samples += 1
                    latest_condition.notify_all()
                if dropped_count:
                    drop_ack_started = time.monotonic()
                    await locked_send_json({
                        "status": "live_frame_dropped",
                        "dropped": dropped_count,
                        "frame_seq": last_dropped_seq,
                        "latest_drop_count": latest_drop_count,
                    })
                    perf_drop_ack_send += time.monotonic() - drop_ack_started
                    perf_drop_ack_messages += 1
        except BaseException as exc:
            reader_error = exc
            reader_done = True
            async with latest_condition:
                latest_condition.notify_all()

    reader_task = asyncio.create_task(receive_latest_frames())
    try:
        while True:
            frame_wait_started = time.monotonic()
            async with latest_condition:
                while not pending_frames and not reader_done:
                    await latest_condition.wait()
                if not pending_frames:
                    if reader_error is not None:
                        raise reader_error
                    return
                frame_item = pending_frames.popleft()
            frame_started = time.monotonic()
            payload = frame_item["payload"]
            metadata = frame_item.get("meta") or {}
            received_at = float(frame_item["received_at"])
            receive_wall_time = float(frame_item.get("receive_wall_time") or 0.0)
            frames_dropped_before_process = max(0, int(frame_item.get("drop_count") or 0) - processed_drop_cursor)
            processed_drop_cursor = int(frame_item.get("drop_count") or processed_drop_cursor)
            server_queue_ms = max(0.0, (frame_started - received_at) * 1000.0)
            client_send_time = metadata.get("send_time")
            client_capture_time = metadata.get("capture_time")
            client_to_server_ms = None
            capture_to_server_ms = None
            if isinstance(client_send_time, (int, float)) and receive_wall_time:
                client_to_server_ms = max(0.0, (receive_wall_time - float(client_send_time)) * 1000.0)
            if isinstance(client_capture_time, (int, float)) and receive_wall_time:
                capture_to_server_ms = max(0.0, (receive_wall_time - float(client_capture_time)) * 1000.0)
            array = np.frombuffer(payload, dtype=np.uint8)
            frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
            decoded_at = time.monotonic()
            if frame is None:
                await locked_send_json({"error": "invalid frame"})
                continue
            frame_height, frame_width = frame.shape[:2]
            process_width, process_height = live_processing_geometry(frame, config)
            if (process_width, process_height) == (frame_width, frame_height):
                process_frame = frame
            else:
                interpolation = cv2.INTER_AREA if process_width < frame_width or process_height < frame_height else cv2.INTER_LINEAR
                process_frame = cv2.resize(frame, (process_width, process_height), interpolation=interpolation)
            resized_at = time.monotonic()
            if not geometry_logged:
                await locked_send_json({
                    "status": "live_geometry",
                    "api_version": API_VERSION,
                    "input": f"{frame_width}x{frame_height}",
                    "processing": f"{process_width}x{process_height}",
                    "detector_size": live_detection_size(config),
                    "detect_every_n": int_config(config, "detect_every_n", 1, 1, 30),
                    "face_model_pack": live_face_model_pack(config),
                    "swapper_precision": live_swapper_precision(config),
                    "swapper_loaded_precision": live_swapper_diagnostics(engine).get("loaded_precision", ""),
                    "cache_source_face": getattr(engine, "cache_source_face", True),
                    "frame_codec": live_frame_codec(config),
                    "output_codec": live_output_codec(config),
                    "frame_quality": live_jpeg_quality(config),
                    "jpeg_quality": live_jpeg_quality(config),
                })
                geometry_logged = True
            try:
                with ENGINE_LOCK:
                    output, frame_timings = live_process_frame(engine, process_frame.copy(), config, live_state)
                processed_at = time.monotonic()
            except Exception as exc:
                await locked_send_json({"error": f"live frame failed: {exc}"})
                continue
            if output is None:
                output = process_frame
            if output.shape[:2] != (process_height, process_width):
                output = cv2.resize(output, (process_width, process_height), interpolation=cv2.INTER_LINEAR)
            ok, encoded, encoded_codec = live_encode_frame(output, config)
            encoded_at = time.monotonic()
            if ok:
                out_bytes = int(encoded.size)
                sent_at = time.monotonic()
                perf_frames += 1
                perf_wait += frame_started - frame_wait_started
                perf_decode += decoded_at - received_at
                perf_resize += resized_at - decoded_at
                perf_process += processed_at - resized_at
                perf_detect += float(frame_timings.get("detect", 0.0))
                perf_landmarks += float(frame_timings.get("landmarks", 0.0))
                perf_swap += float(frame_timings.get("swap", 0.0))
                perf_source_refresh += float(frame_timings.get("source_refresh", 0.0))
                perf_face_swap += float(frame_timings.get("face_swap", 0.0))
                perf_post += float(frame_timings.get("post", 0.0))
                perf_enhance += float(frame_timings.get("enhance", 0.0))
                perf_detect_reused += 1 if frame_timings.get("detect_reused") else 0
                perf_faces += int(frame_timings.get("faces", 0) or 0)
                perf_encode += encoded_at - processed_at
                perf_in_bytes += len(payload)
                perf_out_bytes += out_bytes
                perf_server_queue += server_queue_ms / 1000.0
                perf_receive_to_send += sent_at - received_at
                perf_decode_to_process += processed_at - decoded_at
                perf_process_to_encode += encoded_at - processed_at
                perf_dropped_before_process += frames_dropped_before_process
                if client_to_server_ms is not None:
                    perf_client_to_server += client_to_server_ms / 1000.0
                    perf_frames_with_send_time += 1
                if capture_to_server_ms is not None:
                    perf_capture_to_server += capture_to_server_ms / 1000.0
                    perf_frames_with_capture_time += 1
                elapsed = encoded_at - perf_started
                if elapsed >= 5.0 and perf_frames:
                    await locked_send_json({
                        "status": "live_perf",
                        "api_version": API_VERSION,
                        "server_fps": round(perf_frames / elapsed, 2),
                        "wait_ms": round((perf_wait / perf_frames) * 1000.0, 1),
                        "decode_ms": round((perf_decode / perf_frames) * 1000.0, 1),
                        "resize_ms": round((perf_resize / perf_frames) * 1000.0, 1),
                        "process_ms": round((perf_process / perf_frames) * 1000.0, 1),
                        "detect_ms": round((perf_detect / perf_frames) * 1000.0, 1),
                        "landmarks_ms": round((perf_landmarks / perf_frames) * 1000.0, 1),
                        "swap_ms": round((perf_swap / perf_frames) * 1000.0, 1),
                        "source_refresh_ms": round((perf_source_refresh / perf_frames) * 1000.0, 1),
                        "face_swap_ms": round((perf_face_swap / perf_frames) * 1000.0, 1),
                        "post_ms": round((perf_post / perf_frames) * 1000.0, 1),
                        "enhance_ms": round((perf_enhance / perf_frames) * 1000.0, 1),
                        "detect_reuse_pct": round((perf_detect_reused / perf_frames) * 100.0, 1),
                        "faces": round(perf_faces / perf_frames, 2),
                        "detector_size": live_detection_size(config),
                        "detect_every_n": int_config(config, "detect_every_n", 1, 1, 30),
                        "face_model_pack": live_face_model_pack(config),
                        "swapper_precision": live_swapper_precision(config),
                        "swapper_loaded_precision": live_swapper_diagnostics(engine).get("loaded_precision", ""),
                        "cache_source_face": getattr(engine, "cache_source_face", True),
                        "frame_codec": live_frame_codec(config),
                        "output_codec": live_output_codec(config),
                        "encoded_codec": encoded_codec,
                        "frame_quality": live_jpeg_quality(config),
                        "jpeg_quality": live_jpeg_quality(config),
                        "encode_ms": round((perf_encode / perf_frames) * 1000.0, 1),
                        "in_kb": round((perf_in_bytes / perf_frames) / 1024.0, 1),
                        "out_kb": round((perf_out_bytes / perf_frames) / 1024.0, 1),
                        "frame_seq": metadata.get("seq", ""),
                        "server_queue_ms": round((perf_server_queue / perf_frames) * 1000.0, 1),
                        "client_to_server_ms": round((perf_client_to_server / max(1, perf_frames_with_send_time)) * 1000.0, 1) if perf_frames_with_send_time else "",
                        "capture_to_server_ms": round((perf_capture_to_server / max(1, perf_frames_with_capture_time)) * 1000.0, 1) if perf_frames_with_capture_time else "",
                        "receive_to_send_ms": round((perf_receive_to_send / perf_frames) * 1000.0, 1),
                        "latest_drop_count": latest_drop_count,
                        "frames_dropped_before_process": perf_dropped_before_process,
                        "server_decode_to_process_ms": round((perf_decode_to_process / perf_frames) * 1000.0, 1),
                        "server_process_to_encode_ms": round((perf_process_to_encode / perf_frames) * 1000.0, 1),
                        "transport_batch_size": round(perf_transport_batch_frames / max(1, perf_transport_messages), 2),
                        "transport_batch_frames": round(perf_transport_batch_frames / max(1, perf_transport_messages), 2),
                        "transport_batch_bytes": round(perf_transport_batch_bytes / max(1, perf_transport_messages), 1),
                        "transport_pack_ms": "",
                        "transport_unpack_ms": round((perf_transport_unpack / max(1, perf_transport_messages)) * 1000.0, 2),
                        "frames_per_ws_message": round(perf_transport_batch_frames / max(1, perf_transport_messages), 2),
                        "reader_receive_ms": round((perf_reader_receive / max(1, perf_reader_messages)) * 1000.0, 2),
                        "drop_ack_send_ms": round((perf_drop_ack_send / max(1, perf_drop_ack_messages)) * 1000.0, 2) if perf_drop_ack_messages else 0.0,
                        "drop_ack_messages": perf_drop_ack_messages,
                        "pending_frame_queue": round(perf_pending_queue_depth / max(1, perf_pending_queue_samples), 2),
                        "pending_frame_queue_limit": LIVE_PENDING_FRAME_QUEUE_LIMIT,
                    })
                    perf_started = encoded_at
                    perf_frames = 0
                    perf_wait = 0.0
                    perf_decode = 0.0
                    perf_resize = 0.0
                    perf_process = 0.0
                    perf_detect = 0.0
                    perf_landmarks = 0.0
                    perf_swap = 0.0
                    perf_source_refresh = 0.0
                    perf_face_swap = 0.0
                    perf_post = 0.0
                    perf_enhance = 0.0
                    perf_detect_reused = 0
                    perf_faces = 0
                    perf_encode = 0.0
                    perf_in_bytes = 0
                    perf_out_bytes = 0
                    perf_server_queue = 0.0
                    perf_client_to_server = 0.0
                    perf_capture_to_server = 0.0
                    perf_receive_to_send = 0.0
                    perf_decode_to_process = 0.0
                    perf_process_to_encode = 0.0
                    perf_transport_unpack = 0.0
                    perf_transport_batch_frames = 0
                    perf_transport_batch_bytes = 0
                    perf_transport_messages = 0
                    perf_reader_receive = 0.0
                    perf_reader_messages = 0
                    perf_drop_ack_send = 0.0
                    perf_drop_ack_messages = 0
                    perf_pending_queue_depth = 0
                    perf_pending_queue_samples = 0
                    perf_frames_with_send_time = 0
                    perf_frames_with_capture_time = 0
                    perf_dropped_before_process = 0
                output_payload = encoded.tobytes()
                output_meta = {
                    "seq": metadata.get("seq", ""),
                    "capture_time": metadata.get("capture_time", ""),
                    "client_send_time": metadata.get("send_time", ""),
                    "server_receive_time": receive_wall_time,
                    "server_send_time": time.time(),
                    "codec": encoded_codec,
                    "width": int(output.shape[1]),
                    "height": int(output.shape[0]),
                    "payload_bytes": len(output_payload),
                }
                await locked_send_bytes(pack_live_frame_packet([(output_meta, output_payload)]))
    except WebSocketDisconnect:
        return
    finally:
        reader_task.cancel()
        await asyncio.gather(reader_task, return_exceptions=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Deep-Live-Cam Remote Colab API server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args(argv)
    import uvicorn
    ensure_drive_layout()
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
