"""A stored password hash can never be used as the password (login, change password).

Uses the SQLite stand-in database and sign-in helpers from test_login_lockout.py, so the real routes run
without MySQL.

Run (from backend/src):
    python -m unittest test_password_check -v
"""

import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(SRC_DIR.parent / "tools"))
os.environ.setdefault("FLASK_SECRET_KEY", "dummy-test-only-key-not-a-secret-0123456789")
os.environ.setdefault("NOTION_AUTO_SYNC_ENABLED", "false")
os.environ.setdefault("DOCUMENT_TEXT_BACKFILL", "false")

from werkzeug.security import generate_password_hash  # noqa: E402

import test_login_lockout as t  # noqa: E402
import app as app_module  # noqa: E402
import legacy_password_report as report_tool  # noqa: E402
from password_check import classify_stored_password, looks_like_password_hash, verify_password  # noqa: E402

CHINESE_WRONG = "错误的密码123"
CHINESE_RIGHT = "我的密码Secure1"
LEGACY_PLAIN = "Legacy-Pass-7"
SCRYPT = generate_password_hash(t.PASSWORD)                                   # what the app creates today
PBKDF2 = generate_password_hash(t.PASSWORD, method="pbkdf2:sha256:600000")    # older Werkzeug default


class RuleTests(unittest.TestCase):
    def test_hash_shapes_are_recognised(self):
        for value in (SCRYPT, PBKDF2, f"  {SCRYPT}\n",
                      "sha256$abcdefgh$" + "a" * 64,                                 # old Werkzeug
                      "pbkdf2_sha256$600000$saltsalt$Zm9vYmFyYmF6cXV4",              # Django style
                      "$2b$12$" + "A" * 53, "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",
                      "5f4dcc3b5aa765d61d8327deb882cf99", "5F4DCC3B5AA765D61D8327DEB882CF99", "a" * 64):
            self.assertTrue(looks_like_password_hash(value), value[:20])

    def test_plain_text_is_not_a_hash(self):
        for value in ("Password1", "Pa$$word1", "abc$def", "hello world", "Legacy-Pass-7", "a" * 33, "密码"):
            self.assertFalse(looks_like_password_hash(value), value)
        for value in ("", None, "   "):
            self.assertFalse(looks_like_password_hash(value))

    def test_classification_for_the_report(self):
        self.assertEqual(classify_stored_password(SCRYPT), "verifiable")
        self.assertEqual(classify_stored_password(PBKDF2), "verifiable")
        self.assertEqual(classify_stored_password("$2b$12$" + "A" * 53), "other_hash")
        self.assertEqual(classify_stored_password("sha256$abcdefgh$" + "a" * 64), "other_hash")
        self.assertEqual(classify_stored_password(LEGACY_PLAIN), "plaintext")
        self.assertEqual(classify_stored_password(None), "empty")
        self.assertEqual(classify_stored_password("  "), "empty")

    def test_the_stored_hash_itself_is_never_accepted(self):
        for stored in (SCRYPT, PBKDF2, f"{SCRYPT}\n"):
            self.assertEqual(verify_password(stored, stored), (False, False))
            self.assertEqual(verify_password(stored, stored.strip()), (False, False))
        md5 = "5f4dcc3b5aa765d61d8327deb882cf99"
        self.assertEqual(verify_password(md5, md5), (False, False))       # a hash shape we cannot verify: refused

    def test_correct_and_wrong_passwords(self):
        self.assertEqual(verify_password(SCRYPT, t.PASSWORD), (True, False))
        self.assertEqual(verify_password(PBKDF2, t.PASSWORD), (True, False))
        self.assertEqual(verify_password(f" {SCRYPT} ", t.PASSWORD), (True, False))
        self.assertEqual(verify_password(SCRYPT, t.WRONG), (False, False))

    def test_non_ascii_input_never_raises(self):
        chinese_hash = generate_password_hash(CHINESE_RIGHT)
        self.assertEqual(verify_password(chinese_hash, CHINESE_RIGHT), (True, False))
        self.assertEqual(verify_password(SCRYPT, CHINESE_WRONG), (False, False))
        self.assertEqual(verify_password(LEGACY_PLAIN, CHINESE_WRONG), (False, True))
        self.assertEqual(verify_password("旧密码", "旧密码"), (True, True))
        self.assertEqual(verify_password(SCRYPT, "\ud800lone surrogate"), (False, False))
        self.assertEqual(verify_password(LEGACY_PLAIN, "\ud800"), (False, True))
        self.assertEqual(verify_password(SCRYPT, "emoji 🔑"), (False, False))

    def test_legacy_plain_text_and_odd_input(self):
        self.assertEqual(verify_password(LEGACY_PLAIN, LEGACY_PLAIN), (True, True))
        self.assertEqual(verify_password(LEGACY_PLAIN, "legacy-pass-7"), (False, True))
        for password in (None, "", 123, ["x"]):
            self.assertEqual(verify_password(SCRYPT, password), (False, False))
        for stored in (None, "", "   "):
            self.assertEqual(verify_password(stored, "None"), (False, False))      # NULL never matches "None"
        self.assertEqual(verify_password("scrypt:bad$salt$abcd", "x"), (False, False))  # malformed hash: no error


class LoginTests(t.RouteTestCase):
    def stored_hash(self, user_id=1):
        return self.db.run("SELECT password_hash FROM users WHERE user_id = ?", (user_id,))[0][0]

    def history(self, email):
        return [row[0] for row in self.db.run("SELECT login_status FROM login_history WHERE email = ? ORDER BY login_id", (email,))]

    def test_typing_the_stored_hash_fails_counts_and_changes_nothing(self):
        stored = self.stored_hash()
        attacker = self.device()
        statuses = [self.login(attacker, t.MANAGER, stored) for _ in range(5)]
        self.assertEqual([r.status_code for r in statuses], [401, 401, 401, 401, 429])
        self.assertEqual(statuses[0].get_json(), {"code": "INVALID_CREDENTIALS", "message": "Email or password is incorrect."})
        self.assertEqual(self.stored_hash(), stored)                               # not replaced
        self.assertEqual(self.history(t.MANAGER), ["failed"] * 5)
        self.assertEqual(self.login(self.device(), t.MANAGER, stored).status_code, 429)   # still locked, still refused

    def test_the_correct_password_signs_in_as_before(self):
        client = self.device()
        response = self.login(client, t.MANAGER, t.PASSWORD)
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["user"]["email"], t.MANAGER)
        self.assertTrue(body["csrf_token"])
        self.assertEqual(len(self.device_cookie(response)), 1)
        self.assertEqual(client.get("/api/auth/me").status_code, 200)
        self.assertEqual(self.history(t.MANAGER), ["success"])

    def test_a_wrong_chinese_password_is_a_normal_failure_not_a_500(self):
        client = self.device()
        responses = [self.login(client, t.MANAGER, CHINESE_WRONG) for _ in range(5)]
        self.assertEqual([r.status_code for r in responses], [401, 401, 401, 401, 429])
        self.assertEqual(responses[0].get_json()["message"], "Email or password is incorrect.")
        self.assertEqual(self.history(t.MANAGER), ["failed"] * 5)

    def test_a_correct_non_ascii_password_works(self):
        self.db.run("UPDATE users SET password_hash = ? WHERE user_id = 2", (generate_password_hash(CHINESE_RIGHT),))
        self.assertEqual(self.login(self.device(), t.STAFF, CHINESE_RIGHT).status_code, 200)

    def test_a_legacy_plain_text_account_signs_in_once_and_is_upgraded(self):
        self.db.run("UPDATE users SET password_hash = ? WHERE user_id = 2", (LEGACY_PLAIN,))
        with patch.object(app_module, "check_password_for_unknown_account",
                          wraps=app_module.check_password_for_unknown_account) as dummy:
            self.assertEqual(self.login(self.device(), t.STAFF, CHINESE_WRONG).status_code, 401)
            self.assertEqual(self.login(self.device(), t.STAFF, LEGACY_PLAIN).status_code, 200)
            self.assertEqual(dummy.call_count, 2)                # same hashing time as a hashed account
        upgraded = self.stored_hash(2)
        self.assertNotEqual(upgraded, LEGACY_PLAIN)
        self.assertEqual(classify_stored_password(upgraded), "verifiable")
        self.assertEqual(verify_password(upgraded, LEGACY_PLAIN), (True, False))
        self.assertEqual(self.login(self.device(), t.STAFF, LEGACY_PLAIN).status_code, 200)   # now through the hash
        self.assertEqual(self.login(self.device(), t.STAFF, upgraded).status_code, 401)       # and never the hash

    def test_an_account_without_a_stored_password_cannot_sign_in(self):
        self.db.run("UPDATE users SET password_hash = NULL WHERE user_id = 2")
        self.assertEqual(self.login(self.device(), t.STAFF, "None").status_code, 401)

    def test_unknown_email_answers_exactly_like_a_wrong_password(self):
        for password in (t.WRONG, CHINESE_WRONG, self.stored_hash()):
            known = self.login(self.device(), t.MANAGER, password)
            unknown = self.login(self.device(), t.GHOST, password)
            self.assertEqual((known.status_code, known.get_json()), (unknown.status_code, unknown.get_json()))


class ChangePasswordTests(t.RouteTestCase):
    NEW = "Changed-Pass-8"

    def change(self, current):
        client = self.device()
        token = self.login(client, t.MANAGER, t.PASSWORD).get_json()["csrf_token"]
        return client.put("/api/profile/1/change-password", headers={"X-CSRF-Token": token},
                          json={"current_password": current, "new_password": self.NEW, "confirm_password": self.NEW})

    def stored_hash(self):
        return self.db.run("SELECT password_hash FROM users WHERE user_id = 1")[0][0]

    def test_the_hash_as_current_password_is_rejected(self):
        stored = self.stored_hash()
        response = self.change(stored)
        self.assertEqual((response.status_code, response.get_json()["message"]), (401, "Current password is incorrect."))
        self.assertEqual(self.stored_hash(), stored)

    def test_a_wrong_chinese_current_password_is_rejected_not_a_500(self):
        response = self.change(CHINESE_WRONG)
        self.assertEqual(response.status_code, 401)

    def test_the_correct_current_password_works(self):
        stored = self.stored_hash()
        response = self.change(t.PASSWORD)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(self.stored_hash(), stored)
        self.assertEqual(verify_password(self.stored_hash(), self.NEW), (True, False))
        self.assertEqual(self.login(self.device(), t.MANAGER, self.NEW).status_code, 200)

    def test_a_legacy_plain_text_current_password_still_works(self):
        client = self.device()
        token = self.login(client, t.MANAGER, t.PASSWORD).get_json()["csrf_token"]
        self.db.run("UPDATE users SET password_hash = ? WHERE user_id = 1", (LEGACY_PLAIN,))
        # A session that belongs to that stored value (the password fingerprint check stays on).
        with client.session_transaction() as signed_session:
            signed_session["password_fingerprint"] = app_module.password_session_fingerprint(LEGACY_PLAIN)
        wrong = client.put("/api/profile/1/change-password", headers={"X-CSRF-Token": token},
                           json={"current_password": CHINESE_WRONG, "new_password": self.NEW, "confirm_password": self.NEW})
        self.assertEqual(wrong.status_code, 401)
        response = client.put("/api/profile/1/change-password", headers={"X-CSRF-Token": token},
                              json={"current_password": LEGACY_PLAIN, "new_password": self.NEW, "confirm_password": self.NEW})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(classify_stored_password(self.stored_hash()), "verifiable")
        self.assertEqual(verify_password(self.stored_hash(), self.NEW), (True, False))


class ReportToolTests(unittest.TestCase):
    ROWS = [
        {"user_id": 1, "email": "mia.manager@junglehouse.com", "status": "active", "password_hash": SCRYPT, "role_name": "manager"},
        {"user_id": 2, "email": "jo@junglehouse.com", "status": "active", "password_hash": LEGACY_PLAIN, "role_name": "staff"},
        {"user_id": 3, "email": "x@junglehouse.com", "status": "inactive", "password_hash": None, "role_name": "staff"},
        {"user_id": 4, "email": "old@junglehouse.com", "status": "active", "password_hash": "$2b$12$" + "Q" * 53, "role_name": None},
        {"user_id": 5, "email": "no-at-sign", "status": "pending", "password_hash": "Another-Plain-1", "role_name": "teamlead"},
    ]

    def fake_db(self):
        db = Mock()
        db.rows.return_value = [dict(row) for row in self.ROWS]
        return db

    def test_counts_masked_emails_and_never_a_hash(self):
        output = report_tool.render(report_tool.collect(self.fake_db()))
        self.assertIn("Accounts checked: 5", output)
        self.assertIn("Recognised hash this backend can verify: 1", output)
        self.assertIn("Legacy plain-text password (not a hash). Upgraded to a hash on the next successful sign-in: 2", output)
        self.assertIn("No password stored. This account cannot sign in until the password is reset: 1", output)
        self.assertIn("cannot verify. This account cannot sign in until the password is reset: 1", output)
        self.assertIn("NOT a recognised hash format (plain text or empty): 3", output)
        self.assertIn("user_id=2  role=staff  status=active  email=j***@junglehouse.com", output)
        self.assertIn("email=***", output)
        for row in self.ROWS:
            secret = row["password_hash"] or ""
            for start in range(0, max(len(secret) - 6, 0)):
                self.assertNotIn(secret[start:start + 7], output)          # not even a fragment
            if "@" in row["email"]:
                self.assertNotIn(row["email"], output)
        self.assertNotIn("legacy sign-in path can be removed", output)

    def test_zero_legacy_accounts_says_the_path_can_go(self):
        db = Mock()
        db.rows.return_value = [dict(self.ROWS[0])]
        self.assertIn("the legacy sign-in path can be removed", report_tool.render(report_tool.collect(db)))

    def test_read_only_guard_refuses_writes_before_running_them(self):
        conn = Mock()
        db = report_tool.ReadOnly(conn)
        for sql in ("UPDATE users SET password_hash = 'x'", "DELETE FROM users", "  insert into x values (1)", "SET x = 1"):
            with self.assertRaises(RuntimeError):
                db.rows(sql)
        conn.cursor.return_value.execute.assert_not_called()
        db.rows("SELECT 1")
        conn.cursor.return_value.execute.assert_called_once()

    def test_session_is_read_only_and_errors_print_no_credentials(self):
        conn = Mock()
        with patch("mysql.connector.connect", return_value=conn):
            report_tool.connect()
        conn.cursor.return_value.execute.assert_called_once_with("SET SESSION TRANSACTION READ ONLY")
        with patch.dict(os.environ, {"MYSQL_PASSWORD": "super-secret-value", "MYSQL_HOST": "db.internal.example"}), \
                patch("mysql.connector.connect", side_effect=RuntimeError("cannot reach db.internal.example with super-secret-value")):
            err = io.StringIO()
            with patch("sys.stderr", err), redirect_stdout(io.StringIO()):
                self.assertEqual(report_tool.main([]), 2)
        self.assertNotIn("super-secret-value", err.getvalue())
        self.assertNotIn("db.internal.example", err.getvalue())

    def test_email_masking(self):
        self.assertEqual(report_tool.mask_email("jane.doe@junglehouse.com"), "j***@junglehouse.com")
        self.assertEqual(report_tool.mask_email("a@b.c"), "a***@b.c")
        self.assertEqual(report_tool.mask_email(""), "***")
        self.assertEqual(report_tool.mask_email("@junglehouse.com"), "***")
        self.assertEqual(report_tool.mask_email(None), "***")


if __name__ == "__main__":
    unittest.main()
