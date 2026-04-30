from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
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
    create_escalation,
    resolve_escalation
)

import re

def is_nonsense(text):
    text = text.strip().lower()

    whitelist = ["hi", "hello", "hey", "ok", "thanks"]

    if text in whitelist:
        return False

    if len(text) < 3:
        return True

    if not re.search(r'[aeiou]', text):
        return True

    if re.fullmatch(r'(.)\1{3,}', text):
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
STATIC_DIR = (BASE_DIR.parent / "static").resolve()
LOG_DIR = (BASE_DIR.parent / "logs").resolve()
LOG_JSONL = LOG_DIR / "ai_chat_logs.jsonl"
LOG_CSV = LOG_DIR / "ai_chat_logs.csv"
TEST_REPORT_CSV = LOG_DIR / "ai_test_results.csv"

# Simple in-memory chat context for local prototype use.
# This helps follow-up messages like "step 25" work even if the frontend
# does not send the previous AI response context back to the backend.
AI_CHAT_MEMORY = {}

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
CORS(app)

ESCALATION_MESSAGE = "No confident answer. Escalate to team lead."

REAL_JH_TEST_QUESTIONS = [
    {
        "id": 1,
        "category": "SOP",
        "test_type": "exact match",
        "question": "kiosk opening",
        "expected_title": "JHKC Kiosk Opening",
        "expected_category": "sop",
        "expected_behavior": "answer",
    },
    {
        "id": 2,
        "category": "SOP",
        "test_type": "partial match",
        "question": "how to open kiosk",
        "expected_title": "JHKC Kiosk Opening",
        "expected_category": "sop",
        "expected_behavior": "answer",
    },
    {
        "id": 3,
        "category": "SOP",
        "test_type": "wrong spelling",
        "question": "how to opn kios",
        "expected_title": "JHKC Kiosk Opening",
        "expected_category": "sop",
        "expected_behavior": "answer",
    },
    {
        "id": 4,
        "category": "SOP",
        "test_type": "exact match",
        "question": "kiosk closing checklist",
        "expected_title": "Kiosk Closing Check List",
        "expected_category": "sop",
        "expected_behavior": "answer",
    },
    {
        "id": 5,
        "category": "SOP",
        "test_type": "wrong spelling",
        "question": "shopfy pos opening",
        "expected_title": "Shopify POS app Opening",
        "expected_category": "sop",
        "expected_behavior": "answer",
    },
    {
        "id": 6,
        "category": "SOP",
        "test_type": "partial match",
        "question": "receipt printer setup",
        "expected_title": "Receipt printer preparation for opening",
        "expected_category": "sop",
        "expected_behavior": "answer",
    },
    {
        "id": 7,
        "category": "Product",
        "test_type": "exact match",
        "question": "golden passion honey",
        "expected_title": "Golden Passion Honey (New Product)",
        "expected_category": "product",
        "expected_behavior": "answer",
    },
    {
        "id": 8,
        "category": "Product",
        "test_type": "partial match",
        "question": "new packaging price",
        "expected_title": "Price for new packaging for HWJ and SHVP",
        "expected_category": "product",
        "expected_behavior": "answer",
    },
    {
        "id": 9,
        "category": "Product",
        "test_type": "wrong spelling",
        "question": "goldn passion honey",
        "expected_title": "Golden Passion Honey (New Product)",
        "expected_category": "product",
        "expected_behavior": "answer",
    },
    {
        "id": 10,
        "category": "Promotion",
        "test_type": "exact match",
        "question": "latest promotion",
        "expected_title": "Promotion",
        "expected_category": "promotion",
        "expected_behavior": "answer",
    },
    {
        "id": 11,
        "category": "Promotion",
        "test_type": "partial match",
        "question": "gift guide",
        "expected_title": "Win the Heart Gift Guide",
        "expected_category": "promotion",
        "expected_behavior": "answer",
    },
    {
        "id": 12,
        "category": "Promotion",
        "test_type": "broad wording",
        "question": "promotion",
        "expected_title": None,
        "expected_category": "promotion",
        "expected_behavior": "category_choice",
    },
    {
        "id": 13,
        "category": "Notice",
        "test_type": "exact match",
        "question": "public holiday 2026",
        "expected_title": "PUBLIC HOLIDAY 2026",
        "expected_category": "notice",
        "expected_behavior": "answer",
    },
    {
        "id": 14,
        "category": "Notice",
        "test_type": "partial match",
        "question": "merchant copy need signature",
        "expected_title": "Customer signature for card payment",
        "expected_category": "notice",
        "expected_behavior": "answer",
    },
    {
        "id": 15,
        "category": "Notice",
        "test_type": "partial match",
        "question": "when submit ot",
        "expected_title": "OT Submission Reminder",
        "expected_category": "notice",
        "expected_behavior": "answer",
    },
    {
        "id": 16,
        "category": "Notice",
        "test_type": "partial match",
        "question": "can block chiller or not",
        "expected_title": "Do not Block The Chiller",
        "expected_category": "notice",
        "expected_behavior": "answer",
    },
    {
        "id": 17,
        "category": "Notice",
        "test_type": "partial match",
        "question": "fake jungle house scam",
        "expected_title": "Fake Jungle House",
        "expected_category": "notice",
        "expected_behavior": "answer",
    },
    {
        "id": 18,
        "category": "Notice",
        "test_type": "wrong spelling",
        "question": "bee piont policy",
        "expected_title": "Bee Point Policy – Crew Member Guideline",
        "expected_category": "notice",
        "expected_behavior": "answer",
    },
    {
        "id": 19,
        "category": "Notice",
        "test_type": "wrong spelling",
        "question": "raya dres code",
        "expected_title": "Hari Raya Aidilfitri – Dress Code",
        "expected_category": "notice",
        "expected_behavior": "answer",
    },
    {
        "id": 20,
        "category": "Notice",
        "test_type": "partial match",
        "question": "must wear gloves and mask for juice",
        "expected_title": "Hygiene Compliance Notice – Juice Making (Effective Immediately)",
        "expected_category": "notice",
        "expected_behavior": "answer",
    },
    {
        "id": 21,
        "category": "Notice",
        "test_type": "partial match",
        "question": "who can decide cash transactions",
        "expected_title": "Cashless",
        "expected_category": "notice",
        "expected_behavior": "answer",
    },
    {
        "id": 22,
        "category": "Training",
        "test_type": "exact match",
        "question": "new bee 1st day checklist",
        "expected_title": "New Bee 1st day Check List",
        "expected_category": "training",
        "expected_behavior": "answer",
    },
    {
        "id": 23,
        "category": "Training",
        "test_type": "partial match",
        "question": "wanna bee onboarding",
        "expected_title": "Wanna-Bee onboarding Check list",
        "expected_category": "training",
        "expected_behavior": "answer",
    },
    {
        "id": 24,
        "category": "Unknown",
        "test_type": "unclear wording",
        "question": "I don’t know what to do",
        "expected_title": None,
        "expected_category": None,
        "expected_behavior": "clarification",
    },
    {
        "id": 25,
        "category": "Unknown",
        "test_type": "unclear wording",
        "question": "Still don’t know",
        "expected_title": None,
        "expected_category": None,
        "expected_behavior": "escalation",
        "context": {"unclear_count": 1},
    },
]


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
            "title": result.get("title"),
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
            "title": result.get("title"),
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


def choose_final_result(model_result, retrieval_result):
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

    if model_result and is_valid_answer(model_result):
        if model_result.get("type") == "sop":
            return model_result

        if model_result.get("score", 0.0) >= 0.60:
            return model_result

        if model_result.get("source") in {
            "unclear_question_clarification",
            "repeated_unclear_question",
            "system_problem_clarification",
            "repeated_system_problem",
            "broad_topic_clarification",
        }:
            return model_result

        if model_result.get("escalation_ready", False):
            return model_result

    if retrieval_result and is_valid_answer(retrieval_result):
        if retrieval_result.get("score", 0.0) >= 0.20:
            return retrieval_result

    if model_result and retrieval_result:
        if retrieval_result.get("score", 0.0) > model_result.get("score", 0.0):
            return retrieval_result

        if model_result.get("score", 0.0) >= 0.45:
            return model_result

    if retrieval_result:
        return retrieval_result

    if model_result:
        if model_result.get("escalation_ready", False):
            return model_result

        if model_result.get("source") in {
            "unclear_question_clarification",
            "repeated_unclear_question",
            "system_problem_clarification",
            "repeated_system_problem",
            "broad_topic_clarification",
        }:
            return model_result

        if model_result.get("score", 0.0) >= 0.45:
            return model_result

    return standardize_ai_response({
        "type": "text",
        "category": None,
        "title": None,
        "section": None,
        "reply": ESCALATION_MESSAGE,
        "answer": ESCALATION_MESSAGE,
        "purpose": None,
        "steps": [],
        "notes": [],
        "score": 0.0,
        "confidence": 0.0,
        "source": "fallback",
        "context": {},
        "fallback": True,
        "fallback_message": "Please escalate this question to team lead.",
        "escalation_ready": True,
        "escalation_required": True,
    })


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

    retrieval_result = search_similar_question(question)

    final_result = choose_final_result(
        model_result,
        normalize_result(retrieval_result, "database") if retrieval_result else None
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
        "score": final_result.get("score", 0.0),
        "confidence": final_result.get("confidence", final_result.get("score", 0.0)),
        "confidence_label": final_result.get("confidence_label"),
        "source": final_result.get("source", "unknown"),
        "context": final_result.get("context", {}),
        "fallback": final_result.get("fallback", False),
        "fallback_message": final_result.get("fallback_message", ""),
        "escalation_ready": final_result.get("escalation_ready", False),
        "escalation_required": final_result.get("escalation_required", final_result.get("escalation_ready", False)),
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
    role = data.get("role", "").strip().lower()
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")
    access_key = data.get("access_key", "").strip()

    if not all([full_name, email, role, password, confirm_password, access_key]):
        return jsonify({"message": "Please fill in all fields."}), 400

    if role not in ["staff", "teamlead"]:
        return jsonify({"message": "Only staff and team lead can register."}), 400

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
            return jsonify({"message": "Invalid role selected."}), 400

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
            return jsonify({"message": "Invalid, expired, used, or mismatched registration key."}), 400

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
            return jsonify({"message": "Invalid email or password."}), 401

        user_status = str(user.get("status", "")).strip().lower()
        if user_status != "active":
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
            try:
                cursor.execute("""
                    INSERT INTO login_history (user_id, login_status, ip_address, device_info)
                    VALUES (%s, %s, %s, %s)
                """, (
                    user["user_id"],
                    "failed",
                    request.remote_addr,
                    request.headers.get("User-Agent")
                ))
                conn.commit()
            except Exception as insert_error:
                print("LOGIN HISTORY INSERT FAILED:", insert_error)

            return jsonify({"message": "Invalid email or password."}), 401

        try:
            cursor.execute("""
                INSERT INTO login_history (user_id, login_status, ip_address, device_info)
                VALUES (%s, %s, %s, %s)
            """, (
                user["user_id"],
                "success",
                request.remote_addr,
                request.headers.get("User-Agent")
            ))
            conn.commit()
        except Exception as insert_error:
            print("LOGIN HISTORY INSERT FAILED:", insert_error)

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
            SELECT notification_id AS id, title, message, is_read, created_at
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
                message AS detail,
                is_read AS isRead,
                type,
                created_at
            FROM notification
            WHERE user_id = %s
            ORDER BY created_at DESC
        """, (user_id,))
        notifications = cursor.fetchall()

        return jsonify(notifications), 200

    except mysql.connector.Error as err:
        print("MYSQL ERROR /api/notifications:", err)
        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
        print("GENERAL ERROR /api/notifications:", e)
        return jsonify({"message": f"Server error: {str(e)}"}), 500

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

        return jsonify({"message": "Notification marked as read."}), 200

    except mysql.connector.Error as err:
        print("READ NOTIFICATION MYSQL ERROR:", err)
        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
        print("READ NOTIFICATION GENERAL ERROR:", e)
        return jsonify({"message": f"Server error: {str(e)}"}), 500

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
# AI CHAT ROUTES
# =========================
@app.route("/chat", methods=["POST"])
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}

    try:
        question = data.get("question", "")
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
        # ✅ STEP 1: NONSENSE → ESCALATE
        # =========================
        if is_nonsense(question):
            escalation_id = create_escalation(question, {
                "answer": "Unclear or invalid question",
                "confidence": 0.0,
                "source": "invalid_input"
            })

            return jsonify({
                "reply": "I didn’t understand that. I’ll escalate this to a team lead.",
                "confidence": 0.0,
                "source": "invalid_input",
                "fallback": True,
                "escalation": True,
                "escalation_id": escalation_id
            }), 200

        # =========================
        # ✅ STEP 2: CLEAN QUESTION
        # =========================
        question = clean_question(question)

        if not question:
            return jsonify({
                "reply": "Please ask a question.",
                "fallback": True
            }), 400

        # =========================
        # ✅ STEP 3: CALL AI
        # =========================
        result, status_code = process_question(
            question=question,
            context=prepare_chat_context(data),
        )

        remember_chat_context(data, result)
        log_request(question, result=result)

        # =========================
        # ✅ STEP 4: ESCALATION LOGIC
        # =========================
        LOW_CONFIDENCE_THRESHOLD = 0.6

        clarification_sources = [
            "clarification_round_1",
            "unclear_question_clarification",
            "system_problem_clarification",
            "broad_topic_clarification",
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
        ]

        source = result.get("source", "")

        should_escalate = False

        if result.get("escalation_ready"):
            should_escalate = True

        elif source in force_escalation_sources:
            should_escalate = True

        elif source in clarification_sources:
            should_escalate = False

        elif result.get("confidence", result.get("score", 0)) < LOW_CONFIDENCE_THRESHOLD and result.get("fallback"):
            should_escalate = True

        if should_escalate:
            escalation_id = create_escalation(question, result)

            result["escalation"] = True
            result["escalation_id"] = escalation_id
            result["served_by"] = "escalation_queue"

            return jsonify(result), 200

        # =========================
        # ✅ STEP 5: SAVE GOOD ANSWER
        # =========================
        if result.get("confidence", 0) >= 0.7 and not result.get("fallback"):
            save_qa_to_db(question, result)

        result["final_source"] = result.get("source")
        result["served_by"] = "ai"

        return jsonify(result), 200

    except Exception as error:
        traceback.print_exc()

        question = clean_question(data.get("question", ""))

        log_request(question, error=str(error))

        escalation_id = create_escalation(question, {
            "answer": str(error),
            "confidence": 0.0,
            "source": "system_error"
        })

        return jsonify({
            "reply": "System error. Escalated to team lead.",
            "confidence": 0,
            "fallback": True,
            "escalation": True,
            "escalation_id": escalation_id
        }), 500


# =========================
# KNOWLEDGE BASE ROUTES
# =========================
@app.route("/api/articles", methods=["GET"])
def get_articles():
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT article_id, title, content, category
            FROM wiki_article
            ORDER BY article_id ASC
        """)
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
@app.route('/api/articles', methods=['POST'])
def add_article():
    data = request.get_json()

    title = data.get('title', '').strip()
    category = data.get('category', '').strip()
    sub_category = data.get('sub_category', '').strip()
    link = data.get('link', '').strip()
    content = data.get('content', '').strip()

    if not title or not content:
        return jsonify({'message': 'Title and content are required.'}), 400

    conn = get_db_connection()

    if conn is None:
        return jsonify({'message': 'Database connection failed.'}), 500

    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            INSERT INTO wiki_article 
            (title, content, category, link, sub_category)
            VALUES (%s, %s, %s, %s, %s)
        """, (title, content, category, link, sub_category))

        conn.commit()

        return jsonify({
            'message': 'Article added successfully.',
            'article_id': cursor.lastrowid
        }), 201

    except Exception as error:
        conn.rollback()
        print('MYSQL ERROR /api/articles POST:', error)

        return jsonify({
            'message': 'Failed to save article.',
            'error': str(error)
        }), 500

    finally:
        cursor.close()
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
            SELECT article_id, title, content, category, sub_category, link
            FROM wiki_article
            WHERE article_id = %s
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
    data = request.get_json() or {}

    title = data.get('title', '').strip()
    category = data.get('category', '').strip()
    sub_category = data.get('sub_category', '').strip()
    link = data.get('link', '').strip()
    content = data.get('content', '').strip()

    if not title or not content:
        return jsonify({'message': 'Title and content are required.'}), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            UPDATE wiki_article
            SET title = %s,
                content = %s,
                category = %s,
                link = %s,
                sub_category = %s
            WHERE article_id = %s
        """, (title, content, category, link, sub_category, article_id))

        conn.commit()

        return jsonify({'message': 'Article updated successfully.'}), 200

    except Exception as error:
        if conn:
            conn.rollback()
        print('MYSQL ERROR /api/articles PUT:', error)
        return jsonify({'message': 'Failed to update article.', 'error': str(error)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# Delete Article ROUTES
# =========================
@app.route('/api/articles/<int:article_id>', methods=['DELETE'])
def delete_article(article_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            DELETE FROM wiki_article
            WHERE article_id = %s
        """, (article_id,))

        conn.commit()

        return jsonify({'message': 'Article deleted successfully.'}), 200

    except Exception as error:
        if conn:
            conn.rollback()
        print('MYSQL ERROR /api/articles DELETE:', error)
        return jsonify({'message': 'Failed to delete article.', 'error': str(error)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



# =========================
# ESCALATION ROUTES
# =========================

@app.route('/api/escalations', methods=['GET'])
def get_escalations():
    conn = None
    cursor = None

    try:
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
                e.status,
                e.created_at,
                e.updated_at,
                e.resolved_at,
                u.full_name AS asked_by_name
            FROM escalation e
            LEFT JOIN users u ON e.asked_by = u.user_id
            ORDER BY e.created_at DESC
        """)

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
    data = request.get_json() or {}

    manual_answer = data.get('manual_answer', '').strip()
    handled_by = data.get('handled_by')

    if not manual_answer:
        return jsonify({'message': 'Manual answer is required.'}), 400

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            UPDATE escalation
            SET 
                manual_answer = %s,
                handled_by = %s,
                status = 'resolved',
                resolved_at = CURRENT_TIMESTAMP
            WHERE escalation_id = %s
        """, (manual_answer, handled_by, escalation_id))

        conn.commit()

        return jsonify({
            'message': 'Escalation resolved successfully.'
        }), 200

    except Exception as error:
        if conn:
            conn.rollback()

        print('MYSQL ERROR /api/escalations PUT:', error)

        return jsonify({
            'message': 'Failed to submit manual answer.',
            'error': str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route("/api/escalations/<int:escalation_id>", methods=["DELETE"])
def delete_escalation(escalation_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()

        if conn is None:
            return jsonify({"message": "Database connection failed."}), 500

        cursor = conn.cursor()

        print("DELETE ESCALATION HIT:", escalation_id)

        cursor.execute("""
            DELETE FROM escalation
            WHERE escalation_id = %s
        """, (escalation_id,))

        conn.commit()

        print("DELETE ROWCOUNT:", cursor.rowcount)

        if cursor.rowcount == 0:
            return jsonify({
                "message": "Escalation not found.",
                "escalation_id": escalation_id
            }), 404

        return jsonify({
            "message": "Escalation deleted successfully.",
            "deleted_id": escalation_id
        }), 200

    except mysql.connector.Error as err:
        if conn:
            conn.rollback()

        print("MYSQL ERROR /api/escalations DELETE:", err)

        return jsonify({
            "message": "Database error while deleting escalation.",
            "error": str(err)
        }), 500

    except Exception as e:
        if conn:
            conn.rollback()

        print("GENERAL ERROR /api/escalations DELETE:", e)

        return jsonify({
            "message": "Server error while deleting escalation.",
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# =========================
# QUIZ ROUTES
# =========================

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

        return jsonify({
            "message": "Quiz created successfully.",
            "quiz_id": cursor.lastrowid
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


@app.route("/static/<path:filename>", methods=["GET"])
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)

from db_helper import resolve_escalation

@app.route("/api/escalation/answer", methods=["POST"])
def answer_escalation():
    data = request.get_json()

    escalation_id = data.get("escalation_id")
    answer = data.get("answer")

    resolve_escalation(escalation_id, answer)

    return jsonify({"message": "Escalation resolved and saved"})


# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    verify_manager_account()
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)