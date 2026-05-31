import json
from pathlib import Path

import numpy as np
from PIL import Image
from sentence_transformers import SentenceTransformer


_model = None
MODEL_NAME = "clip-ViT-B-32"


def get_image_model():
    global _model

    if _model is None:
        print("Loading image embedding model...")
        _model = SentenceTransformer(MODEL_NAME)
        print("Image embedding model loaded.")

    return _model


def create_image_embedding(image_path):
    try:
        image_path = Path(image_path)

        if not image_path.exists():
            print("IMAGE EMBEDDING ERROR: file does not exist:", image_path)
            return None

        model = get_image_model()
        image = Image.open(image_path).convert("RGB")

        embedding = model.encode(image, normalize_embeddings=True)

        return json.dumps([float(value) for value in embedding.tolist()])

    except Exception as error:
        print("IMAGE EMBEDDING ERROR:", error)
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