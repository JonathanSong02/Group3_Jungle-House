from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from pathlib import Path
import csv
import json
import traceback

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

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
CORS(app)

ESCALATION_MESSAGE = "No confident answer. Escalate to team lead."

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
    "new bee 3rd day checklist",
    "new bee 1st day checklist",
    "wanna bee onboarding checklist",
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


def ensure_log_files() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_CSV.exists():
        with open(LOG_CSV, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow([
                "timestamp", "question", "title", "section", "type", "score",
                "source", "escalation_ready", "reply", "error"
            ])


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
            "escalation_ready": is_escalation_result(result),
            "reply": str(result.get("reply", result.get("answer", ""))),
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


def call_model_answer(question: str, context: dict | None = None):
    context = normalize_context(context or {})
    try:
        return get_model_answer(question, context=context)
    except TypeError:
        return get_model_answer(question)

def normalize_result(result, default_source="unknown"):
    if isinstance(result, dict):
        return {
            "type": result.get("type", "text"),
            "category": result.get("category"),
            "title": result.get("title"),
            "section": result.get("section"),
            "reply": result.get("reply", result.get("answer", "No answer returned.")),
            "answer": result.get("answer", result.get("reply", "No answer returned.")),
            "purpose": result.get("purpose"),
            "steps": result.get("steps", []),
            "notes": result.get("notes", []),
            "score": float(result.get("score", 0.0)),
            "source": result.get("source", default_source),
            "context": result.get("context", {}),
            "escalation_ready": result.get("escalation_ready", False),
        }

    return {
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
        "source": default_source,
    }


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

    return {
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
        "source": "fallback",
        "context": {},
        "escalation_ready": True,
    }


def process_question(question, context=None):
    question = clean_question(question)
    context = normalize_context(context or {})

    if not question:
        return {
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
            "source": "none",
        }, 400

    model_result = None

    if MODEL_AVAILABLE and get_model_answer is not None:
        try:
            model_result = normalize_result(
                call_model_answer(question, context=context),
                default_source="pytorch_model"
            )
        except Exception as error:
            model_result = {
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
                "source": "pytorch_model_error",
            }

    final_result = choose_final_result(model_result, None)

    return {
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
        "source": final_result.get("source", "unknown"),
        "context": final_result.get("context", {}),
        "escalation_ready": final_result.get("escalation_ready", False),
    }, 200


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
    success_count = 0
    escalation_count = 0

    for question in REAL_JH_TEST_QUESTIONS:
        try:
            result, status = process_question(question, context={})
            log_request(question, result=result)
            is_escalation = is_escalation_result(result)

            if status == 200 and not is_escalation:
                success_count += 1
            if is_escalation:
                escalation_count += 1

            results.append({
                "question": question,
                "status_code": status,
                "title": result.get("title"),
                "section": result.get("section"),
                "reply": result.get("reply", result.get("answer")),
                "score": result.get("score"),
                "source": result.get("source"),
                "escalation_ready": is_escalation,
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
                "escalation_ready": True,
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


# =========================
# AI CHAT ROUTES
# =========================
@app.route("/chat", methods=["POST"])
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}

    try:
        result, status_code = process_question(
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
            "category": None,
            "title": None,
            "section": None,
            "reply": "There was a problem while generating the answer.",
            "answer": f"Prediction error: {error}",
            "purpose": None,
            "steps": [],
            "notes": [],
            "score": 0.0,
            "source": "prediction_error",
        }), 500


@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json(silent=True) or {}

    try:
        result, status_code = process_question(
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
            "category": None,
            "title": None,
            "section": None,
            "reply": "There was a problem while generating the answer.",
            "answer": f"Prediction error: {error}",
            "purpose": None,
            "steps": [],
            "notes": [],
            "score": 0.0,
            "source": "prediction_error",
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
        

@app.route("/static/<path:filename>", methods=["GET"])
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)


# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    verify_manager_account()
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)