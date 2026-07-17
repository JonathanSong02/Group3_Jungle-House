"""
Unit tests for the improved multi-stage image retrieval pipeline.

These tests mock MySQL and the CLIP model so they can run without a live
database or a downloaded model -- run with:

    pip install -r requirements.txt pytest
    pytest src/test_image_retrieval.py

They cover the tiering behaviour (Requirement 5/6/7 of the image-retrieval
improvement): a near-identical photo should still answer directly, a
different angle/colour/background of the same item should come back as
related options instead of failing outright, and a completely unrelated
photo should fall through to the existing text-based search.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as app_module  # noqa: E402


def fake_embedding(seed):
    """A tiny deterministic 'embedding' so cosine similarity is predictable."""
    return json.dumps([seed, 1.0 - seed, 0.0])


def make_row(image_id, score_hint, source_type="knowledge_base", caption="dustbin cleaning SOP"):
    return {
        "image_id": image_id,
        "source_type": source_type,
        "image_embedding": fake_embedding(score_hint),
        "image_caption": caption,
        "image_keywords": "dustbin trash bin",
        "question": f"{caption} {image_id}",
        "answer": "Empty the dustbin and wipe it down during closing.",
        "image_url": f"/static/uploads/chat/{image_id}.jpg",
        "image_type": "image/jpeg",
    }


def _run_with_mocks(rows, cosine_side_effect, question="how do I clean this"):
    fake_cursor = MagicMock()
    fake_cursor.fetchall.return_value = rows

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    with patch.object(app_module, "IMAGE_EMBEDDING_AVAILABLE", True), \
         patch.object(app_module, "create_image_embedding", return_value=fake_embedding(0.9)), \
         patch.object(app_module, "create_text_embedding", return_value=fake_embedding(0.5)), \
         patch.object(app_module, "cosine_similarity_from_json", side_effect=cosine_side_effect), \
         patch.object(app_module, "get_local_image_path_from_url", return_value="/tmp/fake.jpg"), \
         patch.object(app_module, "get_db_connection", return_value=fake_conn):

        app_module.UPLOADED_IMAGE_EMBEDDING_CACHE.clear()
        app_module.IMAGE_TEXT_EMBEDDING_CACHE.clear()

        return app_module.search_visual_image_match("/static/uploads/chat/upload.jpg", question=question)


def test_high_confidence_returns_direct_answer():
    rows = [make_row("kb_1", 0.95), make_row("kb_2", 0.2)]

    def cosine(a, b):
        return 0.95 if "kb_1" in b else 0.10

    result = _run_with_mocks(rows, cosine)

    assert result is not None
    assert result.get("type", "text") != "multiple_choice"
    assert result["source"] == "visual_image_match"
    assert result["confidence"] >= app_module.HIGH_CONFIDENCE_THRESHOLD


def test_medium_confidence_returns_related_options_instead_of_failing():
    # Simulates a same-item-different-angle photo: similarity is well below
    # the old hard 0.85 threshold but still clearly related.
    rows = [make_row("kb_1", 0.6, caption="dustbin"), make_row("kb_2", 0.55, caption="dustbin (grey)")]

    def cosine(a, b):
        return 0.60 if "kb_1" in b else 0.55

    result = _run_with_mocks(rows, cosine)

    assert result is not None
    assert result["type"] == "multiple_choice"
    assert 1 <= len(result["options"]) <= app_module.MAX_RELATED_OPTIONS
    assert result["confidence"] < app_module.HIGH_CONFIDENCE_THRESHOLD


def test_low_confidence_returns_none_and_falls_back_to_text_search():
    rows = [make_row("kb_1", 0.1, caption="terminal machine")]

    def cosine(a, b):
        return 0.05

    result = _run_with_mocks(rows, cosine)

    assert result is None


def test_no_embedding_rows_falls_back_gracefully():
    result = _run_with_mocks([], cosine_side_effect=lambda a, b: 0.0)
    assert result is None


def test_embedding_provider_unavailable_returns_none_without_crashing():
    with patch.object(app_module, "IMAGE_EMBEDDING_AVAILABLE", False):
        result = app_module.search_visual_image_match("/static/uploads/chat/upload.jpg", question="x")
    assert result is None
