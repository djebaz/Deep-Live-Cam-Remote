from __future__ import annotations

import json
import mimetypes
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from windows_app.settings import AppSettings, PHOTO_EXTENSIONS, REMOTE_PREFIXES, VIDEO_EXTENSIONS


def is_local_path(path: str) -> bool:
    if not path:
        return False
    normalized = path.replace("\\", "/")
    if normalized.startswith(REMOTE_PREFIXES):
        return False
    if len(path) >= 2 and path[1] == ":":
        return True
    if path.startswith("\\\\"):
        return True
    return Path(path).exists()


def local_files(path: str, extensions: set[str], recursive: bool) -> list[Path]:
    root = Path(path)
    if root.is_file():
        return [root] if root.suffix.lower() in extensions else []
    if not root.is_dir():
        raise FileNotFoundError(f"Local input folder does not exist: {path}")
    iterator = root.rglob("*") if recursive else root.glob("*")
    return sorted(p for p in iterator if p.is_file() and p.suffix.lower() in extensions)


def format_size(size: int | None) -> str:
    if size is None:
        return ""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{size} B"


def _http_error_message(exc: urllib.error.HTTPError, method: str, url: str) -> str:
    try:
        raw = exc.read()
    except Exception:
        raw = b""
    body = ""
    if raw:
        try:
            body = raw.decode("utf-8", errors="replace").strip()
        except Exception:
            body = repr(raw[:1000])
    base = f"{method} {url} failed: HTTP {exc.code} {exc.reason}"
    return f"{base}: {body}" if body else base


def _read_json_response(response: Any) -> dict[str, Any]:
    text = response.read().decode("utf-8")
    return json.loads(text) if text else {}


def _open_json(request: urllib.request.Request, timeout: float) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _read_json_response(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_http_error_message(exc, request.get_method(), request.full_url)) from exc


def _open_bytes(url: str, timeout: float) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_http_error_message(exc, "GET", url)) from exc


def check_tailscale_cli() -> bool:
    """Check if tailscale CLI is available on PATH."""
    try:
        subprocess.run(
            ["tailscale", "version"],
            capture_output=True,
            timeout=3.0,
            check=False,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def taildrop_receive_file(remote_host: str, remote_path: str, local_destination: Path) -> tuple[bool, str]:
    """Attempt to receive a file via Tailscale Taildrop."""
    try:
        local_destination.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["tailscale", "file", "cp", f"{remote_host}:{remote_path}", str(local_destination)],
            capture_output=True,
            text=True,
            timeout=600.0,
            check=False,
        )
        if result.returncode == 0:
            return (True, f"Taildrop transfer complete: {local_destination}")
        error_msg = result.stderr.strip() if result.stderr else f"exit code {result.returncode}"
        return (False, f"Taildrop failed: {error_msg}")
    except subprocess.TimeoutExpired:
        return (False, "Taildrop transfer timed out (10 min)")
    except Exception as exc:
        return (False, f"Taildrop error: {exc}")


class ApiClient:
    def __init__(self, settings: AppSettings):
        self.settings = settings

    def url(self, path: str) -> str:
        return self.settings.base_url + urllib.parse.quote(path, safe="/:?=&%")

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url(path),
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        return _open_json(request, timeout)

    def download_bytes(self, path: str, timeout: float = 120.0) -> bytes:
        return _open_bytes(self.url(path), timeout)

    def download_file(self, path: str, destination: Path, timeout: float = 600.0) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        url = self.url(path)
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response, destination.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(_http_error_message(exc, "GET", url)) from exc
        return destination

    def create_zip(self, kind: str, timeout: float = 120.0) -> dict[str, Any]:
        """Call /create-zip endpoint to prepare archive for transfer."""
        return self.request_json("POST", f"/outputs/{kind}/create-zip", timeout=timeout)

    def download_archive(self, archive_id: str, destination: Path, timeout: float = 1800.0) -> Path:
        """HTTP fallback download for pre-created archives."""
        return self.download_file(f"/download-archive/{archive_id}", destination, timeout=timeout)

    def upload_file(
        self,
        endpoint: str,
        file_path: Path,
        field_name: str = "file",
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        boundary = f"----DeepLiveCamBoundary{uuid.uuid4().hex}"
        content_type = f"multipart/form-data; boundary={boundary}"
        mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        file_data = file_path.read_bytes()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field_name}"; filename="{file_path.name}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")
        request = urllib.request.Request(
            self.url(endpoint),
            data=body,
            method="POST",
            headers={"Content-Type": content_type},
        )
        return _open_json(request, timeout)

    def upload_files(
        self,
        endpoint: str,
        file_paths: list[Path],
        field_name: str = "files",
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        boundary = f"----DeepLiveCamBoundary{uuid.uuid4().hex}"
        content_type = f"multipart/form-data; boundary={boundary}"
        body_parts = []
        for file_path in file_paths:
            mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            file_data = file_path.read_bytes()
            body_parts.append(
                (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{field_name}"; filename="{file_path.name}"\r\n'
                    f"Content-Type: {mime_type}\r\n\r\n"
                ).encode("utf-8") + file_data + b"\r\n"
            )
        body = b"".join(body_parts) + f"--{boundary}--\r\n".encode("utf-8")
        request = urllib.request.Request(
            self.url(endpoint),
            data=body,
            method="POST",
            headers={"Content-Type": content_type},
        )
        return _open_json(request, timeout)


def job_payload(settings: AppSettings, input_dir: str, output_dir: str, source_face: str | None = None) -> dict[str, Any]:
    normalized_input = str(input_dir).replace("\\", "/")
    is_photo_job = "/photos" in normalized_input and "/videos" not in normalized_input
    output_max_width = int(getattr(settings, "photo_max_width", 0)) if is_photo_job else None
    max_width = int(settings.max_width)
    quality = int(getattr(settings, "photo_quality", 95)) if is_photo_job else int(settings.quality)
    detector_size = int(getattr(settings, "photo_detector_size", 640)) if is_photo_job else int(getattr(settings, "detector_size", 640))
    face_model_pack = str(getattr(settings, "photo_face_model_pack", "buffalo_l")) if is_photo_job else str(getattr(settings, "face_model_pack", "buffalo_l"))
    swapper_precision = str(getattr(settings, "photo_swapper_precision", "fp32")) if is_photo_job else str(getattr(settings, "swapper_precision", "fp32"))
    payload: dict[str, Any] = {
        "source_face": source_face or settings.source_face,
        "input_dir": input_dir,
        "output_dir": output_dir,
        "recursive": settings.recursive,
        "overwrite": settings.overwrite,
        "skip_processed": settings.skip_processed,
        "many_faces": settings.many_faces,
        "enhancer": settings.enhancer,
        "opacity": settings.opacity,
        "sharpness": settings.sharpness,
        "mouth_mask_size": settings.mouth_mask_size,
        "interpolation_weight": settings.interpolation_weight,
        "poisson_blend": settings.poisson_blend,
        "color_correction": settings.color_correction,
        "max_fps": settings.max_fps,
        "max_width": max_width,
        "quality": quality,
        "detector_size": detector_size,
        "face_model_pack": face_model_pack,
        "swapper_precision": swapper_precision,
        "start_pct": settings.start_pct,
        "end_pct": settings.end_pct,
    }
    if output_max_width and output_max_width > 0:
        payload["output_max_width"] = output_max_width
    return payload


__all__ = [
    "ApiClient",
    "PHOTO_EXTENSIONS",
    "VIDEO_EXTENSIONS",
    "check_tailscale_cli",
    "format_size",
    "is_local_path",
    "job_payload",
    "local_files",
    "taildrop_receive_file",
    "urllib",
]
