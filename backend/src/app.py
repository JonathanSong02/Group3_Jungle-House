from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import time
from werkzeug.utils import secure_filename
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from pathlib import Path
import csv
import json
import traceback
from db_helper import (
    save_qa_to_db,
    search_similar_question,
    search_similar_questions,
    create_escalation,
    resolve_escalation
)
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
            "type": file.content_type
        })

    return saved_files

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


def log_request(question: str, result: dict | None = None, error: str | None = None) -> None:
    ensure_log_files()
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
        payload = {
            "timestamp": timestamp,
            "question": question,
            "title": result.get("title") or result.get("question"),
            "question": result.get("question"),
            "category": result.get("category"),
            "section": result.get("section"),
            "type": result.get("type", "text"),
            "score": float(result.get("score", 0.0)),
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
        f"[{timestamp}] CHAT | question={question!r} | "
        f"title={payload['title']!r} | category={payload['category']!r} | "
        f"section={payload['section']!r} | score={payload['score']} | "
        f"source={payload['source']!r} | fallback={payload['fallback']} | "
        f"escalation_ready={payload['escalation_ready']}"
    )

    with open(LOG_JSONL, "a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")

    with open(LOG_CSV, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([
            payload["timestamp"],
            payload["question"],
            payload["title"],
            payload["category"],
            payload["section"],
            payload["type"],
            payload["score"],
            payload["confidence"],
            payload["confidence_label"],
            payload["source"],
            payload["fallback"],
            payload["fallback_message"],
            payload["escalation_ready"],
            payload["reply"],
            payload["error"],
        ])

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


def choose_final_result(model_result, retrieval_result, kb_result=None):
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

    # Priority 2: Manager-approved Team Lead answer.
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
    final_result = choose_final_result(model_result, retrieval_result, kb_result)  

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

    # Client feedback: crew members do not choose role during registration.
    # Every self-registered account is staff by default.
    role = "staff"

    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")
    access_key = data.get("access_key", "").strip()

    if not all([full_name, email, password, confirm_password, access_key]):
        return jsonify({"message": "Please fill in all fields."}), 400

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

        cursor.execute("SELECT user_id FROM users WHERE LOWER(email) = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.rollback()
            return jsonify({"message": "Email is already registered."}), 409

        cursor.execute("""
            SELECT role_id, role_name
            FROM roles
            WHERE LOWER(role_name) = %s
        """, (role,))
        role_row = cursor.fetchone()

        if not role_row:
            conn.rollback()
            return jsonify({"message": "Staff role does not exist in database."}), 400

        cursor.execute("""
            SELECT rk.key_id, rk.is_used, rk.is_active, rk.expires_at, r.role_name
            FROM registration_keys rk
            JOIN roles r ON rk.allowed_role_id = r.role_id
            WHERE rk.key_code = %s
              AND rk.is_used = FALSE
              AND rk.is_active = TRUE
              AND LOWER(r.role_name) = %s
              AND (rk.expires_at IS NULL OR rk.expires_at > NOW())
            FOR UPDATE
        """, (access_key, role))
        key_row = cursor.fetchone()

        if not key_row:
            conn.rollback()
            return jsonify({"message": "Invalid, expired, used, or non-staff registration key."}), 400

        password_hash = generate_password_hash(password)

        cursor.execute("""
            INSERT INTO users (full_name, email, password_hash, role_id, status)
            VALUES (%s, %s, %s, %s, 'active')
        """, (full_name, email, password_hash, role_row["role_id"]))

        new_user_id = cursor.lastrowid

        cursor.execute("""
            UPDATE registration_keys
            SET is_used = TRUE,
                used_by = %s,
                used_at = NOW()
            WHERE key_id = %s
        """, (new_user_id, key_row["key_id"]))

        conn.commit()

        add_audit_log(
            actor_id=new_user_id,
            actor_name=full_name,
            action="Registered account",
            module="Authentication",
            description=f"New staff account registered using manager registration key. Email: {email}"
        )

        return jsonify({"message": "Registration successful. You can now log in."}), 201

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
                r.role_name
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
        if user_status != "active":
            record_login_history(
                cursor,
                user_id=user["user_id"],
                email=user["email"],
                full_name=user["full_name"],
                status="failed"
            )
            conn.commit()
            return jsonify({"message": "This account is inactive. Please contact the manager."}), 403

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
    try:
        ensure_log_files()

        rows = []

        with open(LOG_CSV, "r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)

            for row in reader:
                question = str(row.get("question", "")).strip()

                if not question:
                    continue

                try:
                    confidence = float(row.get("confidence", 0) or 0)
                except Exception:
                    confidence = 0.0

                fallback_value = str(row.get("fallback", "")).lower()
                escalation_value = str(row.get("escalation_ready", "")).lower()

                rows.append({
                    "timestamp": row.get("timestamp", ""),
                    "question": question,
                    "title": row.get("title", ""),
                    "category": row.get("category", ""),
                    "confidence": confidence,
                    "confidence_label": row.get("confidence_label", ""),
                    "source": row.get("source", ""),
                    "fallback": fallback_value in ["true", "1", "yes"],
                    "escalation_ready": escalation_value in ["true", "1", "yes"],
                    "reply": row.get("reply", "")
                })

        # =========================
        # Question Analytics
        # =========================
        question_counter = {}

        for row in rows:
            key = row["question"].lower()

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
        print("ANALYTICS ERROR:", e)
        return jsonify({
            "message": "Failed to load analytics.",
            "error": str(e)
        }), 500


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
                log_request(question, result=result)

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
                log_request(question, result=result)
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
        log_request(question, result=result)
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

        log_request(question, error=str(error))

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

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if saved_files:
            attachment_url = saved_files[0]["url"]
            attachment_type = saved_files[0]["type"]
            image_files = json.dumps(saved_files)

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
        else:
            cursor.execute("""
                UPDATE wiki_article
                SET title = %s,
                    content = %s,
                    category = %s,
                    link = %s,
                    sub_category = %s
                WHERE article_id = %s
            """, (
                title,
                content,
                category,
                link,
                sub_category,
                article_id
            ))

        conn.commit()

        add_audit_log(
            action="Edited article",
            module="Content Management",
            description=f"Article updated: {title}"
        )

        return jsonify({
            'message': 'Article updated successfully.',
            'image_files': saved_files
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
            SELECT article_id
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
            SELECT article_id
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
# USER MANAGEMENT ROUTES
# =========================

@app.route("/api/admin/users", methods=["GET"])
def get_admin_users():
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
            ORDER BY u.user_id ASC
        """)

        users = cursor.fetchall()

        for user in users:
            user["created_at"] = format_datetime_value(user.get("created_at"))

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
    role = data.get("role", "").strip().lower()

    if role not in ["staff", "teamlead"]:
        return jsonify({"message": "Invalid role."}), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT role_id
            FROM roles
            WHERE LOWER(role_name) = %s
            LIMIT 1
        """, (role,))
        role_row = cursor.fetchone()

        if not role_row:
            return jsonify({"message": "Role not found."}), 404

        cursor.execute("""
            UPDATE users
            SET role_id = %s
            WHERE user_id = %s
              AND user_id <> 1
        """, (role_row["role_id"], user_id))

        conn.commit()

        add_audit_log(
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