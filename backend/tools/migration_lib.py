"""Migration engine behind migrate.py.

A migration is a numbered Python file in backend/migrations/ with one function, upgrade(ctx).
`ctx` only offers ADDITIVE, "add if missing" operations:

    create_table / add_column / add_index / add_foreign_key

There is no drop, rename, truncate, modify or data change, so a migration cannot lose data and is
safe to run twice. MySQL commits every DDL statement at once (there is no rollback), which is why
each operation first looks at the live schema and does nothing when its result is already there.
If a migration stops half-way, the ones that finished stay finished, the migration is NOT recorded as
applied, and running it again completes the rest.

The same migration files are replayed against an empty in-memory schema to learn what the database
is EXPECTED to look like; `migrate.py check` compares that with the real database.
"""

import copy
import hashlib
import importlib.util
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import mysql.connector

from schema_lib import (  # CURRENT_TIMESTAMP is re-exported: migration files import it from here
    CURRENT_TIMESTAMP, LEDGER_TABLE, Column, Expr, ForeignKey, Index, ReadOnly, Schema, SchemaToolError, Table,
    check_identifier, compare, describe_sql_error, fk_signature, index_satisfied, introspect, server_version,
)

LOCK_NAME = "jungle_house_schema_migrate"
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
_FILE_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.py$")
_TYPE = re.compile(r"^[A-Za-z]+(\s*\((\s*\d+\s*(,\s*\d+\s*)?|(\s*'[^'\\]*'\s*,?)+)\))?(\s+UNSIGNED)?$", re.I)

LEDGER_DDL = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    " version VARCHAR(20) NOT NULL PRIMARY KEY,"
    " name VARCHAR(255) NOT NULL,"
    " checksum CHAR(64) NOT NULL,"
    " applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
)

# MySQL error numbers that mean "somebody (the app's own runtime code) just created it": not a failure.
_ALREADY_THERE = {1050, 1060, 1061, 1826, 1022}


class MigrationError(SchemaToolError):
    """A clear one-line problem; `results` holds what finished before it."""

    def __init__(self, message, results=None):
        super().__init__(message)
        self.results = results or []


class SqlFailure(Exception):
    def __init__(self, errno):
        super().__init__(f"error code {errno}")
        self.errno = errno


# --------------------------------------------------------------------------
# Declaring schema in a migration file
# --------------------------------------------------------------------------
def _names(columns):
    if isinstance(columns, str):
        columns = (columns,)
    return tuple(check_identifier(c) for c in columns)


def col(name, type, null=True, default=None, auto_increment=False, on_update=None):
    """A column. `default=None` means no default. Use CURRENT_TIMESTAMP for a timestamp default."""
    if not _TYPE.match(str(type)):
        raise MigrationError(f"Column {name}: unsupported type {type!r}.")
    if isinstance(on_update, str):
        on_update = Expr(on_update)
    return Column(check_identifier(name), str(type).strip(), bool(null), default, bool(auto_increment), on_update)


def index(*columns, name=None, unique=False):
    return Index(_names(columns), bool(unique), check_identifier(name) if name else None)


def unique(*columns, name=None):
    return index(*columns, name=name, unique=True)


def fk(columns, ref_table, ref_columns, on_delete=None, on_update=None, name=None):
    return ForeignKey(_names(columns), check_identifier(ref_table), _names(ref_columns),
                      on_delete.upper() if on_delete else None, on_update.upper() if on_update else None,
                      check_identifier(name) if name else None)


# --------------------------------------------------------------------------
# SQL text (only ever produced from validated names and values)
# --------------------------------------------------------------------------
def q(name):
    return "`" + check_identifier(name) + "`"


def qlist(columns):
    return ", ".join(q(c) for c in columns)


def literal(value):
    if isinstance(value, Expr):
        if value.sql.upper() != "CURRENT_TIMESTAMP":
            raise MigrationError("Only CURRENT_TIMESTAMP is allowed as an expression default.")
        return "CURRENT_TIMESTAMP"
    if value is True:
        return "1"
    if value is False:
        return "0"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def render_column(column):
    parts = [q(column.name), column.type, "NULL" if column.nullable else "NOT NULL"]
    if column.auto_increment:
        parts.append("AUTO_INCREMENT")
    if column.default is not None:
        parts.append("DEFAULT " + literal(column.default))
    if column.on_update is not None:
        parts.append("ON UPDATE " + literal(column.on_update))
    return " ".join(parts)


def auto_name(prefix, table, columns):
    return (f"{prefix}_{table}_{'_'.join(columns)}")[:64]


def index_name(table, idx):
    return idx.name or auto_name("uq" if idx.unique else "idx", table, idx.columns)


def render_index(table, idx):
    return f"{'UNIQUE ' if idx.unique else ''}KEY {q(index_name(table, idx))} ({qlist(idx.columns)})"


def render_foreign_key(table, key):
    sql = (f"CONSTRAINT {q(key.name or auto_name('fk', table, key.columns))} FOREIGN KEY ({qlist(key.columns)}) "
           f"REFERENCES {q(key.ref_table)} ({qlist(key.ref_columns)})")
    if key.on_delete:
        sql += " ON DELETE " + key.on_delete
    if key.on_update:
        sql += " ON UPDATE " + key.on_update
    return sql


def render_create_table(table):
    lines = [render_column(c) for c in table.columns.values()]
    if table.primary_key:
        lines.append(f"PRIMARY KEY ({qlist(table.primary_key)})")
    lines += [render_index(table.name, i) for i in table.indexes if not i.implicit]
    lines += [render_foreign_key(table.name, f) for f in table.foreign_keys]
    tail = f" ENGINE={table.engine or 'InnoDB'}" + (f" DEFAULT CHARSET={table.charset}" if table.charset else "")
    return f"CREATE TABLE IF NOT EXISTS {q(table.name)} (\n  " + ",\n  ".join(lines) + f"\n){tail}"


_ALLOWED_SQL = re.compile(
    r"^(CREATE TABLE IF NOT EXISTS `\w+` \(|ALTER TABLE `\w+` (ADD COLUMN|ADD UNIQUE KEY|ADD KEY|ADD CONSTRAINT) )")


def _add_implicit_index(table, key):
    """MySQL creates an index for a foreign key when none of the existing ones can serve it."""
    probe = Index(tuple(c.lower() for c in key.columns))
    if not index_satisfied(probe, table):
        table.indexes.append(Index(probe.columns, False, key.name or key.columns[0], implicit=True))


def assert_additive(sql):
    """Last line of defence: the only statements the runner will ever send."""
    if not _ALLOWED_SQL.match(sql) or ";" in sql:
        raise MigrationError("Refusing to run a statement that is not an additive CREATE/ADD.")


# --------------------------------------------------------------------------
# Operations and the context a migration receives
# --------------------------------------------------------------------------
@dataclass
class Op:
    label: str
    sql: str
    apply: object   # callable(schema): updates an in-memory Schema the same way the statement updates MySQL


@dataclass
class Step:
    status: str     # done | exists | would | recorded
    label: str
    sql: str


class Context:
    """What `upgrade(ctx)` gets. `backend=None` or `dry_run=True` only records; nothing is executed."""

    def __init__(self, schema, backend=None, dry_run=False):
        self.schema = schema
        self.backend = backend
        self.dry_run = dry_run
        self.steps = []

    # -- operations ------------------------------------------------------
    def create_table(self, name, columns, primary_key=(), indexes=(), foreign_keys=(), engine="InnoDB", charset=None):
        check_identifier(name)
        table = Table(name=name, engine=engine, charset=charset, primary_key=_names(primary_key) if primary_key else ())
        for column in columns:
            if column.name.lower() in table.columns:
                raise MigrationError(f"Table {name}: column {column.name} is declared twice.")
            if column.name.lower() in {c.lower() for c in table.primary_key}:
                column.nullable = False
            table.columns[column.name.lower()] = column
        for key in table.primary_key:
            if key.lower() not in table.columns:
                raise MigrationError(f"Table {name}: primary key column {key} does not exist.")
            table.columns[key.lower()].nullable = False
        for idx in indexes:
            self._need_columns(table, idx.columns, f"index on {idx.columns}")
            table.indexes.append(Index(idx.columns, idx.unique, index_name(name, idx)))
        for key in foreign_keys:
            self._need_columns(table, key.columns, "foreign key")
            self._need_reference(key, own=table)
            table.foreign_keys.append(ForeignKey(key.columns, key.ref_table.lower(), tuple(c.lower() for c in key.ref_columns),
                                                 key.on_delete, key.on_update, key.name or auto_name("fk", name, key.columns)))
        op = Op(f"create table {name}", render_create_table(table),
                lambda schema, t=table: schema.tables.__setitem__(t.name.lower(), copy.deepcopy(t)))
        for key in table.foreign_keys:  # after rendering: MySQL adds these by itself
            _add_implicit_index(table, key)
        if self.schema.get(name) is not None:
            return self._log("exists", op)
        return self._execute(op)

    def add_column(self, table, column):
        have = self._table(table)
        if column.name.lower() in have.columns:
            return self._log("exists", Op(f"add column {table}.{column.name}", "", None))
        if not column.nullable and column.default is None and not column.auto_increment:
            raise MigrationError(f"Column {table}.{column.name} is NOT NULL: give it a default so existing rows stay valid.")
        sql = f"ALTER TABLE {q(table)} ADD COLUMN {render_column(column)}"
        return self._execute(Op(f"add column {table}.{column.name}", sql,
                                lambda schema, c=column: schema.get(table).columns.__setitem__(c.name.lower(), copy.deepcopy(c))))

    def add_index(self, table, idx):
        have = self._table(table)
        self._need_columns(have, idx.columns, f"index on {table}")
        name = index_name(table, idx)
        label = f"add {'unique ' if idx.unique else ''}index {table}.{name}"
        for existing in have.indexes:
            if existing.name == name:
                if existing.unique == idx.unique and tuple(existing.columns) == tuple(c.lower() for c in idx.columns):
                    return self._log("exists", Op(label, "", None))
                raise MigrationError(f"Index {table}.{name} already exists on different columns.")
        if any(i.unique == idx.unique and tuple(i.columns) == tuple(c.lower() for c in idx.columns) for i in have.indexes) \
                or (idx.unique and index_satisfied(idx, have)):
            return self._log("exists", Op(label, "", None))
        sql = f"ALTER TABLE {q(table)} ADD {'UNIQUE ' if idx.unique else ''}KEY {q(name)} ({qlist(idx.columns)})"
        return self._execute(Op(label, sql, lambda schema, i=Index(tuple(c.lower() for c in idx.columns), idx.unique, name):
                                schema.get(table).indexes.append(copy.deepcopy(i))))

    def add_foreign_key(self, table, key):
        have = self._table(table)
        self._need_columns(have, key.columns, f"foreign key on {table}")
        self._need_reference(key)
        name = key.name or auto_name("fk", table, key.columns)
        label = f"add foreign key {table}.{name}"
        stored = ForeignKey(tuple(c.lower() for c in key.columns), key.ref_table.lower(),
                            tuple(c.lower() for c in key.ref_columns), key.on_delete, key.on_update, name)
        for existing in have.foreign_keys:
            if existing.name == name and fk_signature(existing) != fk_signature(stored):
                raise MigrationError(f"Foreign key {table}.{name} already exists with different columns.")
            if fk_signature(existing) == fk_signature(stored):
                return self._log("exists", Op(label, "", None))
        sql = f"ALTER TABLE {q(table)} ADD {render_foreign_key(table, ForeignKey(key.columns, key.ref_table, key.ref_columns, key.on_delete, key.on_update, name))}"
        def apply(schema):
            target = schema.get(table)
            target.foreign_keys.append(copy.deepcopy(stored))
            _add_implicit_index(target, stored)

        return self._execute(Op(label, sql, apply))

    # -- plumbing --------------------------------------------------------
    def _table(self, name):
        table = self.schema.get(check_identifier(name))
        if table is None:
            raise MigrationError(f"Table {name} does not exist yet; create it first.")
        return table

    def _need_columns(self, table, columns, what):
        for column in columns:
            if column.lower() not in table.columns:
                raise MigrationError(f"Table {table.name}: {what} uses column {column}, which does not exist.")

    def _need_reference(self, key, own=None):
        target = own if own is not None and own.name.lower() == key.ref_table.lower() else self.schema.get(key.ref_table)
        if target is None:
            raise MigrationError(f"Foreign key refers to table {key.ref_table}, which does not exist yet.")
        for column in key.ref_columns:
            if column.lower() not in target.columns:
                raise MigrationError(f"Foreign key refers to {key.ref_table}.{column}, which does not exist.")

    def _log(self, status, op):
        self.steps.append(Step(status, op.label, op.sql))

    def _execute(self, op):
        if self.dry_run or self.backend is None:
            status = "would" if self.dry_run else "recorded"
        else:
            assert_additive(op.sql)
            try:
                self.backend.run(op)
                status = "done"
            except SqlFailure as failure:
                if failure.errno not in _ALREADY_THERE:
                    raise MigrationError(f"Could not {op.label}: {describe_sql_error(failure)}.") from None
                status = "exists"
        op.apply(self.schema)
        self.steps.append(Step(status, op.label, op.sql))


# --------------------------------------------------------------------------
# Migration files
# --------------------------------------------------------------------------
@dataclass
class Migration:
    version: str
    name: str
    path: Path
    checksum: str

    def upgrade(self, ctx):
        spec = importlib.util.spec_from_file_location(f"jh_migration_{self.version}", self.path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not callable(getattr(module, "upgrade", None)):
            raise MigrationError(f"Migration {self.version} has no upgrade(ctx) function.")
        module.upgrade(ctx)


def file_checksum(path):
    """sha256 of the file; CRLF and LF checkouts of the same file give the same checksum."""
    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def load_migrations(directory=None):
    directory = Path(directory or MIGRATIONS_DIR)
    if not directory.is_dir():
        raise MigrationError("The migrations folder was not found.")
    found = []
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        match = _FILE_NAME.match(path.name)
        if not match:
            raise MigrationError(f"Migration file {path.name} must be named like 0002_add_something.py.")
        found.append(Migration(match.group(1), match.group(2), path, file_checksum(path)))
    for position, migration in enumerate(found, start=1):
        if int(migration.version) != position:
            raise MigrationError(f"Migration numbers must be 0001, 0002, 0003 ... without gaps or repeats (see {migration.path.name}).")
    return found


def replay(migrations):
    """The schema these migrations describe, built in memory only (nothing touches a database)."""
    schema = Schema()
    for migration in migrations:
        migration.upgrade(Context(schema))
    return schema


# --------------------------------------------------------------------------
# What is applied, what is pending
# --------------------------------------------------------------------------
@dataclass
class Entry:
    version: str
    name: str
    state: str          # applied | pending | changed | missing_file
    applied_at: object = None


@dataclass
class Status:
    entries: list = field(default_factory=list)
    problems: list = field(default_factory=list)

    def pending(self):
        return [e for e in self.entries if e.state == "pending"]

    def applied_versions(self):
        return {e.version for e in self.entries if e.state in ("applied", "changed")}


def classify(migrations, ledger_rows):
    status = Status()
    recorded = {str(r["version"]): r for r in ledger_rows}
    for migration in migrations:
        row = recorded.pop(migration.version, None)
        if row is None:
            status.entries.append(Entry(migration.version, migration.name, "pending"))
        elif str(row["checksum"]) != migration.checksum:
            status.entries.append(Entry(migration.version, migration.name, "changed", row.get("applied_at")))
            status.problems.append(f"Migration {migration.version} has changed since it was applied.")
        elif str(row["name"]) != migration.name:
            status.entries.append(Entry(migration.version, migration.name, "changed", row.get("applied_at")))
            status.problems.append(f"Migration {migration.version} was applied as '{row['name']}' but the file is now '{migration.name}'.")
        else:
            status.entries.append(Entry(migration.version, migration.name, "applied", row.get("applied_at")))
    for version, row in sorted(recorded.items()):
        status.entries.append(Entry(version, str(row["name"]), "missing_file", row.get("applied_at")))
        status.problems.append(f"Migration {version} is recorded as applied but its file is missing.")
    status.entries.sort(key=lambda e: e.version)
    applied = [e.version for e in status.entries if e.state in ("applied", "changed", "missing_file")]
    for entry in status.entries:
        if entry.state == "pending" and applied and entry.version < max(applied):
            status.problems.append(f"Migration {entry.version} is not applied but a later migration is.")
    return status


# --------------------------------------------------------------------------
# Talking to MySQL
# --------------------------------------------------------------------------
class MySQLBackend:
    def __init__(self, conn):
        self.conn = conn
        self._locked = False

    def server_version(self):
        return server_version(ReadOnly(self.conn))

    def close(self):
        self.conn.close()

    def introspect(self):
        return introspect(ReadOnly(self.conn))

    def run(self, op):
        cursor = self.conn.cursor()
        try:
            cursor.execute(op.sql)
        except mysql.connector.Error as error:
            raise SqlFailure(getattr(error, "errno", None)) from None
        finally:
            cursor.close()

    def ledger_exists(self):
        row = ReadOnly(self.conn).one(
            "SELECT 1 AS x FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
            (LEDGER_TABLE,))
        return bool(row)

    def ledger_create(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute(LEDGER_DDL)
        finally:
            cursor.close()

    def ledger_rows(self):
        return ReadOnly(self.conn).rows(
            "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version")

    def ledger_add(self, version, name, checksum):
        cursor = self.conn.cursor()
        try:
            cursor.execute("INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s)",
                           (version, name, checksum))
            self.conn.commit()
        finally:
            cursor.close()

    def lock(self):
        row = ReadOnly(self.conn).one("SELECT GET_LOCK(%s, 0) AS got", (LOCK_NAME,))
        self._locked = bool(row and row["got"] == 1)
        return self._locked

    def unlock(self):
        if self._locked:
            ReadOnly(self.conn).one("SELECT RELEASE_LOCK(%s) AS released", (LOCK_NAME,))
            self._locked = False


class MemoryBackend:
    """A database in memory: same interface as MySQLBackend, used by the tests."""
    _locks = set()

    def __init__(self, schema=None, fail_on=None):
        self.schema = schema or Schema()
        self.ledger = None          # None = table does not exist
        self.executed = []
        self.fail_on = fail_on      # label of the operation that should fail
        self._locked = False

    def server_version(self):
        return "memory"

    def close(self):
        self.unlock()

    def introspect(self):
        return self.schema.copy()

    def run(self, op):
        if self.fail_on and op.label == self.fail_on:
            raise SqlFailure(1146)
        self.executed.append(op.sql)
        op.apply(self.schema)

    def ledger_exists(self):
        return self.ledger is not None

    def ledger_create(self):
        if self.ledger is None:
            self.ledger = []
            self.executed.append(LEDGER_DDL)

    def ledger_rows(self):
        return [dict(r) for r in sorted(self.ledger or [], key=lambda r: r["version"])]

    def ledger_add(self, version, name, checksum):
        self.ledger.append({"version": version, "name": name, "checksum": checksum, "applied_at": "now"})

    def lock(self):
        if LOCK_NAME in MemoryBackend._locks and not self._locked:
            return False
        MemoryBackend._locks.add(LOCK_NAME)
        self._locked = True
        return True

    def unlock(self):
        if self._locked:
            MemoryBackend._locks.discard(LOCK_NAME)
            self._locked = False


# --------------------------------------------------------------------------
# Commands (return data; migrate.py prints it)
# --------------------------------------------------------------------------
@dataclass
class MigrationResult:
    migration: Migration
    steps: list


def read_ledger(backend):
    return backend.ledger_rows() if backend.ledger_exists() else None


def apply_migrations(backend, migrations, dry_run=False, adopt_existing=False):
    """Run every pending migration in order. Returns a list of MigrationResult."""
    if not backend.lock():
        raise MigrationError("Another migration runner is already running.")
    results = []
    try:
        rows = read_ledger(backend)
        status = classify(migrations, rows or [])
        if status.problems:
            raise MigrationError(" ".join(status.problems) + " Nothing was run.")
        pending = [m for m in migrations if m.version in {e.version for e in status.pending()}]
        schema = backend.introspect()
        if rows is None:
            others = [t.name for t in schema.tables.values() if t.name.lower() != LEDGER_TABLE]
            if others and not adopt_existing:
                raise MigrationError(
                    f"This database already has {len(others)} table(s) but no migration record. Run `baseline` "
                    "to check it against migration 0001 and record it. (`apply --adopt-existing` skips that check.)")
        if not pending:
            return results
        if not dry_run and rows is None:
            backend.ledger_create()
        for migration in pending:
            ctx = Context(schema, backend, dry_run)
            try:
                migration.upgrade(ctx)
            except MigrationError as error:
                results.append(MigrationResult(migration, ctx.steps))
                raise MigrationError(f"Migration {migration.version} ({migration.name}) stopped: {error} "
                                     "It is NOT recorded as applied; fix the cause and run apply again.", results) from None
            if not dry_run:
                backend.ledger_add(migration.version, migration.name, migration.checksum)
            results.append(MigrationResult(migration, ctx.steps))
        return results
    finally:
        backend.unlock()


class BaselineMismatch(MigrationError):
    def __init__(self, message, differences):
        super().__init__(message)
        self.differences = differences


def baseline_database(backend, migrations, accept_extras=False):
    """Record migration 0001 on an existing database - only if its schema matches 0001. Changes nothing otherwise."""
    if not migrations:
        raise MigrationError("There are no migration files.")
    first = migrations[0]
    if not backend.lock():
        raise MigrationError("Another migration runner is already running.")
    try:
        rows = read_ledger(backend)
        if rows:
            raise MigrationError("This database already has migration records; baseline is only for a database that has none.")
        differences = compare(replay([first]), backend.introspect())
        errors = [d for d in differences if d.severity == "error"]
        if errors or (differences and not accept_extras):
            raise BaselineMismatch(
                f"Schema differs from the baseline ({len(errors)} difference(s), {len(differences) - len(errors)} warning(s)). "
                "Nothing was changed." + ("" if errors else " Re-run with --accept-extras if the extra items are expected."),
                differences)
        if rows is None:
            backend.ledger_create()
        backend.ledger_add(first.version, first.name, first.checksum)
        return first, differences
    finally:
        backend.unlock()


@dataclass
class CheckReport:
    status: Status
    differences: list
    scope: list
    notes: list

    def errors(self):
        return [d for d in self.differences if d.severity == "error"]

    def warnings(self):
        return [d for d in self.differences if d.severity == "warning"]


def check_schema(migrations, actual, ledger_rows):
    """Compare a live (or snapshot) schema with what the applied migrations promise. Read-only.

    A database with no migration record (ledger_rows None or empty) has not been baselined yet, so it is
    compared with the baseline (the first migration) only; later migrations are simply not applied yet."""
    notes = []
    status = classify(migrations, ledger_rows or [])
    if not ledger_rows:
        scope = migrations[:1]
        notes.append("No migration is recorded yet, so the schema is compared with the baseline (0001) only."
                     + (f" {len(migrations) - 1} later migration(s) are not applied and not compared." if len(migrations) > 1 else ""))
    else:
        applied = status.applied_versions()
        scope = [m for m in migrations if m.version in applied]
    return CheckReport(status, compare(replay(scope), actual), [m.version for m in scope], notes)


# --------------------------------------------------------------------------
# Drafting a baseline from a snapshot
# --------------------------------------------------------------------------
_NUMERIC_TYPE = re.compile(r"^(tinyint|smallint|mediumint|int|integer|bigint|decimal|numeric|float|double)\b", re.I)
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def _py(value):
    return json.dumps(value, ensure_ascii=False)


def _py_names(names):
    names = tuple(names)
    return _py(names[0]) if len(names) == 1 else "(" + ", ".join(_py(n) for n in names) + ")"


def _table_order(schema):
    """Tables so that every foreign key points at a table created earlier; cycles are left for add_foreign_key."""
    remaining = {t.name.lower(): t for t in schema.tables.values() if t.name.lower() != LEDGER_TABLE}
    ordered, done = [], set()
    while remaining:
        ready = sorted(k for k, t in remaining.items()
                       if all(f.ref_table.lower() in done or f.ref_table.lower() == k or f.ref_table.lower() not in remaining
                              for f in t.foreign_keys))
        if not ready:
            ready = [sorted(remaining)[0]]
        for key in ready:
            ordered.append(remaining.pop(key))
            done.add(key)
    return ordered, done


def _pretty_type(raw):
    text = str(raw).strip()
    if re.match(r"^(enum|set)\(", text, re.I):          # keep the case of the values
        return text[:text.index("(")].upper() + text[text.index("("):]
    return text.upper()


def _emit_column(column):
    args = [_py(_pretty_type(column.type)), "null=False" if not column.nullable else None,
            "auto_increment=True" if column.auto_increment else None]
    default = column.default
    if isinstance(default, Expr):
        args.append("default=CURRENT_TIMESTAMP")
    elif default is not None:
        if _NUMERIC_TYPE.match(column.type) and _NUMBER.match(str(default)):
            args.append("default=" + format(Decimal(str(default)).normalize(), "f"))   # 0.0000 -> 0
        else:
            args.append("default=" + _py(str(default)))
    if column.on_update is not None:
        args.append("on_update=" + _py(column.on_update.sql))
    return f"        col({_py(column.name)}, " + ", ".join(a for a in args if a) + "),"


def _emit_fk(key):
    args = [_py_names(key.columns), _py(key.ref_table), _py_names(key.ref_columns)]
    for keyword, rule in (("on_delete", key.on_delete), ("on_update", key.on_update)):
        if rule and rule.upper() not in ("RESTRICT", "NO ACTION"):
            args.append(f"{keyword}={_py(rule.upper())}")
    if key.name:
        args.append(f"name={_py(key.name)}")
    return "fk(" + ", ".join(args) + ")"


def _emit_index(idx):
    return (f"{'unique' if idx.unique else 'index'}(" + ", ".join(_py(c) for c in idx.columns)
            + (f", name={_py(idx.name)}" if idx.name else "") + ")")


def emit_baseline_source(schema):
    """Python source for a first migration that rebuilds `schema` (a draft: a person must review it)."""
    ordered, _ = _table_order(schema)
    created = set()
    deferred = []
    lines = [
        '"""0001 baseline: DRAFT generated from a schema snapshot. Review every table before using it.',
        "",
        "Not captured by a snapshot: check constraints, triggers, partitions, fulltext/spatial index kinds,",
        "column comments and per-column collations. Indexes MySQL created for foreign keys appear as plain indexes.",
        '"""',
        "",
        "from migration_lib import CURRENT_TIMESTAMP, col, fk, index, unique",
        "",
        'DESCRIPTION = "Baseline of the existing Jungle House database (generated from a snapshot)"',
        "",
        "",
        "def upgrade(ctx):",
    ]
    for table in ordered:
        key = table.name.lower()
        lines.append(f"    ctx.create_table({_py(table.name)}, [")
        lines += [_emit_column(c) for c in table.columns.values()]
        simple = []
        if table.primary_key:
            simple.append(f"primary_key={_py_names(table.primary_key)}")
        if table.charset:
            simple.append(f"charset={_py(table.charset)}")
        if table.engine and table.engine.lower() != "innodb":
            simple.append(f"engine={_py(table.engine)}")
        usable = [f for f in table.foreign_keys if f.ref_table.lower() in created or f.ref_table.lower() == key]
        deferred += [(table.name, f) for f in table.foreign_keys if f not in usable]
        blocks = [(name, items) for name, items in (("indexes", [_emit_index(i) for i in table.indexes]),
                                                    ("foreign_keys", [_emit_fk(f) for f in usable])) if items]
        head = "    ]" + "".join(", " + s for s in simple)
        if not blocks:
            lines.append(head + ")")
        else:
            lines.append(head + ",")
            for position, (name, items) in enumerate(blocks):
                lines.append(f"        {name}=[")
                lines += [f"            {item}," for item in items]
                lines.append("        ]" + ("," if position < len(blocks) - 1 else ")"))
        lines.append("")
        created.add(key)
    for table_name, key in deferred:
        lines.append(f"    ctx.add_foreign_key({_py(table_name)}, {_emit_fk(key)})")
    return "\n".join(lines).rstrip() + "\n"
