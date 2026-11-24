"""AI Chat failures show staff a short, friendly message in their language, never the technical error.

The real /api/chat route runs against the SQLite stand-in database from test_login_lockout (no MySQL, no AI
provider, no network). Each failure is forced with an error whose text holds a fake file path and a fake
secret, and the tests check that neither reaches the reply, the stored chat log, chat memory, the AI
provider's input, the escalation ticket or a notification. The server log keeps only the error type and
where it happened.

Run (from backend/src):
    python -m unittest test_chat_failure_messages -v
"""

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import test_login_lockout as lockout
from test_login_lockout import app_module

import chat_attachment_service

FAKE_PATH = "/app/backend/secrets/provider_key.json"
FAKE_SECRET = "sk-FAKE-SECRET-123"
TECHNICAL = (FAKE_PATH, FAKE_SECRET, "Errno", "Traceback", "Model prediction failed", "backend terminal")

QUESTIONS = {
    "en": "How do I close the kiosk at night?",
    "zh": "晚上怎么关闭售货亭？",
    "ms": "Bagaimana cara tutup kiosk pada waktu malam?",
}
MESSAGES = app_module.CHAT_FAILURE_MESSAGES


def technical_error(kind=FileNotFoundError):
    return kind(f"[Errno 2] No such file or directory: '{FAKE_PATH}' api_key={FAKE_SECRET}")


class ChatFailureRouteTestCase(lockout.RouteTestCase):
    """A signed-in staff browser on the real chat route, with every place a failure could be copied to
    recorded: the stored chat log row, chat memory, the AI provider's input, escalations, notifications."""

    def setUp(self):
        super().setUp()
        logs = Path(tempfile.mkdtemp(prefix="jh_chat_failure_logs_"))
        self.addCleanup(shutil.rmtree, logs, ignore_errors=True)
        self.saved_logs = Mock(name="save_ai_chat_log_to_mysql")
        self.escalations = Mock(name="create_chat_escalation", return_value=77)
        self.provider = Mock(name="answer_question_with_ai_provider", return_value=None)
        self.recorded = {name: Mock(name=name, wraps=getattr(app_module, name)) for name in
                         ("log_request", "remember_chat_context", "remember_last_ai_answer")}
        for target, value in (("LOG_DIR", logs), ("LOG_CSV", logs / "ai_chat_logs.csv"),
                              ("save_ai_chat_log_to_mysql", self.saved_logs),
                              ("create_chat_escalation", self.escalations),
                              ("answer_question_with_ai_provider", self.provider),
                              ("AI_CHAT_MEMORY", {}), ("AI_LAST_ANSWER_MEMORY", {}), ("AI_FAIL_MEMORY", {}),
                              *self.recorded.items()):
            patcher = patch.object(app_module, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = self.device()
        self.assertEqual(self.login(self.client, lockout.STAFF, lockout.PASSWORD).status_code, 200)

    def ask(self, question, **extra):
        """Post one chat question; return (status, body, server log text)."""
        log = io.StringIO()
        with redirect_stdout(log), redirect_stderr(log):
            response = self.client.post("/api/chat", json={"question": question, "chat_session_id": "failure-test",
                                                           **extra},
                                        headers={"X-CSRF-Token": self.csrf(self.client)})
        return response.status_code, response.get_json(), log.getvalue()

    def everything_kept(self):
        """Every place a failure's text could be copied to, as one string."""
        return repr([
            self.saved_logs.call_args_list,
            {name: mock.call_args_list for name, mock in self.recorded.items()},
            self.escalations.call_args_list, self.provider.call_args_list, self.notify.call_args_list,
            app_module.AI_CHAT_MEMORY, app_module.AI_LAST_ANSWER_MEMORY, app_module.AI_FAIL_MEMORY,
        ])

    def assert_nothing_technical(self, *texts):
        for text in texts:
            for technical in TECHNICAL:
                self.assertNotIn(technical, text)


class AiUnavailableTests(ChatFailureRouteTestCase):
    """The AI provider fails (outage, quota, timeout) with an error holding a file path and a secret:
    staff get "AI chat is currently unavailable" in their language; nothing is escalated."""

    def setUp(self):
        super().setUp()
        self.provider.side_effect = technical_error(RuntimeError)
        patcher = patch.object(app_module, "AI_PROVIDER_SERVICE_AVAILABLE", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_friendly_unavailable_reply_in_each_language_and_no_ticket(self):
        for language, question in QUESTIONS.items():
            with self.subTest(language=language):
                status, body, log = self.ask(question)
                self.assertEqual(status, 200)
                expected = MESSAGES["ai_unavailable"][language]
                self.assertEqual((body["reply"], body["answer"], body["source"]), (expected, expected, "ai_unavailable"))
                self.assertEqual((body["escalation_ready"], body["escalation_required"]), (False, False))
                self.assertNotIn("escalation_offer", body)
                self.assertIn("AI CHAT PROVIDER ERROR: RuntimeError at app.py:", log)
                self.assert_nothing_technical(json.dumps(body, ensure_ascii=False), log)
        self.escalations.assert_not_called()

    def test_the_error_text_reaches_no_reply_log_memory_provider_escalation_or_notification(self):
        for question in (*QUESTIONS.values(), "kiosk"):
            status, body, _ = self.ask(question)
            self.assertEqual(status, 200)
            self.assert_nothing_technical(json.dumps(body, ensure_ascii=False))
        self.assertTrue(self.saved_logs.called, "chat log rows were written")
        self.assert_nothing_technical(self.everything_kept())


class ChatCrashTests(ChatFailureRouteTestCase):
    """The chat route's last-resort handler (an unexpected error anywhere in the chat flow)."""

    def setUp(self):
        super().setUp()
        # Any unexpected error in the flow; here the Team Lead answer lookup.
        self.lookup = Mock(side_effect=technical_error(RuntimeError))
        patcher = patch.object(app_module, "search_similar_question", self.lookup)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_friendly_reply_in_each_language_with_the_same_status_keys_and_ticket(self):
        for language, question in QUESTIONS.items():
            with self.subTest(language=language):
                self.escalations.reset_mock()
                self.saved_logs.reset_mock()
                status, body, log = self.ask(question)
                self.assertEqual(status, 500)
                self.assertEqual(body, {"reply": MESSAGES["escalated"][language], "confidence": 0, "fallback": True,
                                        "escalation": True, "escalation_id": 77})
                # The ticket still gets the staff question and the same fixed note as before.
                self.escalations.assert_called_once()
                self.assertEqual(self.escalations.call_args.args[0], question)
                self.assertEqual(self.escalations.call_args.args[1], {
                    "answer": "An internal system error occurred while generating the answer.",
                    "confidence": 0.0, "source": "system_error"})
                # The stored analytics row keeps only the error type.
                stored = self.saved_logs.call_args.args[0]
                self.assertEqual((stored["source"], stored["error"]), ("prediction_error", "RuntimeError"))
                self.assertIn("AI CHAT ERROR: RuntimeError at app.py:", log)
                self.assertIn(" in chat", log)
                self.assert_nothing_technical(json.dumps(body, ensure_ascii=False), log, self.everything_kept())

    def test_a_failed_ticket_save_still_gets_the_existing_ticket_not_saved_reply(self):
        self.escalations.return_value = None
        status, body, log = self.ask(QUESTIONS["en"])
        self.assertEqual(status, 500)
        self.assertEqual(body["source"], "escalation_save_failed")
        self.assertEqual(body["reply"], "The escalation ticket could not be saved. Please retry or contact a team lead.")
        self.assertIs(body["escalation_id"], None)
        self.assert_nothing_technical(json.dumps(body), log)

    def test_an_attachment_error_with_internal_detail_gets_the_generic_attachment_message(self):
        self.lookup.side_effect = chat_attachment_service.AttachmentError(
            f"Attachment row missing at {FAKE_PATH} key={FAKE_SECRET}")
        for language, question in QUESTIONS.items():
            with self.subTest(language=language):
                status, body, log = self.ask(question)
                self.assertEqual(status, 400)
                self.assertEqual(body, {"message": MESSAGES["attachment_unavailable"][language],
                                        "answer": MESSAGES["attachment_unavailable"][language],
                                        "source": "attachment_unavailable"})
                self.assert_nothing_technical(json.dumps(body, ensure_ascii=False), log)

    def test_the_known_attachment_messages_are_translated(self):
        self.lookup.side_effect = chat_attachment_service.AttachmentError(
            "A valid chat is required for image uploads.")
        status, body, _ = self.ask(QUESTIONS["zh"])
        self.assertEqual((status, body["message"]), (400, MESSAGES["attachment_chat_required"]["zh"]))
        self.lookup.side_effect = chat_attachment_service.AttachmentError(
            "Attachment unavailable. Please attach the image again.")
        status, body, _ = self.ask(QUESTIONS["ms"])
        self.assertEqual((status, body["message"]), (400, MESSAGES["attachment_unavailable"]["ms"]))


class ProviderAnswerTests(ChatFailureRouteTestCase):
    """The AI is the only answer engine: "not found" and "provider failed" are told apart."""

    def setUp(self):
        super().setUp()
        patcher = patch.object(app_module, "AI_PROVIDER_SERVICE_AVAILABLE", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_not_found_offers_related_articles_and_a_team_lead_but_never_escalates_by_itself(self):
        status, body, _ = self.ask(QUESTIONS["zh"])
        self.assertEqual(status, 200)
        self.assertTrue(self.provider.called, "the AI was asked")
        self.assertEqual((body["source"], body["reply"]), ("ai_not_found", MESSAGES["ai_not_found"]["zh"]))
        self.assertEqual(body["type"], "options")
        self.assertTrue(body["escalation_offer"])
        self.assertEqual(body["question"], QUESTIONS["zh"])
        self.assertEqual((body["escalation_ready"], body["escalation_required"]), (False, False))
        for _ in range(3):  # asking again and again never opens a ticket on its own
            self.ask(QUESTIONS["en"])
        self.escalations.assert_not_called()

    def test_provider_error_is_logged_by_type_and_status_and_shows_unavailable(self):
        response = requests.Response()
        response.status_code = 503
        self.provider.side_effect = requests.HTTPError(
            f"503 Server Error for url: https://provider.example/v1?key={FAKE_SECRET}", response=response)
        status, body, log = self.ask(QUESTIONS["en"])
        self.assertEqual(status, 200)
        self.assertIn("AI CHAT PROVIDER ERROR: HTTPError HTTP 503", log)
        self.assertEqual(body["reply"], MESSAGES["ai_unavailable"]["en"])
        self.escalations.assert_not_called()
        self.assert_nothing_technical(json.dumps(body), log)

    def test_no_ai_configured_shows_unavailable(self):
        with patch.object(app_module, "AI_PROVIDER_SERVICE_AVAILABLE", False):
            status, body, _ = self.ask(QUESTIONS["ms"])
        self.assertEqual((status, body["reply"]), (200, MESSAGES["ai_unavailable"]["ms"]))
        self.provider.assert_not_called()


class HelperTests(unittest.TestCase):
    def test_every_failure_message_exists_in_english_chinese_and_malay(self):
        for kind, messages in MESSAGES.items():
            self.assertEqual(set(messages), {"en", "zh", "ms"}, kind)
            for text in messages.values():
                self.assertTrue(text.strip())
                self.assert_plain(text)

    def assert_plain(self, text):
        for technical in ("error", "Error", "exception", "server", "backend", "/", "\\", "{", "}"):
            self.assertNotIn(technical, text)

    def test_the_language_follows_the_question_then_the_chat_page_hint(self):
        language = app_module.chat_failure_language
        self.assertEqual([language(question) for question in QUESTIONS.values()], ["en", "zh", "ms"])
        self.assertEqual(language("", "zh"), "zh")
        self.assertEqual(language("   ", "MS"), "ms")
        self.assertEqual(language("", "fr"), "en")
        self.assertEqual(language("", None), "en")
        self.assertEqual(language("How do I close the kiosk?", "zh"), "en")

    def test_the_log_line_has_the_type_and_place_but_never_the_message(self):
        def load_model():
            raise technical_error()

        log = io.StringIO()
        try:
            load_model()
        except FileNotFoundError as error:
            with redirect_stdout(log):
                app_module.log_chat_failure("INTENT MODEL ERROR", error)
        line = log.getvalue()
        self.assertRegex(line, r"^INTENT MODEL ERROR: FileNotFoundError at test_chat_failure_messages\.py:\d+ in load_model\n$")
        for technical in (FAKE_PATH, FAKE_SECRET, "Errno", "Traceback"):
            self.assertNotIn(technical, line)

    def test_a_library_error_names_the_library_file_and_an_http_status(self):
        log = io.StringIO()
        try:
            json.loads("{" + FAKE_SECRET)
        except ValueError as error:
            with redirect_stdout(log):
                app_module.log_chat_failure("AI CHAT ERROR", error)
        self.assertRegex(log.getvalue(), r"^AI CHAT ERROR: JSONDecodeError at test_chat_failure_messages\.py:\d+ in "
                                         r"test_a_library_error_names_the_library_file_and_an_http_status "
                                         r"\(raised in decoder\.py\)\n$")
        response = requests.Response()
        response.status_code = 429
        log = io.StringIO()
        with redirect_stdout(log):
            app_module.log_chat_failure("AI CHAT PROVIDER FALLBACK ERROR",
                                        requests.HTTPError(f"429 for url ?key={FAKE_SECRET}", response=response))
        self.assertEqual(log.getvalue(), "AI CHAT PROVIDER FALLBACK ERROR: HTTPError HTTP 429\n")

    def test_no_chat_code_puts_exception_text_into_a_reply_or_the_chat_log(self):
        source = Path(app_module.__file__).read_text(encoding="utf-8")
        for text in ("Model prediction failed", "backend terminal", "CREATE ESCALATION ERROR.\"",
                     'jsonify({"message": str(error)', "error=str(error)"):
            self.assertNotIn(text, source)


if __name__ == "__main__":
    unittest.main()
