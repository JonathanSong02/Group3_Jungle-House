"""Private image references. No runtime DDL and no trust in client file paths."""
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from db_helper import get_db_connection
from image_embedding_helper import image_sha256

TTL_DAYS = 7


class AttachmentError(ValueError):
    pass


def valid_chat_key(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,96}", value))


def register_attachment(owner, chat, path, mime):
    if not owner or not valid_chat_key(chat):
        raise AttachmentError("A valid chat is required for image uploads.")
    path = Path(path)
    reference = secrets.token_hex(32)
    digest = image_sha256(path)
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""SELECT observations FROM chat_attachments
            WHERE owner_id = %s AND chat_key = %s AND image_hash = %s
            AND expires_at > UTC_TIMESTAMP() AND observations IS NOT NULL
            ORDER BY created_at DESC LIMIT 1""", (owner, chat, digest))
        cached = cursor.fetchone() or {}
        cursor.execute("""INSERT INTO chat_attachments
            (attachment_id, owner_id, chat_key, storage_name, mime_type, image_hash, expires_at, observations)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (reference, owner, chat, path.name, mime, digest,
             datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=TTL_DAYS), cached.get("observations")))
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    return reference


def load_attachment(owner, chat, reference, folder):
    if not valid_chat_key(chat) or not isinstance(reference, str) or not re.fullmatch(r"[a-f0-9]{64}", reference):
        raise AttachmentError("Attachment unavailable. Please attach the image again.")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""SELECT * FROM chat_attachments WHERE attachment_id = %s
            AND owner_id = %s AND chat_key = %s AND expires_at > UTC_TIMESTAMP()""", (reference, owner, chat))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()
    if not row:
        raise AttachmentError("Attachment unavailable. Please attach the image again.")
    root = Path(folder).resolve()
    path = (root / row["storage_name"]).resolve()
    if path.parent != root or not path.is_file() or image_sha256(path) != row["image_hash"]:
        raise AttachmentError("Attachment unavailable. Please attach the image again.")
    row["path"] = path
    try:
        row["observations"] = json.loads(row.get("observations") or "null")
    except (ValueError, TypeError):
        row["observations"] = None
    return row


def save_observations(owner, chat, reference, observations):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""UPDATE chat_attachments SET observations = %s WHERE attachment_id = %s
            AND owner_id = %s AND chat_key = %s AND expires_at > UTC_TIMESTAMP()""",
            (json.dumps(observations), reference, owner, chat))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def authorize_file(owner, storage_name):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT owner_id, expires_at > UTC_TIMESTAMP() AS valid FROM chat_attachments WHERE storage_name = %s", (storage_name,))
        rows = cursor.fetchall()
        if any(row["owner_id"] == owner and row["valid"] for row in rows):
            return True
        # A current escalation attachment is visible to its existing reviewers;
        # a published approved answer is shared KB evidence for active employees.
        cursor.execute("""SELECT e.escalation_id, e.asked_by,
            (SELECT q.status FROM review_queue q WHERE q.escalation_id = e.escalation_id
             ORDER BY q.review_id DESC LIMIT 1) AS review_status
            FROM escalation e WHERE e.image_url = %s AND COALESCE(e.is_deleted, 0) = 0""",
            ("/static/uploads/chat/" + storage_name,))
        escalations = cursor.fetchall()
        if any(row.get("asked_by") == owner for row in escalations):
            return True
        if any(row.get("review_status") in {"approved", "published"} for row in escalations):
            return True
        if escalations:
            cursor.execute("SELECT r.role_name FROM users u JOIN roles r ON u.role_id = r.role_id WHERE u.user_id = %s", (owner,))
            user = cursor.fetchone() or {}
            return str(user.get("role_name", "")).lower().replace(" ", "").replace("_", "") in {"manager", "admin", "teamlead", "teamleader"}
        return False
    finally:
        cursor.close()
        conn.close()
