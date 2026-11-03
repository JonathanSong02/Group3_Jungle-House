"""Database schema versioning: see what is applied, check for drift, apply migrations.

It connects with the same MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE
variables the backend uses, so run it where those point at the database you mean (e.g. `railway run
python backend/tools/migrate.py status`). It prints no credentials and no stack traces. It is never
started by the app, the Procfile or the Railway start command.

    python backend/tools/migrate.py status                  read-only: what is applied / pending
    python backend/tools/migrate.py check                   read-only: does the database match the migrations?
    python backend/tools/migrate.py check --snapshot FILE   the same, against a schema_snapshot.py file (no database)
    python backend/tools/migrate.py apply --dry-run         show what apply would do, change nothing
    python backend/tools/migrate.py apply                   run the pending migrations (additive only)
    python backend/tools/migrate.py baseline                existing database: record migration 0001 if the schema matches it
    python backend/tools/migrate.py generate-baseline --snapshot FILE   draft a baseline migration from a snapshot

Exit codes: 0 fine, 1 a problem was found (drift, failed or changed migration), 2 it could not run.
The only thing this tool ever writes to the database is the schema_migrations table and what the
migration files add (new tables / columns / indexes / foreign keys). It never drops or changes data.
"""

import argparse
import json
import sys
from pathlib import Path

import mysql.connector

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from migration_lib import (  # noqa: E402
    BaselineMismatch, MigrationError, MySQLBackend, apply_migrations, baseline_database, check_schema,
    classify, emit_baseline_source, load_migrations, read_ledger,
)
from schema_lib import SchemaToolError, connect, schema_from_dict  # noqa: E402

_MARK = {"done": "+", "exists": "=", "would": "~", "recorded": "+"}


def default_backend(read_only):
    return MySQLBackend(connect(read_only))


def cmd_status(args, backend, migrations, out):
    rows = read_ledger(backend)
    status = classify(migrations, rows or [])
    out("MIGRATION STATUS  (read-only - nothing was changed)")
    out("=" * 50)
    if rows is None:
        out("No migration record yet: the schema_migrations table does not exist in this database.")
    for entry in status.entries:
        when = f"  {entry.applied_at}" if entry.applied_at and entry.state == "applied" else ""
        label = {"applied": "applied", "pending": "PENDING", "changed": "CHANGED", "missing_file": "FILE MISSING"}[entry.state]
        out(f"  {entry.version}  {entry.name:<28}{label}{when}")
    for problem in status.problems:
        out("PROBLEM: " + problem)
    out(f"\n{len(status.pending())} pending, {len(status.problems)} problem(s).")
    return 1 if status.problems else 0


def cmd_check(args, backend, migrations, out):
    if args.snapshot:
        data = _read_snapshot(args.snapshot)
        actual = schema_from_dict(data)
        records = data.get("migration_records")
        source = f"snapshot file {Path(args.snapshot).name}"
    else:
        records = read_ledger(backend)
        actual = backend.introspect()
        source = "the database"
    report = check_schema(migrations, actual, records)

    out("SCHEMA CHECK  (read-only - nothing was changed)")
    out("=" * 50)
    out(f"Compared {source} with migrations: {', '.join(report.scope) or 'none'}")
    for note in report.notes:
        out("NOTE: " + note)
    for problem in report.status.problems:
        out("PROBLEM: " + problem)
    for pending in report.status.pending():
        if records:
            out(f"Pending (not applied yet, so not compared): {pending.version} {pending.name}")
    for difference in report.differences:
        out(str(difference))
    errors, warnings = len(report.errors()), len(report.warnings())
    out(f"\n{errors} difference(s), {warnings} warning(s).")
    if errors or report.status.problems or (args.strict and warnings):
        out("Schema differs from the migrations." if errors else "Check finished with problems.")
        return 1
    out("Schema matches the migrations." + (" (Warnings are extras or cosmetic differences.)" if warnings else ""))
    return 0


def cmd_apply(args, backend, migrations, out):
    mode = "DRY RUN - nothing will be changed" if args.dry_run else "applying"
    out(f"MIGRATE  ({mode})")
    out("=" * 50)
    try:
        results = apply_migrations(backend, migrations, dry_run=args.dry_run, adopt_existing=args.adopt_existing)
    except MigrationError as error:
        _print_results(error.results, args.dry_run, out)
        raise
    if not results:
        out("Nothing to do: the database is up to date.")
        return 0
    _print_results(results, args.dry_run, out)
    out(f"\n{'Would apply' if args.dry_run else 'Applied'} {len(results)} migration(s).")
    return 0


def _print_results(results, dry_run, out):
    for result in results:
        out(f"\n{result.migration.version} {result.migration.name}")
        for step in result.steps:
            out(f"  {_MARK.get(step.status, '?')} {step.label}" + (" (already there)" if step.status == "exists" else ""))
            if dry_run and step.status == "would":
                out("      " + step.sql.replace("\n", "\n      "))


def cmd_baseline(args, backend, migrations, out):
    out("BASELINE  (records migration 0001 only if the schema matches it)")
    out("=" * 50)
    try:
        first, differences = baseline_database(backend, migrations, accept_extras=args.accept_extras)
    except BaselineMismatch as error:
        for difference in error.differences:
            out(str(difference))
        raise
    for difference in differences:
        out(str(difference))
    out(f"\nRecorded migration {first.version} ({first.name}) in schema_migrations. No other change was made.")
    return 0


def cmd_generate(args, backend, migrations, out):
    schema = schema_from_dict(_read_snapshot(args.snapshot))
    source = emit_baseline_source(schema)
    target = Path(args.out) if args.out else TOOLS_DIR / "schema_output" / "0001_baseline.generated.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    out(f"Draft baseline written to {target}")
    out("Review it, then copy it to backend/migrations/0001_baseline.py. It was NOT installed for you.")
    return 0


def _read_snapshot(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError:
        raise SchemaToolError("The snapshot file could not be read.") from None
    except ValueError:
        raise SchemaToolError("This is not a schema snapshot file written by schema_snapshot.py.") from None


# command -> (handler, needs a database, read-only session)
COMMANDS = {
    "status": (cmd_status, True, True),
    "check": (cmd_check, True, True),
    "apply": (cmd_apply, True, False),
    "baseline": (cmd_baseline, True, False),
    "generate-baseline": (cmd_generate, False, True),
}


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0], prog="migrate.py")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="what is applied / pending (read-only)")
    check = sub.add_parser("check", help="compare the database with the migrations (read-only)")
    check.add_argument("--snapshot", help="compare a schema_snapshot.py file instead of connecting to a database")
    check.add_argument("--strict", action="store_true", help="also fail on warnings (extra tables/columns, cosmetic differences)")
    apply = sub.add_parser("apply", help="run pending migrations")
    apply.add_argument("--dry-run", action="store_true", help="show what would run; change nothing")
    apply.add_argument("--adopt-existing", action="store_true",
                       help="allow apply on a database that has tables but no migration record (skips the baseline check)")
    baseline = sub.add_parser("baseline", help="record migration 0001 on an existing database after verifying it")
    baseline.add_argument("--accept-extras", action="store_true",
                          help="proceed although the database has extra tables/columns the baseline does not describe")
    generate = sub.add_parser("generate-baseline", help="draft a baseline migration from a schema snapshot")
    generate.add_argument("--snapshot", required=True)
    generate.add_argument("--out", help="where to write the draft (default: backend/tools/schema_output/)")
    return parser


def run(argv=None, backend_factory=None, migrations_dir=None, out=print):
    args = build_parser().parse_args(argv)
    handler, needs_database, read_only = COMMANDS[args.command]
    backend = None
    try:
        migrations = load_migrations(migrations_dir)
        if needs_database and not (args.command == "check" and args.snapshot):
            backend = (backend_factory or default_backend)(read_only)
        return handler(args, backend, migrations, out)
    except BaselineMismatch as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except MigrationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except SchemaToolError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except mysql.connector.Error as error:
        print(f"ERROR: The database refused a request (error code {getattr(error, 'errno', None)}).", file=sys.stderr)
        return 2
    finally:
        if backend is not None:
            backend.close()


def main():
    try:
        code = run()
    except Exception as error:  # never show a stack trace: it can contain connection details
        print(f"ERROR: Unexpected {type(error).__name__}. Check the MYSQL_* variables and try again.", file=sys.stderr)
        code = 2
    sys.exit(code)


if __name__ == "__main__":
    main()
