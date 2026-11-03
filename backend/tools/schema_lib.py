"""Shared building blocks for the schema tools (schema_snapshot.py and migrate.py).

  * a small model of a database schema (tables, columns, indexes, foreign keys),
  * READ-ONLY introspection of a MySQL database through information_schema,
  * snapshot (de)serialisation -- structure only, never row data, never credentials,
  * the drift comparison used by `migrate.py check` and `migrate.py baseline`.

Everything that reads the database goes through the same SELECT/SHOW-only guard as
notion_duplicate_report.py. This module never prints a password or a stack trace.
"""

import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import mysql.connector

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from notion_duplicate_report import ReadOnly  # noqa: E402  (the SELECT/SHOW-only SQL guard)

SNAPSHOT_FORMAT = 1
LEDGER_TABLE = "schema_migrations"  # managed by migrate.py; never reported as drift


# --------------------------------------------------------------------------
# Connection (same MYSQL_* variables as the backend and the other tools)
# --------------------------------------------------------------------------
class SchemaToolError(Exception):
    """A problem to show the user as a clear one-line message (never a stack trace)."""


def require_env():
    missing = [name for name in ("MYSQL_HOST", "MYSQL_USER", "MYSQL_DATABASE") if not os.getenv(name)]
    if missing:
        raise SchemaToolError("Missing environment variables: " + ", ".join(missing))


def connect(read_only):
    """Open a connection from MYSQL_*; a read-only session when `read_only` is True."""
    require_env()
    try:
        conn = mysql.connector.connect(
            host=os.getenv("MYSQL_HOST"),
            port=int(os.getenv("MYSQL_PORT", 3306)),
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            database=os.getenv("MYSQL_DATABASE"),
            charset="utf8mb4",
            connection_timeout=15,
        )
    except ValueError:
        raise SchemaToolError("MYSQL_PORT must be a number.") from None
    except mysql.connector.Error as error:
        raise SchemaToolError(describe_connect_error(error)) from None
    if read_only:
        cursor = conn.cursor()
        cursor.execute("SET SESSION TRANSACTION READ ONLY")
        cursor.close()
    return conn


def describe_connect_error(error):
    """Our own wording, keyed on the error number. The driver's message can contain host or account names."""
    errno = getattr(error, "errno", None)
    if errno == 1045:
        return "Access denied. Check MYSQL_USER and MYSQL_PASSWORD."
    if errno == 1049:
        return "Unknown database. Check MYSQL_DATABASE."
    if errno in (2002, 2003, 2005, 2006, 2013, None):
        return "Database is not reachable. Check the MYSQL_* variables."
    return f"Could not connect to the database (error code {errno}). Check the MYSQL_* variables."


def describe_sql_error(error):
    """A safe explanation of a failed statement. Never echoes the driver text: it can include row values."""
    errno = getattr(error, "errno", None)
    known = {
        1050: "the table already exists with a different definition",
        1060: "a column with that name already exists",
        1061: "an index with that name already exists",
        1062: "existing rows contain duplicate values, so a unique index cannot be added",
        1071: "an index key is too long",
        1072: "an index refers to a column that does not exist",
        1075: "there can be only one auto-increment column and it must be a key",
        1142: "the database user is not allowed to run this statement (CREATE/ALTER permission)",
        1146: "a table the statement needs does not exist",
        1215: "a foreign key could not be created (check the column types match)",
        1005: "a table or foreign key could not be created (check the column types match)",
        1452: "existing rows would violate the new foreign key",
        3780: "a foreign key column and its referenced column have incompatible types",
    }
    why = known.get(errno)
    return f"error code {errno}" + (f": {why}" if why else "")


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Expr:
    """A raw SQL expression used as a default, e.g. CURRENT_TIMESTAMP."""
    sql: str


CURRENT_TIMESTAMP = Expr("CURRENT_TIMESTAMP")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def check_identifier(name):
    if not isinstance(name, str) or not _IDENT.match(name):
        raise SchemaToolError(f"Not a valid table/column/index name: {name!r}")
    return name


@dataclass
class Column:
    name: str
    type: str
    nullable: bool = True
    default: object = None          # None = no default; Expr; str; int/float/bool
    auto_increment: bool = False
    on_update: Expr = None


@dataclass
class Index:
    columns: tuple
    unique: bool = False
    name: str = None
    implicit: bool = False   # MySQL creates it by itself to back a foreign key; never written out or required


@dataclass
class ForeignKey:
    columns: tuple
    ref_table: str
    ref_columns: tuple
    on_delete: str = None
    on_update: str = None
    name: str = None


@dataclass
class Table:
    name: str
    columns: dict = field(default_factory=dict)       # lower-case name -> Column, in column order
    primary_key: tuple = ()
    indexes: list = field(default_factory=list)
    foreign_keys: list = field(default_factory=list)
    engine: str = None
    charset: str = None
    collation: str = None


@dataclass
class Schema:
    tables: dict = field(default_factory=dict)        # lower-case name -> Table

    def get(self, name):
        return self.tables.get(str(name).lower())

    def copy(self):
        import copy
        return copy.deepcopy(self)


# --------------------------------------------------------------------------
# Normalisation (so MySQL / MariaDB / our own declarations can be compared)
# --------------------------------------------------------------------------
def normalize_type(raw):
    text = re.sub(r"\s+", " ", str(raw or "").strip().lower()).replace(" (", "(")
    text = {"boolean": "tinyint(1)", "bool": "tinyint(1)", "integer": "int", "double precision": "double",
            "numeric": "decimal", "real": "double"}.get(text, text)

    enum = re.match(r"^(enum|set)\((.*)\)$", text)
    if enum:
        values = re.findall(r"'((?:[^']|'')*)'", str(raw))
        return f"{enum.group(1)}(" + ",".join("'" + v + "'" for v in values) + ")"

    integer = re.match(r"^(tinyint|smallint|mediumint|integer|int|bigint)(?:\((\d+)\))?(.*)$", text)
    if integer:
        base = "int" if integer.group(1) == "integer" else integer.group(1)
        keep_width = base == "tinyint" and integer.group(2) == "1"
        return base + ("(1)" if keep_width else "") + integer.group(3)

    decimal = re.match(r"^(decimal|numeric)(?:\((\d+)(?:,(\d+))?\))?(.*)$", text)
    if decimal:
        return f"decimal({decimal.group(2) or 10},{decimal.group(3) or 0})" + decimal.group(4)

    return re.sub(r"^(datetime|timestamp|time)\(0\)", r"\1", text)


def normalize_default(value):
    """Comparable form of a default. None means "no default" (also what DEFAULT NULL means)."""
    if value is None:
        return None
    text = value.sql if isinstance(value, Expr) else ("1" if value is True else "0" if value is False else str(value))
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] == "'":
        text = text[1:-1].replace("''", "'")
    if text.lower() == "null":
        return None
    if re.match(r"^(current_timestamp|now|localtimestamp|localtime)(\(\d*\))?$", text, re.I):
        return "current_timestamp"
    if re.match(r"^-?\d+(\.\d+)?$", text):  # a DECIMAL(6,4) column reports its default 0 as 0.0000
        return format(Decimal(text).normalize(), "f")
    return text


def _text(value):
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", "replace")
    return value


# --------------------------------------------------------------------------
# Introspection (read-only)
# --------------------------------------------------------------------------
def introspect(db):
    """Build a Schema from information_schema. `db` is a ReadOnly-style object with .rows(sql, params)."""
    schema = Schema()

    for row in db.rows("""
        SELECT TABLE_NAME AS table_name, ENGINE AS engine, TABLE_COLLATION AS collation_name
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
    """):
        collation = _text(row["collation_name"])
        schema.tables[_text(row["table_name"]).lower()] = Table(
            name=_text(row["table_name"]),
            engine=_text(row["engine"]),
            collation=collation,
            charset=collation.split("_")[0] if collation else None,
        )

    for row in db.rows("""
        SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name, COLUMN_TYPE AS column_type,
               IS_NULLABLE AS is_nullable, COLUMN_DEFAULT AS column_default, EXTRA AS extra
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        ORDER BY TABLE_NAME, ORDINAL_POSITION
    """):
        table = schema.tables.get(_text(row["table_name"]).lower())
        if table is None:  # a view's columns
            continue
        extra = str(_text(row["extra"]) or "").lower()
        on_update = re.search(r"on update (\S+(?:\(\d*\))?)", extra)
        default = _text(row["column_default"])
        table.columns[_text(row["column_name"]).lower()] = Column(
            name=_text(row["column_name"]),
            type=_text(row["column_type"]),
            nullable=str(_text(row["is_nullable"])).upper() == "YES",
            default=default if default is None or "default_generated" not in extra
            else Expr(str(default)),
            auto_increment="auto_increment" in extra,
            on_update=Expr(on_update.group(1).upper()) if on_update else None,
        )

    grouped = {}
    for row in db.rows("""
        SELECT TABLE_NAME AS table_name, INDEX_NAME AS index_name, NON_UNIQUE AS non_unique,
               SEQ_IN_INDEX AS seq, COLUMN_NAME AS column_name
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
        ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX
    """):
        key = (_text(row["table_name"]).lower(), _text(row["index_name"]))
        entry = grouped.setdefault(key, {"unique": int(row["non_unique"]) == 0, "columns": []})
        entry["columns"].append(_text(row["column_name"]).lower())
    for (table_name, index_name), entry in grouped.items():
        table = schema.tables.get(table_name)
        if table is None:
            continue
        if index_name == "PRIMARY":
            table.primary_key = tuple(entry["columns"])
        else:
            table.indexes.append(Index(tuple(entry["columns"]), entry["unique"], index_name))

    fks = {}
    for row in db.rows("""
        SELECT k.TABLE_NAME AS table_name, k.CONSTRAINT_NAME AS constraint_name, k.COLUMN_NAME AS column_name,
               k.REFERENCED_TABLE_NAME AS ref_table, k.REFERENCED_COLUMN_NAME AS ref_column,
               r.DELETE_RULE AS delete_rule, r.UPDATE_RULE AS update_rule
        FROM information_schema.KEY_COLUMN_USAGE k
        JOIN information_schema.REFERENTIAL_CONSTRAINTS r
          ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
         AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
         AND r.TABLE_NAME = k.TABLE_NAME
        WHERE k.TABLE_SCHEMA = DATABASE() AND k.REFERENCED_TABLE_NAME IS NOT NULL
        ORDER BY k.TABLE_NAME, k.CONSTRAINT_NAME, k.ORDINAL_POSITION
    """):
        key = (_text(row["table_name"]).lower(), _text(row["constraint_name"]))
        entry = fks.setdefault(key, {"columns": [], "ref_columns": [], "ref_table": _text(row["ref_table"]).lower(),
                                     "delete": _text(row["delete_rule"]), "update": _text(row["update_rule"])})
        entry["columns"].append(_text(row["column_name"]).lower())
        entry["ref_columns"].append(_text(row["ref_column"]).lower())
    for (table_name, constraint_name), entry in fks.items():
        table = schema.tables.get(table_name)
        if table is not None:
            table.foreign_keys.append(ForeignKey(
                tuple(entry["columns"]), entry["ref_table"], tuple(entry["ref_columns"]),
                entry["delete"], entry["update"], constraint_name))

    return schema


def server_version(db):
    rows = db.rows("SELECT VERSION() AS v")
    return str(_text(rows[0]["v"])) if rows else None


# --------------------------------------------------------------------------
# Snapshot files
# --------------------------------------------------------------------------
def _default_text(value):
    return "1" if value is True else "0" if value is False else str(value)


def schema_to_dict(schema, label=None, version=None):
    tables = {}
    for key in sorted(schema.tables):
        table = schema.tables[key]
        tables[table.name] = {
            "engine": table.engine,
            "charset": table.charset,
            "collation": table.collation,
            "columns": [
                {
                    "name": c.name,
                    "type": c.type,
                    "nullable": c.nullable,
                    "default": None if c.default is None else (c.default.sql if isinstance(c.default, Expr) else _default_text(c.default)),
                    "default_is_expression": isinstance(c.default, Expr),
                    "auto_increment": c.auto_increment,
                    "on_update": c.on_update.sql if c.on_update else None,
                }
                for c in table.columns.values()
            ],
            "primary_key": list(table.primary_key),
            "indexes": [{"name": i.name, "unique": i.unique, "columns": list(i.columns)} for i in table.indexes],
            "foreign_keys": [
                {"name": f.name, "columns": list(f.columns), "ref_table": f.ref_table,
                 "ref_columns": list(f.ref_columns), "on_delete": f.on_delete, "on_update": f.on_update}
                for f in table.foreign_keys
            ],
        }
    return {
        "format": SNAPSHOT_FORMAT,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "label": label,
        "server_version": version,
        "note": "Structure only: no row data, no credentials.",
        "tables": tables,
    }


def schema_from_dict(data):
    if not isinstance(data, dict) or data.get("format") != SNAPSHOT_FORMAT or "tables" not in data:
        raise SchemaToolError("This is not a schema snapshot file written by schema_snapshot.py.")
    schema = Schema()
    for name, t in data["tables"].items():
        table = Table(name=name, engine=t.get("engine"), charset=t.get("charset"), collation=t.get("collation"),
                      primary_key=tuple(c.lower() for c in t.get("primary_key", [])))
        for c in t.get("columns", []):
            default = c.get("default")
            table.columns[c["name"].lower()] = Column(
                name=c["name"], type=c["type"], nullable=bool(c["nullable"]),
                default=Expr(default) if default is not None and c.get("default_is_expression") else default,
                auto_increment=bool(c.get("auto_increment")),
                on_update=Expr(c["on_update"]) if c.get("on_update") else None)
        for i in t.get("indexes", []):
            table.indexes.append(Index(tuple(x.lower() for x in i["columns"]), bool(i["unique"]), i.get("name")))
        for f in t.get("foreign_keys", []):
            table.foreign_keys.append(ForeignKey(
                tuple(x.lower() for x in f["columns"]), f["ref_table"].lower(),
                tuple(x.lower() for x in f["ref_columns"]), f.get("on_delete"), f.get("on_update"), f.get("name")))
        schema.tables[name.lower()] = table
    return schema


# --------------------------------------------------------------------------
# Drift comparison
# --------------------------------------------------------------------------
@dataclass
class Difference:
    severity: str   # "error": the database is missing or has something different; "warning": extra / cosmetic
    kind: str
    table: str
    detail: str

    def __str__(self):
        return f"[{self.severity.upper():<7}] {self.table}: {self.detail}"


def _cols(columns):
    return "(" + ", ".join(columns) + ")"


def _norm_rule(rule):
    rule = str(rule or "RESTRICT").upper()
    return "RESTRICT" if rule in ("NO ACTION", "RESTRICT") else rule


def index_satisfied(expected, actual_table):
    """A unique index must exist exactly. A plain index is also covered by any index that starts with the same columns."""
    columns = tuple(c.lower() for c in expected.columns)
    if expected.unique:
        if actual_table.primary_key and tuple(actual_table.primary_key) == columns:
            return True
        return any(i.unique and tuple(i.columns) == columns for i in actual_table.indexes)
    if actual_table.primary_key and tuple(actual_table.primary_key[:len(columns)]) == columns:
        return True
    return any(tuple(i.columns[:len(columns)]) == columns for i in actual_table.indexes)


def fk_signature(fk):
    return (tuple(c.lower() for c in fk.columns), fk.ref_table.lower(), tuple(c.lower() for c in fk.ref_columns))


def compare(expected, actual, ignore=(LEDGER_TABLE,)):
    """What is wrong with `actual` compared to `expected`. Read-only; returns a list of Difference."""
    found = []
    ignore = {name.lower() for name in ignore}

    for key, want in expected.tables.items():
        have = actual.tables.get(key)
        if have is None:
            found.append(Difference("error", "missing_table", want.name, "table is missing"))
            continue

        for ckey, wc in want.columns.items():
            hc = have.columns.get(ckey)
            if hc is None:
                found.append(Difference("error", "missing_column", want.name,
                                        f"missing column {wc.name} ({wc.type})"))
                continue
            if normalize_type(hc.type) != normalize_type(wc.type):
                found.append(Difference("error", "type_mismatch", want.name,
                                        f"column {wc.name} has type {normalize_type(hc.type)}, expected {normalize_type(wc.type)}"))
            if hc.nullable != wc.nullable:
                is_timestamp = normalize_type(wc.type).startswith("timestamp")
                found.append(Difference(
                    "warning" if is_timestamp else "error", "nullable_mismatch", want.name,
                    f"column {wc.name} is {'NULL' if hc.nullable else 'NOT NULL'}, expected {'NULL' if wc.nullable else 'NOT NULL'}"
                    + (" (TIMESTAMP nullability depends on the server mode)" if is_timestamp else "")))
            if hc.auto_increment != wc.auto_increment:
                found.append(Difference("error", "auto_increment_mismatch", want.name,
                                        f"column {wc.name} auto_increment is {hc.auto_increment}, expected {wc.auto_increment}"))
            if normalize_default(hc.default) != normalize_default(wc.default):
                found.append(Difference("warning", "default_mismatch", want.name,
                                        f"column {wc.name} default is {normalize_default(hc.default)!r}, expected {normalize_default(wc.default)!r}"))
            if normalize_default(hc.on_update) != normalize_default(wc.on_update):
                found.append(Difference("warning", "on_update_mismatch", want.name,
                                        f"column {wc.name} ON UPDATE is {normalize_default(hc.on_update)!r}, expected {normalize_default(wc.on_update)!r}"))
        for ckey, hc in have.columns.items():
            if ckey not in want.columns:
                found.append(Difference("warning", "extra_column", want.name,
                                        f"extra column {hc.name} ({normalize_type(hc.type)}) is not described by the migrations"))

        if tuple(c.lower() for c in want.primary_key) != tuple(have.primary_key):
            found.append(Difference("error", "primary_key_mismatch", want.name,
                                    f"primary key is {_cols(have.primary_key) if have.primary_key else 'missing'}, "
                                    f"expected {_cols(want.primary_key) if want.primary_key else 'none'}"))

        for index in want.indexes:
            if not index.implicit and not index_satisfied(index, have):
                kind = "unique index" if index.unique else "index"
                found.append(Difference("error", "missing_unique_index" if index.unique else "missing_index", want.name,
                                        f"missing {kind} on {_cols(index.columns)}"
                                        + (f" ({index.name})" if index.name else "")))
        wanted = [(tuple(c.lower() for c in w.columns), w.unique) for w in want.indexes]
        for index in have.indexes:
            # not "extra" when it is a wanted index, or a longer index that starts with one (it serves the same queries)
            if not any(index.unique == unique and tuple(index.columns[:len(columns)]) == columns for columns, unique in wanted):
                found.append(Difference("warning", "extra_index", want.name,
                                        f"extra {'unique index' if index.unique else 'index'} {index.name} on {_cols(index.columns)}"))

        have_fks = {fk_signature(f): f for f in have.foreign_keys}
        for fk in want.foreign_keys:
            actual_fk = have_fks.get(fk_signature(fk))
            if actual_fk is None:
                found.append(Difference("error", "missing_foreign_key", want.name,
                                        f"missing foreign key {_cols(fk.columns)} -> {fk.ref_table}{_cols(fk.ref_columns)}"))
            elif _norm_rule(actual_fk.on_delete) != _norm_rule(fk.on_delete):
                found.append(Difference("error", "fk_rule_mismatch", want.name,
                                        f"foreign key {_cols(fk.columns)} has ON DELETE {_norm_rule(actual_fk.on_delete)}, "
                                        f"expected {_norm_rule(fk.on_delete)}"))
        wanted_sigs = {fk_signature(f) for f in want.foreign_keys}
        for sig, fk in have_fks.items():
            if sig not in wanted_sigs:
                found.append(Difference("warning", "extra_foreign_key", want.name,
                                        f"extra foreign key {_cols(fk.columns)} -> {fk.ref_table}{_cols(fk.ref_columns)}"))

        if want.engine and have.engine and want.engine.lower() != have.engine.lower():
            found.append(Difference("error", "engine_mismatch", want.name,
                                    f"storage engine is {have.engine}, expected {want.engine}"))
        if want.charset and have.charset and want.charset.lower() != have.charset.lower():
            found.append(Difference("error", "charset_mismatch", want.name,
                                    f"character set is {have.charset}, expected {want.charset} (non-English text can break)"))

    for key, have in actual.tables.items():
        if key not in expected.tables and key not in ignore:
            found.append(Difference("warning", "extra_table", have.name, "table is not described by the migrations"))

    order = {"error": 0, "warning": 1}
    return sorted(found, key=lambda d: (order.get(d.severity, 2), d.table.lower(), d.kind, d.detail))
