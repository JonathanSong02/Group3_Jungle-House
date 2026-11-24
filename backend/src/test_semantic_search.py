"""Meaning search ("看意思"): sections, Google calls, stored index, merge with
the word search, and the accuracy check's "other words" questions.
No network: Google is a fake that turns text into word-group vectors.
Run (from backend/src): python -m unittest test_semantic_search -v
"""

import re
import unittest

import numpy

import retrieval_audit
import semantic_search
import test_document_context as context_tests

# Words that mean the same go to the same place, like a real embedding.
GROUPS = [{"ice", "freezer", "cube", "cubes", "frozen"}, {"kiosk", "booth", "stall"},
          {"open", "opening", "unlock"}, {"close", "closing", "lock"}, {"cash", "money", "float"},
          {"honey", "tester", "sample"}]


def meaning(text):
    vector = numpy.zeros(semantic_search.DIMENSIONS, dtype=numpy.float32)
    for word in re.findall(r"[a-z]+", text.lower()):
        for position, group in enumerate(GROUPS):
            if word in group:
                vector[position] += 1
    vector[len(GROUPS)] = 0.05  # never all zero
    return vector


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self.payload


class FakeGoogle:
    def __init__(self, broken_models=()):
        self.calls = []
        self.broken = set(broken_models)

    def __call__(self, url, headers, json, timeout):
        model = url.rsplit("/", 1)[1].split(":")[0]
        self.calls.append((model, json))
        if model in self.broken:
            return FakeResponse({}, 404)
        texts = [item["content"]["parts"][0]["text"] for item in json["requests"]]
        return FakeResponse({"embeddings": [{"values": meaning(text).tolist()} for text in texts]})


class SectionTests(unittest.TestCase):
    def test_sections_are_exact_pieces_of_the_text(self):
        text = semantic_search.clean_text("<p>" + "Turn on the freezer. " * 80 + "</p><p>Count the float.</p>")
        chunks = semantic_search.chunk_text(text, size=200)
        self.assertGreater(len(chunks), 5)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 200)
            self.assertIn(chunk, text)

    def test_hash_changes_with_the_text(self):
        article = {"title": "A", "content": "x"}
        self.assertNotEqual(semantic_search.content_hash(article), semantic_search.content_hash(dict(article, content="y")))
        self.assertNotEqual(semantic_search.content_hash(article), semantic_search.content_hash(article, "pdf text"))


class GoogleTests(unittest.TestCase):
    def test_newest_model_with_prefixes_and_768_numbers(self):
        google = FakeGoogle()
        embedder = semantic_search.Embedder("key", post=google)
        vectors = embedder.embed(["Refill the freezer"], titles=["Ice"])
        embedder.embed(["make ice"], kind="query")
        self.assertEqual(embedder.model, "gemini-embedding-2")
        self.assertAlmostEqual(float(numpy.linalg.norm(vectors[0])), 1.0, places=5)
        document, query = google.calls[0][1]["requests"][0], google.calls[1][1]["requests"][0]
        self.assertEqual(document["content"]["parts"][0]["text"], "title: Ice | text: Refill the freezer")
        self.assertEqual(query["content"]["parts"][0]["text"], "task: search result | query: make ice")
        self.assertEqual(document["outputDimensionality"], 768)
        self.assertNotIn("taskType", document)

    def test_older_model_when_the_newest_is_unavailable(self):
        google = FakeGoogle(broken_models={"gemini-embedding-2"})
        embedder = semantic_search.Embedder("key", post=google)
        embedder.embed(["make ice"], kind="query")
        self.assertEqual(embedder.model, "gemini-embedding-001")
        self.assertEqual(google.calls[-1][1]["requests"][0]["taskType"], "RETRIEVAL_QUERY")

    def test_large_lists_go_in_batches_of_100(self):
        google = FakeGoogle()
        semantic_search.Embedder("key", post=google).embed(["ice"] * 250)
        self.assertEqual([len(json["requests"]) for _, json in google.calls], [100, 100, 50])


class FakeTable:
    """article_chunk_embedding in memory."""

    def __init__(self):
        self.rows = []
        self.commits = 0

    def cursor(self):
        table = self

        class Cursor:
            def execute(self, sql, params=()):
                if sql.strip().startswith("CREATE TABLE"):
                    self.result = []
                elif sql.startswith("SELECT article_id, MIN(content_hash)"):
                    seen = {}
                    for row in table.rows:
                        seen.setdefault(row["article_id"], {"article_id": row["article_id"],
                                                            "content_hash": row["content_hash"], "model": row["model"]})
                    self.result = list(seen.values())
                elif sql.strip().startswith("DELETE"):
                    table.rows = [row for row in table.rows if row["article_id"] != params[0]]
                elif sql.strip().startswith("INSERT"):
                    keys = ("article_id", "chunk_index", "source", "content_hash", "model", "chunk_text", "vector")
                    table.rows.append(dict(zip(keys, params)))
                elif "FROM article_chunk_embedding e" in sql:
                    self.result = sorted(table.rows, key=lambda r: (r["article_id"], r["chunk_index"]))
                else:
                    raise AssertionError(sql)

            def fetchall(self):
                return self.result

        return Cursor()

    def commit(self):
        self.commits += 1


ARTICLES = [
    {"article_id": 1, "title": "Freezer care", "category": "SOP", "content": "<p>Fill the freezer tray with water. Wait two hours for cubes.</p>"},
    {"article_id": 2, "title": "Booth morning", "category": "SOP", "content": "<p>Unlock the booth shutters at 9am.</p>"},
    {"article_id": 3, "title": "Float count", "category": "SOP", "content": "<p>Count the float in the drawer.</p>"},
]


class IndexTests(unittest.TestCase):
    def setUp(self):
        semantic_search.invalidate_index()
        semantic_search._query_cache.clear()
        self.table = FakeTable()
        self.google = FakeGoogle()
        self.embedder = semantic_search.Embedder("key", post=self.google)

    def sync(self, articles, documents=None):
        return semantic_search.sync(self.table.cursor(), self.table.commit, articles, documents or {},
                                    self.embedder, pause=0)

    def test_only_new_or_changed_articles_are_embedded(self):
        self.assertEqual(self.sync(ARTICLES), 3)
        self.assertEqual(len(self.google.calls), 1, "3 articles share one Google call")
        calls = len(self.google.calls)
        self.assertEqual(self.sync(ARTICLES), 0, "nothing changed: no Google call")
        self.assertEqual(len(self.google.calls), calls)
        changed = [dict(ARTICLES[0], content="<p>New freezer text.</p>")] + ARTICLES[1:]
        self.assertEqual(self.sync(changed), 1)
        self.assertEqual(self.sync(ARTICLES[1:]), 0)
        self.assertEqual({row["article_id"] for row in self.table.rows}, {2, 3}, "removed article dropped")

    def test_attachment_text_is_searchable_too(self):
        self.sync(ARTICLES[:1], {1: "Annual leave needs fourteen days notice."})
        self.assertEqual([row["source"] for row in self.table.rows], ["article", "document"])

    def test_search_finds_the_article_by_meaning(self):
        self.sync(ARTICLES)
        index = semantic_search.load_index(self.table.cursor(), max_age=0)
        matches = index.article_matches(semantic_search.query_vector(self.embedder, "how to make ice"))
        best = max(matches, key=lambda article_id: matches[article_id][0])
        self.assertEqual(best, 1)
        self.assertEqual(matches[1][1:], ("article", "Fill the freezer tray with water. Wait two hours for cubes."))

    def test_question_meanings_are_remembered(self):
        semantic_search.query_vector(self.embedder, "make ice")
        semantic_search.query_vector(self.embedder, "make ice")
        semantic_search.warm_queries(self.embedder, ["make ice", "open booth", "count money"])
        self.assertEqual(sum(len(json["requests"]) for _, json in self.google.calls), 3)


LONG = ("Check the stock list. " * 60)


class MergeTests(unittest.TestCase):
    """build_ai_chat_context with the meaning search's answer."""
    ARTICLES = [
        {"article_id": 1, "title": "Ice machine", "category": "SOP", "sub_category": "",
         "content": "<p>" + LONG + "Press the green button to start making cubes. " + LONG + "</p>"},
        *[{"article_id": 10 + n, "title": f"Make sure list {n}", "category": "SOP", "sub_category": "",
           "content": f"<p>Make sure the shelf {n} is tidy.</p>"} for n in range(8)],
    ]
    SECTION = "Press the green button to start making cubes."

    def test_no_meaning_search_is_word_search_as_before(self):
        text, candidates = context_tests.build(self.ARTICLES, [], "where do i get frozen stuff", semantic=None)
        self.assertNotIn(1, [c["article_id"] for c in candidates], "no shared word: not found by words")

    def test_article_found_by_meaning_and_its_section_reaches_the_ai(self):
        semantic = {1: (0.91, "article", self.SECTION), 11: (0.40, "article", "Make sure the shelf 1 is tidy.")}
        text, candidates = context_tests.build(self.ARTICLES, [], "where do i get frozen stuff", semantic=semantic)
        self.assertEqual(candidates[0]["article_id"], 1)
        self.assertIn(self.SECTION, text)

    def test_a_sure_title_match_still_comes_first(self):
        context_tests_build = context_tests.build
        semantic = {1: (0.95, "article", self.SECTION)}
        text, candidates = context_tests_build(self.ARTICLES, [], "make sure list 3", semantic=semantic,
                                               **{"limit": 3})
        self.assertIn(13, [c["article_id"] for c in candidates])


class OtherWordsQuestionTests(unittest.TestCase):
    ARTICLE = {"article_id": 7, "title": "Ice machine", "content": "<p>Press the green button to start making cubes.</p>"}

    def test_only_questions_with_a_real_quote_are_kept(self):
        reply = ('Here: [{"id": 7, "question": "how do i get ice", "quote": "Press the green button to start making cubes."},'
                 ' {"id": 7, "question": "dup", "quote": "Press the green button to start making cubes."},'
                 ' {"id": 8, "question": "unknown article", "quote": "Press the green button to start."},'
                 ' {"id": 7, "question": "changed", "quote": "Push the green switch to make ice."}]')
        items = retrieval_audit.parse_questions(reply, [self.ARTICLE])
        self.assertEqual([(i["article_id"], i["question"]) for i in items], [(7, "how do i get ice")])
        self.assertEqual(retrieval_audit.parse_questions("not json", [self.ARTICLE]), [])

    def test_prompt_asks_for_other_words_and_the_exact_sentence(self):
        prompt = retrieval_audit.question_prompt([self.ARTICLE])
        self.assertIn("DIFFERENT words", prompt)
        self.assertIn("word for word", prompt)
        self.assertIn("### id=7 | title: Ice machine", prompt)

    def test_run_compares_words_only_with_words_and_meaning(self):
        other = [{"article_id": 7, "title": "Ice machine", "question": "how do i get ice",
                  "sentence": "Press the green button to start making cubes."}]
        asked = []

        def build_context(question, preloaded, meaning):
            asked.append(meaning)
            found = meaning or question != "how do i get ice"
            return ("### Ice machine\nPress the green button to start making cubes." if found else ""), \
                [{"article_id": 7, "title": "Ice machine"}] if found else []

        report = retrieval_audit.run_audit([dict(self.ARTICLE, content="<p>Press the green button to start making "
                                                 "cubes before the shop opens.</p>")], {}, build_context,
                                           other_words=other, meaning=520)
        self.assertEqual(report["comparison"]["other"], {"total": 1, "words": 0.0, "meaning": 1.0})
        self.assertEqual(report["comparison"]["own"]["meaning"], 1.0)
        self.assertEqual((report["meaning"], report["meaningArticles"]), (True, 520))
        self.assertEqual((report["passed"], report["total"], report["misses"]), (2, 2, []))
        self.assertEqual(set(asked), {False, True})


if __name__ == "__main__":
    unittest.main()
