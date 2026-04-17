from pathlib import Path
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

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
CORS(app)


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

    return {
        "type": result.get("type", "text"),
        "reply": result.get("reply"),
        "title": result.get("title"),
        "section": result.get("section"),
        "answer": result.get("answer", ""),
        "steps": result.get("steps", []),
        "score": float(result.get("score", 0.0)),
        "source": result.get("source", "unknown"),
    }


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


@app.route("/chat", methods=["POST"])
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()
    context = data.get("context") or {}

    if not question:
        return jsonify({
            "question": "",
            "type": "text",
            "reply": "Please enter a question.",
            "title": None,
            "section": None,
            "answer": "Please enter a question.",
            "steps": [],
            "score": 0.0,
            "source": "empty",
        }), 400

    if not MODEL_AVAILABLE or get_model_answer is None:
        return jsonify({
            "question": question,
            "type": "text",
            "reply": "AI backend is not available.",
            "title": None,
            "section": None,
            "answer": MODEL_ERROR or "Model not loaded.",
            "steps": [],
            "score": 0.0,
            "source": "model_unavailable",
        }), 500

    try:
        result = normalize_result(get_model_answer(question, context=context))
        return jsonify({
            "question": question,
            **result
        }), 200
    except Exception as error:
        traceback.print_exc()
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