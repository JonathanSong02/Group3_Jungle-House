# Trigger redeploy to verify the persistent uploads volume survives a restart.
from flask import Flask, request, jsonify, send_from_directory, redirect
from flask_cors import CORS
import os
import time
from werkzeug.utils import secure_filename
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from pathlib import Path
import csv
import json
import traceback
import smtplib
import secrets
import hashlib
import requests
from email.message import EmailMessage
from db_helper import (
    save_qa_to_db,
    search_similar_question,
    search_similar_questions,
    search_image_retrieval,
    create_escalation,
    resolve_escalation,
    similarity_ratio as db_similarity_ratio,
)

# AI provider settings (Gemini/OpenAI/DeepSeek/Claude) are optional --
# the app must still run even if the cryptography dependency isn't
# installed yet (e.g. right after this feature is deployed but before the
# next full dependency install finishes).
try:
    import ai_provider_service
    AI_PROVIDER_SERVICE_AVAILABLE = True
    AI_PROVIDER_SERVICE_LOAD_ERROR = None
except Exception as error:
    ai_provider_service = None
    AI_PROVIDER_SERVICE_AVAILABLE = False
    AI_PROVIDER_SERVICE_LOAD_ERROR = str(error)

try:
    import notion_sync_service
    NOTION_SYNC_SERVICE_AVAILABLE = True
    NOTION_SYNC_SERVICE_LOAD_ERROR = None
except Exception as error:
    notion_sync_service = None
    NOTION_SYNC_SERVICE_AVAILABLE = False
    NOTION_SYNC_SERVICE_LOAD_ERROR = str(error)

try:
    from image_embedding_helper import (
        create_image_embedding,
        create_text_embedding,
        cosine_similarity_from_json,
        MODEL_NAME as IMAGE_EMBEDDING_MODEL_NAME
    )
    IMAGE_EMBEDDING_AVAILABLE = True
    IMAGE_EMBEDDING_LOAD_ERROR = None
except Exception as error:
    create_image_embedding = None
    create_text_embedding = None
    cosine_similarity_from_json = None
    IMAGE_EMBEDDING_MODEL_NAME = None
    IMAGE_EMBEDDING_AVAILABLE = False
    IMAGE_EMBEDDING_LOAD_ERROR = str(error)

# OCR is optional. The system must still run even when pytesseract is not installed.
try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    OCR_AVAILABLE = True
except Exception as error:
    pytesseract = None
    OCR_AVAILABLE = False
    OCR_LOAD_ERROR = str(error)

import re

def is_nonsense(text):
    text = text.strip().lower()

    whitelist = ["hi", "hello", "hey", "ok", "thanks"]

    if text in whitelist:
        return False

    # ❌ too short
    if len(text) < 5:
        return True

    # ❌ no vowels (asdfgh)
    if not re.search(r'[aeiou]', text):
        return True

    # ❌ repeated characters
    if re.fullmatch(r'(.)\1{3,}', text):
        return True

    # ❌ keyboard smash patterns
    if re.search(r'(asdf|qwer|zxcv)', text):
        return True

    # ❌ no real words (only symbols/numbers)
    if not re.search(r'[a-z]', text):
        return True

    return False

try:
    from predict_intent import get_model_answer
    try:
        from predict_intent import MODEL_ERROR as PREDICT_MODEL_ERROR
    except Exception:
        PREDICT_MODEL_ERROR = None
    MODEL_AVAILABLE = True
    MODEL_LOAD_ERROR = None
except Exception as error:
    get_model_answer = None
    PREDICT_MODEL_ERROR = str(error)
    MODEL_AVAILABLE = False
    MODEL_LOAD_ERROR = str(error)

BASE_DIR = Path(__file__).resolve().parent

# =========================
# STATIC / UPLOAD / LOG PATHS
# =========================
# Use only ONE static folder so uploaded files and served files use the same path.
STATIC_DIR = BASE_DIR.parent / "static"

UPLOAD_FOLDER = STATIC_DIR / "uploads" / "articles"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

CHAT_UPLOAD_FOLDER = STATIC_DIR / "uploads" / "chat"
CHAT_UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

SOP_IMAGE_FOLDER = STATIC_DIR / "sop_images"
SOP_IMAGE_FOLDER.mkdir(parents=True, exist_ok=True)

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_JSONL = LOG_DIR / "ai_chat_logs.jsonl"
LOG_CSV = LOG_DIR / "ai_chat_logs.csv"
TEST_REPORT_CSV = LOG_DIR / "ai_test_results.csv"

ESCALATION_MESSAGE = "Please escalate this question to team lead."
REAL_JH_TEST_QUESTIONS = []

# Simple in-memory chat context for local prototype use.
# This helps follow-up messages like "step 25" work even if the frontend
# does not send the previous AI response context back to the backend.
AI_CHAT_MEMORY = {}
AI_FAIL_MEMORY = {}
AI_LAST_ANSWER_MEMORY = {}

app = Flask(__name__, static_folder=None)

# Reject oversized uploads before they hit disk/AI providers (cost control +
# Requirement 13 "file too large" handling). 8MB covers a normal phone photo
# with headroom; anything bigger is almost certainly a mistake.
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


@app.errorhandler(413)
def handle_file_too_large(_error):
    return jsonify({
        "reply": "This file is too large. Please upload an image under 8MB.",
        "answer": "This file is too large. Please upload an image under 8MB.",
        "success": False,
        "source": "upload_too_large",
        "fallback": True,
        "escalation_ready": False,
        "escalation_required": False,
    }), 413


CORS(
    app,
    resources={r"/*": {"origins": [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://ai-powered-wiki-training-assistant.vercel.app",
        "https://ai-powered-wiki-training-assistant-l68o9pdok.vercel.app",
        "https://ai-powered-wiki-training-assistant-l68o9pdok.vercel.app"
    ]}},
    supports_credentials=True,
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"]
)

# =========================
# FILE UPLOAD CONFIG
# =========================

# Save uploaded article files inside the same static folder served by Flask.
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "heic", "heif", "pdf", "doc", "docx"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_article_attachment(file):
    if not file or file.filename == "":
        return None, None

    if not allowed_file(file.filename):
        return None, None

    filename = secure_filename(file.filename)
    unique_filename = f"{int(time.time())}_{filename}"

    file_path = UPLOAD_FOLDER / unique_filename
    file.save(str(file_path))

    attachment_url = f"/static/uploads/articles/{unique_filename}"
    attachment_type = file.content_type

    return attachment_url, attachment_type



def save_article_attachments(files):
    saved_files = []

    for file in files:
        if not file or file.filename == "":
            continue

        if not allowed_file(file.filename):
            continue

        filename = secure_filename(file.filename)
        unique_filename = f"{int(time.time() * 1000)}_{filename}"

        file_path = UPLOAD_FOLDER / unique_filename
        file.save(str(file_path))

        saved_files.append({
            "url": f"/static/uploads/articles/{unique_filename}",
            "type": file.content_type,
            "name": filename
        })

    return saved_files


def ensure_wiki_article_content_capacity(cursor):
    """
    wiki_article.content was originally created as TEXT (64KB limit).
    Pasted screenshots inserted as inline HTML can easily exceed that,
    causing the UPDATE/INSERT to fail. Widen it to MEDIUMTEXT (16MB) once.
    """
    try:
        cursor.execute("""
            SELECT DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'wiki_article'
              AND COLUMN_NAME = 'content'
            LIMIT 1
        """)
        column_info = cursor.fetchone() or {}
        current_type = str(column_info.get("DATA_TYPE", "")).lower()

        if current_type in ("mediumtext", "longtext"):
            return

        cursor.execute("ALTER TABLE wiki_article MODIFY COLUMN content MEDIUMTEXT")
    except Exception as error:
        print("ENSURE WIKI ARTICLE CONTENT CAPACITY ERROR:", error)


def save_chat_image(file):
    """
    Save an upload from AI Chat or Escalation.
    The function name is kept as save_chat_image so existing routes still work,
    but it now supports mobile camera photos, images, PDF, DOC and DOCX files.
    """
    if not file or file.filename == "":
        return None, None

    if not allowed_file(file.filename):
        return None, None

    filename = secure_filename(file.filename)
    unique_filename = f"{int(time.time() * 1000)}_{filename}"

    file_path = CHAT_UPLOAD_FOLDER / unique_filename
    file.save(str(file_path))

    attachment_url = f"/static/uploads/chat/{unique_filename}"
    attachment_type = file.content_type or "application/octet-stream"

    return attachment_url, attachment_type

def extract_image_search_text(image_url, original_filename, question):
    filename_text = str(original_filename or "")

    # Remove extension
    filename_text = filename_text.rsplit(".", 1)[0]

    # Make filename searchable
    filename_text = (
        filename_text
        .replace("_", " ")
        .replace("-", " ")
        .replace(".", " ")
    )

    filename_text = " ".join(filename_text.split()).strip()

    q = str(question or "").lower().strip()

    generic_image_questions = {
        "what is this image",
        "what is this image?",
        "what is this photo",
        "what is this photo?",
        "what is this picture",
        "what is this picture?",
        "identify this image",
        "identify this photo",
        "can you identify this image",
        "can you identify this photo",
    }

    # IMPORTANT:
    # If staff asks a generic image question, do NOT search "what is this image".
    # Only use filename keywords first, for example phoenix_bird.jpg -> phoenix bird.
    if q in generic_image_questions:
        return filename_text

    # If staff gives useful words, combine both.
    # Example: question = "is this bird?", filename = "phoenix_bird"
    # Search text = "is this bird phoenix bird"
    combined_text = f"{question} {filename_text}".strip()

    return combined_text

def get_local_image_path_from_url(image_url):
    """
    Convert stored image URL like:
    /static/uploads/chat/xxx.jpg

    into the real backend file path.
    """
    image_url = str(image_url or "").strip()

    if not image_url:
        return None

    if "/static/" in image_url:
        image_url = image_url[image_url.index("/static/"):]

    if image_url.startswith("/static/"):
        relative_path = image_url.replace("/static/", "", 1)
        return STATIC_DIR / relative_path

    if image_url.startswith("static/"):
        relative_path = image_url.replace("static/", "", 1)
        return STATIC_DIR / relative_path

    return None


def build_visual_image_match_result(row, similarity_score):
    answer = row.get("answer") or row.get("image_caption") or ""
    image_url = row.get("image_url")
    image_type = row.get("image_type")

    return standardize_ai_response({
        "reply": answer,
        "answer": answer,
        "confidence": round(float(similarity_score), 4),
        "score": round(float(similarity_score), 4),
        "source": "visual_image_match",
        "final_source": "visual_image_match",
        "served_by": "image_embedding_retrieval",
        "fallback": False,
        "escalation_ready": False,
        "escalation_required": False,
        "image_url": image_url,
        "image_type": image_type,
        "attachment_url": image_url,
        "attachment_type": image_type,
        "image_files": (
            [{"url": image_url, "type": image_type}]
            if image_url
            else []
        ),
        "context": {
            "image_id": row.get("image_id"),
            "source_type": row.get("source_type"),
            "source_id": row.get("source_id"),
            "similarity_score": round(float(similarity_score), 4),
        }
    })


# =========================
# MULTI-STAGE IMAGE + QUESTION RETRIEVAL
# =========================
#
# Root cause of the old strict matching: it only compared the uploaded photo
# against other stored photos with a single hard threshold (0.85) and a
# confusability gap check. A different angle/background/lighting/colour of
# the SAME item drops raw image-to-image cosine similarity well below 0.85,
# so the whole image signal was discarded and the system fell back to
# filename-only text search -- the AI never got a chance to reason about
# "this looks like a dustbin" vs "this looks nothing like a dustbin".
#
# CLIP (the model already loaded in image_embedding_helper.py) puts images
# AND text in the same embedding space, so the fix below also compares the
# uploaded photo directly against each Knowledge Base image's caption /
# keywords / answer text. That is what lets a different-coloured, different
# angle dustbin still match "dustbin" without any hard-coded object rules --
# no new hard-coded keyword list, no manual labelling required.

# In-memory caches (per Flask worker process). These are best-effort speed
# optimisations, not a source of truth -- losing them on restart is fine.
IMAGE_TEXT_EMBEDDING_CACHE = {}   # image_id -> (text_hash, text_embedding_json)
UPLOADED_IMAGE_EMBEDDING_CACHE = {}  # file_hash -> (timestamp, embedding_json)
UPLOADED_IMAGE_CACHE_MAX = 200
UPLOADED_IMAGE_CACHE_TTL_SECONDS = 600

HIGH_CONFIDENCE_THRESHOLD = 0.78
HIGH_CONFIDENCE_MIN_GAP = 0.04
MEDIUM_CONFIDENCE_THRESHOLD = 0.45
MAX_RELATED_OPTIONS = 3


def _row_searchable_text(row):
    return " ".join([
        str(row.get("image_caption") or ""),
        str(row.get("image_keywords") or ""),
        str(row.get("question") or ""),
        str(row.get("answer") or ""),
    ]).strip()


def _hash_text(text):
    return hashlib.md5(str(text or "").encode("utf-8", errors="ignore")).hexdigest()


def _get_row_text_embedding(row):
    """
    Text embeddings for existing Knowledge Base images are computed once and
    reused. They are only regenerated when the underlying caption/keywords/
    answer text actually changes (tracked by a content hash), so normal chat
    traffic never re-triggers the AI provider for unchanged KB content.
    """
    if not create_text_embedding:
        return None

    image_id = row.get("image_id")
    text = _row_searchable_text(row)

    if not text:
        return None

    text_hash = _hash_text(text)
    cached = IMAGE_TEXT_EMBEDDING_CACHE.get(image_id)

    if cached and cached[0] == text_hash:
        return cached[1]

    embedding = create_text_embedding(text)

    if embedding:
        IMAGE_TEXT_EMBEDDING_CACHE[image_id] = (text_hash, embedding)

    return embedding


def _get_uploaded_image_embedding(uploaded_image_path):
    """
    Duplicate-submission protection: hashing the uploaded file bytes and
    reusing a recent embedding avoids re-calling the AI provider when a
    staff member re-sends the same photo (slow network retry, accidental
    double tap, etc).
    """
    try:
        file_bytes = Path(uploaded_image_path).read_bytes()
    except Exception as error:
        print("READ UPLOADED IMAGE ERROR:", error)
        return None, None

    file_hash = hashlib.md5(file_bytes).hexdigest()
    now = time.time()

    cached = UPLOADED_IMAGE_EMBEDDING_CACHE.get(file_hash)
    if cached and (now - cached[0]) < UPLOADED_IMAGE_CACHE_TTL_SECONDS:
        return cached[1], file_hash

    embedding = create_image_embedding(uploaded_image_path)

    if embedding:
        if len(UPLOADED_IMAGE_EMBEDDING_CACHE) >= UPLOADED_IMAGE_CACHE_MAX:
            oldest_key = min(
                UPLOADED_IMAGE_EMBEDDING_CACHE,
                key=lambda key: UPLOADED_IMAGE_EMBEDDING_CACHE[key][0]
            )
            UPLOADED_IMAGE_EMBEDDING_CACHE.pop(oldest_key, None)

        UPLOADED_IMAGE_EMBEDDING_CACHE[file_hash] = (now, embedding)

    return embedding, file_hash


def build_related_image_option(row, combined_score, match_reason):
    answer = row.get("answer") or row.get("image_caption") or ""
    title = row.get("question") or row.get("image_caption") or "Related item"
    image_url = row.get("image_url")
    image_type = row.get("image_type")

    return {
        "label": title,
        "title": title,
        "category": None,
        "source": f"image_retrieval_{row.get('source_type') or 'approved'}",
        "answer": answer,
        "reply": answer,
        "confidence": round(float(combined_score), 4),
        "match_reason": match_reason,
        "confidence_label": get_confidence_label(combined_score),
        "image_url": image_url,
        "image_type": image_type,
        "attachment_url": image_url,
        "attachment_type": image_type,
        "image_files": (
            [{"url": image_url, "type": image_type}]
            if image_url
            else []
        ),
    }


def search_visual_image_match(uploaded_image_url, question="", threshold=HIGH_CONFIDENCE_THRESHOLD, min_gap=HIGH_CONFIDENCE_MIN_GAP):
    """
    Multi-stage image + question retrieval against approved image_retrieval
    records.

    Stage 1: encode the uploaded photo with CLIP.
    Stage 2: score every candidate using THREE signals combined --
             (a) image-to-image similarity when a stored photo exists,
             (b) image-to-text similarity against that record's own
                 caption/keywords/answer (this is what generalises across
                 angle, colour, size and lighting -- CLIP recognises the
                 object itself, not just the pixels), and
             (c) how well the record's text matches the staff member's
                 written question (so image understanding and question
                 intent are combined, not searched separately).
    Stage 3/4: rank and tier into HIGH (answer directly), MEDIUM (return the
               best related options instead of failing), or LOW (let the
               caller fall back to the existing text-based KB/SOP search).

    Returns:
      - a single answer dict (backward compatible "direct answer") on HIGH confidence
      - a dict with type "multiple_choice" and up to 3 options on MEDIUM confidence
      - None on LOW confidence / no usable signal, so the caller keeps using
        the existing text fallback and escalation flow unchanged.
    """
    if not IMAGE_EMBEDDING_AVAILABLE or not create_image_embedding or not cosine_similarity_from_json:
        print("IMAGE EMBEDDING NOT AVAILABLE:", IMAGE_EMBEDDING_LOAD_ERROR)
        return None

    uploaded_image_path = get_local_image_path_from_url(uploaded_image_url)

    if not uploaded_image_path:
        return None

    uploaded_embedding, _file_hash = _get_uploaded_image_embedding(uploaded_image_path)

    if not uploaded_embedding:
        return None

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT *
            FROM image_retrieval
            WHERE approval_status = 'approved'
              AND visual_match_enabled = 1
            ORDER BY
                CASE
                    WHEN source_type = 'knowledge_base' THEN 1
                    WHEN source_type = 'approved_escalation' THEN 2
                    ELSE 3
                END,
                created_at DESC
            LIMIT 200
        """)

        rows = cursor.fetchall() or []
        scored_rows = []

        for row in rows:
            image_sim = 0.0
            has_image_sim = False

            if row.get("image_embedding"):
                try:
                    image_sim = float(cosine_similarity_from_json(
                        uploaded_embedding,
                        row.get("image_embedding")
                    ) or 0.0)
                    has_image_sim = True
                except Exception:
                    image_sim = 0.0

            text_sim = 0.0
            try:
                row_text_embedding = _get_row_text_embedding(row)
                if row_text_embedding:
                    text_sim = float(cosine_similarity_from_json(
                        uploaded_embedding,
                        row_text_embedding
                    ) or 0.0)
            except Exception:
                text_sim = 0.0

            keyword_sim = db_similarity_ratio(question, _row_searchable_text(row)) if question else 0.0

            if has_image_sim:
                combined = (0.55 * image_sim) + (0.30 * text_sim) + (0.15 * keyword_sim)
                dominant = "visual similarity to a known photo" if image_sim >= text_sim else "matches the item description"
            else:
                combined = (0.65 * text_sim) + (0.35 * keyword_sim)
                dominant = "matches the item description" if text_sim >= keyword_sim else "matches your question"

            scored_rows.append((combined, row, dominant, image_sim if has_image_sim else 0.0))

        scored_rows.sort(key=lambda item: item[0], reverse=True)

        if not scored_rows:
            return None

        best_score, best_row, _best_reason, best_image_sim = scored_rows[0]
        second_score = scored_rows[1][0] if len(scored_rows) > 1 else 0.0

        print("BEST IMAGE MATCH SCORE:", round(best_score, 4), "raw image_sim:", round(best_image_sim, 4))

        for debug_score, debug_row, debug_reason, debug_image_sim in scored_rows[:5]:
            print(
                "IMAGE MATCH CANDIDATE:",
                "image_id=", debug_row.get("image_id"),
                "score=", round(debug_score, 4),
                "reason=", debug_reason,
                "answer=", str(debug_row.get("answer") or "")[:80]
            )

        # HIGH confidence: answer directly, same as the previous behaviour.
        # A near-duplicate photo (raw image-to-image similarity alone, the
        # original 0.85 rule) always qualifies on its own -- it shouldn't
        # need a strong text/keyword signal too, since the photo itself is
        # already near-conclusive. Otherwise the blended score has to clear
        # the bar, which is what lets a strong combination of a decent photo
        # match + matching description + matching question also count.
        is_near_duplicate_photo = best_image_sim >= threshold
        is_high_confidence_blend = best_score >= threshold

        if (is_near_duplicate_photo or is_high_confidence_blend) and (second_score == 0.0 or (best_score - second_score) >= min_gap):
            return build_visual_image_match_result(best_row, max(best_score, best_image_sim if is_near_duplicate_photo else 0.0))

        # MEDIUM confidence: do not fail -- offer the best related options
        # instead of forcing the user back to a plain text search.
        if best_score >= MEDIUM_CONFIDENCE_THRESHOLD:
            seen_titles = set()
            options = []

            for score, row, reason, _row_image_sim in scored_rows:
                if score < MEDIUM_CONFIDENCE_THRESHOLD:
                    break

                title_key = str(row.get("question") or row.get("image_caption") or "").lower().strip()

                if not title_key or title_key in seen_titles:
                    continue

                seen_titles.add(title_key)
                options.append(build_related_image_option(row, score, reason))

                if len(options) >= MAX_RELATED_OPTIONS:
                    break

            if not options:
                return None

            return standardize_ai_response({
                "type": "multiple_choice",
                "reply": (
                    "I'm not fully certain of the exact item, but here are the most "
                    "relevant instructions I found for what this looks like:"
                ),
                "answer": (
                    "I'm not fully certain of the exact item, but here are the most "
                    "relevant instructions I found for what this looks like:"
                ),
                "score": best_score,
                "confidence": best_score,
                "confidence_label": get_confidence_label(best_score),
                "source": "visual_image_match_related",
                "final_source": "visual_image_match_related",
                "served_by": "image_embedding_retrieval",
                "fallback": False,
                "escalation_ready": False,
                "escalation_required": False,
                "options": options,
                "context": {
                    "match_tier": "medium",
                },
            })

        print("VISUAL MATCH REJECTED: below related-item threshold")
        return None

    except Exception as error:
        print("SEARCH VISUAL IMAGE MATCH ERROR:", error)
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# GEMINI VISION RELEVANCE CHECK
#
# The CLIP pipeline above only "knows" what it has already seen in the
# Knowledge Base, so it can't reliably tell a selfie/meme/blank photo apart
# from a genuinely new work item it just doesn't have a KB photo for yet.
# This step is a second opinion, only spent when CLIP couldn't already
# answer confidently, so normal high-confidence matches never touch it and
# never cost an API call.
# =========================
VISION_RELEVANCE_PROMPT = """You are an image understanding assistant for Jungle House internal staff training system.

Your job is to identify whether the uploaded image is related to Jungle House work, products, equipment, stocktake, SOP, opening, closing, POS, display, cabinet, storage, customer service, or internal operations.

Return ONLY valid JSON. No markdown, no code fences, no extra text.

Fields:
- isWorkRelated: boolean
- confidence: number between 0 and 1
- detectedObjects: array of strings
- possibleAliases: array of strings
- imageSummary: string
- irrelevantReason: string or null

Important:
- Detect objects even if shown from front, back, side, tilted, close-up, far away, or a different angle.
- If the image is random, personal, unclear, a meme, a selfie, food unrelated to work, or otherwise not related to work, set isWorkRelated to false.
- Do not answer the user's question here.
- Only describe the image and whether it is work-related."""

GEMINI_VISION_CACHE = {}  # file_hash -> (timestamp, result_dict or None)
GEMINI_VISION_CACHE_MAX = 200
GEMINI_VISION_CACHE_TTL_SECONDS = 600


def _parse_vision_json_reply(raw_text):
    text = str(raw_text or "").strip()

    # Gemini sometimes wraps JSON in ```json ... ``` even when told not to.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*", "", text).strip()
        text = text.rsplit("```", 1)[0].strip()

    parsed = json.loads(text)

    return {
        "isWorkRelated": bool(parsed.get("isWorkRelated", False)),
        "confidence": float(parsed.get("confidence", 0.0) or 0.0),
        "detectedObjects": [str(item) for item in (parsed.get("detectedObjects") or [])][:10],
        "possibleAliases": [str(item) for item in (parsed.get("possibleAliases") or [])][:10],
        "imageSummary": str(parsed.get("imageSummary") or ""),
        "irrelevantReason": parsed.get("irrelevantReason"),
    }


def analyze_uploaded_image_with_vision(image_path, file_hash=None):
    """
    Ask the manager-configured Gemini model what the uploaded photo shows
    and whether it's work-related. Returns None (never raises) whenever
    vision isn't usable for any reason -- not configured, wrong provider,
    network/timeout error, bad JSON back -- so callers always have a clean
    "fall back to the existing text/CLIP pipeline" path.
    """
    if not AI_PROVIDER_SERVICE_AVAILABLE or not ai_provider_service:
        return None

    if file_hash:
        cached = GEMINI_VISION_CACHE.get(file_hash)
        if cached and (time.time() - cached[0]) < GEMINI_VISION_CACHE_TTL_SECONDS:
            return cached[1]

    try:
        raw_reply = ai_provider_service.generate_ai_vision_reply(
            VISION_RELEVANCE_PROMPT, image_path, timeout=20
        )
        result = _parse_vision_json_reply(raw_reply)
    except ai_provider_service.AIProviderNotConfiguredError:
        result = None
    except ai_provider_service.AIProviderVisionUnsupportedError:
        result = None
    except Exception as error:
        print("GEMINI VISION ERROR:", error)
        result = None

    if file_hash:
        if len(GEMINI_VISION_CACHE) >= GEMINI_VISION_CACHE_MAX:
            oldest_key = min(GEMINI_VISION_CACHE, key=lambda key: GEMINI_VISION_CACHE[key][0])
            GEMINI_VISION_CACHE.pop(oldest_key, None)

        GEMINI_VISION_CACHE[file_hash] = (time.time(), result)

    return result


def build_image_irrelevant_response(vision_result):
    reason = (vision_result or {}).get("irrelevantReason") or ""
    message = "This image does not look related to Jungle House work or Knowledge Base. Please upload a relevant work image or ask a clear work-related question."

    return standardize_ai_response({
        "type": "text",
        "reply": message,
        "answer": message,
        "score": 0.0,
        "confidence": 0.0,
        "source": "vision_irrelevant_image",
        "final_source": "vision_irrelevant_image",
        "served_by": "vision_relevance_check",
        "fallback": False,
        "escalation_ready": False,
        "escalation_required": False,
        "context": {
            "rejected": True,
            "irrelevant_reason": reason,
            "image_summary": (vision_result or {}).get("imageSummary", ""),
        },
    })


def build_vision_augmented_question(question, vision_result):
    """
    Combine the detected object(s) with the staff member's own question so
    the existing KB/SOP text search (unchanged) receives both signals
    together, per "question meaning first, image second" -- the image only
    fills in what "this"/"it" refers to.
    """
    detected = list((vision_result or {}).get("detectedObjects") or [])
    aliases = list((vision_result or {}).get("possibleAliases") or [])

    object_terms = " ".join(dict.fromkeys(detected + aliases))
    question = str(question or "").strip()

    if object_terms and question:
        return f"{question} {object_terms}".strip()

    return object_terms or question


@app.route("/static/uploads/articles/<path:filename>", methods=["GET"])
def serve_article_attachment(filename):
    file_path = UPLOAD_FOLDER / filename

    print("REQUESTED ARTICLE ATTACHMENT:", filename)
    print("UPLOAD_FOLDER:", UPLOAD_FOLDER)
    print("FILE EXISTS:", file_path.exists())

    if not file_path.exists():
        return jsonify({
            "message": "Attachment file not found on server.",
            "filename": filename,
            "upload_folder": str(UPLOAD_FOLDER),
            "expected_path": str(file_path)
        }), 404

    return send_from_directory(str(UPLOAD_FOLDER), filename)

@app.route("/static/uploads/chat/<path:filename>", methods=["GET"])
def serve_chat_upload(filename):
    file_path = CHAT_UPLOAD_FOLDER / filename

    print("REQUESTED CHAT IMAGE:", filename)
    print("CHAT_UPLOAD_FOLDER:", CHAT_UPLOAD_FOLDER)
    print("FILE EXISTS:", file_path.exists())

    if not file_path.exists():
        return jsonify({
            "message": "Chat uploaded image not found on server.",
            "filename": filename,
            "chat_upload_folder": str(CHAT_UPLOAD_FOLDER),
            "expected_path": str(file_path)
        }), 404

    return send_from_directory(str(CHAT_UPLOAD_FOLDER), filename)

@app.route("/api/debug/chat-uploads", methods=["GET"])
def debug_chat_uploads():
    files = []

    if CHAT_UPLOAD_FOLDER.exists():
        files = [file.name for file in CHAT_UPLOAD_FOLDER.iterdir() if file.is_file()]

    return jsonify({
        "chat_upload_folder": str(CHAT_UPLOAD_FOLDER),
        "folder_exists": CHAT_UPLOAD_FOLDER.exists(),
        "files": files
    }), 200

@app.route("/static/sop_images/<path:filename>", methods=["GET"])
def serve_sop_image(filename):
    clean_filename = str(filename or "").replace("\\", "/").strip().lstrip("/")
    file_path = SOP_IMAGE_FOLDER / clean_filename

    print("REQUESTED SOP IMAGE:", clean_filename)
    print("SOP_IMAGE_FOLDER:", SOP_IMAGE_FOLDER)
    print("EXACT FILE EXISTS:", file_path.exists())

    if file_path.exists() and file_path.is_file():
        return send_from_directory(str(file_path.parent), file_path.name)

    # Fallback: sometimes the AI dataset stores only sop_images/kiosk_opening/step3_1.jpg,
    # while the server path differs slightly. Search by basename inside sop_images.
    basename = Path(clean_filename).name
    matched_file = None

    if basename and SOP_IMAGE_FOLDER.exists():
        for candidate in SOP_IMAGE_FOLDER.rglob(basename):
            if candidate.exists() and candidate.is_file():
                matched_file = candidate
                break

    print("MATCHED SOP IMAGE:", matched_file)

    if matched_file:
        return send_from_directory(str(matched_file.parent), matched_file.name)

    return jsonify({
        "message": "SOP image file not found on server.",
        "filename": clean_filename,
        "sop_image_folder": str(SOP_IMAGE_FOLDER),
        "expected_path": str(file_path)
    }), 404


@app.route("/api/debug/sop-images", methods=["GET"])
def debug_sop_images():
    files = []

    if SOP_IMAGE_FOLDER.exists():
        files = [str(file.relative_to(SOP_IMAGE_FOLDER)).replace("\\", "/") for file in SOP_IMAGE_FOLDER.rglob("*") if file.is_file()]

    return jsonify({
        "sop_image_folder": str(SOP_IMAGE_FOLDER),
        "folder_exists": SOP_IMAGE_FOLDER.exists(),
        "files": files
    }), 200


@app.route("/api/debug/static-files", methods=["GET"])
def debug_static_files():
    files = []

    if STATIC_DIR.exists():
        files = [str(file.relative_to(STATIC_DIR)).replace("\\", "/") for file in STATIC_DIR.rglob("*") if file.is_file()]

    return jsonify({
        "static_folder": str(STATIC_DIR),
        "folder_exists": STATIC_DIR.exists(),
        "files": files
    }), 200

@app.route("/api/debug/uploads", methods=["GET"])
def debug_uploads():
    files = []

    if UPLOAD_FOLDER.exists():
        files = [file.name for file in UPLOAD_FOLDER.iterdir() if file.is_file()]

    return jsonify({
        "upload_folder": str(UPLOAD_FOLDER),
        "folder_exists": UPLOAD_FOLDER.exists(),
        "files": files
    }), 200


# =========================
# DATABASE CONNECTION
# =========================
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="shuttle.proxy.rlwy.net",
            port=26909,
            user="root",
            password="zzUtzEvBsOnHpeUqaHCIJOdilqfoHxHI",
            database="railway",
        )
        return conn
    except mysql.connector.Error as err:
        print("DATABASE CONNECTION ERROR:", err)
        raise


# =========================
# HELPER FUNCTIONS
# =========================
def safe_count_query(cursor, query, params=None):
    try:
        cursor.execute(query, params or ())
        result = cursor.fetchone()
        return result["total"] if result and "total" in result and result["total"] is not None else 0
    except Exception as e:
        print("safe_count_query error:", e)
        return 0


def safe_list_query(cursor, query, params=None):
    try:
        cursor.execute(query, params or ())
        return cursor.fetchall()
    except Exception as e:
        print("safe_list_query error:", e)
        return []


def format_datetime_value(value):
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %I:%M %p")
    return value


def format_user_dates(user_row):
    if user_row and "created_at" in user_row:
        user_row["created_at"] = format_datetime_value(user_row["created_at"])
    return user_row


def get_user_profile_payload(user_row):
    if not user_row:
        return None

    user_row = format_user_dates(user_row)

    return {
        "id": user_row.get("user_id"),
        "name": user_row.get("full_name"),
        "full_name": user_row.get("full_name"),
        "email": user_row.get("email"),
        "role": user_row.get("role_name"),
        "status": user_row.get("status"),
        "created_at": user_row.get("created_at"),
    }


def record_login_history(cursor, user_id=None, email=None, full_name=None, status="failed"):
    """
    Save login attempt for Security / Monitoring.
    user_id can be NULL so failed login for unknown email can still be recorded.
    """
    try:
        cursor.execute("""
            INSERT INTO login_history
            (user_id, email, full_name, login_status, ip_address, device_info)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            email,
            full_name,
            status,
            request.remote_addr,
            request.headers.get("User-Agent")
        ))
    except Exception as error:
        print("LOGIN HISTORY INSERT FAILED:", error)


def add_audit_log(actor_id=None, actor_name="System", action="", module="", description=""):
    """
    Save important system actions for Security / Monitoring audit log.
    This helper uses its own DB connection so it can be called safely from routes.
    """
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO audit_log
            (actor_id, actor_name, action, module, description)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            actor_id,
            actor_name,
            action,
            module,
            description
        ))

        conn.commit()

    except Exception as error:
        print("AUDIT LOG ERROR:", error)

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()




# =========================
# REGISTRATION APPROVAL HELPERS
# =========================
APPROVER_ROLES = {"manager", "admin", "teamlead", "team lead"}


# Only approved internal/company email domains can submit registration.
# Change this value in your .env / Render / Railway environment variables.
# Example: ALLOWED_REGISTRATION_DOMAINS=junglehouse.com,junglehouse.my
ALLOWED_REGISTRATION_DOMAINS = [
    domain.strip().lower().lstrip("@")
    for domain in os.getenv("ALLOWED_REGISTRATION_DOMAINS", "junglehouse.com").split(",")
    if domain.strip()
]

REGISTRATION_REVIEW_HOURS = int(os.getenv("REGISTRATION_REVIEW_HOURS", "24"))
EMAIL_VERIFICATION_TOKEN_HOURS = int(os.getenv("EMAIL_VERIFICATION_TOKEN_HOURS", "24"))
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").strip().rstrip("/")
API_PUBLIC_URL = os.getenv("API_PUBLIC_URL", "").strip().rstrip("/")


def get_email_domain(email):
    email = str(email or "").strip().lower()

    if "@" not in email:
        return ""

    return email.rsplit("@", 1)[-1]


def is_valid_email_format(email):
    email = str(email or "").strip().lower()
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def is_allowed_registration_email(email):
    """
    Cybersecurity rule:
    only users with approved internal/company email domains can register.
    The account is still pending until manager/team lead approval.
    """
    if not is_valid_email_format(email):
        return False

    domain = get_email_domain(email)
    return domain in ALLOWED_REGISTRATION_DOMAINS


def allowed_domain_message():
    if not ALLOWED_REGISTRATION_DOMAINS:
        return "Please register using an approved staff email address."

    readable_domains = ", ".join([f"@{domain}" for domain in ALLOWED_REGISTRATION_DOMAINS])
    return f"Please register using an approved staff email domain: {readable_domains}."


def send_email_safe(to_email, subject, body):
    """
    Optional email notification helper.
    It will not break the system if SMTP is not configured yet.

    Required environment variables when you want real email sending:
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM_EMAIL
    """
    to_email = str(to_email or "").strip()

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM_EMAIL", smtp_user).strip()
    smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() != "false"

    if not to_email or not smtp_host or not smtp_from:
        print("EMAIL SKIPPED: SMTP is not configured.")
        return False

    try:
        message = EmailMessage()
        message["From"] = smtp_from
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            if smtp_use_tls:
                server.starttls()

            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)

            server.send_message(message)

        return True

    except Exception as error:
        print("SEND EMAIL SAFE ERROR:", error)
        return False




def ensure_email_verification_table(cursor):
    """
    Creates the email verification table automatically if it does not exist.
    You can also create it using the SQL migration file.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_verifications (
            verification_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            email VARCHAR(255) NOT NULL,
            token_hash CHAR(64) NOT NULL,
            expires_at DATETIME NOT NULL,
            verified_at DATETIME NULL,
            used_at DATETIME NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_email_verifications_user_id (user_id),
            INDEX idx_email_verifications_token_hash (token_hash),
            INDEX idx_email_verifications_email (email),
            CONSTRAINT fk_email_verifications_user
                FOREIGN KEY (user_id) REFERENCES users(user_id)
                ON DELETE CASCADE
        )
    """)


def hash_email_verification_token(token):
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def create_email_verification_token(cursor, user_id, email):
    ensure_email_verification_table(cursor)

    # Invalidate older unused links for this user so only the newest link is useful.
    cursor.execute("""
        UPDATE email_verifications
        SET used_at = NOW()
        WHERE user_id = %s
          AND verified_at IS NULL
          AND used_at IS NULL
    """, (user_id,))

    token = secrets.token_urlsafe(32)
    token_hash = hash_email_verification_token(token)
    expires_at = datetime.utcnow() + timedelta(hours=EMAIL_VERIFICATION_TOKEN_HOURS)

    cursor.execute("""
        INSERT INTO email_verifications (user_id, email, token_hash, expires_at)
        VALUES (%s, %s, %s, %s)
    """, (user_id, email, token_hash, expires_at))

    return token


def get_public_request_base_url():
    """
    Railway terminates TLS at its edge and forwards requests to Flask over
    plain HTTP, so request.host_url/url_root normally resolve to http://
    even though the public site is always served over https. Loading an
    http:// resource (e.g. an <img src>) from the https:// frontend gets
    silently blocked by the browser as mixed content, so force https here.
    """
    try:
        base_url = request.host_url.rstrip("/")
    except RuntimeError:
        return "http://localhost:4000"

    if base_url.startswith("http://"):
        base_url = "https://" + base_url[len("http://"):]

    return base_url


def get_verification_link(token):
    base_url = API_PUBLIC_URL or get_public_request_base_url()

    return f"{base_url}/api/auth/verify-email?token={token}"


def send_email_verification_link(full_name, email, token):
    verification_link = get_verification_link(token)
    subject = "Jungle House AI Wiki - Verify your email"
    body = f"""Hi {full_name},

Thank you for registering for the Jungle House AI Wiki system.

Please verify your email address using this link:
{verification_link}

This link will expire in {EMAIL_VERIFICATION_TOKEN_HOURS} hours.

After your email is verified, a manager or team lead will review your account registration within {REGISTRATION_REVIEW_HOURS} hours. You will receive another email after your account is approved or declined.

If you did not request this account, please ignore this email.

Thank you,
Jungle House AI Wiki Team
"""
    return send_email_safe(email, subject, body)


def is_user_email_verified(cursor, user_id):
    ensure_email_verification_table(cursor)

    cursor.execute("""
        SELECT verification_id, verified_at
        FROM email_verifications
        WHERE user_id = %s
          AND verified_at IS NOT NULL
        ORDER BY verified_at DESC
        LIMIT 1
    """, (user_id,))

    row = cursor.fetchone()
    return bool(row)


def get_user_email_verified_at(cursor, user_id):
    ensure_email_verification_table(cursor)

    cursor.execute("""
        SELECT verified_at
        FROM email_verifications
        WHERE user_id = %s
          AND verified_at IS NOT NULL
        ORDER BY verified_at DESC
        LIMIT 1
    """, (user_id,))

    row = cursor.fetchone()
    if not row:
        return None

    if isinstance(row, dict):
        return row.get("verified_at")

    return row[0] if row else None


def registration_success_redirect(message_key="email_verified"):
    if FRONTEND_URL:
        return redirect(f"{FRONTEND_URL}/login?{message_key}=1")

    return jsonify({"message": "Email verified successfully. You may return to the login page."}), 200

def send_registration_received_email(full_name, email):
    subject = "Jungle House AI Wiki - Registration received"
    body = f"""Hi {full_name},

Your account registration has been received.

For security reasons, your account is currently pending verification. A manager or team lead will review and approve or decline your registration within {REGISTRATION_REVIEW_HOURS} hours.

You will receive another email after the decision has been made.

Thank you,
Jungle House AI Wiki Team
"""
    return send_email_safe(email, subject, body)


def get_table_columns_safe(cursor, table_name):
    cursor.execute(f"SHOW COLUMNS FROM {table_name}")
    rows = cursor.fetchall()
    columns = set()

    for row in rows:
        if isinstance(row, dict):
            column_name = row.get("Field")
        else:
            column_name = row[0] if row else None

        if column_name:
            columns.add(str(column_name))

    return columns


def is_registration_approver(cursor, actor_id):
    if not actor_id:
        return False

    cursor.execute("""
        SELECT r.role_name, u.status
        FROM users u
        JOIN roles r ON u.role_id = r.role_id
        WHERE u.user_id = %s
        LIMIT 1
    """, (actor_id,))

    actor = cursor.fetchone()

    if not actor:
        return False

    role_name = str(actor.get("role_name", "")).strip().lower()
    status = str(actor.get("status", "")).strip().lower()

    return role_name in APPROVER_ROLES and status == "active"


# =========================
# REGISTRATION KEY HELPERS
#
# Replaces the old company-email-domain gate: anyone can register with any
# email as long as they have a valid, unused registration key. Keys are
# single-use forever -- deactivating the account that used a key must never
# free it up again, so a key only ever moves unused -> used (or -> revoked).
# =========================
def is_registration_key_manager(cursor, actor_id):
    if not actor_id:
        return False

    cursor.execute("""
        SELECT r.role_name, u.status
        FROM users u
        JOIN roles r ON u.role_id = r.role_id
        WHERE u.user_id = %s
        LIMIT 1
    """, (actor_id,))

    actor = cursor.fetchone()

    if not actor:
        return False

    role_name = str(actor.get("role_name", "")).strip().lower()
    status = str(actor.get("status", "")).strip().lower()

    return role_name == "manager" and status == "active"


def is_ai_settings_manager(cursor, actor_id):
    if not actor_id:
        return False

    cursor.execute("""
        SELECT r.role_name, u.status
        FROM users u
        JOIN roles r ON u.role_id = r.role_id
        WHERE u.user_id = %s
        LIMIT 1
    """, (actor_id,))

    actor = cursor.fetchone()

    if not actor:
        return False

    role_name = str(actor.get("role_name", "")).strip().lower()
    status = str(actor.get("status", "")).strip().lower()

    return role_name == "manager" and status == "active"


def ensure_registration_keys_table(cursor):
    # Named staff_registration_keys (not registration_keys) on purpose --
    # a table called registration_keys already exists in this database from
    # an older/unrelated system (different schema, 42 real rows already in
    # it) that nothing in this app currently references. Using a distinct
    # name avoids any risk of colliding with that legacy data.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS staff_registration_keys (
            key_id INT AUTO_INCREMENT PRIMARY KEY,
            key_code VARCHAR(10) NOT NULL UNIQUE,
            status ENUM('unused', 'used', 'revoked') NOT NULL DEFAULT 'unused',
            created_by_user_id INT NULL,
            used_by_user_id INT NULL,
            used_by_email VARCHAR(255) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used_at DATETIME NULL,
            revoked_at DATETIME NULL,
            INDEX idx_staff_registration_keys_status (status),
            CONSTRAINT fk_staff_registration_keys_created_by
                FOREIGN KEY (created_by_user_id) REFERENCES users(user_id)
                ON DELETE SET NULL,
            CONSTRAINT fk_staff_registration_keys_used_by
                FOREIGN KEY (used_by_user_id) REFERENCES users(user_id)
                ON DELETE SET NULL
        )
    """)


def generate_registration_key_code():
    import string

    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(10))


def create_notification_safe(
    user_id=None,
    title="",
    detail="",
    notification_type="system",
    related_id=None,
    target_role=None,
    created_by=None
):
    """
    Safe notification insert.
    It only inserts columns that exist in your notification table.
    This prevents backend crash if your notification table structure changes.
    """
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        columns = get_table_columns_safe(cursor, "notification")

        payload = {}

        if "user_id" in columns:
            payload["user_id"] = user_id

        if "title" in columns:
            payload["title"] = title

        if "detail" in columns:
            payload["detail"] = detail

        if "message" in columns:
            payload["message"] = detail

        if "type" in columns:
            payload["type"] = notification_type

        if "related_id" in columns:
            payload["related_id"] = related_id

        if "target_role" in columns:
            payload["target_role"] = target_role

        if "created_by" in columns:
            payload["created_by"] = created_by

        if "is_read" in columns:
            payload["is_read"] = False

        if not payload:
            return

        insert_columns = list(payload.keys())
        placeholders = ", ".join(["%s"] * len(insert_columns))
        column_names = ", ".join(insert_columns)
        values = [payload[column] for column in insert_columns]

        cursor.execute(f"""
            INSERT INTO notification ({column_names})
            VALUES ({placeholders})
        """, tuple(values))

        conn.commit()

    except Exception as error:
        print("CREATE NOTIFICATION SAFE ERROR:", error)

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def notify_registration_approvers(new_user_id, full_name, email):
    """
    Notify active managers/admins/team leads that a new user is waiting for approval.
    """
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT u.user_id
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE LOWER(u.status) = 'active'
              AND LOWER(r.role_name) IN ('manager', 'admin', 'teamlead', 'team lead')
        """)

        approvers = cursor.fetchall() or []

        for approver in approvers:
            create_notification_safe(
                user_id=approver["user_id"],
                title="New account approval needed",
                detail=f"{full_name} ({email}) has registered and is waiting for account verification.",
                notification_type="registration",
                related_id=new_user_id,
                created_by=new_user_id
            )

    except Exception as error:
        print("NOTIFY REGISTRATION APPROVERS ERROR:", error)

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_user_contact_safe(user_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT full_name, email
            FROM users
            WHERE user_id = %s
            LIMIT 1
        """, (user_id,))

        return cursor.fetchone()

    except Exception as error:
        print("GET USER CONTACT SAFE ERROR:", error)
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def notify_registration_decision(user_id, approved=True, reason=""):
    user_contact = get_user_contact_safe(user_id) or {}
    full_name = user_contact.get("full_name") or "there"
    email = user_contact.get("email")

    if approved:
        title = "Account approved"
        detail = "Your account has been approved. You can now log in to the Jungle House AI Wiki system."
        subject = "Jungle House AI Wiki - Account approved"
        body = f"""Hi {full_name},

Your Jungle House AI Wiki account has been approved.

You can now log in using your registered email address.

Thank you,
Jungle House AI Wiki Team
"""
    else:
        title = "Account registration declined"
        detail = "Your account registration was declined."

        if reason:
            detail += f" Reason: {reason}"

        subject = "Jungle House AI Wiki - Registration declined"
        body = f"""Hi {full_name},

Your Jungle House AI Wiki account registration was declined.

Reason: {reason or 'No reason was provided.'}

Please contact your manager or team lead if you think this is a mistake.

Thank you,
Jungle House AI Wiki Team
"""

    create_notification_safe(
        user_id=user_id,
        title=title,
        detail=detail,
        notification_type="registration_decision",
        related_id=user_id
    )

    if email:
        send_email_safe(email, subject, body)


# =========================
# AI CHAT HELPERS
# =========================

def clean_question(value) -> str:
    text = str(value or "").strip()
    text = " ".join(text.split())
    if len(text) > 500:
        text = text[:500].strip()
    return text


def normalize_context(context) -> dict:
    if not isinstance(context, dict):
        return {}

    try:
        unclear_count = int(context.get("unclear_count", 0) or 0)
    except Exception:
        unclear_count = 0

    return {
        "title": str(context.get("title", "")).strip(),
        "category": str(context.get("category", "")).strip(),
        "section": str(context.get("section", "")).strip(),
        "last_step_number": context.get("last_step_number"),
        "unclear_count": unclear_count,
    }


def get_chat_memory_key(data: dict | None = None) -> str:
    data = data or {}
    user_id = data.get("user_id") or data.get("userId")
    if user_id:
        return f"user:{user_id}"
    return f"ip:{request.remote_addr or 'local'}"


def prepare_chat_context(data: dict | None = None) -> dict:
    data = data or {}
    request_context = normalize_context(data.get("context") or {})
    memory_context = normalize_context(AI_CHAT_MEMORY.get(get_chat_memory_key(data)) or {})

    merged_context = memory_context.copy()
    for key, value in request_context.items():
        if value not in [None, "", 0]:
            merged_context[key] = value

    return normalize_context(merged_context)


def remember_chat_context(data: dict | None, result: dict | None) -> None:
    result = result or {}
    result_context = normalize_context(result.get("context") or {})

    if result_context.get("title") or result_context.get("category") or result_context.get("unclear_count", 0) > 0:
        AI_CHAT_MEMORY[get_chat_memory_key(data)] = result_context
        return

    AI_CHAT_MEMORY.pop(get_chat_memory_key(data), None)


def ensure_log_files() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    expected_headers = [
        "timestamp", "question", "title", "category", "section", "type",
        "score", "confidence", "confidence_label", "source", "fallback",
        "fallback_message", "escalation_ready", "reply", "error"
    ]

    if not LOG_CSV.exists():
        with open(LOG_CSV, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(expected_headers)
        return

    try:
        with open(LOG_CSV, "r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            rows = list(reader)

        if rows and set(expected_headers).issubset(set(rows[0].keys())):
            return

        with open(LOG_CSV, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=expected_headers)
            writer.writeheader()
            for row in rows:
                writer.writerow({header: row.get(header, "") for header in expected_headers})
    except Exception as error:
        print("AI log header migration skipped:", error)

def get_last_answer_key(data: dict | None = None) -> str:
    data = data or {}
    user_id = data.get("user_id") or data.get("userId")

    if user_id:
        return f"user:{user_id}:last_answer"

    return f"ip:{request.remote_addr or 'local'}:last_answer"


def is_staff_not_satisfied(text: str) -> bool:
    text = clean_question(text).lower()

    phrases = [
        "you sure",
        "are you sure",
        "not what i want",
        "not what i mean",
        "i don't mean this",
        "i dont mean this",
        "not this",
        "not this one",
        "wrong",
        "wrong answer",
        "this is wrong",
        "not the content",
        "not related",
        "not correct",
        "i mean another",
        "i mean something else",
        "dont know",
        "don't know",
        "i dont know",
        "i don't know",
        "no idea",
        "not sure",
        "none of these",
        "not these",
    ]

    return any(phrase in text for phrase in phrases)

def should_escalate_generic_answer(question: str, result: dict | None) -> bool:
    result = result or {}

    source = str(result.get("source", "")).strip().lower()
    question_clean = clean_question(question).lower()

    # These are allowed broad category questions.
    # Example: staff types "product", "promotion", "sop"
    allowed_generic_questions = {
        "product",
        "products",
        "promotion",
        "promotions",
        "sop",
        "notice",
        "notices",
        "training",
    }

    if question_clean in allowed_generic_questions:
        return False

    # If AI only gives generic category choices for a specific-looking question,
    # escalate instead of pretending it knows the answer.
    if source.startswith("generic_"):
        return True

    if source in {"category_choice", "broad_topic_clarification"}:
        return False

    return False


def remember_last_ai_answer(data: dict | None, question: str, result: dict | None) -> None:
    if not result:
        return

    AI_LAST_ANSWER_MEMORY[get_last_answer_key(data)] = {
        "question": question,
        "result": result,
    }

def get_ai_fail_key(data: dict | None, question: str = "") -> str:
    data = data or {}
    user_id = data.get("user_id") or data.get("userId")

    if user_id:
        return f"user:{user_id}:ai_fail_count"

    return f"ip:{request.remote_addr or 'local'}:ai_fail_count"


def update_ai_fail_count(data: dict | None, question: str, result: dict | None) -> int:
    result = result or {}

    bad_sources = {
        "ambiguous_title_choice",
        "clarification_round_1",
        "clarification_round_2",
        "unclear_question_clarification",
        "system_problem_clarification",
        "step_request_missing_topic",
        "low_confidence_or_model_unavailable",
        "fallback",
        "unknown",
        "prediction_error",
        "engine_unavailable",
    }

    source = str(result.get("source", "")).strip()
    confidence = float(result.get("confidence", result.get("score", 0.0)) or 0.0)

    if (
        source in {"broad_topic_clarification", "category_choice"}
        or source.startswith("generic_")
        or "out_of_bounds" in source
        or source in {"context_step", "context_step_range", "context_show_all", "context_picture", "context_section"}
    ):
        AI_FAIL_MEMORY.pop(get_ai_fail_key(data, question), None)
        return 0

    is_failed_answer = (
        source in bad_sources
        or bool(result.get("fallback", False))
        or confidence < 1.0
    )

    fail_key = get_ai_fail_key(data, question)

    if is_failed_answer:
        AI_FAIL_MEMORY[fail_key] = AI_FAIL_MEMORY.get(fail_key, 0) + 1
    else:
        AI_FAIL_MEMORY.pop(fail_key, None)

    return AI_FAIL_MEMORY.get(fail_key, 0)


def clear_ai_fail_count(data: dict | None, question: str) -> None:
    fail_key = get_ai_fail_key(data, question)
    AI_FAIL_MEMORY.pop(fail_key, None)


def is_escalation_result(result: dict | None) -> bool:
    result = result or {}

    if bool(result.get("escalation_ready", False)):
        return True

    source = str(result.get("source", "")).strip()
    reply = str(result.get("reply", "")).lower()
    answer = str(result.get("answer", "")).lower()

    if source in {
        "irrelevant_question",
        "low_confidence_or_model_unavailable",
        "prediction_error",
        "engine_unavailable",
        "fallback",
        "repeated_unclear_question",
        "repeated_system_problem",
    }:
        return True

    return "escalate" in reply or "escalate" in answer


def get_confidence_label(score: float) -> str:
    try:
        score = float(score or 0.0)
    except Exception:
        score = 0.0

    if score >= 0.90:
        return "high"
    if score >= 0.72:
        return "medium"
    return "low"


def is_fallback_result(result: dict | None) -> bool:
    result = result or {}

    if bool(result.get("fallback", False)):
        return True

    if is_escalation_result(result):
        return True

    source = str(result.get("source", "")).strip()

    if (
        source in {"broad_topic_clarification", "category_choice"}
        or source.startswith("generic_")
        or "out_of_bounds" in source
        or source in {"context_step", "context_step_range", "context_show_all", "context_picture", "context_section"}
    ):
        return False

    if source in {
        "empty_question",
        "none",
        "fallback",
        "clarification_round_1",
        "clarification_round_2",
        "unclear_question_clarification",
        "system_problem_clarification",
        "low_confidence_or_model_unavailable",
        "prediction_error",
        "pytorch_model_error",
        "ambiguous_title_choice",
        "step_request_missing_topic",
    }:
        return True

    return "clarification" in source or "fallback" in source


def build_fallback_message(result: dict | None, fallback: bool, escalation_required: bool) -> str:
    result = result or {}

    if result.get("fallback_message"):
        return str(result.get("fallback_message"))

    if escalation_required:
        return "Please escalate this question to team lead."

    if fallback:
        return str(result.get("reply", result.get("answer", "Please provide more details.")))

    return ""


def standardize_ai_response(result: dict | None) -> dict:
    result = result or {}

    score = result.get("score", result.get("confidence", 0.0))
    try:
        score = float(score or 0.0)
    except Exception:
        score = 0.0

    confidence = result.get("confidence", score)
    try:
        confidence = float(confidence or 0.0)
    except Exception:
        confidence = score

    escalation_required = bool(
        result.get("escalation_required", result.get("escalation_ready", False))
    ) or is_escalation_result(result)

    fallback = is_fallback_result(result)
    fallback_message = build_fallback_message(result, fallback, escalation_required)

    reply = result.get("reply", result.get("answer", ""))
    answer = result.get("answer", result.get("reply", ""))

    result["reply"] = reply
    result["answer"] = answer
    result["message"] = result.get("message", reply)
    result["score"] = round(score, 4)
    result["confidence"] = round(confidence, 4)
    result["confidence_label"] = result.get("confidence_label") or get_confidence_label(confidence)
    result["fallback"] = fallback
    result["fallback_message"] = fallback_message
    result["escalation_ready"] = escalation_required
    result["escalation_required"] = escalation_required

    result["options"] = result.get("options", [])

    return result



def ensure_ai_chat_log_table():
    """
    Create the AI chat analytics table if it does not exist.
    Analytics will read from this MySQL table instead of local CSV files.
    """
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_chat_log (
                log_id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NULL,
                question TEXT NOT NULL,
                title VARCHAR(255) NULL,
                category VARCHAR(100) NULL,
                article_section VARCHAR(100) NULL,
                response_type VARCHAR(50) DEFAULT 'text',
                score DECIMAL(6,4) DEFAULT 0,
                confidence DECIMAL(6,4) DEFAULT 0,
                confidence_label VARCHAR(20) NULL,
                source VARCHAR(100) NULL,
                fallback TINYINT DEFAULT 0,
                fallback_message TEXT NULL,
                escalation_ready TINYINT DEFAULT 0,
                reply MEDIUMTEXT NULL,
                error TEXT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                INDEX idx_ai_chat_log_created_at (created_at),
                INDEX idx_ai_chat_log_category (category),
                INDEX idx_ai_chat_log_source (source),
                INDEX idx_ai_chat_log_fallback (fallback),
                INDEX idx_ai_chat_log_escalation (escalation_ready)
            )
        """)

        conn.commit()

    except Exception as error:
        print("AI CHAT LOG TABLE CHECK ERROR:", error)

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def save_ai_chat_log_to_mysql(payload, user_id=None):
    """
    Save AI Chat interaction logs into MySQL for the Analytics page.
    Logging errors should not stop the AI Chat from replying to staff.
    """
    conn = None
    cursor = None

    try:
        ensure_ai_chat_log_table()

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO ai_chat_log
            (
                user_id,
                question,
                title,
                category,
                article_section,
                response_type,
                score,
                confidence,
                confidence_label,
                source,
                fallback,
                fallback_message,
                escalation_ready,
                reply,
                error
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            payload.get("question") or "",
            payload.get("title"),
            payload.get("category"),
            payload.get("section"),
            payload.get("type", "text"),
            float(payload.get("score", 0.0) or 0.0),
            float(payload.get("confidence", 0.0) or 0.0),
            payload.get("confidence_label"),
            payload.get("source"),
            1 if payload.get("fallback") else 0,
            payload.get("fallback_message"),
            1 if payload.get("escalation_ready") else 0,
            payload.get("reply"),
            payload.get("error")
        ))

        conn.commit()

    except Exception as error:
        print("SAVE AI CHAT LOG MYSQL ERROR:", error)

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def log_request(question: str, result: dict | None = None, error: str | None = None, user_id=None) -> None:
    """
    Standardise every AI Chat result and save it into MySQL for Analytics.
    This replaces the previous CSV-based analytics logging.
    """
    timestamp = datetime.now().isoformat(timespec="seconds")

    if error:
        payload = {
            "timestamp": timestamp,
            "question": question,
            "title": None,
            "category": None,
            "section": None,
            "type": "text",
            "score": 0.0,
            "confidence": 0.0,
            "confidence_label": "low",
            "source": "prediction_error",
            "fallback": True,
            "fallback_message": "There was a problem while generating the answer.",
            "escalation_ready": True,
            "reply": "There was a problem while generating the answer.",
            "error": error,
        }
    else:
        result = standardize_ai_response(result or {})

        # Keep the real user question.
        # If result["question"] is empty, fall back to the original question parameter.
        logged_question = result.get("question") or question

        payload = {
            "timestamp": timestamp,
            "question": logged_question,
            "title": result.get("title") or logged_question,
            "category": result.get("category"),
            "section": result.get("section"),
            "type": result.get("type", "text"),
            "score": float(result.get("score", 0.0) or 0.0),
            "confidence": float(result.get("confidence", result.get("score", 0.0)) or 0.0),
            "confidence_label": result.get("confidence_label"),
            "source": result.get("source", "unknown"),
            "fallback": bool(result.get("fallback", False)),
            "fallback_message": str(result.get("fallback_message", "")),
            "escalation_ready": is_escalation_result(result),
            "reply": str(result.get("reply", result.get("answer", ""))),
            "error": None,
        }

    print(
        f"[{timestamp}] CHAT | question={payload['question']!r} | "
        f"title={payload['title']!r} | category={payload['category']!r} | "
        f"section={payload['section']!r} | score={payload['score']} | "
        f"source={payload['source']!r} | fallback={payload['fallback']} | "
        f"escalation_ready={payload['escalation_ready']}"
    )

    save_ai_chat_log_to_mysql(payload, user_id=user_id)


def call_model_answer(question: str, context: dict | None = None):
    context = normalize_context(context or {})
    try:
        return get_model_answer(question, context=context)
    except TypeError:
        return get_model_answer(question)

def normalize_result(result, default_source="unknown"):
    if isinstance(result, dict):
        return standardize_ai_response({
            "type": result.get("type", "text"),
            "category": result.get("category"),
            "title": result.get("title") or result.get("question"),
            "question": result.get("question"),
            "section": result.get("section"),
            "reply": result.get("reply", result.get("answer", "No answer returned.")),
            "answer": result.get("answer", result.get("reply", "No answer returned.")),
            "purpose": result.get("purpose"),
            "steps": result.get("steps", []),
            "notes": result.get("notes", []),
            "score": float(result.get("score", result.get("confidence", 0.0)) or 0.0),
            "confidence": float(result.get("confidence", result.get("score", 0.0)) or 0.0),
            "confidence_label": result.get("confidence_label"),
            "source": result.get("source", default_source),
            "context": result.get("context", {}),
            "fallback": result.get("fallback", False),
            "fallback_message": result.get("fallback_message", ""),
            "escalation_ready": result.get("escalation_ready", False),
            "escalation_required": result.get("escalation_required", result.get("escalation_ready", False)),
            "options": result.get("options", []),
            "image_url": result.get("image_url"),
            "image_type": result.get("image_type"),
            "image_files": result.get("image_files") or (
                [{"url": result.get("image_url"), "type": result.get("image_type")}]
                if result.get("image_url")
                else []
            ),
            "attachment_url": result.get("attachment_url") or result.get("image_url"),
            "attachment_type": result.get("attachment_type") or result.get("image_type"),
        })

    return standardize_ai_response({
        "type": "text",
        "category": None,
        "title": None,
        "section": None,
        "reply": str(result),
        "answer": str(result),
        "purpose": None,
        "steps": [],
        "notes": [],
        "score": 0.0,
        "confidence": 0.0,
        "source": default_source,
    })


def is_valid_answer(result):
    if not result:
        return False

    if result.get("type") == "sop":
        return bool(result.get("steps"))

    answer_text = str(result.get("answer", "")).strip()

    if not answer_text:
        return False

    if answer_text == ESCALATION_MESSAGE:
        return False

    return True


def choose_final_result(model_result, retrieval_result, kb_result=None, image_retrieval_result=None):
    REQUIRED_CONFIDENCE = 1.0

    def is_fully_confident(result):
        if not result:
            return False

        if not is_valid_answer(result):
            return False

        confidence = float(result.get("confidence", result.get("score", 0.0)) or 0.0)

        return confidence >= REQUIRED_CONFIDENCE

    # Allow control messages such as step out of bounds to return.
    # These are not wrong knowledge answers; they guide the staff.
    if model_result:
        model_source = str(model_result.get("source", ""))
        non_escalation_control_sources = {
            "step_request_missing_topic",
            "context_step_out_of_bounds",
            "context_step_range_out_of_bounds",
            "matched_title_step_out_of_bounds",
            "matched_title_step_range_out_of_bounds",
        }

        if (
            model_source in non_escalation_control_sources
            or "step_out_of_bounds" in model_source
            or "step_range_out_of_bounds" in model_source
            or "step_range_limited" in model_source
            or "part_prompt" in model_source
            or "step_prompt" in model_source
            or model_source == "context_guidance"
        ):
            return model_result

        # Priority 1: live Knowledge Base article.
    if is_fully_confident(kb_result):
        kb_result["score"] = 1.0
        kb_result["confidence"] = 1.0
        return kb_result

    # Priority 2: approved image retrieval.
    # This includes Knowledge Base image records and Manager-approved escalation image records.
    if is_fully_confident(image_retrieval_result):
        image_retrieval_result["score"] = 1.0
        image_retrieval_result["confidence"] = 1.0
        return image_retrieval_result

    # Priority 3: Manager-approved Team Lead answer.
    if is_fully_confident(retrieval_result):
        retrieval_result["score"] = 1.0
        retrieval_result["confidence"] = 1.0
        return retrieval_result

    # Priority 3: PyTorch/training answer only if truly 100%.
    if is_fully_confident(model_result):
        model_result["score"] = 1.0
        model_result["confidence"] = 1.0
        return model_result

    # Anything below 100% must not guess.
    return standardize_ai_response({
        "type": "text",
        "category": None,
        "title": None,
        "section": None,
        "reply": "Sorry, I don’t understand this topic clearly. I have escalated it to the Team Lead.",
        "answer": "Sorry, I don’t understand this topic clearly. I have escalated it to the Team Lead.",
        "purpose": None,
        "steps": [],
        "notes": [],
        "score": 0.0,
        "confidence": 0.0,
        "source": "low_confidence_direct_escalation",
        "context": {},
        "fallback": True,
        "fallback_message": "Confidence is below 100%, so this question was escalated to the Team Lead.",
        "escalation_ready": True,
        "escalation_required": True,
    })

def extract_numbered_option_titles(text):
    titles = []

    for line in str(text or "").splitlines():
        line = line.strip()

        match = re.match(r"^\d+\.\s*(.+)$", line)
        if match:
            title = match.group(1).strip()
            if title:
                titles.append(title)

    return titles


def build_training_data_options_from_model_reply(model_result, context=None):
    model_result = model_result or {}
    context = normalize_context(context or {})

    reply = model_result.get("reply") or model_result.get("answer") or ""
    titles = extract_numbered_option_titles(reply)

    options = []
    seen = set()

    for title in titles[:6]:
        key = title.lower().strip()

        if key in seen:
            continue

        seen.add(key)

        try:
            detail_result = normalize_result(
                call_model_answer(title, context=context),
                default_source="pytorch_model"
            )
        except Exception:
            detail_result = None

        answer = ""
        category = None
        section = None
        confidence = 0.0
        option_type = "text"
        steps = []
        notes = []

        if detail_result:
            answer = detail_result.get("answer") or detail_result.get("reply") or ""
            category = detail_result.get("category")
            section = detail_result.get("section")
            confidence = float(detail_result.get("confidence", detail_result.get("score", 0.0)) or 0.0)
            option_type = detail_result.get("type", "text")
            steps = detail_result.get("steps", [])
            notes = detail_result.get("notes", [])
            image_files = detail_result.get("image_files")
            attachment_url = detail_result.get("attachment_url")
            attachment_type = detail_result.get("attachment_type")

        if not answer:
            answer = f"Please ask about {title} for more details."

        options.append({
            "label": title,
            "title": title,
            "category": category,
            "section": section,
            "source": "training_data",
            "confidence": confidence,
            "reply": answer,
            "answer": answer,
            "type": option_type,
            "steps": steps,
            "notes": notes,
            "image_files": image_files if 'image_files' in locals() else None,
            "attachment_url": attachment_url if 'attachment_url' in locals() else None,
            "attachment_type": attachment_type if 'attachment_type' in locals() else None,
        })

    return options

def filter_short_keyword_options(question, options):
    """
    Keep short related options for staff keyword search.
    Example:
    - daily => daily, daily ice bin
    - daily royal black => daily, daily ice bin, daily royal black
    - opening kiosk notes => opening notes, kiosk opening, opening notes kiosk
    """
    question_clean = clean_question(question).lower()
    q_tokens = question_clean.split()

    if not q_tokens:
        return options

    parent_token = q_tokens[0]
    q_token_set = set(q_tokens)

    filtered = []
    seen = set()

    for option in options:
        title = str(option.get("title") or option.get("label") or "").lower().strip()
        title_tokens = title.split()
        title_token_set = set(title_tokens)

        if not title or title in seen:
            continue

        include = False

        if title == question_clean:
            include = True

        elif title == parent_token:
            include = True

        elif title.startswith(parent_token + " ") and len(title_tokens) <= 4:
            include = True

        # NEW: allow reversed word order like "kiosk opening"
        elif parent_token in title_token_set and len(title_tokens) <= 4:
            include = True

        # NEW: allow "opening notes" for "opening kiosk notes"
        elif len(q_token_set & title_token_set) >= 2 and len(title_tokens) <= 4:
            include = True

        if include:
            seen.add(title)
            filtered.append(option)

    return filtered

def build_answer_options(question, model_result=None, retrieval_result=None):
    options = []
    seen = set()

    def add_option(result, source_label):
        if not result:
            return

        title = (
            result.get("title")
            or result.get("question")
            or result.get("category")
            or ""
        )

        answer = result.get("answer") or result.get("reply") or ""

        if not title or not answer:
            return

        key = str(title).lower().strip()

        if key in seen:
            return

        seen.add(key)

        options.append({
            "label": title,
            "title": title,
            "category": result.get("category"),
            "section": result.get("section"),
            "source": result.get("source", source_label),
            "confidence": float(result.get("confidence", result.get("score", 0.0)) or 0.0),
            "reply": answer,
            "answer": answer,
            "type": result.get("type", "text"),
            "steps": result.get("steps", []),
            "notes": result.get("notes", []),
            "image_files": result.get("image_files"),
            "attachment_url": result.get("attachment_url"),
            "attachment_type": result.get("attachment_type"),
            "link": result.get("link") or result.get("article_link"),
            "article_link": result.get("article_link") or result.get("link")
        })

    add_option(model_result, "training_data")
    add_option(retrieval_result, "team_lead")

    return sorted(
        options,
        key=lambda item: item.get("confidence", 0.0),
        reverse=True
    )[:6]


def tokenize_for_knowledge_match(value):
    value = str(value or "").lower()

    stop_words = {
        "a", "an", "the", "to", "for", "of", "and", "or", "is", "are", "do", "does",
        "can", "i", "me", "my", "you", "your", "what", "how", "when", "where", "which",
        "show", "tell", "need", "want", "about", "info", "information", "please",
        "this", "that", "with", "in", "on", "at", "from", "by"
    }

    word_map = {
        "opening": "open",
        "opened": "open",
        "opens": "open",
        "closing": "close",
        "closed": "close",
        "closes": "close",
        "products": "product",
        "promotions": "promotion",
        "questions": "question",
        "answers": "answer",
        "staffs": "staff",
        "articles": "article",
        "steps": "step",
    }

    raw_tokens = re.findall(r"[a-z0-9]+", value)

    tokens = set()

    for token in raw_tokens:
        if token in stop_words:
            continue

        if len(token) <= 1:
            continue

        tokens.add(word_map.get(token, token))

    return tokens


def normalize_article_image_files(value):
    """Return article images/files in one clean list for AI Chat."""
    files = []

    if not value:
        return files

    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except Exception:
        parsed = value

    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                url = item.get("url") or item.get("path") or item.get("image_url")
                file_type = item.get("type") or item.get("mime_type")
                if url:
                    files.append({"url": url, "type": file_type})
            elif item:
                files.append({"url": str(item), "type": None})
    elif isinstance(parsed, dict):
        url = parsed.get("url") or parsed.get("path") or parsed.get("image_url")
        file_type = parsed.get("type") or parsed.get("mime_type")
        if url:
            files.append({"url": url, "type": file_type})
    else:
        files.append({"url": str(parsed), "type": None})

    return files


def calculate_article_match_score(question, article):
    question_text = clean_question(question).lower()
    q_tokens = tokenize_for_knowledge_match(question_text)

    title = str(article.get("title") or "").lower()
    category = str(article.get("category") or "").lower()
    sub_category = str(article.get("sub_category") or "").lower()
    content = str(article.get("content") or "").lower()

    title_tokens = tokenize_for_knowledge_match(title)
    category_tokens = tokenize_for_knowledge_match(category)
    sub_category_tokens = tokenize_for_knowledge_match(sub_category)
    content_tokens = tokenize_for_knowledge_match(content)

    meta_tokens = title_tokens | category_tokens | sub_category_tokens
    all_tokens = meta_tokens | content_tokens

    if not q_tokens or not all_tokens:
        return 0.0

    # Exact title match.
    if question_text == title:
        return 1.0

    # Example: "kiosk opening" matches "JHKC Kiosk Opening".
    if q_tokens.issubset(title_tokens):
        return 1.0

    # Example: "how to open kiosk" matches title/category/subcategory.
    if q_tokens.issubset(meta_tokens):
        return 1.0

    title_overlap_count = len(q_tokens & title_tokens)
    title_overlap_ratio = title_overlap_count / max(len(q_tokens), 1)

    # Strong title match.
    if len(q_tokens) >= 2 and title_overlap_ratio >= 0.75:
        return 1.0

    # Step/detail question can still match article if the main topic is in the title.
    # Example: "step 2 kiosk opening".
    if title_overlap_count >= 2 and q_tokens.issubset(all_tokens):
        return 1.0

    # Anything else is not fully confident.
    overlap = len(q_tokens & all_tokens) / max(len(q_tokens), 1)
    weak_score = round(min(overlap, 0.99), 4)

    return weak_score


def parse_article_steps(content):
    text = str(content or "").strip()
    if not text:
        return []

    pattern = re.compile(
        r"(?:^|\n)\s*(?:step\s*)?(\d+)\s*[\).:-]?\s*(.*?)(?=(?:\n\s*(?:step\s*)?\d+\s*[\).:-])|\Z)",
        re.IGNORECASE | re.DOTALL
    )

    matches = list(pattern.finditer(text))
    steps = []

    for match in matches:
        step_no = int(match.group(1))
        step_text = str(match.group(2) or "").strip()

        if not step_text:
            continue

        image_files = []

        # Find [IMAGE]https://xxx image links inside the step content
        image_matches = re.findall(r"\[IMAGE\]\s*(https?://[^\s]+)", step_text, re.IGNORECASE)

        for image_url in image_matches:
            image_files.append({
                "url": image_url.strip(),
                "type": "image"
            })

        # Remove [IMAGE] links from the text so they do not show as ugly text
        clean_step_text = re.sub(
            r"\[IMAGE\]\s*https?://[^\s]+",
            "",
            step_text,
            flags=re.IGNORECASE
        ).strip()

        steps.append({
            "step": step_no,
            "step_order": step_no,
            "title": f"Step {step_no}",
            "answer": clean_step_text,
            "content": clean_step_text,
            "image_files": image_files
        })

    return steps


def build_article_ai_result(article, question, score):
    title = article.get("title")
    content = article.get("content") or ""
    category = article.get("category")
    sub_category = article.get("sub_category")
    article_link = str(article.get("link") or "").strip()

    article_files = normalize_article_image_files(article.get("image_files"))

    if article.get("attachment_url"):
        article_files.append({
            "url": article.get("attachment_url"),
            "type": article.get("attachment_type")
        })

    # Remove duplicate file URLs.
    unique_files = []
    seen_urls = set()
    for item in article_files:
        url = str(item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        unique_files.append(item)

    steps = parse_article_steps(content)
    result_type = "sop" if steps else "text"

    if result_type == "text":
        reply = content
    else:
        reply = f"{title}"
        if unique_files:
            # Article-level attachments are shown in the first step so staff can see them in AI Chat.
            steps[0]["image_files"] = unique_files

    return standardize_ai_response({
        "question": question,
        "type": result_type,
        "category": category,
        "title": title,
        "section": sub_category,
        "reply": reply,
        "answer": content,
        "purpose": None,
        "steps": steps,
        "notes": [],
        "image_files": unique_files,
        "attachment_url": article.get("attachment_url"),
        "attachment_type": article.get("attachment_type"),
        "link": article_link,
        "article_link": article_link,
        "score": score,
        "confidence": score,
        "confidence_label": get_confidence_label(score),
        "source": "wiki_article_database",
        "context": {
            "source_type": "knowledge_base",
            "article_id": article.get("article_id"),
            "title": title,
            "category": category,
            "section": sub_category,
        },
        "fallback": False,
        "fallback_message": "",
        "escalation_ready": False,
        "escalation_required": False,
    })


def search_knowledge_base_articles(question, limit=1):
    """
    Main AI knowledge retrieval.
    AI Chat reads live wiki_article database first, so new Content Management articles
    can be found without changing cleaned_knowledge.csv or retraining PyTorch.
    """
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                article_id,
                title,
                content,
                category,
                sub_category,
                link,
                attachment_url,
                attachment_type,
                image_files,
                created_at
            FROM wiki_article
            WHERE COALESCE(is_deleted, 0) = 0
            ORDER BY created_at DESC, article_id DESC
        """)
        articles = cursor.fetchall() or []
    except Exception as error:
        print("KB ARTICLE SEARCH ERROR:", error)
        return [] if limit != 1 else None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    scored_results = []
    for article in articles:
        score = calculate_article_match_score(question, article)

        # Strict lecturer rule:
        # Only return Knowledge Base answer when confidence is 100%.
        if score >= 1.0:
            scored_results.append(build_article_ai_result(article, question, 1.0))

    scored_results = sorted(scored_results, key=lambda item: item.get("score", 0.0), reverse=True)

    if limit == 1:
        return scored_results[0] if scored_results else None

    return scored_results[:limit]

def process_question(question, context=None):
    question = clean_question(question)
    context = normalize_context(context or {})

    if not question:
        return standardize_ai_response({
            "question": "",
            "type": "text",
            "category": None,
            "title": None,
            "section": None,
            "reply": "Please enter a question.",
            "answer": "Please enter a question.",
            "purpose": None,
            "steps": [],
            "notes": [],
            "score": 0.0,
            "confidence": 0.0,
            "source": "none",
            "fallback": True,
            "fallback_message": "Please enter a question.",
            "escalation_ready": False,
            "escalation_required": False,
        }), 400

    kb_result = search_knowledge_base_articles(question, limit=1)
    kb_options = search_knowledge_base_articles(question, limit=10)

    image_retrieval_result = search_image_retrieval(question, limit=1)

    if image_retrieval_result:
        image_retrieval_result = normalize_result(image_retrieval_result, "image_retrieval")

    image_retrieval_options = search_image_retrieval(question, limit=10)
    image_retrieval_options = [
        normalize_result(item, "image_retrieval")
        for item in image_retrieval_options
    ]

    retrieval_result = search_similar_question(question)

    if retrieval_result:
        retrieval_result = normalize_result(retrieval_result, "database")

    retrieval_options = search_similar_questions(question, team_lead_only=False, limit=10)
    retrieval_options = [
        normalize_result(item, "database")
        for item in retrieval_options
    ]

    model_result = None

    if MODEL_AVAILABLE and get_model_answer is not None:
        try:
            model_result = normalize_result(
                call_model_answer(question, context=context),
                default_source="pytorch_model"
            )
        except Exception as error:
            model_result = standardize_ai_response({
                "type": "text",
                "category": None,
                "title": None,
                "section": None,
                "reply": f"Model prediction failed: {error}",
                "answer": f"Model prediction failed: {error}",
                "purpose": None,
                "steps": [],
                "notes": [],
                "score": 0.0,
                "confidence": 0.0,
                "source": "pytorch_model_error",
                "fallback": True,
                "fallback_message": "There was a problem while generating the answer.",
                "escalation_ready": True,
                "escalation_required": True,
            })
    else:
        model_result = standardize_ai_response({
            "type": "text",
            "category": None,
            "title": None,
            "section": None,
            "reply": "AI model is not available.",
            "answer": "AI model is not available.",
            "purpose": None,
            "steps": [],
            "notes": [],
            "score": 0.0,
            "confidence": 0.0,
            "source": "engine_unavailable",
            "fallback": True,
            "fallback_message": "AI model is not available.",
            "escalation_ready": True,
            "escalation_required": True,
        })

    # Build selectable options from PyTorch training data and Team Lead/database data.
    answer_options = []

    model_source = str(model_result.get("source", "") if model_result else "")

    # If PyTorch returns a broad numbered list, convert each numbered item into a clickable option.
    if model_source in {
        "broad_topic_clarification",
        "category_choice",
        "ambiguous_title_choice",
    }:
        answer_options.extend(
            build_training_data_options_from_model_reply(model_result, context=context)
        )
    else:
        answer_options.extend(
            build_answer_options(question, model_result, None)
        )

    # Add Knowledge Base article results first because wiki_article is the live main knowledge source.
    answer_options.extend(
        build_answer_options(question, None, kb_result)
    )

    for item in kb_options:
        answer_options.extend(build_answer_options(question, None, item))

    # Add approved image retrieval results.
    answer_options.extend(
        build_answer_options(question, None, image_retrieval_result)
    )

    for item in image_retrieval_options:
        answer_options.extend(build_answer_options(question, None, item))

    # Add the best Team Lead/database result.
    answer_options.extend(
        build_answer_options(question, None, retrieval_result)
    )

    for item in retrieval_options:
        extra_options = build_answer_options(question, None, item)
        answer_options.extend(extra_options)

    # remove duplicates after adding multiple retrieval options
    unique_options = []
    seen_titles = set()

    for option in answer_options:
        title_key = str(option.get("title", "")).lower().strip()
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_options.append(option)

    def option_rank(item):
        source = str(item.get("source", "")).lower()
        title = str(item.get("title", item.get("label", ""))).lower()
        question_text = question.lower()

        team_lead_priority = 1 if source == "team_lead" else 0
        exact_title_priority = 1 if question_text in title or title in question_text else 0

        return (
            team_lead_priority,
            exact_title_priority,
            item.get("confidence", 0.0),
        )

    answer_options = sorted(
        unique_options,
        key=option_rank,
        reverse=True
    )

    keyword_question = len(question.split()) <= 3

    if keyword_question:
        filtered_options = filter_short_keyword_options(question, answer_options)

        if filtered_options:
            answer_options = filtered_options

    answer_options = answer_options[:5]

    if (
        keyword_question
        and len(answer_options) >= 1
        and float(answer_options[0].get("confidence", 0.0) or 0.0) >= 1.0
    ):
        return standardize_ai_response({
            "question": question,
            "type": "multiple_choice",
            "category": None,
            "title": None,
            "section": None,
            "reply": "I found a few possible answers. Please select one:",
            "answer": "I found a few possible answers. Please select one:",
            "purpose": None,
            "steps": [],
            "notes": [],
            "score": answer_options[0].get("confidence", 0.0),
            "confidence": answer_options[0].get("confidence", 0.0),
            "confidence_label": get_confidence_label(answer_options[0].get("confidence", 0.0)),
            "source": "suggestion_options",
            "context": {},
            "fallback": False,
            "fallback_message": "",
            "escalation_ready": False,
            "escalation_required": False,
            "options": answer_options,
        }), 200

    # Prefer training data / PyTorch model result for normal valid questions.
    # Retrieved Team Lead answers are used mainly when the model cannot answer confidently.
    final_result = choose_final_result(
        model_result,
        retrieval_result,
        kb_result,
        image_retrieval_result
    )

    response_payload = {
        "question": question,
        "type": final_result.get("type", "text"),
        "category": final_result.get("category"),
        "title": final_result.get("title"),
        "section": final_result.get("section"),
        "reply": final_result.get("reply", final_result.get("answer", "")),
        "answer": final_result.get("answer", final_result.get("reply", "")),
        "purpose": final_result.get("purpose"),
        "steps": final_result.get("steps", []),
        "notes": final_result.get("notes", []),
        "image_files": final_result.get("image_files"),
        "attachment_url": final_result.get("attachment_url"),
        "attachment_type": final_result.get("attachment_type"),
        "score": final_result.get("score", 0.0),
        "confidence": final_result.get("confidence", final_result.get("score", 0.0)),
        "confidence_label": final_result.get("confidence_label"),
        "source": final_result.get("source", "unknown"),
        "context": final_result.get("context", {}),
        "fallback": final_result.get("fallback", False),
        "fallback_message": final_result.get("fallback_message", ""),
        "escalation_ready": final_result.get("escalation_ready", False),
        "escalation_required": final_result.get("escalation_required", final_result.get("escalation_ready", False)),
        "options": final_result.get("options", []),
    }

    return standardize_ai_response(response_payload), 200


# =========================
# STARTUP CHECKS
# =========================
def verify_manager_account():
    """
    If the manager password is still plain text in DB, hash it once on startup.
    Default manager password used here: admin1234567
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT password_hash
            FROM users
            WHERE email = 'manager@junglehouse.com'
            LIMIT 1
        """)
        user = cursor.fetchone()

        if user and user["password_hash"] == "admin1234567":
            print("Fixing plain-text manager password on startup...")

            new_hash = generate_password_hash("admin1234567")

            cursor.execute("""
                UPDATE users
                SET password_hash = %s
                WHERE email = 'manager@junglehouse.com'
            """, (new_hash,))
            conn.commit()

            print("Manager password successfully hashed.")

    except Exception as e:
        print(f"Could not verify manager password on startup: {e}")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# BASIC BACKEND STATUS
# =========================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "Jungle House AI backend is running",
        "model_available": MODEL_AVAILABLE,
        "model_load_error": MODEL_LOAD_ERROR,
        "engine_available": MODEL_AVAILABLE,
        "engine_import_error": MODEL_LOAD_ERROR,
        "model_error": PREDICT_MODEL_ERROR,
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "model_available": MODEL_AVAILABLE,
        "model_load_error": MODEL_LOAD_ERROR,
        "engine_available": MODEL_AVAILABLE,
        "engine_import_error": MODEL_LOAD_ERROR,
        "model_error": PREDICT_MODEL_ERROR,
        "ai_provider_service_available": AI_PROVIDER_SERVICE_AVAILABLE,
        "ai_provider_service_load_error": AI_PROVIDER_SERVICE_LOAD_ERROR,
    })


@app.route("/api/test-db", methods=["GET"])
def test_db():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT 1 AS ok")
        result = cursor.fetchone()
        return jsonify({
            "message": "Database connection successful.",
            "result": result
        }), 200
    except Exception as e:
        print("TEST DB ERROR:", e)
        return jsonify({"message": f"Database connection failed: {str(e)}"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# AUTH - REGISTER
# =========================
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    print("REGISTER ROUTE HIT:", data)

    full_name = data.get("full_name", "").strip()
    email = data.get("email", "").strip().lower()
    registration_key = str(data.get("registration_key", "")).strip().lower()

    # A valid registration key is now the trust boundary, replacing the old
    # company-email-domain restriction -- any email can register.
    role = "staff"

    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")

    if not all([full_name, email, password, confirm_password]):
        return jsonify({"message": "Please fill in all fields."}), 400

    if not is_valid_email_format(email):
        return jsonify({"message": "Please enter a valid email address."}), 400

    if not registration_key:
        return jsonify({"message": "Registration key is required."}), 400

    if password != confirm_password:
        return jsonify({"message": "Passwords do not match."}), 400

    if len(password) < 8:
        return jsonify({"message": "Password must be at least 8 characters."}), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        ensure_registration_keys_table(cursor)

        cursor.execute("SELECT user_id FROM users WHERE LOWER(email) = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.rollback()
            return jsonify({"message": "Email is already registered."}), 409

        # Lock the key row so two simultaneous registrations can never both
        # succeed with the same key.
        cursor.execute("""
            SELECT key_id, status
            FROM staff_registration_keys
            WHERE key_code = %s
            LIMIT 1
            FOR UPDATE
        """, (registration_key,))
        key_row = cursor.fetchone()

        if not key_row:
            conn.rollback()
            return jsonify({"message": "Invalid registration key."}), 400

        if key_row["status"] == "used":
            conn.rollback()
            return jsonify({"message": "This registration key has already been used."}), 400

        if key_row["status"] == "revoked":
            conn.rollback()
            return jsonify({"message": "This registration key has been revoked."}), 400

        cursor.execute("""
            SELECT role_id, role_name
            FROM roles
            WHERE LOWER(role_name) = %s
        """, (role,))
        role_row = cursor.fetchone()

        if not role_row:
            conn.rollback()
            return jsonify({"message": "Staff role does not exist in database."}), 400

        password_hash = generate_password_hash(password)

        # Security flow:
        # The registration key is the trust boundary (a manager already
        # decided to hand it out), so the account goes active immediately --
        # no email domain check and no separate pending-approval step.
        cursor.execute("""
            INSERT INTO users (full_name, email, password_hash, role_id, status)
            VALUES (%s, %s, %s, %s, 'active')
        """, (full_name, email, password_hash, role_row["role_id"]))

        new_user_id = cursor.lastrowid

        # Mark the key used inside the same transaction. The extra
        # "AND status = 'unused'" guards against a race even though the
        # earlier SELECT ... FOR UPDATE already locked the row -- a used key
        # must never become available again, even after the account that
        # used it is later deactivated.
        cursor.execute("""
            UPDATE staff_registration_keys
            SET status = 'used',
                used_by_user_id = %s,
                used_by_email = %s,
                used_at = NOW()
            WHERE key_id = %s
              AND status = 'unused'
        """, (new_user_id, email, key_row["key_id"]))

        if cursor.rowcount != 1:
            conn.rollback()
            return jsonify({"message": "This registration key has already been used."}), 400

        conn.commit()

        add_audit_log(
            actor_id=new_user_id,
            actor_name=full_name,
            action="Registered with registration key",
            module="Authentication",
            description=f"New staff account created and activated using a registration key. Email: {email}"
        )

        send_email_safe(
            email,
            "Jungle House AI Wiki - Registration successful",
            f"""Hi {full_name},

Your Jungle House AI Wiki account has been created successfully using a registration key.

You can now log in using your registered email address.

Thank you,
Jungle House AI Wiki Team
"""
        )

        return jsonify({
            "message": "Registration successful. You can now log in."
        }), 201

    except mysql.connector.Error as err:
        print("REGISTER MYSQL ERROR:", err)

        if conn:
            conn.rollback()

        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
        print("REGISTER GENERAL ERROR:", e)

        if conn:
            conn.rollback()

        return jsonify({"message": f"Server error: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/auth/verify-email", methods=["GET"])
def verify_email():
    token = request.args.get("token", "").strip()

    if not token:
        return jsonify({"message": "Verification token is required."}), 400

    token_hash = hash_email_verification_token(token)
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        ensure_email_verification_table(cursor)

        cursor.execute("""
            SELECT
                ev.verification_id,
                ev.user_id,
                ev.email,
                ev.expires_at,
                ev.verified_at,
                ev.used_at,
                u.full_name,
                u.status
            FROM email_verifications ev
            JOIN users u ON ev.user_id = u.user_id
            WHERE ev.token_hash = %s
            LIMIT 1
        """, (token_hash,))

        verification = cursor.fetchone()

        if not verification:
            conn.rollback()
            return jsonify({"message": "Invalid verification link."}), 400

        if verification.get("verified_at"):
            conn.rollback()
            return registration_success_redirect("emailAlreadyVerified")

        if verification.get("used_at"):
            conn.rollback()
            return jsonify({"message": "This verification link has already been used. Please request a new link."}), 400

        expires_at = verification.get("expires_at")
        if expires_at and datetime.utcnow() > expires_at:
            conn.rollback()
            return jsonify({"message": "This verification link has expired. Please request a new verification link."}), 400

        cursor.execute("""
            UPDATE email_verifications
            SET verified_at = NOW(),
                used_at = NOW()
            WHERE verification_id = %s
        """, (verification["verification_id"],))

        conn.commit()

        create_notification_safe(
            user_id=verification["user_id"],
            title="Email verified",
            detail="Your email has been verified. Your account is now waiting for manager/team lead approval.",
            notification_type="email_verification",
            related_id=verification["user_id"]
        )

        add_audit_log(
            actor_id=verification["user_id"],
            actor_name=verification.get("full_name") or "New User",
            action="Verified registration email",
            module="Authentication",
            description=f"Verified email address: {verification.get('email')}"
        )

        return registration_success_redirect("emailVerified")

    except Exception as error:
        if conn:
            conn.rollback()

        print("VERIFY EMAIL ERROR:", error)
        return jsonify({"message": "Failed to verify email.", "error": str(error)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/auth/resend-verification", methods=["POST"])
def resend_email_verification():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()

    if not email:
        return jsonify({"message": "Email is required."}), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        ensure_email_verification_table(cursor)

        cursor.execute("""
            SELECT user_id, full_name, email, status
            FROM users
            WHERE LOWER(email) = %s
            LIMIT 1
        """, (email,))

        user = cursor.fetchone()

        # Generic response prevents attackers from checking whether an email exists.
        generic_message = "If the email is registered and not verified, a new verification link will be sent."

        if not user:
            conn.rollback()
            return jsonify({"message": generic_message}), 200

        if is_user_email_verified(cursor, user["user_id"]):
            conn.rollback()
            return jsonify({"message": "This email is already verified. Please wait for manager/team lead approval or try logging in."}), 200

        if str(user.get("status", "")).lower() == "declined":
            conn.rollback()
            return jsonify({"message": "This registration has been declined. Please contact your manager or team lead."}), 403

        verification_token = create_email_verification_token(cursor, user["user_id"], user["email"])
        conn.commit()

        email_sent = send_email_verification_link(user["full_name"], user["email"], verification_token)

        return jsonify({
            "message": "A new verification link has been sent if SMTP email is configured.",
            "email_sent": email_sent
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("RESEND EMAIL VERIFICATION ERROR:", error)
        return jsonify({"message": "Failed to resend verification link.", "error": str(error)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# REGISTRATION KEY ROUTES
# =========================
@app.route("/api/registration-keys/generate", methods=["POST"])
def generate_registration_key():
    data = request.get_json(silent=True) or {}
    actor_id = data.get("created_by") or data.get("user_id")

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        ensure_registration_keys_table(cursor)

        if not is_registration_key_manager(cursor, actor_id):
            return jsonify({
                "message": "Only managers can generate registration keys."
            }), 403

        # Extremely unlikely to collide (36^10 possibilities), but retry a
        # few times just in case instead of trusting luck.
        key_code = None

        for _ in range(5):
            candidate = generate_registration_key_code()

            cursor.execute(
                "SELECT key_id FROM staff_registration_keys WHERE key_code = %s LIMIT 1",
                (candidate,)
            )

            if not cursor.fetchone():
                key_code = candidate
                break

        if not key_code:
            return jsonify({
                "message": "Failed to generate registration key."
            }), 500

        cursor.execute("""
            INSERT INTO staff_registration_keys (key_code, status, created_by_user_id)
            VALUES (%s, 'unused', %s)
        """, (key_code, actor_id))

        conn.commit()

        add_audit_log(
            actor_id=actor_id,
            action="Generated registration key",
            module="User Management",
            description=f"Registration key generated: {key_code}"
        )

        return jsonify({
            "message": "Registration key generated successfully.",
            "key_code": key_code
        }), 201

    except Exception as error:
        if conn:
            conn.rollback()

        print("GENERATE REGISTRATION KEY ERROR:", error)

        return jsonify({
            "message": "Failed to generate registration key.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/registration-keys", methods=["GET"])
def list_registration_keys():
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        ensure_registration_keys_table(cursor)

        cursor.execute("""
            SELECT
                rk.key_id,
                rk.key_code,
                rk.status,
                rk.used_by_email,
                rk.created_at,
                rk.used_at,
                creator.full_name AS created_by_name
            FROM staff_registration_keys rk
            LEFT JOIN users creator ON rk.created_by_user_id = creator.user_id
            ORDER BY rk.created_at DESC
        """)

        keys = cursor.fetchall()

        return jsonify(keys), 200

    except Exception as error:
        print("LIST REGISTRATION KEYS ERROR:", error)

        return jsonify({
            "message": "Failed to load registration keys.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# AUTH - LOGIN
# =========================
@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    print("LOGIN ROUTE HIT:", data)

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"message": "Email and password are required."}), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                u.user_id,
                u.full_name,
                u.email,
                u.password_hash,
                u.status,
                u.created_at,
                r.role_name,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM email_verifications ev
                        WHERE ev.user_id = u.user_id
                          AND ev.verified_at IS NOT NULL
                    ) THEN TRUE
                    ELSE FALSE
                END AS email_verified,
                (
                    SELECT MAX(ev2.verified_at)
                    FROM email_verifications ev2
                    WHERE ev2.user_id = u.user_id
                      AND ev2.verified_at IS NOT NULL
                ) AS email_verified_at
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE LOWER(u.email) = %s
            LIMIT 1
        """, (email,))
        user = cursor.fetchone()

        print("LOGIN USER FOUND:", user)

        if not user:
            record_login_history(
                cursor,
                user_id=None,
                email=email,
                full_name="Unknown",
                status="failed"
            )
            conn.commit()
            return jsonify({"message": "Invalid email or password."}), 401

        user_status = str(user.get("status", "")).strip().lower()
        email_verified = is_user_email_verified(cursor, user["user_id"])

        if user_status == "pending" and not email_verified:
            record_login_history(
                cursor,
                user_id=user["user_id"],
                email=user["email"],
                full_name=user["full_name"],
                status="failed"
            )
            conn.commit()

            return jsonify({
                "message": "Please verify your email first. Check your inbox for the Jungle House AI Wiki verification link."
            }), 403

        if user_status == "pending":
            record_login_history(
                cursor,
                user_id=user["user_id"],
                email=user["email"],
                full_name=user["full_name"],
                status="failed"
            )
            conn.commit()

            return jsonify({
                "message": "Your account is pending verification. A manager or team lead will review your registration within 24 hours. You will be notified through your registered email."
            }), 403

        if user_status == "declined":
            record_login_history(
                cursor,
                user_id=user["user_id"],
                email=user["email"],
                full_name=user["full_name"],
                status="failed"
            )
            conn.commit()

            return jsonify({
                "message": "Your registration was declined. Please contact the manager if you think this is a mistake."
            }), 403

        if user_status != "active":
            record_login_history(
                cursor,
                user_id=user["user_id"],
                email=user["email"],
                full_name=user["full_name"],
                status="failed"
            )
            conn.commit()

            return jsonify({
                "message": "This account is inactive. Please contact the manager."
            }), 403

        stored_password = str(user.get("password_hash", "")).strip()

        password_ok = False

        try:
            password_ok = check_password_hash(stored_password, password)
        except Exception:
            password_ok = False

        # fallback for old plain-text passwords
        if not password_ok and stored_password == password:
            print("PLAIN TEXT PASSWORD MATCH DETECTED. Auto-fixing hash...")
            new_hash = generate_password_hash(password)

            cursor.execute("""
                UPDATE users
                SET password_hash = %s
                WHERE user_id = %s
            """, (new_hash, user["user_id"]))
            conn.commit()

            password_ok = True

        print("PASSWORD CHECK RESULT:", password_ok)

        if not password_ok:
            record_login_history(
                cursor,
                user_id=user["user_id"],
                email=user["email"],
                full_name=user["full_name"],
                status="failed"
            )
            conn.commit()

            return jsonify({"message": "Invalid email or password."}), 401

        record_login_history(
            cursor,
            user_id=user["user_id"],
            email=user["email"],
            full_name=user["full_name"],
            status="success"
        )
        conn.commit()

        user_payload = get_user_profile_payload({
            "user_id": user["user_id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "role_name": user["role_name"],
            "status": user_status,
            "created_at": user.get("created_at"),
        })

        return jsonify({
            "message": "Login successful.",
            "user": user_payload
        }), 200

    except mysql.connector.Error as err:
        print("LOGIN MYSQL ERROR:", err)
        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
        print("LOGIN GENERAL ERROR:", e)
        return jsonify({"message": f"Server error: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# PROFILE
# =========================
@app.route("/api/profile/<int:user_id>", methods=["GET"])
def get_profile(user_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                u.user_id,
                u.full_name,
                u.email,
                u.status,
                u.created_at,
                r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.user_id = %s
            LIMIT 1
        """, (user_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"message": "User not found."}), 404

        return jsonify(get_user_profile_payload(user)), 200

    except mysql.connector.Error as err:
        print("GET PROFILE MYSQL ERROR:", err)
        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
        print("GET PROFILE GENERAL ERROR:", e)
        return jsonify({"message": f"Server error: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/profile/<int:user_id>", methods=["PUT"])
def update_profile(user_id):
    data = request.get_json() or {}

    full_name = data.get("full_name", "").strip()
    email = data.get("email", "").strip().lower()

    if not full_name or not email:
        return jsonify({"message": "Full name and email are required."}), 400

    if len(full_name) < 3:
        return jsonify({"message": "Full name must be at least 3 characters."}), 400

    if "@" not in email or "." not in email:
        return jsonify({"message": "Please enter a valid email address."}), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT user_id
            FROM users
            WHERE user_id = %s
            LIMIT 1
        """, (user_id,))
        existing_user = cursor.fetchone()

        if not existing_user:
            conn.rollback()
            return jsonify({"message": "User not found."}), 404

        cursor.execute("""
            SELECT user_id
            FROM users
            WHERE LOWER(email) = %s AND user_id <> %s
            LIMIT 1
        """, (email, user_id))
        email_owner = cursor.fetchone()

        if email_owner:
            conn.rollback()
            return jsonify({"message": "Email is already used by another account."}), 409

        cursor.execute("""
            UPDATE users
            SET full_name = %s,
                email = %s
            WHERE user_id = %s
        """, (full_name, email, user_id))
        conn.commit()

        cursor.execute("""
            SELECT
                u.user_id,
                u.full_name,
                u.email,
                u.status,
                u.created_at,
                r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.user_id = %s
            LIMIT 1
        """, (user_id,))
        updated_user = cursor.fetchone()

        return jsonify({
            "message": "Profile updated successfully.",
            "user": get_user_profile_payload(updated_user)
        }), 200

    except mysql.connector.Error as err:
        print("UPDATE PROFILE MYSQL ERROR:", err)
        if conn:
            conn.rollback()
        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
        print("UPDATE PROFILE GENERAL ERROR:", e)
        if conn:
            conn.rollback()
        return jsonify({"message": f"Server error: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/profile/<int:user_id>/change-password", methods=["PUT"])
def change_password(user_id):
    data = request.get_json() or {}

    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    confirm_password = data.get("confirm_password", "")

    if not current_password or not new_password or not confirm_password:
        return jsonify({"message": "All password fields are required."}), 400

    if len(new_password) < 6:
        return jsonify({"message": "New password must be at least 6 characters."}), 400

    if new_password != confirm_password:
        return jsonify({"message": "New password and confirm password do not match."}), 400

    if new_password == current_password:
        return jsonify({"message": "New password must be different from current password."}), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT user_id, password_hash
            FROM users
            WHERE user_id = %s
            LIMIT 1
        """, (user_id,))
        user = cursor.fetchone()

        if not user:
            conn.rollback()
            return jsonify({"message": "User not found."}), 404

        stored_password = str(user.get("password_hash", "")).strip()

        password_ok = False
        try:
            password_ok = check_password_hash(stored_password, current_password)
        except Exception:
            password_ok = False

        if not password_ok and stored_password == current_password:
            password_ok = True

        if not password_ok:
            conn.rollback()
            return jsonify({"message": "Current password is incorrect."}), 401

        new_hash = generate_password_hash(new_password)

        cursor.execute("""
            UPDATE users
            SET password_hash = %s
            WHERE user_id = %s
        """, (new_hash, user_id))
        conn.commit()

        return jsonify({"message": "Password updated successfully."}), 200

    except mysql.connector.Error as err:
        print("CHANGE PASSWORD MYSQL ERROR:", err)
        if conn:
            conn.rollback()
        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
        print("CHANGE PASSWORD GENERAL ERROR:", e)
        if conn:
            conn.rollback()
        return jsonify({"message": f"Server error: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# SECURITY / MONITORING ROUTES
# =========================
@app.route("/api/security/login-history", methods=["GET"])
def get_login_history():
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                lh.login_id,
                lh.user_id,
                COALESCE(lh.full_name, u.full_name, 'Unknown') AS user,
                COALESCE(lh.email, u.email, '-') AS email,
                lh.login_status AS status,
                lh.ip_address,
                lh.device_info,
                DATE_FORMAT(lh.login_time, '%Y-%m-%d %H:%i') AS time
            FROM login_history lh
            LEFT JOIN users u ON lh.user_id = u.user_id
            ORDER BY lh.login_time DESC
            LIMIT 100
        """)

        login_history = cursor.fetchall()

        return jsonify({
            "login_history": login_history
        }), 200

    except mysql.connector.Error as err:
        print("MYSQL ERROR /api/security/login-history:", err)
        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
        print("GENERAL ERROR /api/security/login-history:", e)
        return jsonify({"message": f"Server error: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/security/audit-logs", methods=["GET"])
def get_audit_logs():
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                audit_id,
                COALESCE(actor_name, 'System') AS actor,
                action,
                module,
                description,
                DATE_FORMAT(created_at, '%Y-%m-%d %H:%i') AS time
            FROM audit_log
            ORDER BY created_at DESC
            LIMIT 100
        """)

        audit_logs = cursor.fetchall()

        return jsonify({
            "audit_logs": audit_logs
        }), 200

    except mysql.connector.Error as err:
        print("MYSQL ERROR /api/security/audit-logs:", err)
        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
        print("GENERAL ERROR /api/security/audit-logs:", e)
        return jsonify({"message": f"Server error: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# DASHBOARD
# =========================
@app.route("/api/dashboard", methods=["GET"])
def get_dashboard():
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        articles = safe_count_query(cursor, "SELECT COUNT(*) AS total FROM wiki_article")
        questions = safe_count_query(
            cursor,
            "SELECT COUNT(*) AS total FROM question WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)"
        )
        escalations = safe_count_query(
            cursor,
            "SELECT COUNT(*) AS total FROM escalation WHERE status = 'pending'"
        )
        notifications_count = safe_count_query(
            cursor,
            "SELECT COUNT(*) AS total FROM notification WHERE is_read = 0"
        )

        ai_conf = 0
        try:
            cursor.execute("SELECT ROUND(AVG(confidence), 2) AS avg_conf FROM ai_response")
            result = cursor.fetchone()
            if result and result["avg_conf"] is not None:
                ai_conf = result["avg_conf"]
        except Exception:
            ai_conf = 0

        recent_notifications = safe_list_query(cursor, """
            SELECT 
                notification_id AS id,
                title,
                detail,
                is_read,
                created_at
            FROM notification
            ORDER BY created_at DESC
            LIMIT 3
        """)

        activities = safe_list_query(cursor, """
            SELECT action, created_at
            FROM audit_log
            ORDER BY created_at DESC
            LIMIT 3
        """)

        return jsonify({
            "stats": [
                {"label": "Knowledge Articles", "value": articles},
                {"label": "Questions This Week", "value": questions},
                {"label": "Pending Escalations", "value": escalations},
                {"label": "Unread Notifications", "value": notifications_count}
            ],
            "ai": {
                "accuracy": f"{ai_conf * 100:.0f}%"
            },
            "notifications": recent_notifications,
            "activities": activities
        }), 200

    except Exception as e:
        print("DASHBOARD ERROR:", e)
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



# =========================
# NOTIFICATIONS
# =========================
@app.route("/api/notifications/<int:user_id>", methods=["GET"])
def get_notifications(user_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                notification_id AS id,
                title,
                detail,
                is_read AS isRead,
                type,
                related_id,
                target_role,
                created_by,
                created_at
            FROM notification
            WHERE user_id = %s
               OR user_id IS NULL
            ORDER BY created_at DESC
        """, (user_id,))

        notifications = cursor.fetchall()

        return jsonify(notifications), 200

    except mysql.connector.Error as err:
        print("MYSQL ERROR /api/notifications:", err)
        return jsonify({
            "message": f"Database error: {str(err)}"
        }), 500

    except Exception as e:
        print("GENERAL ERROR /api/notifications:", e)
        return jsonify({
            "message": f"Server error: {str(e)}"
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/notifications/read/<int:notification_id>", methods=["PUT"])
def mark_notification_as_read(notification_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE notification
            SET is_read = TRUE
            WHERE notification_id = %s
        """, (notification_id,))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({
                "message": "Notification not found."
            }), 404

        return jsonify({
            "message": "Notification marked as read."
        }), 200

    except mysql.connector.Error as err:
        if conn:
            conn.rollback()

        print("READ NOTIFICATION MYSQL ERROR:", err)
        return jsonify({
            "message": f"Database error: {str(err)}"
        }), 500

    except Exception as e:
        if conn:
            conn.rollback()

        print("READ NOTIFICATION GENERAL ERROR:", e)
        return jsonify({
            "message": f"Server error: {str(e)}"
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()




@app.route("/api/chat/test", methods=["GET"])
def chat_test():
    results = []
    correct_count = 0
    partial_count = 0
    wrong_count = 0
    fallback_count = 0
    weak_count = 0
    escalation_count = 0
    error_count = 0

    category_summary = {}
    test_type_summary = {}

    def add_summary(summary, key, result_status):
        key = key or "Unknown"
        if key not in summary:
            summary[key] = {
                "total": 0,
                "correct": 0,
                "partial": 0,
                "wrong": 0,
                "fallback": 0,
                "weak": 0,
                "escalated": 0,
                "error": 0,
            }

        summary[key]["total"] += 1

        if result_status == "Correct":
            summary[key]["correct"] += 1
        elif result_status == "Partially Correct":
            summary[key]["partial"] += 1
        elif result_status == "Wrong":
            summary[key]["wrong"] += 1
        elif result_status == "Fallback":
            summary[key]["fallback"] += 1
        elif result_status == "Weak Answer":
            summary[key]["weak"] += 1
        elif result_status == "Escalated":
            summary[key]["escalated"] += 1
        elif result_status == "Error":
            summary[key]["error"] += 1

    def evaluate_test_case(test_case, result, status_code):
        expected_title = test_case.get("expected_title")
        expected_category = test_case.get("expected_category")
        expected_behavior = test_case.get("expected_behavior", "answer")

        actual_title = result.get("title")
        actual_category = result.get("category")
        actual_source = result.get("source")
        actual_score = float(result.get("confidence", result.get("score", 0.0)) or 0.0)
        actual_answer = str(result.get("answer", result.get("reply", ""))).strip()
        actual_fallback = bool(result.get("fallback", False))
        actual_escalation = bool(result.get("escalation_required", result.get("escalation_ready", False)))

        if status_code != 200:
            return "Error", "Backend returned error status."

        if expected_behavior == "clarification":
            if actual_fallback and not actual_escalation:
                return "Fallback", "Correct fallback: AI asked the staff to be more specific."
            if actual_escalation:
                return "Wrong", "AI escalated too early for the first unclear question."
            return "Partially Correct", "AI answered, but expected a clarification/fallback message."

        if expected_behavior == "escalation":
            if actual_escalation:
                return "Escalated", "Correct escalation after repeated unclear question."
            return "Wrong", "Expected escalation, but AI did not escalate."

        if expected_behavior == "category_choice":
            if actual_escalation:
                return "Wrong", "AI escalated a broad category question instead of showing options."
            if "clarification" in str(actual_source) or "generic" in str(actual_source) or actual_category == expected_category:
                return "Correct", "AI showed category options or guidance as expected."
            return "Partially Correct", "AI responded, but category guidance was not clear."

        if actual_escalation or actual_fallback:
            return "Fallback", "AI could not answer confidently."

        if expected_title and actual_title == expected_title:
            if actual_score >= 0.60:
                return "Correct", "Expected title matched and confidence is acceptable."
            return "Weak Answer", "Expected title matched, but confidence is below 60%."

        if expected_category and actual_category == expected_category and actual_answer:
            return "Partially Correct", "Category matched, but the title was not the expected one."

        if actual_answer and actual_score < 0.35:
            return "Weak Answer", "AI returned an answer with weak confidence."

        return "Wrong", "Actual answer did not match the expected title or category."

    for test_case in REAL_JH_TEST_QUESTIONS:
        question = clean_question(test_case.get("question", ""))
        test_context = normalize_context(test_case.get("context") or {})

        try:
            result, status = process_question(question, context=test_context)
            log_request(question, result=result)
            result_status, remarks = evaluate_test_case(test_case, result, status)

            if result_status == "Correct":
                correct_count += 1
            elif result_status == "Partially Correct":
                partial_count += 1
            elif result_status == "Wrong":
                wrong_count += 1
            elif result_status == "Fallback":
                fallback_count += 1
            elif result_status == "Weak Answer":
                weak_count += 1
            elif result_status == "Escalated":
                escalation_count += 1
            elif result_status == "Error":
                error_count += 1

            add_summary(category_summary, test_case.get("category"), result_status)
            add_summary(test_type_summary, test_case.get("test_type"), result_status)

            results.append({
                "id": test_case.get("id"),
                "category": test_case.get("category"),
                "test_type": test_case.get("test_type"),
                "question": question,
                "expected_title": test_case.get("expected_title"),
                "expected_category": test_case.get("expected_category"),
                "expected_behavior": test_case.get("expected_behavior"),
                "actual_title": result.get("title"),
                "actual_category": result.get("category"),
                "actual_section": result.get("section"),
                "actual_reply": result.get("reply", result.get("answer")),
                "confidence": result.get("confidence", result.get("score")),
                "confidence_label": result.get("confidence_label"),
                "source": result.get("source"),
                "fallback": bool(result.get("fallback", False)),
                "escalation_required": bool(result.get("escalation_required", result.get("escalation_ready", False))),
                "status_code": status,
                "result_status": result_status,
                "remarks": remarks,
            })
        except Exception as error:
            traceback.print_exc()
            log_request(question, error=str(error))
            error_count += 1
            add_summary(category_summary, test_case.get("category"), "Error")
            add_summary(test_type_summary, test_case.get("test_type"), "Error")

            results.append({
                "id": test_case.get("id"),
                "category": test_case.get("category"),
                "test_type": test_case.get("test_type"),
                "question": question,
                "expected_title": test_case.get("expected_title"),
                "expected_category": test_case.get("expected_category"),
                "expected_behavior": test_case.get("expected_behavior"),
                "actual_title": None,
                "actual_category": None,
                "actual_section": None,
                "actual_reply": "There was a problem while generating the answer.",
                "confidence": 0.0,
                "confidence_label": "low",
                "source": "prediction_error",
                "fallback": True,
                "escalation_required": True,
                "status_code": 500,
                "result_status": "Error",
                "remarks": str(error),
            })

    ensure_log_files()
    with open(TEST_REPORT_CSV, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([
            "id",
            "category",
            "test_type",
            "question",
            "expected_title",
            "expected_category",
            "expected_behavior",
            "actual_title",
            "actual_category",
            "confidence",
            "confidence_label",
            "source",
            "fallback",
            "escalation_required",
            "result_status",
            "remarks",
        ])

        for item in results:
            writer.writerow([
                item.get("id"),
                item.get("category"),
                item.get("test_type"),
                item.get("question"),
                item.get("expected_title"),
                item.get("expected_category"),
                item.get("expected_behavior"),
                item.get("actual_title"),
                item.get("actual_category"),
                item.get("confidence"),
                item.get("confidence_label"),
                item.get("source"),
                item.get("fallback"),
                item.get("escalation_required"),
                item.get("result_status"),
                item.get("remarks"),
            ])

    total = len(REAL_JH_TEST_QUESTIONS)
    pass_count = correct_count + partial_count + fallback_count + escalation_count
    answered_count = correct_count + partial_count + weak_count

    return jsonify({
        "status": "ok",
        "message": "AI validation test completed.",
        "total_questions": total,
        "correct_count": correct_count,
        "partial_count": partial_count,
        "wrong_count": wrong_count,
        "fallback_count": fallback_count,
        "weak_count": weak_count,
        "escalation_count": escalation_count,
        "error_count": error_count,
        "answered_count": answered_count,
        "pass_count": pass_count,
        "answer_rate": round((answered_count / total) * 100, 2) if total else 0.0,
        "pass_rate": round((pass_count / total) * 100, 2) if total else 0.0,
        "report_file": str(TEST_REPORT_CSV),
        "category_summary": category_summary,
        "test_type_summary": test_type_summary,
        "results": results,
    })




# =========================
# ANALYTICS ROUTES
# =========================

@app.route("/api/analytics", methods=["GET"])
def get_analytics():
    conn = None
    cursor = None

    try:
        ensure_ai_chat_log_table()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                log_id,
                user_id,
                question,
                title,
                category,
                article_section,
                response_type,
                score,
                confidence,
                confidence_label,
                source,
                fallback,
                fallback_message,
                escalation_ready,
                reply,
                error,
                DATE_FORMAT(created_at, '%Y-%m-%d %H:%i') AS timestamp
            FROM ai_chat_log
            WHERE question IS NOT NULL
              AND TRIM(question) <> ''
            ORDER BY created_at ASC, log_id ASC
        """)

        db_rows = cursor.fetchall() or []
        rows = []

        for row in db_rows:
            try:
                confidence = float(row.get("confidence", 0) or 0)
            except Exception:
                confidence = 0.0

            rows.append({
                "timestamp": row.get("timestamp") or "-",
                "question": row.get("question") or "",
                "title": row.get("title") or "",
                "category": row.get("category") or "-",
                "confidence": confidence,
                "confidence_label": row.get("confidence_label") or "",
                "source": row.get("source") or "-",
                "fallback": bool(row.get("fallback")),
                "escalation_ready": bool(row.get("escalation_ready")),
                "reply": row.get("reply") or ""
            })

        # =========================
        # Question Analytics
        # =========================
        question_counter = {}

        for row in rows:
            key = str(row["question"]).lower().strip()

            if key not in question_counter:
                question_counter[key] = {
                    "question": row["question"],
                    "count": 0,
                    "category": row.get("category") or "-",
                    "last_asked": row.get("timestamp") or "-"
                }

            question_counter[key]["count"] += 1

            if row.get("timestamp"):
                question_counter[key]["last_asked"] = row.get("timestamp")

        top_questions = sorted(
            question_counter.values(),
            key=lambda item: item["count"],
            reverse=True
        )[:10]

        # =========================
        # Knowledge Gap
        # =========================
        gap_rows = []

        for row in rows:
            if (
                row.get("fallback")
                or row.get("escalation_ready")
                or row.get("confidence", 0) < 0.6
            ):
                gap_rows.append({
                    "question": row.get("question"),
                    "category": row.get("category") or "-",
                    "confidence": row.get("confidence", 0),
                    "source": row.get("source") or "-",
                    "reason": "Fallback / low confidence / escalation needed",
                    "time": row.get("timestamp") or "-"
                })

        knowledge_gaps = gap_rows[-10:]
        knowledge_gaps.reverse()

        # =========================
        # Search Log
        # =========================
        search_logs = rows[-20:]
        search_logs.reverse()

        return jsonify({
            "summary": {
                "total_questions": len(rows),
                "unique_questions": len(question_counter),
                "knowledge_gap_count": len(gap_rows),
                "fallback_count": len([row for row in rows if row.get("fallback")]),
                "escalation_count": len([row for row in rows if row.get("escalation_ready")])
            },
            "top_questions": top_questions,
            "knowledge_gaps": knowledge_gaps,
            "search_logs": search_logs
        }), 200

    except Exception as e:
        print("ANALYTICS MYSQL ERROR:", e)
        return jsonify({
            "message": "Failed to load analytics from MySQL.",
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def is_broad_topic_question(question):
    """
    Short keyword questions should show selectable options first.
    Example:
    - daily
    - daily royal black
    - daily ice bin
    """
    if not question:
        return False

    q = clean_question(question).lower()
    words = q.replace("?", "").replace(".", "").replace(",", "").split()

    if not words:
        return False

    broad_words = {
        "opening",
        "closing",
        "daily",
        "sop",
        "stocktake",
        "settlement",
        "shopify",
        "roadshow",
        "kiosk",
        "booth",
        "promotion",
        "product",
        "honey",
    }

    # One broad word: "daily", "kiosk", "product"
    if len(words) == 1 and words[0] in broad_words:
        return True

    # Short child topic: "daily royal black", "daily ice bin"
    if len(words) <= 3 and words[0] in broad_words:
        return True

    return False

# =========================
# AI MODEL / PROVIDER SETTINGS ROUTES
#
# Lets a manager choose a real AI provider (Gemini/OpenAI/DeepSeek/Claude)
# and paste an API key once. The key is encrypted before it's stored, and
# is NEVER sent back to the frontend -- only a masked hint. Any feature
# (quiz generation, future AI chat upgrades, etc.) can then call
# ai_provider_service.generate_ai_reply(prompt) without needing to know
# which provider is actually configured.
# =========================
@app.route("/api/ai-settings", methods=["GET"])
def get_ai_settings():
    if not AI_PROVIDER_SERVICE_AVAILABLE:
        return jsonify({
            "success": False,
            "message": "AI provider service is not available on this server."
        }), 500

    conn = None
    cursor = None

    try:
        conn = ai_provider_service.get_db_connection()
        cursor = conn.cursor(dictionary=True)

        ai_provider_service.ensure_ai_provider_configs_table(cursor)
        config = ai_provider_service.get_ai_provider_public_config(cursor)

        return jsonify({"success": True, "config": config}), 200

    except Exception as error:
        print("GET AI SETTINGS ERROR:", error)

        return jsonify({
            "success": False,
            "message": "Failed to load AI settings."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/ai-settings", methods=["POST"])
def save_ai_settings():
    if not AI_PROVIDER_SERVICE_AVAILABLE:
        return jsonify({
            "success": False,
            "message": "AI provider service is not available on this server."
        }), 500

    data = request.get_json(silent=True) or {}

    actor_id = data.get("updated_by") or data.get("user_id")
    provider = str(data.get("provider", "")).strip().lower()
    model_name = str(data.get("model_name", "")).strip()
    api_key = str(data.get("api_key", "")).strip()

    if provider not in ai_provider_service.SUPPORTED_PROVIDERS:
        return jsonify({"success": False, "message": "Unsupported AI provider."}), 400

    if not model_name:
        return jsonify({"success": False, "message": "Model name is required."}), 400

    if not api_key:
        return jsonify({"success": False, "message": "API key is required."}), 400

    conn = None
    cursor = None

    try:
        conn = ai_provider_service.get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        ai_provider_service.ensure_ai_provider_configs_table(cursor)

        if not is_ai_settings_manager(cursor, actor_id):
            conn.rollback()
            return jsonify({
                "success": False,
                "message": "Only managers can update AI settings."
            }), 403

        ai_provider_service.save_ai_provider_config(
            cursor, provider, model_name, api_key, actor_id
        )

        conn.commit()

        add_audit_log(
            actor_id=actor_id,
            action="Updated AI provider settings",
            module="AI Settings",
            description=f"Active AI provider set to {provider} ({model_name})."
        )

        config = ai_provider_service.get_ai_provider_public_config(cursor)

        return jsonify({
            "success": True,
            "message": "AI settings saved successfully.",
            "config": config
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("SAVE AI SETTINGS ERROR:", error)

        return jsonify({
            "success": False,
            "message": "Failed to save AI settings."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/ai-settings/test", methods=["POST"])
def test_ai_settings():
    if not AI_PROVIDER_SERVICE_AVAILABLE:
        return jsonify({
            "success": False,
            "message": "AI provider service is not available on this server."
        }), 500

    data = request.get_json(silent=True) or {}

    actor_id = data.get("user_id")
    provider = str(data.get("provider", "")).strip().lower()
    model_name = str(data.get("model_name", "")).strip()
    api_key = str(data.get("api_key", "")).strip()

    conn = None
    cursor = None

    try:
        conn = ai_provider_service.get_db_connection()
        cursor = conn.cursor(dictionary=True)

        ai_provider_service.ensure_ai_provider_configs_table(cursor)

        if not is_ai_settings_manager(cursor, actor_id):
            return jsonify({
                "success": False,
                "message": "Only managers can test AI settings."
            }), 403

        # If the manager hasn't typed a provider/key in the form yet, fall
        # back to testing whatever is already saved.
        testing_saved_config = not provider or not api_key

        if testing_saved_config:
            existing = ai_provider_service.get_active_ai_provider_config(cursor)

            if not existing:
                return jsonify({
                    "success": False,
                    "message": "No AI provider is configured yet."
                }), 400

            provider = existing["provider"]
            model_name = existing["model_name"]
            api_key = ai_provider_service.decrypt_api_key(existing["encrypted_api_key"])

        try:
            ai_provider_service.call_ai_provider(
                "Reply with only: OK", provider, model_name, api_key
            )
            success = True
            message = "AI provider connected successfully."
        except requests.exceptions.Timeout:
            print("AI PROVIDER TEST CALL ERROR: timed out waiting for", provider)
            success = False
            message = (
                f"Connection to {provider} timed out. The provider may be slow "
                "or unreachable right now -- this is not an API key or billing "
                "problem. Please try again in a moment."
            )
        except requests.exceptions.HTTPError as call_error:
            status_code = call_error.response.status_code if call_error.response is not None else None
            print("AI PROVIDER TEST CALL ERROR:", status_code, call_error)
            if status_code == 429:
                message = "AI provider rejected the request: rate limit or quota exceeded (HTTP 429)."
            elif status_code in (401, 403):
                message = f"AI provider rejected the API key (HTTP {status_code}). Please check the key is correct and active."
            elif status_code == 404:
                message = f"AI provider could not find model \"{model_name}\" (HTTP 404). Please check the model name is correct and still supported."
            else:
                message = f"AI provider returned an error (HTTP {status_code})."
            success = False
        except Exception as call_error:
            print("AI PROVIDER TEST CALL ERROR:", call_error)
            success = False
            message = "AI provider connection failed. Please check your API key."

        if testing_saved_config:
            ai_provider_service.update_active_provider_test_status(cursor, success)
            conn.commit()

        return jsonify({"success": success, "message": message}), (200 if success else 400)

    except Exception as error:
        if conn:
            conn.rollback()

        print("TEST AI SETTINGS ERROR:", error)

        return jsonify({
            "success": False,
            "message": "AI provider connection failed. Please check your API key."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# NOTION SYNC ROUTES
#
# Reuses the exact same encryption service already built for AI provider
# keys (ai_provider_service.encrypt_api_key/decrypt_api_key/mask_api_key)
# instead of a second encryption scheme, and the same manager-only access
# check pattern used everywhere else in this file.
# =========================
@app.route("/api/notion-sync/config", methods=["GET"])
def get_notion_sync_config():
    if not NOTION_SYNC_SERVICE_AVAILABLE:
        return jsonify({"success": False, "message": "Notion sync service is not available on this server."}), 500

    conn = None
    cursor = None

    try:
        conn = notion_sync_service.get_db_connection()
        cursor = conn.cursor(dictionary=True)

        notion_sync_service.ensure_notion_sync_tables(cursor)
        config = notion_sync_service.get_notion_public_config(cursor)

        return jsonify({"success": True, "config": config}), 200

    except Exception as error:
        print("GET NOTION SYNC CONFIG ERROR:", error)
        return jsonify({"success": False, "message": "Failed to load Notion sync settings."}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/notion-sync/config", methods=["POST"])
def save_notion_sync_config():
    if not NOTION_SYNC_SERVICE_AVAILABLE:
        return jsonify({"success": False, "message": "Notion sync service is not available on this server."}), 500

    data = request.get_json(silent=True) or {}

    actor_id = data.get("updated_by") or data.get("user_id")
    raw_token = str(data.get("token", "")).strip()
    raw_source = str(data.get("source", "")).strip()

    if not raw_token:
        return jsonify({"success": False, "message": "Notion integration token is required."}), 400

    if not raw_source:
        return jsonify({"success": False, "message": "Notion page/database URL or ID is required."}), 400

    source_id = notion_sync_service.extract_notion_id(raw_source)

    if not source_id:
        return jsonify({"success": False, "message": "Could not read a valid Notion ID from that URL/ID."}), 400

    conn = None
    cursor = None

    try:
        conn = notion_sync_service.get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        notion_sync_service.ensure_notion_sync_tables(cursor)

        if not is_ai_settings_manager(cursor, actor_id):
            conn.rollback()
            return jsonify({"success": False, "message": "Only managers can update Notion sync settings."}), 403

        notion_sync_service.save_notion_config(cursor, raw_token, source_id, raw_source, actor_id)
        conn.commit()

        add_audit_log(
            actor_id=actor_id,
            action="Updated Notion sync settings",
            module="Notion Sync",
            description=f"Notion source set to {source_id}."
        )

        config = notion_sync_service.get_notion_public_config(cursor)

        return jsonify({"success": True, "message": "Notion sync settings saved successfully.", "config": config}), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("SAVE NOTION SYNC CONFIG ERROR:", error)
        return jsonify({"success": False, "message": "Failed to save Notion sync settings."}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/notion-sync/test", methods=["POST"])
def test_notion_sync():
    if not NOTION_SYNC_SERVICE_AVAILABLE:
        return jsonify({"success": False, "message": "Notion sync service is not available on this server."}), 500

    data = request.get_json(silent=True) or {}

    actor_id = data.get("user_id")
    raw_token = str(data.get("token", "")).strip()
    raw_source = str(data.get("source", "")).strip()

    conn = None
    cursor = None

    try:
        conn = notion_sync_service.get_db_connection()
        cursor = conn.cursor(dictionary=True)

        notion_sync_service.ensure_notion_sync_tables(cursor)

        if not is_ai_settings_manager(cursor, actor_id):
            return jsonify({"success": False, "message": "Only managers can test Notion sync."}), 403

        if not raw_token or not raw_source:
            existing = notion_sync_service.get_active_notion_config(cursor)

            if not existing:
                return jsonify({"success": False, "message": "No Notion sync source is configured yet."}), 400

            raw_token = ai_provider_service.decrypt_api_key(existing["encrypted_notion_token"])
            source_id = existing["source_id"]
        else:
            source_id = notion_sync_service.extract_notion_id(raw_source)

            if not source_id:
                return jsonify({"success": False, "message": "Could not read a valid Notion ID from that URL/ID."}), 400

        try:
            pages = notion_sync_service.list_notion_pages(raw_token, source_id)
            return jsonify({
                "success": True,
                "message": f"Notion connected successfully. Found {len(pages)} page(s)."
            }), 200
        except Exception as call_error:
            print("NOTION TEST CALL ERROR:", call_error)
            return jsonify({
                "success": False,
                "message": "Notion connection failed. Please make sure the page/database is shared with your integration, and the token is correct."
            }), 400

    except Exception as error:
        print("TEST NOTION SYNC ERROR:", error)
        return jsonify({"success": False, "message": "Notion connection failed."}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/notion-sync/run", methods=["POST"])
def run_notion_sync():
    if not NOTION_SYNC_SERVICE_AVAILABLE:
        return jsonify({"success": False, "message": "Notion sync service is not available on this server."}), 500

    data = request.get_json(silent=True) or {}
    actor_id = data.get("user_id")

    conn = None
    cursor = None

    try:
        conn = notion_sync_service.get_db_connection()
        cursor = conn.cursor(dictionary=True)

        notion_sync_service.ensure_notion_sync_tables(cursor)

        if not is_ai_settings_manager(cursor, actor_id):
            return jsonify({"success": False, "message": "Only managers can run Notion sync."}), 403

        config = notion_sync_service.get_active_notion_config(cursor)

        if not config:
            return jsonify({"success": False, "message": "No Notion sync source is configured yet."}), 400

        raw_token = ai_provider_service.decrypt_api_key(config["encrypted_notion_token"])

    except Exception as error:
        print("RUN NOTION SYNC SETUP ERROR:", error)
        return jsonify({"success": False, "message": "Failed to start Notion sync."}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    result = notion_sync_service.sync_notion_source(
        raw_token, config["source_id"], actor_id, UPLOAD_FOLDER
    )

    add_audit_log(
        actor_id=actor_id,
        action="Ran Notion sync",
        module="Notion Sync",
        description=f"Imported {result['imported']}, updated {result['updated']}, skipped {result['skipped']}, failed {result['failed']}."
    )

    return jsonify({"success": result["status"] == "completed", **result}), 200


@app.route("/api/notion-sync/jobs", methods=["GET"])
def get_notion_sync_jobs():
    if not NOTION_SYNC_SERVICE_AVAILABLE:
        return jsonify({"success": False, "message": "Notion sync service is not available on this server."}), 500

    conn = None
    cursor = None

    try:
        conn = notion_sync_service.get_db_connection()
        cursor = conn.cursor(dictionary=True)

        notion_sync_service.ensure_notion_sync_tables(cursor)

        cursor.execute("""
            SELECT id, status, imported_count, updated_count, skipped_count,
                   failed_count, error_message, started_at, completed_at
            FROM notion_sync_jobs
            ORDER BY id DESC
            LIMIT 20
        """)
        jobs = cursor.fetchall()

        return jsonify({"success": True, "jobs": jobs}), 200

    except Exception as error:
        print("GET NOTION SYNC JOBS ERROR:", error)
        return jsonify({"success": False, "message": "Failed to load Notion sync history."}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# AI CHAT + REAL AI PROVIDER FALLBACK
#
# The existing rule-based matcher (predict_intent.py / calculate_article_
# match_score) is intentionally strict -- it only auto-answers when it is
# fully confident, and escalates everything else to a Team Lead. This adds
# a real AI provider as an extra step that runs ONLY at the exact point
# where the rule-based system was already about to escalate, grounded in
# the actual Knowledge Base content. If the strict matcher already found a
# confident answer, none of this runs -- zero change to already-working
# behavior.
# =========================
def build_ai_chat_context(question, limit=5, max_chars=6000):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT article_id, title, content, category, sub_category
            FROM wiki_article
            WHERE COALESCE(is_deleted, 0) = 0
        """)
        articles = cursor.fetchall() or []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    scored_articles = []

    for article in articles:
        score = calculate_article_match_score(question, article)

        if score > 0:
            scored_articles.append((score, article))

    scored_articles.sort(key=lambda item: item[0], reverse=True)
    top_articles = [article for _, article in scored_articles[:limit]]

    def clean_text(text):
        text = re.sub(r"<[^>]+>", " ", str(text or ""))
        text = re.sub(r"\s+", " ", text).strip()
        return text

    chunks = []
    total_len = 0

    for article in top_articles:
        title = article.get("title") or ""
        body = clean_text(article.get("content"))
        entry = f"### {title}\n{body}\n"

        if total_len + len(entry) > max_chars:
            remaining = max_chars - total_len

            if remaining > 200:
                chunks.append(entry[:remaining])

            break

        chunks.append(entry)
        total_len += len(entry)

    return "\n".join(chunks)


def answer_question_with_ai_provider(question):
    """
    Returns {"answer": str, "sourceTitle": str} if the AI provider found a
    grounded answer in the Knowledge Base, or None if it couldn't (in
    which case the caller should fall through to the normal escalation
    flow -- this function never forces an answer that isn't grounded).
    """
    context_text = build_ai_chat_context(question)

    if not context_text.strip():
        return None

    prompt = f"""You are Jungle House's internal AI Wiki Assistant.

Answer the staff question using ONLY the provided Knowledge Base context
below. Do not invent company rules or information that isn't in the
context.

If the answer is not clearly found in the context, respond with ONLY this
exact JSON and nothing else:
{{"answered": false}}

If you can answer from the context, respond with ONLY valid JSON in this
exact shape (no markdown, no text outside the JSON):
{{"answered": true, "answer": "...", "sourceTitle": "..."}}

Keep the answer simple and practical for staff.

Staff question: {question}

Knowledge Base context:
{context_text}
"""

    raw_reply = ai_provider_service.generate_ai_reply(prompt)

    json_text = raw_reply.strip()
    json_text = re.sub(r"^```(?:json)?\s*", "", json_text)
    json_text = re.sub(r"\s*```$", "", json_text)

    parsed = json.loads(json_text)

    if not isinstance(parsed, dict) or not parsed.get("answered"):
        return None

    answer_text = str(parsed.get("answer") or "").strip()

    if not answer_text:
        return None

    return {
        "answer": answer_text,
        "sourceTitle": str(parsed.get("sourceTitle") or "").strip(),
    }


# =========================
# AI CHAT ROUTES
# =========================
@app.route("/chat", methods=["POST"])
@app.route("/api/chat", methods=["POST"])
def chat():
    data = {}
    uploaded_chat_image = None
    uploaded_chat_image_url = None
    uploaded_chat_image_type = None
    uploaded_chat_image_filename = ""

    try:
        if request.content_type and request.content_type.startswith("multipart/form-data"):
            question = request.form.get("question", "")
            uploaded_chat_image = request.files.get("image") or request.files.get("attachment")
            uploaded_chat_image_filename = uploaded_chat_image.filename if uploaded_chat_image else ""

            try:
                context_raw = request.form.get("context", "{}")
                data["context"] = json.loads(context_raw) if context_raw else {}
            except Exception:
                data["context"] = {}

            data["user_id"] = request.form.get("user_id") or request.form.get("userId")

            if uploaded_chat_image:
                uploaded_chat_image_url, uploaded_chat_image_type = save_chat_image(uploaded_chat_image)

                if uploaded_chat_image_url:
                    visual_match_result = search_visual_image_match(
                        uploaded_chat_image_url,
                        question=question
                    )

                    if visual_match_result:
                        clear_ai_fail_count(data, question)
                        remember_chat_context(data, visual_match_result)
                        log_request(
                            question,
                            result=visual_match_result,
                            user_id=data.get("user_id") or data.get("userId")
                        )

                        visual_match_result["final_source"] = visual_match_result.get("source")
                        visual_match_result["served_by"] = "image_embedding_retrieval"

                        return jsonify(visual_match_result), 200

                    # CLIP couldn't already answer confidently. Only spend a
                    # real Gemini Vision call when the staff member actually
                    # typed a question -- an image with no question at all
                    # is the cheap/free path (falls straight through to the
                    # existing filename-based text search below), which is
                    # the main cost-control lever for the vision API.
                    vision_result = None
                    used_vision = False

                    if question and len(question.strip()) >= 3:
                        local_image_path = get_local_image_path_from_url(uploaded_chat_image_url)

                        if local_image_path:
                            try:
                                file_hash = hashlib.md5(Path(local_image_path).read_bytes()).hexdigest()
                            except Exception:
                                file_hash = None

                            vision_result = analyze_uploaded_image_with_vision(local_image_path, file_hash)
                            used_vision = vision_result is not None

                    if used_vision and not vision_result.get("isWorkRelated") and vision_result.get("confidence", 0) >= 0.55:
                        rejection_result = build_image_irrelevant_response(vision_result)

                        log_request(
                            question,
                            result=rejection_result,
                            user_id=data.get("user_id") or data.get("userId")
                        )

                        rejection_result["final_source"] = rejection_result.get("source")
                        rejection_result["served_by"] = "vision_relevance_check"

                        return jsonify(rejection_result), 200

                    if used_vision and vision_result.get("isWorkRelated"):
                        question = build_vision_augmented_question(question, vision_result)
                        print("VISION-AUGMENTED SEARCH QUESTION:", question)
                    else:
                        image_search_text = extract_image_search_text(
                            uploaded_chat_image_url,
                            uploaded_chat_image_filename,
                            question
                        )

                        print("UPLOADED IMAGE FILENAME:", uploaded_chat_image_filename)
                        print("IMAGE SEARCH TEXT:", image_search_text)

                        question = image_search_text or question

        else:
            data = request.get_json(silent=True) or {}
            question = data.get("question", "")

        question = clean_question(question)
        q_lower = question.lower()

        greetings = ["hi", "hello", "hey", "morning", "afternoon", "evening", "good morning", "good afternoon", "good evening"]

        # =========================
        # ✅ STEP 0: GREETING
        # =========================
        if q_lower.strip() in greetings:
            return jsonify({
                "reply": "Hi! 👋 I can help you with SOP, kiosk steps, product info, or promotion.\n\nTry asking:\n- kiosk opening\n- show step 4\n- latest promotion",
                "confidence": 1.0,
                "source": "greeting",
                "fallback": False,
                "escalation_ready": False
            }), 200

        # =========================
        # ✅ STEP 1: NONSENSE / INVALID INPUT
        # Check Team Lead resolved answer first.
        # If none, first time = ask again, second time = escalate.
        # =========================
        if is_nonsense(question):
            retrieval_result = search_similar_question(question)

            if retrieval_result:
                result = normalize_result(retrieval_result, "database")

                clear_ai_fail_count(data, question)
                remember_chat_context(data, result)
                log_request(
                    question,
                    result=result,
                    user_id=data.get("user_id") or data.get("userId")
                )

                result["final_source"] = result.get("source")
                result["served_by"] = "team_lead_answer"

                return jsonify(result), 200

            fail_key = get_ai_fail_key(data, question)
            AI_FAIL_MEMORY[fail_key] = AI_FAIL_MEMORY.get(fail_key, 0) + 1

            if AI_FAIL_MEMORY[fail_key] >= 2:
                result = {
                    "reply": "I still could not understand the question after repeated attempts. I’ll escalate this to a team lead.",
                    "answer": "I still could not understand the question after repeated attempts. I’ll escalate this to a team lead.",
                    "confidence": 0.0,
                    "score": 0.0,
                    "source": "repeated_invalid_input",
                    "fallback": True,
                    "escalation_ready": True,
                    "escalation_required": True
                }

                escalation_id = create_escalation(
                    question,
                    result,
                    data.get("user_id") or data.get("userId"),
                    uploaded_chat_image_url,
                    uploaded_chat_image_type
                )

                AI_FAIL_MEMORY.pop(fail_key, None)

                result["escalation"] = True
                result["escalation_id"] = escalation_id
                result["served_by"] = "escalation_queue"

                return jsonify(result), 200

            return jsonify({
                "reply": (
                    "I could not understand your question clearly.\n\n"
                    "Please ask again using a clearer topic, for example:\n"
                    "- kiosk opening\n"
                    "- kiosk closing\n"
                    "- latest promotion\n"
                    "- public holiday\n"
                    "- new bee 1st day"
                ),
                "answer": (
                    "I could not understand your question clearly.\n\n"
                    "Please ask again using a clearer topic."
                ),
                "confidence": 0.0,
                "score": 0.0,
                "source": "invalid_input_first_attempt",
                "fallback": True,
                "escalation_ready": False,
                "escalation_required": False
            }), 200

        # =========================
        # ✅ STEP 2: CLEAN QUESTION
        # =========================
        question = clean_question(question)

                # =========================
        # HANDLE "NAME is?" STYLE QUESTION
        # Example: "Brian is?" -> "who is Brian"
        # =========================
        name_is_match = re.fullmatch(r"([a-zA-Z]+)\s+is\??", question.strip())

        if name_is_match:
            name = name_is_match.group(1)
            question = f"who is {name}"

        if not question:
            return jsonify({
                "reply": "Please ask a question.",
                "fallback": True
            }), 400


        # =========================
        # ✅ STEP 2.5: STAFF SAYS PREVIOUS ANSWER IS NOT WHAT THEY MEAN
        # Example:
        # Staff asks: "Liong"
        # AI gives possible answers
        # Staff replies: "not this" / "dont know"
        # Escalation should save original question: "Liong"
        # =========================
        if is_staff_not_satisfied(question):
            last_answer = AI_LAST_ANSWER_MEMORY.get(get_last_answer_key(data))

            if not last_answer:
                return jsonify({
                    "reply": (
                        "I understand this answer is not what you want, but I cannot find the previous question clearly.\n\n"
                        "Please type the original question again so I can escalate the correct question to the team lead."
                    ),
                    "answer": (
                        "I understand this answer is not what you want, but I cannot find the previous question clearly. "
                        "Please type the original question again so I can escalate the correct question to the team lead."
                    ),
                    "confidence": 0.0,
                    "score": 0.0,
                    "source": "staff_not_satisfied_no_previous_question",
                    "fallback": True,
                    "escalation_ready": False,
                    "escalation_required": False
                }), 200

            previous_question = clean_question(last_answer.get("question") or question)
            old_result = last_answer.get("result") or {}

            wrong_answer_text = (
                old_result.get("title")
                or old_result.get("answer")
                or old_result.get("reply")
                or "No previous answer text"
            )

            previous_result = {
                "answer": (
                    "Staff said this previous AI answer was not correct.\n\n"
                    f"Original staff question: {previous_question}\n\n"
                    f"Wrong AI answer/source: {wrong_answer_text}\n\n"
                    f"Staff latest message: {question}"
                ),
                "reply": (
                    "Staff said this previous AI answer was not correct.\n\n"
                    f"Original staff question: {previous_question}\n\n"
                    f"Wrong AI answer/source: {wrong_answer_text}\n\n"
                    f"Staff latest message: {question}"
                ),
                "confidence": 0.0,
                "score": 0.0,
                "source": "staff_not_satisfied_escalated",
                "fallback": True,
                "escalation_ready": True,
                "escalation_required": True
            }

            escalation_id = create_escalation(
                previous_question,
                previous_result,
                data.get("user_id") or data.get("userId"),
                uploaded_chat_image_url,
                uploaded_chat_image_type
            )

            clear_ai_fail_count(data, previous_question)

            return jsonify({
                "question": previous_question,
                "reply": (
                    "I detected that the previous answer may not be the content you wanted.\n\n"
                    f"I have escalated the original question to a team lead: {previous_question}"
                ),
                "answer": (
                    "I detected that the previous answer may not be the content you wanted. "
                    f"I have escalated the original question to a team lead: {previous_question}"
                ),
                "confidence": 0.0,
                "score": 0.0,
                "source": "staff_not_satisfied_escalated",
                "fallback": True,
                "escalation": True,
                "escalation_ready": True,
                "escalation_required": True,
                "escalation_id": escalation_id,
                "served_by": "escalation_queue",
                "options": [
                    {
                        "label": "Escalated to team lead",
                        "value": "escalated",
                        "type": "status"
                    }
                ]
            }), 200

        # =========================
        # CHECK TEAM LEAD ANSWER FIRST
        # But broad words like "opening" or "daily" should go to AI/KB matching first.
        # This prevents old Team Lead answers like "ok" from blocking topic selection.
        # =========================
        skip_team_lead_first = is_broad_topic_question(question)

        if not skip_team_lead_first:
            team_lead_result = search_similar_question(question, team_lead_only=True)

            if team_lead_result:
                result = normalize_result(team_lead_result, "team_lead")

                clear_ai_fail_count(data, question)
                remember_chat_context(data, result)
                log_request(
                    question,
                    result=result,
                    user_id=data.get("user_id") or data.get("userId")
                )
                remember_last_ai_answer(data, question, result)

                result["final_source"] = result.get("source")
                result["served_by"] = "team_lead_answer"

                return jsonify(result), 200

        # =========================
        # ✅ STEP 3: CALL AI
        # =========================
        result, status_code = process_question(
            question=question,
            context=prepare_chat_context(data),
        )

        # =========================
        # GENERIC ANSWER SHOULD ESCALATE
        # Example:
        # "honeybee" -> generic_product choices -> escalate to team lead
        # =========================
        if should_escalate_generic_answer(question, result):
            escalation_id = create_escalation(
                question,
                result,
                data.get("user_id") or data.get("userId"),
                uploaded_chat_image_url,
                uploaded_chat_image_type
            )

            result = {
                "question": question,
                "reply": (
                    "I could not find a specific answer for this question.\n\n"
                    "I have escalated it to a team lead. Once the team lead answers, "
                    "the answer will be saved for future staff questions."
                ),
                "answer": (
                    "I could not find a specific answer for this question. "
                    "I have escalated it to a team lead. Once the team lead answers, "
                    "the answer will be saved for future staff questions."
                ),
                "confidence": 0.0,
                "score": 0.0,
                "confidence_label": "low",
                "source": "generic_answer_escalated",
                "fallback": True,
                "escalation": True,
                "escalation_ready": True,
                "escalation_required": True,
                "escalation_id": escalation_id,
                "served_by": "escalation_queue",
                "options": [
                    {
                        "label": "Escalated to team lead",
                        "value": "escalated",
                        "type": "status"
                    }
                ]
            }

        remember_chat_context(data, result)
        log_request(
                    question,
                    result=result,
                    user_id=data.get("user_id") or data.get("userId")
                )
        remember_last_ai_answer(data, question, result)

        # =========================
        # ✅ STEP 4: ESCALATION LOGIC
        # =========================
        LOW_CONFIDENCE_THRESHOLD = 1.0

        clarification_sources = [
            "clarification_round_1",
            "unclear_question_clarification",
            "system_problem_clarification",
                "step_request_missing_topic",
        ]

        force_escalation_sources = [
            "repeated_unclear_question",
            "repeated_system_problem",
            "escalate_after_two_unclear_attempts",
            "irrelevant_question",
            "fallback",
            "unknown",
            "prediction_error",
            "engine_unavailable",
            "low_confidence_or_model_unavailable",
            "invalid_input_first_attempt",
            "staff_not_satisfied_escalated",
            "generic_answer_escalated",
            "repeated_invalid_input",
            "repeated_failed_answer",
        ]

        source = result.get("source", "")

        fail_count = update_ai_fail_count(data, question, result)

        should_escalate = False

        if fail_count >= 2:
            should_escalate = True
            result["reply"] = "I could not find a confident answer after repeated attempts. I’ll escalate this to a team lead."
            result["answer"] = result["reply"]
            result["source"] = "repeated_failed_answer"
            result["fallback"] = True
            result["escalation_ready"] = True
            result["escalation_required"] = True

        elif result.get("escalation_ready"):
            should_escalate = True

        elif source in force_escalation_sources:
            should_escalate = True

        elif source in clarification_sources:
            should_escalate = False

        elif result.get("confidence", result.get("score", 0)) < LOW_CONFIDENCE_THRESHOLD:
            should_escalate = True

        # Before actually escalating, give a real AI provider (if the
        # manager has configured one) one chance to answer, grounded only
        # in the real Knowledge Base content. Any failure here (not
        # configured, bad AI output, provider outage) falls straight
        # through to the normal escalation flow below -- this can only
        # ever prevent an escalation, never cause one that wasn't already
        # about to happen.
        if should_escalate and AI_PROVIDER_SERVICE_AVAILABLE:
            try:
                ai_answer = answer_question_with_ai_provider(question)
            except ai_provider_service.AIProviderNotConfiguredError:
                ai_answer = None
            except Exception as error:
                print("AI CHAT PROVIDER FALLBACK ERROR:", error)
                ai_answer = None

            if ai_answer:
                result["reply"] = ai_answer["answer"]
                result["answer"] = ai_answer["answer"]
                result["message"] = ai_answer["answer"]
                result["title"] = ai_answer["sourceTitle"] or result.get("title")
                result["source"] = "ai_provider_answer"
                result["fallback"] = False
                result["fallback_message"] = ""
                result["escalation_ready"] = False
                result["escalation_required"] = False
                should_escalate = False
                clear_ai_fail_count(data, question)

        if should_escalate:
            escalation_id = create_escalation(
            question,
            result,
            data.get("user_id") or data.get("userId"),
            uploaded_chat_image_url,
            uploaded_chat_image_type
        )

            clear_ai_fail_count(data, question)

            result["escalation"] = True
            result["escalation_ready"] = True
            result["escalation_required"] = True
            result["escalation_id"] = escalation_id
            result["served_by"] = "escalation_queue"

            if escalation_id is None:
                result["reply"] = "Escalation failed to save. Please check backend terminal for CREATE ESCALATION ERROR."
                result["answer"] = result["reply"]
                result["source"] = "escalation_save_failed"

            return jsonify(result), 200

        # =========================
        # ✅ STEP 5: SAVE GOOD ANSWER
        # =========================
        if (
            result.get("confidence", 0) >= 0.7
            and not result.get("fallback")
            and result.get("source") != "ai_provider_answer"
            and not is_nonsense(question)
            and not is_nonsense(result.get("answer", ""))
        ):
            save_qa_to_db(question, result)

        result["final_source"] = result.get("source")
        result["served_by"] = "ai"

        return jsonify(result), 200

    except Exception as error:
        traceback.print_exc()

        question = clean_question(data.get("question", ""))

        log_request(
            question,
            error=str(error),
            user_id=data.get("user_id") or data.get("userId")
        )

        escalation_id = create_escalation(
            question,
            {
                "answer": str(error),
                "confidence": 0.0,
                "source": "system_error"
            },
            data.get("user_id") or data.get("userId"),
            uploaded_chat_image_url,
            uploaded_chat_image_type
        )

        return jsonify({
            "reply": "System error. Escalated to team lead.",
            "confidence": 0,
            "fallback": True,
            "escalation": True,
            "escalation_id": escalation_id
        }), 500


# =========================
# KNOWLEDGE BASE ROUTES
# Active Articles / Retrieve Bin
# =========================
@app.route("/api/articles", methods=["GET"])
def get_articles():
    conn = None
    cursor = None

    try:
        show_deleted = request.args.get("deleted", "false").lower() == "true"

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                article_id,
                title,
                content,
                category,
                sub_category,
                link,
                attachment_url,
                attachment_type,
                image_files,
                is_deleted,
                deleted_at,
                deleted_by
            FROM wiki_article
            WHERE is_deleted = %s
            ORDER BY article_id DESC
        """, (show_deleted,))

        articles = cursor.fetchall()

        return jsonify(articles), 200

    except mysql.connector.Error as err:
        print("MYSQL ERROR /api/articles:", err)
        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
        print("GENERAL ERROR /api/articles:", e)
        return jsonify({"message": f"Server error: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# Add Article ROUTES
# =========================
@app.route("/api/articles", methods=["POST"])
def add_article():
    conn = None
    cursor = None

    try:
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        sub_category = request.form.get("sub_category", "").strip()
        link = request.form.get("link", "").strip()
        content = request.form.get("content", "").strip()

        if not title or not content:
            return jsonify({"message": "Title and content are required."}), 400

        # Multiple image upload support.
        # Frontend must append files using the key name: attachments
        uploaded_files = request.files.getlist("attachments")
        saved_files = save_article_attachments(uploaded_files)

        # Keep old single-file columns for backward compatibility.
        attachment_url = saved_files[0]["url"] if saved_files else None
        attachment_type = saved_files[0]["type"] if saved_files else None

        # Store all uploaded image/file paths as JSON text.
        image_files = json.dumps(saved_files) if saved_files else None

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        ensure_wiki_article_content_capacity(cursor)

        cursor.execute("""
            INSERT INTO wiki_article
            (
                title,
                content,
                category,
                sub_category,
                link,
                attachment_url,
                attachment_type,
                image_files,
                is_deleted
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE)
        """, (
            title,
            content,
            category,
            sub_category,
            link,
            attachment_url,
            attachment_type,
            image_files
        ))

        conn.commit()

        return jsonify({
            "message": "Article added successfully.",
            "article_id": cursor.lastrowid,
            "attachment_url": attachment_url,
            "attachment_type": attachment_type,
            "image_files": saved_files
        }), 201

    except Exception as error:
        print("ADD ARTICLE ERROR:", error)
        return jsonify({
            "message": "Failed to save article.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# =========================
# Article Links ROUTES
# =========================
@app.route("/api/article-links/<int:article_id>", methods=["GET"])
def get_article_links(article_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                link_id,
                article_id,
                label,
                url
            FROM article_links
            WHERE article_id = %s
            ORDER BY link_id ASC
        """, (article_id,))

        links = cursor.fetchall()
        return jsonify(links), 200

    except mysql.connector.Error as err:
        print("MYSQL ERROR /api/article-links:", err)
        return jsonify([]), 200

    except Exception as error:
        print("GENERAL ERROR /api/article-links:", error)
        return jsonify([]), 200

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# Get Single Article ROUTES
# =========================
@app.route('/api/articles/<int:article_id>', methods=['GET'])
def get_article_detail(article_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                article_id, 
                title, 
                content, 
                category, 
                sub_category, 
                link,
                attachment_url,
                attachment_type,
                image_files
            FROM wiki_article
            WHERE article_id = %s
            AND is_deleted = FALSE
            LIMIT 1
        """, (article_id,))

        article = cursor.fetchone()

        if not article:
            return jsonify({'message': 'Article not found.'}), 404

        return jsonify(article), 200

    except Exception as error:
        print('MYSQL ERROR /api/articles/<id> GET:', error)
        return jsonify({
            'message': 'Failed to load article.',
            'error': str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



# =========================
# EDITOR IMAGE UPLOAD ROUTE
# Used by the JoditEditor "uploader" in AddArticle/EditArticle so pasted or
# dropped images are saved as real files and inserted as a URL, instead of
# being embedded inline as a giant base64 string (which used to overflow the
# wiki_article.content column and make the save fail).
# =========================
@app.route("/api/articles/upload-image", methods=["POST"])
def upload_article_editor_image():
    uploaded_files = request.files.getlist("attachments")

    if not uploaded_files:
        uploaded_files = list(request.files.values())

    saved_files = save_article_attachments(uploaded_files)

    if not saved_files:
        return jsonify({
            "files": [],
            "path": "",
            "baseurl": "",
            "error": 1,
            "msg": "No valid image file was uploaded."
        }), 400

    base_url = get_public_request_base_url()
    file_urls = [f"{base_url}{item['url']}" for item in saved_files]

    return jsonify({
        "files": file_urls,
        "path": "",
        "baseurl": "",
        "error": 0,
        "msg": "success"
    }), 200


# =========================
# Edit Article ROUTES
# =========================
@app.route('/api/articles/<int:article_id>', methods=['PUT'])
def edit_article(article_id):
    title = request.form.get('title', '').strip()
    category = request.form.get('category', '').strip()
    sub_category = request.form.get('sub_category', '').strip()
    link = request.form.get('link', '').strip()
    content = request.form.get('content', '').strip()

    if not title or not content:
        return jsonify({'message': 'Title and content are required.'}), 400

    # Multiple image upload support.
    # Frontend must append files using the key name: attachments
    uploaded_files = request.files.getlist("attachments")
    saved_files = save_article_attachments(uploaded_files)

    # Files the client wants to KEEP from what was already attached to this
    # article (JSON array of {url, type, name}). The client is expected to
    # always send this (even as "[]") so removals are explicit; if it's
    # missing entirely (older client), fall back to keeping everything that
    # was already there so we never silently drop existing attachments.
    existing_attachments_raw = request.form.get("existing_attachments")

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        ensure_wiki_article_content_capacity(cursor)

        cursor.execute("""
            SELECT attachment_url, attachment_type, image_files, content
            FROM wiki_article
            WHERE article_id = %s
            LIMIT 1
        """, (article_id,))

        old_article = cursor.fetchone() or {}
        old_filenames = extract_article_upload_filenames(old_article)

        if existing_attachments_raw is not None:
            try:
                kept_attachments = json.loads(existing_attachments_raw)
                if not isinstance(kept_attachments, list):
                    kept_attachments = []
            except Exception:
                kept_attachments = []
        else:
            kept_attachments = []
            old_image_files_raw = old_article.get("image_files")
            if old_image_files_raw:
                try:
                    parsed_old = (
                        json.loads(old_image_files_raw)
                        if isinstance(old_image_files_raw, str)
                        else old_image_files_raw
                    )
                    if isinstance(parsed_old, list):
                        kept_attachments = parsed_old
                except Exception:
                    kept_attachments = []
            elif old_article.get("attachment_url"):
                kept_attachments = [{
                    "url": old_article.get("attachment_url"),
                    "type": old_article.get("attachment_type"),
                }]

        final_files = [
            item for item in kept_attachments if isinstance(item, dict) and item.get("url")
        ] + saved_files

        attachment_url = final_files[0]["url"] if final_files else None
        attachment_type = final_files[0]["type"] if final_files else None
        image_files = json.dumps(final_files) if final_files else None

        cursor.execute("""
            UPDATE wiki_article
            SET title = %s,
                content = %s,
                category = %s,
                link = %s,
                sub_category = %s,
                attachment_url = %s,
                attachment_type = %s,
                image_files = %s
            WHERE article_id = %s
        """, (
            title,
            content,
            category,
            link,
            sub_category,
            attachment_url,
            attachment_type,
            image_files,
            article_id
        ))

        new_filenames = extract_article_upload_filenames({
            "attachment_url": attachment_url,
            "image_files": image_files,
            "content": content,
        })

        conn.commit()

        # Any file that was referenced before this edit but no longer
        # appears anywhere in the saved article (e.g. removed by the user,
        # or an image pasted by mistake and then removed inside the editor)
        # is now orphaned on the volume -- clean it up instead of leaving
        # it there forever.
        delete_upload_filenames(old_filenames - new_filenames)

        add_audit_log(
            action="Edited article",
            module="Content Management",
            description=f"Article updated: {title}"
        )

        return jsonify({
            'message': 'Article updated successfully.',
            'image_files': final_files
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print('MYSQL ERROR /api/articles PUT:', error)

        return jsonify({
            'message': 'Failed to update article.',
            'error': str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# =========================
# SOFT DELETE ARTICLE ROUTE
# Move article to Retrieve Bin
# =========================
@app.route('/api/articles/<int:article_id>', methods=['DELETE'])
def delete_article(article_id):
    conn = None
    cursor = None

    try:
        data = request.get_json(silent=True) or {}
        deleted_by = data.get("deleted_by")

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            UPDATE wiki_article
            SET 
                is_deleted = TRUE,
                deleted_at = NOW(),
                deleted_by = %s
            WHERE article_id = %s
        """, (deleted_by, article_id))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({'message': 'Article not found.'}), 404

        add_audit_log(
            actor_id=deleted_by,
            action="Moved article to Retrieve Bin",
            module="Content Management",
            description=f"Article ID {article_id} was soft deleted."
        )

        return jsonify({
            'message': 'Article moved to Retrieve Bin successfully.'
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print('MYSQL ERROR /api/articles DELETE:', error)

        return jsonify({
            'message': 'Failed to move article to Retrieve Bin.',
            'error': str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# RESTORE ARTICLE ROUTE
# Restore article from Retrieve Bin
# =========================
@app.route('/api/articles/<int:article_id>/restore', methods=['PUT'])
def restore_article(article_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            UPDATE wiki_article
            SET 
                is_deleted = FALSE,
                deleted_at = NULL,
                deleted_by = NULL
            WHERE article_id = %s
        """, (article_id,))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({'message': 'Article not found.'}), 404

        add_audit_log(
            action="Restored article",
            module="Content Management",
            description=f"Article ID {article_id} was restored from Retrieve Bin."
        )

        return jsonify({
            'message': 'Article restored successfully.'
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print('MYSQL ERROR /api/articles RESTORE:', error)

        return jsonify({
            'message': 'Failed to restore article.',
            'error': str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
def extract_article_upload_filenames(article_row):
    """
    Collect every uploads/articles/<filename> referenced by this article --
    attachment_url, the image_files JSON column, and any <img src="..."> baked
    directly into the rich-text content -- so permanent delete can also
    remove the actual files from the volume instead of leaving them orphaned
    on disk forever.
    """
    filenames = set()

    def add_from_url(url):
        match = re.search(r"/static/uploads/articles/([^\s\"'?]+)", str(url or ""))

        if match:
            filenames.add(match.group(1))

    add_from_url(article_row.get("attachment_url"))

    image_files_raw = article_row.get("image_files")

    if image_files_raw:
        try:
            parsed = json.loads(image_files_raw) if isinstance(image_files_raw, str) else image_files_raw

            if isinstance(parsed, list):
                for item in parsed:
                    add_from_url(item.get("url") if isinstance(item, dict) else item)
        except Exception:
            pass

    content = article_row.get("content") or ""

    for match in re.finditer(r"/static/uploads/articles/([^\s\"'?]+)", content):
        filenames.add(match.group(1))

    return filenames


def delete_upload_filenames(filenames):
    for filename in filenames:
        try:
            file_path = UPLOAD_FOLDER / filename

            if file_path.exists() and file_path.is_file():
                file_path.unlink()
        except Exception as error:
            print("DELETE ARTICLE FILE ERROR:", filename, error)


def delete_article_upload_files(article_row):
    delete_upload_filenames(extract_article_upload_filenames(article_row))


# =========================
# BULK PERMANENT DELETE ARTICLE ROUTE
# Delete selected articles permanently from Retrieve Bin only
# =========================
@app.route('/api/articles/bulk-permanent-delete', methods=['POST'])
def bulk_permanent_delete_articles():
    conn = None
    cursor = None

    try:
        data = request.get_json(silent=True) or {}

        article_ids = data.get("article_ids") or data.get("ids") or []
        deleted_by = data.get("deleted_by")

        clean_ids = []

        for item in article_ids:
            try:
                clean_id = int(item)

                if clean_id not in clean_ids:
                    clean_ids.append(clean_id)

            except (TypeError, ValueError):
                continue

        if not clean_ids:
            return jsonify({
                "message": "No article selected for permanent deletion."
            }), 400

        placeholders = ",".join(["%s"] * len(clean_ids))

        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        # 1. Only delete articles that are already inside Retrieve Bin.
        cursor.execute(f"""
            SELECT article_id, attachment_url, image_files, content
            FROM wiki_article
            WHERE article_id IN ({placeholders})
            AND COALESCE(is_deleted, 0) = 1
        """, tuple(clean_ids))

        trash_rows = cursor.fetchall()
        trash_ids = [row["article_id"] for row in trash_rows]

        if not trash_ids:
            conn.rollback()
            return jsonify({
                "message": "No selected article found in Retrieve Bin."
            }), 404

        trash_placeholders = ",".join(["%s"] * len(trash_ids))

        # 2. Delete related article links first.
        # If the article_links table does not exist, skip this part safely.
        try:
            cursor.execute(f"""
                DELETE FROM article_links
                WHERE article_id IN ({trash_placeholders})
            """, tuple(trash_ids))
        except mysql.connector.Error as link_error:
            if getattr(link_error, "errno", None) == 1146:
                print("article_links table does not exist, skipping article link delete.")
            else:
                raise

        # 3. Delete selected articles permanently.
        cursor.execute(f"""
            DELETE FROM wiki_article
            WHERE article_id IN ({trash_placeholders})
            AND COALESCE(is_deleted, 0) = 1
        """, tuple(trash_ids))

        deleted_count = cursor.rowcount

        conn.commit()

        for row in trash_rows:
            delete_article_upload_files(row)

        add_audit_log(
            actor_id=deleted_by,
            action="Bulk permanently deleted articles",
            module="Content Management",
            description=f"{deleted_count} article(s) were permanently deleted from Retrieve Bin."
        )

        return jsonify({
            "message": f"{deleted_count} article(s) permanently deleted successfully.",
            "deleted_count": deleted_count
        }), 200

    except mysql.connector.Error as err:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/articles/bulk-permanent-delete:", err)

        return jsonify({
            "message": "Failed to permanently delete selected articles.",
            "error": str(err)
        }), 500

    except Exception as error:
        if conn:
            conn.rollback()

        print("GENERAL ERROR /api/articles/bulk-permanent-delete:", error)

        return jsonify({
            "message": "Failed to permanently delete selected articles.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# PERMANENT DELETE ARTICLE ROUTE
# Delete article permanently from Retrieve Bin only
# Also removes related article links first
# =========================
@app.route('/api/articles/<int:article_id>/permanent-delete', methods=['DELETE'])
def permanent_delete_article(article_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Check article exists in Retrieve Bin
        cursor.execute("""
            SELECT article_id, attachment_url, image_files, content
            FROM wiki_article
            WHERE article_id = %s
            AND is_deleted = TRUE
            LIMIT 1
        """, (article_id,))

        article = cursor.fetchone()

        if not article:
            return jsonify({
                'message': 'Article not found in Retrieve Bin.'
            }), 404

        # 2. Delete related article links first
        cursor.execute("""
            DELETE FROM article_links
            WHERE article_id = %s
        """, (article_id,))

        # 3. Delete article permanently
        cursor.execute("""
            DELETE FROM wiki_article
            WHERE article_id = %s
            AND is_deleted = TRUE
        """, (article_id,))

        conn.commit()

        delete_article_upload_files(article)

        add_audit_log(
            action="Permanently deleted article",
            module="Content Management",
            description=f"Article ID {article_id} was permanently deleted from Retrieve Bin."
        )

        return jsonify({
            'message': 'Article permanently deleted successfully.'
        }), 200

    except mysql.connector.Error as err:
        if conn:
            conn.rollback()

        print('MYSQL ERROR /api/articles PERMANENT DELETE:', err)

        return jsonify({
            'message': f'Database error: {str(err)}'
        }), 500

    except Exception as error:
        if conn:
            conn.rollback()

        print('GENERAL ERROR /api/articles PERMANENT DELETE:', error)

        return jsonify({
            'message': 'Failed to permanently delete article.',
            'error': str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



# =========================
# ESCALATION ROUTES
# =========================

def _safe_int_value(value):
    if value is None:
        return None

    text_value = str(value).strip()
    if text_value == "" or text_value.lower() in {"null", "none", "undefined"}:
        return None

    try:
        return int(text_value)
    except (TypeError, ValueError):
        return None


def _get_table_columns(cursor, table_name):
    cursor.execute(f"SHOW COLUMNS FROM {table_name}")
    rows = cursor.fetchall()
    columns = set()

    for row in rows:
        if isinstance(row, dict):
            column_name = row.get("Field")
        else:
            column_name = row[0] if row else None

        if column_name:
            columns.add(str(column_name))

    return columns


def _save_approved_escalation_to_qa_knowledge(cursor, question, answer, image_url=None, image_type=None):
    """
    Save approved escalation answer into qa_knowledge only after Manager/Admin approval.
    This helper updates an existing same-question row first to avoid duplicate-key errors.
    """
    question = str(question or "").strip()
    answer = str(answer or "").strip()

    if not question or not answer:
        return

    columns = _get_table_columns(cursor, "qa_knowledge")

    if "question" not in columns or "answer" not in columns:
        return

    cursor.execute("""
        SELECT question
        FROM qa_knowledge
        WHERE question = %s
        LIMIT 1
    """, (question,))
    existing = cursor.fetchone()

    if existing:
        set_parts = ["answer = %s"]
        params = [answer]

        if "source" in columns:
            set_parts.append("source = %s")
            params.append("manager_approved_review")

        if "confidence" in columns:
            set_parts.append("confidence = %s")
            params.append(1.0)

        if "image_url" in columns:
            set_parts.append("image_url = %s")
            params.append(image_url)

        if "image_type" in columns:
            set_parts.append("image_type = %s")
            params.append(image_type)

        params.append(question)

        cursor.execute(f"""
            UPDATE qa_knowledge
            SET {', '.join(set_parts)}
            WHERE question = %s
        """, tuple(params))

        return

    insert_columns = ["question", "answer"]
    placeholders = ["%s", "%s"]
    params = [question, answer]

    if "source" in columns:
        insert_columns.append("source")
        placeholders.append("%s")
        params.append("manager_approved_review")

    if "confidence" in columns:
        insert_columns.append("confidence")
        placeholders.append("%s")
        params.append(1.0)

    if "image_url" in columns:
        insert_columns.append("image_url")
        placeholders.append("%s")
        params.append(image_url)

    if "image_type" in columns:
        insert_columns.append("image_type")
        placeholders.append("%s")
        params.append(image_type)

    cursor.execute(f"""
        INSERT INTO qa_knowledge ({', '.join(insert_columns)})
        VALUES ({', '.join(placeholders)})
    """, tuple(params))

def _save_approved_escalation_to_image_retrieval(cursor, escalation_id, question, answer, image_url=None, image_type=None):
    """
    Save Manager-approved escalation image answer into image_retrieval.
    This allows AI Chat to reuse approved image answers later.
    """
    question = str(question or "").strip()
    answer = str(answer or "").strip()
    image_url = str(image_url or "").strip()
    image_type = str(image_type or "").strip() or None

    if not question or not answer or not image_url:
        return

    try:
        columns = _get_table_columns(cursor, "image_retrieval")
    except Exception as error:
        print("IMAGE RETRIEVAL TABLE NOT READY:", error)
        return

    required_columns = {"source_type", "source_id", "question", "answer", "image_url"}
    if not required_columns.issubset(columns):
        print("IMAGE RETRIEVAL TABLE MISSING REQUIRED COLUMNS")
        return

    cursor.execute("""
        SELECT image_id
        FROM image_retrieval
        WHERE source_type = 'approved_escalation'
        AND source_id = %s
        LIMIT 1
    """, (escalation_id,))

    existing = cursor.fetchone()

    image_caption = answer
    image_keywords = question

    image_embedding = None

    if image_url and IMAGE_EMBEDDING_AVAILABLE and create_image_embedding:
        local_image_path = get_local_image_path_from_url(image_url)

        if local_image_path:
            image_embedding = create_image_embedding(local_image_path)

    if existing:
        set_parts = [
            "question = %s",
            "answer = %s",
            "image_url = %s"
        ]
        params = [question, answer, image_url]

        if "image_type" in columns:
            set_parts.append("image_type = %s")
            params.append(image_type)

        if "image_caption" in columns:
            set_parts.append("image_caption = %s")
            params.append(image_caption)

        if "image_keywords" in columns:
            set_parts.append("image_keywords = %s")
            params.append(image_keywords)

        if "approval_status" in columns:
            set_parts.append("approval_status = %s")
            params.append("approved")

        if "image_embedding" in columns:
            set_parts.append("image_embedding = %s")
            params.append(image_embedding)

        if "embedding_model" in columns:
            set_parts.append("embedding_model = %s")
            params.append(IMAGE_EMBEDDING_MODEL_NAME)

        if "visual_match_enabled" in columns:
            set_parts.append("visual_match_enabled = %s")
            params.append(1)

        params.append(escalation_id)

        cursor.execute(f"""
            UPDATE image_retrieval
            SET {', '.join(set_parts)}
            WHERE source_type = 'approved_escalation'
            AND source_id = %s
        """, tuple(params))

        return

    insert_columns = [
        "source_type",
        "source_id",
        "question",
        "answer",
        "image_url"
    ]
    placeholders = ["%s", "%s", "%s", "%s", "%s"]
    params = [
        "approved_escalation",
        escalation_id,
        question,
        answer,
        image_url
    ]

    if "image_type" in columns:
        insert_columns.append("image_type")
        placeholders.append("%s")
        params.append(image_type)

    if "image_caption" in columns:
        insert_columns.append("image_caption")
        placeholders.append("%s")
        params.append(image_caption)

    if "image_keywords" in columns:
        insert_columns.append("image_keywords")
        placeholders.append("%s")
        params.append(image_keywords)

    if "approval_status" in columns:
        insert_columns.append("approval_status")
        placeholders.append("%s")
        params.append("approved")

    if "image_embedding" in columns:
        insert_columns.append("image_embedding")
        placeholders.append("%s")
        params.append(image_embedding)

    if "embedding_model" in columns:
        insert_columns.append("embedding_model")
        placeholders.append("%s")
        params.append(IMAGE_EMBEDDING_MODEL_NAME)

    if "visual_match_enabled" in columns:
        insert_columns.append("visual_match_enabled")
        placeholders.append("%s")
        params.append(1)

    cursor.execute(f"""
        INSERT INTO image_retrieval ({', '.join(insert_columns)})
        VALUES ({', '.join(placeholders)})
    """, tuple(params))


@app.route('/api/escalations', methods=['GET'])
def get_escalations():
    conn = None
    cursor = None

    try:
        show_deleted = request.args.get("deleted", "false").lower() == "true"

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                e.escalation_id,
                e.question,
                e.ai_answer,
                e.ai_score,
                e.ai_source,
                e.manual_answer,
                e.asked_by,
                e.handled_by,
                e.image_url,
                e.image_type,
                e.status,
                e.created_at,
                e.updated_at,
                e.resolved_at,
                e.is_deleted,
                e.deleted_at,
                e.deleted_by,
                u.full_name AS asked_by_name,
                deleted_user.full_name AS deleted_by_name,
                latest_review.review_id,
                latest_review.status AS review_status,
                latest_review.reviewer_comment,
                latest_review.reviewed_at,
                latest_review.published_at
            FROM escalation e
            LEFT JOIN users u ON e.asked_by = u.user_id
            LEFT JOIN users deleted_user ON e.deleted_by = deleted_user.user_id
            LEFT JOIN (
                SELECT rq.*
                FROM review_queue rq
                INNER JOIN (
                    SELECT escalation_id, MAX(review_id) AS max_review_id
                    FROM review_queue
                    GROUP BY escalation_id
                ) latest_rq ON rq.review_id = latest_rq.max_review_id
            ) latest_review ON e.escalation_id = latest_review.escalation_id
            WHERE COALESCE(e.is_deleted, 0) = %s
            ORDER BY e.created_at DESC
        """, (1 if show_deleted else 0,))

        escalations = cursor.fetchall()
        return jsonify(escalations), 200

    except Exception as error:
        print('MYSQL ERROR /api/escalations GET:', error)
        return jsonify({
            'message': 'Failed to load escalations.',
            'error': str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route('/api/escalations/<int:escalation_id>/answer', methods=['PUT'])
def submit_escalation_answer(escalation_id):
    conn = None
    cursor = None

    try:
        answer_image_url = None
        answer_image_type = None

        if request.content_type and request.content_type.startswith('multipart/form-data'):
            manual_answer = str(request.form.get('manual_answer', '')).strip()
            handled_by = request.form.get('handled_by') or request.form.get('user_id') or request.form.get('userId')

            image_file = request.files.get('image') or request.files.get('attachment')

            print("CONTENT TYPE:", request.content_type)
            print("FORM DATA:", request.form)
            print("FILES:", request.files)
            print("IMAGE FILE:", image_file)

            if image_file and image_file.filename:
                answer_image_url, answer_image_type = save_chat_image(image_file)

                if not answer_image_url:
                    return jsonify({
                        'message': 'Attachment upload failed. Please check file type or server upload folder.',
                        'filename': image_file.filename,
                        'content_type': image_file.content_type
                    }), 400

        else:
            data = request.get_json(silent=True) or {}
            manual_answer = str(data.get('manual_answer', '')).strip()
            handled_by = data.get('handled_by') or data.get('user_id') or data.get('userId')

        if not manual_answer:
            return jsonify({'message': 'Manual answer is required.'}), 400

        handled_by = _safe_int_value(handled_by)

        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT escalation_id, question, image_url, image_type
            FROM escalation
            WHERE escalation_id = %s
              AND COALESCE(is_deleted, 0) = 0
            LIMIT 1
        """, (escalation_id,))
        escalation = cursor.fetchone()

        if not escalation:
            conn.rollback()
            return jsonify({'message': 'Escalation not found.'}), 404

        final_image_url = answer_image_url or escalation.get('image_url')
        final_image_type = answer_image_type or escalation.get('image_type')
        question = escalation.get('question') or ''

        cursor.execute("""
            UPDATE escalation
            SET
                manual_answer = %s,
                handled_by = %s,
                status = 'resolved',
                resolved_at = NOW(),
                image_url = COALESCE(%s, image_url),
                image_type = COALESCE(%s, image_type)
            WHERE escalation_id = %s
        """, (
            manual_answer,
            handled_by,
            final_image_url,
            final_image_type,
            escalation_id
        ))

        cursor.execute("""
            SELECT review_id
            FROM review_queue
            WHERE escalation_id = %s
            ORDER BY review_id DESC
            LIMIT 1
        """, (escalation_id,))
        review = cursor.fetchone()

        if review:
            cursor.execute("""
                UPDATE review_queue
                SET
                    question = %s,
                    answer = %s,
                    submitted_by = %s,
                    reviewed_by = NULL,
                    reviewer_comment = '',
                    status = 'pending',
                    reviewed_at = NULL,
                    published_at = NULL
                WHERE review_id = %s
            """, (
                question,
                manual_answer,
                handled_by,
                review['review_id']
            ))
        else:
            cursor.execute("""
                INSERT INTO review_queue
                (escalation_id, question, answer, submitted_by, status, created_at)
                VALUES (%s, %s, %s, %s, 'pending', NOW())
            """, (
                escalation_id,
                question,
                manual_answer,
                handled_by
            ))

        cursor.execute("""
            DELETE FROM qa_knowledge
            WHERE question = %s
        """, (question,))

        cursor.execute("""
            DELETE FROM image_retrieval
            WHERE source_type = 'approved_escalation'
            AND source_id = %s
        """, (escalation_id,))

        conn.commit()

        add_audit_log(
            actor_id=handled_by,
            actor_name="Team Lead",
            action="Submitted escalation answer for admin review",
            module="Escalation",
            description=f"Escalation ID {escalation_id} was answered and sent for admin approval."
        )

        return jsonify({
            'message': 'Manual answer submitted for admin approval.',
            'image_url': final_image_url,
            'image_type': final_image_type
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("SUBMIT ESCALATION ANSWER ERROR:", error)
        return jsonify({
            'message': 'Failed to submit manual answer.',
            'error': str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route('/api/escalations/<int:escalation_id>/approve', methods=['PUT'])
def approve_escalation_answer(escalation_id):
    data = request.get_json(silent=True) or {}
    reviewed_by = _safe_int_value(data.get('reviewed_by') or data.get('user_id') or data.get('userId'))
    reviewer_comment = str(data.get('reviewer_comment', '')).strip()

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT escalation_id, question, manual_answer, asked_by, handled_by, image_url, image_type
            FROM escalation
            WHERE escalation_id = %s
              AND COALESCE(is_deleted, 0) = 0
            LIMIT 1
        """, (escalation_id,))
        escalation = cursor.fetchone()

        if not escalation:
            conn.rollback()
            return jsonify({'message': 'Escalation not found.'}), 404

        question = escalation.get('question') or ''
        manual_answer = str(escalation.get('manual_answer') or '').strip()

        if not manual_answer:
            conn.rollback()
            return jsonify({'message': 'No manual answer to approve.'}), 400

        if reviewed_by is None:
            reviewed_by = _safe_int_value(escalation.get('handled_by')) or _safe_int_value(escalation.get('asked_by'))

        cursor.execute("""
            SELECT review_id
            FROM review_queue
            WHERE escalation_id = %s
            ORDER BY review_id DESC
            LIMIT 1
        """, (escalation_id,))
        review = cursor.fetchone()

        if review:
            cursor.execute("""
                UPDATE review_queue
                SET
                    question = %s,
                    answer = %s,
                    reviewed_by = %s,
                    reviewer_comment = %s,
                    status = 'approved',
                    reviewed_at = NOW()
                WHERE review_id = %s
            """, (
                question,
                manual_answer,
                reviewed_by,
                reviewer_comment,
                review['review_id']
            ))
        else:
            cursor.execute("""
                INSERT INTO review_queue
                (escalation_id, question, answer, submitted_by, reviewed_by, status, reviewer_comment, created_at, reviewed_at)
                VALUES (%s, %s, %s, %s, %s, 'approved', %s, NOW(), NOW())
            """, (
                escalation_id,
                question,
                manual_answer,
                escalation.get('handled_by'),
                reviewed_by,
                reviewer_comment
            ))

        _save_approved_escalation_to_qa_knowledge(
            cursor,
            question,
            manual_answer,
            escalation.get('image_url'),
            escalation.get('image_type')
        )

        _save_approved_escalation_to_image_retrieval(
            cursor,
            escalation_id,
            question,
            manual_answer,
            escalation.get('image_url'),
            escalation.get('image_type')
        )

        cursor.execute("""
            UPDATE escalation
            SET
                status = 'resolved',
                resolved_at = COALESCE(resolved_at, NOW())
            WHERE escalation_id = %s
        """, (escalation_id,))

        conn.commit()

        add_audit_log(
            actor_id=reviewed_by,
            actor_name="Admin",
            action="Approved escalation answer",
            module="Escalation",
            description=f"Approved escalation answer ID {escalation_id} and saved it into AI knowledge."
        )

        return jsonify({'message': 'Escalation answer approved and saved into AI knowledge.'}), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print('MYSQL ERROR /api/escalations APPROVE:', error)
        return jsonify({
            'message': 'Failed to approve escalation answer.',
            'error': str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route('/api/escalations/<int:escalation_id>/reject', methods=['PUT'])
def reject_escalation_answer(escalation_id):
    data = request.get_json(silent=True) or {}
    reviewed_by = _safe_int_value(data.get('reviewed_by') or data.get('user_id') or data.get('userId'))
    reviewer_comment = str(data.get('reviewer_comment', '')).strip()

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT escalation_id, question, manual_answer, asked_by, handled_by
            FROM escalation
            WHERE escalation_id = %s
              AND COALESCE(is_deleted, 0) = 0
            LIMIT 1
        """, (escalation_id,))
        escalation = cursor.fetchone()

        if not escalation:
            conn.rollback()
            return jsonify({'message': 'Escalation not found.'}), 404

        question = escalation.get('question') or ''
        manual_answer = str(escalation.get('manual_answer') or '').strip()

        if reviewed_by is None:
            reviewed_by = _safe_int_value(escalation.get('handled_by')) or _safe_int_value(escalation.get('asked_by'))

        cursor.execute("""
            SELECT review_id
            FROM review_queue
            WHERE escalation_id = %s
            ORDER BY review_id DESC
            LIMIT 1
        """, (escalation_id,))
        review = cursor.fetchone()

        if review:
            cursor.execute("""
                UPDATE review_queue
                SET
                    question = %s,
                    answer = %s,
                    reviewed_by = %s,
                    reviewer_comment = %s,
                    status = 'rejected',
                    reviewed_at = NOW()
                WHERE review_id = %s
            """, (
                question,
                manual_answer,
                reviewed_by,
                reviewer_comment,
                review['review_id']
            ))
        else:
            cursor.execute("""
                INSERT INTO review_queue
                (escalation_id, question, answer, submitted_by, reviewed_by, status, reviewer_comment, created_at, reviewed_at)
                VALUES (%s, %s, %s, %s, %s, 'rejected', %s, NOW(), NOW())
            """, (
                escalation_id,
                question,
                manual_answer,
                escalation.get('handled_by'),
                reviewed_by,
                reviewer_comment
            ))

        cursor.execute("""
            DELETE FROM qa_knowledge
            WHERE question = %s
        """, (question,))

        cursor.execute("""
            DELETE FROM image_retrieval
            WHERE source_type = 'approved_escalation'
            AND source_id = %s
        """, (escalation_id,))

        cursor.execute("""
            UPDATE escalation
            SET
                status = 'pending',
                manual_answer = NULL,
                handled_by = NULL,
                resolved_at = NULL
            WHERE escalation_id = %s
        """, (escalation_id,))

        conn.commit()

        add_audit_log(
            actor_id=reviewed_by,
            actor_name="Admin",
            action="Rejected escalation answer",
            module="Escalation",
            description=f"Rejected escalation answer ID {escalation_id} and moved it back to pending."
        )

        return jsonify({'message': 'Escalation answer rejected and moved back to pending.'}), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print('MYSQL ERROR /api/escalations REJECT:', error)
        return jsonify({
            'message': 'Failed to reject escalation answer.',
            'error': str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# =========================
# BULK SOFT DELETE ESCALATION ROUTE
# Move selected escalations to Trash Bin
# =========================
@app.route('/api/escalations/bulk-delete', methods=['POST'])
def bulk_delete_escalations():
    conn = None
    cursor = None

    try:
        data = request.get_json(silent=True) or {}

        escalation_ids = data.get("escalation_ids") or data.get("ids") or []
        deleted_by = _safe_int_value(data.get("deleted_by"))

        clean_ids = []

        for item in escalation_ids:
            clean_id = _safe_int_value(item)

            if clean_id is not None and clean_id not in clean_ids:
                clean_ids.append(clean_id)

        if not clean_ids:
            return jsonify({
                "message": "No escalation selected for deletion."
            }), 400

        placeholders = ",".join(["%s"] * len(clean_ids))

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(f"""
            UPDATE escalation
            SET
                is_deleted = 1,
                deleted_at = NOW(),
                deleted_by = %s
            WHERE escalation_id IN ({placeholders})
            AND COALESCE(is_deleted, 0) = 0
        """, [deleted_by] + clean_ids)

        deleted_count = cursor.rowcount

        conn.commit()

        add_audit_log(
            actor_id=deleted_by,
            action="Bulk moved escalations to Trash Bin",
            module="Escalation",
            description=f"{deleted_count} escalation(s) were moved to Trash Bin."
        )

        return jsonify({
            "message": f"{deleted_count} escalation(s) moved to Trash Bin successfully.",
            "deleted_count": deleted_count
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/escalations/bulk-delete:", error)

        return jsonify({
            "message": "Failed to move selected escalations to Trash Bin.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# BULK PERMANENT DELETE ESCALATION ROUTE
# Delete selected Trash Bin escalations forever
# =========================
@app.route('/api/escalations/bulk-permanent-delete', methods=['POST'])
def bulk_permanent_delete_escalations():
    conn = None
    cursor = None

    try:
        data = request.get_json(silent=True) or {}

        escalation_ids = data.get("escalation_ids") or data.get("ids") or []

        clean_ids = []

        for item in escalation_ids:
            clean_id = _safe_int_value(item)

            if clean_id is not None and clean_id not in clean_ids:
                clean_ids.append(clean_id)

        if not clean_ids:
            return jsonify({
                "message": "No escalation selected for permanent deletion."
            }), 400

        placeholders = ",".join(["%s"] * len(clean_ids))

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(f"""
            SELECT escalation_id
            FROM escalation
            WHERE escalation_id IN ({placeholders})
            AND COALESCE(is_deleted, 0) = 1
        """, clean_ids)

        trash_rows = cursor.fetchall()
        trash_ids = [row["escalation_id"] for row in trash_rows]

        if not trash_ids:
            return jsonify({
                "message": "No selected escalation found in Trash Bin."
            }), 404

        trash_placeholders = ",".join(["%s"] * len(trash_ids))

        cursor.execute(f"""
            DELETE FROM review_queue
            WHERE escalation_id IN ({trash_placeholders})
        """, trash_ids)

        cursor.execute(f"""
            DELETE FROM escalation
            WHERE escalation_id IN ({trash_placeholders})
            AND COALESCE(is_deleted, 0) = 1
        """, trash_ids)

        deleted_count = cursor.rowcount

        conn.commit()

        add_audit_log(
            action="Bulk permanently deleted escalations",
            module="Escalation",
            description=f"{deleted_count} escalation(s) were permanently deleted from Trash Bin."
        )

        return jsonify({
            "message": f"{deleted_count} escalation(s) permanently deleted successfully.",
            "deleted_count": deleted_count
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/escalations/bulk-permanent-delete:", error)

        return jsonify({
            "message": "Failed to permanently delete selected escalations.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# =========================
# SOFT DELETE ESCALATION ROUTE
# Move escalation to Trash Bin
# =========================
@app.route('/api/escalations/<int:escalation_id>', methods=['DELETE'])
def delete_escalation(escalation_id):
    conn = None
    cursor = None

    try:
        data = request.get_json(silent=True) or {}
        deleted_by = data.get("deleted_by")

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            UPDATE escalation
            SET 
                is_deleted = 1,
                deleted_at = NOW(),
                deleted_by = %s
            WHERE escalation_id = %s
            AND COALESCE(is_deleted, 0) = 0
        """, (deleted_by, escalation_id))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({
                'message': 'Escalation not found or already moved to Trash Bin.'
            }), 404

        add_audit_log(
            actor_id=deleted_by,
            action="Moved escalation to Trash Bin",
            module="Escalation",
            description=f"Escalation ID {escalation_id} was moved to Trash Bin."
        )

        return jsonify({
            'message': 'Escalation moved to Trash Bin successfully.'
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print('MYSQL ERROR /api/escalations DELETE:', error)

        return jsonify({
            'message': 'Failed to move escalation to Trash Bin.',
            'error': str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# RESTORE ESCALATION ROUTE
# Restore escalation from Trash Bin
# =========================
@app.route('/api/escalations/<int:escalation_id>/restore', methods=['PUT'])
def restore_escalation(escalation_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            UPDATE escalation
            SET 
                is_deleted = 0,
                deleted_at = NULL,
                deleted_by = NULL
            WHERE escalation_id = %s
            AND COALESCE(is_deleted, 0) = 1
        """, (escalation_id,))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({
                'message': 'Escalation not found in Trash Bin.'
            }), 404

        add_audit_log(
            action="Restored escalation",
            module="Escalation",
            description=f"Escalation ID {escalation_id} was restored from Trash Bin."
        )

        return jsonify({
            'message': 'Escalation restored successfully.'
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print('MYSQL ERROR /api/escalations RESTORE:', error)

        return jsonify({
            'message': 'Failed to restore escalation.',
            'error': str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# PERMANENT DELETE ESCALATION ROUTE
# Delete escalation permanently from Trash Bin only
# =========================
@app.route('/api/escalations/<int:escalation_id>/permanent-delete', methods=['DELETE'])
def permanent_delete_escalation(escalation_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT escalation_id
            FROM escalation
            WHERE escalation_id = %s
            AND COALESCE(is_deleted, 0) = 1
            LIMIT 1
        """, (escalation_id,))

        escalation = cursor.fetchone()

        if not escalation:
            return jsonify({
                'message': 'Escalation not found in Trash Bin.'
            }), 404

        cursor.execute("""
            DELETE FROM escalation
            WHERE escalation_id = %s
            AND COALESCE(is_deleted, 0) = 1
        """, (escalation_id,))

        conn.commit()

        add_audit_log(
            action="Permanently deleted escalation",
            module="Escalation",
            description=f"Escalation ID {escalation_id} was permanently deleted from Trash Bin."
        )

        return jsonify({
            'message': 'Escalation permanently deleted successfully.'
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print('MYSQL ERROR /api/escalations PERMANENT DELETE:', error)

        return jsonify({
            'message': 'Failed to permanently delete escalation.',
            'error': str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# =========================
# REVIEW MANAGEMENT ROUTES
# =========================

@app.route("/api/reviews", methods=["GET"])
def get_reviews():
    conn = None
    cursor = None

    try:
        status = request.args.get("status", "").strip().lower()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        base_query = """
            SELECT
                rq.review_id,
                rq.escalation_id,
                rq.question,
                rq.answer,
                rq.submitted_by,
                rq.reviewed_by,
                rq.status,
                rq.reviewer_comment,
                rq.created_at,
                rq.reviewed_at,
                rq.published_at,
                submitter.full_name AS submitted_by_name,
                reviewer.full_name AS reviewed_by_name
            FROM review_queue rq
            LEFT JOIN users submitter ON rq.submitted_by = submitter.user_id
            LEFT JOIN users reviewer ON rq.reviewed_by = reviewer.user_id
        """

        params = []

        if status in ["pending", "approved", "rejected", "published"]:
            base_query += " WHERE rq.status = %s"
            params.append(status)

        base_query += " ORDER BY rq.created_at DESC"

        cursor.execute(base_query, tuple(params))
        reviews = cursor.fetchall()

        for review in reviews:
            review["created_at"] = format_datetime_value(review.get("created_at"))
            review["reviewed_at"] = format_datetime_value(review.get("reviewed_at"))
            review["published_at"] = format_datetime_value(review.get("published_at"))

        return jsonify(reviews), 200

    except Exception as error:
        print("MYSQL ERROR /api/reviews GET:", error)
        return jsonify({
            "message": "Failed to load review queue.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/reviews/<int:review_id>/approve", methods=["PUT"])
def approve_review(review_id):
    data = request.get_json() or {}

    reviewed_by = data.get("reviewed_by")
    reviewer_comment = data.get("reviewer_comment", "").strip()

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            UPDATE review_queue
            SET
                status = 'approved',
                reviewed_by = %s,
                reviewer_comment = %s,
                reviewed_at = NOW()
            WHERE review_id = %s
              AND status = 'pending'
        """, (reviewed_by, reviewer_comment, review_id))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({
                "message": "Review item not found or already processed."
            }), 404

        add_audit_log(
            actor_id=reviewed_by,
            actor_name="Manager",
            action="Approved review answer",
            module="Review Management",
            description=f"Approved review item ID {review_id}."
        )

        return jsonify({"message": "Answer approved successfully."}), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/reviews APPROVE:", error)

        return jsonify({
            "message": "Failed to approve answer.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/reviews/<int:review_id>/reject", methods=["PUT"])
def reject_review(review_id):
    data = request.get_json() or {}

    reviewed_by = data.get("reviewed_by")
    reviewer_comment = data.get("reviewer_comment", "").strip()

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            UPDATE review_queue
            SET
                status = 'rejected',
                reviewed_by = %s,
                reviewer_comment = %s,
                reviewed_at = NOW()
            WHERE review_id = %s
              AND status = 'pending'
        """, (reviewed_by, reviewer_comment, review_id))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({
                "message": "Review item not found or already processed."
            }), 404

        add_audit_log(
            actor_id=reviewed_by,
            actor_name="Manager",
            action="Rejected review answer",
            module="Review Management",
            description=f"Rejected review item ID {review_id}."
        )

        return jsonify({"message": "Answer rejected successfully."}), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/reviews REJECT:", error)

        return jsonify({
            "message": "Failed to reject answer.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/reviews/<int:review_id>/publish", methods=["PUT"])
def publish_review(review_id):
    data = request.get_json() or {}
    reviewed_by = data.get("reviewed_by")

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT review_id, question, answer, status
            FROM review_queue
            WHERE review_id = %s
            LIMIT 1
        """, (review_id,))

        review = cursor.fetchone()

        if not review:
            conn.rollback()
            return jsonify({"message": "Review item not found."}), 404

        if review["status"] != "approved":
            conn.rollback()
            return jsonify({
                "message": "Only approved answers can be published."
            }), 400

        cursor.execute("""
            INSERT INTO wiki_article
            (title, content, category, sub_category, link)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            review["question"][:255],
            review["answer"],
            "FAQ",
            "Manager Approved Answer",
            ""
        ))

        cursor.execute("""
            UPDATE review_queue
            SET
                status = 'published',
                published_at = NOW()
            WHERE review_id = %s
        """, (review_id,))

        conn.commit()

        save_qa_to_db(
            review["question"],
            {
                "answer": review["answer"],
                "confidence": 1.0,
                "source": "manager_approved_review"
            }
        )

        add_audit_log(
            actor_id=reviewed_by,
            actor_name="Manager",
            action="Published approved answer",
            module="Review Management",
            description=f"Published review item ID {review_id} to knowledge base."
        )

        return jsonify({"message": "Approved answer published successfully."}), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/reviews PUBLISH:", error)

        return jsonify({
            "message": "Failed to publish approved answer.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()






# =========================
# QUIZ ROUTES
# =========================

import random

def get_knowledge_for_quiz(topic):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT question, answer
        FROM qa_knowledge
        WHERE question LIKE %s
        ORDER BY created_at DESC
        LIMIT 20
    """, ("%" + topic + "%",))

    data = cursor.fetchall()

    cursor.close()
    conn.close()

    return data

def create_quiz_and_questions(topic, knowledge, count=5):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1. Create quiz
    cursor.execute("""
        INSERT INTO quiz (title, created_at)
        VALUES (%s, NOW())
    """, (topic,))
    quiz_id = cursor.lastrowid

    # 2. Generate MCQ
    questions = []

    for k in knowledge:
        base_text = k.get("question", "") + " " + k.get("answer", "")

        # 🔥 CALL YOUR PYTORCH MODEL
        result = call_model_answer(
            f"""
    Create a SHORT and CLEAR quiz question for staff training.

    Rules:
    - Max 10 words
    - Must be meaningful
    - No nonsense
    - Based on real SOP or product

    Content:
    {base_text}

    Return only the question.
    """
        )

        if not result:
            continue

        a = str(result.get("answer", "")).strip()
        q = str(result.get("question", "")).strip().lower()

        # ❌ filter bad AI output
        if (
            len(q) < 8 or len(q) > 120
            or len(a) < 5 or len(a) > 100
            or is_nonsense(q)
            or any(x in q for x in ["lol", "haha", "test", "asdf"])
            or len(q.split()) < 3   # avoid "grease", "lol", etc
        ):
            continue

        questions.append({
            "question": q,
            "options": [
                a,
                "None of the above",
                "Not related",
                "All of the above"
            ],
            "correct_answer": "A"
        })

        if len(questions) >= count:
            break

    # 3. Save questions
    for q in questions:

        options = q.get("options", [])

        # ✅ Ensure max 4 options
        options = options[:4]

        # ✅ Limit length (IMPORTANT FIX)
        options = [str(opt)[:250] for opt in options]

        # ✅ Fill missing options
        while len(options) < 4:
            options.append("")

        # ✅ Convert correct answer
        correct = q.get("correct_answer", "")

        if correct in options:
            correct = ["A", "B", "C", "D"][options.index(correct)]
        else:
            correct = "A"

        cursor.execute("""
            INSERT INTO quiz_question
            (quiz_id, question_text, option_a, option_b, option_c, option_d, correct_option)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            quiz_id,
            q.get("question", "")[:500],   # also safe limit question
            options[0],
            options[1],
            options[2],
            options[3],
            correct
        ))

    conn.commit()
    cursor.close()
    conn.close()

    return quiz_id


import random

def generate_mcq_from_knowledge(knowledge, count=5):
    import random

    questions = []
    used_questions = set()

    for k in knowledge:
        print("RAW:", k)
        q_text = k.get("question", "").strip()
        a_text = k.get("answer", "").strip()

        # ❌ skip bad / long / repeated
        if len(q_text) < 5 or len(q_text) > 100:
            continue

        if q_text in used_questions:
            continue

        if len(a_text) < 3 or len(a_text) > 120:
            continue

        used_questions.add(q_text)

        # ✅ clean short question
        question = q_text.capitalize()

        # ✅ correct answer
        correct = a_text.strip()

        # ❌ generate simple distractors
        wrong_options = []
        for other in knowledge:
            wrong = other.get("answer", "")
            if wrong != correct and len(wrong) < 120:
                wrong_options.append(wrong)

        random.shuffle(wrong_options)

        options = [correct] + wrong_options[:3]
        random.shuffle(options)

        questions.append({
            "question": question,
            "options": options,
            "correct_answer": ["A", "B", "C", "D"][options.index(correct)]
        })

        if len(questions) >= count:
            break

    return questions


def save_quiz_to_db(title, questions):
    conn = get_db_connection()
    cursor = conn.cursor()

    # create quiz
    cursor.execute("""
        INSERT INTO quiz (title, status)
        VALUES (%s, 'active')
    """, (title,))

    quiz_id = cursor.lastrowid

    for q in questions:
        import json

        cursor.execute("""
            INSERT INTO quiz_question (quiz_id, question, options, correct_answer)
            VALUES (%s, %s, %s, %s)
        """, (
            quiz_id,
            q["question"],
            json.dumps(q["options"]),
            q["correct"]
        ))

    conn.commit()
    conn.close()

    return quiz_id

@app.route("/api/generate-quiz", methods=["POST"])
def generate_quiz():
    # Automatic quiz generation is intentionally disabled.
    # Quiz / Training remains available through manual admin quiz management routes.
    return jsonify({
        "message": "Automatic quiz generation is disabled. Please create quizzes manually from Quiz Management."
    }), 400

@app.route("/api/quizzes", methods=["GET"])
def get_quizzes():
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                q.quiz_id,
                q.title,
                q.description,
                q.category,
                q.status,
                q.created_at,
                COUNT(qq.question_id) AS question_count
            FROM quiz q
            LEFT JOIN quiz_question qq ON q.quiz_id = qq.quiz_id
            WHERE q.status = 'active'
            GROUP BY q.quiz_id, q.title, q.description, q.category, q.status, q.created_at
            ORDER BY q.created_at DESC
        """)

        quizzes = cursor.fetchall()

        return jsonify(quizzes), 200

    except Exception as e:
        print("GET QUIZZES ERROR:", e)
        return jsonify({"message": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/quizzes/<int:quiz_id>/questions", methods=["GET"])
def get_quiz_questions(quiz_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                question_id,
                quiz_id,
                question_text,
                option_a,
                option_b,
                option_c,
                option_d,
                correct_option,
                explanation,
                points
            FROM quiz_question
            WHERE quiz_id = %s
            ORDER BY question_id ASC
        """, (quiz_id,))

        questions = cursor.fetchall()

        formatted_questions = []

        for q in questions:
            correct_answer = None

            if q["correct_option"] == "A":
                correct_answer = q["option_a"]
            elif q["correct_option"] == "B":
                correct_answer = q["option_b"]
            elif q["correct_option"] == "C":
                correct_answer = q["option_c"]
            elif q["correct_option"] == "D":
                correct_answer = q["option_d"]

            formatted_questions.append({
                "id": q["question_id"],
                "question": q["question_text"],
                "options": [
                    q["option_a"],
                    q["option_b"],
                    q["option_c"],
                    q["option_d"]
                ],
                "correctAnswer": correct_answer,
                "correctOption": q["correct_option"],
                "explanation": q["explanation"],
                "points": q["points"]
            })

        return jsonify(formatted_questions), 200

    except Exception as e:
        print("GET QUIZ QUESTIONS ERROR:", e)
        return jsonify({"message": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# ADMIN QUIZ MANAGEMENT ROUTES
# =========================

@app.route("/api/admin/quizzes", methods=["GET"])
def get_admin_quizzes():
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                q.quiz_id,
                q.title,
                q.description,
                q.category,
                q.status,
                q.created_by,
                q.created_at,
                q.updated_at,
                COUNT(qq.question_id) AS question_count
            FROM quiz q
            LEFT JOIN quiz_question qq ON q.quiz_id = qq.quiz_id
            GROUP BY 
                q.quiz_id,
                q.title,
                q.description,
                q.category,
                q.status,
                q.created_by,
                q.created_at,
                q.updated_at
            ORDER BY q.created_at DESC
        """)

        quizzes = cursor.fetchall()

        return jsonify(quizzes), 200

    except Exception as error:
        print("MYSQL ERROR /api/admin/quizzes GET:", error)
        return jsonify({
            "message": "Failed to load admin quizzes.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/admin/quizzes", methods=["POST"])
def create_admin_quiz():
    data = request.get_json() or {}

    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    category = data.get("category", "").strip()
    created_by = data.get("created_by")
    status = data.get("status", "active").strip().lower()

    if not title:
        return jsonify({"message": "Quiz title is required."}), 400

    if status not in ["active", "inactive"]:
        status = "active"

    if created_by in ["", "undefined"]:
        created_by = None

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            INSERT INTO quiz 
            (title, description, category, created_by, status)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            title,
            description,
            category,
            created_by,
            status
        ))

        conn.commit()

        quiz_id = cursor.lastrowid
        add_audit_log(
            actor_id=created_by,
            action="Created quiz",
            module="Quiz Management",
            description=f"Quiz created: {title}"
        )

        return jsonify({
            "message": "Quiz created successfully.",
            "quiz_id": quiz_id
        }), 201

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/admin/quizzes POST:", error)

        return jsonify({
            "message": "Failed to create quiz.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/admin/quizzes/<int:quiz_id>", methods=["PUT"])
def update_admin_quiz(quiz_id):
    data = request.get_json() or {}

    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    category = data.get("category", "").strip()
    status = data.get("status", "active").strip().lower()

    if not title:
        return jsonify({"message": "Quiz title is required."}), 400

    if status not in ["active", "inactive"]:
        status = "active"

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            UPDATE quiz
            SET 
                title = %s,
                description = %s,
                category = %s,
                status = %s
            WHERE quiz_id = %s
        """, (
            title,
            description,
            category,
            status,
            quiz_id
        ))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"message": "Quiz not found."}), 404

        add_audit_log(
            action="Updated quiz",
            module="Quiz Management",
            description=f"Quiz ID {quiz_id} updated: {title}"
        )

        return jsonify({"message": "Quiz updated successfully."}), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/admin/quizzes PUT:", error)

        return jsonify({
            "message": "Failed to update quiz.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/admin/quizzes/<int:quiz_id>", methods=["DELETE"])
def delete_admin_quiz(quiz_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            DELETE FROM quiz
            WHERE quiz_id = %s
        """, (quiz_id,))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"message": "Quiz not found."}), 404

        return jsonify({"message": "Quiz deleted successfully."}), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/admin/quizzes DELETE:", error)

        return jsonify({
            "message": "Failed to delete quiz.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/admin/quizzes/<int:quiz_id>/questions", methods=["GET"])
def get_admin_quiz_questions(quiz_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                question_id,
                quiz_id,
                question_text,
                option_a,
                option_b,
                option_c,
                option_d,
                correct_option,
                explanation,
                points,
                created_at
            FROM quiz_question
            WHERE quiz_id = %s
            ORDER BY question_id ASC
        """, (quiz_id,))

        questions = cursor.fetchall()

        return jsonify(questions), 200

    except Exception as error:
        print("MYSQL ERROR /api/admin/quizzes/<quiz_id>/questions GET:", error)

        return jsonify({
            "message": "Failed to load quiz questions.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/admin/quizzes/<int:quiz_id>/questions", methods=["POST"])
def create_quiz_question(quiz_id):
    data = request.get_json() or {}

    question_text = data.get("question_text", "").strip()
    option_a = data.get("option_a", "").strip()
    option_b = data.get("option_b", "").strip()
    option_c = data.get("option_c", "").strip()
    option_d = data.get("option_d", "").strip()
    correct_option = data.get("correct_option", "").strip().upper()
    explanation = data.get("explanation", "").strip()
    points = data.get("points", 1)

    if not question_text:
        return jsonify({"message": "Question text is required."}), 400

    if not option_a or not option_b or not option_c or not option_d:
        return jsonify({"message": "All four options are required."}), 400

    if correct_option not in ["A", "B", "C", "D"]:
        return jsonify({"message": "Correct option must be A, B, C, or D."}), 400

    try:
        points = int(points)
    except Exception:
        points = 1

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT quiz_id
            FROM quiz
            WHERE quiz_id = %s
            LIMIT 1
        """, (quiz_id,))

        quiz = cursor.fetchone()

        if not quiz:
            return jsonify({"message": "Quiz not found."}), 404

        cursor.execute("""
            INSERT INTO quiz_question
            (
                quiz_id,
                question_text,
                option_a,
                option_b,
                option_c,
                option_d,
                correct_option,
                explanation,
                points
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            quiz_id,
            question_text,
            option_a,
            option_b,
            option_c,
            option_d,
            correct_option,
            explanation,
            points
        ))

        conn.commit()

        return jsonify({
            "message": "Question added successfully.",
            "question_id": cursor.lastrowid
        }), 201

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/admin/quizzes/<quiz_id>/questions POST:", error)

        return jsonify({
            "message": "Failed to add question.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/admin/questions/<int:question_id>", methods=["PUT"])
def update_admin_quiz_question(question_id):
    data = request.get_json() or {}

    question_text = data.get("question_text", "").strip()
    option_a = data.get("option_a", "").strip()
    option_b = data.get("option_b", "").strip()
    option_c = data.get("option_c", "").strip()
    option_d = data.get("option_d", "").strip()
    correct_option = data.get("correct_option", "").strip().upper()
    explanation = data.get("explanation", "").strip()
    points = data.get("points", 1)

    if not question_text:
        return jsonify({"message": "Question text is required."}), 400

    if not option_a or not option_b or not option_c or not option_d:
        return jsonify({"message": "All four options are required."}), 400

    if correct_option not in ["A", "B", "C", "D"]:
        return jsonify({"message": "Correct option must be A, B, C, or D."}), 400

    try:
        points = int(points)
    except Exception:
        points = 1

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            UPDATE quiz_question
            SET 
                question_text = %s,
                option_a = %s,
                option_b = %s,
                option_c = %s,
                option_d = %s,
                correct_option = %s,
                explanation = %s,
                points = %s
            WHERE question_id = %s
        """, (
            question_text,
            option_a,
            option_b,
            option_c,
            option_d,
            correct_option,
            explanation,
            points,
            question_id
        ))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"message": "Question not found."}), 404

        return jsonify({"message": "Question updated successfully."}), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/admin/questions PUT:", error)

        return jsonify({
            "message": "Failed to update question.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/admin/questions/<int:question_id>", methods=["DELETE"])
def delete_admin_quiz_question(question_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            DELETE FROM quiz_question
            WHERE question_id = %s
        """, (question_id,))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"message": "Question not found."}), 404

        return jsonify({"message": "Question deleted successfully."}), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/admin/questions DELETE:", error)

        return jsonify({
            "message": "Failed to delete question.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# AI GENERATED QUIZ (template-based, no external AI provider)
#
# This project has no live generative-AI/LLM integration (AI Chat only
# matches/retrieves existing stored answers). Rather than fake it, this
# builds multiple-choice questions directly out of the numbered SOP steps
# already stored in wiki_article.content, picking distractor options from
# other steps depending on the requested difficulty. It only ever returns
# a preview -- saving reuses the existing manual quiz create routes below.
# =========================
def build_ai_quiz_questions(category_filter, question_count, difficulty):
    import random as random_module

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT article_id, title, content, category
            FROM wiki_article
            WHERE COALESCE(is_deleted, 0) = 0
        """
        params = ()

        if category_filter and str(category_filter).strip().lower() != "all":
            query += " AND category = %s"
            params = (category_filter,)

        cursor.execute(query, params)
        articles = cursor.fetchall() or []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    def clean_step_text(text):
        text = re.sub(r"\s+", " ", str(text or "")).strip()

        if len(text) > 180:
            text = text[:177].rstrip() + "..."

        return text

    article_step_groups = []

    for article in articles:
        steps = parse_article_steps(article.get("content"))
        clean_steps = []

        for step in steps:
            text = clean_step_text(step.get("answer") or step.get("content"))

            if text:
                clean_steps.append({
                    "title": article.get("title"),
                    "step": step.get("step"),
                    "text": text,
                })

        # Need at least 2 steps in an article so it can supply its own
        # "same article" distractor option.
        if len(clean_steps) >= 2:
            article_step_groups.append(clean_steps)

    all_steps_flat = [step for group in article_step_groups for step in group]
    distinct_texts = {step["text"] for step in all_steps_flat}

    if not article_step_groups or len(distinct_texts) < 4:
        return []

    shuffled_groups = list(article_step_groups)
    random_module.shuffle(shuffled_groups)

    generated = []
    used_correct_texts = set()

    for group in shuffled_groups:
        if len(generated) >= question_count:
            break

        candidates = [step for step in group if step["text"] not in used_correct_texts]

        if not candidates:
            continue

        correct_step = random_module.choice(candidates)
        used_correct_texts.add(correct_step["text"])

        same_article_pool = [
            step["text"] for step in group
            if step["text"] != correct_step["text"]
        ]
        other_article_pool = [
            step["text"] for step in all_steps_flat
            if step["title"] != correct_step["title"] and step["text"] != correct_step["text"]
        ]

        random_module.shuffle(same_article_pool)
        random_module.shuffle(other_article_pool)

        if difficulty == "basic":
            # Easier: distractors mostly from the SAME article (more
            # obviously related, easier to eliminate by context).
            distractor_source = same_article_pool + other_article_pool
        elif difficulty == "advanced":
            # Harder: distractors mostly from OTHER articles (less
            # contextual overlap, harder to tell apart at a glance).
            distractor_source = other_article_pool + same_article_pool
        else:
            # intermediate: one distractor from the same article, rest mixed.
            distractor_source = same_article_pool[:1] + other_article_pool + same_article_pool[1:]

        distractors = []
        seen_texts = {correct_step["text"]}

        for text in distractor_source:
            if text in seen_texts:
                continue

            seen_texts.add(text)
            distractors.append(text)

            if len(distractors) == 3:
                break

        if len(distractors) < 3:
            continue

        options = [correct_step["text"]] + distractors
        random_module.shuffle(options)
        correct_index = options.index(correct_step["text"])

        generated.append({
            "question": f'In the "{correct_step["title"]}" SOP, what is Step {correct_step["step"]}?',
            "options": options,
            "correctAnswerIndex": correct_index,
            "explanation": f'This is Step {correct_step["step"]} from the "{correct_step["title"]}" SOP.',
            "sourceTitle": correct_step["title"],
        })

    return generated


def build_ai_quiz_source_text(category_filter, max_chars=6000):
    """
    Collect the latest verified article content into one text blob to feed
    a real AI provider as context. Capped by character count so it stays a
    reasonable prompt size regardless of how large the Knowledge Base gets.
    """
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT title, content
            FROM wiki_article
            WHERE COALESCE(is_deleted, 0) = 0
        """
        params = ()

        if category_filter and str(category_filter).strip().lower() != "all":
            query += " AND category = %s"
            params = (category_filter,)

        query += " ORDER BY created_at DESC"

        cursor.execute(query, params)
        articles = cursor.fetchall() or []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    def clean_text(text):
        text = re.sub(r"<[^>]+>", " ", str(text or ""))
        text = re.sub(r"\s+", " ", text).strip()
        return text

    chunks = []
    total_len = 0

    for article in articles:
        title = article.get("title") or ""
        body = clean_text(article.get("content"))
        entry = f"### {title}\n{body}\n"

        if total_len + len(entry) > max_chars:
            remaining = max_chars - total_len

            if remaining > 200:
                chunks.append(entry[:remaining])

            break

        chunks.append(entry)
        total_len += len(entry)

    return "\n".join(chunks)


def build_ai_quiz_questions_via_provider(category_filter, question_count, difficulty):
    """
    Same output shape as build_ai_quiz_questions(), but genuinely written by
    whichever AI provider the manager configured in AI Model Settings.
    Returns None (not an empty list) if there's no usable source content, so
    the caller can tell "nothing to work with" apart from "AI returned zero
    valid questions".
    """
    source_text = build_ai_quiz_source_text(category_filter)

    if not source_text.strip():
        return None

    prompt = f"""You are generating training quiz questions for Jungle House staff.

Use only the provided source content. Do not invent information outside the source.
Generate practical staff training questions at {difficulty} difficulty.

Return ONLY valid JSON. No markdown. No explanation outside JSON.
Return a JSON array of up to {question_count} question objects (fewer only if
the source content truly does not support more distinct questions). Each
object must have exactly these fields:
- "question": string
- "options": array of exactly 4 strings
- "correctAnswerIndex": integer, 0, 1, 2 or 3
- "explanation": string
- "sourceTitle": string (the article title this question is based on)

Source content:
{source_text}
"""

    raw_reply = ai_provider_service.generate_ai_reply(prompt)

    json_text = raw_reply.strip()
    json_text = re.sub(r"^```(?:json)?\s*", "", json_text)
    json_text = re.sub(r"\s*```$", "", json_text)

    parsed = json.loads(json_text)

    if isinstance(parsed, dict) and isinstance(parsed.get("questions"), list):
        parsed = parsed["questions"]

    if not isinstance(parsed, list):
        raise ValueError("AI did not return a JSON array of questions.")

    questions = []

    for item in parsed:
        if not isinstance(item, dict):
            continue

        options = item.get("options")

        if not isinstance(options, list) or len(options) != 4:
            continue

        if not all(str(option).strip() for option in options):
            continue

        correct_index = item.get("correctAnswerIndex")

        if correct_index not in (0, 1, 2, 3):
            continue

        question_text = str(item.get("question") or "").strip()
        explanation = str(item.get("explanation") or "").strip()

        if not question_text or not explanation:
            continue

        questions.append({
            "question": question_text,
            "options": [str(option).strip() for option in options],
            "correctAnswerIndex": correct_index,
            "explanation": explanation,
            "sourceTitle": str(item.get("sourceTitle") or "").strip(),
        })

    return questions[:question_count]


@app.route("/api/admin/quizzes/ai-generate", methods=["POST"])
def ai_generate_quiz():
    data = request.get_json() or {}

    title = data.get("title", "").strip() or "AI Generated Quiz"
    source_category = str(data.get("sourceCategory") or data.get("category") or "All").strip()
    status = str(data.get("status", "active")).strip().lower()
    difficulty = str(data.get("difficulty", "intermediate")).strip().lower()

    if status not in ("active", "inactive"):
        status = "active"

    if difficulty not in ("basic", "intermediate", "advanced"):
        difficulty = "intermediate"

    try:
        question_count = int(data.get("questionCount", 5))
    except Exception:
        question_count = 5

    question_count = max(1, min(question_count, 20))

    generation_method = "template"
    questions = []

    # Prefer a real AI provider if the manager has configured one in AI
    # Model Settings. Any failure here (not configured, bad key, provider
    # outage, malformed AI output) falls back to the template generator
    # instead of failing the whole request -- quiz generation must keep
    # working either way.
    if AI_PROVIDER_SERVICE_AVAILABLE:
        try:
            provider_questions = build_ai_quiz_questions_via_provider(
                source_category, question_count, difficulty
            )

            if provider_questions:
                questions = provider_questions
                generation_method = "ai_provider"
        except ai_provider_service.AIProviderNotConfiguredError:
            pass
        except Exception as error:
            print("AI PROVIDER QUIZ GENERATION FAILED, FALLING BACK TO TEMPLATE:", error)

    if not questions:
        try:
            questions = build_ai_quiz_questions(source_category, question_count, difficulty)
            generation_method = "template"
        except Exception as error:
            print("AI GENERATE QUIZ ERROR:", error)
            return jsonify({
                "message": "AI quiz generation failed. Please try again later or create quiz manually."
            }), 500

    # Validate generated output before it ever reaches the frontend.
    questions = [
        q for q in questions
        if q.get("question")
        and isinstance(q.get("options"), list)
        and len(q["options"]) == 4
        and all(str(option).strip() for option in q["options"])
        and q.get("correctAnswerIndex") in (0, 1, 2, 3)
        and str(q.get("explanation") or "").strip()
    ]

    if not questions:
        return jsonify({
            "message": "Not enough verified content to generate quiz. Please add or verify more articles first."
        }), 400

    category_label = source_category if source_category.lower() != "all" else "Training"

    description = (
        f"AI generated quiz based on the latest verified {category_label} content."
        if generation_method == "ai_provider"
        else f"Quiz generated from the latest verified {category_label} content."
    )

    return jsonify({
        "success": True,
        "quiz": {
            "title": title,
            "description": description,
            "category": category_label,
            "status": status,
            "questions": questions,
            "generationMethod": generation_method,
        }
    }), 200


# =========================
# USER MANAGEMENT ROUTES
# =========================

@app.route("/api/admin/users", methods=["GET"])
def get_admin_users():
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        ensure_email_verification_table(cursor)

        cursor.execute("""
            SELECT
                u.user_id,
                u.full_name,
                u.email,
                u.status,
                u.created_at,
                r.role_name,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM email_verifications ev
                        WHERE ev.user_id = u.user_id
                          AND ev.verified_at IS NOT NULL
                    ) THEN TRUE
                    ELSE FALSE
                END AS email_verified,
                (
                    SELECT MAX(ev2.verified_at)
                    FROM email_verifications ev2
                    WHERE ev2.user_id = u.user_id
                      AND ev2.verified_at IS NOT NULL
                ) AS email_verified_at
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            ORDER BY u.user_id ASC
        """)

        users = cursor.fetchall()

        for user in users:
            user["created_at"] = format_datetime_value(user.get("created_at"))
            user["email_verified_at"] = format_datetime_value(user.get("email_verified_at"))
            user["email_verified"] = bool(user.get("email_verified"))

        return jsonify(users), 200

    except Exception as error:
        print("MYSQL ERROR /api/admin/users GET:", error)
        return jsonify({
            "message": "Failed to load users.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/admin/users/<int:user_id>/role", methods=["PUT"])
def update_admin_user_role(user_id):
    data = request.get_json() or {}

    role = str(data.get("role", "")).strip().lower()
    actor_id = _safe_int_value(
        data.get("actor_id")
        or data.get("user_id")
        or data.get("userId")
    )

    if role not in ["staff", "teamlead"]:
        return jsonify({"message": "Invalid role."}), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        if actor_id and not is_registration_approver(cursor, actor_id):
            conn.rollback()
            return jsonify({
                "message": "Only manager or team lead can update user roles."
            }), 403

        cursor.execute("""
            SELECT
                u.user_id,
                r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.user_id = %s
            LIMIT 1
        """, (user_id,))

        target_user = cursor.fetchone()

        if not target_user:
            conn.rollback()
            return jsonify({"message": "User not found."}), 404

        target_role = str(target_user.get("role_name", "")).strip().lower()

        if target_role in ["manager", "admin"]:
            conn.rollback()
            return jsonify({"message": "Manager account is protected."}), 403

        cursor.execute("""
            SELECT role_id
            FROM roles
            WHERE LOWER(role_name) = %s
            LIMIT 1
        """, (role,))

        role_row = cursor.fetchone()

        if not role_row:
            conn.rollback()
            return jsonify({"message": "Role not found."}), 404

        cursor.execute("""
            UPDATE users
            SET role_id = %s
            WHERE user_id = %s
        """, (role_row["role_id"], user_id))

        conn.commit()

        add_audit_log(
            actor_id=actor_id,
            actor_name="Manager/Team Lead",
            action="Updated user role",
            module="User Management",
            description=f"User ID {user_id} role changed to {role}."
        )

        return jsonify({
            "message": "User role updated successfully."
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/admin/users/role PUT:", error)

        return jsonify({
            "message": "Failed to update user role.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/admin/users/<int:user_id>/status", methods=["PUT"])
def update_admin_user_status(user_id):
    data = request.get_json() or {}

    status = str(data.get("status", "")).strip().lower()
    actor_id = _safe_int_value(
        data.get("actor_id")
        or data.get("user_id")
        or data.get("userId")
    )

    if status not in ["active", "inactive"]:
        return jsonify({"message": "Invalid status."}), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        if actor_id and not is_registration_approver(cursor, actor_id):
            conn.rollback()
            return jsonify({
                "message": "Only manager or team lead can update user status."
            }), 403

        cursor.execute("""
            SELECT
                u.user_id,
                u.status,
                r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.user_id = %s
            LIMIT 1
        """, (user_id,))

        target_user = cursor.fetchone()

        if not target_user:
            conn.rollback()
            return jsonify({"message": "User not found."}), 404

        target_role = str(target_user.get("role_name", "")).strip().lower()
        target_status = str(target_user.get("status", "")).strip().lower()

        if target_role in ["manager", "admin"]:
            conn.rollback()
            return jsonify({"message": "Manager account is protected."}), 403

        if target_status == "pending":
            conn.rollback()
            return jsonify({
                "message": "Pending users must be approved or declined first."
            }), 400

        cursor.execute("""
            UPDATE users
            SET status = %s
            WHERE user_id = %s
        """, (status, user_id))

        conn.commit()

        add_audit_log(
            actor_id=actor_id,
            actor_name="Manager/Team Lead",
            action="Updated user status",
            module="User Management",
            description=f"User ID {user_id} status changed to {status}."
        )

        return jsonify({
            "message": f"User status updated to {status}."
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/admin/users/status PUT:", error)

        return jsonify({
            "message": "Failed to update user status.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# REGISTRATION APPROVAL ROUTES
# Manager / Team Lead can approve or decline new accounts
# =========================

@app.route("/api/admin/registration-requests", methods=["GET"])
def get_registration_requests():
    conn = None
    cursor = None

    try:
        status = request.args.get("status", "pending").strip().lower()
        actor_id = _safe_int_value(
            request.args.get("actor_id")
            or request.args.get("user_id")
            or request.args.get("userId")
        )

        if status not in ["pending", "active", "declined", "inactive", "all"]:
            status = "pending"

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_email_verification_table(cursor)

        if not actor_id:
            return jsonify({
                "message": "Approver user ID is required."
            }), 400

        if not is_registration_approver(cursor, actor_id):
            return jsonify({
                "message": "Only manager or team lead can view registration requests."
            }), 403

        query = """
            SELECT
                u.user_id,
                u.full_name,
                u.email,
                u.status,
                u.created_at,
                r.role_name,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM email_verifications ev
                        WHERE ev.user_id = u.user_id
                          AND ev.verified_at IS NOT NULL
                    ) THEN TRUE
                    ELSE FALSE
                END AS email_verified,
                (
                    SELECT MAX(ev2.verified_at)
                    FROM email_verifications ev2
                    WHERE ev2.user_id = u.user_id
                      AND ev2.verified_at IS NOT NULL
                ) AS email_verified_at
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
        """

        params = []

        if status != "all":
            query += " WHERE LOWER(u.status) = %s"
            params.append(status)

        query += " ORDER BY u.created_at DESC, u.user_id DESC"

        cursor.execute(query, tuple(params))
        users = cursor.fetchall()

        for user in users:
            user["created_at"] = format_datetime_value(user.get("created_at"))
            user["email_verified_at"] = format_datetime_value(user.get("email_verified_at"))
            user["email_verified"] = bool(user.get("email_verified"))

        return jsonify(users), 200

    except Exception as error:
        print("GET REGISTRATION REQUESTS ERROR:", error)
        return jsonify({
            "message": "Failed to load registration requests.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/admin/registration-requests/<int:user_id>/approve", methods=["PUT"])
def approve_registration_request(user_id):
    data = request.get_json(silent=True) or {}

    approved_by = _safe_int_value(
        data.get("approved_by")
        or data.get("actor_id")
        or data.get("user_id")
        or data.get("userId")
    )

    new_role = str(data.get("role", "staff")).strip().lower()

    if new_role not in ["staff", "teamlead"]:
        new_role = "staff"

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        if not approved_by:
            conn.rollback()
            return jsonify({
                "message": "Approver user ID is required."
            }), 400

        if not is_registration_approver(cursor, approved_by):
            conn.rollback()
            return jsonify({
                "message": "Only manager or team lead can approve registrations."
            }), 403

        cursor.execute("""
            SELECT
                u.user_id,
                u.full_name,
                u.email,
                u.status,
                r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.user_id = %s
            LIMIT 1
        """, (user_id,))

        target_user = cursor.fetchone()

        if not target_user:
            conn.rollback()
            return jsonify({"message": "Registration request not found."}), 404

        if str(target_user.get("status", "")).lower() != "pending":
            conn.rollback()
            return jsonify({
                "message": "Only pending registration requests can be approved."
            }), 400

        if not is_user_email_verified(cursor, user_id):
            conn.rollback()
            return jsonify({
                "message": "This user has not verified their email yet. Ask them to click the email verification link before approval."
            }), 400

        cursor.execute("""
            SELECT role_id
            FROM roles
            WHERE LOWER(role_name) = %s
            LIMIT 1
        """, (new_role,))

        role_row = cursor.fetchone()

        if not role_row:
            conn.rollback()
            return jsonify({"message": "Selected role does not exist."}), 400

        cursor.execute("""
            UPDATE users
            SET status = 'active',
                role_id = %s
            WHERE user_id = %s
        """, (role_row["role_id"], user_id))

        conn.commit()

        notify_registration_decision(user_id, approved=True)

        add_audit_log(
            actor_id=approved_by,
            actor_name="Manager/Team Lead",
            action="Approved account registration",
            module="User Management",
            description=f"Approved user ID {user_id} as {new_role}."
        )

        return jsonify({
            "message": "Registration approved successfully. The user can now log in."
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("APPROVE REGISTRATION ERROR:", error)

        return jsonify({
            "message": "Failed to approve registration.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/admin/registration-requests/<int:user_id>/decline", methods=["PUT"])
def decline_registration_request(user_id):
    data = request.get_json(silent=True) or {}

    declined_by = _safe_int_value(
        data.get("declined_by")
        or data.get("actor_id")
        or data.get("user_id")
        or data.get("userId")
    )

    reason = str(data.get("reason", "")).strip()

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        if not declined_by:
            conn.rollback()
            return jsonify({
                "message": "Approver user ID is required."
            }), 400

        if not is_registration_approver(cursor, declined_by):
            conn.rollback()
            return jsonify({
                "message": "Only manager or team lead can decline registrations."
            }), 403

        cursor.execute("""
            SELECT user_id, full_name, email, status
            FROM users
            WHERE user_id = %s
            LIMIT 1
        """, (user_id,))

        target_user = cursor.fetchone()

        if not target_user:
            conn.rollback()
            return jsonify({"message": "Registration request not found."}), 404

        if str(target_user.get("status", "")).lower() != "pending":
            conn.rollback()
            return jsonify({
                "message": "Only pending registration requests can be declined."
            }), 400

        cursor.execute("""
            UPDATE users
            SET status = 'declined'
            WHERE user_id = %s
        """, (user_id,))

        conn.commit()

        notify_registration_decision(user_id, approved=False, reason=reason)

        add_audit_log(
            actor_id=declined_by,
            actor_name="Manager/Team Lead",
            action="Declined account registration",
            module="User Management",
            description=f"Declined user ID {user_id}. Reason: {reason or 'No reason provided.'}"
        )

        return jsonify({
            "message": "Registration declined successfully."
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("DECLINE REGISTRATION ERROR:", error)

        return jsonify({
            "message": "Failed to decline registration.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# MESSAGE CENTRE ROUTES
# Uses existing user_message table
# =========================

@app.route("/api/messages/users", methods=["GET"])
def get_message_users():
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                u.user_id,
                u.full_name,
                u.email,
                u.status,
                r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE LOWER(u.status) = 'active'
            ORDER BY u.full_name ASC
        """)

        users = cursor.fetchall()
        return jsonify(users), 200

    except Exception as error:
        print("MYSQL ERROR /api/messages/users:", error)
        return jsonify({
            "message": "Failed to load message users.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/messages/send", methods=["POST"])
def send_message():
    data = request.get_json() or {}

    sender_id = data.get("sender_id")
    receiver_id = data.get("receiver_id")
    subject = data.get("subject", "").strip()
    message = data.get("message", "").strip()

    if not sender_id or not receiver_id or not subject or not message:
        return jsonify({
            "message": "Sender, receiver, subject and message are required."
        }), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            INSERT INTO user_message
            (sender_id, receiver_id, subject, message)
            VALUES (%s, %s, %s, %s)
        """, (sender_id, receiver_id, subject, message))

        message_id = cursor.lastrowid

        cursor.execute("""
            UPDATE user_message
            SET thread_id = %s
            WHERE message_id = %s
        """, (message_id, message_id))

        conn.commit()

        return jsonify({
            "message": "Message sent successfully.",
            "message_id": message_id,
            "thread_id": message_id
        }), 201

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/messages/send:", error)
        return jsonify({
            "message": "Failed to send message.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/messages/threads/<int:user_id>", methods=["GET"])
def get_message_threads(user_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                latest.thread_id,
                latest.subject,
                latest.message AS latest_message,
                latest.created_at AS latest_created_at,
                latest.sender_id AS latest_sender_id,
                latest.receiver_id AS latest_receiver_id,

                CASE
                    WHEN latest.sender_id = %s THEN receiver.full_name
                    ELSE sender.full_name
                END AS other_user_name,

                COALESCE(unread.unread_count, 0) AS unread_count

            FROM user_message latest

            JOIN (
                SELECT
                    thread_id,
                    MAX(created_at) AS latest_time
                FROM user_message
                WHERE
                    (sender_id = %s AND is_deleted_by_sender = FALSE)
                    OR
                    (receiver_id = %s AND is_deleted_by_receiver = FALSE)
                GROUP BY thread_id
            ) grouped
                ON latest.thread_id = grouped.thread_id
                AND latest.created_at = grouped.latest_time

            LEFT JOIN users sender
                ON latest.sender_id = sender.user_id

            LEFT JOIN users receiver
                ON latest.receiver_id = receiver.user_id

            LEFT JOIN (
                SELECT
                    thread_id,
                    COUNT(*) AS unread_count
                FROM user_message
                WHERE receiver_id = %s
                AND is_read = FALSE
                AND is_deleted_by_receiver = FALSE
                GROUP BY thread_id
            ) unread
                ON latest.thread_id = unread.thread_id

            WHERE
                (latest.sender_id = %s AND latest.is_deleted_by_sender = FALSE)
                OR
                (latest.receiver_id = %s AND latest.is_deleted_by_receiver = FALSE)

            ORDER BY latest.created_at DESC
        """, (
            user_id,
            user_id,
            user_id,
            user_id,
            user_id,
            user_id
        ))

        threads = cursor.fetchall()
        return jsonify(threads), 200

    except Exception as error:
        print("MYSQL ERROR /api/messages/threads:", error)
        return jsonify({
            "message": "Failed to load message threads.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/messages/thread/<int:thread_id>/<int:user_id>", methods=["GET"])
def get_thread_messages(thread_id, user_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            UPDATE user_message
            SET is_read = TRUE
            WHERE thread_id = %s
            AND receiver_id = %s
        """, (thread_id, user_id))

        conn.commit()

        cursor.execute("""
            SELECT
                m.message_id,
                m.thread_id,
                m.parent_message_id,
                m.sender_id,
                m.receiver_id,
                m.subject,
                m.message,
                m.is_read,
                m.created_at,
                m.edited_at,
                sender.full_name AS sender_name,
                receiver.full_name AS receiver_name
            FROM user_message m
            LEFT JOIN users sender
                ON m.sender_id = sender.user_id
            LEFT JOIN users receiver
                ON m.receiver_id = receiver.user_id
            WHERE m.thread_id = %s
            AND (
                (m.sender_id = %s AND m.is_deleted_by_sender = FALSE)
                OR
                (m.receiver_id = %s AND m.is_deleted_by_receiver = FALSE)
            )
            ORDER BY m.created_at ASC
        """, (thread_id, user_id, user_id))

        messages = cursor.fetchall()
        return jsonify(messages), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/messages/thread:", error)
        return jsonify({
            "message": "Failed to load conversation.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/messages/reply", methods=["POST"])
def reply_message():
    data = request.get_json() or {}

    thread_id = data.get("thread_id")
    parent_message_id = data.get("parent_message_id")
    sender_id = data.get("sender_id")
    receiver_id = data.get("receiver_id")
    subject = data.get("subject", "").strip()
    message = data.get("message", "").strip()

    if not thread_id or not sender_id or not receiver_id or not message:
        return jsonify({
            "message": "Thread, sender, receiver and message are required."
        }), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            INSERT INTO user_message
            (
                thread_id,
                parent_message_id,
                sender_id,
                receiver_id,
                subject,
                message
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            thread_id,
            parent_message_id,
            sender_id,
            receiver_id,
            subject,
            message
        ))

        conn.commit()

        return jsonify({
            "message": "Reply sent successfully."
        }), 201

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/messages/reply:", error)
        return jsonify({
            "message": "Failed to send reply.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/messages/edit/<int:message_id>", methods=["PUT"])
def edit_message(message_id):
    data = request.get_json() or {}

    user_id = data.get("user_id")
    message = data.get("message", "").strip()

    if not user_id or not message:
        return jsonify({
            "message": "User ID and message are required."
        }), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            UPDATE user_message
            SET message = %s,
                edited_at = NOW()
            WHERE message_id = %s
            AND sender_id = %s
        """, (message, message_id, user_id))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({
                "message": "You can only edit messages you sent."
            }), 403

        return jsonify({
            "message": "Message updated successfully."
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/messages/edit:", error)
        return jsonify({
            "message": "Failed to edit message.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/messages/delete/<int:message_id>", methods=["PUT"])
def delete_message_from_view(message_id):
    data = request.get_json() or {}

    user_id = data.get("user_id")

    if not user_id:
        return jsonify({
            "message": "User ID is required."
        }), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT sender_id, receiver_id
            FROM user_message
            WHERE message_id = %s
            LIMIT 1
        """, (message_id,))

        msg = cursor.fetchone()

        if not msg:
            return jsonify({
                "message": "Message not found."
            }), 404

        if int(msg["sender_id"]) == int(user_id):
            cursor.execute("""
                UPDATE user_message
                SET is_deleted_by_sender = TRUE
                WHERE message_id = %s
            """, (message_id,))

        elif int(msg["receiver_id"]) == int(user_id):
            cursor.execute("""
                UPDATE user_message
                SET is_deleted_by_receiver = TRUE
                WHERE message_id = %s
            """, (message_id,))

        else:
            return jsonify({
                "message": "You can only delete messages linked to your account."
            }), 403

        conn.commit()

        return jsonify({
            "message": "Message deleted from your view."
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/messages/delete:", error)
        return jsonify({
            "message": "Failed to delete message.",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()




@app.route("/static/<path:filename>", methods=["GET"])
def serve_static(filename):
    clean_filename = str(filename or "").replace("\\", "/").strip().lstrip("/")
    file_path = STATIC_DIR / clean_filename

    if file_path.exists() and file_path.is_file():
        return send_from_directory(str(file_path.parent), file_path.name)

    basename = Path(clean_filename).name
    matched_file = None

    if basename and STATIC_DIR.exists():
        for candidate in STATIC_DIR.rglob(basename):
            if candidate.exists() and candidate.is_file():
                matched_file = candidate
                break

    if matched_file:
        return send_from_directory(str(matched_file.parent), matched_file.name)

    return jsonify({
        "message": "Static file not found on server.",
        "filename": clean_filename,
        "static_folder": str(STATIC_DIR),
        "expected_path": str(file_path)
    }), 404

# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    verify_manager_account()
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)