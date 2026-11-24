"""Speed: the AI answer starts while the old rule engine runs, not after it.

Real /api/chat route on the SQLite stand-in database (see test_login_lockout).
The rule engine and the AI are each slowed to DELAY seconds; run side by side
the question takes about DELAY, one after the other about 2 x DELAY.
Run (from backend/src): python -m unittest test_chat_parallel_ai -v
"""

import time
from unittest.mock import Mock, patch

import test_chat_failure_messages as base
from test_login_lockout import app_module

DELAY = 0.6
AI_ANSWER = {"answer": "Open the kiosk shutters, then switch on the lights.", "sourceTitle": "",
             "article_id": None, "off_topic": False}


class ParallelAITests(base.ChatFailureRouteTestCase):
    def setUp(self):
        super().setUp()
        real_rules = app_module.process_question

        def slow_rules(*args, **kwargs):
            time.sleep(DELAY)
            return real_rules(*args, **kwargs)

        def slow_ai(**kwargs):
            time.sleep(DELAY)
            return self.ai_reply(**kwargs)

        self.ai_reply = Mock(return_value=dict(AI_ANSWER))
        for target, value in (("AI_PROVIDER_SERVICE_AVAILABLE", True), ("process_question", slow_rules),
                              ("answer_question_with_ai_provider", Mock(side_effect=slow_ai))):
            patcher = patch.object(app_module, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def timed_ask(self, question, **extra):
        started = time.monotonic()
        status, body, log = self.ask(question, **extra)
        return time.monotonic() - started, status, body

    def test_first_question_runs_rules_and_ai_side_by_side(self):
        seconds, status, body = self.timed_ask("how do I open the kiosk in the morning")
        self.assertEqual(status, 200)
        self.assertIn(AI_ANSWER["answer"], body.get("reply") or body.get("answer"))
        self.assertEqual(self.ai_reply.call_count, 1, "the AI is asked once")
        self.assertLess(seconds, 2 * DELAY - 0.15, "rules and AI overlapped")
        kwargs = self.ai_reply.call_args.kwargs
        self.assertEqual((kwargs["smart"], kwargs["focus_title"], kwargs["timeout"]), (True, "", 25))

    def test_follow_up_with_the_previous_article_also_overlaps(self):
        history = [{"role": "user", "content": "how do I open the kiosk"},
                   {"role": "assistant", "content": "Open the shutters first."}]
        seconds, status, body = self.timed_ask("what about the lights after that", history=history,
                                               context={"title": "JHKC Kiosk Opening"})
        self.assertEqual(status, 200)
        self.assertEqual(self.ai_reply.call_count, 1)
        self.assertLess(seconds, 2 * DELAY - 0.15)
        self.assertEqual(self.ai_reply.call_args.kwargs["focus_title"], "JHKC Kiosk Opening")

    def test_follow_up_without_the_article_keeps_the_old_order(self):
        history = [{"role": "user", "content": "how do I open the kiosk"},
                   {"role": "assistant", "content": "Open the shutters first."}]
        seconds, status, body = self.timed_ask("what about the lights after that", history=history)
        self.assertEqual(status, 200)
        self.assertEqual(self.ai_reply.call_count, 1)
        self.assertGreaterEqual(seconds, 2 * DELAY - 0.05, "asked after the rule engine, as before")

    def test_greeting_and_step_controls_never_start_the_ai_early(self):
        # (The old flow may still ask the AI as a backup afterwards, as before.)
        early = Mock(wraps=app_module.EarlyCall)
        with patch.object(app_module, "EarlyCall", early):
            for question in ("hello", "next step"):
                self.ask(question)
            self.assertEqual(early.call_count, 0)
            self.ask("how do I open the kiosk in the morning")
            self.assertEqual(early.call_count, 1)

    def test_an_ai_error_in_the_background_is_handled_like_before(self):
        self.ai_reply.side_effect = RuntimeError("provider down")
        status, body, log = self.ask("how do I open the kiosk in the morning")
        self.assertEqual(status, 200)
        self.assertIn("AI CHAT PROVIDER FALLBACK ERROR", log)
        self.assertNotIn("provider down", body.get("reply") or "")


class EarlyCallTests(base.unittest.TestCase):
    def test_value_error_and_inputs(self):
        call = app_module.EarlyCall(lambda a, b: a + b, a=2, b=3)
        self.assertEqual((call.result(), call.kwargs), (5, {"a": 2, "b": 3}))
        failing = app_module.EarlyCall(lambda: (_ for _ in ()).throw(ValueError("x")))
        with self.assertRaises(ValueError):
            failing.result()


if __name__ == "__main__":
    base.unittest.main()
