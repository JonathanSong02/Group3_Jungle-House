"""Saved copies of AI chat / AI quiz replies ("AI keeps running", 2026-11-26).

The page still gets its reply the normal way. A copy of exactly the same reply
is also saved here, per signed-in user and request_id, so a page that was
closed, put in the phone background or lost its connection while waiting can
fetch the answer later (GET /api/ai-tasks/<request_id>). Nothing here changes
how a question is answered.

Copies are deleted after 7 days. The table is created at runtime with exactly
the definition of migration 0008, so nothing breaks before 0008 is applied.
"""

import json
import threading
import time

KEEP_DAYS = 7
CLEANUP_EVERY_SECONDS = 600
MAX_REQUEST_ID_LENGTH = 64

_cleanup_lock = threading.Lock()
_last_cleanup = 0.0


def ensure_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_task_result (
            ai_task_result_id INT NOT NULL AUTO_INCREMENT,
            user_id INT NOT NULL,
            request_id VARCHAR(64) NOT NULL,
            kind VARCHAR(20) NOT NULL,
            http_status INT NOT NULL,
            result MEDIUMTEXT NOT NULL,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (ai_task_result_id),
            UNIQUE KEY uq_ai_task_result_request (user_id, request_id),
            CONSTRAINT fk_ai_task_result_user FOREIGN KEY (user_id)
                REFERENCES users (user_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def _cleanup_due():
    global _last_cleanup
    with _cleanup_lock:
        now = time.monotonic()
        if _last_cleanup and now - _last_cleanup < CLEANUP_EVERY_SECONDS:
            return False
        _last_cleanup = now
        return True


def save_result(get_connection, user_id, request_id, kind, http_status, body):
    """Store (or replace) one reply copy. Never raises: a failed save only means no copy."""
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        ensure_table(cursor)
        cursor.execute(
            "INSERT INTO ai_task_result (user_id, request_id, kind, http_status, result, created_at) "
            "VALUES (%s, %s, %s, %s, %s, NOW()) "
            "ON DUPLICATE KEY UPDATE kind = VALUES(kind), http_status = VALUES(http_status), "
            "result = VALUES(result), created_at = VALUES(created_at)",
            (user_id, request_id, kind, int(http_status), body),
        )
        if _cleanup_due():
            cursor.execute(f"DELETE FROM ai_task_result WHERE created_at < NOW() - INTERVAL {KEEP_DAYS} DAY")
        conn.commit()
    except Exception as error:
        print("AI TASK RESULT SAVE ERROR:", type(error).__name__)
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            conn.close()


def fetch_result(get_connection, user_id, request_id):
    """{kind, http_status, result} for this user's request, or None."""
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_table(cursor)
        cursor.execute(
            "SELECT kind, http_status, result FROM ai_task_result "
            "WHERE user_id = %s AND request_id = %s LIMIT 1",
            (user_id, request_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {"kind": row["kind"], "http_status": int(row["http_status"]), "result": json.loads(row["result"])}
    except Exception as error:
        print("AI TASK RESULT FETCH ERROR:", type(error).__name__)
        return None
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            conn.close()
