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


def sync_article(cursor, article, upload_folder):
    """Bring the stored text for one article in line with its current files.

    New or changed files are extracted, unchanged ones (same SHA-256) skipped,
    rows for files no longer attached deleted. Returns the number of files
    extracted.
    """
    article_id = article["article_id"]
    cursor.execute(
        "SELECT file_url, file_hash FROM article_attachment_text WHERE article_id = %s",
        (article_id,),
    )
    existing = {row["file_url"]: row["file_hash"] for row in (cursor.fetchall() or [])}
    wanted = document_files(article)

    extracted = 0
    for url in wanted:
        path = Path(upload_folder) / _local_name(url)
        file_hash = file_sha256(path) if path.is_file() else ""
        if url in existing and existing[url] == file_hash:
            continue
        status, text = extract_text(path)
        cursor.execute("""
            INSERT INTO article_attachment_text
                (article_id, file_url, file_hash, status, text, extracted_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE file_hash = VALUES(file_hash), status = VALUES(status),
                text = VALUES(text), extracted_at = VALUES(extracted_at)
        """, (article_id, url, file_hash, status, text))
        extracted += 1

    removed = 0
    for url in existing:
        if url not in wanted:
            cursor.execute(
                "DELETE FROM article_attachment_text WHERE article_id = %s AND file_url = %s",
                (article_id, url),
            )
            removed += 1
    if extracted or removed:
        invalidate_cache()
    return extracted


_cache = {"texts": None, "loaded_at": 0.0}
_cache_lock = threading.Lock()


def invalidate_cache():
    with _cache_lock:
        _cache["texts"] = None


def load_texts(cursor, max_age=300):
    """{article_id: text} for every successfully extracted attachment.

    Kept in memory for `max_age` seconds so every chat question does not
    re-read all document text; any sync clears it at once.
    """
    with _cache_lock:
        if _cache["texts"] is not None and max_age > 0 and time.monotonic() - _cache["loaded_at"] < max_age:
            return _cache["texts"]
    cursor.execute("""
        SELECT article_id, text FROM article_attachment_text
        WHERE status = 'ok' ORDER BY article_id, attachment_text_id
    """)
    texts = {}
    for row in cursor.fetchall() or []:
        if row.get("text"):
            texts.setdefault(row["article_id"], []).append(row["text"])
    result = {article_id: " ".join(parts) for article_id, parts in texts.items()}
    with _cache_lock:
        _cache["texts"] = result
        _cache["loaded_at"] = time.monotonic()
    return result


def _default_tokens(text):
    text = str(text or "").lower()
    tokens = set(re.findall(r"[a-z0-9]+", text))
    for run in re.findall(r"[㐀-鿿]+", text):
        tokens.update(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def best_passages(text, question_tokens, limit=1500, tokenize=_default_tokens):
    """The passages that share the most words with the question, in document order, <= limit chars."""
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
        hits = len(set(question_tokens) & tokenize(passage))
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
