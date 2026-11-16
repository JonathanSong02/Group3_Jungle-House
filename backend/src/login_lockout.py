"""Login lockout rules (Part 1: device based, the client IP is NOT used).

Why: the old rule locked an EMAIL for everyone after 5 wrong passwords, so anybody could lock the manager out
by typing wrong passwords on purpose.

Rules
-----
* Known device  = a browser that has signed in to this account before. It carries a signed, HttpOnly device
  cookie; the server stores only a SHA-256 hash of the random id, linked to the account. A known device has its
  OWN counter for that account: 5 wrong passwords lock only that device, for that account.
* Unknown device = every request without a valid device cookie for that account. All unknown devices share ONE
  counter per account: 5 wrong passwords lock unknown devices for that account. Known devices are never blocked
  by it, so the real owner can still sign in on a device they used before.
* The device cookie only selects which counter is used. It never replaces the password.

Counting is safe under parallel requests: an attempt is reserved under a row lock BEFORE the password is checked
(`begin_attempt`), so 20 simultaneous guesses still get at most 5 password checks.

Storage: the existing `login_rate_limit` table (one row per counter, keyed by a SHA-256 hash) and the new
`login_known_devices` table. Nothing here keeps a counter in process memory.

Part 2 (per-IP rules such as password spraying) is not built. It plugs in by adding a `Rule` below and returning
one more `Counter` from `counters_for_login`; `begin_attempt`, `record_failure` and `record_success` already work
on a list of counters.

All functions take a DB cursor that returns rows as dictionaries (mysql.connector `dictionary=True`).
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from itsdangerous import BadSignature, URLSafeSerializer


# =========================================================
# CONFIGURATION: the one place for every lockout value
# =========================================================
@dataclass(frozen=True)
class Rule:
    scope: str            # short name, also part of the counter key
    max_failures: int     # wrong passwords before the lock
    window_minutes: int   # the wrong passwords must happen inside this window
    block_minutes: int    # how long the lock lasts


# Rule A: one known device, one account.
RULE_KNOWN_DEVICE = Rule(scope="device", max_failures=5, window_minutes=15, block_minutes=15)
# All unknown devices together, one account (the stricter form of rule C).
RULE_UNKNOWN_DEVICES = Rule(scope="unknown", max_failures=5, window_minutes=15, block_minutes=15)

DEVICE_COOKIE_NAME = "jh_wiki_device"
DEVICE_COOKIE_PATH = "/api"            # login, reset password and /auth/me are all under /api
DEVICE_COOKIE_DAYS = 180               # a device stays known this long after its last sign-in
DEVICE_REFRESH_AFTER_HOURS = 24        # how often an active device's expiry is pushed forward
MAX_KNOWN_DEVICES_PER_ACCOUNT = 20     # the oldest ones are removed above this number

COUNTER_RETENTION_HOURS = 24           # finished counters older than this are deleted
CLEANUP_EVERY_SECONDS = 600            # how often one process runs the cleanup (a throttle, not a counter)

# Old per-email rows used sha256("email|<email>"). Every new key starts with this prefix, so an old lock can
# never match a new counter: nobody stays locked by the old rule.
_KEY_PREFIX = "lockout-v2"
_DEVICE_COOKIE_SALT = "jh-wiki-device-cookie-v1"
_DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{40,64}$")
_MAX_COOKIE_LENGTH = 512

_last_cleanup_at = 0.0


# =========================================================
# TABLES
# =========================================================
_COUNTER_TABLE_READY = False
_DEVICE_TABLE_READY = False


def ensure_counter_table(cursor):
    """The failure counters. This table already exists in production (the old per-email rule created it)."""
    global _COUNTER_TABLE_READY

    if _COUNTER_TABLE_READY:
        return

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS login_rate_limit (
            rate_key CHAR(64) PRIMARY KEY,
            failed_attempts INT NOT NULL DEFAULT 0,
            window_started_at DATETIME NULL,
            blocked_until DATETIME NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_login_rate_limit_blocked_until (blocked_until)
        )
    """)
    _COUNTER_TABLE_READY = True


def ensure_known_device_table(cursor):
    """The new table: which devices have signed in to which account (hash of the device id only)."""
    global _DEVICE_TABLE_READY

    if _DEVICE_TABLE_READY:
        return

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS login_known_devices (
            known_device_id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            device_hash CHAR(64) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_at DATETIME NOT NULL,
            expires_at DATETIME NOT NULL,
            UNIQUE KEY uq_login_known_devices_user_device (user_id, device_hash),
            INDEX idx_login_known_devices_expires_at (expires_at),
            CONSTRAINT fk_login_known_devices_user
                FOREIGN KEY (user_id) REFERENCES users(user_id)
                ON DELETE CASCADE
        )
    """)
    _DEVICE_TABLE_READY = True


def ensure_login_lockout_tables(cursor):
    """Create both tables on demand (same approach as the other runtime tables). Safe to run again."""
    ensure_counter_table(cursor)
    ensure_known_device_table(cursor)


def lookup_known_device(cursor, user_id, device_hash):
    """is_known_device() that can never break a login.

    If the known-device table cannot be created or read, every device simply counts as unknown: the lockout
    still works with the shared per-account counter, only the known-device exemption is missing.
    """
    try:
        ensure_known_device_table(cursor)
        return is_known_device(cursor, user_id, device_hash)
    except Exception:
        print("LOGIN LOCKOUT ERROR: Could not read the known devices; treating this device as unknown.")
        return False


# =========================================================
# COUNTERS
# =========================================================
@dataclass(frozen=True)
class Counter:
    rule: Rule
    key: str   # SHA-256 hex. The table never holds the email, the device id or anything else readable.


@dataclass(frozen=True)
class Gate:
    """Result of a check. `blocked` requests must not have their password checked."""
    blocked: bool = False
    retry_after: int = 0          # seconds until the lock ends
    newly_blocked: bool = False   # True only for the request that started the lock (for monitoring)
    scope: str | None = None      # which rule blocked


def normalize_email(email):
    return str(email or "").strip().lower()


def _counter(rule, *parts):
    raw = "|".join((_KEY_PREFIX, rule.scope) + tuple(str(part) for part in parts))
    return Counter(rule=rule, key=hashlib.sha256(raw.encode("utf-8")).hexdigest())


def counters_for_login(email, known_device_hash=None):
    """Which counters one login attempt uses.

    A known device uses ONLY its own counter, so it is never blocked by what unknown devices do.
    Emails that do not exist get a counter exactly like real accounts (no user enumeration).
    """
    email = normalize_email(email)
    if known_device_hash:
        return [_counter(RULE_KNOWN_DEVICE, known_device_hash, email)]
    return [_counter(RULE_UNKNOWN_DEVICES, email)]


def _seconds_left(until, now):
    return max(1, int((until - now).total_seconds()))


def _lock_row(cursor, key):
    """Create the row if needed and lock it until COMMIT, so parallel requests take turns."""
    # ON DUPLICATE KEY UPDATE takes the exclusive row lock straight away. (A plain INSERT IGNORE would take a
    # shared lock first, and two requests upgrading it at the same time can deadlock.)
    cursor.execute("""
        INSERT INTO login_rate_limit (rate_key, failed_attempts)
        VALUES (%s, 0)
        ON DUPLICATE KEY UPDATE rate_key = rate_key
    """, (key,))
    cursor.execute("""
        SELECT failed_attempts, window_started_at, blocked_until
        FROM login_rate_limit
        WHERE rate_key = %s
        FOR UPDATE
    """, (key,))
    return cursor.fetchone() or {}


def _save_row(cursor, key, attempts, window_started_at, blocked_until):
    cursor.execute("""
        UPDATE login_rate_limit
        SET failed_attempts = %s,
            window_started_at = %s,
            blocked_until = %s
        WHERE rate_key = %s
    """, (attempts, window_started_at, blocked_until, key))


def begin_attempt(cursor, counters, now=None):
    """Reserve one login attempt on every counter. Call BEFORE checking the password, then COMMIT at once.

    The attempt is counted here, under the row lock, so simultaneous requests cannot all slip past the limit.
    `record_success` clears the counter when the password turns out to be correct; otherwise the reservation
    stays as the failure and `record_failure` decides whether the lock starts.
    """
    now = now or datetime.now()
    rows = [(counter, _lock_row(cursor, counter.key)) for counter in sorted(counters, key=lambda c: c.key)]

    # 1. An active lock on any counter stops the attempt. Further attempts do not extend the lock.
    blocked = [
        (counter, row["blocked_until"]) for counter, row in rows
        if row.get("blocked_until") and row["blocked_until"] > now
    ]
    if blocked:
        counter, until = max(blocked, key=lambda item: item[1])
        return Gate(blocked=True, retry_after=_seconds_left(until, now), scope=counter.rule.scope)

    # 2. Work out the current window of every counter.
    states = []
    full = []
    for counter, row in rows:
        attempts = int(row.get("failed_attempts") or 0)
        window_started_at = row.get("window_started_at")
        window = timedelta(minutes=counter.rule.window_minutes)
        if row.get("blocked_until") or not window_started_at or now - window_started_at > window:
            attempts, window_started_at = 0, now          # a finished lock or an old window starts clean
        states.append((counter, attempts, window_started_at))
        if attempts >= counter.rule.max_failures:
            full.append((counter, attempts, window_started_at))

    # 3. Every slot of the window is already taken (attempts still being checked, or failed ones whose lock
    #    has not been written yet): lock now and do not check this password.
    if full:
        longest = 0
        scope = None
        for counter, attempts, window_started_at in full:
            block_seconds = counter.rule.block_minutes * 60
            _save_row(cursor, counter.key, attempts, window_started_at, now + timedelta(seconds=block_seconds))
            if block_seconds > longest:
                longest, scope = block_seconds, counter.rule.scope
        return Gate(blocked=True, retry_after=longest, newly_blocked=True, scope=scope)

    # 4. Take one slot on every counter.
    for counter, attempts, window_started_at in states:
        _save_row(cursor, counter.key, attempts + 1, window_started_at, None)
    return Gate()


def record_failure(cursor, counters, now=None):
    """The password was wrong. The attempt is already counted; start the lock when the limit is reached."""
    now = now or datetime.now()
    active = []       # (seconds left, scope) of locks that already existed
    started = []      # (seconds, scope) of locks started by this failure

    for counter in sorted(counters, key=lambda c: c.key):
        cursor.execute("""
            SELECT failed_attempts, window_started_at, blocked_until
            FROM login_rate_limit
            WHERE rate_key = %s
            FOR UPDATE
        """, (counter.key,))
        row = cursor.fetchone()
        if not row:
            continue      # cleared in the meantime by a correct password on the same counter

        until = row.get("blocked_until")
        if until and until > now:
            active.append((_seconds_left(until, now), counter.rule.scope))
            continue

        attempts = int(row.get("failed_attempts") or 0)
        if attempts >= counter.rule.max_failures:
            block_seconds = counter.rule.block_minutes * 60
            _save_row(cursor, counter.key, attempts, row.get("window_started_at"),
                      now + timedelta(seconds=block_seconds))
            started.append((block_seconds, counter.rule.scope))

    if started:
        seconds, scope = max(started)
        return Gate(blocked=True, retry_after=seconds, newly_blocked=True, scope=scope)
    if active:
        seconds, scope = max(active)
        return Gate(blocked=True, retry_after=seconds, scope=scope)
    return Gate()


def record_success(cursor, counters):
    """The password was correct: reset ONLY the counters of this device and this account."""
    for counter in counters:
        cursor.execute("DELETE FROM login_rate_limit WHERE rate_key = %s", (counter.key,))


def clear_device_counter(cursor, email, device_hash):
    """Used after a password reset: the device that completed it starts with a clean counter."""
    record_success(cursor, counters_for_login(email, device_hash))


# =========================================================
# DEVICE COOKIE
# =========================================================
def new_device_id():
    return secrets.token_urlsafe(32)


def hash_device_id(device_id):
    """The only form of the device id that is ever stored."""
    return hashlib.sha256(f"device|{device_id}".encode("utf-8")).hexdigest()


def _serializer(secret_key):
    return URLSafeSerializer(secret_key, salt=_DEVICE_COOKIE_SALT)


def sign_device_id(secret_key, device_id):
    return _serializer(secret_key).dumps(device_id)


def read_device_cookie(secret_key, cookie_value):
    """-> (device_id, device_hash), or (None, None) for a missing, forged or malformed cookie."""
    value = str(cookie_value or "")
    if not value or len(value) > _MAX_COOKIE_LENGTH:
        return None, None
    try:
        device_id = _serializer(secret_key).loads(value)
    except BadSignature:
        return None, None
    except Exception:
        return None, None
    if not isinstance(device_id, str) or not _DEVICE_ID_RE.match(device_id):
        return None, None
    return device_id, hash_device_id(device_id)


def device_cookie_max_age():
    return DEVICE_COOKIE_DAYS * 24 * 60 * 60


# =========================================================
# KNOWN DEVICES
# =========================================================
def is_known_device(cursor, user_id, device_hash, now=None):
    """True when this device has signed in to this account before (and has not expired).

    Call it with user_id 0 for an email that has no account, so both cases run the same query.
    """
    if not device_hash:
        return False
    now = now or datetime.now()
    cursor.execute("""
        SELECT known_device_id
        FROM login_known_devices
        WHERE user_id = %s
          AND device_hash = %s
          AND expires_at > %s
        LIMIT 1
    """, (int(user_id or 0), device_hash, now))
    return cursor.fetchone() is not None


def remember_device(cursor, user_id, device_hash, now=None):
    """Link this device to this account (or push its expiry forward). Keeps at most the newest N per account."""
    now = now or datetime.now()
    expires_at = now + timedelta(days=DEVICE_COOKIE_DAYS)
    cursor.execute("""
        INSERT INTO login_known_devices (user_id, device_hash, last_seen_at, expires_at)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE last_seen_at = %s, expires_at = %s
    """, (int(user_id), device_hash, now, expires_at, now, expires_at))

    cursor.execute("""
        SELECT known_device_id
        FROM login_known_devices
        WHERE user_id = %s
        ORDER BY last_seen_at DESC, known_device_id DESC
    """, (int(user_id),))
    extra = [row["known_device_id"] for row in (cursor.fetchall() or [])][MAX_KNOWN_DEVICES_PER_ACCOUNT:]
    for known_device_id in extra:
        cursor.execute("DELETE FROM login_known_devices WHERE known_device_id = %s", (known_device_id,))


def refresh_known_device(cursor, user_id, device_hash, now=None):
    """-> 'unknown', 'fresh' (nothing to do) or 'refreshed' (expiry pushed forward; renew the cookie too)."""
    if not device_hash:
        return "unknown"
    now = now or datetime.now()
    cursor.execute("""
        SELECT known_device_id, last_seen_at
        FROM login_known_devices
        WHERE user_id = %s
          AND device_hash = %s
          AND expires_at > %s
        LIMIT 1
    """, (int(user_id), device_hash, now))
    row = cursor.fetchone()
    if not row:
        return "unknown"
    last_seen_at = row.get("last_seen_at")
    if last_seen_at and now - last_seen_at < timedelta(hours=DEVICE_REFRESH_AFTER_HOURS):
        return "fresh"
    cursor.execute("""
        UPDATE login_known_devices
        SET last_seen_at = %s, expires_at = %s
        WHERE known_device_id = %s
    """, (now, now + timedelta(days=DEVICE_COOKIE_DAYS), row["known_device_id"]))
    return "refreshed"


def forget_devices(cursor, user_id, keep_device_hash=None):
    """Remove an account's known devices (password changed or reset), optionally keeping the current one."""
    if keep_device_hash:
        cursor.execute(
            "DELETE FROM login_known_devices WHERE user_id = %s AND device_hash <> %s",
            (int(user_id), keep_device_hash),
        )
    else:
        cursor.execute("DELETE FROM login_known_devices WHERE user_id = %s", (int(user_id),))


# =========================================================
# CLEANUP
# =========================================================
def cleanup(cursor, now=None):
    """Delete finished counters and expired devices so the tables do not grow forever.

    A counter is finished when its lock (if any) is over and its window started more than
    COUNTER_RETENTION_HOURS ago. This also removes the rows of the old per-email rule. Login history is a
    different table and is never touched.
    """
    now = now or datetime.now()
    cutoff = now - timedelta(hours=COUNTER_RETENTION_HOURS)
    cursor.execute("""
        DELETE FROM login_rate_limit
        WHERE (blocked_until IS NULL OR blocked_until < %s)
          AND (window_started_at IS NULL OR window_started_at < %s)
    """, (now, cutoff))
    cursor.execute("DELETE FROM login_known_devices WHERE expires_at < %s", (now,))


def cleanup_is_due():
    """True at most once per CLEANUP_EVERY_SECONDS in this process."""
    global _last_cleanup_at

    current = time.monotonic()
    if _last_cleanup_at and current - _last_cleanup_at < CLEANUP_EVERY_SECONDS:
        return False
    _last_cleanup_at = current
    return True
