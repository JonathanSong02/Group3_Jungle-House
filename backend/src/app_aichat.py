from datetime import datetime
from pathlib import Path
import csv
import json
import traceback

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

try:
    from predict_intent import get_model_answer
    MODEL_AVAILABLE = True
    MODEL_ERROR = None
except Exception as error:
    get_model_answer = None
    MODEL_AVAILABLE = False
    MODEL_ERROR = str(error)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = (BASE_DIR.parent / "static").resolve()
LOG_DIR = (BASE_DIR.parent / "logs").resolve()
LOG_JSONL = LOG_DIR / "ai_chat_logs.jsonl"
LOG_CSV = LOG_DIR / "ai_chat_logs.csv"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
CORS(app)

REAL_JH_TEST_QUESTIONS = [
    "opening sop",
    "kiosk closing checklist",
    "new packaging price",
    "merchant copy need signature",
    "can eat inside store or not",
    "what to do if someone harasses me",
    "fake jungle house scam",
    "redeem bee points first or not",
    "when submit ot",
    "can block chiller or not",
    "put tissue on cold drinks",
    "can use kb qb ids to check customer history",
    "how much honey for honey juice",
    "must wear gloves and mask for juice",
    "who can decide cash transactions",
    "morning shift attendance memo",
]


def clean_question(value) -> str:
    text = str(value or "").strip()
    text = " ".join(text.split())
    if len(text) > 500:
        text = text[:500].strip()
    return text


def normalize_context(context) -> dict:
    if not isinstance(context, dict):
        return {}

    return {
        "title": str(context.get("title", "")).strip(),
        "section": str(context.get("section", "")).strip(),
        "last_step_number": context.get("last_step_number"),
    }


def ensure_log_files() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_CSV.exists():
        with open(LOG_CSV, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "timestamp", "question", "title", "section", "type", "score",
                "source", "escalation_ready", "reply", "error"
            ])


def log_request(question: str, result: dict | None = None, error: str | None = None) -> None:
    ensure_log_files()
    timestamp = datetime.now().isoformat(timespec="seconds")

    if error:
        payload = {
            "timestamp": timestamp,
            "question": question,
            "title": None,
            "section": None,
            "type": "text",
            "score": 0.0,
            "source": "prediction_error",
            "escalation_ready": True,
            "reply": "There was a problem while generating the answer.",
            "error": error,
        }
    else:
        result = result or {}
        payload = {
            "timestamp": timestamp,
            "question": question,
            "title": result.get("title"),
            "section": result.get("section"),
            "type": result.get("type", "text"),
            "score": float(result.get("score", 0.0)),
            "source": result.get("source", "unknown"),
            "escalation_ready": bool(
                "escalate" in str(result.get("reply", "")).lower()
                or "escalate" in str(result.get("answer", "")).lower()
                or result.get("source") in {"irrelevant_question", "low_confidence_or_model_unavailable"}
            ),
            "reply": str(result.get("reply", "")),
            "error": None,
        }

    print(
        f"[{timestamp}] CHAT | question={question!r} | "
        f"title={payload['title']!r} | section={payload['section']!r} | "
        f"score={payload['score']} | source={payload['source']!r} | "
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
            payload["section"],
            payload["type"],
            payload["score"],
            payload["source"],
            payload["escalation_ready"],
            payload["reply"],
            payload["error"],
        ])


def normalize_result(result: dict) -> dict:
    if not isinstance(result, dict):
        return {
            "type": "text",
            "reply": "Invalid model output.",
            "title": None,
            "section": None,
            "answer": str(result),
            "steps": [],
            "score": 0.0,
            "source": "invalid_output",
        }

    steps = result.get("steps", [])
    if not isinstance(steps, list):
        steps = []

    return {
        "type": result.get("type", "text"),
        "reply": result.get("reply"),
        "title": result.get("title"),
        "section": result.get("section"),
        "answer": result.get("answer", ""),
        "steps": steps,
        "score": float(result.get("score", 0.0)),
        "source": result.get("source", "unknown"),
    }


def run_single_question(question: str, context: dict | None = None) -> tuple[dict, int]:
    question = clean_question(question)
    context = normalize_context(context or {})

    if not question:
        result = {
            "question": "",
            "type": "text",
            "reply": "Please enter a question.",
            "title": None,
            "section": None,
            "answer": "Please enter a question.",
            "steps": [],
            "score": 0.0,
            "source": "empty",
        }
        return result, 400

    if not MODEL_AVAILABLE or get_model_answer is None:
        result = {
            "question": question,
            "type": "text",
            "reply": "AI backend is not available.",
            "title": None,
            "section": None,
            "answer": MODEL_ERROR or "Model not loaded.",
            "steps": [],
            "score": 0.0,
            "source": "model_unavailable",
        }
        return result, 500

    result = normalize_result(get_model_answer(question, context=context))
    result["question"] = question
    return result, 200


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "Jungle House AI backend is running.",
        "model_available": MODEL_AVAILABLE,
        "model_error": MODEL_ERROR,
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "model_available": MODEL_AVAILABLE,
        "model_error": MODEL_ERROR,
    })


@app.route("/api/dashboard", methods=["GET"])
def dashboard():
    return jsonify({
        "status": "ok",
        "message": "Backend connected successfully",
    })


@app.route("/api/chat/test", methods=["GET"])
def chat_test():
    if not MODEL_AVAILABLE or get_model_answer is None:
        return jsonify({
            "status": "error",
            "message": MODEL_ERROR or "Model not loaded.",
            "results": [],
        }), 500

    results = []
    success_count = 0
    escalation_count = 0

    for question in REAL_JH_TEST_QUESTIONS:
        try:
            result, status = run_single_question(question, context={})
            log_request(question, result=result)
            is_escalation = "escalate" in str(result.get("reply", "")).lower()
            if status == 200 and not is_escalation:
                success_count += 1
            if is_escalation:
                escalation_count += 1

            results.append({
                "question": question,
                "status_code": status,
                "title": result.get("title"),
                "section": result.get("section"),
                "reply": result.get("reply"),
                "score": result.get("score"),
                "source": result.get("source"),
            })
        except Exception as error:
            traceback.print_exc()
            log_request(question, error=str(error))
            results.append({
                "question": question,
                "status_code": 500,
                "title": None,
                "section": None,
                "reply": "There was a problem while generating the answer.",
                "score": 0.0,
                "source": "prediction_error",
            })

    total = len(REAL_JH_TEST_QUESTIONS)
    return jsonify({
        "status": "ok",
        "total_questions": total,
        "answered_without_escalation": success_count,
        "escalation_count": escalation_count,
        "answer_rate": round((success_count / total) * 100, 2) if total else 0.0,
        "results": results,
    })


@app.route("/chat", methods=["POST"])
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}

    try:
        result, status_code = run_single_question(
            question=data.get("question", ""),
            context=data.get("context") or {},
        )
        log_request(result.get("question", ""), result=result)
        return jsonify(result), status_code
    except Exception as error:
        traceback.print_exc()
        question = clean_question(data.get("question", ""))
        log_request(question, error=str(error))
        return jsonify({
            "question": question,
            "type": "text",
            "reply": "There was a problem while generating the answer.",
            "title": None,
            "section": None,
            "answer": f"Prediction error: {error}",
            "steps": [],
            "score": 0.0,
            "source": "prediction_error",
        }), 500


@app.route("/static/<path:filename>", methods=["GET"])
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
