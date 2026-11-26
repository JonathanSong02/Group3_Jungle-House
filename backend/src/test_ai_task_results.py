"""AI keeps running after the page is left (2026-11-26).

The chat / AI-quiz reply is also saved (per user + request_id) so a page that
was closed, put in the background or lost its connection can fetch it later.
These tests check that the saved copy is exactly what was sent, that replies
themselves never change, and that a user can only read their own copies.
No database, login or AI is needed. Run:
python -m unittest discover -s backend/src -p test_ai_task_results.py
"""

import json
import os
import unittest
from unittest import mock

os.environ.setdefault("FLASK_SECRET_KEY", "dummy-test-only-key-not-a-secret-0123456789")
os.environ.setdefault("NOTION_AUTO_SYNC_ENABLED", "false")
os.environ.setdefault("IMAGE_INDEX_WORKER_ENABLED", "false")
os.environ.setdefault("DOCUMENT_TEXT_BACKFILL", "false")

import app as app_module  # noqa: E402
import ai_task_results  # noqa: E402

app = app_module.app


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        self.conn.statements.append((" ".join(sql.split()), params))
        if self.conn.fail:
            raise RuntimeError("database down")

    def fetchone(self):
        return self.conn.row

    def close(self):
        pass


class FakeConnection:
    def __init__(self, row=None, fail=False):
        self.row, self.fail, self.statements, self.committed, self.closed = row, fail, [], False, False

    def cursor(self, dictionary=False):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def run_hook(path, body, endpoint, status=200, json_reply=True):
    """Calls the real after_request hook on a hand-made reply; returns (reply, saves)."""
    saves = []
    with app.test_request_context(path, method="POST", json=body):
        from flask import g, request
        request.url_rule = mock.Mock(endpoint=endpoint)
        g.auth_user = {"user_id": 7}  # what require_authenticated_api sets for a signed-in user
        with mock.patch.object(app_module, "current_auth_user_id", return_value=7), \
                mock.patch.object(app_module, "run_in_background",
                                  side_effect=lambda fn, *a: fn(*a) if fn is ai_task_results.save_result else None), \
                mock.patch.object(app_module.ai_task_results, "save_result",
                                  side_effect=lambda _conn, *a: saves.append(a)):
            if json_reply:
                reply = app.response_class(json.dumps({"reply": "Open cabinet 3", "source": "ai"}),
                                           status=status, mimetype="application/json")
            else:
                reply = app.response_class(b"plain", status=status, mimetype="text/plain")
            before = reply.get_data()
            reply = app_module.save_ai_task_result_copy(reply)
            return reply, before, saves


class SaveCopyHookTests(unittest.TestCase):
    def test_chat_reply_is_saved_exactly_as_sent(self):
        reply, before, saves = run_hook("/api/chat", {"question": "x", "request_id": "abc-1"}, "chat")
        self.assertEqual(saves, [(7, "abc-1", "chat", 200, before.decode("utf-8"))])
        self.assertEqual(reply.get_data(), before)  # the reply itself never changes

    def test_quiz_reply_and_error_status_are_saved(self):
        _, before, saves = run_hook("/api/admin/quizzes/ai-generate", {"request_id": "q-9"}, "ai_generate_quiz", status=500)
        self.assertEqual(saves, [(7, "q-9", "quiz", 500, before.decode("utf-8"))])

    def test_nothing_saved_without_request_id(self):
        _, _, saves = run_hook("/api/chat", {"question": "x", "force_escalate": True}, "chat")
        self.assertEqual(saves, [])

    def test_nothing_saved_for_other_routes(self):
        _, _, saves = run_hook("/api/articles", {"request_id": "abc"}, "add_article")
        self.assertEqual(saves, [])

    def test_nothing_saved_for_non_json_replies(self):
        _, _, saves = run_hook("/api/chat", {"request_id": "abc"}, "chat", json_reply=False)
        self.assertEqual(saves, [])

    def test_overlong_request_id_is_ignored(self):
        _, _, saves = run_hook("/api/chat", {"request_id": "x" * 65}, "chat")
        self.assertEqual(saves, [])

    def test_signed_out_request_is_skipped_quietly(self):
        # A chat request refused with 401 never set g.auth_user: no copy, no error line in the log.
        import contextlib
        import io
        printed = io.StringIO()
        with app.test_request_context("/api/chat", method="POST", json={"request_id": "abc"}), \
                mock.patch.object(app_module, "run_in_background") as background, \
                contextlib.redirect_stdout(printed):
            from flask import request
            request.url_rule = mock.Mock(endpoint="chat")
            reply = app.response_class(json.dumps({"code": "SESSION_EXPIRED"}), status=401, mimetype="application/json")
            app_module.save_ai_task_result_copy(reply)
        background.assert_not_called()
        self.assertEqual(printed.getvalue(), "")

    def test_hook_runs_after_every_other_hook(self):
        # Flask runs after_request hooks last-registered first, so index 0 runs
        # last and sees the final reply (image URL, escalation fixes included).
        self.assertIs(app.after_request_funcs[None][0], app_module.save_ai_task_result_copy)


class StorageTests(unittest.TestCase):
    def test_save_is_an_upsert_scoped_by_user_and_request(self):
        conn = FakeConnection()
        ai_task_results._last_cleanup = 0
        ai_task_results.save_result(lambda: conn, 7, "abc", "chat", 200, '{"reply": "hi"}')
        sql = [s for s, _ in conn.statements]
        self.assertTrue(any(s.startswith("CREATE TABLE IF NOT EXISTS ai_task_result") for s in sql))
        insert = next((s, p) for s, p in conn.statements if s.startswith("INSERT INTO ai_task_result"))
        self.assertIn("ON DUPLICATE KEY UPDATE", insert[0])
        self.assertEqual(insert[1][:5], (7, "abc", "chat", 200, '{"reply": "hi"}'))
        self.assertTrue(any("DELETE FROM ai_task_result" in s and "7 DAY" in s for s in sql))
        self.assertTrue(conn.committed and conn.closed)

    def test_cleanup_runs_at_most_every_ten_minutes(self):
        ai_task_results._last_cleanup = 0
        first, second = FakeConnection(), FakeConnection()
        ai_task_results.save_result(lambda: first, 7, "a", "chat", 200, "{}")
        ai_task_results.save_result(lambda: second, 7, "b", "chat", 200, "{}")
        self.assertTrue(any("DELETE FROM" in s for s, _ in first.statements))
        self.assertFalse(any("DELETE FROM" in s for s, _ in second.statements))

    def test_save_never_raises(self):
        conn = FakeConnection(fail=True)
        ai_task_results.save_result(lambda: conn, 7, "abc", "chat", 200, "{}")
        self.assertTrue(conn.closed)

    def test_fetch_reads_only_the_given_users_row(self):
        conn = FakeConnection(row={"kind": "chat", "http_status": 200, "result": '{"reply": "hi"}'})
        found = ai_task_results.fetch_result(lambda: conn, 7, "abc")
        self.assertEqual(found, {"kind": "chat", "http_status": 200, "result": {"reply": "hi"}})
        select, params = next((s, p) for s, p in conn.statements if s.startswith("SELECT"))
        self.assertIn("WHERE user_id = %s AND request_id = %s", select)
        self.assertEqual(params, (7, "abc"))

    def test_fetch_missing_or_broken_returns_none(self):
        self.assertIsNone(ai_task_results.fetch_result(lambda: FakeConnection(row=None), 7, "abc"))
        self.assertIsNone(ai_task_results.fetch_result(lambda: FakeConnection(fail=True), 7, "abc"))


class FetchRouteTests(unittest.TestCase):
    def call(self, found):
        with app.test_request_context("/api/ai-tasks/abc-1", method="GET"), \
                mock.patch.object(app_module, "current_auth_user_id", return_value=7), \
                mock.patch.object(app_module.ai_task_results, "fetch_result", return_value=found) as fetch:
            reply = app_module.get_ai_task_result("abc-1")
            return reply, fetch

    def test_found(self):
        reply, fetch = self.call({"kind": "chat", "http_status": 200, "result": {"reply": "hi"}})
        self.assertEqual(reply.get_json(), {"found": True, "kind": "chat", "http_status": 200, "result": {"reply": "hi"}})
        self.assertEqual(fetch.call_args.args[1:], (7, "abc-1"))  # always the signed-in user

    def test_not_found(self):
        reply, _ = self.call(None)
        self.assertEqual(reply.get_json(), {"found": False})

    def test_route_is_open_to_every_signed_in_role(self):
        self.assertNotIn("get_ai_task_result", app_module._MANAGER_ENDPOINTS)
        self.assertNotIn("get_ai_task_result", app_module._APPROVER_ENDPOINTS)
        rules = [r for r in app.url_map.iter_rules() if r.endpoint == "get_ai_task_result"]
        self.assertEqual([(r.rule, sorted(r.methods - {"HEAD", "OPTIONS"})) for r in rules],
                         [("/api/ai-tasks/<request_id>", ["GET"])])


if __name__ == "__main__":
    unittest.main()
