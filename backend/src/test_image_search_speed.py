"""search_image_retrieval: one query per kind of source (not one per image),
with the same rules for which images count. Fake database, no MySQL.
Run (from backend/src): python -m unittest test_image_search_speed -v
"""

import unittest

import db_helper
from image_index_service import source_hash


class FakeDB:
    def __init__(self, rows, articles, reviews):
        self.rows, self.articles, self.reviews = rows, articles, reviews
        self.queries = 0

    def connect(self):
        db = self

        class Cursor:
            def execute(self, sql, params=()):
                db.queries += 1
                if "FROM image_retrieval" in sql:
                    self.result = [dict(r) for r in db.rows]
                elif "FROM wiki_article" in sql:
                    self.result = [dict(a) for a in db.articles if a["article_id"] in set(params)]
                else:
                    found = sorted((r for r in db.reviews if r["escalation_id"] in set(params)),
                                   key=lambda r: -r["review_id"])
                    self.result = [{k: r[k] for k in ("escalation_id", "question", "answer", "status", "image_url")}
                                   for r in found]

            def fetchall(self):
                return self.result

            def fetchone(self):
                return self.result[0] if self.result else None

            def close(self):
                pass

        class Conn:
            def cursor(self, **kwargs):
                return Cursor()

            def close(self):
                pass

        return Conn()


def article(article_id, title, deleted=False):
    image = f"/static/uploads/articles/a{article_id}.png"
    return {"article_id": article_id, "title": title, "content": f'<p>{title}</p><img src="{image}">',
            "category": "SOP", "sub_category": "", "image_files": None, "attachment_url": None, "is_deleted": deleted}


def kb_row(item, stale=False):
    return {"image_id": item["article_id"], "source_type": "knowledge_base", "source_id": item["article_id"],
            "source_hash": "old" if stale else source_hash(item),
            "image_url": f"/static/uploads/articles/a{item['article_id']}.png", "image_type": "image/png"}


class ImageSearchTests(unittest.TestCase):
    def search(self, question, rows, articles=(), reviews=(), limit=10):
        db = FakeDB(rows, list(articles), list(reviews))
        original = db_helper.get_db_connection
        db_helper.get_db_connection = db.connect
        try:
            return db_helper.search_image_retrieval(question, limit=limit), db.queries
        finally:
            db_helper.get_db_connection = original

    def test_three_queries_however_many_images(self):
        articles = [article(i, f"ice machine cleaning {i}") for i in range(1, 41)]
        rows = [kb_row(a) for a in articles] + [
            {"image_id": 900 + e, "source_type": "approved_escalation", "source_id": e,
             "image_url": f"/e{e}.png", "image_type": "image/png"} for e in range(1, 11)]
        results, queries = self.search("ice machine cleaning 7", rows, articles)
        self.assertEqual(queries, 3)
        self.assertEqual(results[0]["article_id"], 7)

    def test_only_live_unchanged_articles_count(self):
        live, deleted, changed = article(1, "kiosk opening"), article(2, "kiosk opening", deleted=True), article(3, "kiosk opening")
        rows = [kb_row(live), kb_row(deleted), kb_row(changed, stale=True),
                {**kb_row(article(4, "kiosk opening")), "source_id": 404}]  # article no longer exists
        results, _ = self.search("kiosk opening", rows, [live, deleted, changed])
        self.assertEqual([r["article_id"] for r in results], [1])

    def test_escalation_uses_its_newest_approved_review(self):
        rows = [{"image_id": 9, "source_type": "approved_escalation", "source_id": 5,
                 "image_url": "/e5.png", "image_type": "image/png"}]
        reviews = [{"escalation_id": 5, "review_id": 1, "question": "honey tester refill", "answer": "old",
                    "status": "approved", "image_url": "/e5.png"},
                   {"escalation_id": 5, "review_id": 2, "question": "honey tester refill", "answer": "Refill to the line.",
                    "status": "approved", "image_url": "/e5.png"}]
        best, _ = self.search("honey tester refill", rows, reviews=reviews, limit=1)
        self.assertEqual(best["answer"], "Refill to the line.")
        reviews[1]["status"] = "pending"  # newest review not approved: the image does not count
        self.assertIsNone(self.search("honey tester refill", rows, reviews=reviews, limit=1)[0])


if __name__ == "__main__":
    unittest.main()
