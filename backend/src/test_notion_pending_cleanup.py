"""Tests for backend/tools/notion_pending_cleanup.py.

Same approach as test_notion_sync_dedupe.py: the real tool and the real
notion_sync_service trash/restore/lock code run against SQLite through that
file's MySQL adapter. Nothing here touches MySQL or Notion.

Not covered (needs a real MySQL): the MySQL-specific SQL, i.e. GET_LOCK,
SELECT ... FOR UPDATE and SET SESSION TRANSACTION READ ONLY.

Run (from backend/src):
    python -m unittest test_notion_pending_cleanup -v
"""

import csv
import re
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))

# Importing this module also installs the requests/ai_provider_service stubs
# and the SQLite converters the adapter relies on. Only helpers are imported,
# not its TestCase, so its tests are not run twice.
from test_notion_sync_dedupe import SCHEMA, LOCKS_AVAILABLE, _Conn, _LOCKS  # noqa: E402
import notion_sync_service as svc  # noqa: E402
import notion_pending_cleanup as cleanup  # noqa: E402

_READ_ONLY = re.compile(r"^\s*(SELECT|SHOW)\b", re.IGNORECASE)


class _DryRunCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=()):
        if not _READ_ONLY.match(sql):
            raise AssertionError("a dry run tried to write: " + " ".join(sql.split())[:60])
        return self._cursor.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _DryRunConn:
    """Fails the test if the tool writes through a connection it opened read-only."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self, **kwargs):
        return _DryRunCursor(self._conn.cursor(**kwargs))

    def __getattr__(self, name):
        return getattr(self._conn, name)


def at(minute):
    return datetime(2026, 7, 26, 3, minute, 0)


class PendingCleanupTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.dbfile = str(self.dir / "test.db")
        raw = sqlite3.connect(self.dbfile)
        raw.executescript(SCHEMA)
        raw.close()
        LOCKS_AVAILABLE[0] = True
        _LOCKS.clear()
        self.db = _Conn(self.dbfile)
        self.addCleanup(self.db.close)
        self.lines = []
        self.plan_csv = self.dir / "plan.csv"
        self.undo_log = self.dir / "undo.csv"

    # ---- helpers -------------------------------------------------------
    def connect(self, read_only):
        conn = _Conn(self.dbfile)
        return _DryRunConn(conn) if read_only else conn

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

    def item(self, page_id, minute, status="pending", article_id=None, title="Opening SOP"):
        self.x(
            """INSERT INTO notion_pending_updates
               (article_id, notion_page_id, proposed_title, proposed_content, notion_last_edited_time, status)
               VALUES (%s, %s, %s, '<p>x</p>', %s, %s)""",
            (article_id, page_id, title, None if minute is None else at(minute), status),
        )
        return self.q("SELECT MAX(id) AS id FROM notion_pending_updates")[0]["id"]

    def article(self, page_id, minute, title="Opening SOP"):
        self.x(
            """INSERT INTO wiki_article (title, content, source_type, notion_page_id, notion_last_edited_time)
               VALUES (%s, '<p>live</p>', 'notion', %s, %s)""",
            (title, page_id, None if minute is None else at(minute)),
        )
        return self.q("SELECT MAX(article_id) AS id FROM wiki_article")[0]["id"]

    def status_of(self, item_id):
        return self.q("SELECT status FROM notion_pending_updates WHERE id = %s", (item_id,))[0]["status"]

    def run_tool(self, apply=False, **kwargs):
        return cleanup.run(
            self.connect, apply=apply, plan_csv=self.plan_csv, undo_log=self.undo_log,
            out=self.lines.append, **kwargs,
        )

    def snapshot(self, *tables):
        return {table: self.q(f"SELECT * FROM {table} ORDER BY 1") for table in tables}

    def plan_rows(self):
        with open(self.plan_csv, newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def output(self):
        return "\n".join(self.lines)

    # ---- Rule A ---------------------------------------------------------
    def test_three_pending_items_and_no_article_keeps_only_the_newest(self):
        a = self.item("p-1", 1)
        b = self.item("p-1", 5)
        c = self.item("p-1", 3)

        self.assertEqual(self.run_tool(apply=True), 0)

        self.assertEqual([self.status_of(i) for i in (a, b, c)], ["trashed", "pending", "trashed"])

    def test_tie_on_edit_time_keeps_the_highest_id(self):
        low = self.item("p-1", 4)
        high = self.item("p-1", 4)

        self.run_tool(apply=True)

        self.assertEqual((self.status_of(low), self.status_of(high)), ("trashed", "pending"))

    def test_the_example_from_the_brief(self):
        """Page X: pending #1,#2,#3 and an article that is not older than any of them."""
        ids = [self.item("p-x", 1), self.item("p-x", 2), self.item("p-x", 3)]
        self.article("p-x", 3)

        self.run_tool(apply=True)

        self.assertEqual([self.status_of(i) for i in ids], ["trashed"] * 3)

    # ---- Rule B ---------------------------------------------------------
    def test_two_pending_items_older_than_the_article_are_both_trashed(self):
        a = self.item("p-1", 1)
        b = self.item("p-1", 2)
        self.article("p-1", 9)

        self.run_tool(apply=True)

        self.assertEqual((self.status_of(a), self.status_of(b)), ("trashed", "trashed"))

    def test_item_equal_to_the_article_is_stale(self):
        only = self.item("p-1", 5)
        self.article("p-1", 5)
        self.run_tool(apply=True)
        self.assertEqual(self.status_of(only), "trashed")

    def test_item_newer_than_its_article_is_kept_for_review(self):
        newer = self.item("p-1", 9, article_id=None)
        self.article("p-1", 2)

        self.run_tool(apply=True)

        self.assertEqual(self.status_of(newer), "pending")
        self.assertIn("newer than article", self.output())

    def test_item_for_a_page_with_no_article_is_kept(self):
        only = self.item("p-new", 3)
        self.run_tool(apply=True)
        self.assertEqual(self.status_of(only), "pending")

    def test_old_duplicates_are_trashed_but_a_newer_real_change_survives(self):
        old1, old2, newest = self.item("p-1", 1), self.item("p-1", 2), self.item("p-1", 9)
        self.article("p-1", 5)

        self.run_tool(apply=True)

        self.assertEqual([self.status_of(i) for i in (old1, old2, newest)], ["trashed", "trashed", "pending"])

    # ---- Rule C ---------------------------------------------------------
    def test_null_edit_time_is_untouched_and_listed_for_manual_review(self):
        unknown = self.item("p-1", None)
        self.run_tool(apply=True)
        self.assertEqual(self.status_of(unknown), "pending")
        self.assertIn("needs manual review", self.output().lower())
        row = [r for r in self.plan_rows() if r["item_id"] == str(unknown)][0]
        self.assertEqual((row["action"], row["rule"]), ("MANUAL", "C"))

    def test_other_items_are_still_cleaned_when_one_has_a_null_time(self):
        unknown, older, newer = self.item("p-1", None), self.item("p-1", 1), self.item("p-1", 6)
        self.run_tool(apply=True)
        self.assertEqual([self.status_of(i) for i in (unknown, older, newer)], ["pending", "trashed", "pending"])

    def test_article_without_an_edit_time_means_the_item_is_not_judged(self):
        only = self.item("p-1", 5)
        self.article("p-1", None)
        self.run_tool(apply=True)
        self.assertEqual(self.status_of(only), "pending")
        self.assertEqual(self.plan_rows()[0]["action"], "MANUAL")

    def test_items_linked_to_different_articles_are_left_alone(self):
        first = self.item("p-1", 1, article_id=101)
        second = self.item("p-1", 2, article_id=102)
        self.run_tool(apply=True)
        self.assertEqual((self.status_of(first), self.status_of(second)), ("pending", "pending"))
        self.assertEqual({r["action"] for r in self.plan_rows()}, {"MANUAL"})

    def test_item_linked_to_an_article_the_page_does_not_belong_to_is_left_alone(self):
        other = self.article("p-other", 1)
        stray = self.item("p-1", 1, article_id=other)
        self.article("p-1", 9)
        self.run_tool(apply=True)
        self.assertEqual(self.status_of(stray), "pending")

    def test_item_linked_to_a_missing_article_is_left_alone(self):
        orphan = self.item("p-1", 1, article_id=999)
        self.run_tool(apply=True)
        self.assertEqual(self.status_of(orphan), "pending")

    # ---- Safety ---------------------------------------------------------
    def test_dry_run_is_the_default_and_changes_nothing(self):
        self.item("p-1", 1)
        self.item("p-1", 2)
        self.article("p-1", 9)
        before = self.snapshot("notion_pending_updates", "wiki_article", "notion_sync_jobs")

        code = self.run_tool()  # apply defaults to False; the connection fails the test on any write

        self.assertEqual(code, 0)
        self.assertEqual(self.snapshot("notion_pending_updates", "wiki_article", "notion_sync_jobs"), before)
        self.assertIn("DRY RUN", self.output())
        self.assertFalse(self.undo_log.exists(), "a dry run writes no undo log")
        self.assertEqual(len(self.plan_rows()), 2, "but it does write the plan CSV")

    def test_dry_run_reports_the_counts(self):
        for minute in (1, 2, 3):
            self.item("p-a", minute)  # rule A: 2 trashed, newest kept
        self.item("p-b", 1)
        self.article("p-b", 5)        # rule B: 1 trashed
        self.item("p-c", None)        # manual: 1
        self.run_tool()
        text = self.output()
        for needle in ("Pending items found", "Rule A", "Rule B", "Kept for manager review", "Needs manual review"):
            self.assertIn(needle, text)
        summary = cleanup.summarize(cleanup.build_plan(*cleanup.load_state(cleanup.ReadOnly(self.db))))
        self.assertEqual(summary, {"total": 5, "trash_a": 2, "trash_b": 1, "keep": 1, "manual": 1})

    def test_apply_twice_changes_nothing_the_second_time(self):
        self.item("p-1", 1)
        self.item("p-1", 2)
        self.item("p-2", 1)
        self.article("p-2", 9)
        keeper = self.item("p-3", 8)
        self.article("p-3", 2)

        self.run_tool(apply=True)
        after_first = self.snapshot("notion_pending_updates")
        self.lines.clear()
        self.undo_log.unlink()

        code = self.run_tool(apply=True)

        self.assertEqual(code, 0)
        self.assertEqual(self.snapshot("notion_pending_updates"), after_first)
        self.assertIn("0 item(s) moved to Trash", self.output())
        self.assertFalse(self.undo_log.exists())
        self.assertEqual(self.status_of(keeper), "pending")

    def test_only_pending_items_are_ever_touched(self):
        applied = self.item("p-1", 1, status="applied")
        dismissed = self.item("p-1", 2, status="dismissed")
        trashed = self.item("p-1", 3, status="trashed")
        self.x("UPDATE notion_pending_updates SET trashed_at = '2026-01-01 00:00:00', trashed_by = 7 WHERE id = %s", (trashed,))
        pending = self.item("p-1", 4)
        self.article("p-1", 9)  # makes the pending item stale

        before = {r["id"]: r for r in self.snapshot("notion_pending_updates")["notion_pending_updates"]}
        self.run_tool(apply=True)
        after = {r["id"]: r for r in self.snapshot("notion_pending_updates")["notion_pending_updates"]}

        for untouched in (applied, dismissed, trashed):
            self.assertEqual(after[untouched], before[untouched])
        self.assertEqual(self.status_of(pending), "trashed")
        self.assertEqual([r["item_id"] for r in self.plan_rows()], [str(pending)])

    def test_only_the_pending_table_is_modified(self):
        self.item("p-1", 1)
        self.item("p-1", 2)
        self.article("p-1", 9)
        self.x("INSERT INTO notion_obsolete_articles (notion_page_id, page_title) VALUES ('p-9', 'Gone')")
        self.x("INSERT INTO notion_sync_configs (is_active, connection_status) VALUES (1, 'connected')")
        others = ("wiki_article", "notion_obsolete_articles", "notion_sync_jobs", "notion_sync_configs")
        before = self.snapshot(*others)

        self.run_tool(apply=True)

        self.assertEqual(self.snapshot(*others), before)

    def test_trashed_items_look_exactly_like_ones_trashed_from_the_ui(self):
        via_tool = self.item("p-1", 1)
        self.item("p-1", 2)
        via_ui = self.item("p-2", 1)

        self.run_tool(apply=True)
        cur = self.db.cursor(dictionary=True)
        svc.trash_pending_update(cur, via_ui, 5)  # what the Trash button does
        self.db.commit()
        cur.close()

        rows = {r["id"]: r for r in self.q("SELECT * FROM notion_pending_updates")}
        self.assertEqual(rows[via_tool]["status"], rows[via_ui]["status"])
        self.assertIsNotNone(rows[via_tool]["trashed_at"])
        # What the Trash tab lists:
        listed = {r["id"] for r in svc.list_pending_updates(self.db.cursor(dictionary=True), status="trashed")}
        self.assertIn(via_tool, listed)
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM notion_pending_updates")[0]["n"], 3, "nothing is deleted")

    # ---- Sync lock ------------------------------------------------------
    def test_apply_refuses_while_a_sync_holds_the_lock(self):
        self.item("p-1", 1)
        self.item("p-1", 2)
        before = self.snapshot("notion_pending_updates")
        sync = _Conn(self.dbfile)
        cur = sync.cursor()
        cur.execute("SELECT GET_LOCK(%s, 0)", (svc._DB_CHECK_LOCK_NAME,))
        self.assertEqual(cur.fetchone()[0], 1)
        try:
            code = self.run_tool(apply=True)
        finally:
            sync.close()

        self.assertEqual(code, 2)
        self.assertEqual(self.snapshot("notion_pending_updates"), before)
        self.assertIn("sync is running", self.output().lower())
        self.assertFalse(self.undo_log.exists())

        self.assertEqual(self.run_tool(apply=True), 0, "works once the sync has finished")

    def test_apply_refuses_when_the_lock_cannot_be_taken_at_all(self):
        self.item("p-1", 1)
        self.item("p-1", 2)
        before = self.snapshot("notion_pending_updates")
        LOCKS_AVAILABLE[0] = False
        self.assertEqual(self.run_tool(apply=True), 2)
        self.assertEqual(self.snapshot("notion_pending_updates"), before)

    def test_the_lock_is_released_after_applying(self):
        self.item("p-1", 1)
        self.item("p-1", 2)
        self.run_tool(apply=True)
        probe = _Conn(self.dbfile)
        cur = probe.cursor()
        cur.execute("SELECT GET_LOCK(%s, 0)", (svc._DB_CHECK_LOCK_NAME,))
        self.assertEqual(cur.fetchone()[0], 1)
        probe.close()

    def test_a_failure_part_way_rolls_everything_back_and_leaves_no_undo_log(self):
        first, second, third = self.item("p-1", 1), self.item("p-1", 2), self.item("p-1", 3)
        real = svc.trash_pending_update
        calls = []

        def fail_on_second(cursor, pending_id, actor_id):
            calls.append(pending_id)
            if len(calls) == 2:
                raise RuntimeError("boom with password=hunter2")
            return real(cursor, pending_id, actor_id)

        before = self.snapshot("notion_pending_updates")
        with patch.object(svc, "trash_pending_update", side_effect=fail_on_second), \
             patch.object(_Conn, "rollback", autospec=True, side_effect=_Conn.rollback) as rollback:
            code = self.run_tool(apply=True)

        self.assertTrue(rollback.called, "the transaction is rolled back explicitly")
        self.assertEqual(code, 1)
        self.assertEqual(self.snapshot("notion_pending_updates"), before)
        self.assertFalse(self.undo_log.exists())
        self.assertNotIn("hunter2", self.output())
        self.assertNotIn("Traceback", self.output())
        self.assertIn("nothing was changed", self.output().lower())

    def test_an_item_that_changed_since_planning_is_left_alone_and_not_logged(self):
        """A manager dismisses an item after the plan is made but before it is applied."""
        older, newer = self.item("p-1", 1), self.item("p-1", 2)
        real_load_state = cleanup.load_state

        def load_then_manager_dismisses(db):
            state = real_load_state(db)
            self.x("UPDATE notion_pending_updates SET status = 'dismissed' WHERE id = %s", (older,))
            return state

        with patch.object(cleanup, "load_state", side_effect=load_then_manager_dismisses):
            self.run_tool(apply=True)

        self.assertEqual((self.status_of(older), self.status_of(newer)), ("dismissed", "pending"))
        self.assertFalse(self.undo_log.exists(), "nothing was trashed, so nothing is logged")

    # ---- Undo -----------------------------------------------------------
    def test_undo_log_records_previous_status_and_undo_restores_the_items(self):
        a, b, c = self.item("p-1", 1), self.item("p-1", 2), self.item("p-1", 3)
        self.run_tool(apply=True)
        with open(self.undo_log, newline="", encoding="utf-8") as handle:
            logged = list(csv.DictReader(handle))
        self.assertEqual(sorted(int(r["item_id"]) for r in logged), [a, b])
        self.assertEqual({(r["previous_status"], r["new_status"]) for r in logged}, {("pending", "trashed")})

        self.lines.clear()
        self.assertEqual(cleanup.run(self.connect, undo_file=self.undo_log, out=self.lines.append), 0)
        self.assertEqual((self.status_of(a), self.status_of(b)), ("trashed", "trashed"), "undo is a dry run by default")
        self.assertIn("DRY RUN", self.output())

        self.assertEqual(cleanup.run(self.connect, undo_file=self.undo_log, apply=True, out=self.lines.append), 0)
        self.assertEqual([self.status_of(i) for i in (a, b, c)], ["pending", "pending", "pending"])
        restored = self.q("SELECT trashed_at, trashed_by FROM notion_pending_updates WHERE id = %s", (a,))[0]
        self.assertEqual((restored["trashed_at"], restored["trashed_by"]), (None, None))

        self.lines.clear()
        cleanup.run(self.connect, undo_file=self.undo_log, apply=True, out=self.lines.append)
        self.assertIn("0 item(s) restored", self.output())

    def test_undo_skips_items_that_are_no_longer_in_trash(self):
        a, b = self.item("p-1", 1), self.item("p-1", 2)
        self.run_tool(apply=True)
        self.x("UPDATE notion_pending_updates SET status = 'dismissed' WHERE id = %s", (a,))  # changed since

        cleanup.run(self.connect, undo_file=self.undo_log, apply=True, out=self.lines.append)

        self.assertEqual(self.status_of(a), "dismissed")

    # ---- Output ---------------------------------------------------------
    def test_plan_csv_lists_every_pending_item_with_action_and_reason(self):
        keep = self.item("p-new", 3)
        trash = self.item("p-1", 1)
        self.article("p-1", 9)
        self.run_tool()
        rows = {r["item_id"]: r for r in self.plan_rows()}
        self.assertEqual(rows[str(keep)]["action"], "KEEP")
        self.assertEqual((rows[str(trash)]["action"], rows[str(trash)]["rule"]), ("TRASH", "B"))
        self.assertTrue(rows[str(trash)]["reason"])
        self.assertEqual(rows[str(trash)]["article_id"], "1")

    def test_a_missing_notion_table_gives_a_friendly_error(self):
        raw = sqlite3.connect(self.dbfile)
        raw.executescript("DROP TABLE notion_pending_updates")
        raw.close()
        code = self.run_tool()
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", self.output())


if __name__ == "__main__":
    unittest.main()
