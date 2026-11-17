"""Developer-only routes must not exist on the live site, and no new debug-style route may slip in unnoticed.

Production mode = importing app.py the way gunicorn does (wsgi.py). Development mode = what the
`python app.py` block does (register_dev_only_routes) on a computer without Railway variables. Development
mode runs in a separate Python process, so the extra routes never leak into the other tests.

No MySQL is needed: the database is the SQLite stand-in from test_login_lockout.py.

Run (from backend/src):
    python -m unittest test_dev_only_routes -v
"""

import ast
import json
import os
import re
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR))
os.environ.setdefault("FLASK_SECRET_KEY", "dummy-test-only-key-not-a-secret-0123456789")
os.environ.setdefault("NOTION_AUTO_SYNC_ENABLED", "false")

import test_login_lockout as lockout_tests  # noqa: E402  (SQLite stand-in database and sign-in helpers)
import app as app_module  # noqa: E402

# Developer tools: registered only on a developer computer (see DEV_ONLY_ROUTES in app.py).
DEV_ONLY = {
    "/api/debug/chat-uploads": "debug_chat_uploads",
    "/api/debug/sop-images": "debug_sop_images",
    "/api/debug/static-files": "debug_static_files",
    "/api/debug/uploads": "debug_uploads",
    "/api/test-db": "test_db",
    "/api/chat/test": "chat_test",
}
# Removed completely (dead: it only answered 400 "disabled" and no page called it).
REMOVED = {"/api/generate-quiz": "POST"}

# Words that mark a developer/diagnostic route. Matched as whole words of the path and of the endpoint name,
# so "device" or "testimonial" would not match "dev" or "test".
DEBUG_WORDS = {
    "debug", "test", "tests", "testing", "dev", "devtools", "diag", "diagnostic", "diagnostics", "inspect", "dump",
    "ping", "seed", "mock", "demo", "sample", "samples", "simulate", "simulation", "echo", "env", "environment",
    "config", "schema", "cache", "reset", "raw", "internal",
}
# Routes that contain one of those words but are real features. Each needs a reason. Anything new that matches
# DEBUG_WORDS fails the test until it is removed, made developer-only, or added here on purpose.
ALLOWED = {
    ("/health", "health"): "Railway health check (healthcheckPath in railway.json)",
    ("/api/health", "health"): "same status check through the Vercel /api proxy (kept, see the ASK list)",
    ("/api/admin/email/test", "test_system_email"): "User Management: 'send test email' button",
    ("/api/ai-settings/test", "test_ai_settings"): "AI Settings: 'test connection' button",
    ("/api/notion-sync/config", "get_notion_sync_config"): "Notion Sync page: connection status",
    ("/api/notion-sync/oauth/app-config", "get_notion_oauth_app_config"): "Notion Sync page: OAuth app settings",
    ("/api/notion-sync/oauth/app-config", "save_notion_oauth_app_config"): "Notion Sync page: OAuth app settings",
    ("/api/notion-sync/oauth/app-config", "reset_notion_oauth_app_config"): "Notion Sync page: OAuth app settings",
    ("/api/auth/reset-password", "reset_password"): "forgot / reset password flow",
    ("/api/auth/reset-password/validate", "validate_password_reset_token"): "forgot / reset password flow",
}


def words(text):
    return {part for part in re.split(r"[^a-z0-9]+", str(text).lower()) if part}


def debug_style_rules(flask_app):
    """(path, endpoint) of every registered route whose path or endpoint name contains a debug word."""
    found = set()
    for rule in flask_app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        if (words(rule.rule) | words(rule.endpoint)) & DEBUG_WORDS:
            found.add((rule.rule, rule.endpoint))
    return found


class ProductionModeTests(lockout_tests.RouteTestCase):
    """The app exactly as gunicorn imports it on the live site."""

    def manager(self):
        client = self.device()
        self.assertEqual(self.login(client, lockout_tests.MANAGER, lockout_tests.PASSWORD).status_code, 200)
        return client

    def test_developer_routes_are_not_registered(self):
        registered = {rule.rule for rule in app_module.app.url_map.iter_rules()}
        endpoints = set(app_module.app.view_functions)
        for path, endpoint in DEV_ONLY.items():
            self.assertNotIn(path, registered)
            self.assertNotIn(endpoint, endpoints)
        for path in REMOVED:
            self.assertNotIn(path, registered)
        self.assertFalse(hasattr(app_module, "generate_quiz"))

    def test_a_manager_gets_the_same_404_as_for_any_unknown_url(self):
        manager = self.manager()
        unknown = manager.get("/api/this-route-does-not-exist")
        self.assertEqual(unknown.status_code, 404)
        for path in DEV_ONLY:
            response = manager.get(path)
            self.assertEqual(response.status_code, 404, path)
            self.assertEqual(response.data, unknown.data, path)
        token = self.csrf(manager)
        for path, method in REMOVED.items():
            response = manager.open(path, method=method, headers={"X-CSRF-Token": token}, json={})
            self.assertEqual(response.status_code, 404, path)

    def test_signed_out_visitors_get_the_same_answer_as_for_any_unknown_url(self):
        visitor = self.device()
        unknown = visitor.get("/api/this-route-does-not-exist")
        for path in DEV_ONLY:
            response = visitor.get(path)
            self.assertEqual((response.status_code, response.get_json()), (unknown.status_code, unknown.get_json()), path)

    def test_keep_routes_still_work(self):
        anonymous = self.device()
        for path in ("/health", "/api/health"):
            response = anonymous.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertEqual(response.get_json()["status"], "ok")
        self.assertEqual(anonymous.get("/").status_code, 200)            # on the ASK list, unchanged
        registered = {(rule.rule, rule.endpoint) for rule in app_module.app.url_map.iter_rules()}
        for item in ALLOWED:
            self.assertIn(item, registered)
        for path in ("/api/notion-sync/storage-audit", "/api/notion-sync/storage-cleanup", "/api/security/audit-logs",
                     "/api/registration-keys", "/api/auth/activate-registration-key"):
            self.assertIn(path, {rule for rule, _ in registered}, path)

    def test_no_debug_style_route_is_registered_on_the_live_site(self):
        unexpected = debug_style_rules(app_module.app) - set(ALLOWED)
        self.assertEqual(
            unexpected, set(),
            "A route with a debug/test/dev-style name is registered on the live site. Remove it, add it to "
            "DEV_ONLY_ROUTES in app.py, or (only for a real feature) add it to ALLOWED in this test with a reason.",
        )

    def test_the_guard_catches_a_new_debug_route(self):
        import flask

        scratch = flask.Flask("scratch")
        scratch.add_url_rule("/api/health", "health", lambda: "ok")
        scratch.add_url_rule("/api/debug/new-tool", "show_internal_state", lambda: "x")
        scratch.add_url_rule("/api/ping", "ping", lambda: "x")
        scratch.add_url_rule("/api/devices", "list_devices", lambda: "x")         # "device" is not "dev"
        self.assertEqual(debug_style_rules(scratch) - set(ALLOWED),
                         {("/api/debug/new-tool", "show_internal_state"), ("/api/ping", "ping")})

    def test_only_the_python_app_py_block_registers_developer_routes(self):
        tree = ast.parse((SRC_DIR / "app.py").read_text(encoding="utf-8"))
        main_blocks = [node for node in tree.body if isinstance(node, ast.If) and "__main__" in ast.unparse(node.test)]
        self.assertEqual(len(main_blocks), 1)
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "register_dev_only_routes"]
        self.assertEqual(len(calls), 1)
        self.assertIn(calls[0], list(ast.walk(main_blocks[0])))
        self.assertNotIn("register_dev_only_routes", (SRC_DIR / "wsgi.py").read_text(encoding="utf-8"))
        for path, endpoint in DEV_ONLY.items():                      # no @app.route left on these functions
            function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == endpoint)
            self.assertEqual(function.decorator_list, [], endpoint)

    def test_developer_routes_stay_off_on_railway_even_when_asked(self):
        before = {rule.rule for rule in app_module.app.url_map.iter_rules()}
        for name in ("RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PUBLIC_DOMAIN"):
            with self.subTest(variable=name):
                saved = {key: os.environ.pop(key, None) for key in
                         ("RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PUBLIC_DOMAIN")}
                os.environ[name] = "production"
                try:
                    self.assertTrue(app_module.running_on_railway())
                    self.assertEqual(app_module.register_dev_only_routes(app_module.app), [])
                finally:
                    os.environ.pop(name, None)
                    for key, value in saved.items():
                        if value is not None:
                            os.environ[key] = value
        self.assertEqual({rule.rule for rule in app_module.app.url_map.iter_rules()}, before)


DEVELOPMENT_SCRIPT = textwrap.dedent("""
    import json, os, sys, tempfile
    from pathlib import Path
    sys.path.insert(0, os.getcwd())
    import test_login_lockout as t
    import app as app_module
    from werkzeug.security import generate_password_hash

    db = t.FakeDatabase()
    db.run("INSERT INTO roles (role_id, role_name) VALUES (1, 'manager'), (2, 'staff')")
    password_hash = generate_password_hash(t.PASSWORD, method=t.FAST_HASH)
    db.run("INSERT INTO users (user_id, full_name, email, password_hash, role_id, status) VALUES "
           "(1, 'Mia Manager', ?, ?, 1, 'active'), (2, 'Sam Staff', ?, ?, 2, 'active')",
           (t.MANAGER, password_hash, t.STAFF, password_hash))
    app_module.get_db_connection = db.connect
    # The chat test writes CSV files into logs/. Keep every log file out of the repository.
    logs = Path(tempfile.mkdtemp())
    app_module.LOG_DIR = logs
    app_module.LOG_JSONL = logs / "ai_chat_logs.jsonl"
    app_module.LOG_CSV = logs / "ai_chat_logs.csv"
    app_module.TEST_REPORT_CSV = report = logs / "ai_test_results.csv"

    added = app_module.register_dev_only_routes(app_module.app)
    added_again = app_module.register_dev_only_routes(app_module.app)

    def signed_in(email):
        client = app_module.app.test_client()
        token = client.get("/api/auth/csrf").get_json()["csrf_token"]
        status = client.post("/api/auth/login", json={"email": email, "password": t.PASSWORD},
                             headers={"X-CSRF-Token": token}).status_code
        assert status == 200, status
        return client

    manager, staff = signed_in(t.MANAGER), signed_in(t.STAFF)
    manager_results = {}
    for path in added:
        response = manager.get(path)
        manager_results[path] = [response.status_code, sorted((response.get_json() or {}).keys())]
    print("RESULT " + json.dumps({
        "added": added,
        "added_again": added_again,
        "manager": manager_results,
        "staff": {path: staff.get(path).status_code for path in added},
        "anonymous": {path: app_module.app.test_client().get(path).status_code for path in added},
        "report_written": report.exists(),
    }))
    db.close()
""")


class DevelopmentModeTests(unittest.TestCase):
    """What `python app.py` does on a developer computer, in a separate process."""

    @classmethod
    def setUpClass(cls):
        env = {key: value for key, value in os.environ.items() if not key.startswith("RAILWAY_")}
        env.setdefault("FLASK_SECRET_KEY", "dummy-test-only-key-not-a-secret-0123456789")
        env["NOTION_AUTO_SYNC_ENABLED"] = "false"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run([sys.executable, "-c", DEVELOPMENT_SCRIPT], cwd=SRC_DIR, env=env,
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        line = next((item for item in completed.stdout.splitlines() if item.startswith("RESULT ")), None)
        if line is None:
            raise AssertionError(f"development-mode process failed:\n{completed.stdout[-2000:]}\n{completed.stderr[-4000:]}")
        cls.result = json.loads(line[len("RESULT "):])

    def test_developer_routes_are_added_once(self):
        self.assertEqual(sorted(self.result["added"]), sorted(DEV_ONLY))
        self.assertEqual(self.result["added_again"], [])

    def test_developer_routes_work_for_a_manager(self):
        for path in DEV_ONLY:
            status, keys = self.result["manager"][path]
            self.assertEqual(status, 200, path)
            self.assertTrue(keys, path)
        self.assertIn("files", self.result["manager"]["/api/debug/uploads"][1])
        self.assertIn("result", self.result["manager"]["/api/test-db"][1])
        self.assertIn("pass_rate", self.result["manager"]["/api/chat/test"][1])
        self.assertTrue(self.result["report_written"])

    def test_developer_routes_still_need_a_manager_login(self):
        self.assertEqual(set(self.result["staff"].values()), {403})
        self.assertEqual(set(self.result["anonymous"].values()), {401})


if __name__ == "__main__":
    unittest.main()
