"""Local CLIP encoding. Importing this module never loads Torch or the model."""
import hashlib
import io
import json
import logging
import math
import os
import threading
import time
import warnings
from pathlib import Path

MODEL_NAME = "clip-ViT-B-32"
MODEL_REVISION = "327ab67"
MODEL_VERSION = f"{MODEL_NAME}@{MODEL_REVISION}:rgb-exif-768-v1"
MAX_IMAGE_EDGE_PX = 768
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_BYTES = 8 * 1024 * 1024
_model = None
_model_failure_until = 0.0
_model_lock = threading.Lock()
_encode_lock = threading.Lock()
log = logging.getLogger(__name__)


def get_image_model():
    global _model, _model_failure_until
    if os.getenv("DISABLE_IMAGE_EMBEDDING", "").lower() in {"true", "1", "yes"}:
        raise RuntimeError("Local image embedding is disabled")
    with _model_lock:
        if _model is None:
            if time.monotonic() < _model_failure_until:
                raise RuntimeError("CLIP initialization is cooling down after a failure")
            try:
                os.environ.setdefault("OMP_NUM_THREADS", "1")
                os.environ.setdefault("MKL_NUM_THREADS", "1")
                os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
                import torch
                from sentence_transformers import SentenceTransformer
                torch.set_num_threads(1)
                started = time.monotonic()
                _model = SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION, device="cpu",
                    cache_folder=os.getenv("IMAGE_MODEL_CACHE_DIR") or None)
                log.info("CLIP initialized model=%s seconds=%.3f", MODEL_VERSION, time.monotonic() - started)
            except Exception:
                _model_failure_until = time.monotonic() + 60
                raise

    return _model


def decode_image(image_path):
    """Bound decoding before RGB allocation; never trust a filename or MIME alone."""
    from PIL import Image, ImageOps
    data = Path(image_path).read_bytes()
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds decoding byte limit")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as original:
            if original.width * original.height > MAX_IMAGE_PIXELS:
                raise ValueError("Image exceeds decoding pixel limit")
            original.seek(0)
            image = ImageOps.exif_transpose(original).convert("RGB")
            image.thumbnail((MAX_IMAGE_EDGE_PX, MAX_IMAGE_EDGE_PX), Image.Resampling.LANCZOS)
            return image


def vision_image_bytes(image_path):
    output = io.BytesIO()
    decode_image(image_path).save(output, format="JPEG", quality=85)
    return output.getvalue(), "image/jpeg"


def image_sha256(image_path):
    return hashlib.sha256(Path(image_path).read_bytes()).hexdigest()


def create_image_embedding(image_path):
    try:
        image = decode_image(image_path)
        model = get_image_model()
        import torch
        with _encode_lock, torch.inference_mode():
            embedding = model.encode(image, normalize_embeddings=True)
        return json.dumps([float(value) for value in embedding.tolist()])
    except Exception as error:
        log.warning("Image encoding unavailable (%s)", type(error).__name__)
        return None


def create_text_embedding(text):
    try:
        model = get_image_model()
        import torch
        with _encode_lock, torch.inference_mode():
            embedding = model.encode(str(text), normalize_embeddings=True)
        return json.dumps([float(value) for value in embedding.tolist()])
    except Exception as error:
        log.warning("Text encoding unavailable (%s)", type(error).__name__)
        return None


def cosine_similarity_from_json(a_json, b_json):
    try:
        a, b = json.loads(a_json), json.loads(b_json)
        if not a or len(a) != len(b) or not all(math.isfinite(float(x)) for x in a + b):
            return 0.0
        norm = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
        return max(-1.0, min(1.0, sum(x*y for x,y in zip(a,b)) / norm)) if norm else 0.0
    except (ValueError, TypeError, ZeroDivisionError):
        return 0.0
