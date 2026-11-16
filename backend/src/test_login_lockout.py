"""Tests for the device-based login lockout (login_lockout.py and the login routes in app.py).

No MySQL is needed. The real routes and the real SQL run against a small SQLite database that stands in for
MySQL: `FakeDatabase` translates the few MySQL-only spellings (%s, FOR UPDATE, ON DUPLICATE KEY UPDATE, NOW())
and starts every transaction with BEGIN IMMEDIATE, so transactions take turns the way a MySQL row lock makes
them take turns. That proves the counting logic and the HTTP behaviour. It does NOT prove MySQL's own row
locking; that part must be tested on a real MySQL (see the task report).

Run (from backend/src):
    python -m unittest test_login_lockout -v
"""

import hashlib
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("FLASK_SECRET_KEY", "dummy-test-only-key-not-a-secret-0123456789")
os.environ.setdefault("NOTION_AUTO_SYNC_ENABLED", "false")

from werkzeug.security import generate_password_hash  # noqa: E402

import app as app_module  # noqa: E402
import login_lockout as ll  # noqa: E402

FAST_HASH = "pbkdf2:sha256:1000"          # test-only speed; production hashing is not changed
MANAGER = "manager@junglehouse.com"
STAFF = "staff.a@junglehouse.com"
PENDING = "pending@junglehouse.com"
GHOST = "nobody@junglehouse.com"          # no account uses this email
PASSWORD = "Correct-Horse-9"
WRONG = "Wrong-Password-1"

sqlite3.register_adapter(datetime, lambda value: value.isoformat(" "))
for _declared in ("DATETIME", "TIMESTAMP"):
    sqlite3.register_converter(_declared, lambda raw: datetime.fromisoformat(raw.decode()))

SCHEMA = """
CREATE TABLE roles (role_id INTEGER PRIMARY KEY, role_name TEXT NOT NULL);
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY, full_name TEXT, email TEXT UNIQUE, password_hash TEXT,
    role_id INTEGER, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE login_history (
    login_id INTEGER PRIMARY KEY, user_id INTEGER, email TEXT, full_name TEXT,
    login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, login_status TEXT, ip_address TEXT, device_info TEXT);
CREATE TABLE audit_log (
    audit_id INTEGER PRIMARY KEY, actor_id INTEGER, actor_name TEXT, action TEXT, module TEXT, description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE notification (
    notification_id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, detail TEXT, type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE password_reset_tokens (
    reset_id INTEGER PRIMARY KEY, user_id INTEGER, token_hash TEXT UNIQUE, expires_at DATETIME, used_at DATETIME,
    requested_ip TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE login_rate_limit (
    rate_key TEXT PRIMARY KEY, failed_attempts INTEGER NOT NULL DEFAULT 0, window_started_at DATETIME,
    blocked_until DATETIME, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE login_known_devices (
    known_device_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, device_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_seen_at DATETIME NOT NULL, expires_at DATETIME NOT NULL,
    UNIQUE (user_id, device_hash));
"""


def to_sqlite(sql):
    """MySQL statement -> SQLite statement, or None for the runtime CREATE TABLE statements."""
    text = " ".join(sql.split())
    if re.match(r"(?i)^CREATE TABLE", text):
        return None
    text = text.replace("%s", "?")
    text = re.sub(r"(?i)\s+FOR UPDATE\b", "", text)
    text = re.sub(r"(?i)\(NOW\(\) - INTERVAL \? HOUR\)", "datetime('now', '-' || ? || ' hours')", text)
    text = re.sub(r"(?i)\bNOW\(\)", "CURRENT_TIMESTAMP", text)
    if re.search(r"(?i)ON DUPLICATE KEY UPDATE", text):
        target = "rate_key" if "login_rate_limit" in text else "user_id, device_hash"
        text = re.sub(r"(?i)ON DUPLICATE KEY UPDATE", f"ON CONFLICT({target}) DO UPDATE SET", text)
    return text


class FakeCursor:
    def __init__(self, connection, dictionary):
        self.connection = connection
        self.dictionary = dictionary
        self.rowcount = 0
        self._result = None

    def execute(self, sql, params=None):
        text = to_sqlite(sql)
        self.connection.statements.append(" ".join(sql.split()))
        if text is None:
            self._result = None
            return
        self.connection.begin()
        self._result = self.connection.raw.execute(text, tuple(params or ()))
        self.rowcount = self._result.rowcount

    def _shape(self, row):
        if row is None or not self.dictionary:
            return row
        return dict(zip([column[0] for column in self._result.description], row))

    def fetchone(self):
        return self._shape(self._result.fetchone()) if self._result is not None else None

    def fetchall(self):
        return [self._shape(row) for row in self._result.fetchall()] if self._result is not None else []

    def close(self):
        pass


class FakeConnection:
    def __init__(self, path, log):
        self.raw = sqlite3.connect(path, timeout=30, isolation_level=None, detect_types=sqlite3.PARSE_DECLTYPES)
        self.in_transaction = False
        self.statements = log

    def begin(self):
        if not self.in_transaction:
            self.raw.execute("BEGIN IMMEDIATE")      # one writer at a time, like a held row lock
            self.in_transaction = True

    def start_transaction(self):
        self.begin()

    def cursor(self, dictionary=False):
        return FakeCursor(self, dictionary)

    def commit(self):
        if self.in_transaction:
            self.raw.execute("COMMIT")
            self.in_transaction = False

    def rollback(self):
        if self.in_transaction:
            self.raw.execute("ROLLBACK")
            self.in_transaction = False

    def close(self):
        self.rollback()
        self.raw.close()


class FakeDatabase:
    def __init__(self):
        self.directory = tempfile.mkdtemp(prefix="jh_lockout_")
        self.path = os.path.join(self.directory, "test.sqlite")
        self.statements = []
        setup = sqlite3.connect(self.path)
        setup.executescript(SCHEMA)
        setup.close()

    def connect(self):
        return FakeConnection(self.path, self.statements)

    def run(self, sql, params=()):
        conn = sqlite3.connect(self.path, timeout=30, detect_types=sqlite3.PARSE_DECLTYPES)
        try:
            rows = conn.execute(sql, params).fetchall()
            conn.commit()
            return rows
        finally:
            conn.close()

    def close(self):
        shutil.rmtree(self.directory, ignore_errors=True)


class LockoutTestCase(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()
        self.addCleanup(self.db.close)
        ll._COUNTER_TABLE_READY = False
        ll._DEVICE_TABLE_READY = False
        ll._last_cleanup_at = 0.0

    def connection(self):
        conn = self.db.connect()
        self.addCleanup(conn.close)
        return conn, conn.cursor(dictionary=True)


# --------------------------------------------------------------------------
# login_lockout.py on its own
# --------------------------------------------------------------------------
class CounterTests(LockoutTestCase):
    def attempt(self, counters, ok=False, now=None):
        """One login attempt the way the route does it. -> 'ok', 'wrong' or 'locked'."""
        conn, cursor = self.connection()
        gate = ll.begin_attempt(cursor, counters, now)
        conn.commit()
        if gate.blocked:
            return "locked"
        if ok:
            ll.record_success(cursor, counters)
            conn.commit()
            return "ok"
        gate = ll.record_failure(cursor, counters, now)
        conn.commit()
        return "locked" if gate.blocked else "wrong"

    def test_the_fifth_wrong_password_starts_a_15_minute_lock(self):
        counters = ll.counters_for_login(MANAGER)
        self.assertEqual([self.attempt(counters) for _ in range(5)], ["wrong"] * 4 + ["locked"])
        self.assertEqual(self.attempt(counters, ok=True), "locked")        # even the right password waits

        conn, cursor = self.connection()
        gate = ll.begin_attempt(cursor, counters)
        self.assertTrue(gate.blocked)
        self.assertFalse(gate.newly_blocked)
        self.assertTrue(14 * 60 < gate.retry_after <= 15 * 60)

    def test_more_attempts_during_a_lock_do_not_extend_it(self):
        counters = ll.counters_for_login(MANAGER)
        start = datetime(2026, 11, 16, 9, 0, 0)
        for _ in range(5):
            self.attempt(counters, now=start)
        self.assertEqual(self.attempt(counters, now=start + timedelta(minutes=10)), "locked")
        self.assertEqual(self.attempt(counters, now=start + timedelta(minutes=14, seconds=59)), "locked")
        self.assertEqual(self.attempt(counters, now=start + timedelta(minutes=15, seconds=1)), "wrong")

    def test_a_finished_lock_and_an_old_window_start_clean(self):
        counters = ll.counters_for_login(MANAGER)
        start = datetime(2026, 11, 16, 9, 0, 0)
        for _ in range(5):
            self.attempt(counters, now=start)
        later = start + timedelta(minutes=16)
        self.assertEqual([self.attempt(counters, now=later) for _ in range(4)], ["wrong"] * 4)

        other = ll.counters_for_login(STAFF)
        for _ in range(4):
            self.attempt(other, now=start)
        self.assertEqual(self.attempt(other, now=start + timedelta(minutes=16)), "wrong")   # the 4 old ones expired

    def test_a_correct_password_resets_only_its_own_counter(self):
        unknown = ll.counters_for_login(MANAGER)
        known = ll.counters_for_login(MANAGER, "a" * 64)
        other_account = ll.counters_for_login(STAFF)
        for counters in (unknown, known, other_account):
            for _ in range(4):
                self.attempt(counters)
        self.assertEqual(self.attempt(known, ok=True), "ok")
        self.assertEqual(self.attempt(known), "wrong")              # fresh: back to 1 of 5
        self.assertEqual(self.attempt(unknown), "locked")           # untouched: this was its 5th
        self.assertEqual(self.attempt(other_account), "locked")

    def test_known_device_and_unknown_devices_never_share_a_counter(self):
        unknown, = ll.counters_for_login(MANAGER)
        device_a, = ll.counters_for_login(MANAGER, "a" * 64)
        device_b, = ll.counters_for_login(MANAGER, "b" * 64)
        same_device_other_account, = ll.counters_for_login(STAFF, "a" * 64)
        self.assertEqual(len({unknown.key, device_a.key, device_b.key, same_device_other_account.key}), 4)
        self.assertEqual(unknown.rule, ll.RULE_UNKNOWN_DEVICES)
        self.assertEqual(device_a.rule, ll.RULE_KNOWN_DEVICE)
        self.assertEqual(ll.counters_for_login("  Manager@JungleHouse.com ")[0].key, unknown.key)
        for counter in (unknown, device_a):
            self.assertRegex(counter.key, r"^[0-9a-f]{64}$")       # a hash: no email, no device id

    def test_twenty_simultaneous_guesses_get_only_five_password_checks(self):
        counters = ll.counters_for_login(MANAGER)
        allowed, errors = [], []
        barrier = threading.Barrier(20)

        def guess():
            conn = self.db.connect()
            try:
                barrier.wait(timeout=20)
                gate = ll.begin_attempt(conn.cursor(dictionary=True), counters)
                conn.commit()
                allowed.append(not gate.blocked)
            except Exception as error:      # pragma: no cover - shown by the assertion below
                errors.append(repr(error))
            finally:
                conn.close()

        threads = [threading.Thread(target=guess) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        self.assertEqual(errors, [])
        self.assertEqual(len(allowed), 20)
        self.assertEqual(sum(allowed), ll.RULE_UNKNOWN_DEVICES.max_failures)   # 5 checked, 15 refused unchecked
        self.assertEqual(self.attempt(counters, ok=True), "locked")

    def test_several_counters_per_attempt_work_for_the_later_per_ip_rules(self):
        account, = ll.counters_for_login(MANAGER)
        network = ll.Counter(ll.Rule("ip", 3, 15, 15), hashlib.sha256(b"future-per-ip-counter").hexdigest())
        both = [account, network]
        self.assertEqual([self.attempt(both) for _ in range(3)], ["wrong", "wrong", "locked"])   # the stricter rule
        self.assertEqual(self.attempt([account]), "wrong")           # the account counter itself is not locked
        self.assertEqual(self.attempt(both, ok=True), "locked")      # one locked counter stops the attempt

    def test_cleanup_removes_finished_and_old_rule_rows_but_keeps_live_ones(self):
        now = datetime(2026, 11, 16, 12, 0, 0)
        old_rule_key = hashlib.sha256(f"email|{MANAGER}".encode()).hexdigest()       # the previous per-email rule
        rows = [
            (old_rule_key, 5, now - timedelta(days=3), now - timedelta(days=3)),     # old rule, long finished
            ("finished".ljust(64, "0"), 2, now - timedelta(hours=30), None),         # old window, no lock
            ("recent".ljust(64, "0"), 2, now - timedelta(minutes=5), None),          # still counting
            ("locked".ljust(64, "0"), 5, now - timedelta(hours=30), now + timedelta(minutes=3)),   # lock still on
        ]
        for row in rows:
            self.db.run("INSERT INTO login_rate_limit (rate_key, failed_attempts, window_started_at, blocked_until) "
                        "VALUES (?, ?, ?, ?)", row)
        self.db.run("INSERT INTO login_known_devices (user_id, device_hash, last_seen_at, expires_at) VALUES "
                    "(1, 'expired', ?, ?), (1, 'alive', ?, ?)",
                    (now - timedelta(days=200), now - timedelta(days=20), now, now + timedelta(days=180)))
        self.db.run("INSERT INTO login_history (email, login_status) VALUES (?, 'failed')", (MANAGER,))

        conn, cursor = self.connection()
        ll.cleanup(cursor, now)
        conn.commit()

        left = {row[0].rstrip("0") for row in self.db.run("SELECT rate_key FROM login_rate_limit")}
        self.assertEqual(left, {"recent", "locked"})
        self.assertEqual(self.db.run("SELECT device_hash FROM login_known_devices"), [("alive",)])
        self.assertEqual(self.db.run("SELECT COUNT(*) FROM login_history"), [(1,)])       # history is never touched

    def test_cleanup_is_throttled_per_process(self):
        self.assertTrue(ll.cleanup_is_due())
        self.assertFalse(ll.cleanup_is_due())
        ll._last_cleanup_at -= ll.CLEANUP_EVERY_SECONDS + 1
        self.assertTrue(ll.cleanup_is_due())


class KnownDeviceTests(LockoutTestCase):
    def test_remember_expire_refresh_and_forget(self):
        conn, cursor = self.connection()
        now = datetime(2026, 11, 16, 9, 0, 0)
        self.assertFalse(ll.is_known_device(cursor, 1, "a" * 64, now))
        ll.remember_device(cursor, 1, "a" * 64, now)
        ll.remember_device(cursor, 1, "a" * 64, now)                       # twice = still one row
        ll.remember_device(cursor, 1, "b" * 64, now)
        ll.remember_device(cursor, 2, "a" * 64, now)                       # same browser, another account
        conn.commit()
        self.assertEqual(self.db.run("SELECT COUNT(*) FROM login_known_devices"), [(3,)])
        self.assertTrue(ll.is_known_device(cursor, 1, "a" * 64, now))
        self.assertFalse(ll.is_known_device(cursor, 3, "a" * 64, now))     # known for 1 and 2 only
        self.assertFalse(ll.is_known_device(cursor, 0, "a" * 64, now))     # 0 = an email without an account
        self.assertFalse(ll.is_known_device(cursor, 1, None, now))

        almost = now + timedelta(days=ll.DEVICE_COOKIE_DAYS) - timedelta(minutes=1)
        self.assertTrue(ll.is_known_device(cursor, 1, "a" * 64, almost))
        self.assertFalse(ll.is_known_device(cursor, 1, "a" * 64, almost + timedelta(minutes=2)))

        self.assertEqual(ll.refresh_known_device(cursor, 1, "a" * 64, now + timedelta(hours=1)), "fresh")
        self.assertEqual(ll.refresh_known_device(cursor, 1, "a" * 64, now + timedelta(days=100)), "refreshed")
        self.assertTrue(ll.is_known_device(cursor, 1, "a" * 64, now + timedelta(days=250)))     # expiry moved on
        self.assertEqual(ll.refresh_known_device(cursor, 1, "z" * 64, now), "unknown")
        self.assertEqual(ll.refresh_known_device(cursor, 1, None, now), "unknown")

        ll.forget_devices(cursor, 1, keep_device_hash="b" * 64)
        conn.commit()
        self.assertEqual(self.db.run("SELECT user_id, device_hash FROM login_known_devices ORDER BY user_id"),
                         [(1, "b" * 64), (2, "a" * 64)])
        ll.forget_devices(cursor, 1)
        conn.commit()
        self.assertEqual(self.db.run("SELECT user_id FROM login_known_devices"), [(2,)])

    def test_only_the_newest_devices_of_an_account_are_kept(self):
        conn, cursor = self.connection()
        start = datetime(2026, 11, 16, 9, 0, 0)
        total = ll.MAX_KNOWN_DEVICES_PER_ACCOUNT + 3
        for number in range(total):
            ll.remember_device(cursor, 1, f"{number:064d}", start + timedelta(minutes=number))
        conn.commit()
        kept = [row[0] for row in self.db.run("SELECT device_hash FROM login_known_devices ORDER BY device_hash")]
        self.assertEqual(kept, [f"{number:064d}" for number in range(3, total)])       # the 3 oldest were removed

    def test_device_cookie_is_signed_and_only_the_hash_is_derived_from_it(self):
        device_id = ll.new_device_id()
        self.assertNotEqual(device_id, ll.new_device_id())
        cookie = ll.sign_device_id("secret-one", device_id)
        self.assertEqual(ll.read_device_cookie("secret-one", cookie), (device_id, ll.hash_device_id(device_id)))
        self.assertNotIn(device_id, ll.hash_device_id(device_id))
        for bad in (None, "", "garbage", cookie[:-2] + "xx", cookie + "x", "x" * 600,
                    ll.sign_device_id("another-secret", device_id),          # signed with a different key
                    ll.sign_device_id("secret-one", "short"),                # signed, but not one of our ids
                    ll.sign_device_id("secret-one", {"id": device_id})):
            self.assertEqual(ll.read_device_cookie("secret-one", bad), (None, None), bad)


# --------------------------------------------------------------------------
# The real routes in app.py
# --------------------------------------------------------------------------
class RouteTestCase(LockoutTestCase):
    def setUp(self):
        super().setUp()
        self.db.run("INSERT INTO roles (role_id, role_name) VALUES (1, 'manager'), (2, 'staff')")
        password_hash = generate_password_hash(PASSWORD, method=FAST_HASH)
        self.db.run("INSERT INTO users (user_id, full_name, email, password_hash, role_id, status) VALUES "
                    "(1, 'Mia Manager', ?, ?, 1, 'active'), (2, 'Sam Staff', ?, ?, 2, 'active'), "
                    "(3, 'Pat Pending', ?, ?, 2, 'pending')",
                    (MANAGER, password_hash, STAFF, password_hash, PENDING, password_hash))

        self.notify = Mock(name="create_notification_safe")
        for target, value in (("get_db_connection", self.db.connect), ("create_notification_safe", self.notify),
                              ("_LOGIN_UNKNOWN_ACCOUNT_HASH", generate_password_hash("unused", method=FAST_HASH))):
            patcher = patch.object(app_module, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        app_module.app.config["TESTING"] = True

    def device(self):
        """A separate browser: its own cookie jar."""
        return app_module.app.test_client()

    def csrf(self, client):
        return client.get("/api/auth/csrf").get_json()["csrf_token"]

    def login(self, client, email, password):
        return client.post("/api/auth/login", json={"email": email, "password": password},
                           headers={"X-CSRF-Token": self.csrf(client)})

    def logout(self, client):
        return client.post("/api/auth/logout", headers={"X-CSRF-Token": self.csrf(client)})

    def fail(self, client, email, times):
        return [self.login(client, email, WRONG).status_code for _ in range(times)]

    def device_cookie(self, response):
        return [h for h in response.headers.getlist("Set-Cookie") if h.startswith(ll.DEVICE_COOKIE_NAME + "=")]

    def known_devices(self, user_id):
        return self.db.run("SELECT COUNT(*) FROM login_known_devices WHERE user_id = ?", (user_id,))[0][0]

    def expire_all_locks(self):
        self.db.run("UPDATE login_rate_limit SET blocked_until = ?, window_started_at = ?",
                    (datetime.now() - timedelta(seconds=1), datetime.now() - timedelta(minutes=16)))


class LoginRouteTests(RouteTestCase):
    def test_abuse_case_the_owner_still_signs_in_on_a_known_device(self):
        owner_phone = self.device()
        self.assertEqual(self.login(owner_phone, MANAGER, PASSWORD).status_code, 200)
        self.logout(owner_phone)

        attacker = self.device()
        self.assertEqual(self.fail(attacker, MANAGER, 5), [401, 401, 401, 401, 429])
        self.assertEqual(self.login(attacker, MANAGER, WRONG).status_code, 429)
        # Every unknown device is locked for this account, even with the right password ...
        self.assertEqual(self.login(self.device(), MANAGER, PASSWORD).status_code, 429)
        # ... but the device the owner used before is not.
        self.assertEqual(self.login(owner_phone, MANAGER, WRONG).status_code, 401)      # its own counter: 1 of 5
        response = self.login(owner_phone, MANAGER, PASSWORD)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["email"], MANAGER)
        # Other accounts are not affected either.
        self.assertEqual(self.login(self.device(), STAFF, PASSWORD).status_code, 200)

    def test_a_known_device_locks_only_itself(self):
        tablet = self.device()
        self.login(tablet, MANAGER, PASSWORD)
        self.logout(tablet)
        self.assertEqual(self.fail(tablet, MANAGER, 5), [401, 401, 401, 401, 429])
        self.assertEqual(self.login(tablet, MANAGER, PASSWORD).status_code, 429)        # this device waits
        self.assertEqual(self.login(self.device(), MANAGER, PASSWORD).status_code, 200)   # a new device is fine
        # The tablet is locked for that account only: another person can still sign in on it.
        self.assertEqual(self.login(tablet, STAFF, PASSWORD).status_code, 200)

    def test_lock_response_carries_the_server_countdown_and_ends_on_time(self):
        attacker = self.device()
        self.fail(attacker, MANAGER, 4)
        response = self.login(attacker, MANAGER, WRONG)
        body = response.get_json()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(body["code"], "LOGIN_RATE_LIMITED")
        self.assertEqual(body["message"], "Too many wrong attempts on this device. Please try again later.")
        self.assertEqual(body["retry_after_seconds"], 15 * 60)
        self.assertEqual(response.headers["Retry-After"], "900")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

        self.db.run("UPDATE login_rate_limit SET blocked_until = ?", (datetime.now() + timedelta(seconds=100),))
        later = self.login(attacker, MANAGER, WRONG)
        self.assertTrue(95 <= later.get_json()["retry_after_seconds"] <= 100)            # the time that is really left
        self.assertEqual(later.headers["Retry-After"], str(later.get_json()["retry_after_seconds"]))

        self.expire_all_locks()
        self.assertEqual(self.login(attacker, MANAGER, PASSWORD).status_code, 200)

    def test_an_unregistered_email_behaves_exactly_like_a_real_account(self):
        real = [self.login(self.device(), MANAGER, WRONG) for _ in range(6)]
        ghost = [self.login(self.device(), GHOST, WRONG) for _ in range(6)]
        for real_response, ghost_response in zip(real, ghost):
            self.assertEqual(real_response.status_code, ghost_response.status_code)
            self.assertEqual(real_response.get_json(), ghost_response.get_json())
            self.assertEqual(self.device_cookie(real_response), [])
            self.assertEqual(self.device_cookie(ghost_response), [])
        self.assertEqual([r.status_code for r in ghost], [401, 401, 401, 401, 429, 429])
        self.assertEqual(real[0].get_json(), {"code": "INVALID_CREDENTIALS", "message": "Email or password is incorrect."})
        # Failed attempts for both are in the login history, as before.
        history = dict(self.db.run("SELECT email, COUNT(*) FROM login_history WHERE login_status = 'failed' GROUP BY email"))
        self.assertEqual(history, {MANAGER: 5, GHOST: 5})

    def test_a_correct_password_resets_only_that_device_and_account(self):
        phone = self.device()
        self.login(phone, MANAGER, PASSWORD)
        self.logout(phone)

        self.fail(self.device(), MANAGER, 4)                         # unknown devices: 4 of 5
        self.assertEqual(self.fail(phone, MANAGER, 4), [401] * 4)    # the phone: 4 of 5
        self.assertEqual(self.login(phone, MANAGER, PASSWORD).status_code, 200)        # resets the phone only
        self.logout(phone)
        self.assertEqual(self.fail(phone, MANAGER, 4), [401] * 4)    # the phone starts from 0 again
        self.assertEqual(self.login(self.device(), MANAGER, WRONG).status_code, 429)   # unknown: this was the 5th

    def test_the_device_cookie_never_replaces_the_password(self):
        phone = self.device()
        granted = self.login(phone, MANAGER, PASSWORD)
        cookie, = self.device_cookie(granted)
        self.logout(phone)
        # A known device with a wrong password is refused, and without a session it has no access at all.
        self.assertEqual(self.login(phone, MANAGER, WRONG).status_code, 401)
        self.assertEqual(phone.get("/api/auth/me").status_code, 401)
        self.assertEqual(phone.get("/api/articles").status_code, 401)

        attributes = [part.strip().lower() for part in cookie.split(";")[1:]]
        self.assertIn("httponly", attributes)
        self.assertIn("samesite=lax", attributes)
        self.assertIn("path=/api", attributes)
        self.assertIn(f"max-age={180 * 24 * 60 * 60}", attributes)
        self.assertNotIn("secure", attributes)                       # plain http in this test, as for the session

        with patch.dict(app_module.app.config, {"SESSION_COOKIE_SECURE": True}):
            secure_cookie, = self.device_cookie(self.login(self.device(), STAFF, PASSWORD))
        self.assertIn("secure", [part.strip().lower() for part in secure_cookie.split(";")[1:]])

    def test_only_a_hash_of_the_device_id_is_stored_and_nothing_secret_is_logged(self):
        phone = self.device()
        cookie, = self.device_cookie(self.login(phone, MANAGER, PASSWORD))
        value = cookie.split(";")[0].split("=", 1)[1]
        device_id, device_hash = ll.read_device_cookie(app_module.app.config["SECRET_KEY"], value)
        self.assertEqual(self.db.run("SELECT user_id, device_hash FROM login_known_devices"), [(1, device_hash)])
        self.fail(self.device(), MANAGER, 5)

        stored = repr([self.db.run(f"SELECT * FROM {table}") for table in
                       ("login_known_devices", "login_rate_limit", "audit_log", "login_history")])
        for secret in (device_id, value, PASSWORD, WRONG):
            self.assertNotIn(secret, stored)
        self.assertNotIn(MANAGER, repr(self.db.run("SELECT * FROM login_rate_limit")))   # counters hold hashes only

    def test_forged_or_foreign_device_cookies_count_as_unknown_devices(self):
        staff_tablet = self.device()
        staff_cookie, = self.device_cookie(self.login(staff_tablet, STAFF, PASSWORD))     # known for STAFF only
        self.logout(staff_tablet)
        self.fail(self.device(), MANAGER, 5)                                             # unknown devices locked

        forged = self.device()
        forged.set_cookie(ll.DEVICE_COOKIE_NAME, "not-a-real-cookie", path="/api")
        wrong_key = self.device()
        wrong_key.set_cookie(ll.DEVICE_COOKIE_NAME, ll.sign_device_id("attacker-key", ll.new_device_id()), path="/api")
        self_made = self.device()
        self_made.set_cookie(ll.DEVICE_COOKIE_NAME,
                             ll.sign_device_id(app_module.app.config["SECRET_KEY"], ll.new_device_id()), path="/api")
        for client in (forged, wrong_key, self_made, staff_tablet):
            self.assertEqual(self.login(client, MANAGER, PASSWORD).status_code, 429)
        self.assertTrue(staff_cookie)

    def test_old_per_email_locks_do_not_carry_over_and_history_is_kept(self):
        old_key = hashlib.sha256(f"email|{MANAGER}".encode()).hexdigest()
        self.db.run("INSERT INTO login_rate_limit (rate_key, failed_attempts, window_started_at, blocked_until) "
                    "VALUES (?, 5, ?, ?)", (old_key, datetime.now(), datetime.now() + timedelta(minutes=14)))
        self.db.run("INSERT INTO login_history (user_id, email, login_status) VALUES (1, ?, 'failed')", (MANAGER,))

        self.assertEqual(self.login(self.device(), MANAGER, PASSWORD).status_code, 200)
        self.assertEqual(self.db.run("SELECT login_status FROM login_history ORDER BY login_id"),
                         [("failed",), ("success",)])

    def test_pending_accounts_keep_their_answer_and_are_not_remembered(self):
        response = self.login(self.device(), PENDING, PASSWORD)
        self.assertEqual((response.status_code, response.get_json()["code"]), (403, "ACCOUNT_PENDING_APPROVAL"))
        self.assertEqual(self.device_cookie(response), [])
        self.assertEqual(self.known_devices(3), 0)

    def test_sign_in_still_works_when_the_lockout_storage_is_broken(self):
        with patch.object(ll, "begin_attempt", side_effect=RuntimeError("storage down")):
            self.assertEqual(self.login(self.device(), MANAGER, WRONG).status_code, 401)
            self.assertEqual(self.login(self.device(), MANAGER, PASSWORD).status_code, 200)
        with patch.object(ll, "remember_device", side_effect=RuntimeError("storage down")):
            response = self.login(self.device(), STAFF, PASSWORD)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.device_cookie(response), [])

    def test_without_the_known_device_table_the_shared_counter_still_protects(self):
        # e.g. the new table could not be created: nobody is a known device, but the lockout itself still works.
        with patch.object(ll, "ensure_known_device_table", side_effect=RuntimeError("cannot create table")):
            response = self.login(self.device(), MANAGER, PASSWORD)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.device_cookie(response), [])
            self.assertEqual(self.fail(self.device(), MANAGER, 5), [401, 401, 401, 401, 429])
            self.assertEqual(self.login(self.device(), MANAGER, PASSWORD).status_code, 429)
            self.assertEqual(self.login(self.device(), STAFF, PASSWORD).status_code, 200)

    def test_missing_fields_and_csrf_are_unchanged(self):
        client = self.device()
        self.assertEqual(client.post("/api/auth/login", json={"email": MANAGER, "password": PASSWORD}).status_code, 403)
        missing = client.post("/api/auth/login", json={"email": MANAGER}, headers={"X-CSRF-Token": self.csrf(client)})
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(self.db.run("SELECT COUNT(*) FROM login_rate_limit"), [(0,)])


class KnownDeviceRouteTests(RouteTestCase):
    def lock_unknown_devices(self, email=MANAGER):
        self.assertEqual(self.fail(self.device(), email, 5)[-1], 429)

    def test_an_existing_session_becomes_a_known_device_on_auth_me(self):
        laptop = self.device()
        self.login(laptop, MANAGER, PASSWORD)
        # As if the session was created before this feature went live: no device cookie, no device row.
        laptop.delete_cookie(ll.DEVICE_COOKIE_NAME, path="/api")
        self.db.run("DELETE FROM login_known_devices")

        response = laptop.get("/api/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.device_cookie(response)), 1)
        self.assertEqual(self.known_devices(1), 1)
        again = laptop.get("/api/auth/me")                               # already known: nothing more to do
        self.assertEqual(self.device_cookie(again), [])
        self.assertEqual(self.known_devices(1), 1)

        self.logout(laptop)
        self.lock_unknown_devices()
        self.assertEqual(self.login(laptop, MANAGER, PASSWORD).status_code, 200)

    def test_auth_me_without_a_session_gives_no_device_cookie(self):
        stranger = self.device()
        response = stranger.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.device_cookie(response), [])
        self.assertEqual(self.db.run("SELECT COUNT(*) FROM login_known_devices"), [(0,)])

    def test_a_known_device_is_refreshed_once_a_day_not_on_every_request(self):
        laptop = self.device()
        self.login(laptop, MANAGER, PASSWORD)
        self.assertEqual(self.device_cookie(laptop.get("/api/auth/me")), [])
        self.db.run("UPDATE login_known_devices SET last_seen_at = ?", (datetime.now() - timedelta(days=2),))
        self.assertEqual(len(self.device_cookie(laptop.get("/api/auth/me"))), 1)        # expiry pushed forward
        self.assertEqual(self.device_cookie(laptop.get("/api/auth/me")), [])

    def reset_token(self, user_id, raw="reset-token-for-tests"):
        self.db.run("INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
                    (user_id, app_module.hash_password_reset_token(raw), datetime.now() + timedelta(minutes=20)))
        return raw

    def test_password_reset_lets_the_owner_in_on_a_new_device_during_an_attack(self):
        old_phone = self.device()
        self.login(old_phone, MANAGER, PASSWORD)
        self.logout(old_phone)
        self.lock_unknown_devices()

        new_laptop = self.device()
        self.assertEqual(self.login(new_laptop, MANAGER, PASSWORD).status_code, 429)     # new device: locked out
        new_password = "Brand-New-Pass-7"
        response = new_laptop.post("/api/auth/reset-password", headers={"X-CSRF-Token": self.csrf(new_laptop)},
                                   json={"token": self.reset_token(1), "new_password": new_password,
                                         "confirm_password": new_password})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.device_cookie(response)), 1)
        self.assertEqual(self.known_devices(1), 1)                    # only the device that did the reset

        self.assertEqual(self.login(new_laptop, MANAGER, WRONG).status_code, 401)         # the password is still needed
        self.assertEqual(self.login(new_laptop, MANAGER, new_password).status_code, 200)
        # The old phone is no longer a known device (and the old password is gone).
        self.assertEqual(self.login(old_phone, MANAGER, new_password).status_code, 429)
        self.assertEqual(self.login(self.device(), MANAGER, new_password).status_code, 429)   # attack lock still on

    def test_password_reset_clears_the_lock_of_the_device_that_did_it(self):
        phone = self.device()
        self.login(phone, MANAGER, PASSWORD)
        self.logout(phone)
        self.assertEqual(self.fail(phone, MANAGER, 5)[-1], 429)       # the owner forgot the password on a known device
        new_password = "Brand-New-Pass-7"
        phone.post("/api/auth/reset-password", headers={"X-CSRF-Token": self.csrf(phone)},
                   json={"token": self.reset_token(1), "new_password": new_password, "confirm_password": new_password})
        self.assertEqual(self.login(phone, MANAGER, new_password).status_code, 200)

    def test_a_failed_reset_marks_nothing(self):
        client = self.device()
        response = client.post("/api/auth/reset-password", headers={"X-CSRF-Token": self.csrf(client)},
                               json={"token": "wrong-token", "new_password": "Brand-New-Pass-7",
                                     "confirm_password": "Brand-New-Pass-7"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.device_cookie(response), [])
        self.assertEqual(self.db.run("SELECT COUNT(*) FROM login_known_devices"), [(0,)])

    def test_change_password_keeps_this_device_and_forgets_the_others(self):
        phone, laptop = self.device(), self.device()
        self.login(phone, MANAGER, PASSWORD)
        self.logout(phone)
        token = self.login(laptop, MANAGER, PASSWORD).get_json()["csrf_token"]
        self.assertEqual(self.known_devices(1), 2)

        new_password = "Changed-Pass-8"
        response = laptop.put("/api/profile/1/change-password", headers={"X-CSRF-Token": token},
                              json={"current_password": PASSWORD, "new_password": new_password,
                                    "confirm_password": new_password})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.known_devices(1), 1)
        self.assertEqual(laptop.get("/api/auth/me").status_code, 200)    # the session on this device goes on

        self.logout(laptop)
        self.lock_unknown_devices()
        self.assertEqual(self.login(phone, MANAGER, new_password).status_code, 429)      # forgotten: unknown again
        self.assertEqual(self.login(laptop, MANAGER, new_password).status_code, 200)     # still known


class MonitoringTests(RouteTestCase):
    def events(self):
        return self.db.run("SELECT actor_name, action, module, description FROM audit_log ORDER BY audit_id")

    def test_each_lock_is_recorded_once_for_security_monitoring(self):
        attacker = self.device()
        self.fail(attacker, MANAGER, 5)
        self.fail(attacker, MANAGER, 3)                                # blocked requests add no more entries
        (actor, action, module, description), = self.events()
        self.assertEqual((actor, action, module), ("System", "Login locked for unknown devices", "Authentication"))
        self.assertIn(MANAGER, description)
        self.assertIn("15 minutes", description)
        self.assertNotIn("No account uses this email", description)

        phone = self.device()
        self.login(phone, STAFF, PASSWORD)
        self.logout(phone)
        self.fail(phone, STAFF, 5)
        self.fail(self.device(), GHOST, 5)
        actions = [(action, description) for _, action, _, description in self.events()]
        self.assertEqual([action for action, _ in actions],
                         ["Login locked for unknown devices", "Login locked on a known device",
                          "Login locked for unknown devices"])
        self.assertIn(STAFF, actions[1][1])
        self.assertIn("No account uses this email", actions[2][1])
        for _, description in actions:
            self.assertNotIn(WRONG, description)

    def test_the_owner_is_told_once_when_unknown_devices_are_locked(self):
        self.fail(self.device(), MANAGER, 5)
        self.notify.assert_called_once()
        call = self.notify.call_args.kwargs
        self.assertEqual((call["user_id"], call["title"]), (1, "Sign-in attempts blocked"))
        self.assertIn("Devices you have already used are not affected", call["detail"])

        # A notice from the last 12 hours stops a second one; an older one does not.
        self.db.run("INSERT INTO notification (user_id, title, detail) VALUES (1, 'Sign-in attempts blocked', 'x')")
        self.expire_all_locks()
        self.fail(self.device(), MANAGER, 5)
        self.notify.assert_called_once()
        self.db.run("UPDATE notification SET created_at = datetime('now', '-13 hours')")
        self.expire_all_locks()
        self.fail(self.device(), MANAGER, 5)
        self.assertEqual(self.notify.call_count, 2)

    def test_no_owner_notice_for_a_known_device_lock_or_an_unregistered_email(self):
        phone = self.device()
        self.login(phone, MANAGER, PASSWORD)
        self.logout(phone)
        self.fail(phone, MANAGER, 5)
        self.fail(self.device(), GHOST, 5)
        self.fail(self.device(), PENDING, 5)
        self.notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
