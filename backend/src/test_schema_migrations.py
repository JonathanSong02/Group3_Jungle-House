"""Schema versioning tests: the migration runner, the baseline, the drift check and the snapshot tool.

No MySQL server and no network. The runner is exercised against an in-memory database (MemoryBackend)
and, for the ledger and lock SQL, against SQLite through a tiny adapter. The snapshot tool is run
against a fake connection that answers like INFORMATION_SCHEMA and records every statement it receives.

Not covered here (needs a real MySQL server): the MySQL-specific DDL actually being accepted, and a
from-scratch build. See docs/database-schema.md ("Testing on a scratch MySQL").

Run (from backend/src):
    python -m unittest test_schema_migrations -v
"""

import ast
import contextlib
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import mysql.connector

SRC_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SRC_DIR.parent
REPO_DIR = BACKEND_DIR.parent
TOOLS_DIR = BACKEND_DIR / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import migrate  # noqa: E402
import migration_lib as ml  # noqa: E402
import schema_lib as sl  # noqa: E402
import schema_snapshot  # noqa: E402

HEADER = "from migration_lib import CURRENT_TIMESTAMP, col, fk, index, unique\n\n\n"


def write_migrations(directory, files):
    for name, body in files.items():
        Path(directory, name).write_bytes((HEADER + body).encode("utf-8"))
    return directory


M1 = """def upgrade(ctx):
    ctx.create_table("shop", [col("shop_id", "INT", null=False, auto_increment=True), col("name", "VARCHAR(50)", null=False)],
                     primary_key="shop_id")
    ctx.create_table("item", [col("item_id", "INT", null=False, auto_increment=True), col("shop_id", "INT", null=False)],
                     primary_key="item_id", foreign_keys=[fk("shop_id", "shop", "shop_id", on_delete="CASCADE", name="fk_item_shop")])
"""
M2 = """def upgrade(ctx):
    ctx.add_column("item", col("price", "DECIMAL(8,2)", null=False, default=0))
    ctx.add_index("item", unique("shop_id", "price", name="uq_item_shop_price"))
    ctx.create_table("tag", [col("tag_id", "INT", null=False, auto_increment=True), col("label", "VARCHAR(30)")], primary_key="tag_id")
"""


class TempMigrations(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.backends = []
        self.addCleanup(lambda: [b.close() for b in self.backends])

    def backend(self, **kwargs):
        backend = ml.MemoryBackend(**kwargs)
        self.backends.append(backend)
        return backend

    def migrations(self, files=None):
        write_migrations(self.dir, {"0001_shop.py": M1, "0002_prices.py": M2} if files is None else files)
        return ml.load_migrations(self.dir)


# --------------------------------------------------------------------------
# Test 2 - the runner
# --------------------------------------------------------------------------
class RunnerTests(TempMigrations):
    def test_applies_pending_in_order_and_records_each_one(self):
        migrations, db = self.migrations(), self.backend()
        results = ml.apply_migrations(db, migrations)
        self.assertEqual([r.migration.version for r in results], ["0001", "0002"])
        self.assertEqual([r["version"] for r in db.ledger_rows()], ["0001", "0002"])
        self.assertEqual(db.ledger_rows()[0]["checksum"], migrations[0].checksum)
        self.assertEqual(set(db.schema.tables), {"shop", "item", "tag"})
        self.assertIn("price", db.schema.get("item").columns)

    def test_running_twice_does_nothing_the_second_time(self):
        migrations, db = self.migrations(), self.backend()
        ml.apply_migrations(db, migrations)
        executed = list(db.executed)
        self.assertEqual(ml.apply_migrations(db, migrations), [])
        self.assertEqual(db.executed, executed)

    def test_migration_is_safe_to_run_again_even_without_a_ledger_entry(self):
        migrations, db = self.migrations(), self.backend()
        ml.apply_migrations(db, migrations)
        db.ledger = []                                    # as if recording had been lost
        results = ml.apply_migrations(db, migrations)
        statuses = {s.status for r in results for s in r.steps}
        self.assertEqual(statuses, {"exists"})            # nothing was executed again
        self.assertEqual(len(db.ledger_rows()), 2)

    def test_dry_run_changes_nothing_and_shows_the_sql(self):
        migrations, db = self.migrations(), self.backend()
        results = ml.apply_migrations(db, migrations, dry_run=True)
        self.assertEqual(db.executed, [])
        self.assertIsNone(db.ledger)
        self.assertEqual(db.schema.tables, {})
        steps = [s for r in results for s in r.steps]
        self.assertTrue(all(s.status == "would" for s in steps))
        self.assertTrue(any(s.sql.startswith("CREATE TABLE IF NOT EXISTS `shop`") for s in steps))
        # a later migration is planned against what the earlier one WOULD have created
        self.assertTrue(any("ADD COLUMN `price`" in s.sql for s in steps))

    def test_only_additive_statements_exist(self):
        for sql in ("DROP TABLE users", "ALTER TABLE `a` DROP COLUMN `b`", "ALTER TABLE `a` MODIFY COLUMN `b` INT",
                    "ALTER TABLE `a` RENAME TO `c`", "DELETE FROM `a`", "TRUNCATE TABLE `a`", "UPDATE `a` SET b = 1"):
            with self.assertRaises(ml.MigrationError):
                ml.assert_additive(sql)
        ctx = ml.Context(sl.Schema())
        for name in ("drop_table", "drop_column", "rename_table", "modify_column", "execute", "sql", "truncate"):
            self.assertFalse(hasattr(ctx, name), name)
        everything = sl.Schema()
        ml.replay(self.migrations())
        for step in ml.Context(everything).steps:
            ml.assert_additive(step.sql)

    def test_add_column_rules(self):
        db = self.backend()
        ctx = ml.Context(db.schema, db)
        ctx.create_table("t", [col_("id")], primary_key="id")
        with self.assertRaisesRegex(ml.MigrationError, "NOT NULL: give it a default"):
            ctx.add_column("t", ml.col("flag", "INT", null=False))
        with self.assertRaisesRegex(ml.MigrationError, "does not exist yet"):
            ctx.add_column("nope", ml.col("flag", "INT"))
        with self.assertRaisesRegex(ml.MigrationError, "unsupported type"):
            ml.col("x", "INT); DROP TABLE t; --")
        with self.assertRaises(sl.SchemaToolError):
            ml.col("bad name", "INT")

    def test_foreign_key_needs_its_parent_first(self):
        ctx = ml.Context(sl.Schema())
        with self.assertRaisesRegex(ml.MigrationError, "does not exist yet"):
            ctx.create_table("child", [col_("id"), ml.col("p", "INT")], primary_key="id",
                             foreign_keys=[ml.fk("p", "parent", "id")])

    def test_files_must_be_numbered_without_gaps(self):
        write_migrations(self.dir, {"0001_a.py": M1, "0003_c.py": M2})
        with self.assertRaisesRegex(ml.MigrationError, "without gaps"):
            ml.load_migrations(self.dir)
        (self.dir / "0003_c.py").unlink()
        (self.dir / "extra.py").write_text("x = 1\n")
        with self.assertRaisesRegex(ml.MigrationError, "must be named like"):
            ml.load_migrations(self.dir)


def col_(name):
    return ml.col(name, "INT", null=False, auto_increment=True)


# --------------------------------------------------------------------------
# Test 3 - checksums
# --------------------------------------------------------------------------
class ChecksumTests(TempMigrations):
    def test_changed_file_is_detected_and_blocks_apply(self):
        migrations, db = self.migrations(), self.backend()
        ml.apply_migrations(db, migrations)
        (self.dir / "0002_prices.py").write_bytes((HEADER + M2 + "# edited later\n").encode())
        changed = ml.load_migrations(self.dir)
        status = ml.classify(changed, db.ledger_rows())
        self.assertEqual(status.problems, ["Migration 0002 has changed since it was applied."])
        with self.assertRaisesRegex(ml.MigrationError, "Migration 0002 has changed since it was applied. Nothing was run."):
            ml.apply_migrations(db, changed)

    def test_line_endings_do_not_change_the_checksum(self):
        write_migrations(self.dir, {"0001_shop.py": M1})
        lf = ml.file_checksum(self.dir / "0001_shop.py")
        (self.dir / "0001_shop.py").write_bytes((HEADER + M1).replace("\n", "\r\n").encode())
        self.assertEqual(ml.file_checksum(self.dir / "0001_shop.py"), lf)

    def test_recorded_but_missing_file_and_out_of_order_are_reported(self):
        migrations, db = self.migrations(), self.backend()
        ml.apply_migrations(db, migrations)
        status = ml.classify(migrations[:1], db.ledger_rows())
        self.assertIn("Migration 0002 is recorded as applied but its file is missing.", status.problems)
        status = ml.classify(migrations, [dict(db.ledger_rows()[1])])
        self.assertIn("Migration 0001 is not applied but a later migration is.", status.problems)


# --------------------------------------------------------------------------
# Test 4 - a migration that stops half-way
# --------------------------------------------------------------------------
class HalfWayFailureTests(TempMigrations):
    def test_failure_is_not_recorded_and_rerun_finishes_the_job(self):
        migrations = self.migrations()
        db = self.backend(fail_on="add column item.price")
        with self.assertRaises(ml.MigrationError) as raised:
            ml.apply_migrations(db, migrations)
        message = str(raised.exception)
        self.assertIn("Migration 0002 (prices) stopped", message)
        self.assertIn("NOT recorded as applied", message)
        self.assertNotIn("DECIMAL", message)                       # no SQL text in the message
        self.assertEqual([r["version"] for r in db.ledger_rows()], ["0001"])
        self.assertIsNone(db.schema.get("item").columns.get("price"))
        self.assertIsNone(db.schema.get("tag"))                    # steps after the failure did not run

        db.fail_on = None                                          # the cause is fixed
        results = ml.apply_migrations(db, migrations)
        self.assertEqual([r.migration.version for r in results], ["0002"])
        self.assertEqual([r["version"] for r in db.ledger_rows()], ["0001", "0002"])
        self.assertIn("price", db.schema.get("item").columns)

    def test_part_of_a_migration_that_already_ran_is_not_repeated(self):
        migrations = self.migrations()
        db = self.backend(fail_on="add unique index item.uq_item_shop_price")
        with self.assertRaises(ml.MigrationError):
            ml.apply_migrations(db, migrations)
        done_before = len(db.executed)
        db.fail_on = None
        results = ml.apply_migrations(db, migrations)
        steps = {s.label: s.status for s in results[0].steps}
        self.assertEqual(steps["add column item.price"], "exists")     # finished last time: skipped, not repeated
        self.assertEqual(steps["add unique index item.uq_item_shop_price"], "done")
        self.assertEqual(len(db.executed), done_before + 2)            # the index and the new table only

    def test_a_table_the_app_created_in_the_meantime_is_not_a_failure(self):
        db = self.backend()
        original = db.run

        def racing_run(op):
            if op.label == "create table tag":
                raise ml.SqlFailure(1050)           # "table already exists"
            original(op)

        db.run = racing_run
        results = ml.apply_migrations(db, self.migrations())
        self.assertEqual({s.label: s.status for s in results[1].steps}["create table tag"], "exists")

    def test_error_messages_never_contain_row_values_or_sql(self):
        text = sl.describe_sql_error(mysql.connector.Error(msg="Duplicate entry 'a@b.com' for key 'email'", errno=1062))
        self.assertNotIn("a@b.com", text)
        self.assertIn("1062", text)


# --------------------------------------------------------------------------
# Test 5 - the lock
# --------------------------------------------------------------------------
class LockTests(TempMigrations):
    def test_second_runner_is_refused_and_changes_nothing(self):
        migrations = self.migrations()
        first, second = self.backend(), self.backend()
        self.assertTrue(first.lock())
        with self.assertRaisesRegex(ml.MigrationError, "Another migration runner is already running."):
            ml.apply_migrations(second, migrations)
        with self.assertRaisesRegex(ml.MigrationError, "Another migration runner is already running."):
            ml.baseline_database(second, migrations)
        self.assertEqual(second.executed, [])
        first.unlock()
        self.assertEqual(len(ml.apply_migrations(second, migrations)), 2)

    def test_lock_is_released_after_a_failure(self):
        db = self.backend(fail_on="create table shop")
        with self.assertRaises(ml.MigrationError):
            ml.apply_migrations(db, self.migrations())
        self.assertTrue(self.backend().lock())

    def test_mysql_backend_lock_and_ledger_sql_work_against_sqlite(self):
        raw = _SqliteConn()
        first, second = SqliteLedgerBackend(raw), SqliteLedgerBackend(_SqliteConn())
        self.assertTrue(first.lock())
        self.assertFalse(second.lock())
        first.unlock()
        self.assertTrue(second.lock())
        second.unlock()

        self.assertFalse(first.ledger_exists())
        first.ledger_create()
        self.assertTrue(first.ledger_exists())
        first.ledger_add("0001", "baseline", "ab" * 32)
        rows = first.ledger_rows()
        self.assertEqual([(r["version"], r["name"], r["checksum"]) for r in rows], [("0001", "baseline", "ab" * 32)])
        with self.assertRaises(Exception):
            first.ledger_add("0001", "baseline", "cd" * 32)            # a version can only be recorded once
        self.assertTrue(rows[0]["applied_at"])


class _SqliteConn:
    _held = {}

    def __init__(self):
        self.raw = sqlite3.connect(":memory:", check_same_thread=False)
        self.mine = set()

    def cursor(self, dictionary=False, **_):
        return _SqliteCursor(self, dictionary)

    def commit(self):
        self.raw.commit()

    def close(self):
        for name in list(self.mine):
            _SqliteConn._held.pop(name, None)
        self.raw.close()


class _SqliteCursor:
    def __init__(self, conn, dictionary):
        self.conn, self.dictionary, self.cur, self.synthetic = conn, dictionary, conn.raw.cursor(), None

    def execute(self, sql, params=()):
        text = " ".join(sql.split())
        lock = re.match(r"SELECT (GET_LOCK|RELEASE_LOCK)\(%s(?:, \d+)?\) AS (\w+)$", text)
        if lock:
            name, held = params[0], _SqliteConn._held
            if lock.group(1) == "GET_LOCK":
                got = 1 if held.get(name, self.conn) is self.conn else 0
                if got:
                    held[name] = self.conn
                    self.conn.mine.add(name)
            else:
                got = 1 if held.get(name) is self.conn else None
                if got:
                    del held[name]
            self.synthetic = ([lock.group(2)], [(got,)])
            return
        self.synthetic = None
        self.cur.execute(text.replace("%s", "?"), tuple(params))

    def _names(self):
        return self.synthetic[0] if self.synthetic else [c[0] for c in self.cur.description or []]

    def fetchall(self):
        rows = self.synthetic[1] if self.synthetic else self.cur.fetchall()
        return [dict(zip(self._names(), r)) if self.dictionary else r for r in rows]

    def close(self):
        self.cur.close()


class SqliteLedgerBackend(ml.MySQLBackend):
    """MySQLBackend with the two MySQL-only statements (information_schema, ENGINE=) swapped for SQLite ones."""

    def ledger_exists(self):
        cur = self.conn.raw.cursor()
        cur.execute("SELECT 1 FROM sqlite_master WHERE name = 'schema_migrations'")
        return cur.fetchone() is not None

    def ledger_create(self):
        self.conn.raw.execute("CREATE TABLE schema_migrations (version TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL, "
                              "checksum TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")


# --------------------------------------------------------------------------
# Test 6 - baseline on an existing database
# --------------------------------------------------------------------------
class BaselineTests(TempMigrations):
    def existing_database(self):
        migrations = self.migrations({"0001_shop.py": M1})
        db = self.backend(schema=ml.replay(migrations))
        return migrations, db

    def test_matching_database_gets_only_the_ledger_row(self):
        migrations, db = self.existing_database()
        before = db.schema.copy()
        first, differences = ml.baseline_database(db, migrations)
        self.assertEqual((first.version, differences), ("0001", []))
        self.assertEqual(db.executed, [ml.LEDGER_DDL])               # the one and only statement
        self.assertEqual(sl.compare(before, db.schema), [])
        self.assertEqual(sl.compare(db.schema, before), [])
        self.assertEqual([r["version"] for r in db.ledger_rows()], ["0001"])
        self.assertEqual(ml.apply_migrations(db, migrations), [])    # and it counts as applied

    def test_mismatch_stops_and_lists_every_difference_and_changes_nothing(self):
        migrations, db = self.existing_database()
        del db.schema.get("item").columns["shop_id"]
        db.schema.get("item").foreign_keys.clear()
        del db.schema.tables["shop"]
        with self.assertRaises(ml.BaselineMismatch) as raised:
            ml.baseline_database(db, migrations)
        self.assertIn("Schema differs from the baseline", str(raised.exception))
        kinds = {d.kind for d in raised.exception.differences}
        self.assertTrue({"missing_table", "missing_column", "missing_foreign_key"} <= kinds)
        self.assertEqual(db.executed, [])
        self.assertIsNone(db.ledger)

    def test_extra_things_need_an_explicit_ok(self):
        migrations, db = self.existing_database()
        db.schema.tables["mystery"] = sl.Table("mystery")
        with self.assertRaisesRegex(ml.BaselineMismatch, "--accept-extras"):
            ml.baseline_database(db, migrations)
        self.assertIsNone(db.ledger)
        _, differences = ml.baseline_database(db, migrations, accept_extras=True)
        self.assertEqual([d.kind for d in differences], ["extra_table"])
        self.assertEqual(db.executed, [ml.LEDGER_DDL])

    def test_empty_database_is_not_a_baseline_candidate(self):
        migrations = self.migrations({"0001_shop.py": M1})
        with self.assertRaises(ml.BaselineMismatch):
            ml.baseline_database(self.backend(), migrations)

    def test_baseline_refuses_when_records_already_exist(self):
        migrations, db = self.existing_database()
        ml.baseline_database(db, migrations)
        with self.assertRaisesRegex(ml.MigrationError, "already has migration records"):
            ml.baseline_database(db, migrations)

    def test_apply_on_a_database_without_records_asks_for_baseline(self):
        migrations, db = self.existing_database()
        with self.assertRaisesRegex(ml.MigrationError, "Run `baseline`"):
            ml.apply_migrations(db, migrations)
        self.assertEqual(db.executed, [])
        results = ml.apply_migrations(db, migrations, adopt_existing=True)
        self.assertEqual({s.status for r in results for s in r.steps}, {"exists"})

    def test_apply_builds_the_whole_schema_on_an_empty_database(self):
        migrations = ml.load_migrations()                              # the real migration files
        db = self.backend()
        ml.apply_migrations(db, migrations)
        self.assertEqual(sl.compare(ml.replay(migrations), db.schema), [])
        self.assertEqual(len(db.schema.tables), 36)                   # every table production has


# --------------------------------------------------------------------------
# Test 7 - drift detection
# --------------------------------------------------------------------------
class DriftTests(unittest.TestCase):
    def setUp(self):
        self.expected = ml.replay(ml.load_migrations())

    def kinds(self, actual):
        return {(d.severity, d.kind, d.table) for d in sl.compare(self.expected, actual)}

    def test_identical_schema_has_no_differences(self):
        self.assertEqual(sl.compare(self.expected, self.expected.copy()), [])

    def test_each_kind_of_drift_is_reported(self):
        actual = self.expected.copy()
        del actual.tables["chat_cancelled_requests"]
        del actual.get("users").columns["email"]
        actual.get("users").columns["role_id"].type = "bigint"
        actual.get("wiki_article").indexes[:] = [i for i in actual.get("wiki_article").indexes if not i.unique]
        actual.get("password_reset_tokens").foreign_keys.clear()
        actual.get("quiz").columns["extra_note"] = sl.Column("extra_note", "text")
        actual.tables["stray"] = sl.Table("stray")
        actual.get("escalation").foreign_keys[0].on_delete = "CASCADE"
        found = self.kinds(actual)
        for expected in [
            ("error", "missing_table", "chat_cancelled_requests"),
            ("error", "missing_column", "users"),
            ("error", "type_mismatch", "users"),
            ("error", "missing_unique_index", "wiki_article"),
            ("error", "missing_foreign_key", "password_reset_tokens"),
            ("warning", "extra_column", "quiz"),
            ("warning", "extra_table", "stray"),
            ("error", "fk_rule_mismatch", "escalation"),
        ]:
            self.assertIn(expected, found)

    def test_the_unique_notion_index_and_the_three_job_columns_are_checked(self):
        actual = self.expected.copy()
        actual.get("wiki_article").indexes[:] = []
        for name in ("last_heartbeat", "trigger_source", "details"):
            del actual.get("notion_sync_jobs").columns[name]
        details = [str(d) for d in sl.compare(self.expected, actual)]
        self.assertIn("[ERROR  ] wiki_article: missing unique index on (notion_page_id) (idx_wiki_article_notion_page_id)", details)
        for name in ("last_heartbeat", "trigger_source", "details"):
            self.assertTrue(any(f"notion_sync_jobs: missing column {name}" in d for d in details), name)

    def test_bookkeeping_table_is_not_drift(self):
        actual = self.expected.copy()
        actual.tables["schema_migrations"] = sl.Table("schema_migrations")
        self.assertEqual(sl.compare(self.expected, actual), [])

    def test_harmless_mysql_spellings_are_not_drift(self):
        actual = self.expected.copy()
        actual.get("ai_chat_log").columns["score"].default = "0.0000"                 # DECIMAL(6,4) DEFAULT 0
        actual.get("users").columns["user_id"].type = "int(11)"                       # MySQL 5.7 display width
        actual.get("notification").columns["is_read"].type = "tinyint(1)"             # BOOLEAN
        actual.get("users").columns["created_at"].default = sl.Expr("current_timestamp()")   # MariaDB
        self.assertEqual(sl.compare(self.expected, actual), [])

    def test_check_report_uses_only_applied_migrations(self):
        migrations = ml.load_migrations()
        report = ml.check_schema(migrations, self.expected.copy(), [])
        self.assertEqual(report.scope, ["0001"])
        self.assertTrue(report.notes)
        ledger = [{"version": "0001", "name": "baseline", "checksum": migrations[0].checksum, "applied_at": "x"}]
        report = ml.check_schema(migrations, self.expected.copy(), ledger)
        self.assertEqual((report.errors(), report.status.problems), ([], []))


# --------------------------------------------------------------------------
# Test 1 - inventory: every DDL statement in the repo is in the baseline (or is a known exception)
# --------------------------------------------------------------------------
# Tables the code queries that production does NOT have. The query fails and the code falls back (try/except).
# Listed so that a NEW such table is noticed. Production is not changed for them.
CODE_USES_BUT_PRODUCTION_LACKS = {"ai_response": "dashboard AI accuracy (app.py get_dashboard): wrapped in try/except, shows 0%"}
# Older local copies of schema scripts (database jungle_house_ai); superseded by the scripts next to them.
OLD_SCRIPTS = {"command file.sql", "JH.database.sql"}
# (table, column) whose type the script gives differently from what the app turns it into at runtime.
RUNTIME_WIDENED = {("wiki_article", "content")}
# A string that really is a query (not a print message that happens to start with UPDATE).
SQL_START = re.compile(r"^\s*(SELECT\b.*\bFROM\b|INSERT\s+(IGNORE\s+)?INTO\b|UPDATE\s+`?\w+`?\s+(SET|AS|\w+\s+SET)\b|"
                       r"DELETE\s+FROM\b|REPLACE\s+INTO\b|WITH\b)", re.I | re.S)


def split_top(text):
    parts, depth, quote, current = [], 0, False, []
    for ch in text:
        if ch == "'":
            quote = not quote
        if not quote:
            depth += ch == "("
            depth -= ch == ")"
            if ch == "," and depth == 0:
                parts.append("".join(current).strip())
                current = []
                continue
        current.append(ch)
    if "".join(current).strip():
        parts.append("".join(current).strip())
    return parts


def parse_columns(text):
    """('a, b') -> ('a', 'b')"""
    return tuple(c.strip(" `").lower() for c in text.split(","))


def parse_column(item):
    match = re.match(r"^`?(\w+)`?\s+(.*)$", item, re.S)
    name, rest = match.group(1), " ".join(match.group(2).split())
    type_ = re.match(r"^([A-Za-z]+(?:\s*\((?:[^()']|'[^']*')*\))?(?:\s+UNSIGNED)?)", rest, re.I).group(1)
    flags = rest[len(type_):]
    default = None
    found = re.search(r"DEFAULT\s+('(?:[^']|'')*'|-?\d+(?:\.\d+)?|[A-Za-z_]+(?:\(\d*\))?)", flags, re.I)
    if found:
        default = {"FALSE": "0", "TRUE": "1", "NULL": None}.get(found.group(1).upper(), found.group(1))
    on_update = re.search(r"ON UPDATE\s+(\w+)", flags, re.I)
    primary = bool(re.search(r"\bPRIMARY KEY\b", flags, re.I))
    column = sl.Column(name, type_.strip(), not (primary or re.search(r"\bNOT NULL\b", flags, re.I)), default,
                       bool(re.search(r"\bAUTO_INCREMENT\b", flags, re.I)), sl.Expr(on_update.group(1)) if on_update else None)
    return column, primary, bool(re.search(r"\bUNIQUE\b", flags, re.I))


def parse_create_table(sql):
    """-> (name, columns, [(kind, cols, ...)]) where kind is primary / unique / index / fk."""
    sql = " ".join(sql.split())
    head = re.match(r"^CREATE TABLE (?:IF NOT EXISTS )?`?(\w+)`? \((.*)\)\s*(?:ENGINE.*)?$", sql, re.I)
    name, body = head.group(1), head.group(2)
    columns, keys = [], []
    for item in split_top(body):
        upper = item.upper()
        if upper.startswith("PRIMARY KEY"):
            keys.append(("primary", parse_columns(re.search(r"\((.*)\)", item).group(1))))
        elif re.match(r"^(UNIQUE|KEY|INDEX)\b", upper) or upper.startswith("UNIQUE"):
            cols = parse_columns(re.search(r"\(([^)]*)\)\s*$", item).group(1))
            keys.append(("unique" if upper.startswith("UNIQUE") else "index", cols))
        elif "FOREIGN KEY" in upper:
            m = re.search(r"FOREIGN KEY\s*\(([^)]*)\)\s*REFERENCES\s+`?(\w+)`?\s*\(([^)]*)\)(.*)$", item, re.I)
            rule = re.search(r"ON DELETE\s+(SET NULL|CASCADE|RESTRICT|NO ACTION)", m.group(4), re.I)
            keys.append(("fk", parse_columns(m.group(1)), m.group(2).lower(), parse_columns(m.group(3)),
                         rule.group(1).upper() if rule else None))
        else:
            column, primary, uniq = parse_column(item)
            columns.append(column)
            if primary:
                keys.append(("primary", (column.name.lower(),)))
            if uniq:
                keys.append(("unique", (column.name.lower(),)))
    return name, columns, keys


def parse_alter(sql):
    """-> (table, [(action, payload)]) for ADD [COLUMN] / MODIFY COLUMN / ADD [UNIQUE] INDEX."""
    sql = " ".join(sql.split()).rstrip(";")
    head = re.match(r"^ALTER TABLE `?(\w+)`?\s+(.*)$", sql, re.I)
    actions = []
    for item in split_top(head.group(2)):
        unique_index = re.match(r"^ADD (UNIQUE )?(?:INDEX|KEY)\s+(?:`?\w+`?\s+)?\(([^)]*)\)", item, re.I)
        modify = re.match(r"^MODIFY COLUMN\s+(.*)$", item, re.I)
        add = re.match(r"^ADD (?:COLUMN )?(.*)$", item, re.I)
        if unique_index:
            actions.append(("index", (bool(unique_index.group(1)), parse_columns(unique_index.group(2)))))
        elif modify:
            actions.append(("column", parse_column(re.sub(r"\s+AFTER\s+\w+$", "", modify.group(1)))[0]))
        elif add:
            actions.append(("column", parse_column(re.sub(r"\s+AFTER\s+\w+$", "", add.group(1)))[0]))
    return head.group(1).lower(), actions


def code_strings():
    for path in sorted(SRC_DIR.glob("*.py")):
        if path.name.startswith("test_"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield path.name, node.value
            elif isinstance(node, ast.JoinedStr):
                yield path.name, "".join(v.value if isinstance(v, ast.Constant) else "{..}" for v in node.values)


def script_statements():
    for path in sorted((REPO_DIR / "mysql").glob("*.sql")):
        if path.name in OLD_SCRIPTS:
            continue
        text = re.sub(r"/\*.*?\*/", " ", path.read_text(encoding="utf-8"), flags=re.S)
        text = "\n".join(re.sub(r"(--|#).*$", "", line) for line in text.splitlines())
        for match in re.finditer(r"CREATE TABLE (?:IF NOT EXISTS )?`?\w+`? \(", text, re.I):
            depth, quote, i = 1, False, match.end()
            while depth and i < len(text):
                quote ^= text[i] == "'"
                depth += (not quote) * ((text[i] == "(") - (text[i] == ")"))
                i += 1
            tail = re.match(r"\s*(ENGINE[^;]*)?", text[i:]).group(0)
            yield path.name, text[match.start():i] + tail
        for match in re.finditer(r"ALTER TABLE\s+\w+\s+ADD\s+[^;]+;", text, re.I):
            yield path.name, match.group(0)


# Where the old SQL scripts in mysql/ disagree with PRODUCTION (the baseline). Production wins: the scripts are
# older than the live database. A new disagreement fails the test so it gets looked at.
SCRIPT_DIFFERS_FROM_PRODUCTION = {
    "escalation index on status": "mysql/escalation.sql idx_status: missing in production (migration 0002 can add it)",
    "escalation index on created_at": "mysql/escalation.sql idx_created_at: missing in production (migration 0002 can add it)",
    "login_history.user_id nullability": "mysql/Query1.sql: NOT NULL, production allows NULL (failed logins for unknown emails)",
    "notification.message missing": "mysql/notification.sql: production calls the column detail",
    "notification.user_id nullability": "mysql/notification.sql: NOT NULL, production allows NULL (role-wide notifications)",
    "notification.user_id foreign key": "mysql/notification.sql: production has no foreign key on user_id",
    "notification.type type": "mysql/notification.sql: production has a wider ENUM",
    "review_queue.status type": "mysql/review queue.sql: ENUM, production has VARCHAR(30)",
    "users.status type": "mysql/Query1.sql: ENUM('active','inactive'), production adds pending and declined",
    "users.status default": "mysql/Query1.sql: default 'active', production defaults to 'pending'",
}


class InventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrations = ml.load_migrations()
        cls.expected = ml.replay(migrations)             # 0001 + every later migration
        cls.baseline = ml.replay(migrations[:1])         # 0001 only = production as it is today

    def problems(self, name, columns, keys, schema=None):
        """What differs between a parsed CREATE/ALTER and the schema, as short ids like 'users.status type'."""
        table = (schema or self.expected).get(name)
        if table is None:
            return [f"{name} table missing"]
        found = []
        for column in columns:
            have = table.columns.get(column.name.lower())
            where = f"{name}.{column.name}"
            if have is None:
                found.append(f"{where} missing")
                continue
            if (name, column.name.lower()) not in RUNTIME_WIDENED and \
                    sl.normalize_type(have.type) != sl.normalize_type(column.type):
                found.append(f"{where} type")
            if have.nullable != column.nullable:
                found.append(f"{where} nullability")
            if sl.normalize_default(have.default) != sl.normalize_default(column.default):
                found.append(f"{where} default")
            if have.auto_increment != column.auto_increment:
                found.append(f"{where} auto_increment")
            if sl.normalize_default(have.on_update) != sl.normalize_default(column.on_update):
                found.append(f"{where} on update")
        for key in keys:
            if key[0] == "primary":
                if table.primary_key != key[1]:
                    found.append(f"{name} primary key")
            elif key[0] in ("unique", "index"):
                if not sl.index_satisfied(sl.Index(key[1], key[0] == "unique"), table):
                    found.append(f"{name} {key[0]} on {','.join(key[1])}")
            else:
                mine = [f for f in table.foreign_keys if sl.fk_signature(f) == (key[1], key[2], key[3])]
                if not mine:
                    found.append(f"{name}.{key[1][0]} foreign key")
                elif (mine[0].on_delete or "RESTRICT") != (key[4] or "RESTRICT"):
                    found.append(f"{name}.{key[1][0]} ON DELETE")
        return found

    def test_every_create_table_in_the_python_code_is_in_the_baseline(self):
        seen = set()
        for source, text in code_strings():
            if not re.match(r"^\s*CREATE TABLE", text, re.I) or "{" in text:
                continue
            name, columns, keys = parse_create_table(text)
            seen.add(name)
            self.assertEqual(self.problems(name, columns, keys), [], f"{source}: {name}")
        self.assertGreaterEqual(len(seen), 17)
        self.assertTrue({"escalation_context", "notion_sync_configs", "quiz_attempt_answer"} <= seen)

    def test_every_alter_table_in_the_python_code_is_in_the_baseline(self):
        columns_seen = 0
        for source, text in code_strings():
            if not re.match(r"^\s*ALTER TABLE\s+\w+\s+(ADD|MODIFY)\b", text, re.I) or "{" in text:
                continue
            table, actions = parse_alter(text)
            for kind, payload in actions:
                if kind == "column":
                    columns_seen += 1
                    self.assertEqual(self.problems(table, [payload], []), [], f"{source}: {table}.{payload.name}")
                else:
                    self.assertEqual(self.problems(table, [], [("unique" if payload[0] else "index", payload[1])]), [], source)
        self.assertGreaterEqual(columns_seen, 20)

    def test_sql_scripts_differ_from_production_only_in_the_known_ways(self):
        definitions, alters = {}, []
        for source, text in script_statements():
            if re.match(r"^\s*CREATE TABLE", text, re.I):
                name, columns, keys = parse_create_table(text)
                definitions[(source, name)] = (columns, keys)        # a later definition in a script replaces an earlier one
            else:
                alters.append((source, text))
        self.assertGreaterEqual(len(definitions), 10)
        found = set()
        for (source, name), (columns, keys) in definitions.items():
            found.update(self.problems(name, columns, keys, self.baseline))
        for source, text in alters:
            table, actions = parse_alter(text)
            for kind, payload in actions:
                if kind == "column":
                    found.update(self.problems(table, [payload], [], self.baseline))
        self.assertEqual(sorted(found), sorted(SCRIPT_DIFFERS_FROM_PRODUCTION),
                         "A SQL script disagrees with production in a new way (or no longer does). Production wins: "
                         "update SCRIPT_DIFFERS_FROM_PRODUCTION, never production.")

    def test_every_table_the_code_queries_exists_in_production_or_is_listed(self):
        used = {}
        for source, text in code_strings():
            if not SQL_START.match(text):
                continue
            for match in re.finditer(r"(?<!KEY )\b(?:FROM|JOIN|INTO|UPDATE)\s+`?([A-Za-z_]\w*)`?", text, re.I):
                used.setdefault(match.group(1).lower(), source)
        used.pop("information_schema", None)
        used.pop("dual", None)
        missing = {t for t in used if t not in self.expected.tables}
        self.assertEqual(missing, set(CODE_USES_BUT_PRODUCTION_LACKS),
                         "The code queries a table that is in no migration. Add a migration, or (if production really "
                         "lacks it and the code copes) list it in CODE_USES_BUT_PRODUCTION_LACKS.")

    def test_the_special_cases_from_the_task_are_in_the_baseline(self):
        wiki = self.expected.get("wiki_article")
        self.assertTrue(any(i.unique and i.columns == ("notion_page_id",) for i in wiki.indexes))
        jobs = self.expected.get("notion_sync_jobs")
        self.assertTrue({"last_heartbeat", "trigger_source", "details"} <= set(jobs.columns))

    def test_baseline_has_all_36_production_tables_including_the_production_only_ones(self):
        self.assertEqual(len(self.expected.tables), 36)
        for name in ("audit_log", "chat_session", "email_verifications", "escalation_tickets", "image_retrieval",
                     "qa_knowledge", "registration_keys", "staff_registration_keys"):
            self.assertIn(name, self.expected.tables)

    def test_baseline_is_production_not_the_scripts(self):
        users = self.baseline.get("users").columns["status"]
        self.assertEqual(sl.normalize_type(users.type), "enum('pending','active','inactive','declined')")
        self.assertEqual(users.default, "pending")
        self.assertTrue(self.baseline.get("login_history").columns["user_id"].nullable)
        notification = self.baseline.get("notification")
        self.assertNotIn("message", notification.columns)
        self.assertTrue(notification.columns["user_id"].nullable)
        self.assertEqual(notification.foreign_keys, [])
        self.assertEqual(sl.normalize_type(self.baseline.get("review_queue").columns["status"].type), "varchar(30)")
        escalation = {tuple(i.columns) for i in self.baseline.get("escalation").indexes}
        self.assertNotIn(("status",), escalation)             # the two indexes are in 0002, not in the baseline
        self.assertNotIn(("created_at",), escalation)
        later = {tuple(i.columns) for i in self.expected.get("escalation").indexes}
        self.assertTrue({("status",), ("created_at",)} <= later)


# --------------------------------------------------------------------------
# Test 8 - the snapshot tool: read-only, no secrets
# --------------------------------------------------------------------------
class FakeInformationSchema:
    """A connection that answers like MySQL's INFORMATION_SCHEMA for a given Schema and records every statement."""

    def __init__(self, schema):
        self.schema, self.statements, self.closed = schema, [], False

    def cursor(self, dictionary=False, **_):
        return FakeInformationSchemaCursor(self)

    def close(self):
        self.closed = True


class FakeInformationSchemaCursor:
    def __init__(self, conn):
        self.conn, self.rows_ = conn, []

    def close(self):
        pass

    def fetchall(self):
        return self.rows_

    def execute(self, sql, params=()):
        self.conn.statements.append(" ".join(sql.split()))
        text = sql
        schema = self.conn.schema
        if "information_schema.TABLES" in text and "TABLE_TYPE" in text:
            self.rows_ = [{"table_name": t.name, "engine": t.engine, "collation_name": (t.charset or "utf8mb4") + "_0900_ai_ci"}
                          for t in schema.tables.values()]
        elif "information_schema.COLUMNS" in text:
            self.rows_ = []
            for t in schema.tables.values():
                for c in t.columns.values():
                    extra = ("auto_increment " if c.auto_increment else "") + \
                            ("DEFAULT_GENERATED " if isinstance(c.default, sl.Expr) or c.on_update else "") + \
                            (f"on update {c.on_update.sql}" if c.on_update else "")
                    default = c.default.sql if isinstance(c.default, sl.Expr) else (
                        None if c.default is None else sl._default_text(c.default))
                    scale = re.match(r"decimal\(\d+,(\d+)\)", sl.normalize_type(c.type))
                    if scale and default is not None:
                        default = f"{Decimal(default):.{scale.group(1)}f}"
                    self.rows_.append({"table_name": t.name, "column_name": c.name, "column_type": sl.normalize_type(c.type),
                                       "is_nullable": "YES" if c.nullable else "NO", "column_default": default, "extra": extra.strip()})
        elif "information_schema.STATISTICS" in text:
            self.rows_ = []
            for t in schema.tables.values():
                for seq, column in enumerate(t.primary_key, 1):
                    self.rows_.append({"table_name": t.name, "index_name": "PRIMARY", "non_unique": 0, "seq": seq, "column_name": column})
                for i in t.indexes:
                    for seq, column in enumerate(i.columns, 1):
                        self.rows_.append({"table_name": t.name, "index_name": i.name, "non_unique": 0 if i.unique else 1,
                                           "seq": seq, "column_name": column})
        elif "KEY_COLUMN_USAGE" in text:
            self.rows_ = []
            for t in schema.tables.values():
                for f in t.foreign_keys:
                    for column, ref in zip(f.columns, f.ref_columns):
                        self.rows_.append({"table_name": t.name, "constraint_name": f.name, "column_name": column,
                                           "ref_table": f.ref_table, "ref_column": ref,
                                           "delete_rule": f.on_delete or "NO ACTION", "update_rule": f.on_update or "NO ACTION"})
        elif "VERSION()" in text:
            self.rows_ = [{"v": "8.0.36"}]
        elif "@@" in text:
            self.rows_ = [{"v": "ON"}]
        elif "schema_migrations" in text and "SELECT version" in text:
            self.rows_ = []
        else:
            self.rows_ = []                                  # VIEWS / TRIGGERS / ROUTINES / EVENTS: none


PASSWORD, HOST, DATABASE = "S3cret-pw-9!", "db.internal.example.test", "prod_db_name"


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.expected = ml.replay(ml.load_migrations())
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.target = Path(self._tmp.name) / "snapshot.json"

    def run_snapshot(self, schema=None):
        conn = FakeInformationSchema(schema or self.expected)
        out = []
        code = schema_snapshot.run(["--out", str(self.target), "--label", "test"], connect_fn=lambda read_only: conn, out=out.append)
        return code, conn, "\n".join(out)

    def test_only_select_and_show_statements_are_sent(self):
        code, conn, _ = self.run_snapshot()
        self.assertEqual(code, 0)
        self.assertTrue(conn.statements)
        for statement in conn.statements:
            self.assertRegex(statement, r"^(SELECT|SHOW)\b", statement)
            self.assertNotRegex(statement, r"\b(INSERT|UPDATE|DELETE|ALTER|CREATE|DROP|TRUNCATE|GRANT)\b")
        self.assertTrue(conn.closed)

    def test_the_session_is_opened_read_only(self):
        statements = []

        class Cursor:
            def execute(self, sql, params=()):
                statements.append(sql)

            def close(self):
                pass

        class Conn:
            def cursor(self, **_):
                return Cursor()

        env = {"MYSQL_HOST": HOST, "MYSQL_USER": "u", "MYSQL_PASSWORD": PASSWORD, "MYSQL_DATABASE": DATABASE}
        with patch.dict(os.environ, env), patch.object(mysql.connector, "connect", return_value=Conn()) as connect:
            sl.connect(True)
        self.assertEqual(statements, ["SET SESSION TRANSACTION READ ONLY"])
        self.assertEqual(connect.call_args.kwargs["host"], HOST)         # same MYSQL_* variables as the backend

    def test_file_holds_structure_only_and_no_secrets(self):
        env = {"MYSQL_HOST": HOST, "MYSQL_USER": "u", "MYSQL_PASSWORD": PASSWORD, "MYSQL_DATABASE": DATABASE}
        with patch.dict(os.environ, env):
            code, _, output = self.run_snapshot()
        written = self.target.read_text(encoding="utf-8")
        data = json.loads(written)
        for secret in (PASSWORD, HOST, DATABASE):
            self.assertNotIn(secret, written)
            self.assertNotIn(secret, output)
        self.assertEqual(set(data), {"format", "generated_at", "label", "server_version", "note", "tables", "server_settings",
                                     "other_objects", "migration_records", "notes"})
        self.assertEqual(set(data["tables"]["users"]), {"engine", "charset", "collation", "columns", "primary_key", "indexes", "foreign_keys"})
        self.assertIn("no row data", data["note"])

    def test_snapshot_describes_the_schema_faithfully(self):
        self.run_snapshot()
        data = json.loads(self.target.read_text(encoding="utf-8"))
        back = sl.schema_from_dict(data)
        self.assertEqual(sl.compare(self.expected, back), [])
        self.assertEqual(sl.compare(back, self.expected), [])

    def test_check_against_a_snapshot_finds_drift_without_a_database(self):
        broken = self.expected.copy()
        del broken.get("wiki_article").columns["notion_page_id"]
        self.run_snapshot(broken)
        out, errors = [], io.StringIO()
        with contextlib.redirect_stderr(errors):
            code = migrate.run(["check", "--snapshot", str(self.target)], backend_factory=self.fail_if_called, out=out.append)
        text = "\n".join(out)
        self.assertEqual(code, 1)
        self.assertIn("wiki_article: missing column notion_page_id", text)

    @staticmethod
    def fail_if_called(read_only):
        raise AssertionError("check --snapshot must not connect to a database")

    def test_unreachable_database_message_has_no_host_or_password(self):
        env = {"MYSQL_HOST": HOST, "MYSQL_USER": "u", "MYSQL_PASSWORD": PASSWORD, "MYSQL_DATABASE": DATABASE}
        boom = mysql.connector.Error(msg=f"Can't connect to MySQL server on '{HOST}:3306' using {PASSWORD}", errno=2003)
        errors = io.StringIO()
        with patch.dict(os.environ, env), patch.object(mysql.connector, "connect", side_effect=boom), contextlib.redirect_stderr(errors):
            code = schema_snapshot.run(["--out", str(self.target)], out=lambda *_: None)
            code_migrate = migrate.run(["status"], out=lambda *_: None)
        self.assertEqual((code, code_migrate), (2, 2))
        self.assertIn("Database is not reachable. Check the MYSQL_* variables.", errors.getvalue())
        for secret in (PASSWORD, HOST):
            self.assertNotIn(secret, errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())
        self.assertFalse(self.target.exists())

    def test_missing_variables_are_named_but_not_their_values(self):
        errors = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(errors):
            code = schema_snapshot.run(["--out", str(self.target)], out=lambda *_: None)
        self.assertEqual(code, 2)
        self.assertIn("Missing environment variables: MYSQL_HOST, MYSQL_USER, MYSQL_DATABASE", errors.getvalue())


# --------------------------------------------------------------------------
# The command line (exit codes and the messages people will read)
# --------------------------------------------------------------------------
class CommandLineTests(TempMigrations):
    def run_cli(self, argv, db, files=None):
        self.migrations(files)
        out, errors = [], io.StringIO()
        with contextlib.redirect_stderr(errors):
            code = migrate.run(argv, backend_factory=lambda read_only: db, migrations_dir=self.dir, out=out.append)
        return code, "\n".join(out), errors.getvalue()

    def test_status_apply_dry_run_and_check(self):
        db = self.backend()
        code, text, _ = self.run_cli(["status"], db)
        self.assertEqual(code, 0)
        self.assertIn("No migration record yet", text)
        self.assertIn("PENDING", text)

        code, text, _ = self.run_cli(["apply", "--dry-run"], db)
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN - nothing will be changed", text)
        self.assertIn("CREATE TABLE IF NOT EXISTS `shop`", text)
        self.assertEqual(db.executed, [])

        code, text, _ = self.run_cli(["apply"], db)
        self.assertEqual((code, db.ledger_rows()[0]["version"]), (0, "0001"))
        self.assertIn("Applied 2 migration(s).", text)

        code, text, _ = self.run_cli(["apply"], db)
        self.assertIn("Nothing to do: the database is up to date.", text)

        code, text, _ = self.run_cli(["check"], db)
        self.assertEqual(code, 0)
        self.assertIn("Schema matches the migrations.", text)

        del db.schema.get("item").columns["price"]
        code, text, _ = self.run_cli(["check"], db)
        self.assertEqual(code, 1)
        self.assertIn("item: missing column price", text)

    def test_changed_migration_message(self):
        db = self.backend()
        self.run_cli(["apply"], db)
        (self.dir / "0002_prices.py").write_bytes((HEADER + M2 + "# edit\n").encode())
        code, _, errors = self.run_cli(["apply"], db, files={})
        self.assertEqual(code, 1)
        self.assertIn("Migration 0002 has changed since it was applied.", errors)
        code, text, _ = self.run_cli(["status"], db, files={})
        self.assertEqual(code, 1)
        self.assertIn("CHANGED", text)

    def test_baseline_messages(self):
        migrations = self.migrations({"0001_shop.py": M1})
        db = self.backend(schema=ml.replay(migrations))
        del db.schema.get("item").columns["shop_id"]
        code, text, errors = self.run_cli(["baseline"], db, files={})
        self.assertEqual(code, 1)
        self.assertIn("missing column shop_id", text)
        self.assertIn("Schema differs from the baseline", errors)
        self.assertIsNone(db.ledger)

    def test_running_runner_message(self):
        other = self.backend()
        other.lock()
        code, _, errors = self.run_cli(["apply"], self.backend())
        self.assertEqual(code, 1)
        self.assertIn("Another migration runner is already running.", errors)

    def test_failed_migration_is_reported_with_what_finished(self):
        db = self.backend(fail_on="add column item.price")
        code, text, errors = self.run_cli(["apply"], db)
        self.assertEqual(code, 1)
        self.assertIn("0001 shop", text)
        self.assertIn("Migration 0002 (prices) stopped", errors)
        self.assertNotIn("Traceback", errors)

    def test_generate_baseline_from_a_snapshot_rebuilds_the_same_schema(self):
        expected = ml.replay(ml.load_migrations())
        snapshot = Path(self.dir) / "snap.json"
        snapshot.write_text(json.dumps(sl.schema_to_dict(expected)), encoding="utf-8")
        target = Path(self.dir) / "out" / "0001_baseline.py"
        code = migrate.run(["generate-baseline", "--snapshot", str(snapshot), "--out", str(target)], out=lambda *_: None)
        self.assertEqual(code, 0)
        generated = Path(self.dir) / "gen"
        generated.mkdir()
        (generated / "0001_baseline.py").write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        self.assertEqual(sl.compare(expected, ml.replay(ml.load_migrations(generated))), [])

    def test_the_real_migration_files_load_and_are_numbered(self):
        migrations = ml.load_migrations()
        self.assertEqual(migrations[0].version, "0001")
        self.assertEqual(migrations[0].name, "baseline")
        self.assertEqual(len(migrations[0].checksum), 64)


# --------------------------------------------------------------------------
# Migration 0002 (optional indexes) and what `check` compares
# --------------------------------------------------------------------------
class OptionalIndexMigrationTests(unittest.TestCase):
    def setUp(self):
        self.migrations = ml.load_migrations()
        self.production = ml.replay(self.migrations[:1])          # production = the baseline only

    def test_0002_is_two_add_index_operations_and_is_not_part_of_the_baseline(self):
        self.assertEqual([m.name for m in self.migrations], ["baseline", "escalation_indexes"])
        ctx = ml.Context(self.production.copy(), dry_run=True)
        self.migrations[1].upgrade(ctx)
        self.assertEqual([(s.status, s.sql) for s in ctx.steps], [
            ("would", "ALTER TABLE `escalation` ADD KEY `idx_status` (`status`)"),
            ("would", "ALTER TABLE `escalation` ADD KEY `idx_created_at` (`created_at`)"),
        ])

    def test_0002_adds_the_indexes_only_when_missing_and_only_once(self):
        db = ml.MemoryBackend(schema=self.production.copy())
        ml.baseline_database(db, self.migrations)                 # production matches 0001: only the ledger is written
        self.assertEqual(db.executed, [ml.LEDGER_DDL])
        results = ml.apply_migrations(db, self.migrations)
        self.assertEqual([r.migration.version for r in results], ["0002"])
        self.assertEqual([s.status for s in results[0].steps], ["done", "done"])
        self.assertEqual(len(db.executed), 3)                      # ledger + the two indexes, nothing else
        self.assertEqual(ml.apply_migrations(db, self.migrations), [])
        self.assertEqual(sl.compare(ml.replay(self.migrations), db.schema), [])

    def test_an_index_that_already_exists_under_another_name_is_left_alone(self):
        other = self.production.copy()
        other.get("escalation").indexes.append(sl.Index(("status",), False, "my_status_idx"))
        other.get("escalation").indexes.append(sl.Index(("created_at",), False, "my_created_idx"))
        ctx = ml.Context(other, dry_run=True)
        self.migrations[1].upgrade(ctx)
        self.assertEqual({s.status for s in ctx.steps}, {"exists"})

    def test_check_compares_a_database_without_records_with_the_baseline_only(self):
        for ledger in (None, []):
            report = ml.check_schema(self.migrations, self.production.copy(), ledger)
            self.assertEqual((report.scope, report.differences), (["0001"], []))
            self.assertTrue(any("not applied and not compared" in n for n in report.notes))

    def test_a_pending_migration_is_not_drift_but_an_applied_one_is_checked(self):
        ledger = [{"version": "0001", "name": "baseline", "checksum": self.migrations[0].checksum, "applied_at": "x"}]
        report = ml.check_schema(self.migrations, self.production.copy(), ledger)
        self.assertEqual((report.scope, report.differences), (["0001"], []))
        self.assertEqual([e.version for e in report.status.pending()], ["0002"])
        ledger.append({"version": "0002", "name": "escalation_indexes", "checksum": self.migrations[1].checksum, "applied_at": "x"})
        report = ml.check_schema(self.migrations, self.production.copy(), ledger)
        self.assertEqual({d.kind for d in report.errors()}, {"missing_index"})


# --------------------------------------------------------------------------
# The generated DDL, checked against the rules of MySQL 8.4 / 9 that can be checked without a server
# --------------------------------------------------------------------------
def storage_bytes(type_):
    normalized = sl.normalize_type(type_)
    sized = re.match(r"(var)?char\((\d+)\)", normalized)
    if sized:
        return int(sized.group(2)) * 4 + (2 if sized.group(1) else 0)      # utf8mb4 = up to 4 bytes per character
    if normalized.endswith("text"):
        return 12                                                          # a TEXT column keeps only a pointer in the row
    return {"tinyint(1)": 1, "tinyint": 1, "smallint": 2, "int": 4, "bigint": 8, "float": 4, "double": 8,
            "datetime": 8, "timestamp": 4}.get(normalized.split(" ")[0], 8)


class GeneratedDdlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctx = ml.Context(sl.Schema())
        for migration in ml.load_migrations():
            migration.upgrade(ctx)
        cls.steps, cls.schema = ctx.steps, ctx.schema

    def test_every_statement_is_a_plain_additive_statement_in_the_expected_shape(self):
        self.assertGreaterEqual(len(self.steps), 38)
        for step in self.steps:
            ml.assert_additive(step.sql)
            if step.sql.startswith("CREATE TABLE"):
                self.assertTrue(step.sql.endswith(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"), step.label)

    def test_foreign_keys_follow_the_strict_rules_of_mysql_8_4_and_later(self):
        # Since 8.4 a foreign key must point at a whole PRIMARY KEY or UNIQUE index, with the same type.
        for table in self.schema.tables.values():
            for key in table.foreign_keys:
                parent = self.schema.get(key.ref_table)
                ref = tuple(key.ref_columns)
                where = f"{table.name}.{key.name}"
                self.assertTrue(tuple(parent.primary_key) == ref or any(i.unique and tuple(i.columns) == ref for i in parent.indexes), where)
                for child_column, parent_column in zip(key.columns, key.ref_columns):
                    self.assertEqual(sl.normalize_type(table.columns[child_column].type),
                                     sl.normalize_type(parent.columns[parent_column].type), where)
                self.assertEqual((table.engine, parent.engine), ("InnoDB", "InnoDB"), where)

    def test_names_types_and_defaults_are_valid(self):
        for table in self.schema.tables.values():
            names = [table.name] + [c.name for c in table.columns.values()] + [i.name for i in table.indexes] + \
                    [f.name for f in table.foreign_keys]
            for name in names:
                self.assertLessEqual(len(name), 64, name)
            for column in table.columns.values():
                where = f"{table.name}.{column.name}"
                normalized = sl.normalize_type(column.type)
                if re.match(r"^(tinyint|smallint|mediumint|int|bigint)\(", normalized):
                    self.assertEqual(normalized, "tinyint(1)", where + ": integer display widths are gone in MySQL 8.0.19+")
                if normalized.endswith(("text", "blob")) or normalized == "json":
                    self.assertIsNone(column.default, where + ": a TEXT/BLOB/JSON column cannot have a literal default")
                if column.auto_increment:
                    self.assertTrue(tuple(table.primary_key[:1]) == (column.name.lower(),) or
                                    any(i.columns[:1] == (column.name.lower(),) for i in table.indexes), where)

    def test_keys_and_rows_fit_innodb_limits(self):
        for table in self.schema.tables.values():
            for index in table.indexes:
                for name in index.columns:
                    self.assertFalse(sl.normalize_type(table.columns[name].type).endswith("text"),
                                     f"{table.name}.{name}: a TEXT column in an index needs a prefix length")
                self.assertLessEqual(sum(storage_bytes(table.columns[n].type) for n in index.columns), 3072, f"{table.name}.{index.name}")
            self.assertLess(sum(storage_bytes(c.type) for c in table.columns.values()), 65535, table.name)


# --------------------------------------------------------------------------
# The real production snapshot (kept out of git: it is only used when the file is present)
# --------------------------------------------------------------------------
SNAPSHOT_FILE = REPO_DIR / "schema_production.json"


def exact_view(data):
    """Everything a snapshot says about a table, including names and column order (stricter than `check`)."""
    def column(c):
        default = ("expr:" + c["default"].lower()) if c["default_is_expression"] else sl.normalize_default(c["default"])
        return (c["name"], sl.normalize_type(c["type"]), c["nullable"], default, c["auto_increment"], (c["on_update"] or "").lower())

    return {
        name: {
            "columns": [column(c) for c in t["columns"]],
            "primary_key": t["primary_key"],
            "indexes": sorted((i["name"], i["unique"], tuple(i["columns"])) for i in t["indexes"]),
            "foreign_keys": sorted((f["name"], tuple(f["columns"]), f["ref_table"], tuple(f["ref_columns"]),
                                    f["on_delete"] or "NO ACTION", f["on_update"] or "NO ACTION") for f in t["foreign_keys"]),
            "engine": t["engine"], "charset": t["charset"],
        }
        for name, t in data["tables"].items()
    }


@unittest.skipUnless(SNAPSHOT_FILE.exists(), "schema_production.json (never committed) is not in the repository root")
class ProductionSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
        self.migrations = ml.load_migrations()

    def test_check_shows_no_differences_and_no_warnings(self):
        report = ml.check_schema(self.migrations, sl.schema_from_dict(self.data), self.data.get("migration_records"))
        self.assertEqual([str(d) for d in report.differences], [])

    def test_baseline_reproduces_production_exactly_including_names_and_column_order(self):
        mine = exact_view(sl.schema_to_dict(ml.replay(self.migrations[:1])))
        theirs = exact_view(self.data)
        self.assertEqual(sorted(mine), sorted(theirs))
        for name in theirs:
            self.assertEqual(mine[name], theirs[name], name)

    def test_applying_the_baseline_to_production_would_execute_nothing(self):
        db = ml.MemoryBackend(schema=sl.schema_from_dict(self.data))
        results = ml.apply_migrations(db, self.migrations[:1], dry_run=True, adopt_existing=True)
        self.assertEqual({s.status for s in results[0].steps}, {"exists"})


class GeneratorTests(unittest.TestCase):
    def test_generated_baseline_is_tidy_and_loadable(self):
        source = ml.emit_baseline_source(ml.replay(ml.load_migrations()))
        self.assertIn('col("score", "DECIMAL(6,4)", default=0)', source)                       # not 0.0000
        self.assertIn("\"ENUM('pending','active','inactive','declined')\"", source)             # type upper-cased, values kept
        self.assertIn("        indexes=[\n            index(", source)                          # one index per line
        self.assertNotIn("default=0.0", source)


class StartupIsUntouchedTests(unittest.TestCase):
    """Phase 1 must not change how the live site starts or runs."""

    def test_the_app_never_imports_or_runs_the_migration_tools(self):
        for path in SRC_DIR.glob("*.py"):
            if path.name.startswith("test_"):
                continue
            text = path.read_text(encoding="utf-8")
            for name in ("migration_lib", "schema_lib", "schema_snapshot", "migrate_cli"):
                self.assertNotIn(f"import {name}", text, path.name)
                self.assertNotIn(f"from {name}", text, path.name)

    def test_no_deployment_file_runs_migrations(self):
        for relative in ("backend/Procfile", "backend/src/railway.json", "backend/src/Procfile", "railway.json", "Procfile"):
            path = REPO_DIR / relative
            if path.exists():
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("migrate.py", text, relative)
                self.assertNotIn("schema_migrations", text, relative)


if __name__ == "__main__":
    unittest.main()
