import os

# Must be set before numpy/torch are imported. PyTorch's BLAS backend
# defaults to spawning one thread per CPU core it detects, which on a small
# container can multiply memory/CPU usage far beyond what a single image
# embedding actually needs -- this is a common cause of an OOM SIGKILL
# during inference on constrained hosts like Railway's smaller plans.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from sentence_transformers import SentenceTransformer

torch.set_num_threads(1)

_model = None
MODEL_NAME = "clip-ViT-B-32"

# Longest edge to downscale an uploaded photo to before encoding. CLIP
# resizes to a fixed 224x224 internally either way, but decoding a full
# 12MP phone photo into a raw RGB array first can itself use tens of MB --
# shrinking it up front keeps that intermediate memory small on a
# constrained container.
MAX_IMAGE_EDGE_PX = 768

# Emergency kill switch: if the container still can't fit the model in
# memory even after the thread-count fix, set DISABLE_IMAGE_EMBEDDING=true
# in Railway's environment variables and restart -- no redeploy needed.
# Every caller already treats a None return as "skip visual matching, fall
# back to the existing text-based search," so the rest of the app (normal
# chat, KB search, escalation) keeps working either way.
def _image_embedding_disabled():
    return os.getenv("DISABLE_IMAGE_EMBEDDING", "").strip().lower() in {"1", "true", "yes"}


def get_image_model():
    global _model

    if _image_embedding_disabled():
        raise RuntimeError("Image embedding is disabled via DISABLE_IMAGE_EMBEDDING.")

    if _model is None:
        print("Loading image embedding model...")
        _model = SentenceTransformer(MODEL_NAME)
        print("Image embedding model loaded.")

    return _model


def _downscale_for_encoding(image):
    width, height = image.size
    longest_edge = max(width, height)

    if longest_edge <= MAX_IMAGE_EDGE_PX:
        return image

    scale = MAX_IMAGE_EDGE_PX / float(longest_edge)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))

    return image.resize(new_size, Image.LANCZOS)


def create_image_embedding(image_path):
    try:
        image_path = Path(image_path)

        if not image_path.exists():
            print("IMAGE EMBEDDING ERROR: file does not exist:", image_path)
            return None

        model = get_image_model()
        image = Image.open(image_path).convert("RGB")
        image = _downscale_for_encoding(image)

        with torch.inference_mode():
            embedding = model.encode(image, normalize_embeddings=True)

        return json.dumps([float(value) for value in embedding.tolist()])

    except Exception as error:
        print("IMAGE EMBEDDING ERROR:", error)
        return None


def create_text_embedding(text):
    """
    Encode text into the same CLIP embedding space used for images.
    This lets an uploaded photo be compared directly against KB captions,
    titles, keywords and answers (not just other stored photos), which is
    what makes category-level / different-angle matching possible.
    """
    try:
        text = str(text or "").strip()

        if not text:
            return None

        model = get_image_model()

        with torch.inference_mode():
            embedding = model.encode(text, normalize_embeddings=True)

        return json.dumps([float(value) for value in embedding.tolist()])

    except Exception as error:
        print("TEXT EMBEDDING ERROR:", error)
        return None


def cosine_similarity_from_json(a_json, b_json):
    try:
        if not a_json or not b_json:
            return 0.0

        a = np.array(json.loads(a_json), dtype=np.float32)
        b = np.array(json.loads(b_json), dtype=np.float32)

        if a.size == 0 or b.size == 0:
            return 0.0

        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    except Exception as error:
        print("IMAGE SIMILARITY ERROR:", error)
        return 0.0