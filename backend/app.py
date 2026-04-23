from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

try:
    from predict_intent import get_model_answer
    MODEL_AVAILABLE = True
    MODEL_LOAD_ERROR = None
except Exception as error:
    get_model_answer = None
    MODEL_AVAILABLE = False
    MODEL_LOAD_ERROR = str(error)

try:
    from retrieve import get_answer as get_retrieval_answer
    RETRIEVAL_AVAILABLE = True
    RETRIEVAL_LOAD_ERROR = None
except Exception as error:
    get_retrieval_answer = None
    RETRIEVAL_AVAILABLE = False
    RETRIEVAL_LOAD_ERROR = str(error)

app = Flask(__name__, static_folder="static")
CORS(app)

ESCALATION_MESSAGE = "No confident answer. Escalate to team lead."


# =========================
# DATABASE CONNECTION
# =========================
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="jh_app",
            password="JHapp123!",
            database="jungle_house_ai"
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
def normalize_result(result, default_source="unknown"):
    if isinstance(result, dict):
        return {
            "type": result.get("type", "text"),
            "category": result.get("category"),
            "title": result.get("title"),
            "answer": result.get("answer", "No answer returned."),
            "purpose": result.get("purpose"),
            "steps": result.get("steps", []),
            "notes": result.get("notes", []),
            "score": float(result.get("score", 0.0)),
            "source": result.get("source", default_source),
        }

    return {
        "type": "text",
        "category": None,
        "title": None,
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
        if model_result["type"] == "sop":
            return model_result
        if model_result["score"] >= 0.60:
            return model_result

    if retrieval_result and is_valid_answer(retrieval_result):
        if retrieval_result["score"] >= 0.20:
            return retrieval_result

    if model_result and retrieval_result:
        if retrieval_result["score"] > model_result["score"]:
            return retrieval_result
        return model_result

    if retrieval_result:
        return retrieval_result

    if model_result:
        return model_result

    return {
        "type": "text",
        "category": None,
        "title": None,
        "answer": ESCALATION_MESSAGE,
        "purpose": None,
        "steps": [],
        "notes": [],
        "score": 0.0,
        "source": "fallback",
    }


def process_question(question):
    question = str(question).strip()

    if not question:
        return {
            "question": "",
            "type": "text",
            "category": None,
            "title": None,
            "answer": "Please enter a question.",
            "purpose": None,
            "steps": [],
            "notes": [],
            "score": 0.0,
            "source": "none",
        }, 400

    model_result = None
    retrieval_result = None

    if MODEL_AVAILABLE and get_model_answer is not None:
        try:
            model_result = normalize_result(
                get_model_answer(question),
                default_source="pytorch_model"
            )
        except Exception as error:
            model_result = {
                "type": "text",
                "category": None,
                "title": None,
                "answer": f"Model prediction failed: {error}",
                "purpose": None,
                "steps": [],
                "notes": [],
                "score": 0.0,
                "source": "pytorch_model_error",
            }

    if RETRIEVAL_AVAILABLE and get_retrieval_answer is not None:
        try:
            retrieval_result = normalize_result(
                get_retrieval_answer(question),
                default_source="retrieval"
            )
        except Exception as error:
            retrieval_result = {
                "type": "text",
                "category": None,
                "title": None,
                "answer": f"Retrieval failed: {error}",
                "purpose": None,
                "steps": [],
                "notes": [],
                "score": 0.0,
                "source": "retrieval_error",
            }

    final_result = choose_final_result(model_result, retrieval_result)

    return {
        "question": question,
        "type": final_result.get("type", "text"),
        "category": final_result["category"],
        "title": final_result["title"],
        "answer": final_result["answer"],
        "purpose": final_result.get("purpose"),
        "steps": final_result.get("steps", []),
        "notes": final_result.get("notes", []),
        "score": final_result["score"],
        "source": final_result["source"],
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
        "retrieval_available": RETRIEVAL_AVAILABLE,
        "retrieval_load_error": RETRIEVAL_LOAD_ERROR,
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "model_available": MODEL_AVAILABLE,
        "model_load_error": MODEL_LOAD_ERROR,
        "retrieval_available": RETRIEVAL_AVAILABLE,
        "retrieval_load_error": RETRIEVAL_LOAD_ERROR,
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


# =========================
# AI CHAT ROUTES
# =========================
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    result, status_code = process_question(data.get("question", ""))
    return jsonify(result), status_code


@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json(silent=True) or {}
    result, status_code = process_question(data.get("question", ""))
    return jsonify(result), status_code


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


@app.route("/api/articles/<int:article_id>", methods=["GET"])
def get_article_detail(article_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT article_id, title, content, category
            FROM wiki_article
            WHERE article_id = %s
        """, (article_id,))
        article = cursor.fetchone()

        if not article:
            return jsonify({"message": "Article not found."}), 404

        return jsonify(article), 200

    except mysql.connector.Error as err:
        print("MYSQL ERROR /api/articles/<id>:", err)
        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
        print("GENERAL ERROR /api/articles/<id>:", e)
        return jsonify({"message": f"Server error: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/api/article-links/<int:article_id>", methods=["GET"])
def get_article_links(article_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT link_id, article_id, label, url
            FROM article_links
            WHERE article_id = %s
            ORDER BY link_id ASC
        """, (article_id,))
        links = cursor.fetchall()

        return jsonify(links), 200

    except mysql.connector.Error as err:
        print("MYSQL ERROR /api/article-links:", err)
        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
        print("GENERAL ERROR /api/article-links:", e)
        return jsonify({"message": f"Server error: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    verify_manager_account()
    app.run(host="127.0.0.1", port=5000, debug=True)