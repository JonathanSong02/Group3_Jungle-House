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


def _run_with_mocks(rows, cosine_side_effect, question="how do I clean this", tmp_path=None):
    fake_cursor = MagicMock()
    fake_cursor.fetchall.return_value = rows

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    # _get_uploaded_image_embedding() hashes the real file on disk (that's
    # how duplicate-submission caching works in production, where the file
    # always exists because save_chat_image() just wrote it) -- so the test
    # needs a real file too, not just a fake path string.
    fake_upload_path = tmp_path / "upload.jpg"
    fake_upload_path.write_bytes(b"fake-image-bytes")

    with patch.object(app_module, "IMAGE_EMBEDDING_AVAILABLE", True), \
         patch.object(app_module, "create_image_embedding", return_value=fake_embedding(0.9)), \
         patch.object(app_module, "create_text_embedding", return_value=fake_embedding(0.5)), \
         patch.object(app_module, "cosine_similarity_from_json", side_effect=cosine_side_effect), \
         patch.object(app_module, "get_local_image_path_from_url", return_value=str(fake_upload_path)), \
         patch.object(app_module, "get_db_connection", return_value=fake_conn):

        app_module.UPLOADED_IMAGE_EMBEDDING_CACHE.clear()
        app_module.IMAGE_TEXT_EMBEDDING_CACHE.clear()

        return app_module.search_visual_image_match("/static/uploads/chat/upload.jpg", question=question)


def _cosine_from_embedding_seed(a, b):
    """Test double: the fake embeddings encode their intended similarity as
    the first element (see fake_embedding()), so cosine can just read it
    back directly instead of needing a real vector comparison."""
    return json.loads(b)[0]


def test_high_confidence_returns_direct_answer(tmp_path):
    rows = [make_row("kb_1", 0.95), make_row("kb_2", 0.2)]

    result = _run_with_mocks(rows, _cosine_from_embedding_seed, tmp_path=tmp_path)

    assert result is not None
    assert result.get("type", "text") != "multiple_choice"
    assert result["source"] == "visual_image_match"
    assert result["confidence"] >= app_module.HIGH_CONFIDENCE_THRESHOLD


def test_medium_confidence_returns_related_options_instead_of_failing(tmp_path):
    # Simulates a same-item-different-angle photo: similarity is well below
    # the old hard 0.85 threshold but still clearly related.
    rows = [make_row("kb_1", 0.6, caption="dustbin"), make_row("kb_2", 0.55, caption="dustbin (grey)")]

    result = _run_with_mocks(rows, _cosine_from_embedding_seed, tmp_path=tmp_path)

    assert result is not None
    assert result["type"] == "multiple_choice"
    assert 1 <= len(result["options"]) <= app_module.MAX_RELATED_OPTIONS
    assert result["confidence"] < app_module.HIGH_CONFIDENCE_THRESHOLD


def test_low_confidence_returns_none_and_falls_back_to_text_search(tmp_path):
    rows = [make_row("kb_1", 0.1, caption="terminal machine")]

    def cosine(a, b):
        return 0.05

    result = _run_with_mocks(rows, cosine, tmp_path=tmp_path)

    assert result is None


def test_no_embedding_rows_falls_back_gracefully(tmp_path):
    result = _run_with_mocks([], cosine_side_effect=lambda a, b: 0.0, tmp_path=tmp_path)
    assert result is None


def test_embedding_provider_unavailable_returns_none_without_crashing():
    with patch.object(app_module, "IMAGE_EMBEDDING_AVAILABLE", False):
        result = app_module.search_visual_image_match("/static/uploads/chat/upload.jpg", question="x")
    assert result is None


# =========================
# Gemini Vision relevance check
# =========================

def test_parse_vision_json_reply_handles_plain_json():
    raw = '{"isWorkRelated": true, "confidence": 0.9, "detectedObjects": ["iPad"], "possibleAliases": ["tablet"], "imageSummary": "An iPad.", "irrelevantReason": null}'
    parsed = app_module._parse_vision_json_reply(raw)

    assert parsed["isWorkRelated"] is True
    assert parsed["detectedObjects"] == ["iPad"]


def test_parse_vision_json_reply_strips_markdown_fences():
    raw = '```json\n{"isWorkRelated": false, "confidence": 0.8, "detectedObjects": [], "possibleAliases": [], "imageSummary": "A selfie.", "irrelevantReason": "Not work related."}\n```'
    parsed = app_module._parse_vision_json_reply(raw)

    assert parsed["isWorkRelated"] is False
    assert parsed["irrelevantReason"] == "Not work related."


def test_build_vision_augmented_question_combines_object_and_question():
    vision_result = {"detectedObjects": ["iPad"], "possibleAliases": ["tablet", "POS iPad"]}
    combined = app_module.build_vision_augmented_question("where do I keep this when closing", vision_result)

    assert "where do I keep this when closing" in combined
    assert "iPad" in combined


def test_build_image_irrelevant_response_does_not_escalate():
    vision_result = {"isWorkRelated": False, "irrelevantReason": "Selfie.", "imageSummary": "A selfie."}
    result = app_module.build_image_irrelevant_response(vision_result)

    assert result["escalation_required"] is False
    assert result["escalation_ready"] is False
    assert "does not look related" in result["answer"]


def test_analyze_uploaded_image_with_vision_falls_back_when_not_configured():
    fake_service = MagicMock()
    fake_service.AIProviderNotConfiguredError = type("AIProviderNotConfiguredError", (Exception,), {})
    fake_service.AIProviderVisionUnsupportedError = type("AIProviderVisionUnsupportedError", (Exception,), {})
    fake_service.generate_ai_vision_reply.side_effect = fake_service.AIProviderNotConfiguredError("not configured")

    with patch.object(app_module, "AI_PROVIDER_SERVICE_AVAILABLE", True), \
         patch.object(app_module, "ai_provider_service", fake_service):

        app_module.GEMINI_VISION_CACHE.clear()
        result = app_module.analyze_uploaded_image_with_vision("/tmp/fake.jpg", file_hash="abc123")

    assert result is None


def test_analyze_uploaded_image_with_vision_uses_cache_on_repeat_call():
    fake_service = MagicMock()
    fake_service.AIProviderNotConfiguredError = Exception
    fake_service.AIProviderVisionUnsupportedError = Exception
    fake_service.generate_ai_vision_reply.return_value = (
        '{"isWorkRelated": true, "confidence": 0.9, "detectedObjects": ["iPad"], '
        '"possibleAliases": [], "imageSummary": "An iPad.", "irrelevantReason": null}'
    )

    with patch.object(app_module, "AI_PROVIDER_SERVICE_AVAILABLE", True), \
         patch.object(app_module, "ai_provider_service", fake_service):

        app_module.GEMINI_VISION_CACHE.clear()

        first = app_module.analyze_uploaded_image_with_vision("/tmp/fake.jpg", file_hash="dup-hash")
        second = app_module.analyze_uploaded_image_with_vision("/tmp/fake.jpg", file_hash="dup-hash")

    assert first["detectedObjects"] == ["iPad"]
    assert second == first
    # Only one real API call should have happened -- the second call reused
    # the cached result, which is the cost-control behaviour under test.
    assert fake_service.generate_ai_vision_reply.call_count == 1
