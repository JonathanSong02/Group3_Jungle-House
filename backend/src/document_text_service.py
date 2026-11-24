"""Text of PDF and Word (.docx) article attachments, for the AI chat.

The text is extracted once, on the server, with free libraries (pypdf,
python-docx) -- no AI call -- and stored in `article_attachment_text`, one row
per (article, file). The AI chat then reads only the passages that match the
question, inside its existing context size limit, so the cost per question
does not change.

Nothing here changes how articles, uploads or attachments look or behave.
A missing, corrupt, scanned (no text) or unsupported file is recorded with a
status and skipped; it never raises to the caller.
"""

import hashlib
import json
import re
import threading
import time
from pathlib import Path

ARTICLE_URL_PREFIX = "/static/uploads/articles/"
SUPPORTED_EXTENSIONS = {".pdf": "pdf", ".docx": "docx"}
MAX_PDF_PAGES = 300
MAX_TEXT_CHARS = 300_000
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_CONTENT_LINK = re.compile(r"(/static/uploads/articles/[A-Za-z0-9._-]+\.(?:pdf|docx))(?![A-Za-z0-9._-])", re.IGNORECASE)


def _normalise(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def extract_text(path, max_chars=MAX_TEXT_CHARS):
    """Return (status, text). Status: ok, empty, unsupported, missing, error."""
    path = Path(path)
    kind = SUPPORTED_EXTENSIONS.get(path.suffix.lower())
    if not kind:
        return "unsupported", ""
    if not path.is_file():
        return "missing", ""
    try:
        if kind == "pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            parts = []
            for page in reader.pages[:MAX_PDF_PAGES]:
                parts.append(page.extract_text() or "")
                if sum(len(part) for part in parts) > max_chars:
                    break
        else:
            import docx
            document = docx.Document(str(path))
            parts = [paragraph.text for paragraph in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    for cell in row.cells:
                        parts.append(cell.text)
        text = _normalise(" ".join(parts))[:max_chars]
    except Exception:
        return "error", ""
    return ("ok", text) if text else ("empty", "")


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _local_name(url):
    """Filename of an uploaded article file, or None if the URL is not one."""
    if not isinstance(url, str) or not url.startswith(ARTICLE_URL_PREFIX):
        return None
    name = url[len(ARTICLE_URL_PREFIX):]
    if not _SAFE_NAME.fullmatch(name) or name.startswith("."):
        return None
    return name


def document_files(article):
    """URLs of the article's uploaded .pdf / .docx files, in order, no duplicates."""
    urls = []
    raw = article.get("image_files")
    if raw:
        try:
            items = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            items = []
        if isinstance(items, list):
            urls = [item.get("url") for item in items if isinstance(item, dict)]
    elif article.get("attachment_url"):
        urls = [article.get("attachment_url")]
    # Files linked inside the article text (e.g. Notion-synced attachments,
    # which are linked with an absolute URL).
    urls = list(urls) + [match.group(1) for match in _CONTENT_LINK.finditer(str(article.get("content") or ""))]

    result = []
    for url in urls:
        name = _local_name(url)
        if name and Path(name).suffix.lower() in SUPPORTED_EXTENSIONS and url not in result:
            result.append(url)
    return result


def ensure_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS article_attachment_text (
            attachment_text_id INT NOT NULL AUTO_INCREMENT,
            article_id INT NOT NULL,
            file_url VARCHAR(512) NOT NULL,
            file_hash CHAR(64) NOT NULL DEFAULT '',
            status VARCHAR(20) NOT NULL,
            text MEDIUMTEXT,
            extracted_at DATETIME NOT NULL,
            PRIMARY KEY (attachment_text_id),
            UNIQUE KEY uq_article_attachment_text_file (article_id, file_url),
            CONSTRAINT fk_article_attachment_text_article FOREIGN KEY (article_id)
                REFERENCES wiki_article (article_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    # Added after the first release (migration 0006): a one-time AI summary.
    cursor.execute("SHOW COLUMNS FROM article_attachment_text LIKE 'summary'")
    if not cursor.fetchall():
        cursor.execute("ALTER TABLE article_attachment_text ADD COLUMN summary TEXT")


MAX_SUMMARY_INPUT_CHARS = 40_000
MAX_SUMMARY_CHARS = 1500


def _safe_summary(summarize, text):
    """Run the summarizer once; any failure or empty result gives None."""
    if not summarize or not text:
        return None
    try:
        summary = summarize(text[:MAX_SUMMARY_INPUT_CHARS])
    except Exception:
        return None
    summary = _normalise(summary)[:MAX_SUMMARY_CHARS]
    return summary or None


def sync_article(cursor, article, upload_folder, summarize=None):
    """Bring the stored text for one article in line with its current files.

    New or changed files are extracted (and summarised once when
    `summarize` is given), unchanged ones (same SHA-256) skipped -- except
    that a readable file still without a summary gets one -- and rows for
    files no longer attached deleted. Returns the number of files extracted.
    """
    article_id = article["article_id"]
    cursor.execute("""
        SELECT file_url, file_hash, status, (summary IS NULL) AS needs_summary
        FROM article_attachment_text WHERE article_id = %s
    """, (article_id,))
    existing = {row["file_url"]: row for row in (cursor.fetchall() or [])}
    wanted = document_files(article)

    extracted = 0
    summarised = 0
    for url in wanted:
        path = Path(upload_folder) / _local_name(url)
        file_hash = file_sha256(path) if path.is_file() else ""
        row = existing.get(url)
        if row and row["file_hash"] == file_hash:
            if summarize and row.get("status") == "ok" and row.get("needs_summary"):
                cursor.execute(
                    "SELECT text FROM article_attachment_text WHERE article_id = %s AND file_url = %s",
                    (article_id, url),
                )
                stored = (cursor.fetchall() or [{}])[0].get("text")
                summary = _safe_summary(summarize, stored)
                if summary:
                    cursor.execute(
                        "UPDATE article_attachment_text SET summary = %s WHERE article_id = %s AND file_url = %s",
                        (summary, article_id, url),
                    )
                    summarised += 1
            continue
        status, text = extract_text(path)
        summary = _safe_summary(summarize, text) if status == "ok" else None
        cursor.execute("""
            INSERT INTO article_attachment_text
                (article_id, file_url, file_hash, status, text, extracted_at, summary)
            VALUES (%s, %s, %s, %s, %s, NOW(), %s)
            ON DUPLICATE KEY UPDATE file_hash = VALUES(file_hash), status = VALUES(status),
                text = VALUES(text), extracted_at = VALUES(extracted_at), summary = VALUES(summary)
        """, (article_id, url, file_hash, status, text, summary))
        extracted += 1

    removed = 0
    for url in existing:
        if url not in wanted:
            cursor.execute(
                "DELETE FROM article_attachment_text WHERE article_id = %s AND file_url = %s",
                (article_id, url),
            )
            removed += 1
    if extracted or removed or summarised:
        invalidate_cache()
    return extracted


_cache = {"documents": None, "loaded_at": 0.0}
_cache_lock = threading.Lock()
_UPLOAD_PREFIX = re.compile(r"^\d+_(?:[0-9a-f]{6}_)?")


def invalidate_cache():
    with _cache_lock:
        _cache["documents"] = None


def display_name(url):
    """'1700000000000_a1b2c3_Lab_10_Manual.pdf' -> 'Lab_10_Manual.pdf'."""
    name = str(url or "").rsplit("/", 1)[-1]
    return _UPLOAD_PREFIX.sub("", name) or name


def load_documents(cursor, max_age=300):
    """{article_id: {"text": joined readable text, "files": [{url, name, status, summary}]}}.

    Missing and unsupported files are left out. Kept in memory for
    `max_age` seconds so every chat question does not re-read all document
    text; any sync clears it at once.
    """
    with _cache_lock:
        if _cache["documents"] is not None and max_age > 0 and time.monotonic() - _cache["loaded_at"] < max_age:
            return _cache["documents"]
    cursor.execute("""
        SELECT article_id, file_url, status, text, summary FROM article_attachment_text
        WHERE status IN ('ok', 'empty', 'error') ORDER BY article_id, attachment_text_id
    """)
    documents = {}
    for row in cursor.fetchall() or []:
        entry = documents.setdefault(row["article_id"], {"texts": [], "files": []})
        if row.get("file_url"):
            entry["files"].append({"url": row["file_url"], "name": display_name(row["file_url"]),
                                   "status": row.get("status") or "ok", "summary": row.get("summary")})
        if (row.get("status") or "ok") == "ok" and row.get("text"):
            entry["texts"].append(row["text"])
    result = {article_id: {"text": " ".join(entry["texts"]), "files": entry["files"]}
              for article_id, entry in documents.items()}
    with _cache_lock:
        _cache["documents"] = result
        _cache["loaded_at"] = time.monotonic()
    return result


def load_texts(cursor, max_age=300):
    """{article_id: text} for every successfully extracted attachment."""
    return {article_id: entry["text"]
            for article_id, entry in load_documents(cursor, max_age).items() if entry["text"]}


def _default_tokens(text):
    text = str(text or "").lower()
    tokens = set(re.findall(r"[a-z0-9]+", text))
    for run in re.findall(r"[㐀-鿿]+", text):
        tokens.update(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def best_passages(text, question_tokens, limit=1500, tokenize=_default_tokens, weights=None):
    """The passages that share the most words with the question, in document order, <= limit chars.

    `weights` (word -> weight) lets rare words count more; without it every
    shared word counts 1.
    """
    if not text or not question_tokens or limit <= 0:
        return ""
    size = min(600, limit)
    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
    passages, current = [], ""
    for sentence in sentences:
        while len(sentence) > size:
            if current:
                passages.append(current)
                current = ""
            passages.append(sentence[:size])
            sentence = sentence[size:]
        if current and len(current) + 1 + len(sentence) > size:
            passages.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        passages.append(current)

    scored = []
    for position, passage in enumerate(passages):
        shared = set(question_tokens) & tokenize(passage)
        hits = sum((weights or {}).get(word, 1.0) for word in shared)
        if hits:
            scored.append((hits, position, passage))
    scored.sort(key=lambda item: (-item[0], item[1]))

    chosen, total = [], 0
    for _, position, passage in scored:
        extra = len(passage) + (3 if chosen else 0)
        if total + extra > limit:
            continue
        chosen.append((position, passage))
        total += extra
    return " … ".join(passage for _, passage in sorted(chosen))
