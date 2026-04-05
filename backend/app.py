from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from werkzeug.security import check_password_hash

app = Flask(__name__)
CORS(app)

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="jh_app",
        password="JHapp123!",
        database="jungle_house_ai"
    )

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
            except:
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
        print("MYSQL ERROR:", err)
        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
        print("GENERAL ERROR:", e)
        return jsonify({"message": f"Server error: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

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

        # 1. Check email exists
        cursor.execute(
            "SELECT user_id FROM users WHERE email = %s",
            (email,)
        )
        existing_user = cursor.fetchone()

        if existing_user:
            conn.rollback()
            return jsonify({"message": "Email is already registered."}), 409

        # 2. Check role
        cursor.execute(
            "SELECT role_id, role_name FROM roles WHERE role_name = %s",
            (role,)
        )
        role_row = cursor.fetchone()

        if not role_row:
            conn.rollback()
            return jsonify({"message": "Invalid role selected."}), 400

        # 3. Check registration key
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

        # 4. Insert user
        password_hash = generate_password_hash(password)

        cursor.execute("""
            INSERT INTO users (full_name, email, password_hash, role_id, status)
            VALUES (%s, %s, %s, %s, 'active')
        """, (full_name, email, password_hash, role_row["role_id"]))

        new_user_id = cursor.lastrowid

        # 5. Mark key as used
        cursor.execute("""
            UPDATE registration_keys
            SET is_used = TRUE,
                used_by = %s,
                used_at = NOW()
            WHERE key_id = %s
        """, (new_user_id, key_row["key_id"]))

        conn.commit()

        return jsonify({
            "message": "Registration successful. You can now log in."
        }), 201
    
    except mysql.connector.Error as err:
        if conn:
            conn.rollback()
        print("MYSQL ERROR:", err)
        return jsonify({"message": f"Database error: {str(err)}"}), 500

    except Exception as e:
        if conn:
            conn.rollback()
        print("GENERAL ERROR:", e)
        return jsonify({"message": f"Server error: {str(e)}"}), 500       

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"message": f"Server error: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    app.run(debug=True)