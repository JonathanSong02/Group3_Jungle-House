"""Retrieval audit: can the AI actually SEE the answer?

For every step of every article in backend/data/cleaned_knowledge.csv (the
459-step SOP set), a question is built from that step's own words, the way
staff type, and the real build_ai_chat_context must put the answer line into
the text the AI reads. Also pins real questions that once failed.

This guards the class of bug where search picked the wrong article or cut the
answer line off (e.g. "how many cabinet i need to open when opening" lost
"Unlock all cabinet doors from B, C, E, F, K and L"). No database, no AI.
Run: python -m unittest discover -s backend/src -p test_retrieval_audit.py
"""

import csv
import os
import re
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("FLASK_SECRET_KEY", "dummy-test-only-key-not-a-secret-0123456789")
os.environ.setdefault("NOTION_AUTO_SYNC_ENABLED", "false")
os.environ.setdefault("DOCUMENT_TEXT_BACKFILL", "false")
os.environ.setdefault("IMAGE_INDEX_WORKER_ENABLED", "false")
import app  # noqa: E402

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "cleaned_knowledge.csv"
ROWS = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))

_by_title = defaultdict(list)
for _row in ROWS:
    _by_title[_row["title"]].append(_row)
ARTICLES = []
for _index, (_title, _steps) in enumerate(_by_title.items(), 1):
    _steps.sort(key=lambda r: float(r.get("step_order") or 0))
    ARTICLES.append({"article_id": _index, "title": _title, "category": _steps[0]["category"],
                     "sub_category": _steps[0].get("section") or "",
                     "content": "".join(f"<p>{r['content']}</p>" for r in _steps if r["content"].strip())})

STOP = set("""a an the and or of to in on at for with by from is are be it this that these those you your
we our they their them as if then than so not no do does did can will should must have has had into out
up down over under all any each every some more most other such only own same too very just also there
here when where what which who how why after before during while again once both few near next first last
per via""".split())


def words(text):
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOP]


DOC_FREQ = Counter()
for _row in ROWS:
    DOC_FREQ.update(set(words(_row["content"])))
ROW_WORDS = [(r, set(words(r["content"]))) for r in ROWS]


def snippet(row):
    return re.sub(r"\s+", " ", row["content"]).strip()[:60].lower()


def visible(row, context):
    """The step, or the same step in another article, reaches the AI."""
    context = context.lower()
    if snippet(row) in context:
        return True
    mine = set(words(row["content"]))
    for other, other_words in ROW_WORDS:
        if other is not row and mine and other_words and \
                len(mine & other_words) / len(mine | other_words) >= 0.7 and snippet(other) in context:
            return True
    return False


class _Cursor:
    def __init__(self):
        self.rows = []

    def execute(self, sql, params=()):
        self.rows = ARTICLES if "FROM wiki_article" in sql else []

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class _Conn:
    def cursor(self, **kwargs):
        return _Cursor()

    def close(self):
        pass


def context_for(question):
    with patch.object(app, "get_db_connection", lambda: _Conn()):
        text, _ = app.build_ai_chat_context(question, search_question=question)
    return text


class RealQuestionsTests(unittest.TestCase):
    """Questions staff really asked that once failed."""
    CABINET = "unlock all cabinet doors from b, c, e, f, k and l"

    def test_how_many_cabinets_when_opening(self):
        self.assertIn(self.CABINET, context_for("how many cabinet i need to open when opening").lower())

    def test_after_opening_the_cabinets(self):
        self.assertIn(self.CABINET, context_for("after open cabinet what should i do").lower())

    def test_aeon_opening_reaches_the_aeon_list(self):
        self.assertIn("### aeon roadshow opening list", context_for("aeon opening").lower())


class CoverageTests(unittest.TestCase):
    """Every SOP step, asked with its own key words, must be visible to the AI."""

    @classmethod
    def setUpClass(cls):
        cls.results = {"keywords": [], "keywords+title": []}
        for row in ROWS:
            row_words = words(row["content"])
            if len(row_words) < 3:
                continue
            keywords = sorted(set(row_words), key=lambda w: (DOC_FREQ[w], w))[:4]
            title_word = next((w for w in words(row["title"]) if w not in keywords), "")
            for label, question in (("keywords", " ".join(keywords)),
                                    ("keywords+title", " ".join(keywords + [title_word]).strip())):
                cls.results[label].append(visible(row, context_for(question)))

    def rate(self, label):
        items = self.results[label]
        return sum(items) / len(items)

    def test_questions_with_a_topic_word(self):
        # Measured 99% (433/436) on 2026-11-24.
        self.assertGreaterEqual(self.rate("keywords+title"), 0.97)

    def test_questions_with_only_step_words(self):
        # Measured 95% (414/436) on 2026-11-24; the rest are steps repeated in
        # several lists or written in very generic words.
        self.assertGreaterEqual(self.rate("keywords"), 0.92)


class LiveCheckTests(unittest.TestCase):
    """The manager's "check search accuracy" button, on these 48 articles."""

    def test_preloaded_data_gives_the_same_context_as_the_database(self):
        for question in ("aeon opening", "how many cabinet i need to open when opening"):
            with patch.object(app, "get_db_connection", lambda: _Conn()):
                from_db = app.build_ai_chat_context(question, search_question=question)
            preloaded = app.build_ai_chat_context(question, search_question=question, preloaded=(ARTICLES, {}))
            self.assertEqual(preloaded, from_db)

    def test_live_check_on_the_sop_articles(self):
        import retrieval_audit
        report = retrieval_audit.run_audit(ARTICLES, {}, app._audit_build_context)
        self.assertGreater(report["total"], 100)
        self.assertEqual(report["passed"] + report["wrongArticle"] + report["lineCut"], report["total"])
        # Measured 2026-11-24, see the check's own report in AI Model Settings.
        self.assertGreaterEqual(report["rate"], 0.95)


if __name__ == "__main__":
    unittest.main()
