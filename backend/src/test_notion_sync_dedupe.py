"""Notion Sync duplicate-prevention tests.

Runs the real notion_sync_service code (check_for_notion_updates and
apply_pending_update) with the Notion API calls patched out. Needs no MySQL
server and no network: SQL goes to an in-memory-style SQLite file through a
small adapter that translates the few MySQL-only bits the service uses
(%s placeholders, NOW(), SELECT ... FOR UPDATE, GET_LOCK/RELEASE_LOCK).

Not covered here (needs a real MySQL): the INFORMATION_SCHEMA / ALTER TABLE
DDL in ensure_notion_sync_tables and the real GET_LOCK / row-lock behaviour.

Run (from backend/src):
    python -m unittest test_notion_sync_dedupe -v
"""

import re
import sqlite3
import sys
import tempfile
import threading
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import mysql.connector

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import requests
except ImportError:  # keep the suite runnable without the HTTP client installed
    requests = types.ModuleType("requests")

    class _HTTPError(Exception):
        def __init__(self, *args, response=None):
            super().__init__(*args)
            self.response = response

    requests.HTTPError = _HTTPError
    requests.Timeout = type("Timeout", (Exception,), {})
    requests.ConnectionError = type("ConnectionError", (Exception,), {})
    sys.modules["requests"] = requests

# notion_sync_service only needs this for token encryption, which these tests
# never touch.
sys.modules.setdefault("ai_provider_service", types.ModuleType("ai_provider_service"))

import notion_sync_service as svc  # noqa: E402


# --------------------------------------------------------------------------
# MySQL -> SQLite adapter (test harness only)
# --------------------------------------------------------------------------
sqlite3.register_converter("DATETIME", lambda raw: datetime.strptime(raw.decode(), "%Y-%m-%d %H:%M:%S"))
sqlite3.register_adapter(datetime, lambda value: value.strftime("%Y-%m-%d %H:%M:%S"))

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()
LOCKS_AVAILABLE = [True]  # flip to False to simulate a server without GET_LOCK


class _Cursor:
    def __init__(self, conn, dictionary=False):
        self._conn = conn
        self._cur = conn._raw.cursor()
        self._dict = dictionary
        self._synthetic = None
        self.lastrowid = None
        self.rowcount = -1

    def execute(self, sql, params=()):
        text = " ".join(sql.split())
        lock = re.match(r"SELECT (GET_LOCK|RELEASE_LOCK)\(%s(?:, \d+)?\)(?: AS (\w+))?$", text)
        if lock:
            value = self._conn._lock_call(lock.group(1), params[0])
            self._synthetic = ([lock.group(2) or lock.group(1)], [(value,)])
            return
        self._synthetic = None
        text = text.replace("%s", "?").replace("NOW()", "CURRENT_TIMESTAMP")
        text = re.sub(r"\s+FOR UPDATE$", "", text)
        try:
            self._cur.execute(text, tuple(params))
        except sqlite3.IntegrityError as error:
            # What MySQL raises for a duplicate key (errno 1062).
            raise mysql.connector.IntegrityError(msg=str(error), errno=1062) from error
        self.lastrowid = self._cur.lastrowid
        self.rowcount = self._cur.rowcount

    def _names(self):
        if self._synthetic:
            return self._synthetic[0]
        return [column[0] for column in (self._cur.description or [])]

    def _shape(self, row):
        return dict(zip(self._names(), row)) if self._dict else row

    def fetchone(self):
        if self._synthetic:
            rows = self._synthetic[1]
            row = rows.pop(0) if rows else None
        else:
            row = self._cur.fetchone()
        return None if row is None else self._shape(row)

    def fetchall(self):
        if self._synthetic:
            rows, self._synthetic = self._synthetic[1], (self._synthetic[0], [])
        else:
            rows = self._cur.fetchall()
        return [self._shape(row) for row in rows]

    def close(self):
        self._cur.close()


class _Conn:
    def __init__(self, path):
        self._raw = sqlite3.connect(path, timeout=15, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
        self._held = set()

    def cursor(self, dictionary=False, **_ignored):
        return _Cursor(self, dictionary)

    def start_transaction(self):
        pass

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        with _LOCKS_GUARD:
            for name in list(self._held):
                if _LOCKS.get(name) is self:
                    del _LOCKS[name]
        self._raw.close()

    def _lock_call(self, function, name):
        if not LOCKS_AVAILABLE[0]:
            raise RuntimeError("GET_LOCK is not available on this server")
        with _LOCKS_GUARD:
            if function == "GET_LOCK":
                owner = _LOCKS.get(name)
                if owner is None or owner is self:
                    _LOCKS[name] = self
                    self._held.add(name)
                    return 1
                return 0
            if _LOCKS.get(name) is self:
                del _LOCKS[name]
                self._held.discard(name)
                return 1
            return None


SCHEMA = """
CREATE TABLE wiki_article (
    article_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT, content TEXT, category TEXT, sub_category TEXT, link TEXT,
    is_deleted INTEGER DEFAULT 0,
    source_type TEXT DEFAULT 'manual',
    notion_page_id TEXT,
    notion_last_edited_time DATETIME
);
CREATE UNIQUE INDEX idx_wiki_article_notion_page_id ON wiki_article(notion_page_id);
CREATE TABLE notion_pending_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER, notion_page_id TEXT NOT NULL,
    proposed_title TEXT, proposed_content TEXT, previous_title TEXT, previous_content TEXT,
    notion_last_edited_time DATETIME,
    status TEXT NOT NULL DEFAULT 'pending',
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_by INTEGER, resolved_at DATETIME, trashed_by INTEGER, trashed_at DATETIME
);
CREATE TABLE notion_obsolete_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notion_page_id TEXT NOT NULL UNIQUE, page_title TEXT, deleted_at DATETIME, deleted_by INTEGER,
    last_known_notion_edited_time DATETIME, last_known_content_hash TEXT,
    latest_notion_edited_time DATETIME, latest_content_hash TEXT,
    obsolete_status TEXT DEFAULT 'unchanged', updated_after_obsolete INTEGER DEFAULT 0,
    last_checked_at DATETIME, last_sync_result TEXT
);
CREATE TABLE notion_sync_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT, imported_count INTEGER, updated_count INTEGER, skipped_count INTEGER,
    failed_count INTEGER, error_message TEXT,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP, completed_at DATETIME, created_by INTEGER
);
CREATE TABLE notion_sync_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, is_active INTEGER DEFAULT 1,
    connection_status TEXT, last_error TEXT, last_sync_at DATETIME
);
"""


def notion_time(minute):
    return f"2026-07-26T03:{minute:02d}:00.000Z"


def page(page_id, title, minute):
    return {
        "id": page_id,
        "object": "page",
        "last_edited_time": notion_time(minute),
        "properties": {"Name": {"type": "title", "title": [{"plain_text": title}]}},
    }


class NotionSyncDedupeTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.dbfile = str(self.dir / "test.db")
        raw = sqlite3.connect(self.dbfile)
        raw.executescript(SCHEMA)
        raw.close()

        LOCKS_AVAILABLE[0] = True
        _LOCKS.clear()
        self.db = _Conn(self.dbfile)
        self.pages, self.content = [], {}
        self.fetched, self.released, self.fail_pages = [], [], {}

        for target, replacement in (
            ("get_db_connection", lambda: _Conn(self.dbfile)),
            ("ensure_notion_sync_tables", lambda cursor: None),
        ):
            patcher = patch.object(svc, target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.db.close)

    # ---- helpers -------------------------------------------------------
    def q(self, sql, params=()):
        cur = self.db.cursor(dictionary=True)
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.close()
        return rows

    def x(self, sql, params=()):
        cur = self.db.cursor()
        cur.execute(sql, params)
        self.db.commit()
        cur.close()

    def articles(self, page_id=None):
        if page_id:
            return self.q("SELECT * FROM wiki_article WHERE notion_page_id = %s", (page_id,))
        return self.q("SELECT * FROM wiki_article ORDER BY article_id")

    def pendings(self, status=None):
        if status:
            return self.q("SELECT * FROM notion_pending_updates WHERE status = %s ORDER BY id", (status,))
        return self.q("SELECT * FROM notion_pending_updates ORDER BY id")

    def set_notion(self, *pages, **contents):
        self.pages = list(pages)
        for page_id, html in contents.items():
            self.content[page_id.replace("_", "-")] = html

    def check(self, token="secret-token-never-in-output"):
        def fake_blocks(_token, page_id):
            self.fetched.append(page_id)
            if page_id in self.fail_pages:
                raise self.fail_pages[page_id]
            return page_id

        with patch.object(svc, "discover_notion_content", side_effect=lambda _t: list(self.pages)), \
             patch.object(svc, "fetch_notion_block_children", side_effect=fake_blocks), \
             patch.object(svc, "notion_blocks_to_html", side_effect=lambda _t, page_id, _f: self.content.get(page_id, "<p>x</p>")):
            return svc.check_for_notion_updates(
                token, 1, self.dir,
                release_unused_uploads=lambda row, cursor: self.released.append(row),
            )

    def apply(self, pending_id):
        conn = svc.get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            result = svc.apply_pending_update(cur, pending_id, 1)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()

    def stage_raw_pending(self, page_id, content, minute, article_id=None):
        self.x(
            """INSERT INTO notion_pending_updates
               (article_id, notion_page_id, proposed_title, proposed_content, notion_last_edited_time, status)
               VALUES (%s, %s, 'Opening SOP', %s, %s, 'pending')""",
            (article_id, page_id, content, f"2026-07-26 03:{minute:02d}:00"),
        )

    # ---- Test 1 / 2: first sync, then repeated sync --------------------
    def test_first_check_stages_one_item_per_page_and_apply_creates_one_article_each(self):
        self.set_notion(page("p-1", "Opening SOP", 1), page("p-2", "Closing SOP", 2),
                        p_1="<p>open</p>", p_2="<p>close</p>")

        result = self.check()

        self.assertEqual(result["status"], "completed")
        self.assertEqual((result["new"], result["flagged"], result["unchanged"], result["failed"]), (2, 0, 0, 0))
        self.assertEqual(len(self.pendings("pending")), 2)
        self.assertEqual(self.articles(), [], "checking must never publish by itself")

        for item in self.pendings("pending"):
            self.assertIsNotNone(self.apply(item["id"]))

        rows = self.articles()
        self.assertEqual(sorted(r["notion_page_id"] for r in rows), ["p-1", "p-2"])
        self.assertTrue(all(r["source_type"] == "notion" and r["category"] == "Notion" and not r["is_deleted"] for r in rows))
        self.assertTrue(all(r["notion_last_edited_time"] is not None for r in rows))

    def test_second_check_with_no_notion_change_creates_and_updates_nothing(self):
        self.set_notion(page("p-1", "Opening SOP", 1), page("p-2", "Closing SOP", 2))
        self.check()
        for item in self.pendings("pending"):
            self.apply(item["id"])
        articles_before = self.articles()
        pending_before = self.pendings()
        self.fetched.clear()

        again = self.check()

        self.assertEqual((again["new"], again["flagged"], again["refreshed"], again["unchanged"], again["failed"]), (0, 0, 0, 2, 0))
        self.assertEqual(self.articles(), articles_before)
        self.assertEqual(self.pendings(), pending_before)
        self.assertEqual(self.fetched, [], "skipped pages must not be re-read from Notion (no image re-download)")

    def test_repeated_checks_before_review_do_not_stack_pending_items(self):
        self.set_notion(page("p-1", "Opening SOP", 1))
        for _ in range(4):
            self.check()
        self.assertEqual(len(self.pendings("pending")), 1)

    def test_published_page_is_never_proposed_again(self):
        self.set_notion(page("p-1", "Opening SOP", 1))
        self.check()
        self.apply(self.pendings("pending")[0]["id"])
        for _ in range(3):
            result = self.check()
            self.assertEqual((result["new"], result["flagged"], result["refreshed"]), (0, 0, 0))
        self.assertEqual(len(self.articles()), 1)
        self.assertEqual(len(self.pendings()), 1)

    # ---- Test 3: concurrent syncs --------------------------------------
    def test_overlapping_checks_in_one_process_run_one_at_a_time(self):
        self.set_notion(page("p-1", "Opening SOP", 1), page("p-2", "Closing SOP", 2))
        started, release = threading.Event(), threading.Event()
        first_result = {}

        def slow_discover(_token):
            started.set()
            release.wait(10)
            return list(self.pages)

        with patch.object(svc, "discover_notion_content", side_effect=slow_discover), \
             patch.object(svc, "fetch_notion_block_children", return_value=[]), \
             patch.object(svc, "notion_blocks_to_html", return_value="<p>x</p>"):
            worker = threading.Thread(
                target=lambda: first_result.update(svc.check_for_notion_updates("t", 1, self.dir))
            )
            worker.start()
            self.assertTrue(started.wait(10))
            second = svc.check_for_notion_updates("t", 1, self.dir)
            release.set()
            worker.join(15)

        self.assertEqual(second["status"], "already_running")
        self.assertEqual(second["errorMessage"], "Another sync is already running.")
        self.assertEqual(first_result["status"], "completed")
        self.assertEqual(len(self.pendings("pending")), 2)
        self.assertEqual(len(self.q("SELECT id FROM notion_sync_jobs")), 1, "a refused run must not be logged as a job")

    def test_check_refuses_when_another_process_holds_the_database_lock(self):
        self.set_notion(page("p-1", "Opening SOP", 1))
        other = svc.get_db_connection()
        other_cur = other.cursor()
        other_cur.execute("SELECT GET_LOCK(%s, 0)", (svc._DB_CHECK_LOCK_NAME,))
        self.assertEqual(other_cur.fetchone()[0], 1)
        try:
            refused = self.check()
            self.assertEqual(refused["status"], "already_running")
            self.assertEqual(self.pendings(), [])
            self.assertEqual(self.q("SELECT id FROM notion_sync_jobs"), [])
        finally:
            other_cur.close()
            other.close()

        self.assertEqual(self.check()["status"], "completed")
        self.assertEqual(len(self.pendings("pending")), 1)

    def test_database_lock_is_released_after_a_run(self):
        self.set_notion(page("p-1", "Opening SOP", 1))
        self.check()
        probe = svc.get_db_connection()
        cur = probe.cursor()
        cur.execute("SELECT GET_LOCK(%s, 0)", (svc._DB_CHECK_LOCK_NAME,))
        self.assertEqual(cur.fetchone()[0], 1)
        cur.close()
        probe.close()

    def test_check_still_runs_when_the_server_has_no_get_lock(self):
        LOCKS_AVAILABLE[0] = False
        self.set_notion(page("p-1", "Opening SOP", 1))
        self.assertEqual(self.check()["status"], "completed")
        self.assertEqual(len(self.pendings("pending")), 1)

    # ---- Edits before review never create a second item ----------------
    def test_new_page_edited_again_before_approval_refreshes_the_same_pending_item(self):
        self.set_notion(page("p-1", "Opening SOP", 1), p_1="<p>v1</p>")
        self.check()
        original_id = self.pendings("pending")[0]["id"]

        self.set_notion(page("p-1", "Opening SOP (edited)", 5), p_1="<p>v2</p>")
        again = self.check()

        self.assertEqual((again["new"], again["flagged"], again["refreshed"]), (0, 0, 1))
        pending = self.pendings("pending")
        self.assertEqual([p["id"] for p in pending], [original_id])
        self.assertEqual(pending[0]["proposed_content"], "<p>v2</p>")
        self.assertEqual(pending[0]["proposed_title"], "Opening SOP (edited)")
        self.assertEqual(len(self.released), 1, "files of the replaced proposal are handed back for cleanup")
        self.assertIn("<p>v1</p>", self.released[0]["proposed_content"])

        self.apply(original_id)
        self.assertEqual(len(self.articles("p-1")), 1)
        self.assertEqual(self.articles("p-1")[0]["content"], "<p>v2</p>")

    def test_legacy_double_pending_items_for_one_page_still_yield_one_article(self):
        """Production may already hold two 'new' items for the same page."""
        self.stage_raw_pending("p-1", "<p>v1</p>", 1)
        self.stage_raw_pending("p-1", "<p>v2</p>", 9)
        first, second = self.pendings("pending")

        self.apply(first["id"])
        self.apply(second["id"])

        rows = self.articles("p-1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["content"], "<p>v2</p>", "the newer Notion version wins")

    def test_applying_older_items_in_reverse_order_does_not_roll_the_article_back(self):
        self.stage_raw_pending("p-1", "<p>v1</p>", 1)
        self.stage_raw_pending("p-1", "<p>v2</p>", 9)
        older, newer = self.pendings("pending")

        self.apply(newer["id"])
        self.apply(older["id"])

        rows = self.articles("p-1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["content"], "<p>v2</p>")
        self.assertEqual(self.pendings("pending"), [])

    def test_the_same_pending_item_cannot_be_applied_twice(self):
        self.set_notion(page("p-1", "Opening SOP", 1))
        self.check()
        pending_id = self.pendings("pending")[0]["id"]
        self.assertIsNotNone(self.apply(pending_id))
        self.assertIsNone(self.apply(pending_id))
        self.assertEqual(len(self.articles("p-1")), 1)

    # ---- Test 4: local edits are not "modified in Notion" --------------
    def test_local_edit_is_kept_and_does_not_trigger_a_resync(self):
        self.set_notion(page("p-1", "Opening SOP", 1), p_1="<p>from notion</p>")
        self.check()
        article_id = self.apply(self.pendings("pending")[0]["id"])

        # What PUT /api/articles/<id> does: changes the article, never the
        # Notion bookkeeping columns.
        self.x("UPDATE wiki_article SET title = 'Manager title', content = '<p>manager edit</p>' WHERE article_id = %s",
               (article_id,))

        again = self.check()

        self.assertEqual((again["new"], again["flagged"], again["refreshed"], again["unchanged"]), (0, 0, 0, 1))
        row = self.articles("p-1")[0]
        self.assertEqual((row["title"], row["content"]), ("Manager title", "<p>manager edit</p>"))
        self.assertEqual(len(self.pendings("pending")), 0)

    # ---- Test 5 / 6: Notion edits and renames update the SAME article ---
    def test_notion_edit_and_rename_update_the_same_article_and_keep_status(self):
        self.set_notion(page("p-1", "Opening SOP", 1), p_1="<p>v1</p>")
        self.check()
        article_id = self.apply(self.pendings("pending")[0]["id"])
        self.x("UPDATE wiki_article SET category = 'SOP', content = '<p>local edit</p>', is_deleted = 1 WHERE article_id = %s",
               (article_id,))

        self.set_notion(page("p-1", "Opening SOP - renamed", 7), p_1="<p>v2</p>")
        changed = self.check()

        self.assertEqual((changed["new"], changed["flagged"], changed["unchanged"]), (0, 1, 0))
        item = self.pendings("pending")[0]
        self.assertEqual(item["article_id"], article_id)
        self.assertEqual(item["previous_content"], "<p>local edit</p>")

        self.assertEqual(self.apply(item["id"]), article_id)

        rows = self.articles()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["article_id"], article_id)
        self.assertEqual((rows[0]["title"], rows[0]["content"]), ("Opening SOP - renamed", "<p>v2</p>"))
        self.assertEqual(rows[0]["category"], "SOP", "sync must not change the category")
        self.assertEqual(rows[0]["is_deleted"], 1, "sync must not change the publish/bin state")
        self.assertEqual(self.check()["unchanged"], 1)

    def test_replaced_version_is_kept_in_history_even_if_edited_after_staging(self):
        self.set_notion(page("p-1", "Opening SOP", 1), p_1="<p>v1</p>")
        self.check()
        article_id = self.apply(self.pendings("pending")[0]["id"])

        self.set_notion(page("p-1", "Opening SOP", 4), p_1="<p>v2</p>")
        self.check()
        item = self.pendings("pending")[0]
        # Manager edits locally AFTER the Notion change was staged but BEFORE approving.
        self.x("UPDATE wiki_article SET content = '<p>late local edit</p>' WHERE article_id = %s", (article_id,))

        self.apply(item["id"])

        history = self.q("SELECT previous_content FROM notion_pending_updates WHERE id = %s", (item["id"],))[0]
        self.assertEqual(history["previous_content"], "<p>late local edit</p>")

    def test_page_edited_twice_before_review_refreshes_one_update_item(self):
        self.set_notion(page("p-1", "Opening SOP", 1), p_1="<p>v1</p>")
        self.check()
        self.apply(self.pendings("pending")[0]["id"])

        self.set_notion(page("p-1", "Opening SOP", 4), p_1="<p>v2</p>")
        self.check()
        self.set_notion(page("p-1", "Opening SOP", 8), p_1="<p>v3</p>")
        third = self.check()

        self.assertEqual((third["flagged"], third["refreshed"]), (0, 1))
        self.assertEqual(len(self.pendings("pending")), 1)
        self.apply(self.pendings("pending")[0]["id"])
        self.assertEqual(self.articles("p-1")[0]["content"], "<p>v3</p>")

    def test_applying_links_a_legacy_article_that_has_no_notion_page_id(self):
        self.x("INSERT INTO wiki_article (title, content, category, source_type) VALUES ('Old import', '<p>old</p>', 'Notion', 'notion')")
        legacy_id = self.articles()[0]["article_id"]
        self.stage_raw_pending("p-1", "<p>new</p>", 3, article_id=legacy_id)

        self.assertEqual(self.apply(self.pendings("pending")[0]["id"]), legacy_id)

        rows = self.articles()
        self.assertEqual([(r["article_id"], r["notion_page_id"], r["content"]) for r in rows], [(legacy_id, "p-1", "<p>new</p>")])

    # ---- Test 8: failures ----------------------------------------------
    def test_one_failing_page_does_not_stop_the_others_or_leave_partial_rows(self):
        self.set_notion(page("p-1", "Opening SOP", 1), page("p-bad", "Broken page", 2), page("p-3", "Closing SOP", 3))
        self.fail_pages["p-bad"] = requests.HTTPError(
            "500 Server Error for url: https://api.notion.com/v1/blocks/p-bad/children?token=secret",
            response=types.SimpleNamespace(status_code=500),
        )

        result = self.check()

        self.assertEqual(result["status"], "completed")
        self.assertEqual((result["new"], result["failed"]), (2, 1))
        self.assertEqual(sorted(p["notion_page_id"] for p in self.pendings()), ["p-1", "p-3"])
        self.assertEqual(len(result["failedItems"]), 1)
        failure = result["failedItems"][0]
        self.assertEqual(failure["title"], "Broken page")
        self.assertIn("500", failure["reason"])
        blob = repr(result)
        for secret in ("secret", "api.notion.com", "Traceback"):
            self.assertNotIn(secret, blob)

        self.fail_pages.clear()
        retry = self.check()
        self.assertEqual((retry["new"], retry["unchanged"], retry["failed"]), (1, 2, 0))
        self.assertEqual(len(self.pendings("pending")), 3)

    def test_inaccessible_page_is_skipped_without_failing_the_run(self):
        self.set_notion(page("p-1", "Opening SOP", 1), page("p-gone", "Removed page", 2))
        self.fail_pages["p-gone"] = requests.HTTPError("404", response=types.SimpleNamespace(status_code=404))

        result = self.check()

        self.assertEqual((result["status"], result["new"], result["failed"], result["inaccessible"]), ("completed", 1, 0, 1))

    def test_notion_permission_error_gives_a_friendly_message_without_internals(self):
        forbidden = requests.HTTPError(
            "403 Client Error: Forbidden for url: https://api.notion.com/v1/search",
            response=types.SimpleNamespace(status_code=403),
        )
        with patch.object(svc, "discover_notion_content", side_effect=forbidden):
            result = svc.check_for_notion_updates("t", 1, self.dir)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errorMessage"], "Notion connection failed. Check the integration permission.")
        self.assertNotIn("api.notion.com", repr(result))

    def test_rejected_token_asks_for_reconnect(self):
        with patch.object(svc, "discover_notion_content", side_effect=svc.NotionAuthError("401 with token abc")):
            result = svc.check_for_notion_updates("t", 1, self.dir)
        self.assertEqual(result["status"], "reconnect_required")

    def test_failed_run_is_recorded_hides_internals_and_releases_the_lock(self):
        with patch.object(svc, "discover_notion_content", side_effect=RuntimeError("boom with password=hunter2")):
            result = svc.check_for_notion_updates("t", 1, self.dir)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("hunter2", repr(result))
        job = self.q("SELECT status, error_message FROM notion_sync_jobs")[0]
        self.assertEqual(job["status"], "failed")
        self.assertNotIn("hunter2", job["error_message"])

        self.set_notion(page("p-1", "Opening SOP", 1))
        self.assertEqual(self.check()["status"], "completed")

    # ---- Test 7: unique index migration --------------------------------
    def test_unique_index_is_added_only_when_no_duplicates_exist(self):
        class Scripted:
            def __init__(self, existing_unique, duplicates):
                self.existing_unique, self.duplicates = existing_unique, duplicates
                self.executed, self._next = [], None

            def execute(self, sql, params=()):
                sql = " ".join(sql.split())
                self.executed.append(sql)
                if "INFORMATION_SCHEMA.STATISTICS" in sql:
                    self._next = {"c": 1 if self.existing_unique else 0}
                elif "GROUP BY notion_page_id" in sql:
                    self._next = {"notion_page_id": "dup"} if self.duplicates else None

            def fetchone(self):
                return self._next

        def altered(cursor):
            return any("ADD UNIQUE INDEX" in sql for sql in cursor.executed)

        clean = Scripted(existing_unique=False, duplicates=False)
        svc._NOTION_PAGE_ID_INDEX_READY = False
        svc._ensure_notion_page_id_unique_index(clean)
        self.assertTrue(altered(clean))
        self.assertTrue(svc._NOTION_PAGE_ID_INDEX_READY)

        for existing_unique, duplicates in ((True, False), (False, True)):
            svc._NOTION_PAGE_ID_INDEX_READY = False
            cursor = Scripted(existing_unique, duplicates)
            svc._ensure_notion_page_id_unique_index(cursor)
            self.assertFalse(altered(cursor), (existing_unique, duplicates))
            self.assertEqual(svc._NOTION_PAGE_ID_INDEX_READY, existing_unique)
            self.assertFalse(any(word in " ".join(cursor.executed).upper() for word in ("DELETE", "DROP")))

        svc._NOTION_PAGE_ID_INDEX_READY = True
        untouched = Scripted(False, False)
        svc._ensure_notion_page_id_unique_index(untouched)
        self.assertEqual(untouched.executed, [], "once confirmed, later calls cost nothing")

        # A database user that may not ALTER must not break every Notion request.
        class CannotAlter(Scripted):
            def execute(self, sql, params=()):
                super().execute(sql, params)
                if "ADD UNIQUE INDEX" in " ".join(sql.split()):
                    raise mysql.connector.ProgrammingError(msg="ALTER command denied", errno=1142)

        svc._NOTION_PAGE_ID_INDEX_READY = False
        svc._ensure_notion_page_id_unique_index(CannotAlter(False, False))
        self.assertFalse(svc._NOTION_PAGE_ID_INDEX_READY)

    def test_unique_index_makes_a_second_article_for_one_page_impossible(self):
        self.x("INSERT INTO wiki_article (title, notion_page_id) VALUES ('A', 'p-1')")
        with self.assertRaises(mysql.connector.IntegrityError):
            self.x("INSERT INTO wiki_article (title, notion_page_id) VALUES ('A again', 'p-1')")

    def test_losing_a_concurrent_approval_race_updates_instead_of_failing(self):
        """Two approvals pass the 'no article yet' lookup together; the loser's INSERT hits the unique key."""
        self.stage_raw_pending("p-1", "<p>from the loser</p>", 5)
        self.x("""INSERT INTO wiki_article (title, content, source_type, notion_page_id, notion_last_edited_time)
                  VALUES ('Winner', '<p>from the winner</p>', 'notion', 'p-1', '2026-07-26 03:01:00')""")
        real_lookup = svc._find_article_for_pending
        calls = []

        def blind_on_first_call(cursor, pending):
            calls.append(1)
            return None if len(calls) == 1 else real_lookup(cursor, pending)

        with patch.object(svc, "_find_article_for_pending", side_effect=blind_on_first_call):
            article_id = self.apply(self.pendings("pending")[0]["id"])

        rows = self.articles("p-1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["article_id"], article_id)
        self.assertEqual(rows[0]["content"], "<p>from the loser</p>", "the newer Notion version is applied to the one article")


if __name__ == "__main__":
    unittest.main()
