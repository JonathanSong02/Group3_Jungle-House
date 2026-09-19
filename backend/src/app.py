# Trigger redeploy to verify the persistent uploads volume survives a restart.
from flask import Flask, request, jsonify, send_from_directory, redirect, g, session
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
import hmac
import requests

from email.message import EmailMessage


def load_local_env_file():
    """
    Load backend/src/.env automatically for local development.

    Existing OS/Railway environment variables always win.
    This keeps production configuration unchanged while removing the need
    to manually enter SMTP variables in PowerShell every time.
    """
    try:
        env_path = Path(__file__).resolve().parent / ".env"

        if not env_path.exists():
            return

        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if not key:
                continue

            # Support normal .env quoting.
            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in {"'", '"'}
            ):
                value = value[1:-1]

            # Do not overwrite real Railway/system environment variables.
            os.environ.setdefault(key, value)

        print(f"LOCAL ENV LOADED: {env_path}")

    except Exception as error:
        print("LOCAL ENV LOAD WARNING:", error)


load_local_env_file()

# ============================================================
# PRESENTATION DEMO MODE
# ============================================================
# Legacy toggle retained only for the separate system email-test screen.
# The new registration and approval flow NEVER sends emails or activation keys.
# Demo mode defaults off and disables password-recovery email attempts.
PRESENTATION_DEMO_MODE = os.getenv("PRESENTATION_DEMO_MODE", "false").strip().lower() == "true"

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

CJK_CHAR_RE = re.compile(r'[一-鿿㐀-䶿豈-﫿]')


def is_nonsense(text):
    text = text.strip().lower()

    whitelist = ["hi", "hello", "hey", "ok", "thanks"]

    if text in whitelist:
        return False

    # The heuristics below (vowels, a-z letters, "asdf"/"qwer" keyboard-smash
    # patterns) all assume Latin-alphabet input. Chinese text has no Latin
    # vowels/letters at all by design, so without this bypass EVERY Chinese
    # question would be wrongly flagged as nonsense before it ever reached
    # KB search. Only keep the script-agnostic checks (too-short, spam
    # repeated characters) for CJK text.
    if CJK_CHAR_RE.search(text):
        if len(text) < 2:
            return True
        if re.fullmatch(r'(.)\1{3,}', text):
            return True
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
# A stable, private key is mandatory for signed, HttpOnly Flask session cookies.
# Set FLASK_SECRET_KEY (at least 32 random bytes) in Railway and backend/src/.env.
_session_secret = os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY")
if not _session_secret or len(_session_secret) < 32:
    raise RuntimeError("Configure a stable FLASK_SECRET_KEY of at least 32 characters.")
app.config.update(
    SECRET_KEY=_session_secret,
    SESSION_COOKIE_NAME="jh_wiki_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=(
        os.getenv("SESSION_COOKIE_SECURE", "true" if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_ENVIRONMENT_NAME") else "false")
        .strip().lower() == "true"
    ),
    SESSION_COOKIE_SAMESITE="Lax",  # Production /api must go through the Vercel same-origin proxy.
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

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


@app.after_request
def attach_uploaded_chat_image_url(response):
    """
    /chat has several early-return paths (direct visual match, related
    options, irrelevant-image rejection, normal KB/SOP fallback). Every one
    of them should tell the frontend the PERMANENT saved URL of whatever
    photo the user just uploaded, so the "You uploaded..." chat bubble can
    be re-saved pointing at that instead of a browser blob: URL (which
    breaks the moment it's revoked/the page reloads). Doing it here once,
    keyed off flask.g, is simpler and less error-prone than editing every
    return statement in chat() by hand.
    """
    uploaded_image_url = getattr(g, "uploaded_chat_image_url", None)

    if not uploaded_image_url or not response.is_json:
        return response

    try:
        payload = response.get_json()

        if isinstance(payload, dict):
            payload.setdefault("uploaded_image_url", uploaded_image_url)
            payload.setdefault("uploaded_image_type", getattr(g, "uploaded_chat_image_type", None))
            response.set_data(json.dumps(payload))
    except Exception as error:
        print("ATTACH UPLOADED IMAGE URL ERROR:", error)

    return response


# Browser origins allowed to call the Railway API.  Keep the deployed
# frontend in the list and also honour FRONTEND_URL so production can be
# changed from Railway Variables without editing Python again.
_cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://ai-powered-wiki-training-assistant.vercel.app",
    "https://jhgroup3.com",
    "https://www.jhgroup3.com",
]
_configured_frontend_origin = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
if _configured_frontend_origin and _configured_frontend_origin not in _cors_origins:
    _cors_origins.append(_configured_frontend_origin)

CORS(
    app,
    resources={r"/*": {"origins": _cors_origins}},
    supports_credentials=True,
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
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

        # Temporary diagnostic logging: two rounds of guessing at the
        # pasted-image corruption bug (Content-Type header, Vercel proxy)
        # both turned out wrong. This prints the real, actual bytes Railway
        # received, so the next fix is based on evidence instead of a
        # third guess. Safe to remove once that bug is confirmed fixed.
        try:
            saved_size = file_path.stat().st_size
            with open(file_path, "rb") as saved_file:
                first_bytes = saved_file.read(16)
            print(
                "ARTICLE UPLOAD DEBUG:",
                "filename=", filename,
                "content_type=", file.content_type,
                "saved_size_bytes=", saved_size,
                "first_16_bytes_hex=", first_bytes.hex(),
            )
        except Exception as debug_error:
            print("ARTICLE UPLOAD DEBUG ERROR:", debug_error)

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


def build_image_only_clarification_response(vision_result, kb_hint=None):
    """
    Case B (image uploaded with no real question): identify the object and
    ask what the user wants to know instead of forcing the request through
    the strict KB/escalation pipeline, which only ever finds a 100%-exact
    text match and would otherwise escalate every plain "here's a photo"
    upload -- exactly the bug this fixes.
    """
    detected = list((vision_result or {}).get("detectedObjects") or [])
    object_phrase = detected[0] if detected else None

    if object_phrase:
        message = (
            f"This looks like {object_phrase}. What would you like to know about it? "
            "For example, you can ask where it's stored, how to use it, or its opening/closing steps."
        )
    else:
        message = (
            "I can see you uploaded an image, but I need a bit more detail. "
            "What would you like to know about it?"
        )

    if kb_hint and kb_hint.get("title"):
        message += f" I also found a related guide: \"{kb_hint['title']}\" -- ask me about it directly for the full steps."

    return standardize_ai_response({
        "type": "text",
        "reply": message,
        "answer": message,
        "score": 0.0,
        "confidence": 0.0,
        "source": "image_only_clarification",
        "final_source": "image_only_clarification",
        "served_by": "vision_relevance_check",
        "fallback": False,
        "escalation_ready": False,
        "escalation_required": False,
        "context": {
            "image_summary": (vision_result or {}).get("imageSummary", ""),
            "detected_objects": detected,
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


def send_private_static_file(directory, filename):
    """Serve only an exact file inside its expected directory; never search other folders."""
    relative_name = str(filename or "").replace("\\", "/")
    if (not relative_name or relative_name.startswith("/") or
            any(part in {"", ".", ".."} for part in relative_name.split("/"))):
        return jsonify({"message": "File not found."}), 404

    root = Path(directory).resolve()
    try:
        resolved_file = (root / relative_name).resolve(strict=True)
    except (OSError, RuntimeError):
        return jsonify({"message": "File not found."}), 404

    # Reject symlinks leading outside the upload directory and directories themselves.
    if not resolved_file.is_relative_to(root) or not resolved_file.is_file():
        return jsonify({"message": "File not found."}), 404
    return send_from_directory(str(root), relative_name)


@app.route("/static/uploads/articles/<path:filename>", methods=["GET"])
def serve_article_attachment(filename):
    return send_private_static_file(UPLOAD_FOLDER, filename)


@app.route("/static/uploads/chat/<path:filename>", methods=["GET"])
def serve_chat_upload(filename):
    return send_private_static_file(CHAT_UPLOAD_FOLDER, filename)

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
    return send_private_static_file(SOP_IMAGE_FOLDER, filename)


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
    """Connect using Railway Variables or backend/src/.env, never embedded credentials."""
    host = os.getenv("DB_HOST") or os.getenv("MYSQL_HOST") or os.getenv("MYSQLHOST")
    port = os.getenv("DB_PORT") or os.getenv("MYSQL_PORT") or os.getenv("MYSQLPORT") or "3306"
    username = os.getenv("DB_USER") or os.getenv("MYSQL_USER") or os.getenv("MYSQLUSER")
    password = os.getenv("DB_PASSWORD") or os.getenv("MYSQL_PASSWORD") or os.getenv("MYSQLPASSWORD")
    database = os.getenv("DB_NAME") or os.getenv("MYSQL_DATABASE") or os.getenv("MYSQLDATABASE")
    if not all((host, username, password, database)):
        raise RuntimeError("Missing MySQL environment configuration (DB_* or MYSQL*).")
    try:
        return mysql.connector.connect(
            host=host, port=int(port), user=username,
            password=password, database=database,
        )
    except mysql.connector.Error:
        print("DATABASE CONNECTION ERROR: Check MySQL connectivity and Railway Variables.")
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
# SESSION AUTHENTICATION / AUTHORIZATION
# =========================
def password_session_fingerprint(password_hash):
    """Password changes invalidate older signed sessions on their next request."""
    return hashlib.sha256(str(password_hash or "").encode("utf-8")).hexdigest()


def current_auth_user_id():
    return int(g.auth_user["user_id"])


@app.route("/api/auth/csrf", methods=["GET"])
def auth_csrf():
    """Initialize a browser session before register/login and return its CSRF token."""
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    response = jsonify({"csrf_token": session["csrf_token"]})
    response.headers["Cache-Control"] = "no-store"
    return response, 200


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    response = jsonify({
        "user": get_user_profile_payload(g.auth_user),
        "csrf_token": session["csrf_token"],
    })
    response.headers["Cache-Control"] = "no-store"
    return response, 200


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    response = jsonify({"message": "Logged out successfully."})
    response.headers["Cache-Control"] = "no-store"
    return response, 200


_AUTH_PUBLIC = {
    "auth_csrf", "register", "login", "forgot_password",
    "validate_password_reset_token", "reset_password", "health",
}
_LEGACY_REGISTRATION_ENDPOINTS = {
    "generate_registration_key", "list_registration_keys", "resend_registration_key",
    "revoke_registration_key", "activate_registration_key", "resend_activation_key",
}
_APPROVER_ENDPOINTS = {
    "get_registration_requests", "get_registration_history", "approve_registration_request", "decline_registration_request",
    "get_admin_users", "test_system_email", "get_admin_quizzes",
    "create_admin_quiz", "update_admin_quiz", "delete_admin_quiz",
    "get_admin_quiz_questions", "create_quiz_question", "update_admin_quiz_question",
    "delete_admin_quiz_question", "ai_generate_quiz",
    "get_reviews", "approve_review", "reject_review", "publish_review",
    "get_analytics",
    # Team Leaders may view Security Monitoring reports, but cannot manage
    # user roles/statuses or change privileged system configuration.
    "get_login_history", "get_audit_logs",
    "get_escalations", "submit_escalation_answer", "approve_escalation_answer",
    "reject_escalation_answer", "bulk_delete_escalations",
    "bulk_permanent_delete_escalations", "delete_escalation",
    "restore_escalation", "permanent_delete_escalation",
    "add_article", "upload_article_editor_image", "edit_article", "delete_article",
    "restore_article", "bulk_permanent_delete_articles", "permanent_delete_article",
}
_MANAGER_ENDPOINTS = {
    "get_ai_settings", "save_ai_settings", "test_ai_settings",
    "get_notion_sync_config", "save_notion_sync_config", "test_notion_sync",
    "run_notion_sync", "get_notion_sync_jobs",
    "update_admin_user_role", "update_admin_user_status", "test_db",
    "debug_chat_uploads", "debug_sop_images", "debug_static_files", "debug_uploads",
}
_SELF_PROFILE_ENDPOINTS = {"get_profile", "update_profile", "change_password"}
_SELF_MESSAGE_ENDPOINTS = {"get_message_threads", "get_thread_messages"}


@app.before_request
def require_authenticated_api():
    """Enforce active DB-backed identities for every private API request.

    Frontend role, actor_id and localStorage values are NEVER authentication.
    """
    if request.method == "OPTIONS":
        return None  # CORS preflight has no signed cookie or CSRF header.
    path = request.path
    endpoint = request.endpoint or ""
    if endpoint in {"serve_static", "serve_article_attachment", "serve_chat_upload", "serve_sop_image"}:
        filename = str((request.view_args or {}).get("filename") or "").replace("\\", "/")
        if not filename or any(segment in {".", ".."} for segment in filename.split("/")):
            return jsonify({"message": "File not found."}), 404
    # The session cookie is shared with /static via the Vercel same-origin rewrite.
    # Protect both the Vercel proxy path and direct requests to Railway.
    if not (path.startswith("/api/") or path == "/chat" or path.startswith("/static/")):
        return None
    if endpoint in _LEGACY_REGISTRATION_ENDPOINTS:
        return jsonify({
            "code": "REGISTRATION_KEYS_REMOVED",
            "message": "Registration keys are no longer supported. Contact your Manager for approval."
        }), 410
    if endpoint in _AUTH_PUBLIC:
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            expected = str(session.get("csrf_token") or "")
            provided = request.headers.get("X-CSRF-Token", "")
            if not expected or not hmac.compare_digest(expected, provided):
                return jsonify({"code": "CSRF_INVALID", "message": "Security token missing or expired. Refresh the page and retry."}), 403
        return None
    if endpoint == "auth_logout":
        expected = str(session.get("csrf_token") or "")
        provided = request.headers.get("X-CSRF-Token", "")
        if not expected or not hmac.compare_digest(expected, provided):
            return jsonify({"code": "CSRF_INVALID", "message": "Security token missing or expired."}), 403
        return None

    stored_id = session.get("user_id")
    fingerprint = session.get("password_fingerprint")
    if not isinstance(stored_id, int) or not fingerprint:
        session.clear()
        return jsonify({"code": "SESSION_EXPIRED", "message": "Please log in to continue."}), 401
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.user_id, u.full_name, u.email, u.password_hash,
                   u.status, u.created_at, r.role_name
            FROM users u JOIN roles r ON u.role_id = r.role_id
            WHERE u.user_id = %s LIMIT 1
        """, (stored_id,))
        user = cursor.fetchone()
    except Exception:
        print("SESSION CHECK ERROR: Could not validate session against database.")
        return jsonify({"code": "AUTH_UNAVAILABLE", "message": "Authentication service unavailable. Please retry."}), 503
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    if not user:
        session.clear()
        return jsonify({"code": "SESSION_EXPIRED", "message": "Your session has expired. Please log in."}), 401
    if str(user.get("status") or "").lower() != "active":
        session.clear()
        return jsonify({"code": "ACCOUNT_INACTIVE", "message": "This account is not active."}), 403
    if not hmac.compare_digest(str(fingerprint), password_session_fingerprint(user["password_hash"])):
        session.clear()
        return jsonify({"code": "SESSION_EXPIRED", "message": "Your account credentials have changed. Please log in again."}), 401
    g.auth_user = user
    role = str(user.get("role_name") or "").strip().lower()
    if endpoint in _MANAGER_ENDPOINTS and role not in {"manager", "admin"}:
        return jsonify({"code": "FORBIDDEN", "message": "Manager access required."}), 403
    if endpoint in _APPROVER_ENDPOINTS and role not in APPROVER_ROLES:
        return jsonify({"code": "FORBIDDEN", "message": "Manager or Team Leader access required."}), 403
    if endpoint in _SELF_PROFILE_ENDPOINTS | _SELF_MESSAGE_ENDPOINTS | {"get_notifications"}:
        requested_user_id = (request.view_args or {}).get("user_id")
        if requested_user_id != stored_id:
            return jsonify({"code": "FORBIDDEN", "message": "You can only access your own account."}), 403
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        expected = str(session.get("csrf_token") or "")
        provided = request.headers.get("X-CSRF-Token", "")
        if not expected or not hmac.compare_digest(expected, provided):
            return jsonify({"code": "CSRF_INVALID", "message": "Security token missing or expired. Refresh the page and retry."}), 403
    return None


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
PASSWORD_RESET_TOKEN_MINUTES = int(os.getenv("PASSWORD_RESET_TOKEN_MINUTES", "30"))
PASSWORD_RESET_COOLDOWN_SECONDS = int(os.getenv("PASSWORD_RESET_COOLDOWN_SECONDS", "60"))
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

    # Presentation-only hardcoded email simulation. This deliberately does
    # not contact Gmail/SMTP. The rest of the application still receives a
    # successful delivery result so the real registration workflow can be
    # demonstrated end-to-end.
    if PRESENTATION_DEMO_MODE:
        if not to_email:
            print("DEMO EMAIL SKIPPED: Recipient email is empty.")
            return False
        print("\n" + "=" * 72)
        print("PRESENTATION DEMO EMAIL (SIMULATED - NOT ACTUALLY SENT)")
        print(f"TO: {to_email}")
        print(f"SUBJECT: {subject}")
        print("-" * 72)
        print(body)
        print("=" * 72 + "\n")
        return True

    # Gmail-compatible defaults. For local use, only the sender email and
    # app password must be placed in backend/src/.env once.
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from = os.getenv("SMTP_FROM_EMAIL", smtp_user).strip()
    smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() != "false"

    # Google shows App Passwords in grouped blocks. If those spaces were
    # copied into Railway, Gmail authentication can fail. Normalise only
    # for Gmail so other SMTP providers keep their password unchanged.
    if "gmail.com" in smtp_host.lower():
        smtp_password = "".join(smtp_password.split())

    if not to_email:
        print("EMAIL SKIPPED: Recipient email is empty.")
        return False

    if not smtp_user or not smtp_password or not smtp_from:
        print(
            "EMAIL SKIPPED: Configure SMTP_USER and SMTP_PASSWORD in Railway Variables "
            "(or backend/src/.env for local development)."
        )
        return False

    try:
        message = EmailMessage()
        message["From"] = f"Jungle House AI Wiki <{smtp_from}>"
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            if smtp_use_tls:
                server.starttls()

            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)

            server.send_message(message)

        print(f"EMAIL SENT: to={to_email} subject={subject!r} via={smtp_host}:{smtp_port}")
        return True

    except smtplib.SMTPAuthenticationError as error:
        print(
            "SEND EMAIL AUTH ERROR: Gmail rejected SMTP credentials. "
            "Use the Google App Password (not the normal account password).",
            error,
        )
        return False
    except Exception as error:
        print("SEND EMAIL SAFE ERROR:", error)
        return False





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



def send_registration_received_email(full_name, email):
    """Legacy compatibility only: registration acknowledgment emails are disabled."""
    return False


def send_registration_declined_email(full_name, email, reason=""):
    """Legacy compatibility only: registration-decision emails are disabled."""
    return False


def send_activation_cancelled_email(full_name, email):
    """Legacy compatibility only: registration-key emails are disabled."""
    return False




# =========================
# PASSWORD RESET HELPERS
# =========================
def ensure_password_reset_tokens_table(cursor):
    """Create the reset-token table on demand; no manual Railway DB migration is required."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            reset_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            token_hash CHAR(64) NOT NULL UNIQUE,
            expires_at DATETIME NOT NULL,
            used_at DATETIME NULL,
            requested_ip VARCHAR(64) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_password_reset_user_id (user_id),
            INDEX idx_password_reset_token_hash (token_hash),
            INDEX idx_password_reset_expires_at (expires_at),
            CONSTRAINT fk_password_reset_user
                FOREIGN KEY (user_id) REFERENCES users(user_id)
                ON DELETE CASCADE
        )
    """)


def hash_password_reset_token(token):
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def create_password_reset_token(cursor, user_id):
    ensure_password_reset_tokens_table(cursor)

    # Only the newest reset link should remain usable.
    cursor.execute("""
        UPDATE password_reset_tokens
        SET used_at = NOW()
        WHERE user_id = %s
          AND used_at IS NULL
    """, (user_id,))

    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_password_reset_token(raw_token)
    expires_at = datetime.now() + timedelta(minutes=PASSWORD_RESET_TOKEN_MINUTES)

    cursor.execute("""
        INSERT INTO password_reset_tokens
            (user_id, token_hash, expires_at, requested_ip)
        VALUES (%s, %s, %s, %s)
    """, (
        user_id,
        token_hash,
        expires_at,
        str(request.remote_addr or "")[:64] or None,
    ))

    return raw_token


def send_password_reset_email(full_name, email, raw_token):
    reset_url = f"{FRONTEND_URL}/reset-password?token={raw_token}"
    subject = "Jungle House AI Wiki - Reset your password"
    body = f"""Hi {full_name or 'there'},

We received a request to reset the password for your Jungle House AI Wiki account.

Reset your password using this link:
{reset_url}

This link expires in {PASSWORD_RESET_TOKEN_MINUTES} minutes and can only be used once.

If you did not request a password reset, you can ignore this email. Your current password will remain unchanged.

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


def is_active_manager(cursor, actor_id):
    """Manager-only check for role/status administration."""
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
    return role_name in {"manager", "admin"} and status == "active"


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

    return role_name in APPROVER_ROLES and status == "active"


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

    return role_name in {"manager", "admin"} and status == "active"


def ensure_registration_keys_table(cursor):
    """
    Keep the existing staff_registration_keys table and upgrade it in-place.

    New activation keys are bound to one email address. Existing legacy keys
    are preserved in the database only for historical compatibility; unassigned
    legacy keys are excluded from the final approval/activation workflow.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS staff_registration_keys (
            key_id INT AUTO_INCREMENT PRIMARY KEY,
            key_code VARCHAR(10) NOT NULL UNIQUE,
            status ENUM('unused', 'used', 'revoked') NOT NULL DEFAULT 'unused',
            created_by_user_id INT NULL,
            used_by_user_id INT NULL,
            used_by_email VARCHAR(255) NULL,
            assigned_email VARCHAR(255) NULL,
            assigned_at DATETIME NULL,
            email_sent_at DATETIME NULL,
            failed_attempts INT NOT NULL DEFAULT 0,
            last_failed_at DATETIME NULL,
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

    # CREATE TABLE IF NOT EXISTS does not add columns to an existing table,
    # so safely add only the new activation-key fields when they are missing.
    columns = get_table_columns_safe(cursor, "staff_registration_keys")

    migrations = {
        "assigned_email": "ALTER TABLE staff_registration_keys ADD COLUMN assigned_email VARCHAR(255) NULL AFTER used_by_email",
        "assigned_at": "ALTER TABLE staff_registration_keys ADD COLUMN assigned_at DATETIME NULL AFTER assigned_email",
        "email_sent_at": "ALTER TABLE staff_registration_keys ADD COLUMN email_sent_at DATETIME NULL AFTER assigned_at",
        "failed_attempts": "ALTER TABLE staff_registration_keys ADD COLUMN failed_attempts INT NOT NULL DEFAULT 0 AFTER email_sent_at",
        "last_failed_at": "ALTER TABLE staff_registration_keys ADD COLUMN last_failed_at DATETIME NULL AFTER failed_attempts",
        "revoked_at": "ALTER TABLE staff_registration_keys ADD COLUMN revoked_at DATETIME NULL AFTER used_at",
    }

    for column_name, statement in migrations.items():
        if column_name not in columns:
            cursor.execute(statement)

    # Older databases may still have ENUM('unused','used') only. The new
    # approval flow needs 'revoked' so a cancelled/declined activation key
    # can never be reused.
    cursor.execute("SHOW COLUMNS FROM staff_registration_keys LIKE 'status'")
    status_column = cursor.fetchone()

    if isinstance(status_column, dict):
        status_type = str(status_column.get("Type", "")).lower()
    else:
        status_type = str(status_column[1] if status_column and len(status_column) > 1 else "").lower()

    if "revoked" not in status_type:
        cursor.execute("""
            ALTER TABLE staff_registration_keys
            MODIFY COLUMN status ENUM('unused', 'used', 'revoked')
            NOT NULL DEFAULT 'unused'
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
            # Older Railway schemas may define notification.type as an ENUM
            # with only a few values. Do not let new registration labels such
            # as "registration" crash the insert; fall back to "system" (or
            # the first allowed ENUM value) when necessary.
            safe_notification_type = notification_type
            try:
                cursor.execute("SHOW COLUMNS FROM notification LIKE 'type'")
                type_column = cursor.fetchone() or {}
                type_definition = str(type_column.get("Type", "")) if isinstance(type_column, dict) else str(type_column[1] if len(type_column) > 1 else "")
                enum_values = re.findall(r"'([^']+)'", type_definition)
                if enum_values and safe_notification_type not in enum_values:
                    safe_notification_type = "system" if "system" in enum_values else enum_values[0]
            except Exception as type_error:
                print("NOTIFICATION TYPE CHECK WARNING:", type_error)

            payload["type"] = safe_notification_type

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
                detail=f"{full_name} ({email}) has registered and is waiting for Manager / Team Leader approval.",
                notification_type="system",
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
    """In-app decision notification only; no registration emails or keys."""
    detail = ("Your account was approved. Sign in with your email and password."
              if approved else "Your registration was declined. Contact your Manager for assistance.")
    if not approved and reason:
        detail += f" Reason: {reason}"
    create_notification_safe(
        user_id=user_id, title="Account approved" if approved else "Registration declined",
        detail=detail, notification_type="system", related_id=user_id,
    )


# =========================
# PENDING REGISTRATION WIPE HELPER
# =========================
def _table_columns_for_cleanup(cursor, table_name):
    cursor.execute("""
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
    """, (table_name,))
    rows = cursor.fetchall() or []
    result = set()
    for row in rows:
        if isinstance(row, dict):
            result.add(str(row.get("COLUMN_NAME") or ""))
        elif row:
            result.add(str(row[0]))
    return {value for value in result if value}


def wipe_pending_registration(cursor, user_id, email):
    """
    Permanently remove a PENDING registration and its auth/security traces
    that directly reference the pending user, so the same email can register
    again immediately. This is intentionally only used by the Manager/Team
    Lead decline route, before the account has ever been activated.
    """
    email = str(email or "").strip().lower()

    # Email-bound activation records are not all foreign-keyed to users, so
    # remove them explicitly first.
    key_columns = _table_columns_for_cleanup(cursor, "staff_registration_keys")
    if key_columns:
        conditions = []
        params = []
        if "assigned_email" in key_columns:
            conditions.append("LOWER(assigned_email) = %s")
            params.append(email)
        if "used_by_email" in key_columns:
            conditions.append("LOWER(used_by_email) = %s")
            params.append(email)
        if "used_by_user_id" in key_columns:
            conditions.append("used_by_user_id = %s")
            params.append(user_id)
        if conditions:
            cursor.execute(
                f"DELETE FROM staff_registration_keys WHERE {' OR '.join(conditions)}",
                tuple(params),
            )

    # Known account/auth tables. Only execute against columns that actually
    # exist in the current Railway schema.
    cleanup_rules = [
        ("password_reset_tokens", [("user_id", user_id)]),
        ("email_verifications", [("user_id", user_id)]),  # legacy-table cleanup only
        ("login_history", [("user_id", user_id)]),
        ("audit_log", [("actor_id", user_id)]),
        ("notification", [("user_id", user_id), ("created_by", user_id)]),
        ("notification_user_reads", [("user_id", user_id)]),
        ("user_message", [("sender_id", user_id), ("receiver_id", user_id)]),
        ("quiz_result", [("user_id", user_id)]),
        ("escalation", [("asked_by", user_id), ("handled_by", user_id), ("deleted_by", user_id)]),
    ]

    for table_name, candidates in cleanup_rules:
        columns = _table_columns_for_cleanup(cursor, table_name)
        if not columns:
            continue
        usable = [(column, value) for column, value in candidates if column in columns]
        if not usable:
            continue
        where_sql = " OR ".join([f"{column} = %s" for column, _ in usable])
        cursor.execute(
            f"DELETE FROM {table_name} WHERE {where_sql}",
            tuple(value for _, value in usable),
        )

    # Final parent delete. If an unexpected table still references this
    # pending user, MySQL will block the transaction rather than silently
    # corrupting data, and the API returns the concrete error for diagnosis.
    cursor.execute("DELETE FROM users WHERE user_id = %s AND status = 'pending'", (user_id,))
    if cursor.rowcount != 1:
        raise RuntimeError("Pending user could not be removed.")


def revoke_legacy_unused_registration_keys(cursor, email):
    """Retain all historical keys; revoke only unused keys bound to this account.

    Older deployments may lack this table or the assigned_email column. Do not
    create or migrate any table as part of the new approval workflow.
    """
    cursor.execute("SHOW TABLES LIKE 'staff_registration_keys'")
    if not cursor.fetchone():
        return
    columns = get_table_columns_safe(cursor, "staff_registration_keys")
    if not {"assigned_email", "status"}.issubset(columns):
        return
    cursor.execute("SHOW COLUMNS FROM staff_registration_keys LIKE 'status'")
    status_column = cursor.fetchone()
    type_definition = (str(status_column.get("Type") or "") if isinstance(status_column, dict)
                       else str(status_column[1] if status_column and len(status_column) > 1 else ""))
    if "revoked" not in type_definition.lower():
        # Key endpoints are disabled. Historical data must not block approval.
        return
    if "revoked_at" in columns:
        cursor.execute("""
            UPDATE staff_registration_keys
            SET status = 'revoked', revoked_at = NOW()
            WHERE LOWER(assigned_email) = %s AND status = 'unused'
        """, (email,))
    else:
        cursor.execute("""
            UPDATE staff_registration_keys SET status = 'revoked'
            WHERE LOWER(assigned_email) = %s AND status = 'unused'
        """, (email,))


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


# =========================
# CROSS-LINGUAL RETRIEVAL BRIDGE
#
# The Knowledge Base (wiki_article) is English-only, and KB search
# (search_knowledge_base_articles / search_related_knowledge_base_articles /
# build_ai_chat_context) matches on English word/token overlap. A Chinese or
# Bahasa Melayu question has zero token overlap with English article text no
# matter how relevant the article is, so retrieval silently finds nothing.
#
# The functions below detect a non-English question and derive a short
# English keyword string from it (via the already-configured AI provider)
# used ONLY to drive retrieval -- the staff member's original question is
# still what gets logged, escalated, and answered. Everything here fails
# soft: if detection/translation isn't possible for any reason, callers fall
# back to the raw original question, which is exactly today's behavior.
# =========================
MALAY_MARKER_WORDS = {
    "yang", "adalah", "ialah", "bagaimana", "macam", "mana", "apa", "apakah",
    "bila", "bilakah", "kenapa", "mengapa", "kalau", "jika", "boleh", "tak",
    "tidak", "nak", "mahu", "saya", "awak", "kami", "kita", "dengan", "untuk",
    "daripada", "cara", "langkah", "tolong", "sila", "di", "ke", "pada",
    "ini", "itu", "siapa", "berapa",
}


def detect_question_language(text: str) -> str:
    """
    Lightweight, dependency-free language guess -- just enough to decide
    whether the cross-lingual retrieval bridge should run. Not a general
    purpose language detector.

    Returns "zh" (Chinese, Simplified or Traditional), "ms" (Bahasa
    Melayu), or "en" (English / anything else / undetermined).
    """
    text = str(text or "")

    if CJK_CHAR_RE.search(text):
        return "zh"

    lowered = re.sub(r"[^a-z\s']", " ", text.lower())
    tokens = set(lowered.split())

    if not tokens:
        return "en"

    english_stopwords = {
        "the", "is", "are", "a", "an", "to", "of", "and", "for", "how",
        "what", "where", "when", "why", "do", "does", "i", "you", "we",
        "please", "can",
    }

    malay_hits = tokens & MALAY_MARKER_WORDS

    # Require at least one distinctive Malay marker word AND no English
    # stopwords, to avoid false-positives on ordinary short English
    # questions (many Malay markers, e.g. "di"/"ini", are also short enough
    # to collide by chance).
    if malay_hits and not (tokens & english_stopwords):
        return "ms"

    return "en"


def translate_query_to_english_keywords(question: str, detected_language: str) -> str:
    """
    Asks the already-configured AI provider for 2-4 short English search
    keywords capturing the intent of a non-English question -- a cheap,
    lightweight call, not a full translation. Used only to drive KB
    retrieval (search_knowledge_base_articles / search_related_knowledge_base_articles /
    build_ai_chat_context); never shown to the user and never stored as the
    logged/escalated question.

    Falls back to the raw original question on ANY failure (no AI provider
    configured, timeout, malformed output) so retrieval still runs the same
    way it did before this feature existed.
    """
    question = str(question or "").strip()

    if not question or detected_language == "en":
        return question

    if not AI_PROVIDER_SERVICE_AVAILABLE or not ai_provider_service:
        return question

    try:
        prompt = (
            "A retail staff member asked a question in a non-English "
            "language. Give 2 to 4 short ENGLISH keywords that capture "
            "what they are asking about, for searching an English-only "
            "knowledge base. Reply with ONLY the keywords separated by "
            "spaces -- no punctuation, no explanation, no translation of "
            "the whole sentence.\n\n"
            f"Question: {question}"
        )
        raw_reply = ai_provider_service.generate_ai_reply(prompt, timeout=8)
        keywords = re.sub(r"[^\w\s]", " ", str(raw_reply or ""))
        keywords = " ".join(keywords.split())

        if keywords:
            return keywords
    except Exception as error:
        print("CROSS-LINGUAL KEYWORD BRIDGE ERROR:", error)

    return question


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
        "article_id": article.get("article_id"),
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


def search_related_knowledge_base_articles(question, limit=3, min_score=0.34):
    """
    Level-2 retrieval: articles that are topically related but do not clear
    the strict 100%-confidence bar used by search_knowledge_base_articles().
    Used to show clickable "related knowledge" cards before escalating,
    instead of jumping straight from "not confident" to a team lead ticket.

    min_score=0.34 is a tunable heuristic (roughly: at least a third of the
    question's meaningful tokens appear somewhere in the article's
    title/category/subcategory/content) chosen to avoid surfacing dozens of
    low-quality/noisy matches.
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
        print("RELATED KB ARTICLE SEARCH ERROR:", error)
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    scored_results = []
    for article in articles:
        score = calculate_article_match_score(question, article)

        if min_score <= score < 1.0:
            scored_results.append(build_article_ai_result(article, question, score))

    scored_results = sorted(scored_results, key=lambda item: item.get("score", 0.0), reverse=True)

    return scored_results[:limit]


def build_article_search_segments(article):
    """
    Split an article into independently-scorable text segments for the
    related-knowledge search above: title/category/subcategory as one
    segment, then each numbered step (parsed the same way parse_article_steps
    already does for rendering) as its own segment, plus any free-text lead-in
    before the first numbered step (e.g. a "Stocktake:" sub-heading). A query
    is scored against whichever ONE segment matches best, so a long multi-step
    SOP isn't penalized for containing many OTHER unrelated steps.
    """
    title = str(article.get("title") or "")
    category = str(article.get("category") or "")
    sub_category = str(article.get("sub_category") or "")
    raw_content = article.get("content")
    plain_content = normalize_article_html_for_parsing(raw_content)

    segments = [f"{title} {category} {sub_category}"]

    # parse_article_steps() normalizes internally too (redundant but
    # idempotent/harmless); the lead-in slice below needs to search the SAME
    # normalized plain text so its offsets line up with real content.
    steps = parse_article_steps(raw_content)

    if steps:
        first_step_match = re.search(
            r"(?:^|\n)\s*(?:step\s*)?\d+\s*[\).:-]", plain_content, re.IGNORECASE
        )
        if first_step_match and first_step_match.start() > 0:
            lead_in = plain_content[:first_step_match.start()].strip()
            if lead_in:
                segments.append(lead_in)

        for step in steps:
            segments.append(str(step.get("answer") or step.get("content") or ""))
    else:
        segments.append(plain_content)

    return segments

def process_question(question, context=None, search_question=None):
    """
    `search_question` optionally overrides what drives KB/database/model
    retrieval below (e.g. English keywords derived from a Chinese/Malay
    `question` by translate_query_to_english_keywords()), while `question`
    itself is still what's echoed back, logged, and used to build/rank the
    selectable answer options. Defaults to `question` when not given, so
    existing callers behave exactly as before.
    """
    question = clean_question(question)
    context = normalize_context(context or {})
    search_term = clean_question(search_question) if search_question else question

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

    kb_result = search_knowledge_base_articles(search_term, limit=1)
    kb_options = search_knowledge_base_articles(search_term, limit=10)

    image_retrieval_result = search_image_retrieval(search_term, limit=1)

    if image_retrieval_result:
        image_retrieval_result = normalize_result(image_retrieval_result, "image_retrieval")

    image_retrieval_options = search_image_retrieval(search_term, limit=10)
    image_retrieval_options = [
        normalize_result(item, "image_retrieval")
        for item in image_retrieval_options
    ]

    retrieval_result = search_similar_question(search_term)

    if retrieval_result:
        retrieval_result = normalize_result(retrieval_result, "database")

    retrieval_options = search_similar_questions(search_term, team_lead_only=False, limit=10)
    retrieval_options = [
        normalize_result(item, "database")
        for item in retrieval_options
    ]

    model_result = None

    if MODEL_AVAILABLE and get_model_answer is not None:
        try:
            model_result = normalize_result(
                call_model_answer(search_term, context=context),
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
    """Legacy no-op: password migration occurs only after successful login."""
    return None


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
@app.route("/api/health", methods=["GET"])
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
def ensure_declined_registration_history_table(cursor):
    """Keep a permanent application snapshot without duplicating users or passwords.

    Called *before* starting the registration transaction: MySQL DDL commits
    implicitly, so CREATE TABLE must never run between the account row lock
    and the final UPDATE/INSERT.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS declined_registration_history (
            history_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            full_name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL,
            originally_registered_at DATETIME NULL,
            declined_at DATETIME NULL,
            declined_by_user_id INT NULL,
            declined_by_name VARCHAR(255) NULL,
            decision_description TEXT NULL,
            archived_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_declined_history_user (user_id),
            INDEX idx_declined_history_email (email)
        ) ENGINE=InnoDB
    """)


@app.route("/api/auth/register", methods=["POST"])
def register():
    """Create a pending account, or accept a fresh application after a decline.

    A declined attempt is archived before its existing user row is reused.
    Active, pending and inactive accounts still cannot register duplicates.
    """
    data = request.get_json(silent=True) or {}
    full_name = str(data.get("full_name") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    confirm_password = str(data.get("confirm_password") or "")

    if not all((full_name, email, password, confirm_password)):
        return jsonify({"message": "Please fill in all required fields."}), 400
    if len(full_name) < 3:
        return jsonify({"message": "Full name must be at least 3 characters."}), 400
    if not is_valid_email_format(email):
        return jsonify({"message": "Please enter a valid email address."}), 400
    if password != confirm_password:
        return jsonify({"message": "Passwords do not match."}), 400
    if len(password) < 8 or not re.search(r"[A-Z]", password) or not re.search(r"\d", password):
        return jsonify({"message": "Password must contain at least 8 characters, an uppercase letter and a number."}), 400

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Only a registration-specific table is created. Do this before BEGIN
        # because CREATE TABLE causes an implicit commit in MySQL.
        ensure_declined_registration_history_table(cursor)
        conn.start_transaction()
        cursor.execute("SELECT role_id FROM roles WHERE LOWER(role_name) = 'staff' LIMIT 1")
        role_row = cursor.fetchone()
        if not role_row:
            conn.rollback()
            return jsonify({"message": "Staff role does not exist in database."}), 500

        cursor.execute("""
            SELECT user_id, full_name, email, status, created_at
            FROM users WHERE LOWER(email) = %s LIMIT 1 FOR UPDATE
        """, (email,))
        existing = cursor.fetchone()
        new_password_hash = generate_password_hash(password)

        if existing and str(existing.get("status") or "").strip().lower() != "declined":
            conn.rollback()
            return jsonify({"message": "Email is already registered. Contact your Manager if you need assistance."}), 409

        if existing:
            # Preserve the actual earlier declined application BEFORE resetting
            # the one unique users row. Do not copy or retain old password hashes.
            user_id = existing["user_id"]
            cursor.execute("""
                SELECT actor_id, actor_name, description, created_at
                FROM audit_log
                WHERE action = 'Declined account registration'
                  AND module = 'User Management'
                  AND description LIKE %s
                ORDER BY created_at DESC, audit_id DESC LIMIT 1
            """, (f"User ID {user_id} registration declined.%",))
            decision = cursor.fetchone() or {}
            cursor.execute("""
                INSERT INTO declined_registration_history
                    (user_id, full_name, email, originally_registered_at,
                     declined_at, declined_by_user_id, declined_by_name,
                     decision_description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id, existing["full_name"], existing["email"],
                existing.get("created_at"), decision.get("created_at"),
                decision.get("actor_id"), decision.get("actor_name"),
                decision.get("description") or "Legacy decline; see audit history.",
            ))
            # An old reset link issued before the original decline must not
            # reset the fresh password after this person is later approved.
            cursor.execute("SHOW TABLES LIKE 'password_reset_tokens'")
            if cursor.fetchone():
                cursor.execute("""
                    UPDATE password_reset_tokens SET used_at = NOW()
                    WHERE user_id = %s AND used_at IS NULL
                """, (user_id,))
            cursor.execute("""
                UPDATE users
                SET full_name = %s, email = %s, password_hash = %s,
                    role_id = %s, status = 'pending', created_at = NOW()
                WHERE user_id = %s AND status = 'declined'
            """, (full_name, email, new_password_hash, role_row["role_id"], user_id))
            if cursor.rowcount != 1:
                conn.rollback()
                return jsonify({"message": "Registration changed while processing. Please try again."}), 409
        else:
            cursor.execute("""
                INSERT INTO users (full_name, email, password_hash, role_id, status)
                VALUES (%s, %s, %s, %s, 'pending')
            """, (full_name, email, new_password_hash, role_row["role_id"]))
            user_id = cursor.lastrowid

        # The historical record and new pending application commit together.
        conn.commit()
        # Notifications and audit logging run after commit. A notification failure
        # must never erase a successfully submitted pending registration.
        notify_registration_approvers(user_id, full_name, email)
        add_audit_log(
            actor_id=user_id, actor_name=full_name,
            action="Submitted account registration", module="Authentication",
            description=f"Pending staff registration submitted for {email}; awaiting manager review."
        )
        return jsonify({
            "message": "Registration submitted. Please allow up to 24 hours for a Manager or Team Leader to review your request.",
            "account_status": "pending", "review_within_hours": 24,
        }), 201
    except mysql.connector.IntegrityError:
        if conn:
            conn.rollback()
        return jsonify({"message": "Email is already registered."}), 409
    except Exception:
        if conn:
            conn.rollback()
        print("REGISTER ERROR: Registration transaction failed.")
        return jsonify({"message": "Unable to complete registration right now."}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# AUTH - FORGOT / RESET PASSWORD
# =========================
@app.route("/api/auth/forgot-password", methods=["POST"])
def forgot_password():
    # Email-based recovery is still supported only where the mailbox is real.
    # Do not simulate delivery or silently issue an unusable reset token.
    if (PRESENTATION_DEMO_MODE or not os.getenv("SMTP_USER", "").strip()
            or not os.getenv("SMTP_PASSWORD", "").strip()):
        return jsonify({
            "code": "PASSWORD_RECOVERY_UNAVAILABLE",
            "message": "Password recovery is currently unavailable. Please contact your Manager."
        }), 503
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()

    # Use a generic response so this endpoint does not reveal whether an
    # account exists or what its current status is.
    generic_response = {
        "message": (
            "If this email belongs to an eligible Jungle House account, "
            "a password reset link will be sent shortly."
        )
    }

    if not email or not is_valid_email_format(email):
        return jsonify(generic_response), 200

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)
        ensure_password_reset_tokens_table(cursor)

        cursor.execute("""
            SELECT user_id, full_name, email, status
            FROM users
            WHERE LOWER(email) = %s
            LIMIT 1
        """, (email,))
        user = cursor.fetchone()

        # Active users and pending registrations may reset their password.
        # Declined/inactive accounts receive the same generic HTTP response,
        # but no reset token/email is created.
        if not user or str(user.get("status", "")).strip().lower() not in {"active", "pending"}:
            conn.rollback()
            return jsonify(generic_response), 200

        # Basic resend cooldown to reduce accidental email spam.
        cursor.execute("""
            SELECT created_at
            FROM password_reset_tokens
            WHERE user_id = %s
            ORDER BY created_at DESC, reset_id DESC
            LIMIT 1
        """, (user["user_id"],))
        latest = cursor.fetchone()
        latest_created = latest.get("created_at") if isinstance(latest, dict) and latest else None

        if latest_created:
            age_seconds = (datetime.now() - latest_created).total_seconds()
            if age_seconds < PASSWORD_RESET_COOLDOWN_SECONDS:
                conn.rollback()
                return jsonify(generic_response), 200

        raw_token = create_password_reset_token(cursor, user["user_id"])
        conn.commit()

        email_sent = send_password_reset_email(
            user.get("full_name"),
            user.get("email"),
            raw_token,
        )

        # Keep the public response generic; server logs still show SMTP errors.
        add_audit_log(
            actor_id=user["user_id"],
            actor_name=user.get("full_name") or "User",
            action="Requested password reset",
            module="Authentication",
            description=(
                f"Password reset requested for {email}; email delivery="
                f"{'sent' if email_sent else 'failed'}"
            )
        )

        return jsonify(generic_response), 200

    except Exception as error:
        if conn:
            conn.rollback()
        print("FORGOT PASSWORD ERROR:", error)
        # Do not leak internal details or account existence.
        return jsonify(generic_response), 200

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/auth/reset-password/validate", methods=["GET"])
def validate_password_reset_token():
    raw_token = str(request.args.get("token", "")).strip()

    if not raw_token:
        return jsonify({"valid": False, "message": "Password reset link is invalid or expired."}), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_password_reset_tokens_table(cursor)

        cursor.execute("""
            SELECT prt.reset_id, u.status
            FROM password_reset_tokens prt
            JOIN users u ON prt.user_id = u.user_id
            WHERE prt.token_hash = %s
              AND prt.used_at IS NULL
              AND prt.expires_at > NOW()
            LIMIT 1
        """, (hash_password_reset_token(raw_token),))
        token_row = cursor.fetchone()

        valid = bool(
            token_row
            and str(token_row.get("status", "")).strip().lower() in {"active", "pending"}
        )

        if not valid:
            return jsonify({"valid": False, "message": "Password reset link is invalid or expired."}), 400

        return jsonify({"valid": True, "message": "Password reset link is valid."}), 200

    except Exception as error:
        print("VALIDATE PASSWORD RESET ERROR:", error)
        return jsonify({"valid": False, "message": "Unable to validate this reset link."}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/auth/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or {}

    raw_token = str(data.get("token", "")).strip()
    new_password = str(data.get("new_password", ""))
    confirm_password = str(data.get("confirm_password", ""))

    if not raw_token or not new_password or not confirm_password:
        return jsonify({"message": "Reset token and both password fields are required."}), 400

    if new_password != confirm_password:
        return jsonify({"message": "Passwords do not match."}), 400

    if len(new_password) < 8:
        return jsonify({"message": "Password must be at least 8 characters."}), 400

    if not re.search(r"[A-Z]", new_password):
        return jsonify({"message": "Password must include at least one uppercase letter."}), 400

    if not re.search(r"\d", new_password):
        return jsonify({"message": "Password must include at least one number."}), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)
        ensure_password_reset_tokens_table(cursor)

        token_hash = hash_password_reset_token(raw_token)

        cursor.execute("""
            SELECT
                prt.reset_id,
                prt.user_id,
                prt.expires_at,
                prt.used_at,
                u.full_name,
                u.email,
                u.status
            FROM password_reset_tokens prt
            JOIN users u ON prt.user_id = u.user_id
            WHERE prt.token_hash = %s
            LIMIT 1
            FOR UPDATE
        """, (token_hash,))
        token_row = cursor.fetchone()

        if not token_row:
            conn.rollback()
            return jsonify({"message": "Password reset link is invalid or expired."}), 400

        if token_row.get("used_at"):
            conn.rollback()
            return jsonify({"message": "This password reset link has already been used."}), 409

        expires_at = token_row.get("expires_at")
        if not expires_at or datetime.now() >= expires_at:
            conn.rollback()
            return jsonify({"message": "Password reset link has expired. Please request a new one."}), 400

        if str(token_row.get("status", "")).strip().lower() not in {"active", "pending"}:
            conn.rollback()
            return jsonify({"message": "This account is not eligible for password reset."}), 403

        cursor.execute("""
            UPDATE users
            SET password_hash = %s
            WHERE user_id = %s
        """, (generate_password_hash(new_password), token_row["user_id"]))

        # Consume this link and invalidate any other outstanding reset links.
        cursor.execute("""
            UPDATE password_reset_tokens
            SET used_at = NOW()
            WHERE user_id = %s
              AND used_at IS NULL
        """, (token_row["user_id"],))

        conn.commit()

        create_notification_safe(
            user_id=token_row["user_id"],
            title="Password changed",
            detail="Your Jungle House AI Wiki password was reset successfully.",
            notification_type="system",
            related_id=token_row["user_id"]
        )

        add_audit_log(
            actor_id=token_row["user_id"],
            actor_name=token_row.get("full_name") or "User",
            action="Reset account password",
            module="Authentication",
            description=f"Password reset completed for {token_row.get('email')}."
        )

        return jsonify({
            "message": "Password updated successfully. You can now sign in with your new password."
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()
        print("RESET PASSWORD ERROR:", error)
        return jsonify({"message": "Unable to reset the password right now."}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



# =========================
# REGISTRATION KEY ROUTES
# =========================

def send_registration_activation_email(full_name, email, key_code):
    """Legacy compatibility only: activation-key emails are permanently disabled."""
    return False

@app.route("/api/registration-keys/generate", methods=["POST"])
def generate_registration_key():
    return jsonify({"code": "REGISTRATION_KEYS_REMOVED", "message": "Registration keys are no longer required. Contact your Manager for account approval."}), 410

@app.route("/api/registration-keys", methods=["GET"])
def list_registration_keys():
    return jsonify({"code": "REGISTRATION_KEYS_REMOVED", "message": "Registration keys are no longer required. Contact your Manager for account approval."}), 410



@app.route("/api/registration-keys/<int:key_id>/resend", methods=["POST"])
def resend_registration_key(key_id):
    return jsonify({"code": "REGISTRATION_KEYS_REMOVED", "message": "Registration keys are no longer required. Contact your Manager for account approval."}), 410



@app.route("/api/registration-keys/<int:key_id>/revoke", methods=["PUT"])
def revoke_registration_key(key_id):
    return jsonify({"code": "REGISTRATION_KEYS_REMOVED", "message": "Registration keys are no longer required. Contact your Manager for account approval."}), 410

# =========================
# AUTH - LOGIN
# =========================
@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    if not email or not password:
        return jsonify({"message": "Email and password are required."}), 400
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.user_id, u.full_name, u.email, u.password_hash,
                   u.status, u.created_at, r.role_name
            FROM users u JOIN roles r ON u.role_id = r.role_id
            WHERE LOWER(u.email) = %s LIMIT 1
        """, (email,))
        user = cursor.fetchone()
        if not user:
            record_login_history(cursor, email=email, full_name="Unknown", status="failed")
            conn.commit()
            return jsonify({"message": "Invalid email or password."}), 401
        stored = str(user.get("password_hash") or "")
        try:
            password_ok = check_password_hash(stored, password)
        except Exception:
            password_ok = False
        if not password_ok and hmac.compare_digest(stored, password):
            stored = generate_password_hash(password)  # Upgrade legacy plaintext on login.
            cursor.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (stored, user["user_id"]))
            password_ok = True
        if not password_ok:
            record_login_history(cursor, user["user_id"], user["email"], user["full_name"], "failed")
            conn.commit()
            return jsonify({"message": "Invalid email or password."}), 401
        status = str(user.get("status") or "").lower()
        if status != "active":
            record_login_history(cursor, user["user_id"], user["email"], user["full_name"], "failed")
            conn.commit()
            code = "ACCOUNT_PENDING_APPROVAL" if status == "pending" else "ACCOUNT_INACTIVE"
            message = ("Your registration is awaiting Manager / Team Leader approval. Please allow up to 24 hours."
                       if status == "pending" else "This account is not active. Please contact your Manager or Team Leader.")
            return jsonify({"code": code, "account_status": status, "message": message}), 403
        record_login_history(cursor, user["user_id"], user["email"], user["full_name"], "success")
        conn.commit()
        session.clear()  # Rotate the session on login; prevent session fixation.
        session.permanent = True
        session["user_id"] = int(user["user_id"])
        session["password_fingerprint"] = password_session_fingerprint(stored)
        session["csrf_token"] = secrets.token_urlsafe(32)
        payload = get_user_profile_payload(user)
        response = jsonify({
            "message": "Login successful.", "user": payload,
            "csrf_token": session["csrf_token"],
        })
        response.headers["Cache-Control"] = "no-store"
        return response, 200
    except Exception:
        if conn:
            conn.rollback()
        print("LOGIN ERROR: Sign-in transaction failed.")
        return jsonify({"message": "Unable to sign in right now."}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# AUTH - REGISTRATION KEY ACTIVATION
# =========================
@app.route("/api/auth/activate-registration-key", methods=["POST"])
def activate_registration_key():
    return jsonify({"code": "REGISTRATION_KEYS_REMOVED", "message": "Registration keys are no longer required. Contact your Manager for account approval."}), 410



@app.route("/api/auth/resend-activation-key", methods=["POST"])
def resend_activation_key():
    return jsonify({"code": "REGISTRATION_KEYS_REMOVED", "message": "Registration keys are no longer required. Contact your Manager for account approval."}), 410

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
        session["password_fingerprint"] = password_session_fingerprint(new_hash)

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
# DASHBOARD / NOTIFICATION READS
# =========================
_notification_user_reads_ready = False

def ensure_notification_user_reads_table(cursor):
    """Set up individual read receipts for shared announcements, if needed.

    Do not alter the existing notification rows: their is_read column remains
    the read status for individually addressed notifications only. A separate
    receipt is needed because a shared row has no single recipient.
    """
    global _notification_user_reads_ready
    if _notification_user_reads_ready:
        return
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_user_reads (
            notification_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            read_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (notification_id, user_id),
            INDEX idx_notification_user_reads_user_id (user_id)
        ) ENGINE=InnoDB
    """)
    _notification_user_reads_ready = True


def load_visible_notifications(cursor, viewer_id, viewer_role):
    """Return one viewer's notifications and individual read statuses.

    Private notifications use notification.is_read as before. Shared notices
    use a separate read receipt, so one staff member cannot mark another's
    notice as read. The dashboard and Notifications page share this helper.
    """
    ensure_notification_user_reads_table(cursor)
    normalized_role = str(viewer_role or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    cursor.execute("""
        SELECT n.notification_id AS id, n.title, n.detail,
               CASE
                   WHEN n.user_id IS NULL THEN (nur.notification_id IS NOT NULL)
                   ELSE COALESCE(n.is_read, 0)
               END AS isRead,
               n.type, n.related_id, n.target_role, n.created_by, n.created_at
        FROM notification AS n
        LEFT JOIN notification_user_reads AS nur
          ON nur.notification_id = n.notification_id AND nur.user_id = %s
        WHERE n.user_id = %s
           OR (n.user_id IS NULL AND (
                n.target_role IS NULL
                OR LOWER(REPLACE(REPLACE(REPLACE(n.target_role, ' ', ''), '_', ''), '-', ''))
                   IN (%s, 'all')
           ))
        ORDER BY n.created_at DESC, n.notification_id DESC
    """, (viewer_id, viewer_id, normalized_role))
    return cursor.fetchall() or []


@app.route("/api/dashboard", methods=["GET"])
def get_dashboard():
    """Return role-appropriate dashboard data for the authenticated account."""
    conn = None
    cursor = None

    # Auth middleware loads this identity from the database-backed Flask session.
    viewer_id = int(g.auth_user["user_id"])
    viewer_role = str(g.auth_user.get("role_name") or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    can_view_management_metrics = viewer_role in {"manager", "admin", "teamlead"}
    is_manager = viewer_role in {"manager", "admin"}

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        articles = safe_count_query(cursor, "SELECT COUNT(*) AS total FROM wiki_article")

        # Use the exact same visible rows and read flags as the Notifications page.
        # Counting a separate SQL query previously caused dashboard/page mismatches.
        visible_notifications = load_visible_notifications(cursor, viewer_id, viewer_role)
        notifications_count = sum(
            1 for item in visible_notifications
            if item.get("isRead") not in (True, 1, "1")
        )

        stats = [
            {"label": "Knowledge Articles", "value": articles},
        ]

        if can_view_management_metrics:
            # The AI question log may not exist on a fresh installation.
            cursor.execute("SHOW TABLES LIKE 'ai_chat_log'")
            questions = (
                safe_count_query(
                    cursor,
                    "SELECT COUNT(*) AS total FROM ai_chat_log "
                    "WHERE question IS NOT NULL AND TRIM(question) <> '' "
                    "AND created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)",
                )
                if cursor.fetchone() else 0
            )
            escalations = safe_count_query(
                cursor, "SELECT COUNT(*) AS total FROM escalation WHERE status = 'pending'"
            )
            stats.extend([
                {"label": "Questions This Week", "value": questions},
                {"label": "Pending Escalations", "value": escalations},
            ])

        stats.append({"label": "Unread Notifications", "value": notifications_count})

        recent_notifications = visible_notifications[:3]

        if is_manager:
            # Managers already have permission to see the system audit log.
            activities = safe_list_query(cursor, """
                SELECT action, created_at FROM audit_log
                ORDER BY created_at DESC LIMIT 3
            """)
        else:
            # Staff and Team Leaders see their own events, not colleagues' logs.
            activities = safe_list_query(cursor, """
                SELECT action, created_at FROM audit_log
                WHERE actor_id = %s
                ORDER BY created_at DESC LIMIT 3
            """, (viewer_id,))

        payload = {
            "stats": stats,
            "notifications": recent_notifications,
            "activities": activities,
        }

        if can_view_management_metrics:
            ai_conf = 0
            try:
                cursor.execute("SELECT ROUND(AVG(confidence), 2) AS avg_conf FROM ai_response")
                result = cursor.fetchone()
                if result and result["avg_conf"] is not None:
                    ai_conf = result["avg_conf"]
            except Exception:
                ai_conf = 0
            payload["ai"] = {"accuracy": f"{ai_conf * 100:.0f}%"}

        response = jsonify(payload)
        response.headers["Cache-Control"] = "no-store"
        return response, 200

    except Exception as error:
        print("DASHBOARD ERROR:", error)
        return jsonify({"error": "Unable to load dashboard."}), 500

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

        # The session middleware has verified that user_id belongs to this viewer.
        # Apply the same recipient/role scope used by the dashboard.
        notifications = load_visible_notifications(
            cursor, user_id, g.auth_user.get("role_name")
        )
        response = jsonify(notifications)
        response.headers["Cache-Control"] = "no-store"
        return response, 200

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
        viewer_id = current_auth_user_id()
        normalized_role = str(g.auth_user.get("role_name") or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_notification_user_reads_table(cursor)

        # Match the GET/dashboard visibility rule exactly. Previously, any
        # authenticated staff member could mark an unrelated shared row read.
        cursor.execute("""
            SELECT user_id
            FROM notification
            WHERE notification_id = %s
              AND (user_id = %s OR (user_id IS NULL AND (
                   target_role IS NULL
                   OR LOWER(REPLACE(REPLACE(REPLACE(target_role, ' ', ''), '_', ''), '-', ''))
                      IN (%s, 'all')
              )))
            LIMIT 1
        """, (notification_id, viewer_id, normalized_role))
        visible_notification = cursor.fetchone()
        if not visible_notification:
            conn.rollback()
            return jsonify({"message": "Notification not found."}), 404

        if visible_notification["user_id"] is None:
            # Atomic and repeatable: only this viewer gets a read receipt.
            # Never set the shared notification row's global is_read flag.
            cursor.execute("""
                INSERT INTO notification_user_reads (notification_id, user_id)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE read_at = read_at
            """, (notification_id, viewer_id))
        else:
            # Preserve existing behaviour for one-recipient notifications.
            # Treat a second Mark read as success rather than an artificial 404.
            cursor.execute("""
                UPDATE notification SET is_read = TRUE
                WHERE notification_id = %s AND user_id = %s
            """, (notification_id, viewer_id))

        conn.commit()
        response = jsonify({"message": "Notification marked as read."})
        response.headers["Cache-Control"] = "no-store"
        return response, 200

    except mysql.connector.Error:
        if conn:
            conn.rollback()
        print("READ NOTIFICATION MYSQL ERROR: Could not update notification")
        return jsonify({"message": "Unable to mark notification as read."}), 500

    except Exception:
        if conn:
            conn.rollback()
        print("READ NOTIFICATION ERROR: Could not update notification")
        return jsonify({"message": "Unable to mark notification as read."}), 500

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

    actor_id = current_auth_user_id()
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

        # The write above already succeeded and is permanent -- nothing
        # past this point should be able to turn it into a reported
        # "failed to save". add_audit_log() already swallows its own
        # errors, but the config read-back could still theoretically fail
        # (stale cursor, etc.), so it gets its own safety net instead of
        # sharing the outer except block.
        add_audit_log(
            actor_id=actor_id,
            action="Updated AI provider settings",
            module="AI Settings",
            description=f"Active AI provider set to {provider} ({model_name})."
        )

        try:
            config = ai_provider_service.get_ai_provider_public_config(cursor)
        except Exception as read_back_error:
            print("AI SETTINGS SAVED BUT READ-BACK FAILED:", read_back_error)
            config = None

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

    actor_id = current_auth_user_id()
    provider = str(data.get("provider", "")).strip().lower()
    model_name = str(data.get("model_name", "")).strip()
    api_key = str(data.get("api_key", "")).strip()

    conn = None
    cursor = None

    # Step 1: open the DB only long enough to check permissions and load
    # whichever config we're about to test, then close it immediately.
    # The actual provider call below can take up to ~90s (a slow/hanging
    # external API) -- holding a MySQL connection open and idle for that
    # whole time risks it going stale, which previously caused a confusing
    # second failure (a DB error) to mask the real, already-classified
    # provider error (timeout/429/404/etc.) with a generic message instead.
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

    except Exception as error:
        print("TEST AI SETTINGS ERROR:", error)

        return jsonify({
            "success": False,
            "message": "Failed to load AI settings for testing."
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    # Step 2: the actual (potentially slow) external call, with no DB
    # connection held open in the background.
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

    # Step 3: a fresh, short-lived DB connection just to record the result.
    # If this part fails, the manager still sees the real test result above
    # -- only the "last tested" record-keeping is affected.
    if testing_saved_config:
        write_conn = None
        write_cursor = None

        try:
            write_conn = ai_provider_service.get_db_connection()
            write_cursor = write_conn.cursor(dictionary=True)
            ai_provider_service.update_active_provider_test_status(write_cursor, success)
            write_conn.commit()
        except Exception as error:
            print("TEST AI SETTINGS: failed to record test status:", error)
        finally:
            if write_cursor:
                write_cursor.close()
            if write_conn:
                write_conn.close()

    return jsonify({"success": success, "message": message}), (200 if success else 400)


# =========================
# NOTION SYNC ROUTES (OAuth "Connect Notion" flow)
#
# Reuses the exact same encryption service already built for AI provider
# keys (ai_provider_service.encrypt_api_key/decrypt_api_key/mask_api_key)
# instead of a second encryption scheme, and the same manager-only access
# check pattern used everywhere else in this file. The OAuth callback is the
# one exception: Notion redirects the browser there directly (no auth
# header, no JSON body possible), so it authenticates via possession of the
# one-time `state` token instead -- that state was only ever handed out to
# an already-manager-authenticated actor by /oauth/start.
# =========================
def _notify_managers_of_notion_update(cursor, title, article_id, actor_id):
    cursor.execute("""
        SELECT u.user_id
        FROM users u
        JOIN roles r ON u.role_id = r.role_id
        WHERE r.role_name = 'manager' AND u.status = 'active'
    """)
    managers = cursor.fetchall() or []

    for manager in managers:
        manager_id = manager["user_id"] if isinstance(manager, dict) else manager[0]
        create_notification_safe(
            user_id=manager_id,
            title="Notion content changed",
            detail=f'"{title}" was edited in Notion. Review it in Notion Sync to update or keep the current version.',
            notification_type="system",
            related_id=article_id,
            created_by=actor_id,
        )


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


@app.route("/api/notion-sync/oauth/start", methods=["POST"])
def start_notion_oauth():
    if not NOTION_SYNC_SERVICE_AVAILABLE:
        return jsonify({"success": False, "message": "Notion sync service is not available on this server."}), 500

    if not os.getenv("NOTION_OAUTH_CLIENT_ID") or not os.getenv("NOTION_OAUTH_CLIENT_SECRET"):
        return jsonify({
            "success": False,
            "message": "Notion OAuth is not configured on the server yet. Set NOTION_OAUTH_CLIENT_ID and NOTION_OAUTH_CLIENT_SECRET."
        }), 500

    data = request.get_json(silent=True) or {}
    actor_id = data.get("user_id")

    conn = None
    cursor = None

    try:
        conn = notion_sync_service.get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        notion_sync_service.ensure_notion_sync_tables(cursor)

        if not is_ai_settings_manager(cursor, actor_id):
            conn.rollback()
            return jsonify({"success": False, "message": "Only managers can connect Notion."}), 403

        state = notion_sync_service.create_oauth_state(cursor, actor_id)
        conn.commit()

        redirect_uri = f"{notion_sync_service.get_public_base_url()}/api/notion-sync/oauth/callback"
        authorize_url = notion_sync_service.build_authorize_url(redirect_uri, state)

        return jsonify({"success": True, "authorizeUrl": authorize_url}), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("START NOTION OAUTH ERROR:", error)
        return jsonify({"success": False, "message": "Failed to start Notion connection."}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _render_notion_oauth_result_page(status, detail=""):
    """
    Notion redirects the browser here directly, so this can't just return
    JSON. Connect Notion opens this callback in a popup window (see
    NotionSync.jsx), so the primary path posts the result back to the
    window that opened the popup and closes it -- the admin never leaves
    the Notion Sync page. If there's no opener (popup blocked, or the
    callback URL was opened directly), it falls back to a normal redirect
    to the Notion Sync page with the old ?connected=1 / ?error=... params.
    """
    query_param = f"connected=1" if status == "connected" else f"error={detail or 'connection_failed'}"
    fallback_url = f"{FRONTEND_URL}/admin/notion-sync?{query_param}"
    message = "Notion connected successfully. You can close this window." if status == "connected" else f"Notion connection failed: {(detail or 'connection_failed').replace('_', ' ')}"

    html = f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>Notion Sync</title></head>
<body style="font-family: sans-serif; padding: 2rem; color: #222;">
<p>{message}</p>
<script>
(function() {{
  var payload = {{ source: "jungle-house-notion-oauth", status: "{status}", detail: "{detail}" }};
  try {{
    if (window.opener && !window.opener.closed) {{
      window.opener.postMessage(payload, "{FRONTEND_URL}");
      window.close();
      return;
    }}
  }} catch (e) {{}}
  window.location.href = "{fallback_url}";
}})();
</script>
</body>
</html>"""
    return html


@app.route("/api/notion-sync/oauth/callback", methods=["GET"])
def notion_oauth_callback():
    if not NOTION_SYNC_SERVICE_AVAILABLE:
        return _render_notion_oauth_result_page("error", "service_unavailable")

    code = request.args.get("code")
    state = request.args.get("state")

    if not code or not state:
        return _render_notion_oauth_result_page("error", "missing_code_or_state")

    conn = None
    cursor = None

    try:
        conn = notion_sync_service.get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        notion_sync_service.ensure_notion_sync_tables(cursor)

        actor_id = notion_sync_service.consume_oauth_state(cursor, state)
        conn.commit()

        if not actor_id:
            return _render_notion_oauth_result_page("error", "invalid_or_expired_state")

        redirect_uri = f"{notion_sync_service.get_public_base_url()}/api/notion-sync/oauth/callback"
        token_response = notion_sync_service.exchange_oauth_code_for_token(code, redirect_uri)

        access_token = token_response.get("access_token")
        workspace_id = token_response.get("workspace_id")
        workspace_name = token_response.get("workspace_name") or "Notion workspace"
        workspace_icon = token_response.get("workspace_icon")
        bot_id = token_response.get("bot_id")

        if not access_token:
            return _render_notion_oauth_result_page("error", "token_exchange_failed")

        conn2 = notion_sync_service.get_db_connection()
        cursor2 = conn2.cursor(dictionary=True)
        notion_sync_service.save_notion_oauth_config(
            cursor2, access_token, workspace_id, workspace_name, workspace_icon, bot_id, actor_id
        )
        conn2.commit()
        cursor2.close()
        conn2.close()

        add_audit_log(
            actor_id=actor_id,
            action="Connected Notion workspace",
            module="Notion Sync",
            description=f"Connected workspace: {workspace_name}."
        )

        return _render_notion_oauth_result_page("connected")

    except Exception as error:
        if conn:
            conn.rollback()

        print("NOTION OAUTH CALLBACK ERROR:", error)
        return _render_notion_oauth_result_page("error", "connection_failed")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/notion-sync/disconnect", methods=["POST"])
def disconnect_notion_sync():
    if not NOTION_SYNC_SERVICE_AVAILABLE:
        return jsonify({"success": False, "message": "Notion sync service is not available on this server."}), 500

    data = request.get_json(silent=True) or {}
    actor_id = data.get("user_id")

    conn = None
    cursor = None

    try:
        conn = notion_sync_service.get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        notion_sync_service.ensure_notion_sync_tables(cursor)

        if not is_ai_settings_manager(cursor, actor_id):
            conn.rollback()
            return jsonify({"success": False, "message": "Only managers can disconnect Notion."}), 403

        notion_sync_service.disconnect_notion(cursor)
        conn.commit()

        add_audit_log(
            actor_id=actor_id,
            action="Disconnected Notion workspace",
            module="Notion Sync",
            description="Notion workspace disconnected."
        )

        return jsonify({"success": True, "message": "Notion disconnected."}), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("DISCONNECT NOTION SYNC ERROR:", error)
        return jsonify({"success": False, "message": "Failed to disconnect Notion."}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/notion-sync/check", methods=["POST"])
def check_notion_sync():
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
            return jsonify({"success": False, "message": "Only managers can check for Notion updates."}), 403

        raw_token = notion_sync_service.get_active_notion_access_token(cursor)

        if not raw_token:
            return jsonify({"success": False, "message": "No Notion workspace is connected yet."}), 400

    except Exception as error:
        print("CHECK NOTION SYNC SETUP ERROR:", error)
        return jsonify({"success": False, "message": "Failed to start checking Notion for updates."}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    result = notion_sync_service.check_for_notion_updates(raw_token, actor_id, UPLOAD_FOLDER)

    if result.get("flaggedItems"):
        notify_conn = None
        notify_cursor = None
        try:
            notify_conn = notion_sync_service.get_db_connection()
            notify_cursor = notify_conn.cursor(dictionary=True)
            for item in result["flaggedItems"]:
                _notify_managers_of_notion_update(
                    notify_cursor, item["title"], item["article_id"], actor_id
                )
            notify_conn.commit()
        except Exception as notify_error:
            print("NOTION UPDATE NOTIFICATION ERROR:", notify_error)
        finally:
            if notify_cursor:
                notify_cursor.close()
            if notify_conn:
                notify_conn.close()

    add_audit_log(
        actor_id=actor_id,
        action="Checked Notion for updates",
        module="Notion Sync",
        description=f"New {result['new']}, flagged {result['flagged']}, unchanged {result['unchanged']}, failed {result['failed']}."
    )

    return jsonify({"success": result["status"] == "completed", **result}), 200


@app.route("/api/notion-sync/pending-updates", methods=["GET"])
def get_notion_pending_updates():
    if not NOTION_SYNC_SERVICE_AVAILABLE:
        return jsonify({"success": False, "message": "Notion sync service is not available on this server."}), 500

    conn = None
    cursor = None

    try:
        conn = notion_sync_service.get_db_connection()
        cursor = conn.cursor(dictionary=True)

        notion_sync_service.ensure_notion_sync_tables(cursor)
        pending = notion_sync_service.list_pending_updates(cursor)

        return jsonify({"success": True, "pending": pending}), 200

    except Exception as error:
        print("GET NOTION PENDING UPDATES ERROR:", error)
        return jsonify({"success": False, "message": "Failed to load pending Notion updates."}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/notion-sync/pending-updates/<int:pending_id>/apply", methods=["POST"])
def apply_notion_pending_update(pending_id):
    if not NOTION_SYNC_SERVICE_AVAILABLE:
        return jsonify({"success": False, "message": "Notion sync service is not available on this server."}), 500

    data = request.get_json(silent=True) or {}
    actor_id = data.get("user_id")

    conn = None
    cursor = None

    try:
        conn = notion_sync_service.get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        notion_sync_service.ensure_notion_sync_tables(cursor)

        if not is_ai_settings_manager(cursor, actor_id):
            conn.rollback()
            return jsonify({"success": False, "message": "Only managers can approve Notion updates."}), 403

        applied = notion_sync_service.apply_pending_update(cursor, pending_id, actor_id)

        if not applied:
            conn.rollback()
            return jsonify({"success": False, "message": "This update was already resolved."}), 409

        conn.commit()

        add_audit_log(
            actor_id=actor_id,
            action="Applied Notion update",
            module="Notion Sync",
            description=f"Applied pending Notion update #{pending_id}."
        )

        return jsonify({"success": True, "message": "Article updated to the latest Notion version."}), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("APPLY NOTION PENDING UPDATE ERROR:", error)
        return jsonify({"success": False, "message": "Failed to apply this update."}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/notion-sync/pending-updates/<int:pending_id>/dismiss", methods=["POST"])
def dismiss_notion_pending_update(pending_id):
    if not NOTION_SYNC_SERVICE_AVAILABLE:
        return jsonify({"success": False, "message": "Notion sync service is not available on this server."}), 500

    data = request.get_json(silent=True) or {}
    actor_id = data.get("user_id")

    conn = None
    cursor = None

    try:
        conn = notion_sync_service.get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        notion_sync_service.ensure_notion_sync_tables(cursor)

        if not is_ai_settings_manager(cursor, actor_id):
            conn.rollback()
            return jsonify({"success": False, "message": "Only managers can dismiss Notion updates."}), 403

        dismissed = notion_sync_service.dismiss_pending_update(cursor, pending_id, actor_id)

        if not dismissed:
            conn.rollback()
            return jsonify({"success": False, "message": "This update was already resolved."}), 409

        conn.commit()

        add_audit_log(
            actor_id=actor_id,
            action="Dismissed Notion update",
            module="Notion Sync",
            description=f"Kept current version over pending Notion update #{pending_id}."
        )

        return jsonify({"success": True, "message": "Kept the current version."}), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print("DISMISS NOTION PENDING UPDATE ERROR:", error)
        return jsonify({"success": False, "message": "Failed to dismiss this update."}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


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


def _notion_auto_sync_loop():
    """
    Background loop so new/edited Notion pages land in the Knowledge Base
    on their own, without a manager having to open Notion Sync and click
    "Check for Updates" every time. Runs in a single daemon thread inside
    the one gunicorn worker this service is deployed with (see
    backend/src/Procfile, --workers 1), so it never runs more than once
    concurrently. Safe to leave running with nothing connected -- it just
    checks the active token each cycle and no-ops when there isn't one.
    """
    interval_seconds = max(60, int(os.getenv("NOTION_AUTO_SYNC_INTERVAL_SECONDS", "300")))
    time.sleep(30)

    while True:
        try:
            conn = notion_sync_service.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            notion_sync_service.ensure_notion_sync_tables(cursor)
            token = notion_sync_service.get_active_notion_access_token(cursor)
            cursor.close()
            conn.close()

            if token:
                result = notion_sync_service.check_for_notion_updates(token, None, UPLOAD_FOLDER)

                if result.get("flaggedItems"):
                    notify_conn = notion_sync_service.get_db_connection()
                    notify_cursor = notify_conn.cursor(dictionary=True)
                    for item in result["flaggedItems"]:
                        _notify_managers_of_notion_update(
                            notify_cursor, item["title"], item["article_id"], None
                        )
                    notify_conn.commit()
                    notify_cursor.close()
                    notify_conn.close()

                if result.get("new") or result.get("flagged"):
                    add_audit_log(
                        actor_id=None,
                        actor_name="System",
                        action="Auto-checked Notion for updates",
                        module="Notion Sync",
                        description=f"New {result['new']}, flagged {result['flagged']}, unchanged {result['unchanged']}, failed {result['failed']}."
                    )
        except Exception as error:
            print("NOTION AUTO SYNC LOOP ERROR:", error)

        time.sleep(interval_seconds)


if NOTION_SYNC_SERVICE_AVAILABLE and os.getenv("NOTION_AUTO_SYNC_ENABLED", "true").strip().lower() == "true":
    import threading
    threading.Thread(target=_notion_auto_sync_loop, daemon=True).start()


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
def build_ai_chat_context(question, limit=5, max_chars=6000, search_question=None):
    """
    `search_question` optionally overrides what's used to SCORE/select
    articles (e.g. the English keywords derived from a Chinese/Malay
    question by translate_query_to_english_keywords()), while `question`
    stays whatever the caller wants echoed/logged. Defaults to `question`
    when not given, so existing callers are unaffected.
    """
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

    scoring_question = search_question if search_question else question

    scored_articles = []

    for article in articles:
        score = calculate_article_match_score(scoring_question, article)

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

    # Returned alongside the text blob so the caller can resolve whichever
    # article title the AI says it used back to a real article_id -- the
    # AI itself never sees or invents IDs, it only ever names a title from
    # what's already in the prompt above.
    candidate_articles = [
        {"article_id": article.get("article_id"), "title": article.get("title") or ""}
        for article in top_articles
    ]

    return "\n".join(chunks), candidate_articles


def answer_question_with_ai_provider(question, timeout=25, search_question=None, user_language="en"):
    """
    Returns {"answer": str, "sourceTitle": str, "article_id": int|None,
    "off_topic": bool} if the AI provider produced a usable reply (either a
    KB-grounded answer, or -- for non-English questions only -- a polite
    decline for off-topic banter), or None if it couldn't (in which case the
    caller should fall through to the normal escalation flow -- this
    function never forces an answer that isn't grounded, and never forces an
    escalation either).

    `search_question` is the English keyword string derived from a
    Chinese/Malay `question` by translate_query_to_english_keywords() --
    used only to look up Knowledge Base articles, since KB content and its
    matcher are English-only. Defaults to `question` when not given.

    `user_language` ("en" / "zh" / "ms") controls what language the final
    answer text is written in, and gives non-English off-topic questions
    (jokes, small talk) a path to a same-language decline instead of
    silently escalating to a Team Lead just because nothing matched.

    Uses a shorter timeout (25s) than generate_ai_reply()'s own 90s
    default on purpose: this runs inline while a staff member is actively
    waiting for a live chat reply, so it's better to give up sooner and
    escalate than to leave them staring at a spinner for a minute and a
    half every time the provider is having a slow moment. Quiz generation
    (a manager clicking a button, not a live conversation) keeps the
    longer default since waiting there is far less disruptive.
    """
    context_text, candidate_articles = build_ai_chat_context(question, search_question=search_question)

    # English behavior is unchanged from before: no KB context at all means
    # there's nothing to ground an answer in, so skip the AI call and let
    # the caller fall straight through to normal escalation. Non-English
    # questions still make this call even with empty context, purely so the
    # AI can tell -- in the user's own language -- genuine unanswered work
    # questions (still escalate) apart from off-topic banter (should not).
    if not context_text.strip() and user_language == "en":
        return None

    language_labels = {
        "zh": "Chinese (use the SAME Chinese variant -- Simplified or Traditional -- as the staff question)",
        "ms": "Bahasa Melayu",
        "en": "English",
    }
    language_label = language_labels.get(user_language, "the same language as the staff question")

    prompt = f"""You are Jungle House's internal AI Wiki Assistant.

Answer the staff question using ONLY the provided Knowledge Base context
below. Do not invent company rules, procedures, or information that is not
written in the context.

The staff question may be written in Chinese, Bahasa Melayu, or English.
You MUST reply strictly in {language_label} -- the same language the staff
question below is written in. Never switch languages, and never answer in
English if the question is not in English.

If the question is unrelated to Jungle House work (e.g. jokes, small talk,
greetings, general trivia -- something no Knowledge Base article could ever
answer), respond with ONLY this exact JSON and nothing else:
{{"answered": false, "off_topic": true, "declineMessage": "..."}}
("declineMessage" must be a short, polite decline written in {language_label}
that invites them to ask a work-related question instead.)

If the question IS a genuine work-related question but the answer is not
clearly found in the context, respond with ONLY this exact JSON:
{{"answered": false, "off_topic": false}}

If you can answer from the context, respond with ONLY valid JSON in this
exact shape (no markdown, no text outside the JSON):
{{"answered": true, "answer": "...", "sourceTitle": "..."}}

Keep the answer SHORT and direct -- one or two sentences maximum, stating
only the specific fact/step asked for. Do not add extra explanation,
preamble, or restate the question. "sourceTitle" must be copied exactly
from one of the "###" headings in the context below (empty string if there
is no context).

Staff question: {question}

Knowledge Base context:
{context_text if context_text.strip() else "(no matching Knowledge Base articles found)"}
"""

    raw_reply = ai_provider_service.generate_ai_reply(prompt, timeout=timeout)

    json_text = raw_reply.strip()
    json_text = re.sub(r"^```(?:json)?\s*", "", json_text)
    json_text = re.sub(r"\s*```$", "", json_text)

    parsed = json.loads(json_text)

    if not isinstance(parsed, dict):
        return None

    if not parsed.get("answered"):
        decline_message = str(parsed.get("declineMessage") or "").strip()

        if parsed.get("off_topic") and decline_message:
            return {
                "answer": decline_message,
                "sourceTitle": "",
                "article_id": None,
                "off_topic": True,
            }

        return None

    answer_text = str(parsed.get("answer") or "").strip()

    if not answer_text:
        return None

    source_title = str(parsed.get("sourceTitle") or "").strip()

    # Resolve the AI's claimed source title back to a real article_id by
    # matching against the candidates actually given to it -- the AI never
    # sees or makes up IDs itself, so a case-insensitive title match is the
    # only way to attach a clickable link safely. No match -> no link,
    # rather than guessing wrong.
    article_id = None
    for candidate in candidate_articles:
        if candidate["title"].strip().lower() == source_title.lower():
            article_id = candidate["article_id"]
            break

    return {
        "answer": answer_text,
        "sourceTitle": source_title,
        "article_id": article_id,
        "off_topic": False,
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

            data["user_id"] = current_auth_user_id()

            if uploaded_chat_image:
                uploaded_chat_image_url, uploaded_chat_image_type = save_chat_image(uploaded_chat_image)

                # Stashed on g so the after_request hook below can attach the
                # permanent saved URL to whichever response path this request
                # ends up taking (direct match / related options / rejection
                # / normal KB fallback) without having to touch every single
                # return statement in this route.
                if uploaded_chat_image_url:
                    g.uploaded_chat_image_url = uploaded_chat_image_url
                    g.uploaded_chat_image_type = uploaded_chat_image_type

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

                    # CLIP couldn't already answer confidently. Case B
                    # (image with no real question) still needs object
                    # detection to work -- so vision now always runs here,
                    # not just when a question was typed. Duplicate-image
                    # caching (GEMINI_VISION_CACHE) is the cost-control
                    # lever instead of skipping the call outright.
                    had_real_question = bool(question and len(question.strip()) >= 3)

                    vision_result = None
                    used_vision = False

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

                    # Case B: image uploaded, no real question typed. Identify
                    # the object and ask what they want to know instead of
                    # letting a bare image fall into the strict KB/escalation
                    # pipeline (which only escalates every plain photo, since
                    # it never finds an exact text match for "").
                    if not had_real_question and (not used_vision or vision_result.get("isWorkRelated")):
                        kb_hint = None
                        detected_terms = " ".join((vision_result or {}).get("detectedObjects") or [])

                        if detected_terms:
                            kb_hint = search_knowledge_base_articles(detected_terms, limit=1)

                        clarification_result = build_image_only_clarification_response(vision_result, kb_hint)

                        log_request(
                            question,
                            result=clarification_result,
                            user_id=data.get("user_id") or data.get("userId")
                        )

                        clarification_result["final_source"] = clarification_result.get("source")
                        clarification_result["served_by"] = "vision_relevance_check"

                        return jsonify(clarification_result), 200

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
            data["user_id"] = current_auth_user_id()
            question = data.get("question", "")

        question = clean_question(question)
        q_lower = question.lower()

        # =========================
        # CROSS-LINGUAL RETRIEVAL BRIDGE
        # The Knowledge Base is English-only. For a Chinese/Malay question,
        # derive a short English keyword string (question_for_search) used
        # ONLY to drive KB retrieval further down -- `question` itself stays
        # exactly what the staff member typed for logging/escalation/replies.
        # Falls back to `question` unchanged on any detection/AI failure.
        # =========================
        detected_language = detect_question_language(question)
        question_for_search = question

        if detected_language != "en":
            question_for_search = translate_query_to_english_keywords(question, detected_language)

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
        last_answer = AI_LAST_ANSWER_MEMORY.get(get_last_answer_key(data))

        # Only treat phrases like "dont know" / "not sure" as a rejection of
        # the PREVIOUS AI answer when there actually is a previous answer on
        # record. Otherwise a brand-new question that happens to contain one
        # of those phrases (e.g. "...but i dont know what to do next") would
        # be misread as dissatisfaction and never reach KB search at all.
        if is_staff_not_satisfied(question) and last_answer:

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
            search_question=question_for_search,
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

        elif source == "irrelevant_question":
            # Off-topic/spam (jokes, memes, "weather", etc.) is deliberately
            # never escalated, no matter how low its confidence score is --
            # only genuine work questions the KB can't answer should reach
            # a team lead. Without this, the low-confidence catch-all below
            # would escalate it anyway.
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
                ai_answer = answer_question_with_ai_provider(
                    question,
                    search_question=question_for_search,
                    user_language=detected_language,
                )
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
                result["source"] = "ai_provider_decline" if ai_answer.get("off_topic") else "ai_provider_answer"
                result["fallback"] = False
                result["fallback_message"] = ""
                result["escalation_ready"] = False
                result["escalation_required"] = False
                should_escalate = False
                clear_ai_fail_count(data, question)

                if ai_answer.get("article_id"):
                    result["article_id"] = ai_answer["article_id"]
                    result.setdefault("context", {})
                    result["context"]["article_id"] = ai_answer["article_id"]

        if should_escalate:
            related_articles = search_related_knowledge_base_articles(question_for_search, limit=3)

            related_options = []
            seen_related_titles = set()
            for item in related_articles:
                for option in build_answer_options(question, None, item):
                    title_key = str(option.get("title", "")).lower().strip()
                    if title_key and title_key not in seen_related_titles:
                        seen_related_titles.add(title_key)
                        related_options.append(option)

            if related_options:
                related_message = (
                    "I couldn't confirm the exact procedure from the information "
                    "provided, but these Knowledge Base articles may help:"
                )

                result = standardize_ai_response({
                    "question": question,
                    "type": "options",
                    "reply": related_message,
                    "answer": related_message,
                    "score": related_articles[0].get("score", 0.0),
                    "confidence": related_articles[0].get("score", 0.0),
                    "confidence_label": get_confidence_label(related_articles[0].get("score", 0.0)),
                    "source": "related_knowledge",
                    "fallback": False,
                    "escalation_ready": False,
                    "escalation_required": False,
                    "options": related_options,
                })

                remember_chat_context(data, result)
                log_request(
                    question,
                    result=result,
                    user_id=data.get("user_id") or data.get("userId")
                )

                result["final_source"] = "related_knowledge"
                result["served_by"] = "related_knowledge"

                return jsonify(result), 200

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

        # All active accounts can read live articles. The recycle bin is a
        # management feature: a Staff account must not bypass the UI by
        # requesting /api/articles?deleted=true directly.
        if show_deleted:
            viewer_role = str(g.auth_user.get("role_name") or "").strip().lower()
            viewer_role = viewer_role.replace(" ", "").replace("_", "").replace("-", "")
            if viewer_role not in {"teamlead", "manager", "admin"}:
                return jsonify({
                    "code": "FORBIDDEN",
                    "message": "Manager or Team Leader access required to view deleted articles."
                }), 403

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

    # Deliberately a relative path, NOT an absolute Railway URL. The global
    # auth guard (require_authenticated_api) now protects /static/ too, and
    # the session cookie is SameSite=Lax -- it's only sent for same-origin
    # requests. A relative "/static/..." src resolves against the page's
    # own Vercel origin, which the Vercel rewrite then forwards to Railway
    # while still carrying the cookie. An absolute Railway URL is a
    # different origin from the browser's point of view, so the cookie
    # never gets attached and the image request comes back 401 instead of
    # the actual file -- which is exactly what was happening here.
    file_urls = [item["url"] for item in saved_files]

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
        deleted_by = current_auth_user_id()

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
        deleted_by = current_auth_user_id()

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

        handled_by = current_auth_user_id()

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
    reviewed_by = current_auth_user_id()
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
    reviewed_by = current_auth_user_id()
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
        deleted_by = current_auth_user_id()

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
        deleted_by = current_auth_user_id()

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

    reviewed_by = current_auth_user_id()
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

    reviewed_by = current_auth_user_id()
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
    reviewed_by = current_auth_user_id()

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
            formatted_questions.append({
                "id": q["question_id"],
                "question": q["question_text"],
                "options": [
                    q["option_a"],
                    q["option_b"],
                    q["option_c"],
                    q["option_d"]
                ],
                # Do not send answer keys or explanations before submission.
                # Flask marks answers against quiz_question.correct_option.
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


@app.route("/api/quizzes/<int:quiz_id>/submit", methods=["POST"])
def submit_quiz(quiz_id):
    """Mark a completed quiz on the server and save one attempt to quiz_result.

    The global before_request hook validates the active session and CSRF token.
    Never trust a user_id, score, percentage, or answer key sent by the browser.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        return jsonify({"message": "Submit your selected answers as an answers object."}), 400

    raw_answers = data["answers"]
    if not raw_answers or len(raw_answers) > 500:
        return jsonify({"message": "A valid set of quiz answers is required."}), 400

    answers = {}
    for raw_question_id, raw_option in raw_answers.items():
        question_id_text = str(raw_question_id).strip()
        if (not question_id_text.isascii() or not question_id_text.isdecimal()
                or len(question_id_text) > 18):
            return jsonify({"message": "Invalid question ID in quiz answers."}), 400
        question_id = int(question_id_text)
        if question_id < 1 or question_id in answers:
            return jsonify({"message": "Duplicate or invalid quiz question ID."}), 400
        if not isinstance(raw_option, str) or raw_option.strip().upper() not in {"A", "B", "C", "D"}:
            return jsonify({"message": "Each answer must be A, B, C, or D."}), 400
        answers[question_id] = raw_option.strip().upper()

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT quiz_id FROM quiz WHERE quiz_id = %s AND status = 'active' LIMIT 1",
            (quiz_id,),
        )
        if not cursor.fetchone():
            conn.rollback()
            return jsonify({"message": "This quiz is not available."}), 404

        cursor.execute(
            "SELECT question_id, correct_option FROM quiz_question WHERE quiz_id = %s ORDER BY question_id ASC",
            (quiz_id,),
        )
        questions = cursor.fetchall() or []
        if not questions:
            conn.rollback()
            return jsonify({"message": "This quiz has no questions."}), 400

        expected_ids = {int(row["question_id"]) for row in questions}
        if set(answers) != expected_ids:
            conn.rollback()
            return jsonify({"message": "Please answer every question in this quiz."}), 400

        correct_count = sum(
            answers[int(row["question_id"])] == str(row["correct_option"] or "").strip().upper()
            for row in questions
        )
        total_questions = len(questions)
        percentage = round(correct_count * 100 / total_questions, 2)

        # The screenshot confirms these quiz_result columns exist. The DB
        # must still be checked for its auto-increment/defaults before deploy.
        cursor.execute(
            """INSERT INTO quiz_result
               (quiz_id, user_id, score, total_questions, percentage, completed_at)
               VALUES (%s, %s, %s, %s, %s, NOW())""",
            (quiz_id, current_auth_user_id(), correct_count, total_questions, percentage),
        )
        result_id = cursor.lastrowid
        conn.commit()
        return jsonify({
            "message": "Quiz completed and result saved.",
            "saved": True,
            "result_id": result_id,
            "quiz_id": quiz_id,
            "score": correct_count,
            "total_questions": total_questions,
            "percentage": percentage,
        }), 201
    except Exception:
        if conn:
            conn.rollback()
        print("QUIZ SUBMISSION ERROR: Unable to save quiz result.")
        return jsonify({"message": "Could not save your result. Please retry."}), 500
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
    created_by = current_auth_user_id()
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

    print(
        f"AI QUIZ: knowledge base records found for category='{category_filter}': "
        f"{len(articles)}"
    )

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
        print(
            "AI QUIZ: no eligible knowledge base content found for category "
            f"'{category_filter}'; skipping AI provider call."
        )
        return None

    def build_prompt(strict_retry=False):
        strict_note = ""

        if strict_retry:
            strict_note = (
                "\nYour previous reply could not be parsed as JSON. Reply again "
                "with ONLY the raw JSON array -- no markdown, no code fences, "
                "no text before or after it.\n"
            )

        return f"""You are generating training quiz questions for Jungle House staff.

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
{strict_note}
Source content:
{source_text}
"""

    def parse_questions(raw_reply):
        json_text = raw_reply.strip()
        json_text = re.sub(r"^```(?:json)?\s*", "", json_text)
        json_text = re.sub(r"\s*```$", "", json_text)

        parsed = json.loads(json_text)

        if isinstance(parsed, dict) and isinstance(parsed.get("questions"), list):
            parsed = parsed["questions"]

        if not isinstance(parsed, list):
            raise ValueError("AI did not return a JSON array of questions.")

        result = []

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

            result.append({
                "question": question_text,
                "options": [str(option).strip() for option in options],
                "correctAnswerIndex": correct_index,
                "explanation": explanation,
                "sourceTitle": str(item.get("sourceTitle") or "").strip(),
            })

        return result

    # The provider call itself (network/auth/HTTP errors) is allowed to raise
    # straight out of this function -- that is a real provider failure, not a
    # JSON formatting problem, and the caller classifies it accordingly.
    raw_reply = ai_provider_service.generate_ai_reply(build_prompt())
    print(f"AI QUIZ: provider response received ({len(raw_reply or '')} chars).")

    try:
        questions = parse_questions(raw_reply)
        print(f"AI QUIZ: JSON validation passed on first attempt, {len(questions)} usable question(s).")
    except Exception as error:
        print(f"AI QUIZ: JSON validation failed on first attempt ({error}); retrying with a stricter prompt.")

        raw_retry_reply = ai_provider_service.generate_ai_reply(build_prompt(strict_retry=True))
        print(f"AI QUIZ: provider retry response received ({len(raw_retry_reply or '')} chars).")

        questions = parse_questions(raw_retry_reply)
        print(f"AI QUIZ: JSON validation passed on retry, {len(questions)} usable question(s).")

    if not questions:
        raise ValueError("AI returned zero valid questions after validation.")

    return questions[:question_count]


@app.route("/api/admin/quizzes/ai-generate", methods=["POST"])
def ai_generate_quiz():
    print("AI QUIZ: /api/admin/quizzes/ai-generate route reached.")

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
    ai_failure_reason = None

    # Prefer a real AI provider if the manager has configured one in AI
    # Model Settings. Track *why* the AI path didn't produce questions so
    # the eventual error message (if the template fallback also comes up
    # empty) tells the truth instead of always blaming "not enough content".
    if not AI_PROVIDER_SERVICE_AVAILABLE:
        ai_failure_reason = "service_unavailable"
        print("AI QUIZ: ai_provider_service module failed to import; using template fallback only.")
    else:
        try:
            provider_questions = build_ai_quiz_questions_via_provider(
                source_category, question_count, difficulty
            )

            if provider_questions:
                questions = provider_questions
                generation_method = "ai_provider"
            else:
                ai_failure_reason = "no_content"
        except ai_provider_service.AIProviderNotConfiguredError:
            ai_failure_reason = "not_configured"
            print("AI QUIZ: no active AI provider configured in AI Model Settings.")
        except ValueError as error:
            ai_failure_reason = "invalid_format"
            print("AI QUIZ: provider returned an invalid quiz format:", error)
        except Exception as error:
            ai_failure_reason = "provider_failed"
            print("AI QUIZ: AI provider request failed, falling back to template:", error)

    if not questions:
        try:
            questions = build_ai_quiz_questions(source_category, question_count, difficulty)

            if questions:
                generation_method = "template"
        except Exception as error:
            print("AI QUIZ: template fallback generation error:", error)

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
        if ai_failure_reason == "not_configured":
            message = "AI model is not configured. Please configure it in AI Model Settings."
        elif ai_failure_reason == "invalid_format":
            message = "The AI returned an invalid quiz format. Please try again."
        elif ai_failure_reason == "provider_failed":
            message = "AI provider request failed. Please try again, or create the quiz manually."
        elif ai_failure_reason == "service_unavailable":
            message = "AI provider service is not available on this server. Please contact an administrator."
        else:
            message = "No verified Knowledge Base content is available for quiz generation."

        print(f"AI QUIZ: generation failed, reason='{ai_failure_reason}'.")

        return jsonify({"message": message}), 400

    category_label = source_category if source_category.lower() != "all" else "Training"

    description = (
        f"AI generated quiz based on the latest verified {category_label} content."
        if generation_method == "ai_provider"
        else f"Quiz generated from the latest verified {category_label} content."
    )

    print(f"AI QUIZ: generation succeeded via '{generation_method}', {len(questions)} question(s).")

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

def format_registration_timestamp(value):
    """User Management only: return UTC ISO-8601, not an ambiguous display string.

    This project's MySQL timestamps are currently read as naive UTC datetimes.
    The frontend converts the explicit UTC value to Asia/Kuching for display.
    No other API response format is changed.
    """
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds") if value.tzinfo else value.strftime("%Y-%m-%dT%H:%M:%SZ")
    return value


@app.route("/api/admin/users", methods=["GET"])
def get_admin_users():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.user_id, u.full_name, u.email, u.status, u.created_at,
                   r.role_name
            FROM users u JOIN roles r ON u.role_id = r.role_id
            ORDER BY u.user_id ASC
        """)
        users = cursor.fetchall() or []
        for user in users:
            user["created_at"] = format_registration_timestamp(user.get("created_at"))
            # Temporary compatibility for older frontend pages, never issue keys.
            user.update(activation_key_status=None, activation_failed_attempts=0, awaiting_activation=False)
        return jsonify(users), 200
    except Exception:
        print("GET ADMIN USERS ERROR: Query failed.")
        return jsonify({"message": "Failed to load users."}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



@app.route("/api/admin/users/<int:user_id>/role", methods=["PUT"])
def update_admin_user_role(user_id):
    data = request.get_json() or {}

    role = str(data.get("role", "")).strip().lower()
    actor_id = current_auth_user_id()

    if role not in ["staff", "teamlead"]:
        return jsonify({"message": "Invalid role."}), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        if not actor_id or not is_active_manager(cursor, actor_id):
            conn.rollback()
            return jsonify({
                "message": "Only a Manager can update user roles."
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
    actor_id = current_auth_user_id()

    if status not in ["active", "inactive"]:
        return jsonify({"message": "Invalid status."}), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        if not actor_id or not is_active_manager(cursor, actor_id):
            conn.rollback()
            return jsonify({
                "message": "Only a Manager can update user status."
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
    status = str(request.args.get("status") or "pending").strip().lower()
    if status not in {"pending", "active", "declined", "inactive", "all"}:
        status = "pending"
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if not is_registration_approver(cursor, g.auth_user["user_id"]):
            return jsonify({"message": "Only a Manager or Team Leader can view registration requests."}), 403
        sql = """
            SELECT u.user_id, u.full_name, u.email, u.status, u.created_at,
                   r.role_name
            FROM users u JOIN roles r ON u.role_id = r.role_id
        """
        params = ()
        if status != "all":
            sql += " WHERE LOWER(u.status) = %s"
            params = (status,)
        sql += " ORDER BY u.created_at DESC, u.user_id DESC"
        cursor.execute(sql, params)
        users = cursor.fetchall() or []
        for user in users:
            user["created_at"] = format_datetime_value(user.get("created_at"))
            user.update(activation_key_status=None, activation_failed_attempts=0, awaiting_activation=False)
        return jsonify(users), 200
    except Exception:
        print("GET REGISTRATION REQUESTS ERROR: Query failed.")
        return jsonify({"message": "Failed to load registration requests."}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



@app.route("/api/admin/registration-history", methods=["GET"])
def get_registration_history():
    """Read-only history for authorized registration approvers.

    Current declined users and archived attempts are both included. This
    endpoint does not update users, change statuses or create tables.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if not is_registration_approver(cursor, current_auth_user_id()):
            return jsonify({"message": "Manager or Team Leader access required."}), 403

        records = []
        cursor.execute("SHOW TABLES LIKE 'declined_registration_history'")
        has_archive = bool(cursor.fetchone())
        if has_archive:
            cursor.execute("""
                SELECT history_id, user_id, full_name, email,
                       originally_registered_at, declined_at,
                       declined_by_name, decision_description, archived_at
                FROM declined_registration_history
                ORDER BY archived_at DESC, history_id DESC
            """)
            for entry in cursor.fetchall() or []:
                records.append({
                    "record_type": "archived",
                    "history_id": entry["history_id"],
                    "user_id": entry["user_id"],
                    "full_name": entry["full_name"],
                    "email": entry["email"],
                    "registered_at": format_registration_timestamp(entry.get("originally_registered_at")),
                    "declined_at": format_registration_timestamp(entry.get("declined_at")),
                    "declined_by_name": entry.get("declined_by_name"),
                    "decision_description": entry.get("decision_description"),
                    "archived_at": format_registration_timestamp(entry.get("archived_at")),
                })

        cursor.execute("""
            SELECT user_id, full_name, email, created_at
            FROM users WHERE LOWER(status) = 'declined'
            ORDER BY created_at DESC, user_id DESC
        """)
        for entry in cursor.fetchall() or []:
            # Each decline already writes an audit record. Read only the
            # corresponding user's latest decision; no schema change required.
            cursor.execute("""
                SELECT actor_name, description, created_at
                FROM audit_log
                WHERE action = 'Declined account registration'
                  AND module = 'User Management'
                  AND description LIKE %s
                ORDER BY created_at DESC, audit_id DESC LIMIT 1
            """, (f"User ID {entry['user_id']} registration declined.%",))
            decision = cursor.fetchone() or {}
            records.append({
                "record_type": "current",
                "history_id": None,
                "user_id": entry["user_id"],
                "full_name": entry["full_name"],
                "email": entry["email"],
                "registered_at": format_registration_timestamp(entry.get("created_at")),
                "declined_at": format_registration_timestamp(decision.get("created_at")),
                "declined_by_name": decision.get("actor_name"),
                "decision_description": decision.get("description"),
                "archived_at": None,
            })

        response = jsonify({"records": records})
        response.headers["Cache-Control"] = "no-store"
        return response, 200
    except Exception:
        print("REGISTRATION HISTORY ERROR: Could not load registration records.")
        return jsonify({"message": "Unable to load registration history."}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/admin/registration-requests/<int:user_id>/approve", methods=["PUT"])
def approve_registration_request(user_id):
    data = request.get_json(silent=True) or {}
    approved_by = g.auth_user["user_id"]
    new_role = str(data.get("role", "staff")).strip().lower()
    if new_role not in {"staff", "teamlead"}:
        return jsonify({"message": "Select a valid staff or team lead role."}), 400

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)
        if not is_registration_approver(cursor, approved_by):
            conn.rollback()
            return jsonify({"message": "Only a Manager or Team Leader can approve registrations."}), 403
        cursor.execute("""
            SELECT user_id, full_name, email, status FROM users
            WHERE user_id = %s LIMIT 1 FOR UPDATE
        """, (user_id,))
        target = cursor.fetchone()
        if not target:
            conn.rollback()
            return jsonify({"message": "Registration request not found."}), 404
        if str(target.get("status") or "").lower() != "pending":
            conn.rollback()
            return jsonify({"message": "Only pending registrations can be approved."}), 409
        cursor.execute("SELECT role_id FROM roles WHERE LOWER(role_name) = %s LIMIT 1", (new_role,))
        role_row = cursor.fetchone()
        if not role_row:
            conn.rollback()
            return jsonify({"message": "Selected role does not exist."}), 400
        # The account becomes usable immediately upon manager approval.
        cursor.execute("""
            UPDATE users SET role_id = %s, status = 'active'
            WHERE user_id = %s AND status = 'pending'
        """, (role_row["role_id"], user_id))
        if cursor.rowcount != 1:
            conn.rollback()
            return jsonify({"message": "Registration was already reviewed."}), 409
        revoke_legacy_unused_registration_keys(cursor, str(target["email"]).strip().lower())
        conn.commit()
        notify_registration_decision(user_id, approved=True)
        add_audit_log(
            actor_id=approved_by, actor_name=g.auth_user["full_name"],
            action="Approved account registration", module="User Management",
            description=f"User ID {user_id} approved as {new_role}; account activated directly."
        )
        return jsonify({
            "message": "Registration approved. The user can now sign in with email and password.",
            "account_status": "active", "activation_key_issued": False,
        }), 200
    except Exception:
        if conn:
            conn.rollback()
        print("APPROVE REGISTRATION ERROR: Approval transaction failed.")
        return jsonify({"message": "Failed to approve registration."}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/admin/registration-requests/<int:user_id>/decline", methods=["PUT"])
def decline_registration_request(user_id):
    """Mark a declined registration without deleting historical account data."""
    data = request.get_json(silent=True) or {}
    declined_by = g.auth_user["user_id"]
    reason = str(data.get("reason") or "").strip()[:1000]
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)
        if not is_registration_approver(cursor, declined_by):
            conn.rollback()
            return jsonify({"message": "Only a Manager or Team Leader can decline registrations."}), 403
        cursor.execute("""
            SELECT user_id, email, status FROM users WHERE user_id = %s
            LIMIT 1 FOR UPDATE
        """, (user_id,))
        target = cursor.fetchone()
        if not target:
            conn.rollback()
            return jsonify({"message": "Registration request not found."}), 404
        if str(target.get("status") or "").lower() != "pending":
            conn.rollback()
            return jsonify({"message": "Only pending registrations can be declined."}), 409
        cursor.execute("""
            UPDATE users SET status = 'declined'
            WHERE user_id = %s AND status = 'pending'
        """, (user_id,))
        if cursor.rowcount != 1:
            conn.rollback()
            return jsonify({"message": "Registration was already reviewed."}), 409
        revoke_legacy_unused_registration_keys(cursor, str(target["email"]).strip().lower())
        conn.commit()
        add_audit_log(
            actor_id=declined_by, actor_name=g.auth_user["full_name"],
            action="Declined account registration", module="User Management",
            description=f"User ID {user_id} registration declined. Reason: {reason or 'Not specified'}."
        )
        return jsonify({
            "message": "Registration declined. The account remains disabled and its history is preserved.",
            "account_status": "declined", "deleted": False,
        }), 200
    except Exception:
        if conn:
            conn.rollback()
        print("DECLINE REGISTRATION ERROR: Decline transaction failed.")
        return jsonify({"message": "Failed to decline registration."}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# ADMIN - SYSTEM EMAIL TEST
# =========================
@app.route("/api/admin/email/test", methods=["POST"])
def test_system_email():
    data = request.get_json(silent=True) or {}
    actor_id = current_auth_user_id()
    requested_email = str(data.get("email") or "").strip().lower()

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if not actor_id or not is_registration_approver(cursor, actor_id):
            return jsonify({"message": "Only manager or team lead can test system email."}), 403

        cursor.execute("SELECT full_name, email FROM users WHERE user_id = %s LIMIT 1", (actor_id,))
        actor = cursor.fetchone() or {}
        recipient = requested_email or str(actor.get("email") or "").strip().lower()

        if not recipient or not is_valid_email_format(recipient):
            return jsonify({"message": "A valid test recipient email is required."}), 400

        if PRESENTATION_DEMO_MODE:
            send_email_safe(
                recipient,
                "Jungle House AI Wiki - Presentation demo email",
                "This is a simulated presentation email. No real SMTP message is sent in demo mode.",
            )
            return jsonify({
                "message": f"Presentation demo email simulated successfully for {recipient}.",
                "configured": True,
                "email_sent": True,
                "presentation_demo_mode": True,
            }), 200

        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
        smtp_user = os.getenv("SMTP_USER", "").strip()
        smtp_from = os.getenv("SMTP_FROM_EMAIL", smtp_user).strip()
        configured = bool(smtp_host and smtp_user and os.getenv("SMTP_PASSWORD", "").strip() and smtp_from)

        if not configured:
            return jsonify({
                "message": "System email is not fully configured in Railway Variables.",
                "configured": False,
                "smtp_host": smtp_host,
                "smtp_user_set": bool(smtp_user),
                "smtp_from_set": bool(smtp_from),
                "smtp_password_set": bool(os.getenv("SMTP_PASSWORD", "").strip()),
            }), 503

        sent = send_email_safe(
            recipient,
            "Jungle House AI Wiki - System email test",
            f"Hi {actor.get('full_name') or 'there'},\n\nThis is a production email test from Jungle House AI Wiki.\n\nIf you received this message, Railway SMTP is configured correctly.\n\nJungle House AI Wiki Team\n",
        )

        if not sent:
            return jsonify({
                "message": "SMTP is configured, but Gmail rejected or failed the send. Check Railway deployment logs for SEND EMAIL AUTH ERROR / SEND EMAIL SAFE ERROR.",
                "configured": True,
                "email_sent": False,
            }), 502

        return jsonify({
            "message": f"Test email sent successfully to {recipient}.",
            "configured": True,
            "email_sent": True,
        }), 200

    except Exception as error:
        print("SYSTEM EMAIL TEST ERROR:", error)
        return jsonify({"message": "System email test failed.", "error": str(error)}), 500
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

    sender_id = current_auth_user_id()
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
    sender_id = current_auth_user_id()
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
        # Do not let an employee inject messages into another conversation.
        cursor.execute("""
            SELECT message_id FROM user_message
            WHERE thread_id = %s AND
                  ((sender_id = %s AND receiver_id = %s)
                   OR (sender_id = %s AND receiver_id = %s))
            LIMIT 1
        """, (thread_id, sender_id, receiver_id, receiver_id, sender_id))
        if not cursor.fetchone():
            return jsonify({"message": "You can only reply to your own conversation."}), 403

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


# Five minutes is enforced against the database's timestamp, not the browser clock.
# Never trust a user_id supplied in JSON for editing/deleting another person's message.
MESSAGE_ACTION_WINDOW_SECONDS = 5 * 60


def _message_action_denied(cursor, message_id, user_id, operation):
    """Explain an unsuccessful atomic UPDATE without disclosing message contents."""
    cursor.execute("""
        SELECT sender_id, is_deleted_by_sender, is_deleted_by_receiver,
               TIMESTAMPDIFF(MICROSECOND, created_at, NOW()) AS age_microseconds
        FROM user_message
        WHERE message_id = %s
        LIMIT 1
    """, (message_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({"message": "Message not found."}), 404
    if int(row["sender_id"]) != int(user_id):
        return jsonify({"message": "You can only change messages you sent."}), 403

    age = row.get("age_microseconds")
    if age is None or not 0 <= int(age) <= MESSAGE_ACTION_WINDOW_SECONDS * 1000000:
        return jsonify({"message": "The five-minute message action window has expired."}), 409

    if operation == "edit" and row["is_deleted_by_sender"]:
        return jsonify({"message": "A message deleted from your view cannot be edited."}), 409
    if operation == "everyone" and row["is_deleted_by_sender"] and row["is_deleted_by_receiver"]:
        return jsonify({"message": "Message is already deleted for everyone."}), 409

    return jsonify({"message": "Message could not be changed. Refresh and try again."}), 409


@app.route("/api/messages/edit/<int:message_id>", methods=["PUT"])
def edit_message(message_id):
    data = request.get_json(silent=True) or {}
    user_id = current_auth_user_id()
    message = str(data.get("message") or "").strip()

    if not message:
        return jsonify({"message": "Message cannot be empty."}), 400

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Atomic condition: ownership, visibility and deadline cannot be
        # bypassed by forging the request or racing the five-minute cutoff.
        cursor.execute("""
            UPDATE user_message
            SET message = %s, edited_at = NOW()
            WHERE message_id = %s
              AND sender_id = %s
              AND is_deleted_by_sender = FALSE
              AND created_at BETWEEN NOW() - INTERVAL 5 MINUTE AND NOW()
        """, (message, message_id, user_id))

        if cursor.rowcount != 1:
            conn.rollback()
            return _message_action_denied(cursor, message_id, user_id, "edit")

        conn.commit()
        return jsonify({"message": "Message updated successfully."}), 200
    except Exception:
        if conn:
            conn.rollback()
        print("MYSQL ERROR /api/messages/edit: unable to update message")
        return jsonify({"message": "Failed to edit message."}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/messages/delete-for-everyone/<int:message_id>", methods=["PUT"])
def delete_message_for_everyone(message_id):
    """Soft-delete for both participants; only the sender and only for 5 minutes."""
    user_id = current_auth_user_id()
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # One UPDATE, one transaction: no impersonation of the receiver,
        # and neither participant can keep seeing the message after commit.
        cursor.execute("""
            UPDATE user_message
            SET is_deleted_by_sender = TRUE,
                is_deleted_by_receiver = TRUE
            WHERE message_id = %s
              AND sender_id = %s
              AND created_at BETWEEN NOW() - INTERVAL 5 MINUTE AND NOW()
              AND (is_deleted_by_sender = FALSE OR is_deleted_by_receiver = FALSE)
        """, (message_id, user_id))

        if cursor.rowcount != 1:
            conn.rollback()
            return _message_action_denied(cursor, message_id, user_id, "everyone")

        conn.commit()
        return jsonify({"message": "Message deleted for everyone."}), 200
    except Exception:
        if conn:
            conn.rollback()
        print("MYSQL ERROR /api/messages/delete-for-everyone: unable to delete message")
        return jsonify({"message": "Failed to delete message for everyone."}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/messages/delete/<int:message_id>", methods=["PUT"])
def delete_message_from_view(message_id):
    data = request.get_json() or {}

    user_id = current_auth_user_id()

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
    return send_private_static_file(STATIC_DIR, filename)


@app.after_request
def prevent_private_static_caching(response):
    """Do not cache internal files (or access-denied responses) in shared proxies."""
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.vary.add("Cookie")
    return response

# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    verify_manager_account()

    # Railway exposes the container through its assigned PORT.  Binding only
    # to 127.0.0.1 makes the service unreachable from Vercel and results in
    # Axios "Network Error".  0.0.0.0 is required for a public container.
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").strip().lower() == "true"

    app.run(host=host, port=port, debug=debug, use_reloader=False)