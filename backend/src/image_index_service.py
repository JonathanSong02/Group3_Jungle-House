"""Published KB image index. Cheap metadata reconciliation on publication;
bounded background embedding batches, never model inference in a DB transaction.
"""
import hashlib
import json
import logging
import os
import re
import threading
from functools import lru_cache
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from db_helper import get_db_connection
from image_embedding_helper import MODEL_VERSION, create_image_embedding, image_sha256, decode_image

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic", ".heif"}
TRUSTED_HOSTS = {"jhgroup3.com", "www.jhgroup3.com", "ai-powered-wiki-training-assistant.vercel.app",
                 "group3jungle-house-production.up.railway.app", "localhost", "127.0.0.1"}
log = logging.getLogger(__name__)
_wake = threading.Event()
_worker_lock = threading.Lock()
_worker = None


def local_image_url(value):
    parsed = urlsplit(unescape(str(value or "").strip()))
    if parsed.scheme and (parsed.scheme not in {"http", "https"} or parsed.hostname not in TRUSTED_HOSTS):
        return None
    path = unquote(parsed.path).replace("\\", "/")
    if path.startswith(("/uploads/articles/", "uploads/articles/")):
        path = "/static/" + path.lstrip("/")
    if path.startswith(("sop_images/", "product_images/", "notice_images/")):
        path = "/static/" + path
    if path.startswith("static/"):
        path = "/" + path
    if not path.startswith(("/static/uploads/articles/", "/static/sop_images/", "/static/product_images/", "/static/notice_images/")):
        return None
    if any(part in {"", ".", ".."} for part in path.lstrip("/").split("/")):
        return None
    if Path(path).suffix.lower() not in IMAGE_SUFFIXES:
        return None
    return path


def local_image_path(url):
    canonical = local_image_url(url)
    if not canonical:
        return None
    root = STATIC_DIR.resolve()
    path = (root / canonical[len("/static/"):]).resolve()
    return path if path.is_relative_to(root) and path.is_file() else None


def approved_image_path(url):
    """For a separately permission-checked approved escalation, permit its local chat file."""
    path = urlsplit(str(url or "")).path
    if path.startswith("/static/uploads/chat/"):
        name = path[len("/static/uploads/chat/"):]
        if not name or "/" in name or "\\" in name or name in {".", ".."}:
            return None
        root = (STATIC_DIR / "uploads" / "chat").resolve()
        file = (root / name).resolve()
        return file if file.parent == root and file.is_file() else None
    return local_image_path(url)


ELIGIBLE_SOURCES = """(
    (r.source_type = 'knowledge_base' AND EXISTS
      (SELECT 1 FROM wiki_article a WHERE a.article_id = r.source_id AND COALESCE(a.is_deleted, 0) = 0))
    OR (r.source_type = 'approved_escalation' AND EXISTS
      (SELECT 1 FROM escalation e JOIN review_queue q ON q.escalation_id = e.escalation_id
       WHERE e.escalation_id = r.source_id AND COALESCE(e.is_deleted, 0) = 0
       AND e.image_url = r.image_url AND q.status IN ('approved', 'published')
       AND q.review_id = (SELECT MAX(q2.review_id) FROM review_queue q2 WHERE q2.escalation_id = e.escalation_id)))
)"""


class _Images(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "img":
            self.urls.append(dict(attrs).get("src", ""))


def article_images(article):
    urls = [article.get("attachment_url")]
    files = article.get("image_files") or []
    try:
        files = json.loads(files) if isinstance(files, str) else files
    except ValueError:
        files = re.split(r"[|\n]", files)
    if isinstance(files, str):
        files = [files]
    if isinstance(files, dict):
        files = [files]
    if isinstance(files, list):
        urls.extend((item.get("url") or item.get("path") or item.get("image_url")) if isinstance(item, dict) else item for item in files)
    parser = _Images()
    parser.feed(str(article.get("content") or ""))
    urls.extend(parser.urls)
    return sorted({url for value in urls if (url := local_image_url(value))})


def published(article):
    return bool(article and not article.get("is_deleted")
                and article.get("approval_status", "approved") == "approved"
                and article.get("status", "published") == "published")


def source_hash(article):
    return hashlib.sha256(json.dumps({k: article.get(k) for k in
        ("title", "content", "category", "sub_category", "image_files", "attachment_url", "is_deleted")},
        sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def sync_article(cursor, article_id):
    """Use caller's publication transaction. No model/file writes or remote calls."""
    cursor.execute("SELECT * FROM wiki_article WHERE article_id = %s FOR UPDATE", (article_id,))
    article = cursor.fetchone()
    if not published(article):
        cursor.execute("DELETE FROM image_retrieval WHERE source_type = 'knowledge_base' AND source_id = %s", (article_id,))
        return
    urls = article_images(article)
    fingerprint = source_hash(article)
    cursor.execute("SELECT * FROM image_retrieval WHERE source_type = 'knowledge_base' AND source_id = %s", (article_id,))
    existing = {}
    for row in cursor.fetchall():
        url = local_image_url(row.get("image_url"))
        if url not in urls or url in existing:
            cursor.execute("DELETE FROM image_retrieval WHERE image_id = %s", (row["image_id"],))
        else:
            existing[url] = row
    for url in urls:
        row = existing.get(url)
        if row:
            cursor.execute("""UPDATE image_retrieval SET source_hash = %s, question = %s,
                answer = NULL, image_caption = %s, approval_status = 'approved', visual_match_enabled = 1,
                image_embedding = CASE WHEN embedding_model = %s THEN image_embedding ELSE NULL END
                WHERE image_id = %s""", (fingerprint, article.get("title"), article.get("title"), MODEL_VERSION, row["image_id"]))
        else:
            cursor.execute("""INSERT INTO image_retrieval
                (source_type, source_id, question, image_url, image_type, image_caption, source_hash,
                 approval_status, visual_match_enabled)
                VALUES ('knowledge_base', %s, %s, %s, 'image', %s, %s, 'approved', 1)""",
                (article_id, article.get("title"), url, article.get("title"), fingerprint))
    _wake.set()


def sync_articles(cursor, article_ids):
    for article_id in sorted(set(article_ids)):
        sync_article(cursor, article_id)


def process_pending(batch_size=16):
    """Snapshot work, close DB, encode, then conditionally persist against source revision."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""SELECT r.* FROM image_retrieval r
            WHERE """ + ELIGIBLE_SOURCES + """
            AND r.approval_status = 'approved' AND r.visual_match_enabled = 1
            AND (r.image_embedding IS NULL OR COALESCE(r.embedding_model, '') <> %s)
            ORDER BY COALESCE(r.indexed_at, '1970-01-01'), r.image_id LIMIT %s""", (MODEL_VERSION, batch_size))
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    success = 0
    for row in rows:
        path = approved_image_path(row["image_url"]) if row["source_type"] == "approved_escalation" else local_image_path(row["image_url"])
        embedding = create_image_embedding(path) if path else None
        digest = image_sha256(path) if path and embedding else None
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""UPDATE image_retrieval SET image_embedding = %s, image_hash = %s,
                embedding_model = %s, indexed_at = UTC_TIMESTAMP(), index_error = %s
                WHERE image_id = %s AND (source_hash = %s OR (source_hash IS NULL AND %s IS NULL)) AND image_url = %s""",
                (embedding, digest, MODEL_VERSION, None if embedding else "encoding_unavailable",
                 row["image_id"], row["source_hash"], row["source_hash"], row["image_url"]))
            conn.commit()
            success += bool(embedding and cursor.rowcount)
        finally:
            cursor.close()
            conn.close()
    return {"processed": len(rows), "indexed": success}


def start_worker():
    global _worker
    if os.getenv("IMAGE_INDEX_WORKER_ENABLED", "true").lower() not in {"true", "1"} or not os.getenv("MYSQL_HOST"):
        return
    def run():
        while True:
            _wake.wait(60)
            _wake.clear()
            try:
                result = process_pending()
                if result["indexed"] and result["processed"] == 16:
                    _wake.set()
            except Exception as error:
                log.warning("Image index worker unavailable (%s); retry in 60s", type(error).__name__)
    with _worker_lock:
        if not _worker or not _worker.is_alive():
            _worker = threading.Thread(target=run, name="kb-image-index", daemon=True)
            _worker.start()


def _candidate_pages(digest=None):
    last_id = 0
    while True:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            sql = """SELECT r.image_id, r.source_type, r.source_id, r.image_url, r.source_hash,
                r.image_hash, r.image_embedding FROM image_retrieval r WHERE """ + ELIGIBLE_SOURCES + """
                AND r.approval_status = 'approved' AND r.visual_match_enabled = 1
                AND r.embedding_model = %s AND r.image_embedding IS NOT NULL AND r.image_id > %s"""
            params = [MODEL_VERSION, last_id]
            if digest:
                sql += " AND r.image_hash = %s"
                params.append(digest)
            cursor.execute(sql + " ORDER BY r.image_id LIMIT 512", tuple(params))
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
        if not rows:
            break
        yield rows
        last_id = rows[-1]["image_id"]
        if len(rows) < 512:
            break


@lru_cache(maxsize=512)
def _copy_signature(filename, modified_ns, size):
    """Small RGB signature; file revision keys invalidate edited/replaced images."""
    from PIL import Image
    image = decode_image(filename)
    ratio = image.width / image.height
    pixels = image.resize((96, 96), Image.Resampling.LANCZOS).tobytes()
    return image_sha256(filename), ratio, pixels


def copy_signature(path):
    info = path.stat()
    return _copy_signature(str(path), info.st_mtime_ns, info.st_size)


def _exact_kb_candidates(digest, query_path):
    """Read current local article images even when legacy/vector metadata is absent."""
    last_id = 0
    query_signature = copy_signature(query_path)
    while True:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""SELECT * FROM wiki_article WHERE COALESCE(is_deleted, 0) = 0
                AND article_id > %s ORDER BY article_id LIMIT 512""", (last_id,))
            articles = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
        if not articles:
            break
        # File reads happen after releasing the DB connection. Never fetch remote URLs.
        for article in articles:
            if not published(article):
                continue
            for url in article_images(article):
                file = local_image_path(url)
                try:
                    if not file:
                        continue
                    signature = copy_signature(file)
                    identical = signature[0] == digest
                    # Clipboard conversion/recompression changes bytes, not the image.
                    # Require the same aspect ratio and nearly identical whole-image RGB.
                    distance = 1.0
                    outliers = 1.0
                    if abs(signature[1] / query_signature[1] - 1) <= 0.01:
                        errors = [abs(a - b) for a, b in zip(signature[2], query_signature[2])]
                        distance = sum(errors) / (len(errors) * 255)
                        outliers = sum(error > 24 for error in errors) / len(errors)
                    if identical or (distance <= 0.015 and outliers <= 0.01):
                        yield {"source_type": "knowledge_base", "source_id": article["article_id"],
                               "image_url": url, "source_hash": source_hash(article), "image_hash": signature[0],
                               "image_similarity": 1.0 if identical else 1 - distance,
                               "exact_image": identical or distance == 0}
                        break
                except (OSError, ValueError):
                    continue  # A missing/unreadable file cannot establish image identity.
        last_id = articles[-1]["article_id"]
        if len(articles) < 512:
            break


def visual_candidates(path, encode=create_image_embedding, similarity=None):
    """Complete keyset scan in bounded pages; no model work holds DB connections."""
    from image_embedding_helper import cosine_similarity_from_json
    similarity = similarity or cosine_similarity_from_json
    digest = image_sha256(path)
    grouped = {}
    def keep(row, score, exact):
        if score < 0.45:
            return
        key = (row["source_type"], row["source_id"])
        current = grouped.get(key)
        if not current or score > current["image_similarity"]:
            grouped[key] = {k: v for k, v in row.items() if k != "image_embedding"}
            grouped[key].update(image_similarity=score, exact_image=exact)
    # Exact identity is stronger than semantic resemblance. Include every exact
    # source so duplicates across articles do not silently choose one policy.
    for rows in _candidate_pages(digest):
        for row in rows:
            keep(row, 1.0, True)
    for row in _exact_kb_candidates(digest, path):
        # Current article membership/revision supersedes stale index metadata.
        grouped[(row["source_type"], row["source_id"])] = row
    if grouped:
        return sorted(grouped.values(), key=lambda row: row["image_similarity"], reverse=True)
    embedding = None
    for rows in _candidate_pages():
        if embedding is None:
            embedding = encode(path)
            if not embedding:
                return []
        for row in rows:
            keep(row, similarity(embedding, row["image_embedding"]), False)
    return sorted(grouped.values(), key=lambda row: row["image_similarity"], reverse=True)


def current_articles(candidates):
    """Re-read policy and membership; index answers are never authority."""
    if not candidates:
        return []
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    result = []
    try:
        for candidate in candidates:
            if len(result) >= 5:
                break
            if candidate["source_type"] == "approved_escalation":
                cursor.execute("""SELECT e.image_url, q.review_id, q.question, q.answer FROM escalation e
                    JOIN review_queue q ON q.escalation_id = e.escalation_id
                    WHERE e.escalation_id = %s AND COALESCE(e.is_deleted, 0) = 0
                    ORDER BY q.review_id DESC LIMIT 1""", (candidate["source_id"],))
                review = cursor.fetchone()
                # Check latest status separately: a later rejection must invalidate an older approval.
                cursor.execute("SELECT status FROM review_queue WHERE review_id = %s", ((review or {}).get("review_id"),))
                status = cursor.fetchone() or {}
                if review and status.get("status") in {"approved", "published"} and review["image_url"] == candidate["image_url"]:
                    result.append({"article_id": None, "title": review["question"], "content": review["answer"],
                                   "approved_review_id": review["review_id"],
                                   "image_similarity": candidate["image_similarity"], "exact_image": candidate["exact_image"]})
                continue
            cursor.execute("SELECT * FROM wiki_article WHERE article_id = %s", (candidate["source_id"],))
            article = cursor.fetchone()
            if (published(article) and source_hash(article) == candidate.get("source_hash")
                    and local_image_url(candidate["image_url"]) in article_images(article)):
                result.append({**article, "image_similarity": candidate["image_similarity"],
                               "exact_image": candidate["exact_image"]})
    finally:
        cursor.close()
        conn.close()
    return result[:5]
