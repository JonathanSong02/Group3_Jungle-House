from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash

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
    return mysql.connector.connect(
        host="localhost",
        user="jh_app",
        password="JHapp123!",
        database="jungle_house_ai"
    )


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


# =========================
# AUTH - REGISTER
# =========================
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()

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

        cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.rollback()
            return jsonify({"message": "Email is already registered."}), 409

        cursor.execute(
            "SELECT role_id, role_name FROM roles WHERE role_name = %s",
            (role,)
        )
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
              AND r.role_name = %s
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
        if conn:
            conn.rollback()
        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
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
    data = request.get_json()

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
                r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.email = %s
            LIMIT 1
        """, (email,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"message": "Invalid email or password."}), 401

        if user["status"] != "active":
            return jsonify({"message": "This account is inactive. Please contact the manager."}), 403

        if not check_password_hash(user["password_hash"], password):
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
            except Exception:
                pass

            return jsonify({"message": "Invalid email or password."}), 401

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

        return jsonify({
            "message": "Login successful.",
            "user": {
                "id": user["user_id"],
                "name": user["full_name"],
                "email": user["email"],
                "role": user["role_name"]
            }
        }), 200

    except mysql.connector.Error as err:
        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
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

        # start with the safest columns only
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


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)