"""Live model list for the AI Settings dropdown, with labels.
No network: requests.get is replaced. Run:
python -m unittest discover -s backend/src -p test_ai_model_list.py
"""

import types
import unittest
from unittest.mock import patch

import ai_provider_service as aps


def reply(payload, status=200):
    return types.SimpleNamespace(
        status_code=status, json=lambda: payload,
        raise_for_status=lambda: None if status < 400 else (_ for _ in ()).throw(
            aps.requests.HTTPError(response=types.SimpleNamespace(status_code=status))))


GEMINI_PAGE_1 = {"models": [
    {"name": "models/gemini-3-flash-preview", "displayName": "Gemini 3 Flash Preview",
     "supportedGenerationMethods": ["generateContent", "countTokens"]},
    {"name": "models/gemini-3.8-flash", "displayName": "Gemini 3.8 Flash",
     "supportedGenerationMethods": ["generateContent"]},
    {"name": "models/gemini-3.1-flash-image", "displayName": "Image",
     "supportedGenerationMethods": ["generateContent"]},
], "nextPageToken": "p2"}
GEMINI_PAGE_2 = {"models": [
    {"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": ["generateContent"]},
    {"name": "models/text-embedding-005", "supportedGenerationMethods": ["embedContent"]},
    {"name": "models/gemini-3.6-flash", "supportedGenerationMethods": ["generateContent"]},
]}


class ModelListTests(unittest.TestCase):
    def test_gemini_all_pages_labelled_and_sorted(self):
        with patch.object(aps.requests, "get", side_effect=[reply(GEMINI_PAGE_1), reply(GEMINI_PAGE_2)]) as get:
            models = aps.list_models("gemini", "key")
        self.assertEqual(get.call_args_list[0].kwargs["headers"]["x-goog-api-key"], "key")
        self.assertEqual(get.call_args_list[1].kwargs["params"]["pageToken"], "p2")
        ids = [m["id"] for m in models]
        # Recommended first (newest first), then other chat models, then preview, then not-for-chat.
        self.assertEqual(ids, ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite",
                               "gemini-3-flash-preview", "gemini-3.1-flash-image", "text-embedding-005"])
        by_id = {m["id"]: m for m in models}
        self.assertTrue(by_id["gemini-3.8-flash"]["recommended"])
        self.assertFalse(by_id["gemini-3.5-flash-lite"]["recommended"])
        self.assertTrue(by_id["gemini-3-flash-preview"]["preview"])
        self.assertFalse(by_id["gemini-3-flash-preview"]["recommended"])
        self.assertFalse(by_id["gemini-3.1-flash-image"]["chat"])
        self.assertFalse(by_id["text-embedding-005"]["chat"])

    def test_openai_and_deepseek(self):
        payload = {"data": [{"id": "gpt-5-mini"}, {"id": "dall-e-3"}, {"id": "whisper-1"},
                            {"id": "gpt-5"}, {"id": "text-embedding-3-small"}, {"id": "o4-mini-preview"}]}
        with patch.object(aps.requests, "get", return_value=reply(payload)) as get:
            models = aps.list_models("openai", "key")
        self.assertEqual(get.call_args.args[0], "https://api.openai.com/v1/models")
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer key")
        by_id = {m["id"]: m for m in models}
        self.assertTrue(by_id["gpt-5-mini"]["recommended"])
        self.assertFalse(by_id["dall-e-3"]["chat"])
        self.assertFalse(by_id["whisper-1"]["chat"])
        self.assertTrue(by_id["o4-mini-preview"]["preview"])
        with patch.object(aps.requests, "get", return_value=reply({"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]})) as get:
            models = aps.list_models("deepseek", "key")
        self.assertEqual(get.call_args.args[0], "https://api.deepseek.com/models")
        self.assertEqual(models[0]["id"], "deepseek-chat")
        self.assertTrue(models[0]["recommended"])

    def test_anthropic_paginates(self):
        pages = [reply({"data": [{"id": "claude-opus-5-5", "display_name": "Claude Opus 5.5"}], "has_more": True, "last_id": "claude-opus-5-5"}),
                 reply({"data": [{"id": "claude-haiku-5-5"}], "has_more": False})]
        with patch.object(aps.requests, "get", side_effect=pages) as get:
            models = aps.list_models("anthropic", "key")
        self.assertEqual(get.call_args_list[0].kwargs["headers"]["x-api-key"], "key")
        self.assertEqual(get.call_args_list[1].kwargs["params"]["after_id"], "claude-opus-5-5")
        self.assertEqual(models[0]["id"], "claude-haiku-5-5")   # fast model recommended first
        self.assertEqual({m["id"] for m in models}, {"claude-opus-5-5", "claude-haiku-5-5"})

    def test_errors_raise(self):
        with patch.object(aps.requests, "get", return_value=reply({}, status=401)):
            with self.assertRaises(aps.requests.HTTPError):
                aps.list_models("gemini", "bad")
        with self.assertRaises(ValueError):
            aps.list_models("unknown", "key")

    def test_page_limit_stops_runaway_pagination(self):
        endless = lambda *a, **k: reply({"models": [], "nextPageToken": "again"})
        with patch.object(aps.requests, "get", side_effect=endless) as get:
            aps.list_models("gemini", "key")
        self.assertLessEqual(get.call_count, 10)


if __name__ == "__main__":
    unittest.main()
