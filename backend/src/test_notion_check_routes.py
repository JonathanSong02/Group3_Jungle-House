"""Tests for the Notion 'Check for Updates' routes in app.py.

Like test_chat_memory.py, this extracts the real route functions from app.py with `ast` instead
of importing the whole app (which would start threads, load models and need a database), and runs
them with fakes for the request, the database and the sync service.

Run (from backend/src):
    python -m unittest test_notion_check_routes -v
"""

import ast
import copy
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

SOURCE = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

ROUTE_FUNCTIONS = {
    "check_notion_sync",
    "get_notion_check_status",
    "_notify_managers_of_flagged_items",
    "_finish_manual_notion_check",
}


def function_node(name):
    return next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)


def route_of(name):
    """(path, methods) from the @app.route(...) decorator."""
    for decorator in function_node(name).decorator_list:
        if isinstance(decorator, ast.Call) and getattr(decorator.func, "attr", "") == "route":
            path = decorator.args[0].value
            methods = [e.value for e in next(k.value for k in decorator.keywords if k.arg == "methods").elts]
            return path, methods
    raise AssertionError(f"{name} has no @app.route")


def manager_endpoints():
    for node in TREE.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_MANAGER_ENDPOINTS" for t in node.targets):
            return {e.value for e in node.value.elts if isinstance(e, ast.Constant)}
    raise AssertionError("_MANAGER_ENDPOINTS not found")


class FakeResponse(dict):
    def __init__(self, payload):
        super().__init__(payload)
        self.headers = {}


def load_routes(env):
    nodes = []
    for name in ROUTE_FUNCTIONS:
        node = copy.deepcopy(function_node(name))  # keep the shared tree (and its decorators) intact
        node.decorator_list = []  # no Flask app here
        nodes.append(node)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "selected_app_routes.py", "exec"), env)


class CheckRouteTests(unittest.TestCase):
    ACTOR = 7

    def setUp(self):
        self.is_manager = True
        self.token = ("secret-notion-token", "connected")
        self.start_outcome = {"started": True, "outcome": "started", "runId": 41, "message": None}

        self.cursor = Mock(name="cursor")
        self.conn = Mock(name="conn")
        self.conn.cursor.return_value = self.cursor
        self.service = types.SimpleNamespace(
            get_db_connection=Mock(return_value=self.conn),
            ensure_notion_sync_tables=Mock(),
            get_active_notion_connection=Mock(side_effect=lambda cursor: self.token),
            start_background_check=Mock(side_effect=lambda *a, **k: self.start_outcome),
            get_check_status=Mock(return_value={"run": {"id": 41, "state": "running"}}),
            ALREADY_RUNNING_MESSAGE="Another sync is already running.",
        )
        self.audit = Mock(name="add_audit_log")
        self.notify = Mock(name="_notify_managers_of_notion_update")
        self.env = {
            "NOTION_SYNC_SERVICE_AVAILABLE": True,
            "notion_sync_service": self.service,
            "request": types.SimpleNamespace(get_json=lambda silent=True: {}),
            "jsonify": FakeResponse,
            "current_auth_user_id": lambda: self.ACTOR,
            "is_ai_settings_manager": lambda cursor, actor_id: self.is_manager and actor_id == self.ACTOR,
            "UPLOAD_FOLDER": Path("uploads"),
            "delete_pending_update_upload_files": Mock(),
            "add_audit_log": self.audit,
            "_notify_managers_of_notion_update": self.notify,
        }
        load_routes(self.env)

    # ---- POST /api/notion-sync/check ------------------------------------
    def test_a_manager_click_starts_the_run_and_answers_at_once_with_202(self):
        body, status = self.env["check_notion_sync"]()

        self.assertEqual(status, 202)
        self.assertEqual((body["success"], body["started"], body["runId"]), (True, True, 41))
        args, kwargs = self.service.start_background_check.call_args
        self.assertEqual(args[:2], ("secret-notion-token", self.ACTOR))
        self.assertEqual(kwargs["trigger"], "manual")
        self.assertTrue(callable(kwargs["on_finished"]))
        self.assertNotIn("secret-notion-token", repr(body))

    def test_a_click_while_a_sync_is_running_is_calm_not_an_error(self):
        self.start_outcome = {"started": False, "outcome": "already_running", "runId": None, "message": "x"}

        body, status = self.env["check_notion_sync"]()

        self.assertEqual(status, 200)
        self.assertEqual((body["success"], body["started"], body["alreadyRunning"]), (True, False, True))
        self.assertEqual(body["message"], "Another sync is already running.")

    def test_a_sync_that_could_not_start_reports_a_safe_message(self):
        self.start_outcome = {"started": False, "outcome": "failed", "runId": None,
                              "message": "The database is unavailable right now. Please try again."}
        body, status = self.env["check_notion_sync"]()
        self.assertEqual(status, 500)
        self.assertFalse(body["success"])
        self.assertEqual(body["message"], "The database is unavailable right now. Please try again.")

    def test_only_managers_may_start_a_check(self):
        self.is_manager = False
        body, status = self.env["check_notion_sync"]()
        self.assertEqual(status, 403)
        self.service.start_background_check.assert_not_called()

    def test_no_connected_workspace_or_a_dead_token_never_starts_a_run(self):
        self.token = (None, None)
        _, status = self.env["check_notion_sync"]()
        self.assertEqual(status, 400)

        self.token = ("tok", "reconnect_required")
        body, status = self.env["check_notion_sync"]()
        self.assertEqual((status, body["connectionStatus"]), (400, "reconnect_required"))
        self.service.start_background_check.assert_not_called()

    def test_the_connections_are_closed_before_the_run_is_started(self):
        self.env["check_notion_sync"]()
        self.cursor.close.assert_called()
        self.conn.close.assert_called()

    # ---- what happens when the background run ends -----------------------
    def test_when_the_run_ends_managers_are_notified_and_the_audit_log_is_written(self):
        self.env["check_notion_sync"]()
        on_finished = self.service.start_background_check.call_args.kwargs["on_finished"]
        result = {
            "status": "completed", "new": 2, "flagged": 1, "refreshed": 0, "unchanged": 9, "failed": 0, "inaccessible": 0,
            "flaggedItems": [{"kind": "new", "article_id": None, "title": "Opening SOP", "pending_id": 3}],
        }

        on_finished(result)

        self.notify.assert_called_once()
        self.assertEqual(self.notify.call_args.args[1:3], ("Opening SOP", None))
        self.audit.assert_called_once()
        self.assertEqual(self.audit.call_args.kwargs["actor_id"], self.ACTOR)
        self.assertEqual(self.audit.call_args.kwargs["action"], "Checked Notion for updates")
        self.assertIn("New 2", self.audit.call_args.kwargs["description"])

    def test_a_failure_to_notify_never_breaks_the_finish_step(self):
        self.service.get_db_connection.side_effect = [self.conn, RuntimeError("db down")]
        self.env["check_notion_sync"]()
        on_finished = self.service.start_background_check.call_args.kwargs["on_finished"]
        on_finished({"status": "completed", "new": 1, "flagged": 0, "unchanged": 0, "failed": 0,
                     "flaggedItems": [{"kind": "new", "article_id": None, "title": "x"}]})
        self.audit.assert_called_once()

    # ---- GET /api/notion-sync/check/status -------------------------------
    def test_the_status_route_returns_the_latest_run_and_is_never_cached(self):
        body, status = self.env["get_notion_check_status"]()

        self.assertEqual(status, 200)
        self.assertEqual(body["run"], {"id": 41, "state": "running"})
        self.assertEqual(body.headers["Cache-Control"], "no-store")
        self.service.get_check_status.assert_called_once_with(self.conn)

    def test_the_status_route_is_managers_only(self):
        self.is_manager = False
        body, status = self.env["get_notion_check_status"]()
        self.assertEqual(status, 403)
        self.service.get_check_status.assert_not_called()

    def test_the_status_route_hides_internal_errors_from_the_response_and_the_log(self):
        self.service.get_check_status.side_effect = RuntimeError("mysql://root:hunter2@host")
        printed = []
        self.env["print"] = lambda *args: printed.append(" ".join(str(a) for a in args))

        body, status = self.env["get_notion_check_status"]()

        self.assertEqual(status, 500)
        self.assertEqual(body["message"], "Failed to load the sync status.")
        self.assertNotIn("hunter2", repr(body))
        self.assertEqual(len(printed), 1)
        self.assertIn("RuntimeError", printed[0])
        self.assertNotIn("hunter2", printed[0])

    def test_the_status_route_does_no_table_setup_per_poll(self):
        self.env["get_notion_check_status"]()
        self.service.ensure_notion_sync_tables.assert_not_called()

    # ---- wiring (static) ---------------------------------------------------
    def test_both_routes_are_registered_and_protected_like_the_other_notion_routes(self):
        self.assertEqual(route_of("check_notion_sync"), ("/api/notion-sync/check", ["POST"]))
        self.assertEqual(route_of("get_notion_check_status"), ("/api/notion-sync/check/status", ["GET"]))
        guarded = manager_endpoints()
        self.assertIn("check_notion_sync", guarded)
        self.assertIn("get_notion_check_status", guarded, "the global session-role guard must cover the new route")

    def test_the_automatic_loop_records_its_runs_as_automatic(self):
        loop_source = ast.get_source_segment(SOURCE, function_node("_notion_auto_sync_loop"))
        self.assertIn('trigger="auto"', loop_source)
        self.assertIn("_notify_managers_of_flagged_items", loop_source)


if __name__ == "__main__":
    unittest.main()
