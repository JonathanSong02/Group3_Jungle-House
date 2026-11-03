"""Tests for the background 'Check for Updates' run and its status.

Same approach as test_notion_sync_dedupe.py: the real notion_sync_service code runs against SQLite
through that file's MySQL adapter, with the Notion API calls patched out. Real threads are used for
the background run; Events (never sleeps) decide when the fake Notion "finishes".

Not covered (needs a real MySQL): GET_LOCK / IS_FREE_LOCK / TIMESTAMPDIFF behaviour on a real server.

Run (from backend/src):
    python -m unittest test_notion_check_status -v
"""

import json
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import mysql.connector

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_notion_sync_dedupe import SCHEMA, LOCKS_AVAILABLE, _Conn, _LOCKS, page, requests  # noqa: E402
import notion_sync_service as svc  # noqa: E402


def wait_until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class CheckStatusTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.dbfile = str(self.dir / "test.db")
        raw = sqlite3.connect(self.dbfile)
        raw.executescript(SCHEMA)
        raw.close()
        LOCKS_AVAILABLE[0] = True
        _LOCKS.clear()

        self.db = _Conn(self.dbfile)
        self.pages = [page("p-1", "Opening SOP", 1), page("p-2", "Closing SOP", 2), page("p-3", "Notice", 3)]
        self.gate = threading.Event()      # the fake Notion answers only once this is set (when hold_at is set)
        self.entered = threading.Event()   # the run has reached the held step
        self.hold_at = None                # "discover" | "page2" | None
        self.fail_with = None
        self.finished = []

        def discover(_token):
            if self.fail_with:
                raise self.fail_with
            if self.hold_at == "discover":
                self.entered.set()
                self.gate.wait(20)
            return list(self.pages)

        def blocks(_token, page_id):
            if self.hold_at == "page2" and page_id == "p-2":
                self.entered.set()
                self.gate.wait(20)
            return page_id

        patches = (
            patch.object(svc, "get_db_connection", lambda: _Conn(self.dbfile)),
            patch.object(svc, "ensure_notion_sync_tables", lambda cursor: None),
            patch.object(svc, "discover_notion_content", discover),
            patch.object(svc, "fetch_notion_block_children", blocks),
            patch.object(svc, "notion_blocks_to_html", lambda _t, page_id, _f: f"<p>{page_id}</p>"),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.db.close)
        self.addCleanup(self._let_background_runs_finish)

    def _let_background_runs_finish(self):
        self.gate.set()
        wait_until(lambda: not svc._CHECK_RUN_LOCK.locked())

    # ---- helpers -------------------------------------------------------
    def status(self):
        conn = _Conn(self.dbfile)
        try:
            return svc.get_check_status(conn)
        finally:
            conn.close()

    def run_state(self):
        run = self.status()["run"]
        return run["state"] if run else None

    def rows(self):
        cur = self.db.cursor(dictionary=True)
        cur.execute("SELECT * FROM notion_sync_jobs ORDER BY id")
        out = cur.fetchall()
        cur.close()
        return out

    def x(self, sql, params=()):
        cur = self.db.cursor()
        cur.execute(sql, params)
        self.db.commit()
        cur.close()

    def start(self, **kwargs):
        kwargs.setdefault("on_finished", self.finished.append)
        return svc.start_background_check("secret-token-never-stored", 7, self.dir, **kwargs)

    # ---- the main behaviour: start fast, keep running, report the result ---
    def test_start_returns_while_the_sync_is_still_running_and_status_then_reports_the_result(self):
        self.hold_at = "discover"

        outcome = self.start()

        self.assertTrue(outcome["started"])
        self.assertEqual(outcome["outcome"], "started")
        self.assertIsNotNone(outcome["runId"])
        self.assertTrue(self.entered.wait(5))
        self.assertFalse(self.gate.is_set(), "start answered while Notion was still busy")

        run = self.status()["run"]
        self.assertEqual((run["state"], run["trigger"]), ("running", "manual"))
        self.assertIsNone(run["summary"])
        self.assertIsNone(run["finishedAt"])

        self.gate.set()
        self.assertTrue(wait_until(lambda: self.run_state() == "done"))

        run = self.status()["run"]
        self.assertEqual(run["summary"], {"new": 3, "updated": 0, "skipped": 0, "failed": 0, "inaccessible": 0, "failedItems": []})
        self.assertIsNotNone(run["finishedAt"])
        self.assertIsNone(run["errorMessage"])
        self.assertEqual(len(self.finished), 1)
        self.assertEqual(self.finished[0]["status"], "completed")
        self.assertTrue(wait_until(lambda: not svc._CHECK_RUN_LOCK.locked()), "the lock is released when the run ends")

    def test_second_click_while_running_starts_nothing_and_changes_nothing(self):
        self.hold_at = "discover"
        first = self.start()
        self.assertTrue(self.entered.wait(5))

        second = self.start()

        self.assertFalse(second["started"])
        self.assertEqual(second["outcome"], "already_running")
        self.assertEqual(len(self.rows()), 1, "no second run was recorded")
        self.assertEqual(self.status()["run"]["id"], first["runId"])
        self.assertEqual(self.run_state(), "running")

        self.gate.set()
        self.assertTrue(wait_until(lambda: self.run_state() == "done"))
        self.assertEqual(len(self.finished), 1, "only the real run reports back")

    def test_the_automatic_run_counts_as_running_and_blocks_a_manual_start(self):
        self.hold_at = "discover"
        auto = threading.Thread(
            target=lambda: svc.check_for_notion_updates("t", None, self.dir, trigger="auto"), daemon=True)
        auto.start()
        self.assertTrue(self.entered.wait(5))

        run = self.status()["run"]
        self.assertEqual((run["state"], run["trigger"]), ("running", "auto"))
        self.assertFalse(self.start()["started"])

        self.gate.set()
        auto.join(10)
        self.assertEqual(self.status()["run"]["state"], "done")
        self.assertEqual(self.status()["run"]["trigger"], "auto")

    def test_the_result_is_still_there_when_the_manager_comes_back_later(self):
        self.start()
        self.assertTrue(wait_until(lambda: self.run_state() == "done"))

        later = self.status()["run"]  # a brand-new connection = a refreshed page / returning manager

        self.assertEqual(later["state"], "done")
        self.assertEqual(later["summary"]["new"], 3)
        self.assertGreaterEqual(later["finishedAgoSeconds"], 0)

    def test_status_with_no_runs_yet(self):
        self.assertIsNone(self.status()["run"])

    # ---- two managers, automatic vs manual, duplicates ----------------------
    def pending_count(self):
        cur = self.db.cursor(dictionary=True)
        cur.execute("SELECT COUNT(*) AS n FROM notion_pending_updates")
        n = cur.fetchone()["n"]
        cur.close()
        return n

    def test_two_managers_clicking_together_get_one_run_and_see_the_same_status(self):
        self.hold_at = "discover"
        first = svc.start_background_check("t", 7, self.dir, on_finished=self.finished.append)
        self.assertTrue(self.entered.wait(5))

        second = svc.start_background_check("t", 8, self.dir, on_finished=self.finished.append)

        self.assertEqual((first["started"], second["started"]), (True, False))
        self.assertEqual(second["outcome"], "already_running")
        rows = self.rows()
        self.assertEqual(len(rows), 1, "the second manager started nothing")
        self.assertEqual(rows[0]["created_by"], 7)
        self.assertEqual(self.status()["run"]["id"], first["runId"], "manager 8 sees manager 7's run")

        self.gate.set()
        self.assertTrue(wait_until(lambda: self.run_state() == "done"))
        self.assertEqual(self.pending_count(), 3, "one Pending item per page, nothing doubled")
        self.assertEqual(len(self.finished), 1)

    def test_a_manual_run_blocks_the_automatic_one_without_recording_it(self):
        self.hold_at = "discover"
        self.start()
        self.assertTrue(self.entered.wait(5))

        automatic = svc.check_for_notion_updates("t", None, self.dir, trigger="auto")

        self.assertEqual(automatic["status"], "already_running")
        self.assertEqual(len(self.rows()), 1)
        self.gate.set()
        self.assertTrue(wait_until(lambda: self.run_state() == "done"))
        self.assertEqual(self.pending_count(), 3)

    def test_back_to_back_manual_and_automatic_runs_never_duplicate_pending_items(self):
        self.start()
        self.assertTrue(wait_until(lambda: self.run_state() == "done"))
        self.assertTrue(wait_until(lambda: not svc._CHECK_RUN_LOCK.locked()))

        automatic = svc.check_for_notion_updates("t", None, self.dir, trigger="auto")

        self.assertEqual((automatic["new"], automatic["unchanged"]), (0, 3))
        self.assertEqual(self.pending_count(), 3)
        self.assertEqual([r["trigger_source"] for r in self.rows()], ["manual", "auto"])
        self.assertEqual(self.status()["run"]["summary"]["skipped"], 3)

    # ---- failures -------------------------------------------------------
    def test_a_failed_run_shows_a_friendly_message_and_frees_the_lock(self):
        self.fail_with = requests.HTTPError(
            "403 Client Error: Forbidden for url: https://api.notion.com/v1/search?token=secret",
            response=types.SimpleNamespace(status_code=403))

        self.start()
        self.assertTrue(wait_until(lambda: self.run_state() == "failed"))

        run = self.status()["run"]
        self.assertEqual(run["errorMessage"], "Notion connection failed. Check the integration permission.")
        self.assertNotIn("api.notion.com", json.dumps(run))
        self.assertNotIn("secret", json.dumps(run))
        self.assertTrue(wait_until(lambda: not svc._CHECK_RUN_LOCK.locked()))

        self.fail_with = None
        again = self.start()
        self.assertTrue(again["started"], "the button works again after a failure")
        self.assertTrue(wait_until(lambda: self.status()["run"]["id"] == again["runId"] and self.run_state() == "done"))

    def test_a_rejected_token_is_reported_as_reconnect_required(self):
        self.fail_with = svc.NotionAuthError("401 with token abc")
        self.start()
        self.assertTrue(wait_until(lambda: self.run_state() == "failed"))
        run = self.status()["run"]
        self.assertTrue(run["reconnectRequired"])
        self.assertEqual(run["errorMessage"], "Your Notion connection needs to be renewed. Please reconnect Notion.")

    def test_failed_pages_are_kept_with_a_safe_reason(self):
        self.pages = [page("p-1", "Opening SOP", 1), page("p-bad", "Broken page", 2)]
        original = svc.fetch_notion_block_children

        def blocks(token, page_id):
            if page_id == "p-bad":
                raise requests.HTTPError("500 for https://api.notion.com/x", response=types.SimpleNamespace(status_code=500))
            return page_id

        with patch.object(svc, "fetch_notion_block_children", blocks):
            self.start()
            self.assertTrue(wait_until(lambda: self.run_state() == "done"))

        summary = self.status()["run"]["summary"]
        self.assertEqual((summary["new"], summary["failed"]), (1, 1))
        self.assertEqual(summary["failedItems"][0]["title"], "Broken page")
        self.assertIn("500", summary["failedItems"][0]["reason"])
        self.assertNotIn("api.notion.com", json.dumps(self.status()))
        self.assertNotIn("secret-token-never-stored", json.dumps(self.rows(), default=str))
        del original

    def test_a_database_problem_when_starting_is_reported_not_left_hanging(self):
        with patch.object(svc, "get_db_connection", side_effect=mysql.connector.Error(msg="cannot reach db.internal host", errno=2003)):
            began = time.monotonic()
            outcome = self.start()
            elapsed = time.monotonic() - began

        self.assertFalse(outcome["started"])
        self.assertEqual(outcome["outcome"], "failed")
        self.assertEqual(outcome["message"], "The database is unavailable right now. Please try again.")
        self.assertNotIn("db.internal", json.dumps(outcome))
        self.assertLess(elapsed, 5)
        self.assertTrue(wait_until(lambda: not svc._CHECK_RUN_LOCK.locked()))

    def test_the_lock_is_released_even_if_the_finish_callback_raises(self):
        def explode(_result):
            raise RuntimeError("notification system down")

        self.start(on_finished=explode)
        self.assertTrue(wait_until(lambda: self.run_state() == "done"))
        self.assertTrue(wait_until(lambda: not svc._CHECK_RUN_LOCK.locked()))
        self.assertTrue(self.start()["started"])

    # ---- progress and heartbeat ----------------------------------------
    def test_progress_and_a_fresh_heartbeat_are_visible_while_pages_are_processed(self):
        self.hold_at = "page2"
        with patch.object(svc, "CHECK_HEARTBEAT_EVERY_SECONDS", 0):
            self.start()
            self.assertTrue(self.entered.wait(5))

            run = self.status()["run"]
            self.assertEqual(run["state"], "running")
            self.assertEqual(run["progress"]["total"], 3)
            self.assertGreaterEqual(run["progress"]["processed"], 1)
            self.assertLessEqual(run["secondsSinceHeartbeat"], 5)

            self.gate.set()
            self.assertTrue(wait_until(lambda: self.run_state() == "done"))

    # ---- runs that died -------------------------------------------------
    def _orphan(self, started_minutes_ago, heartbeat_minutes_ago):
        self.x(
            "INSERT INTO notion_sync_jobs (status, trigger_source, started_at, last_heartbeat) "
            "VALUES ('running', 'manual', datetime('now', %s), datetime('now', %s))",
            (f"-{started_minutes_ago} minutes", f"-{heartbeat_minutes_ago} minutes"))

    def test_a_run_whose_process_was_killed_does_not_stay_running_forever(self):
        self._orphan(started_minutes_ago=30, heartbeat_minutes_ago=20)

        run = self.status()["run"]

        self.assertEqual(run["state"], "failed")
        self.assertTrue(run["stale"])
        self.assertEqual(run["errorMessage"], svc.STALE_RUN_MESSAGE)
        row = self.rows()[0]
        self.assertEqual(row["status"], "failed")
        self.assertIsNotNone(row["completed_at"])
        self.assertEqual(self.status()["run"]["state"], "failed", "and it stays settled on the next look")

    def test_a_recent_heartbeat_is_never_stale_even_when_nothing_holds_the_lock(self):
        self._orphan(started_minutes_ago=1, heartbeat_minutes_ago=0)
        run = self.status()["run"]
        self.assertEqual((run["state"], run["stale"]), ("running", False))

    def test_without_the_lock_a_few_quiet_minutes_are_enough_to_call_it_dead(self):
        self._orphan(started_minutes_ago=10, heartbeat_minutes_ago=3)
        self.assertEqual(self.status()["run"]["state"], "failed")

    def test_with_the_lock_held_elsewhere_the_same_quiet_run_is_still_running(self):
        self._orphan(started_minutes_ago=10, heartbeat_minutes_ago=3)
        holder = _Conn(self.dbfile)
        cur = holder.cursor()
        cur.execute("SELECT GET_LOCK(%s, 0)", (svc._DB_CHECK_LOCK_NAME,))
        cur.fetchone()
        try:
            self.assertEqual(self.status()["run"]["state"], "running")
        finally:
            holder.close()

    def test_a_new_run_settles_leftovers_from_a_dead_process(self):
        self._orphan(started_minutes_ago=2, heartbeat_minutes_ago=0)  # fresh-looking, but its process is gone

        outcome = self.start()
        self.assertTrue(outcome["started"])
        self.assertTrue(wait_until(lambda: self.run_state() == "done"))

        states = [(r["id"], r["status"]) for r in self.rows()]
        self.assertEqual(states[0], (1, "failed"))
        self.assertEqual(states[1], (2, "completed"))

    def test_another_process_holding_the_lock_refuses_the_start_without_a_run_record(self):
        holder = _Conn(self.dbfile)
        cur = holder.cursor()
        cur.execute("SELECT GET_LOCK(%s, 0)", (svc._DB_CHECK_LOCK_NAME,))
        cur.fetchone()
        try:
            outcome = self.start()
        finally:
            holder.close()

        self.assertFalse(outcome["started"])
        self.assertEqual(outcome["outcome"], "already_running")
        self.assertEqual(self.rows(), [])
        self.assertTrue(wait_until(lambda: not svc._CHECK_RUN_LOCK.locked()))
        self.assertTrue(self.start()["started"], "works once the other process is done")

    # ---- tables not migrated yet ---------------------------------------
    def test_status_creates_missing_columns_instead_of_failing(self):
        ensured = []

        class Flaky:
            """First read of the jobs table fails like MySQL does when the new columns are missing."""
            def __init__(self, cursor):
                self.cursor, self.failed = cursor, False

            def execute(self, sql, params=()):
                if "FROM notion_sync_jobs" in sql and not ensured and not self.failed:
                    self.failed = True
                    raise mysql.connector.ProgrammingError(msg="Unknown column 'last_heartbeat'", errno=1054)
                return self.cursor.execute(sql, params)

            def __getattr__(self, name):
                return getattr(self.cursor, name)

        class FlakyConn:
            def __init__(self, conn):
                self.conn = conn

            def cursor(self, **kwargs):
                return Flaky(self.conn.cursor(**kwargs))

            def __getattr__(self, name):
                return getattr(self.conn, name)

        conn = _Conn(self.dbfile)
        with patch.object(svc, "ensure_notion_sync_tables", lambda cursor: ensured.append(1)):
            result = svc.get_check_status(FlakyConn(conn))
        conn.close()
        self.assertEqual(ensured, [1])
        self.assertIsNone(result["run"])

    def test_a_status_poll_does_not_run_the_full_table_setup_every_time(self):
        calls = []
        with patch.object(svc, "ensure_notion_sync_tables", lambda cursor: calls.append(1)):
            for _ in range(5):
                self.status()
        self.assertEqual(calls, [], "polling must stay cheap")


if __name__ == "__main__":
    unittest.main()
