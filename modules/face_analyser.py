import os
import shutil
from typing import Any
import insightface
import threading

import modules.globals
from modules import imread_unicode, imwrite_unicode
from tqdm import tqdm
from modules.typing import Frame
from modules.cluster_analysis import find_cluster_centroids, find_closest_centroid
from modules.utilities import get_temp_directory_path, create_temp, extract_frames, clean_temp, get_temp_frame_paths
from pathlib import Path

FACE_ANALYSER = None
FACE_ANALYSER_LOCK = threading.Lock()
FACE_ANALYSER_MODEL_PACK = "buffalo_l"
FACE_ANALYSER_MODEL_PACKS = {"buffalo_l", "buffalo_m", "buffalo_s"}

DET_SIZE = (640, 640)


def set_face_analyser_detector_size(detector_size: int | None) -> tuple[int, int]:
    """Select the InsightFace detector input size used by future FaceAnalysis calls."""
    global FACE_ANALYSER, DET_SIZE

    try:
        size = int(detector_size or 640)
    except (TypeError, ValueError):
        size = 640
    size = max(160, min(1280, size))
    size = max(32, size // 32 * 32)
    selected = (size, size)
    with FACE_ANALYSER_LOCK:
        if selected != DET_SIZE:
            FACE_ANALYSER = None
            DET_SIZE = selected
    return DET_SIZE


def set_face_analyser_model_pack(model_pack: str | None) -> str:
    """Select the InsightFace model pack used by future FaceAnalysis calls."""
    global FACE_ANALYSER, FACE_ANALYSER_MODEL_PACK

    selected = str(model_pack or "buffalo_l")
    if selected not in FACE_ANALYSER_MODEL_PACKS:
        selected = "buffalo_l"
    with FACE_ANALYSER_LOCK:
        if selected != FACE_ANALYSER_MODEL_PACK:
            FACE_ANALYSER = None
            FACE_ANALYSER_MODEL_PACK = selected
    return FACE_ANALYSER_MODEL_PACK


def get_face_analyser_model_pack() -> str:
    return FACE_ANALYSER_MODEL_PACK


def get_face_analyser() -> Any:
    """Get face analyser with thread-safe initialization."""
    global FACE_ANALYSER

    if FACE_ANALYSER is None:
        with FACE_ANALYSER_LOCK:
            # Double-check after acquiring lock
            if FACE_ANALYSER is None:
                from modules.processors.frame._onnx_enhancer import (
                    build_provider_config,
                )
                providers = build_provider_config()
                FACE_ANALYSER = insightface.app.FaceAnalysis(
                    name=FACE_ANALYSER_MODEL_PACK,
                    providers=providers,
                    allowed_modules=['detection', 'recognition', 'landmark_2d_106']
                )
                FACE_ANALYSER.prepare(ctx_id=0, det_size=DET_SIZE)
                _optimize_det_model(FACE_ANALYSER, providers)
                print(f"InsightFace model pack: {FACE_ANALYSER_MODEL_PACK}")
    return FACE_ANALYSER


def _optimize_det_model(fa: Any, providers) -> None:
    """Replace the detection model's ONNX session with a CoreML-optimized one.

    Folds dynamic Shape→Gather chains into constants (the input size is
    fixed at det_size), eliminating CPU↔ANE partition boundaries in the
    RetinaFace FPN upsampling path.  21ms → 4ms on M3 Max.
    """
    from modules.onnx_optimize import optimize_for_coreml, IS_APPLE_SILICON
    if not IS_APPLE_SILICON:
        return

    det_model = fa.det_model
    model_path = getattr(det_model, 'model_file', None)
    if model_path is None or not os.path.exists(model_path):
        return

    input_shape = (1, 3, DET_SIZE[1], DET_SIZE[0])
    optimized_path = optimize_for_coreml(model_path, input_shape=input_shape)
    if optimized_path == model_path:
        return

    import onnxruntime
    session_options = onnxruntime.SessionOptions()
    session_options.graph_optimization_level = (
        onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
    )

    # Route detection to GPU shader cores (CPUAndGPU) instead of ANE.
    # This lets detection run concurrently with the swap model on the
    # ANE, overlapping the two inference calls.  Detection is fast
    # enough on GPU (~4ms) and this frees ANE for the heavier swap.
    det_providers = []
    for p in providers:
        name = p[0] if isinstance(p, tuple) else p
        if name == "CoreMLExecutionProvider":
            det_providers.append((
                "CoreMLExecutionProvider",
                {"ModelFormat": "MLProgram", "MLComputeUnits": "CPUAndGPU"},
            ))
        else:
            det_providers.append(p)

    det_model.session = onnxruntime.InferenceSession(
        optimized_path, sess_options=session_options, providers=det_providers,
    )


def _needs_landmark() -> bool:
    """Check whether any active feature requires 106-point landmarks.

    Landmarks are needed by face enhancers and mouth masking, but not
    by the face swapper alone.
    """
    if getattr(modules.globals, "mouth_mask", False):
        return True
    processors = getattr(modules.globals, "frame_processors", [])
    return any(p in processors for p in
               ("face_enhancer", "face_enhancer_gpen256", "face_enhancer_gpen512"))


def _is_dml() -> bool:
    return any("DmlExecutionProvider" in p for p in modules.globals.execution_providers)


def _analyse_faces(frame: Frame) -> list:
    """Run face detection, then recognition (and optionally landmark).

    Replaces InsightFace's ``FaceAnalysis.get()`` to skip the
    landmark_2d_106 model when only face_swapper is active (saves ~1ms
    per face and avoids an unnecessary ONNX session call).
    """
    fa = get_face_analyser()

    bboxes, kpss = fa.det_model.detect(frame, max_num=0, metric="default")
    if bboxes.shape[0] == 0:
        return []

    need_landmark = _needs_landmark()
    rec_model = fa.models.get("recognition")
    lmk_model = fa.models.get("landmark_2d_106") if need_landmark else None

    from insightface.app.common import Face

    faces = []
    for i in range(bboxes.shape[0]):
        face = Face(bbox=bboxes[i, 0:4],
                    kps=kpss[i] if kpss is not None else None,
                    det_score=bboxes[i, 4])
        if rec_model is not None:
            rec_model.get(frame, face)
        if lmk_model is not None:
            lmk_model.get(frame, face)
        faces.append(face)

    return faces


def get_one_face(frame: Frame, faces: Any = None) -> Any:
    if faces is None:
        if _is_dml():
            with modules.globals.dml_lock:
                faces = _analyse_faces(frame)
        else:
            faces = _analyse_faces(frame)
    try:
        return min(faces, key=lambda x: x.bbox[0])
    except ValueError:
        return None


def get_many_faces(frame: Frame) -> Any:
    try:
        if _is_dml():
            with modules.globals.dml_lock:
                return _analyse_faces(frame)
        else:
            return _analyse_faces(frame)
    except IndexError:
        return None

def detect_one_face_fast(frame: Frame) -> Any:
    """Detection-only — skips landmark and recognition models.

    Returns a Face with bbox, kps, det_score (enough for face swap).
    ~10ms vs ~16ms for full get_one_face() at 1080p.
    """
    from insightface.app.common import Face
    fa = get_face_analyser()
    bboxes, kpss = fa.det_model.detect(frame, max_num=0, metric='default')
    if bboxes.shape[0] == 0:
        return None
    idx = int(bboxes[:, 0].argmin())
    return Face(bbox=bboxes[idx, :4], kps=kpss[idx], det_score=bboxes[idx, 4])


def detect_many_faces_fast(frame: Frame) -> Any:
    """Detection-only multi-face — skips landmark and recognition."""
    from insightface.app.common import Face
    fa = get_face_analyser()
    bboxes, kpss = fa.det_model.detect(frame, max_num=0, metric='default')
    if bboxes.shape[0] == 0:
        return None
    return [Face(bbox=bboxes[i, :4], kps=kpss[i], det_score=bboxes[i, 4])
            for i in range(bboxes.shape[0])]


def ensure_landmarks(frame: Frame, faces: Any) -> None:
    """Run the 2d106 landmark model in-place on faces that lack it.

    The fast webcam path (detect_one_face_fast / detect_many_faces_fast)
    produces detection-only Face objects with no ``landmark_2d_106``.
    Mouth masking needs those landmarks, so add them on demand only when
    the feature is active — keeping the fast path fast otherwise.
    """
    if faces is None:
        return
    if not isinstance(faces, (list, tuple)):
        faces = [faces]

    fa = get_face_analyser()
    lmk_model = fa.models.get("landmark_2d_106")
    if lmk_model is None:
        return

    for face in faces:
        if face is None:
            continue
        # insightface Face is a dict; missing keys raise AttributeError,
        # so getattr(..., None) is the safe presence check.
        if getattr(face, "landmark_2d_106", None) is None:
            try:
                lmk_model.get(frame, face)
            except Exception as e:  # pragma: no cover - never break the swap
                print(f"Error computing 2d106 landmarks: {e}")


def has_valid_map() -> bool:
    for map in modules.globals.source_target_map:
        if "source" in map and "target" in map:
            return True
    return False

def default_source_face() -> Any:
    for map in modules.globals.source_target_map:
        if "source" in map:
            return map['source']['face']
    return None

def simplify_maps() -> Any:
    centroids = []
    faces = []
    for map in modules.globals.source_target_map:
        if "source" in map and "target" in map:
            centroids.append(map['target']['face'].normed_embedding)
            faces.append(map['source']['face'])

    modules.globals.simple_map = {'source_faces': faces, 'target_embeddings': centroids}
    modules.globals.face_selector_mode = 'reference'

    return None
