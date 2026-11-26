"""AI quiz written in small batches at the same time (2026-11-26).

The user wanted no more stiff template questions and fewer time-outs: a quiz
is now split into batches of about 5 questions, written by the configured AI
at the same time, each batch reading different articles (or a different part
of one article). A failed batch is retried once on its own. No AI, database or
network needed. Run:
python -m unittest discover -s backend/src -p test_quiz_ai_batches.py
"""

import threading
import time
import unittest

import quiz_ai_batches as qb


def question(text, title="Opening"):
    return {"question": text, "options": ["a", "b", "c", "d"], "correctAnswerIndex": 0,
            "explanation": "step 1", "sourceTitle": title}


class PlanTests(unittest.TestCase):
    def test_batch_sizes(self):
        self.assertEqual(qb.batch_sizes(1), [1])
        self.assertEqual(qb.batch_sizes(5), [5])
        self.assertEqual(qb.batch_sizes(7), [4, 3])
        self.assertEqual(qb.batch_sizes(10), [5, 5])
        self.assertEqual(qb.batch_sizes(20), [5, 5, 5, 5])
        self.assertEqual(sum(qb.batch_sizes(17)), 17)
        self.assertLessEqual(len(qb.batch_sizes(20)), qb.MAX_BATCHES)

    def test_articles_are_shared_out_in_turn(self):
        self.assertEqual(qb.share_out(["a", "b", "c", "d", "e"], 2), [["a", "c", "e"], ["b", "d"]])
        self.assertEqual(qb.share_out(["a"], 3), [["a"], ["a"], ["a"]])   # too few: every batch reads it

    def test_category_text_reads_far_more_of_each_article_than_before(self):
        long_body = "word " * 1000
        text = qb.source_text([("Opening", long_body), ("Closing", "Lock the door.")])
        self.assertIn("### Opening\n", text)
        self.assertIn("### Closing\nLock the door.", text)
        opening = text.split("### Closing")[0]
        self.assertGreater(len(opening), 1000)          # used to be cut at 500 characters
        self.assertLessEqual(len(opening), qb.CHARS_PER_ARTICLE + 40)

    def test_category_text_has_a_total_limit(self):
        articles = [(f"A{i}", "x" * 2000) for i in range(40)]
        self.assertLessEqual(len(qb.source_text(articles)), qb.CHARS_PER_BATCH)

    def test_a_long_single_article_is_split_into_parts_in_order(self):
        body = " ".join(f"Sentence {i}." for i in range(800))
        parts = qb.article_parts(body, 3)
        self.assertEqual(len(parts), 3)
        self.assertTrue(parts[0].startswith("Sentence 0."))
        self.assertTrue(parts[2].endswith("Sentence 799."))
        self.assertEqual(" ".join(parts), body)

    def test_a_short_single_article_is_not_split(self):
        self.assertEqual(qb.article_parts("Short text.", 3), ["Short text.", "Short text.", "Short text."])


class DedupeTests(unittest.TestCase):
    def test_same_or_almost_same_questions_are_kept_once(self):
        kept = qb.dedupe([question("How many cabinets do you open?"), question("How many cabinets do you open ?"),
                          question("how many cabinets do you open"), question("Who locks the shutter?")])
        self.assertEqual([q["question"] for q in kept], ["How many cabinets do you open?", "Who locks the shutter?"])

    def test_questions_that_differ_in_one_word_are_both_kept(self):
        kept = qb.dedupe([question("How many cabinets do you open at JHKC?"),
                          question("How many cabinets do you open at JHKL?")])
        self.assertEqual(len(kept), 2)

    def test_chinese_questions_too(self):
        kept = qb.dedupe([question("开店要开几个柜子？"), question("开店要开几个柜子?"), question("谁负责锁门？")])
        self.assertEqual(len(kept), 2)


class RunTests(unittest.TestCase):
    def test_batches_run_at_the_same_time(self):
        started, lock = [], threading.Lock()

        def write(job):
            with lock:
                started.append(time.monotonic())
            time.sleep(0.2)
            return [question(f"Q{job['index']}")]

        began = time.monotonic()
        result = qb.run_batches([{"index": i} for i in range(4)], write)
        self.assertLess(time.monotonic() - began, 0.6)       # not 4 x 0.2 one after another
        self.assertEqual([q["question"] for q in result.questions], ["Q0", "Q1", "Q2", "Q3"])
        self.assertEqual(result.failures, [])

    def test_a_failed_batch_is_retried_once_on_its_own(self):
        calls = []

        def write(job):
            calls.append((job["index"], job["retry"]))
            if job["index"] == 1 and not job["retry"]:
                raise TimeoutError("slow")
            return [question(f"Q{job['index']}")]

        result = qb.run_batches([{"index": 0}, {"index": 1}], write)
        self.assertEqual(sorted(calls), [(0, False), (1, False), (1, True)])
        self.assertEqual(len(result.questions), 2)
        self.assertEqual(result.failures, [])

    def test_a_batch_that_fails_twice_is_reported_and_the_rest_still_count(self):
        def write(job):
            if job["index"] == 1:
                raise ValueError("bad json")
            return [question(f"Q{job['index']}")]

        result = qb.run_batches([{"index": 0}, {"index": 1}, {"index": 2}], write)
        self.assertEqual([q["question"] for q in result.questions], ["Q0", "Q2"])
        self.assertEqual(len(result.failures), 1)
        self.assertIsInstance(result.failures[0], ValueError)

    def test_an_empty_batch_counts_as_failed(self):
        result = qb.run_batches([{"index": 0}], lambda job: [])
        self.assertEqual(result.questions, [])
        self.assertEqual(len(result.failures), 1)

    def test_ai_not_set_up_stops_at_once(self):
        class NotConfigured(Exception):
            pass

        calls = []

        def write(job):
            calls.append(job["index"])
            raise NotConfigured()

        with self.assertRaises(NotConfigured):
            qb.run_batches([{"index": 0}], write, stop_on=(NotConfigured,))
        self.assertEqual(calls, [0])                          # not retried


if __name__ == "__main__":
    unittest.main()


# ------------------------------------------------- the real route in app.py
import json  # noqa: E402
import os  # noqa: E402
from unittest import mock  # noqa: E402

os.environ.setdefault("FLASK_SECRET_KEY", "dummy-test-only-key-not-a-secret-0123456789")
os.environ.setdefault("NOTION_AUTO_SYNC_ENABLED", "false")
os.environ.setdefault("IMAGE_INDEX_WORKER_ENABLED", "false")
os.environ.setdefault("DOCUMENT_TEXT_BACKFILL", "false")

import app as app_module  # noqa: E402


def first_article(prompt):
    # The instructions mention "###" too, so look only after "Source content:".
    return prompt.split("Source content:")[1].split("### ")[1].split("\n")[0]


def ai_reply_for(prompt):
    """A fake AI: as many questions as the prompt asks for, about the first article it was given."""
    count = int(prompt.split("EXACTLY ")[1].split(" ")[0])
    title = first_article(prompt)
    return json.dumps([{"question": f"{title} question {i} {prompt.count('###')}", "options": ["a", "b", "c", "d"],
                        "correctAnswerIndex": 1, "explanation": "from the source", "sourceTitle": title}
                       for i in range(count)])


class RouteTests(unittest.TestCase):
    def generate(self, body, reply=ai_reply_for, articles=None):
        articles = articles if articles is not None else [(f"Article {i}", f"Body of article {i}. " * 50) for i in range(12)]
        prompts = []

        def fake_reply(prompt, timeout=None):
            prompts.append((prompt, timeout))
            return reply(prompt)

        with app_module.app.test_request_context("/api/admin/quizzes/ai-generate", method="POST", json=body), \
                mock.patch.object(app_module, "load_ai_quiz_articles", return_value=articles), \
                mock.patch.object(app_module.ai_provider_service, "generate_ai_reply", side_effect=fake_reply), \
                mock.patch.object(app_module, "resolve_generated_quiz_materials", return_value=[]):
            reply = app_module.app.make_response(app_module.ai_generate_quiz())
        return reply, prompts

    def test_twenty_questions_are_four_batches_of_five_reading_different_articles(self):
        reply, prompts = self.generate({"count": 20, "sourceCategory": "SOP", "difficulty": "Medium"})
        self.assertEqual(reply.status_code, 200)
        quiz = reply.get_json()["quiz"]
        self.assertEqual(len(quiz["questions"]), 20)
        self.assertEqual(quiz["generationMethod"], "ai_provider")
        self.assertEqual(len(prompts), 4)
        self.assertTrue(all("EXACTLY 5 " in prompt for prompt, _ in prompts))
        self.assertTrue(all(timeout == qb.BATCH_TIMEOUT_SECONDS for _, timeout in prompts))
        firsts = {first_article(prompt) for prompt, _ in prompts}
        self.assertEqual(firsts, {"Article 0", "Article 1", "Article 2", "Article 3"})   # each batch its own articles
        self.assertTrue(all("batch" in prompt for prompt, _ in prompts))

    def test_ai_failure_never_falls_back_to_template_questions(self):
        def broken(prompt):
            raise RuntimeError("provider down")
        reply, prompts = self.generate({"count": 5, "sourceCategory": "SOP"}, reply=broken)
        self.assertEqual(reply.status_code, 400)
        self.assertNotIn("quiz", reply.get_json())
        self.assertEqual(len(prompts), 2)            # tried, then retried once
        self.assertFalse(hasattr(app_module, "build_ai_quiz_questions"))

    def test_ai_not_set_up_says_so(self):
        def not_configured(prompt):
            raise app_module.ai_provider_service.AIProviderNotConfiguredError("x")
        reply, prompts = self.generate({"count": 5}, reply=not_configured)
        self.assertEqual(reply.get_json()["message"], "AI model is not configured. Please configure it in AI Model Settings.")
        self.assertEqual(len(prompts), 1)

    def test_one_bad_batch_still_returns_the_others(self):
        def flaky(prompt):
            if first_article(prompt) == "Article 1":
                return "not json at all"
            return ai_reply_for(prompt)
        reply, _ = self.generate({"count": 10, "sourceCategory": "SOP"}, reply=flaky)
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(len(reply.get_json()["quiz"]["questions"]), 5)
