"""'What is in the system' answers and the built-in system guide.
No database, network or AI. Run:
python -m unittest discover -s backend/src -p test_system_knowledge.py
"""

import re
import unittest
from datetime import datetime
from pathlib import Path

import system_knowledge as sk

FRONTEND = Path(__file__).resolve().parents[2] / "jungle-house-wiki-ai" / "src"

ARTICLES = [
    {"article_id": 1, "title": "Kiosk Opening", "category": "SOP"},
    {"article_id": 2, "title": "Kiosk Closing", "category": "SOP"},
    {"article_id": 3, "title": "Golden Passion Honey", "category": "PRODUCT"},
    {"article_id": 4, "title": "Staff Handbook", "category": "Training"},
]
DOCUMENTS = {
    4: {"text": "handbook text", "files": [
        {"url": "/static/uploads/articles/1_abc123_Staff_Handbook.pdf", "name": "Staff_Handbook.pdf",
         "status": "ok", "summary": "Company rules on leave, uniform and conduct."}]},
    1: {"text": "lab text", "files": [
        {"url": "/static/uploads/articles/2_def456_Lab_10_Manual.docx", "name": "Lab_10_Manual.docx",
         "status": "ok", "summary": "Lab 10 covers resistors and breadboards."},
        {"url": "/static/uploads/articles/3_notion_import.pdf", "name": "notion_import.pdf",
         "status": "empty", "summary": None}]},
}


class QuizCursor:
    def __init__(self, quizzes=(), results=()):
        self.quizzes, self.results, self.rows, self.sql = list(quizzes), list(results), [], []

    def execute(self, sql, params=()):
        self.sql.append((sql, params))
        if "FROM quiz_result" in sql:
            self.rows = [r for r in self.results if r["user_id"] == params[0]]
        elif "FROM quiz" in sql:
            self.rows = self.quizzes
        else:
            raise AssertionError(sql)

    def fetchall(self):
        return self.rows


QUIZZES = [
    {"quiz_id": 1, "title": "Opening SOP Quiz", "category": "SOP", "difficulty": "Easy", "passing_score": 80, "question_count": 5},
    {"quiz_id": 2, "title": "Honey Products", "category": "PRODUCT", "difficulty": "Medium", "passing_score": 80, "question_count": 8},
]
RESULTS = [
    {"user_id": 7, "quiz_id": 1, "percentage": 60, "completed_at": datetime(2026, 11, 1, 10, 0)},
    {"user_id": 7, "quiz_id": 1, "percentage": 90, "completed_at": datetime(2026, 11, 3, 10, 0)},
    {"user_id": 8, "quiz_id": 2, "percentage": 100, "completed_at": datetime(2026, 11, 3, 10, 0)},
]


def entries(question, role="staff", user_id=7, cursor=None, documents=DOCUMENTS):
    return dict(sk.context_entries(cursor or QuizCursor(QUIZZES, RESULTS), question, ARTICLES,
                                   documents, user_id=user_id, role=role))


class StatsTests(unittest.TestCase):
    def test_article_counts_by_category(self):
        result = entries("how many articles are there in each category?")
        body = result["Knowledge Base statistics"]
        self.assertIn("4 articles", body)
        self.assertIn("SOP: 2", body)
        self.assertIn("PRODUCT: 1", body)

    def test_chinese_and_malay_count_questions(self):
        self.assertIn("Knowledge Base statistics", entries("知识库总共有几篇文章？"))
        self.assertIn("Knowledge Base statistics", entries("berapa artikel dalam kategori SOP"))

    def test_ordinary_work_question_adds_nothing(self):
        for question in ["How do I open the kiosk in the morning?", "where do I put the test strips?",
                         "what is the price of golden passion honey?", "怎么开店", "蜂蜜多少钱",
                         "kalau buka kedai apa perlu buat", "where do I keep the iPad when closing?"]:
            with self.subTest(question=question):
                self.assertEqual(entries(question), {})


class DocumentListTests(unittest.TestCase):
    def test_count_and_list_documents(self):
        body = entries("how many pdf files are there?")["Attached documents"]
        self.assertIn("3 attached documents", body)
        for name in ["Staff_Handbook.pdf", "Lab_10_Manual.docx", "notion_import.pdf"]:
            self.assertIn(name, body)
        self.assertIn("no readable text", body)

    def test_summary_of_named_document(self):
        body = entries("what is the lab 10 manual about?")["Attached documents"]
        self.assertIn("resistors and breadboards", body)
        self.assertIn('"Kiosk Opening"', body)   # which article it is attached to

    def test_files_of_binned_articles_not_counted(self):
        body = entries("how many pdf files?", documents={99: DOCUMENTS[4]})["Attached documents"]
        self.assertIn("no PDF or Word documents", body)

    def test_document_list_is_capped(self):
        many = {1: {"text": "", "files": [{"url": f"/x/{i}.pdf", "name": f"File_{i}.pdf", "status": "ok",
                                            "summary": "s" * 300} for i in range(200)]}}
        body = entries("list all documents", documents=many)["Attached documents"]
        self.assertLessEqual(len(body), sk.DOCUMENTS_LIMIT)
        self.assertIn("200 attached documents", body)


class QuizTests(unittest.TestCase):
    def test_quiz_list(self):
        body = entries("how many quizzes are there?")["Quizzes"]
        self.assertIn("2 active quizzes", body)
        self.assertIn("Opening SOP Quiz", body)
        self.assertIn("8 questions", body)

    def test_my_quiz_progress_only_mine(self):
        body = entries("which quiz have I not done yet and what was my score?")["Your quiz progress"]
        self.assertIn("Opening SOP Quiz", body)
        self.assertIn("90%", body)          # latest attempt
        self.assertIn("passed", body)
        self.assertIn("Not attempted yet: Honey Products", body)   # user 8's attempt is not user 7's

    def test_my_quiz_needs_a_user(self):
        self.assertNotIn("Your quiz progress", entries("what is my quiz score?", user_id=None))

    def test_quiz_failure_skips_quietly(self):
        class Broken:
            def execute(self, *a, **k):
                raise RuntimeError("no table")
        result = entries("how many quizzes and articles are there?", cursor=Broken())
        self.assertNotIn("Quizzes", result)
        self.assertIn("Knowledge Base statistics", result)


class GuideTests(unittest.TestCase):
    def guide_titles(self, question, role="staff"):
        return [title for title in entries(question, role=role) if title.startswith("System guide")]

    def test_where_is_quiz(self):
        titles = self.guide_titles("where is the quiz?")
        self.assertIn("System guide: Quiz / Training", titles)

    def test_chinese_question(self):
        self.assertIn("System guide: Quiz / Training", self.guide_titles("测验在哪里？"))
        self.assertIn("System guide: Profile", self.guide_titles("怎么改密码"))

    def test_no_permission_says_who_can(self):
        body = entries("how do I add a new article?", role="staff")["System guide: Content Management"]
        self.assertIn("cannot use this", body)
        self.assertIn("Team Lead", body)

    def test_permitted_role_gets_no_warning(self):
        body = entries("how do I add a new article?", role="manager")["System guide: Content Management"]
        self.assertNotIn("cannot use this", body)

    def test_at_most_two_sections(self):
        self.assertLessEqual(len(self.guide_titles("how do I use quiz, profile, messages and notifications?")), 2)

    def test_escalation_help_for_staff(self):
        body = " ".join(entries("how do I send my question to a team lead?").values())
        self.assertIn("No, escalate to a team lead", body)


def translations(language):
    text = (FRONTEND / "i18n" / "translations.js").read_text(encoding="utf-8")
    start = text.index(f"const {language} = {{")
    end = text.index("\n};", start)
    return dict(re.findall(r"^  '([^']+)': '((?:[^'\\]|\\.)*)'", text[start:end], re.M))


class GuideDriftTests(unittest.TestCase):
    """Fails when the sidebar changes but the guide was not updated."""

    def test_every_sidebar_item_has_a_guide_section(self):
        sidebar = (FRONTEND / "components" / "Sidebar.jsx").read_text(encoding="utf-8")
        nav_keys = set(re.findall(r"<NavLink[\s\S]*?t\('(nav\.[A-Za-z]+)'\)", sidebar))
        self.assertGreaterEqual(len(nav_keys), 15)
        missing = nav_keys - {section["nav_key"] for section in sk.GUIDE_SECTIONS}
        self.assertEqual(missing, set(), "Add these sidebar items to GUIDE_SECTIONS in system_knowledge.py")

    def test_guide_labels_match_the_app_text(self):
        for language in ("en", "zh", "ms"):
            strings = translations(language)
            for section in sk.GUIDE_SECTIONS:
                if section["nav_key"]:
                    with self.subTest(language=language, key=section["nav_key"]):
                        self.assertEqual(section["labels"][language], strings[section["nav_key"]])


if __name__ == "__main__":
    unittest.main()
