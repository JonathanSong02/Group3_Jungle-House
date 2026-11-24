"""Meaning-based article search ("看意思") with Gemini text embeddings.

Every live article (and the readable text of its PDF / Word attachments) is cut
into short sections; Google turns each section into a list of numbers that
describes its meaning (an "embedding"). They are stored in
`article_chunk_embedding` and kept in memory. A question is turned into
numbers the same way, and the sections closest in meaning are found, so
"how to make ice" can reach "Ice machine operation" even with no shared word.

Used next to the word search, never instead of it. It only works when the AI
provider in AI Model Settings is Gemini (same key); otherwise, or on any
error or timeout, the chat search is exactly the word search as before.
Sections are re-embedded only when an article's text changes (hash check).
Emergency off switch: SEMANTIC_SEARCH_ENABLED=0.
"""

import hashlib
import os
import re
import threading
import time

EMBED_MODELS = ("gemini-embedding-2", "gemini-embedding-001")  # newest first
DIMENSIONS = 768
CHUNK_CHARS = 900
MAX_DOCUMENT_CHUNKS = 40
BATCH_SIZE = 100
QUERY_TIMEOUT = 4
API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
_SENTENCE_END = re.compile(r"(?<=[.!?。！？])\s+")


def enabled():
    return os.environ.get("SEMANTIC_SEARCH_ENABLED", "1").strip().lower() not in ("0", "false", "off", "no")


def clean_text(text):
    """Same plain text the chat search builds from article HTML."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(text or ""))).strip()


def chunk_text(text, size=CHUNK_CHARS):
    """Whole sentences grouped into sections of at most `size` characters.

    Sections are exact pieces of `text` (joined by single spaces, which is
    how clean_text already spaces it), so a section can be found in it.
    """
    chunks, current = [], ""
    for sentence in _SENTENCE_END.split(text or ""):
        while len(sentence) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:size])
            sentence = sentence[size:]
        if current and len(current) + 1 + len(sentence) > size:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk.strip()]


def article_chunks(article, document_text=""):
    """[(source, text)] for one article: its own text, then its attachments' text."""
    sections = [("article", chunk) for chunk in chunk_text(clean_text(article.get("content")))]
    if document_text:
        sections += [("document", chunk) for chunk in chunk_text(document_text)[:MAX_DOCUMENT_CHUNKS]]
    return sections


def content_hash(article, document_text=""):
    text = "\x1f".join([str(article.get("title") or ""), str(article.get("category") or ""),
                        str(article.get("content") or ""), document_text or ""])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- Google API

class Embedder:
    """Calls Gemini's batchEmbedContents. Tries the newest model first and
    remembers the first one that works."""

    def __init__(self, api_key, post=None):
        import requests
        self.api_key = api_key
        self.post = post or requests.post
        self.model = None

    def _request_text(self, model, text, kind, title=""):
        if model == "gemini-embedding-2":  # takes the task as a text prefix
            return (f"task: search result | query: {text}" if kind == "query"
                    else f"title: {title or 'none'} | text: {text}")
        return text

    def _call(self, model, texts, kind, titles, timeout):
        requests_body = []
        for index, text in enumerate(texts):
            item = {"model": f"models/{model}",
                    "content": {"parts": [{"text": self._request_text(model, text, kind, titles[index])}]},
                    "outputDimensionality": DIMENSIONS}
            if model != "gemini-embedding-2":
                item["taskType"] = "RETRIEVAL_QUERY" if kind == "query" else "RETRIEVAL_DOCUMENT"
            requests_body.append(item)
        response = self.post(f"{API_ROOT}/{model}:batchEmbedContents",
                             headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                             json={"requests": requests_body}, timeout=timeout)
        response.raise_for_status()
        vectors = [item["values"] for item in response.json()["embeddings"]]
        if len(vectors) != len(texts):
            raise ValueError("embedding count mismatch")
        return vectors

    def embed(self, texts, kind="document", titles=None, timeout=60):
        """Unit-length vectors (numpy float32 rows), one per text."""
        import numpy
        texts = list(texts)
        titles = list(titles or [""] * len(texts))
        if not texts:
            return numpy.zeros((0, DIMENSIONS), dtype=numpy.float32)
        # The known working model first; the others if it stops working.
        models = list(dict.fromkeys([model for model in (self.model, *EMBED_MODELS) if model]))
        error = None
        for model in models:
            try:
                rows = []
                for start in range(0, len(texts), BATCH_SIZE):
                    rows += self._call(model, texts[start:start + BATCH_SIZE], kind,
                                       titles[start:start + BATCH_SIZE], timeout)
                self.model = model
                return normalise(numpy.asarray(rows, dtype=numpy.float32))
            except Exception as failure:  # try the next model
                error = failure
        raise error


def normalise(matrix):
    import numpy
    norms = numpy.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


# ------------------------------------------------------------- storage/index

def ensure_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS article_chunk_embedding (
            chunk_embedding_id INT NOT NULL AUTO_INCREMENT,
            article_id INT NOT NULL,
            chunk_index INT NOT NULL,
            source VARCHAR(20) NOT NULL,
            content_hash CHAR(64) NOT NULL,
            model VARCHAR(64) NOT NULL,
            chunk_text TEXT NOT NULL,
            vector MEDIUMBLOB NOT NULL,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (chunk_embedding_id),
            UNIQUE KEY uq_article_chunk_embedding (article_id, chunk_index),
            CONSTRAINT fk_article_chunk_embedding_article FOREIGN KEY (article_id)
                REFERENCES wiki_article (article_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


class Index:
    """All stored sections in memory: one matrix, searched in a few milliseconds."""

    def __init__(self, model, entries, matrix):
        self.model = model
        self.entries = entries  # [(article_id, source, text)]
        self.matrix = matrix

    def article_matches(self, query_vector, top_sections=60):
        """{article_id: (similarity, source, section_text)} for the best sections."""
        import numpy
        if self.matrix is None or not len(self.entries):
            return {}
        similarities = self.matrix @ query_vector
        best = numpy.argsort(-similarities)[:top_sections]
        matches = {}
        for position in best:
            article_id, source, text = self.entries[position]
            if article_id not in matches:
                matches[article_id] = (float(similarities[position]), source, text)
        return matches


_index = {"value": None, "loaded_at": 0.0}
_index_lock = threading.Lock()


def invalidate_index():
    with _index_lock:
        _index["value"] = None


def cached_index():
    """The index already in memory (refreshed by the background sync), or None."""
    with _index_lock:
        return _index["value"]


def load_index(cursor, max_age=600):
    import numpy
    with _index_lock:
        if _index["value"] is not None and time.monotonic() - _index["loaded_at"] < max_age:
            return _index["value"]
    cursor.execute("""
        SELECT e.article_id, e.source, e.chunk_text, e.vector, e.model
        FROM article_chunk_embedding e JOIN wiki_article a ON a.article_id = e.article_id
        WHERE COALESCE(a.is_deleted, 0) = 0
        ORDER BY e.article_id, e.chunk_index
    """)
    rows = cursor.fetchall() or []
    models = {row["model"] for row in rows}
    if len(models) > 1:  # a model change is half done: use the newest only
        newest = next(model for model in EMBED_MODELS if model in models)
        rows = [row for row in rows if row["model"] == newest]
    entries = [(row["article_id"], row["source"], row["chunk_text"]) for row in rows]
    matrix = (numpy.vstack([numpy.frombuffer(bytes(row["vector"]), dtype=numpy.float32) for row in rows])
              if rows else None)
    index = Index(rows[0]["model"] if rows else None, entries, matrix)
    with _index_lock:
        _index["value"] = index
        _index["loaded_at"] = time.monotonic()
    return index


def sync(cursor, commit, articles, documents, embedder, pause=0.3):
    """Embed new or changed articles, drop removed ones. Returns sections embedded.

    `documents` = {article_id: attachment text}. Each article is committed on
    its own, so a stop half way keeps what was done.
    """
    import numpy
    ensure_table(cursor)
    cursor.execute("SELECT article_id, MIN(content_hash) AS content_hash, MIN(model) AS model "
                   "FROM article_chunk_embedding GROUP BY article_id")
    stored = {row["article_id"]: row for row in cursor.fetchall() or []}
    live_ids = {article["article_id"] for article in articles}
    pending = []  # (article, digest, sections) that need new embeddings
    for article in articles:
        document_text = documents.get(article["article_id"]) or ""
        digest = content_hash(article, document_text)
        row = stored.get(article["article_id"])
        if row and row["content_hash"] == digest and (embedder.model is None or row["model"] == embedder.model):
            continue
        sections = article_chunks(article, document_text)
        if sections:
            pending.append((article, digest, sections))

    # Several articles share one Google call (up to BATCH_SIZE sections), so
    # the first full sync of ~660 articles takes a few dozen calls, not 660.
    groups, current, size = [], [], 0
    for item in pending:
        if current and size + len(item[2]) > BATCH_SIZE:
            groups.append(current)
            current, size = [], 0
        current.append(item)
        size += len(item[2])
    if current:
        groups.append(current)

    embedded = 0
    for group in groups:
        texts = [text for _, _, sections in group for _, text in sections]
        titles = [article.get("title") or "" for article, _, sections in group for _ in sections]
        vectors = iter(embedder.embed(texts, titles=titles))
        for article, digest, sections in group:
            cursor.execute("DELETE FROM article_chunk_embedding WHERE article_id = %s", (article["article_id"],))
            for position, (source, text) in enumerate(sections):
                cursor.execute("""
                    INSERT INTO article_chunk_embedding
                        (article_id, chunk_index, source, content_hash, model, chunk_text, vector, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                """, (article["article_id"], position, source, digest, embedder.model, text,
                      numpy.asarray(next(vectors), dtype=numpy.float32).tobytes()))
            embedded += len(sections)
        commit()
        if pause:
            time.sleep(pause)
    for article_id in set(stored) - live_ids:
        cursor.execute("DELETE FROM article_chunk_embedding WHERE article_id = %s", (article_id,))
        commit()
    if embedded or set(stored) - live_ids:
        invalidate_index()
    return embedded


# ------------------------------------------------------------------ queries

_query_cache = {}
_QUERY_CACHE_SIZE = 2000


def query_vector(embedder, question):
    key = (embedder.model, question)
    if key in _query_cache:
        return _query_cache[key]
    vector = embedder.embed([question], kind="query", timeout=QUERY_TIMEOUT)[0]
    if len(_query_cache) >= _QUERY_CACHE_SIZE:
        _query_cache.clear()
    _query_cache[(embedder.model, question)] = vector
    return vector


def warm_queries(embedder, questions):
    """Embed many questions in a few batch calls (the accuracy check)."""
    missing = [q for q in dict.fromkeys(questions) if (embedder.model, q) not in _query_cache]
    if missing:
        vectors = embedder.embed(missing, kind="query", timeout=60)
        for question, vector in zip(missing, vectors):
            _query_cache[(embedder.model, question)] = vector
