"""Gemini calls ask for low thinking (much faster answers) and read only the
answer text. No network: requests.post is replaced. Run:
python -m unittest discover -s backend/src -p test_ai_provider_gemini.py
"""

import types
import unittest
from unittest.mock import patch

import ai_provider_service as aps


def response(status=200, parts=None):
    parts = parts if parts is not None else [{"text": "Answer"}]
    return types.SimpleNamespace(
        status_code=status,
        json=lambda: {"candidates": [{"content": {"parts": parts}}]},
        raise_for_status=lambda: None if status < 400 else (_ for _ in ()).throw(
            aps.requests.HTTPError(response=types.SimpleNamespace(status_code=status))),
    )


class GeminiThinkingTests(unittest.TestCase):
    def call(self, model, responses):
        with patch.object(aps.requests, "post", side_effect=responses) as post:
            text = aps._call_gemini("Question", model, "key", timeout=10)
        return text, [c.kwargs["json"] for c in post.call_args_list]

    def test_gemini_3_and_4_ask_for_low_thinking(self):
        for model in ["gemini-3.8-flash", "gemini-3-flash-preview", "gemini-3.5-flash-lite", "gemini-4-hydrogen"]:
            with self.subTest(model=model):
                text, payloads = self.call(model, [response()])
                self.assertEqual(text, "Answer")
                self.assertEqual(payloads[0]["generationConfig"], {"thinkingConfig": {"thinkingLevel": "low"}})

    def test_older_models_unchanged(self):
        for model in ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-1.5-pro"]:
            with self.subTest(model=model):
                _, payloads = self.call(model, [response()])
                self.assertEqual(payloads, [{"contents": [{"parts": [{"text": "Question"}]}]}])

    def test_rejected_setting_retries_once_without_it(self):
        text, payloads = self.call("gemini-3.8-flash", [response(400), response()])
        self.assertEqual(text, "Answer")
        self.assertEqual(len(payloads), 2)
        self.assertIn("generationConfig", payloads[0])
        self.assertNotIn("generationConfig", payloads[1])

    def test_other_errors_are_not_retried_here(self):
        with self.assertRaises(aps.requests.HTTPError):
            self.call("gemini-3.8-flash", [response(503)])

    def test_thought_parts_are_skipped(self):
        parts = [{"text": "thinking...", "thought": True}, {"text": "Real "}, {"text": "answer"}]
        text, _ = self.call("gemini-3.8-flash", [response(parts=parts)])
        self.assertEqual(text, "Real answer")


if __name__ == "__main__":
    unittest.main()
