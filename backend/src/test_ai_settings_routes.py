"""AI Settings routes: model list, test, save -- with the saved key reused when
the key box is left as is. Real route functions are extracted from app.py;
the database and AI providers are fakes. Run:
python -m unittest discover -s backend/src -p test_ai_settings_routes.py
"""

import ast
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

import requests

source = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
tree = ast.parse(source)
ROUTES = ["save_ai_settings", "test_ai_settings", "list_ai_models"]
nodes = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in ROUTES:
        node.decorator_list = []
        nodes.append(node)
MANAGER_ENDPOINTS = next(
    ast.literal_eval(node.value) for node in tree.body
    if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "_MANAGER_ENDPOINTS" for t in node.targets)
)

SAVED = {"provider": "gemini", "model_name": "gemini-3-flash-preview", "encrypted_api_key": "encrypted"}


class Conn:
    def __init__(self):
        self.commits = 0
    def start_transaction(self): pass
    def cursor(self, **kwargs): return types.SimpleNamespace(close=lambda: None)
    def commit(self): self.commits += 1
    def rollback(self): pass
    def close(self): pass


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.body = {}
        self.service = types.SimpleNamespace(
            SUPPORTED_PROVIDERS={"gemini", "openai", "deepseek", "anthropic"},
            get_db_connection=Conn,
            ensure_ai_provider_configs_table=Mock(),
            get_active_ai_provider_config=Mock(return_value=dict(SAVED)),
            decrypt_api_key=Mock(return_value="saved-key"),
            save_ai_provider_config=Mock(),
            get_ai_provider_public_config=Mock(return_value={"modelName": "x"}),
            call_ai_provider=Mock(return_value="OK"),
            update_active_provider_test_status=Mock(),
            list_models=Mock(return_value=[{"id": "gemini-3.8-flash", "label": "Gemini 3.8 Flash", "chat": True,
                                            "preview": False, "recommended": True}]),
        )
        self.manager = Mock(return_value=True)
        env = {
            "AI_PROVIDER_SERVICE_AVAILABLE": True,
            "ai_provider_service": self.service,
            "request": types.SimpleNamespace(get_json=lambda silent=False: self.body),
            "jsonify": lambda value: value,
            "current_auth_user_id": lambda: 1,
            "is_ai_settings_manager": self.manager,
            "add_audit_log": Mock(),
            "requests": requests,
        }
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "ai_settings_routes.py", "exec"), env)
        self.env = env

    def run_route(self, name, **body):
        self.body = body
        return self.env[name]()

    # ---- save ----
    def test_save_without_new_key_keeps_the_saved_key(self):
        result, status = self.run_route("save_ai_settings", provider="gemini", model_name="gemini-3.8-flash", api_key="")
        self.assertEqual(status, 200)
        self.service.save_ai_provider_config.assert_called_once()
        args = self.service.save_ai_provider_config.call_args.args
        self.assertEqual(args[1:4], ("gemini", "gemini-3.8-flash", "saved-key"))

    def test_save_new_provider_needs_its_own_key(self):
        result, status = self.run_route("save_ai_settings", provider="openai", model_name="gpt-5-mini", api_key="")
        self.assertEqual(status, 400)
        self.service.save_ai_provider_config.assert_not_called()

    def test_save_first_time_needs_a_key(self):
        self.service.get_active_ai_provider_config.return_value = None
        _, status = self.run_route("save_ai_settings", provider="gemini", model_name="gemini-3.8-flash", api_key="")
        self.assertEqual(status, 400)

    def test_save_with_new_key_uses_it(self):
        self.run_route("save_ai_settings", provider="openai", model_name="gpt-5-mini", api_key="new-key")
        self.assertEqual(self.service.save_ai_provider_config.call_args.args[3], "new-key")

    def test_save_still_manager_only(self):
        self.manager.return_value = False
        _, status = self.run_route("save_ai_settings", provider="gemini", model_name="gemini-3.8-flash", api_key="")
        self.assertEqual(status, 403)
        self.service.save_ai_provider_config.assert_not_called()

    # ---- test connection ----
    def test_test_uses_the_chosen_model_with_the_saved_key(self):
        result, status = self.run_route("test_ai_settings", provider="gemini", model_name="gemini-3.8-flash", api_key="")
        self.assertEqual(status, 200)
        call = self.service.call_ai_provider.call_args.args
        self.assertEqual(call[1:4], ("gemini", "gemini-3.8-flash", "saved-key"))
        # A different model than the saved one: do not mark the saved config as tested.
        self.service.update_active_provider_test_status.assert_not_called()

    def test_test_of_the_saved_model_records_the_result(self):
        self.run_route("test_ai_settings", provider="gemini", model_name="gemini-3-flash-preview", api_key="")
        self.service.update_active_provider_test_status.assert_called_once()

    def test_test_other_provider_without_key_is_refused(self):
        result, status = self.run_route("test_ai_settings", provider="openai", model_name="gpt-5-mini", api_key="")
        self.assertEqual(status, 400)
        self.service.call_ai_provider.assert_not_called()

    def test_test_with_typed_key(self):
        self.run_route("test_ai_settings", provider="openai", model_name="gpt-5-mini", api_key="typed")
        self.assertEqual(self.service.call_ai_provider.call_args.args[1:4], ("openai", "gpt-5-mini", "typed"))

    # ---- model list ----
    def test_models_with_saved_key(self):
        result, status = self.run_route("list_ai_models", provider="gemini", api_key="")
        self.assertEqual(status, 200)
        self.service.list_models.assert_called_once_with("gemini", "saved-key")
        self.assertEqual(result["models"][0]["id"], "gemini-3.8-flash")
        self.assertEqual(result["savedModel"], "gemini-3-flash-preview")

    def test_models_other_provider_needs_key(self):
        result, status = self.run_route("list_ai_models", provider="openai", api_key="")
        self.assertEqual(status, 400)
        self.service.list_models.assert_not_called()
        self.run_route("list_ai_models", provider="openai", api_key="typed")
        self.service.list_models.assert_called_once_with("openai", "typed")

    def test_models_bad_key_and_outage(self):
        error = requests.HTTPError(response=types.SimpleNamespace(status_code=401))
        self.service.list_models.side_effect = error
        _, status = self.run_route("list_ai_models", provider="gemini", api_key="")
        self.assertEqual(status, 400)
        self.service.list_models.side_effect = requests.ConnectionError("down")
        result, status = self.run_route("list_ai_models", provider="gemini", api_key="")
        self.assertEqual(status, 502)
        self.assertNotIn("down", result["message"])     # no raw error text to the browser

    def test_models_manager_only(self):
        self.manager.return_value = False
        _, status = self.run_route("list_ai_models", provider="gemini", api_key="")
        self.assertEqual(status, 403)
        self.assertIn("list_ai_models", MANAGER_ENDPOINTS)

    def test_models_unknown_provider(self):
        _, status = self.run_route("list_ai_models", provider="nope", api_key="x")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
