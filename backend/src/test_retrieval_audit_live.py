"""The live search accuracy check (AI Model Settings page): question making,
pass/miss rules, miss causes, background run, and the manager-only routes.
Run: python -m unittest discover -s backend/src -p test_retrieval_audit_live.py
"""

import ast
import threading
import time
import types
import unittest
from pathlib import Path

import retrieval_audit as audit

OPENING = {"article_id": 1, "title": "JHKC Opening Checklist", "category": "SOP", "content": (
    "<h2>Before opening</h2><ul><li>Switch on the main lights and the signboard.</li>"
    "<li>Unlock all cabinet doors from B, C, E, F, K and L.</li>"
    "<li>Count the float cash in the drawer and record it.</li></ul>"
    "<p>Turn on the iPad terminal and log into the POS system.</p>")}
CLOSING = {"article_id": 2, "title": "JHKC Closing Checklist", "category": "SOP", "content": (
    "<p>Lock every cabinet door and hand the keys to the supervisor.</p>"
    "<p>Charge the iPad terminal overnight in the back office drawer.</p>"
    "<p>Clock out using TimeTec before leaving the outlet.</p>")}
SHIFT = {"article_id": 3, "title": "Shift Handover", "category": "SOP", "content": (
    "<p>Write the handover notes in the shift book for the next team.</p>"
    "<p>Clock out using TimeTec before leaving the outlet today.</p>")}


def wait_until_finished(timeout=5):
    deadline = time.monotonic() + timeout
    while audit.status()["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    return audit.status()


class QuestionTests(unittest.TestCase):
    def test_sentences_follow_blocks_and_sentence_ends(self):
        sentences = audit.article_sentences({"content": "<p>One two. Three four!</p><li>Five</li>"})
        self.assertEqual(sentences, ["One two.", "Three four!", "Five"])

    def test_questions_spread_over_the_article_and_use_rare_and_title_words(self):
        questions, _ = audit.make_questions([OPENING, CLOSING, SHIFT])
        opening = [q for q in questions if q["article_id"] == 1]
        self.assertEqual(len(opening), 3)
        self.assertEqual(opening[0]["sentence"], "Switch on the main lights and the signboard.")
        self.assertEqual(opening[-1]["sentence"], "Turn on the iPad terminal and log into the POS system.")
        title_words = {"jhkc", "opening", "checklist"}
        # First and last carry a title word; the middle one, like many staff questions, does not.
        self.assertEqual([bool(set(item["question"].split()) & title_words) for item in opening], [True, False, True])

    def test_too_short_sentences_are_not_asked(self):
        questions, _ = audit.make_questions([{"article_id": 9, "title": "X", "content": "<p>Wash hands.</p>"}])
        self.assertEqual(questions, [])

    def test_question_count_is_capped_evenly(self):
        many = [dict(OPENING, article_id=i) for i in range(50)]
        questions, _ = audit.make_questions(many, max_questions=20)
        self.assertEqual(len(questions), 20)
        self.assertGreater(len({q["article_id"] for q in questions}), 10)


class RunTests(unittest.TestCase):
    def test_pass_wrong_article_and_line_cut(self):
        articles = [OPENING, CLOSING, SHIFT]

        def build_context(question, preloaded):
            self.assertIs(preloaded[0], articles)
            # Always picks the closing article and shows only its first line.
            return "### JHKC Closing Checklist\n" + audit.article_sentences(CLOSING)[0], \
                [{"article_id": 2, "title": CLOSING["title"]}]

        report = audit.run_audit(articles, {}, build_context)
        self.assertEqual(report["articleCount"], 3)
        self.assertEqual(report["passed"], 1)  # the closing article's first line
        self.assertEqual(report["wrongArticle"], 3 + 2)  # every opening and shift question
        self.assertEqual(report["lineCut"], 2)  # closing lines 2 and 3
        miss = next(m for m in report["misses"] if m["article_id"] == 1)
        self.assertEqual((miss["cause"], miss["picked"]), ("wrong_article", ["JHKC Closing Checklist"]))
        self.assertAlmostEqual(report["rate"], round(1 / report["total"], 4))

    def test_same_step_in_another_article_counts_as_found(self):
        _, sentences = audit.make_questions([CLOSING, SHIFT])
        duplicates = audit._NearDuplicates(sentences)
        context = "### Shift Handover\nClock out using TimeTec before leaving the outlet today."
        self.assertTrue(duplicates.visible("Clock out using TimeTec before leaving the outlet.", context))
        self.assertFalse(duplicates.visible("Charge the iPad terminal overnight in the back office drawer.", context))


class SameInfoTests(unittest.TestCase):
    SENTENCE = "Click Shopify app and start the session for iPad."

    def test_same_step_in_other_words_counts(self):
        context = "### Shopify POS app Opening\nOpen the Shopify POS app on the iPad and start a new session."
        self.assertTrue(audit.same_info_in(self.SENTENCE, context))

    def test_words_scattered_over_the_context_do_not_count(self):
        filler = " ".join(f"filler{i}" for i in range(30))
        context = f"Click the bell. {filler} Download the app. {filler} Start early. {filler} New iPad case."
        self.assertFalse(audit.same_info_in(self.SENTENCE, context))

    def test_too_few_shared_words_do_not_count(self):
        self.assertFalse(audit.same_info_in(self.SENTENCE, "Charge the iPad overnight in the drawer."))

    def test_run_counts_it_as_found_elsewhere(self):
        article = {"article_id": 5, "title": "Aeon Roadshow Opening List", "content": f"<p>{self.SENTENCE}</p>"}
        context = "### Shopify POS app Opening\nOpen the Shopify POS app on the iPad and start a new session."
        report = audit.run_audit([article], {}, lambda q, p: (context, [{"article_id": 9, "title": "Shopify"}]))
        self.assertEqual((report["passed"], report["foundElsewhere"], report["misses"]), (1, 1, []))


class DuplicateTests(unittest.TestCase):
    def test_same_title_and_same_text_are_listed(self):
        text = "<p>Keep the stirrers and tissues under the counter, left side.</p>"
        articles = [
            {"article_id": 1, "title": "Stirrer & Tissue Location SOP", "category": "SOP", "content": text},
            {"article_id": 2, "title": "stirrer &  tissue location sop ", "category": "Notion", "content": "<p>Other</p>"},
            {"article_id": 3, "title": "Where are the stirrers", "category": "SOP", "content": text},
            {"article_id": 4, "title": "Closing", "category": "SOP", "content": "<p>Lock up.</p>"},
        ]
        groups = audit.duplicate_articles(articles)
        same_title = next(g for g in groups if g["reason"] == "same_title")
        self.assertEqual([a["article_id"] for a in same_title["articles"]], [1, 2])
        same_text = next(g for g in groups if g["reason"] == "same_content")
        self.assertEqual([a["article_id"] for a in same_text["articles"]], [1, 3])
        self.assertEqual(len(groups), 2)

    def test_report_includes_duplicates(self):
        report = audit.run_audit([OPENING, dict(OPENING, article_id=7)], {}, lambda q, p: ("", []))
        self.assertEqual(len(report["duplicates"]), 1)


class BackgroundTests(unittest.TestCase):
    def setUp(self):
        audit._state.update(status="idle", done=0, total=0, result=None, error=None)

    def test_runs_in_the_background_and_reports_progress(self):
        release = threading.Event()

        def build_context(question, preloaded):
            release.wait(2)
            return "", []

        self.assertTrue(audit.start(lambda: ([OPENING], {}), build_context))
        self.assertEqual(audit.status()["status"], "running")
        self.assertFalse(audit.start(lambda: ([OPENING], {}), build_context), "second start refused")
        release.set()
        state = wait_until_finished()
        self.assertEqual((state["status"], state["done"], state["total"]), ("done", 3, 3))
        self.assertEqual(state["result"]["passed"], 0)

    def test_a_failure_is_reported_and_keeps_the_last_result(self):
        audit._state["result"] = {"passed": 7}

        def broken():
            raise RuntimeError("database down")

        self.assertTrue(audit.start(broken, lambda q, p: ("", [])))
        state = wait_until_finished()
        self.assertEqual(state["status"], "failed")
        self.assertTrue(state["error"])
        self.assertEqual(state["result"], {"passed": 7})


class RouteTests(unittest.TestCase):
    source = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    def setUp(self):
        names = {"start_retrieval_audit", "get_retrieval_audit", "_audit_build_context"}
        nodes = [node for node in self.tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        for node in nodes:
            node.decorator_list = []
        self.calls = []
        self.fake = types.SimpleNamespace(
            start=lambda load, build: self.calls.append((load, build)) or self.allowed,
            status=lambda: {"status": "running"},
        )
        self.allowed = True
        self.env = {"jsonify": lambda value: value, "retrieval_audit": self.fake,
                    "load_chat_search_data": "LOADER",
                    "build_ai_chat_context": lambda q, **kw: (q, kw)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "audit_routes.py", "exec"), self.env)

    def test_start_and_status(self):
        result, status = self.env["start_retrieval_audit"]()
        self.assertEqual((status, result["audit"]["status"]), (202, "running"))
        load, build = self.calls[0]
        self.assertEqual(load, "LOADER")
        self.assertEqual(build("aeon opening", "DATA"),
                         ("aeon opening", {"search_question": "aeon opening", "preloaded": "DATA"}))
        result, status = self.env["get_retrieval_audit"]()
        self.assertEqual(status, 200)

    def test_already_running_gives_409(self):
        self.allowed = False
        _, status = self.env["start_retrieval_audit"]()
        self.assertEqual(status, 409)

    def test_managers_only(self):
        managers = next(ast.literal_eval(node.value) for node in self.tree.body if isinstance(node, ast.Assign)
                        and any(getattr(t, "id", "") == "_MANAGER_ENDPOINTS" for t in node.targets))
        self.assertTrue({"start_retrieval_audit", "get_retrieval_audit"} <= managers)


if __name__ == "__main__":
    unittest.main()
