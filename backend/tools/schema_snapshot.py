"""Read-only snapshot of the database STRUCTURE (a dry run: nothing is changed).

Writes a JSON file describing every table, column, index and foreign key, plus a few server settings
that affect how the schema behaves. It NEVER reads row data and never writes anything to the database:
every statement must be a SELECT/SHOW (the script refuses otherwise) and the session is opened
read-only. The file holds no credentials, no host name and no database name.

It connects with the same MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE
variables the backend uses, so run it where those point at the database you want to describe (e.g.
`railway run python backend/tools/schema_snapshot.py`).

    python backend/tools/schema_snapshot.py
    python backend/tools/schema_snapshot.py --out production_schema.json --label production
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import mysql.connector

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from schema_lib import (  # noqa: E402
    LEDGER_TABLE, ReadOnly, SchemaToolError, connect, introspect, schema_to_dict, server_version,
)

OUTPUT_DIR = TOOLS_DIR / "schema_output"

_SETTINGS = (
    ("sql_mode", "@@sql_mode"),
    ("database_charset", "@@character_set_database"),
    ("database_collation", "@@collation_database"),
    ("explicit_defaults_for_timestamp", "@@explicit_defaults_for_timestamp"),
    ("lower_case_table_names", "@@lower_case_table_names"),
)

# Objects other than tables that a schema can contain. Names only: no definitions, no data.
_OTHER_OBJECTS = (
    ("views", "SELECT TABLE_NAME AS name FROM information_schema.VIEWS WHERE TABLE_SCHEMA = DATABASE() ORDER BY 1"),
    ("triggers", "SELECT TRIGGER_NAME AS name FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = DATABASE() ORDER BY 1"),
    ("routines", "SELECT ROUTINE_NAME AS name FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA = DATABASE() ORDER BY 1"),
    ("events", "SELECT EVENT_NAME AS name FROM information_schema.EVENTS WHERE EVENT_SCHEMA = DATABASE() ORDER BY 1"),
)


def _value(raw):
    if isinstance(raw, (bytes, bytearray)):
        raw = bytes(raw).decode("utf-8", "replace")
    return raw if raw is None or isinstance(raw, (int, float, bool)) else str(raw)


def build_snapshot(db, label=None):
    """The snapshot as a dict. `db` only needs .rows(sql, params) and may only be asked SELECT/SHOW."""
    snapshot = schema_to_dict(introspect(db), label=label, version=server_version(db))
    notes = []

    settings = {}
    for key, expression in _SETTINGS:
        try:
            row = db.one(f"SELECT {expression} AS v")
            settings[key] = _value(row["v"]) if row else None
        except mysql.connector.Error:
            settings[key] = None
            notes.append(f"Could not read {key}.")
    snapshot["server_settings"] = settings

    others = {}
    for key, sql in _OTHER_OBJECTS:
        try:
            others[key] = [str(_value(row["name"])) for row in db.rows(sql)]
        except mysql.connector.Error:
            others[key] = None
            notes.append(f"Could not list {key} (missing permission?).")
    snapshot["other_objects"] = others

    # The ledger is migrate.py's own bookkeeping: version, name, checksum and time. No application data.
    records = None
    if LEDGER_TABLE in {name.lower() for name in snapshot["tables"]}:
        try:
            records = [{"version": str(r["version"]), "name": str(r["name"]), "checksum": str(r["checksum"]),
                        "applied_at": str(r["applied_at"])}
                       for r in db.rows("SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version")]
        except mysql.connector.Error:
            notes.append("Could not read schema_migrations.")
    snapshot["migration_records"] = records
    snapshot["notes"] = notes
    return snapshot


def summarize(snapshot):
    tables = snapshot["tables"]
    columns = sum(len(t["columns"]) for t in tables.values())
    indexes = sum(len(t["indexes"]) for t in tables.values())
    keys = sum(len(t["foreign_keys"]) for t in tables.values())
    lines = [f"Tables: {len(tables)}   Columns: {columns}   Indexes: {indexes}   Foreign keys: {keys}",
             f"Server: {snapshot.get('server_version')}"]
    extra = {k: v for k, v in (snapshot.get("other_objects") or {}).items() if v}
    if extra:
        lines.append("Also present (not described by migrations): " + ", ".join(f"{len(v)} {k}" for k, v in extra.items()))
    records = snapshot.get("migration_records")
    lines.append("Migration records: " + ("none (schema_migrations does not exist yet)" if records is None
                                          else ", ".join(r["version"] for r in records) or "table exists but is empty"))
    return lines


def run(argv=None, connect_fn=None, out=print):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", help="where to write the JSON file (default: backend/tools/schema_output/schema_snapshot_<time>.json)")
    parser.add_argument("--label", help="free text stored in the file, e.g. 'production'")
    args = parser.parse_args(argv)

    try:
        conn = (connect_fn or connect)(True)
    except SchemaToolError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    try:
        snapshot = build_snapshot(ReadOnly(conn), args.label)
    except mysql.connector.Error as error:
        print(f"ERROR: Could not read the schema (error code {getattr(error, 'errno', None)}).", file=sys.stderr)
        return 2
    finally:
        conn.close()

    target = Path(args.out) if args.out else OUTPUT_DIR / f"schema_snapshot_{datetime.now():%Y%m%d_%H%M%S}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    out("SCHEMA SNAPSHOT  (read-only - nothing was changed)")
    out("=" * 50)
    for line in summarize(snapshot):
        out(line)
    for note in snapshot["notes"]:
        out("NOTE: " + note)
    out(f"\nWritten to {target}")
    out("The file holds structure only (no row data, no credentials). Review it, then send it back.")
    return 0


def main():
    try:
        code = run()
    except Exception as error:  # never show a stack trace: it can contain connection details
        print(f"ERROR: Unexpected {type(error).__name__}. Check the MYSQL_* variables and try again.", file=sys.stderr)
        code = 2
    sys.exit(code)


if __name__ == "__main__":
    main()
