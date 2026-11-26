"""Web Push: tell a phone / browser that the AI is done (2026-11-26, step 2).

Standard Web Push written with the packages the backend already has
(`cryptography`, `requests`), so no new dependency:
  * RFC 8291 / RFC 8188 "aes128gcm" message encryption (checked against the
    RFC 8291 Appendix A example in test_web_push.py),
  * RFC 8292 VAPID: the server proves who it is with an ES256-signed token.

The server's key pair is made once and kept in `web_push_key`, so nothing has
to be set up in Railway. Subscriptions (one per browser / phone) are kept in
`web_push_subscription` with the notification words in the user's language.
Only the big push services are ever contacted (the address comes from the
browser, so anything else is refused).

Notifications never contain the question or the answer.
"""

import base64
import hashlib
import json
import os
import threading
import time
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

RECORD_SIZE = 4096
TTL_SECONDS = 3600
SEND_TIMEOUT_SECONDS = 10
TOKEN_LIFETIME_SECONDS = 12 * 3600
SEEN_KEEP_SECONDS = 600
FALLBACK_SUBJECT = "mailto:admin@junglehouse.invalid"
ALLOWED_PUSH_HOST_SUFFIXES = (
    "fcm.googleapis.com",            # Chrome, Edge on Android, most Android browsers
    "push.services.mozilla.com",     # Firefox
    "push.apple.com",                # Safari / iPhone (web.push.apple.com)
    "notify.windows.com",            # Edge on Windows
)
MAX_LABEL_LENGTH = 80


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64url(text):
    text = str(text or "")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _hkdf(salt, ikm, info, length):
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def _public_bytes(public_key):
    return public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


# ---------------------------------------------------------------- encryption
def encrypt(plaintext, ua_public_b64, auth_secret_b64, server_private_key=None, salt=None):
    """aes128gcm body for one push message (RFC 8291 section 3.4, single record)."""
    try:
        ua_public = _unb64url(ua_public_b64)
        auth_secret = _unb64url(auth_secret_b64)
    except Exception as error:
        raise ValueError("bad subscription keys") from error
    if len(ua_public) != 65 or ua_public[0] != 4 or len(auth_secret) != 16:
        raise ValueError("bad subscription keys")
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)

    server_private_key = server_private_key or ec.generate_private_key(ec.SECP256R1())
    as_public = _public_bytes(server_private_key.public_key())
    salt = salt or os.urandom(16)

    ecdh_secret = server_private_key.exchange(ec.ECDH(), ua_key)
    ikm = _hkdf(auth_secret, ecdh_secret, b"WebPush: info\x00" + ua_public + as_public, 32)
    content_key = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    ciphertext = AESGCM(content_key).encrypt(nonce, bytes(plaintext) + b"\x02", None)  # 0x02 = last record
    return salt + RECORD_SIZE.to_bytes(4, "big") + bytes([len(as_public)]) + as_public + ciphertext


# --------------------------------------------------------------------- VAPID
def new_key_pair():
    """(private key PEM text, public key base64url) for VAPID."""
    key = ec.generate_private_key(ec.SECP256R1())
    private_text = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()).decode("ascii")
    return private_text, b64url(_public_bytes(key.public_key()))


def load_private_key(private_text):
    return serialization.load_pem_private_key(private_text.encode("ascii"), password=None)


def vapid_token(private_key, endpoint, subject, now=None):
    parts = urlsplit(endpoint)
    claims = {
        "aud": f"{parts.scheme}://{parts.netloc}",
        "exp": int(now if now is not None else time.time()) + TOKEN_LIFETIME_SECONDS,
        "sub": subject if str(subject or "").startswith(("https://", "mailto:")) else FALLBACK_SUBJECT,
    }
    header = b64url(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64url(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{header}.{body}".encode("ascii")
    r, s = decode_dss_signature(private_key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
    return f"{header}.{body}.{b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


# ---------------------------------------------------------------------- send
def allowed_endpoint(endpoint):
    try:
        parts = urlsplit(str(endpoint or ""))
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
        return False
    return any(host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_PUSH_HOST_SUFFIXES)


def send(subscription, payload, private_key, public_key_b64, post=None):
    """'sent', 'gone' (subscription no longer exists), 'failed' or 'refused'. Never raises."""
    endpoint = subscription.get("endpoint")
    if not allowed_endpoint(endpoint):
        return "refused"
    try:
        body = encrypt(json.dumps(payload).encode("utf-8"), subscription["p256dh"], subscription["auth"])
        headers = {
            "Authorization": f"vapid t={vapid_token(private_key, endpoint, subscription.get('subject'))}, k={public_key_b64}",
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(TTL_SECONDS),
            "Urgency": "high",
        }
        if post is None:
            import requests
            post = requests.post
        response = post(endpoint, data=body, headers=headers, timeout=SEND_TIMEOUT_SECONDS)
    except Exception as error:
        print("WEB PUSH SEND ERROR:", type(error).__name__)
        return "failed"
    if response.status_code in (404, 410):
        return "gone"
    return "sent" if 200 <= response.status_code < 300 else "failed"


# ------------------------------------------------------- "already seen" marks
# The page says "I showed this answer" (POST /api/ai-tasks/<id>/seen) when it
# got the reply while visible, or when Stop was pressed. One gunicorn worker,
# so memory is shared by all requests; a restart only means one extra push.
_seen_lock = threading.Lock()
_seen = {}


def mark_seen(user_id, request_id, now=None):
    now = time.time() if now is None else now
    with _seen_lock:
        for key in [key for key, at in _seen.items() if now - at > SEEN_KEEP_SECONDS]:
            del _seen[key]
        _seen[(int(user_id), str(request_id))] = now


def was_seen(user_id, request_id, now=None):
    now = time.time() if now is None else now
    with _seen_lock:
        at = _seen.get((int(user_id), str(request_id)))
    return at is not None and now - at <= SEEN_KEEP_SECONDS


# ------------------------------------------------------------------ database
def ensure_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS web_push_key (
            web_push_key_id INT NOT NULL AUTO_INCREMENT,
            private_key TEXT NOT NULL,
            public_key VARCHAR(255) NOT NULL,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (web_push_key_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS web_push_subscription (
            web_push_subscription_id INT NOT NULL AUTO_INCREMENT,
            user_id INT NOT NULL,
            endpoint_hash CHAR(64) NOT NULL,
            endpoint TEXT NOT NULL,
            p256dh VARCHAR(255) NOT NULL,
            auth VARCHAR(64) NOT NULL,
            subject VARCHAR(255) NOT NULL,
            labels TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            last_used_at DATETIME NULL,
            PRIMARY KEY (web_push_subscription_id),
            UNIQUE KEY uq_web_push_subscription_endpoint (endpoint_hash),
            KEY idx_web_push_subscription_user (user_id),
            CONSTRAINT fk_web_push_subscription_user FOREIGN KEY (user_id)
                REFERENCES users (user_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


_key_lock = threading.Lock()
_key_cache = None


def server_keys(get_connection):
    """(private key object, public key base64url); made and stored on first use."""
    global _key_cache
    with _key_lock:
        if _key_cache:
            return _key_cache
        conn = cursor = None
        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            ensure_tables(cursor)
            cursor.execute("SELECT private_key, public_key FROM web_push_key ORDER BY web_push_key_id LIMIT 1")
            row = cursor.fetchone()
            if not row:
                private_text, public_text = new_key_pair()
                cursor.execute("INSERT INTO web_push_key (private_key, public_key, created_at) VALUES (%s, %s, NOW())",
                               (private_text, public_text))
                conn.commit()
                # Two servers starting at once: keep whichever row was first.
                cursor.execute("SELECT private_key, public_key FROM web_push_key ORDER BY web_push_key_id LIMIT 1")
                row = cursor.fetchone()
            _key_cache = (load_private_key(row["private_key"]), row["public_key"])
            return _key_cache
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()


def clean_labels(labels):
    labels = labels if isinstance(labels, dict) else {}
    return {key: str(labels.get(key) or "").strip()[:MAX_LABEL_LENGTH] for key in ("chat", "quiz", "view")}


def save_subscription(get_connection, user_id, subscription, labels, subject):
    """Store (or move to this user / refresh) one browser's subscription. Returns False if it is unusable."""
    subscription = subscription if isinstance(subscription, dict) else {}
    keys = subscription.get("keys") if isinstance(subscription.get("keys"), dict) else {}
    endpoint = str(subscription.get("endpoint") or "")
    p256dh, auth = str(keys.get("p256dh") or ""), str(keys.get("auth") or "")
    if len(endpoint) > 2000 or not allowed_endpoint(endpoint) or not p256dh or not auth or len(p256dh) > 255 or len(auth) > 64:
        return False
    try:
        encrypt(b"", p256dh, auth)  # proves the keys are real P-256 / 16-byte values
    except ValueError:
        return False
    subject = subject if str(subject or "").startswith("https://") and len(subject) <= 255 else ""
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        ensure_tables(cursor)
        cursor.execute(
            "INSERT INTO web_push_subscription (user_id, endpoint_hash, endpoint, p256dh, auth, subject, labels, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, NOW()) "
            "ON DUPLICATE KEY UPDATE user_id = VALUES(user_id), endpoint = VALUES(endpoint), p256dh = VALUES(p256dh), "
            "auth = VALUES(auth), subject = VALUES(subject), labels = VALUES(labels)",
            (int(user_id), hashlib.sha256(endpoint.encode("utf-8")).hexdigest(), endpoint, p256dh, auth,
             subject, json.dumps(clean_labels(labels), ensure_ascii=False)),
        )
        conn.commit()
        return True
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def delete_subscription(get_connection, endpoint, user_id=None):
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        ensure_tables(cursor)
        sql = "DELETE FROM web_push_subscription WHERE endpoint_hash = %s"
        params = [hashlib.sha256(str(endpoint or "").encode("utf-8")).hexdigest()]
        if user_id is not None:
            sql += " AND user_id = %s"
            params.append(int(user_id))
        cursor.execute(sql, tuple(params))
        conn.commit()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def subscriptions_for(get_connection, user_id):
    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_tables(cursor)
        cursor.execute("SELECT endpoint, p256dh, auth, subject, labels FROM web_push_subscription WHERE user_id = %s",
                       (int(user_id),))
        return list(cursor.fetchall() or [])
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def notification_for(kind, session_id, labels):
    labels = clean_labels(json.loads(labels) if isinstance(labels, str) else labels)
    title = labels["quiz" if kind == "quiz" else "chat"] or ("AI quiz is ready" if kind == "quiz" else "AI answer is ready")
    url = "/admin/quiz-management" if kind == "quiz" else (f"/chat?aiSession={session_id}" if session_id else "/chat")
    return {"title": title, "body": labels["view"] or "Tap to view", "url": url, "kind": kind,
            "sessionId": session_id, "tag": f"jh-ai-{kind}-{session_id or ''}"}


def notify_user(get_connection, user_id, request_id, kind, session_id, wait_seconds, sleep=time.sleep):
    """Run in a background thread after the reply copy was saved: push unless the page already showed it."""
    try:
        sleep(wait_seconds)
        if was_seen(user_id, request_id):
            return
        subscriptions = subscriptions_for(get_connection, user_id)
        if not subscriptions:
            return
        private_key, public_key = server_keys(get_connection)
        for row in subscriptions:
            outcome = send(row, notification_for(kind, session_id, row.get("labels")), private_key, public_key)
            if outcome == "gone":
                delete_subscription(get_connection, row["endpoint"])
    except Exception as error:
        print("WEB PUSH NOTIFY ERROR:", type(error).__name__)
