"""
Unit tests for image evidence and Vision parsing. Full local Flask/SQLite coverage is in test_hybrid_image_pipeline.py.

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

import os  # noqa: E402
os.environ.setdefault("DOCUMENT_TEXT_BACKFILL", "false")
import app as app_module  # noqa: E402


def test_high_confidence_returns_current_quote_not_index_answer():
    article = {"article_id": 9, "title": "Current guide", "content": "Keep the item inside the designated area.", "image_similarity": .95}
    with patch.object(app_module, "get_local_image_path_from_url", return_value="fixture"), \
         patch.object(app_module.image_index_service, "visual_candidates", return_value=[{}]), \
         patch.object(app_module.image_index_service, "current_articles", return_value=[article]):
        result = app_module.search_visual_image_match("fixture", "Where should I put it?")
    assert result["answer"] == article["content"]
    assert result["article_id"] == 9
    assert result["image_similarity"] == .95
    assert result["confidence_kind"] == "not_calibrated"


def test_medium_confidence_does_not_assert_company_policy():
    with patch.object(app_module, "get_local_image_path_from_url", return_value="fixture"), \
         patch.object(app_module.image_index_service, "visual_candidates", return_value=[{}]), \
         patch.object(app_module.image_index_service, "current_articles", return_value=[{"image_similarity": .6}]):
        assert app_module.search_visual_image_match("fixture", "Where should I put it?") is None


def test_low_confidence_returns_none_and_falls_back_to_text_search():
    with patch.object(app_module, "get_local_image_path_from_url", return_value="fixture"), \
         patch.object(app_module.image_index_service, "visual_candidates", return_value=[]), \
         patch.object(app_module.image_index_service, "current_articles", return_value=[]):
        assert app_module.search_visual_image_match("fixture", "question") is None


def test_image_only_never_returns_policy_even_on_exact_match():
    with patch.object(app_module, "get_local_image_path_from_url", return_value="fixture"), \
         patch.object(app_module.image_index_service, "visual_candidates", return_value=[{}]), \
         patch.object(app_module.image_index_service, "current_articles", return_value=[{"image_similarity": 1.0}]):
        assert app_module.search_visual_image_match("fixture")["source"] == "image_only_clarification"


def test_embedding_provider_unavailable_returns_none_without_crashing():
    with patch.object(app_module, "get_local_image_path_from_url", return_value="fixture"), \
         patch.object(app_module.image_index_service, "visual_candidates", side_effect=RuntimeError("unavailable")):
        assert app_module.search_visual_image_match("fixture", "question") is None


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


def test_build_image_only_clarification_mentions_detected_object_and_does_not_escalate():
    vision_result = {"detectedObjects": ["an iPad"], "imageSummary": "An iPad on a table."}
    result = app_module.build_image_only_clarification_response(vision_result)

    assert result["escalation_required"] is False
    assert result["escalation_ready"] is False
    assert "an iPad" in result["answer"]
    assert "what would you like to know" in result["answer"].lower()


def test_build_image_only_clarification_handles_no_vision_result():
    result = app_module.build_image_only_clarification_response(None)

    assert result["escalation_required"] is False
    assert "uploaded an image" in result["answer"].lower()


def test_build_image_only_clarification_includes_kb_hint_when_available():
    vision_result = {"detectedObjects": ["a dustbin"]}
    kb_hint = {"title": "Dustbin Cleaning SOP"}
    result = app_module.build_image_only_clarification_response(vision_result, kb_hint)

    assert "Dustbin Cleaning SOP" in result["answer"]


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
