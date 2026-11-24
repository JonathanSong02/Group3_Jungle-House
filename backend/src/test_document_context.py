"""build_ai_chat_context reads attachment text. Extracts the real function from
app.py (no app import, no database, no AI). Run:
python -m unittest discover -s backend/src -p test_document_context.py
"""

import ast
import re
import types
import unittest
from pathlib import Path

import document_text_service
import system_knowledge

source = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
tree = ast.parse(source)
node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_ai_chat_context")


class Cursor:
    def __init__(self, articles, doc_rows, fail_docs=False):
        self.articles, self.doc_rows, self.fail_docs = articles, doc_rows, fail_docs
        self.rows = []

    def execute(self, sql, params=()):
        if "FROM wiki_article" in sql:
            self.rows = self.articles
        elif "FROM article_attachment_text" in sql:
            if self.fail_docs:
                raise RuntimeError("table missing")
            self.rows = self.doc_rows
        else:
            raise AssertionError(sql)

    def fetchall(self):
        return self.rows

    def close(self):
        pass


def build(articles, doc_rows, question, fail_docs=False, max_chars=6000, auth_user=None, semantic=None, **kwargs):
    """`semantic` = what the meaning search returns ({article_id: (similarity, source, section)});
    None = not available (another provider, no key), i.e. word search only."""
    document_text_service.invalidate_cache()
    cursor = Cursor(articles, doc_rows, fail_docs)
    env = {
        "semantic_article_matches": lambda q: semantic,
        "FUSION_RANK_OFFSET": 20, "SEMANTIC_WEIGHT": 1.0,
        "system_knowledge": system_knowledge,
        "SYSTEM_CONTEXT_LIMIT": 3500, "DETAIL_EXCERPT_CHARS": 9000, "DETAIL_MAX_CHARS": 14000, "TITLE_WORD_WEIGHT": 3,
        "g": types.SimpleNamespace(get=lambda key, default=None: auth_user if key == "auth_user" else default),
        "re": re,
        "get_db_connection": lambda: types.SimpleNamespace(cursor=lambda **k: cursor, close=lambda: None),
        "tokenize_for_knowledge_match": lambda text: set(re.findall(r"[a-z0-9]+", str(text).lower())),
        "clean_question": lambda text: text,
        "calculate_article_match_score": lambda q, a: 0.0,
        "CONFIDENCE_DIRECT_ANSWER": 0.72,
        "document_text_service": document_text_service,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "build_ai_chat_context.py", "exec"), env)
    return env["build_ai_chat_context"](question, max_chars=max_chars, **kwargs)


ARTICLES = [
    {"article_id": 1, "title": "Kiosk Opening", "content": "Turn on the lights.", "category": "SOP", "sub_category": ""},
    {"article_id": 2, "title": "Staff Handbook", "content": "See the attached handbook.", "category": "Training", "sub_category": ""},
]
HANDBOOK = ("Welcome to the company. " * 40) + "Annual leave requests need fourteen days notice. " + ("Dress code applies. " * 40)


class DocumentContextTests(unittest.TestCase):
    def test_article_found_only_through_its_pdf(self):
        text, candidates = build(ARTICLES, [{"article_id": 2, "text": HANDBOOK}], "annual leave notice")
        self.assertIn(2, [c["article_id"] for c in candidates])
        self.assertIn("Annual leave requests need fourteen days notice", text)
        self.assertIn("Attached document (excerpt):", text)

    def test_excerpt_not_whole_document(self):
        text, _ = build(ARTICLES, [{"article_id": 2, "text": HANDBOOK}], "annual leave notice")
        self.assertLess(len(text), len(HANDBOOK))

    def test_context_stays_within_cap(self):
        rows = [{"article_id": 2, "text": "annual leave notice. " * 2000}]
        text, _ = build(ARTICLES, rows, "annual leave notice", max_chars=1200)
        self.assertLessEqual(len(text), 1200)

    def test_document_table_failure_keeps_old_behaviour(self):
        text, candidates = build(ARTICLES, [], "kiosk opening lights", fail_docs=True)
        self.assertEqual([c["article_id"] for c in candidates], [1])
        self.assertNotIn("Attached document", text)

    def test_no_documents_output_unchanged(self):
        text, _ = build(ARTICLES, [], "kiosk opening lights")
        self.assertEqual(text, "### Kiosk Opening\nTurn on the lights.\n")


class SystemContextTests(unittest.TestCase):
    def test_count_question_gets_statistics_first(self):
        text, _ = build(ARTICLES, [], "how many articles are there?")
        self.assertTrue(text.startswith("### Knowledge Base statistics"))
        self.assertIn("2 articles", text)

    def test_guide_uses_the_signed_in_role(self):
        text, _ = build(ARTICLES, [], "how do I add a new article?", auth_user={"user_id": 7, "role_name": "Staff"})
        self.assertIn("### System guide: Content Management", text)
        self.assertIn("cannot use this", text)

    def test_document_summary_reaches_the_context(self):
        rows = [{"article_id": 2, "file_url": "/static/uploads/articles/1_abc123_Lab_10_Manual.pdf",
                 "status": "ok", "text": HANDBOOK, "summary": "Lab 10 covers resistors."}]
        text, _ = build(ARTICLES, rows, "what is the lab 10 manual about?")
        self.assertIn("Lab 10 covers resistors.", text)
        self.assertIn('attached to "Staff Handbook"', text)

    def test_system_part_never_crowds_out_everything(self):
        text, _ = build(ARTICLES, [], "how many articles are there? kiosk opening lights", max_chars=6000)
        self.assertIn("### Kiosk Opening", text)

    def test_ordinary_question_unchanged(self):
        text, _ = build(ARTICLES, [], "kiosk opening lights")
        self.assertEqual(text, "### Kiosk Opening\nTurn on the lights.\n")


class LongArticleTests(unittest.TestCase):
    """Long articles must not crowd out the line that answers the question."""
    CLOSING = {"article_id": 11, "title": "Kiosk Closing Check List", "category": "SOP", "sub_category": "",
               "content": " ".join(f"Step {i}: wipe the counter and count stock in drawer {i} and record it in the sheet." for i in range(150))}
    OPENING = {"article_id": 12, "title": "JHKC Kiosk Opening", "category": "SOP", "sub_category": "",
               "content": " ".join(f"Step {i}: switch on light {i} near the entrance." for i in range(40))
               + " Step 41: Unlock all cabinet doors from B, C, E, F, K and L. Step 42: Keep the locks inside."}

    # Ranked above JHKC (more question words, long), like the real roadshow lists.
    SPRING = {"article_id": 13, "title": "Spring Roadshow Opening List", "category": "SOP", "sub_category": "",
              "content": " ".join(f"Step {i}: how many testers you need to open the roadshow booth {i}." for i in range(150))}

    def test_answer_line_reaches_the_ai_even_at_the_end_of_a_long_article(self):
        text, candidates = build([self.SPRING, self.CLOSING, self.OPENING], [], "how many cabinet i need to open when opening")
        self.assertIn(12, [c["article_id"] for c in candidates])
        self.assertIn("Unlock all cabinet doors from B, C, E, F, K and L", text)
        self.assertLessEqual(len(text), 6000)

    def test_every_chosen_article_gets_a_share(self):
        text, candidates = build([self.CLOSING, self.OPENING], [], "kiosk step counter cabinet opening")
        for candidate in candidates:
            self.assertIn(f"### {candidate['title']}", text)

    def test_short_articles_are_passed_in_full(self):
        text, _ = build(ARTICLES, [], "kiosk opening lights")
        self.assertEqual(text, "### Kiosk Opening\nTurn on the lights.\n")


class RareWordRankingTests(unittest.TestCase):
    """A rare, specific word (TimeTec) must outweigh words that are everywhere."""
    COMMON = [{"article_id": 20 + i, "title": f"Closing List {i}", "category": "SOP", "sub_category": "",
               "content": "Using the iPad, check the terminal and clock the stock before closing. " * 3}
              for i in range(6)]
    RARE = {"article_id": 30, "title": "Staff Attendance", "category": "Notice", "sub_category": "",
            "content": "Clock out using TimeTec before you leave."}

    def test_rare_word_article_is_chosen(self):
        _, candidates = build(self.COMMON + [self.RARE], [], "clock out using timetec check terminal")
        self.assertEqual(candidates[0]["article_id"], 30)

    def test_rare_word_passage_is_chosen_inside_a_long_article(self):
        long_article = {"article_id": 31, "title": "Kiosk Opening", "category": "SOP", "sub_category": "",
                        "content": ("Check the area and check the stock. " * 120) + "Check Maybank app is logged in. "
                        + ("Check the area again. " * 120)}
        text, _ = build([long_article], [], "check maybank app logged")
        self.assertIn("Check Maybank app is logged in.", text)


class FocusArticleTests(unittest.TestCase):
    def test_previous_article_comes_first_even_without_matching_words(self):
        text, candidates = build(ARTICLES, [], "what is next", focus_title="staff handbook")
        self.assertEqual(candidates[0]["article_id"], 2)
        self.assertTrue(text.startswith("### Staff Handbook"))

    def test_unknown_focus_title_changes_nothing(self):
        self.assertEqual(build(ARTICLES, [], "kiosk opening lights", focus_title="Nope"),
                         build(ARTICLES, [], "kiosk opening lights"))


class ExactTitleTests(unittest.TestCase):
    """Typing (or clicking) exactly one article's title puts that article first."""
    PROMOTIONS = [
        {"article_id": 40, "title": "\U0001F1F2\U0001F1FE Merdeka Promotion", "category": "SALES", "sub_category": "",
         "content": "Merdeka promotion: promotion price for every honey promotion set, promotion ends 31 August."},
        {"article_id": 41, "title": "Free Drink Promotion", "category": "SALES", "sub_category": "",
         "content": "Free drink promotion with every promotion purchase above RM50, promotion while stocks last."},
        {"article_id": 42, "title": "Promotion", "category": "SALES", "sub_category": "",
         "content": "Current promotions this month."},
    ]

    def test_exact_title_comes_first(self):
        _, candidates = build(self.PROMOTIONS, [], "promotion")
        self.assertEqual(candidates[0]["article_id"], 42)
        self.assertEqual(len(candidates), 3)

    def test_clicked_option_with_emoji_comes_first(self):
        _, candidates = build(self.PROMOTIONS, [], "Merdeka Promotion!")
        self.assertEqual(candidates[0]["article_id"], 40)

    def test_broad_question_is_not_pinned(self):
        _, candidates = build(self.PROMOTIONS, [], "what promotion now")
        self.assertNotEqual(candidates[0]["article_id"], 42)

    def test_two_articles_with_the_same_title_both_come_first(self):
        # Like the real #14 and #249, both "Promotion" with different content.
        twin = dict(self.PROMOTIONS[2], article_id=43, content="Old promotion list from April.")
        text, candidates = build(self.PROMOTIONS + [twin], [], "promotion")
        self.assertEqual({c["article_id"] for c in candidates[:2]}, {42, 43})
        self.assertIn("Current promotions this month.", text)
        self.assertIn("Old promotion list from April.", text)

    def test_follow_up_focus_still_wins(self):
        _, candidates = build(self.PROMOTIONS, [], "promotion", focus_title="Free Drink Promotion")
        self.assertEqual(candidates[0]["article_id"], 41)


class DetailModeTests(unittest.TestCase):
    LONG = " ".join(f"Lab step {i}: connect resistor {i} to the breadboard row {i}." for i in range(400))

    def test_detail_gives_a_much_longer_excerpt(self):
        rows = [{"article_id": 2, "text": self.LONG}]
        normal, _ = build(ARTICLES, rows, "lab resistor breadboard steps")
        detailed, _ = build(ARTICLES, rows, "lab resistor breadboard steps", detail=True)
        self.assertLess(len(normal), 2200)
        self.assertGreater(len(detailed), 6000)
        self.assertLessEqual(len(detailed), 14000)

    def test_detail_without_documents_is_unchanged(self):
        self.assertEqual(build(ARTICLES, [], "kiosk opening lights", detail=True),
                         build(ARTICLES, [], "kiosk opening lights"))


class SyncHookTests(unittest.TestCase):
    def load_sync(self, articles, sync_article):
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_sync_document_texts")
        self.conn = types.SimpleNamespace(commits=0, rollbacks=0)
        cursor = types.SimpleNamespace(executed=[], close=lambda: None)
        cursor.execute = lambda sql, params=(): cursor.executed.append((sql, params))
        cursor.fetchall = lambda: articles
        self.conn.cursor = lambda **k: cursor
        self.conn.commit = lambda: setattr(self.conn, "commits", self.conn.commits + 1)
        self.conn.rollback = lambda: setattr(self.conn, "rollbacks", self.conn.rollbacks + 1)
        self.conn.close = lambda: None
        self.invalidations = 0
        def invalidate():
            self.invalidations += 1
        fake_service = types.SimpleNamespace(ensure_table=lambda c: None, sync_article=sync_article,
                                             invalidate_cache=invalidate)
        env = {"get_db_connection": lambda: self.conn, "document_text_service": fake_service,
               "UPLOAD_FOLDER": Path("uploads"), "_summarize_document_text": lambda text: None}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "sync.py", "exec"), env)
        return env["_sync_document_texts"], cursor

    def test_each_article_synced_and_one_failure_does_not_stop_others(self):
        seen = []
        def sync_article(cursor, article, folder, summarize=None):
            seen.append(article["article_id"])
            if article["article_id"] == 1:
                raise ValueError("bad file")
        sync, cursor = self.load_sync([{"article_id": 1}, {"article_id": 2}], sync_article)
        sync([1, 2])
        self.assertEqual(seen, [1, 2])
        self.assertEqual(self.conn.rollbacks, 1)
        self.assertEqual(self.conn.commits, 1)
        self.assertEqual(self.invalidations, 1)   # cleared after the successful commit
        self.assertIn((1, 2), [params for _, params in cursor.executed])

    def test_backfill_reads_all_live_articles(self):
        sync, cursor = self.load_sync([], lambda *a, **k: 0)
        sync(None)
        self.assertIn("is_deleted", cursor.executed[0][0])
        self.assertIn("content", cursor.executed[0][0])   # Notion files are linked inside the content

    def load_summarizer(self, service, available=True):
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_summarize_document_text")
        env = {"AI_PROVIDER_SERVICE_AVAILABLE": available, "ai_provider_service": service}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "summary.py", "exec"), env)
        return env["_summarize_document_text"]

    def test_summary_uses_ai_once_and_treats_document_as_data(self):
        prompts = []
        service = types.SimpleNamespace(generate_ai_reply=lambda p, timeout=0: prompts.append(p) or "Short summary")
        self.assertEqual(self.load_summarizer(service)("Lab manual text"), "Short summary")
        self.assertEqual(len(prompts), 1)
        self.assertIn("not instructions", prompts[0])
        self.assertIn("Lab manual text", prompts[0])

    def test_summary_none_without_ai_or_on_error(self):
        self.assertIsNone(self.load_summarizer(None, available=False)("text"))
        def boom(p, timeout=0):
            raise RuntimeError("down")
        self.assertIsNone(self.load_summarizer(types.SimpleNamespace(generate_ai_reply=boom))("text"))

    def test_sync_passes_the_summarizer(self):
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_sync_document_texts")
        self.assertIn("summarize=_summarize_document_text", ast.unparse(fn))

    def test_create_and_edit_routes_start_sync_after_commit(self):
        routes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("add_article", "edit_article")]
        self.assertEqual(len(routes), 2)
        for route in routes:
            body = ast.unparse(route)
            with self.subTest(route=route.name):
                self.assertIn("start_document_text_sync([article_id])", body)
                self.assertLess(body.index("conn.commit()"), body.index("start_document_text_sync([article_id])"))


if __name__ == "__main__":
    unittest.main()
