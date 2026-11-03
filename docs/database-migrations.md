# Database migrations: setup guide (Phase 1)

Phase 1 adds a **record** of the schema version, a **baseline** that describes the production database as it is,
a safe **runner**, and a read-only **drift check**. It does not change how the live site starts or runs, and the
app's own runtime table creation is untouched. What the code creates today, and how production differs from the
old SQL scripts, is in [database-schema.md](database-schema.md).

**Production is the source of truth.** `0001_baseline.py` was generated from a read-only snapshot of production
(2026-11-03, MySQL 9.7.2, 36 tables) and reviewed by hand. The tools never change production to match it.

| Piece | Where |
|---|---|
| Migration files (numbered) | `backend/migrations/0001_baseline.py` (production as it is), `0002_escalation_indexes.py` (optional) |
| Command line tool | `backend/tools/migrate.py` (`status`, `check`, `apply`, `baseline`, `generate-baseline`) |
| Read-only snapshot tool | `backend/tools/schema_snapshot.py` |
| Shared code | `backend/tools/migration_lib.py`, `backend/tools/schema_lib.py` |
| Version record | table `schema_migrations` (`version`, `name`, `checksum`, `applied_at`), the only table these tools create themselves |
| Tests | `backend/src/test_schema_migrations.py` |

The tools use the same `MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE` variables as the
backend, print no credentials and no stack traces, and are **never** started by the app, the `Procfile` or the
Railway start command.

## Rules a migration must follow

* Only **additive** operations exist: `create_table`, `add_column`, `add_index`, `add_foreign_key`. There is no
  drop, rename, modify, truncate or data change, so a migration cannot lose data.
* Each operation looks at the live schema first and does nothing if its result is already there, so a
  migration is **safe to run twice**.
* MySQL commits every `CREATE`/`ALTER` immediately (no rollback). If a migration stops half-way, what finished
  stays, the migration is **not** recorded as applied, and running it again finishes the rest.
* A migration file never changes after it has been applied (its checksum is stored). To fix something,
  add the next number.
* A new `NOT NULL` column needs a default so existing rows stay valid.

## A. Look at production (read-only), then send the file back

Run from the repository root, the same way you ran `notion_duplicate_report.py`:

```powershell
# structure only: no row data, no credentials, no host or database name in the file
railway run python backend/tools/schema_snapshot.py --out schema_production.json --label production
```

It sets the session read-only and refuses any statement that is not `SELECT`/`SHOW`. Open the file and look at
it before you send it. **Do not commit it.** (On the machine where it was first saved it is listed in `.git/info/exclude`,
which is local to that clone, so other clones must keep it out of `git add` themselves.)
Without `--out` it writes to `backend/tools/schema_output/` (ignored by git).

## B. Compare a snapshot with the migrations (no database needed)

```powershell
python backend/tools/migrate.py check --snapshot schema_production.json
```

Prints every `missing table`, `missing/extra column`, `different type`, `missing unique index`,
`missing foreign key` as `[ERROR]` (something the migrations promise is not there or differs) or
`[WARNING]` (extra items, cosmetic differences). Exit code 0 = no errors, 1 = differences.

A database with no migration record is compared with the baseline (0001) only; later migrations such as the
optional 0002 are "not applied yet", not drift. For the production snapshot of 2026-11-03 the result is
`0 difference(s), 0 warning(s)`.

## C. A new, empty database (staging, a teammate's machine)

```powershell
# in a PowerShell window used only for this: point MYSQL_* at the NEW database
python backend/tools/migrate.py apply --dry-run     # shows every statement, changes nothing
python backend/tools/migrate.py apply               # builds all 36 tables, adds the 0002 indexes, records both
python backend/tools/migrate.py check               # should say: Schema matches the migrations.
```

## D. The existing production database (once)

```powershell
railway run python backend/tools/migrate.py check       # read-only: must show no [ERROR] and no [WARNING]
railway run python backend/tools/migrate.py baseline    # records 0001 ONLY if the schema matches it
railway run python backend/tools/migrate.py status      # 0001 applied, 0002 PENDING
```

`baseline` changes nothing except creating `schema_migrations` and inserting one row. If the schema differs
it stops, lists every difference and writes nothing. `--accept-extras` lets it continue when the only
differences are extra tables/columns that the baseline does not know about.
`apply` on a database that has tables but no record refuses and points you to `baseline`
(`apply --adopt-existing` skips that check, use it only on a throwaway database).

**Migration 0002 is optional.** It adds `idx_status` and `idx_created_at` to `escalation` only if they are
missing (production has neither). It is not in the baseline. See what it would do before deciding:

```powershell
railway run python backend/tools/migrate.py apply --dry-run
```

Migrations are applied in order, so the next `apply` runs 0002; if you never run `apply` nothing changes. It is
two `ALTER TABLE ... ADD KEY` statements and touches no data. Once it is recorded, `check` also expects the two
indexes.

## E. Adding a migration

Create `backend/migrations/0003_short_name.py` (next number, no gaps):

```python
from migration_lib import col, index

DESCRIPTION = "Why this change exists"


def upgrade(ctx):
    ctx.add_column("quiz", col("retake_allowed", "TINYINT(1)", null=False, default=1))
    ctx.add_index("ai_chat_log", index("user_id", name="idx_ai_chat_log_user"))
```

Then `python backend/tools/migrate.py apply --dry-run`, review the statements, `apply`, and run
`python -m unittest test_schema_migrations` from `backend/src`. The test suite also fails if the code
starts using a table that no migration creates.

## Commands and exit codes

| Command | Reads / writes | Notes |
|---|---|---|
| `migrate.py status` | read-only | applied / PENDING / CHANGED / FILE MISSING |
| `migrate.py check [--snapshot F] [--strict]` | read-only | compares with the **applied** migrations (the baseline only, if nothing is recorded); `--strict` also fails on warnings |
| `migrate.py apply [--dry-run] [--adopt-existing]` | writes (additive) | takes the lock `jungle_house_schema_migrate`; stops at the first failure |
| `migrate.py baseline [--accept-extras]` | writes `schema_migrations` only | verifies first, see D |
| `migrate.py generate-baseline --snapshot F [--out F]` | writes a local file | drafts a baseline from a snapshot; never installs it |

Exit codes: `0` fine, `1` a problem was found (drift, failed or changed migration), `2` it could not run
(bad variables, database unreachable).

Messages you may see: `Database is not reachable. Check the MYSQL_* variables.` ·
`Migration 0003 has changed since it was applied.` · `Schema differs from the baseline (…)` ·
`Another migration runner is already running.` · `Migration 0002 (name) stopped: … It is NOT recorded as applied`.

## What the baseline does not capture

A snapshot lists tables, columns (type, null, default, auto-increment, ON UPDATE), indexes and foreign keys. It does
not capture check constraints, column comments or per-column collations (production has no views, triggers,
routines or events). If any of those matter later, add them by hand in a new migration; `check` cannot see them.
The tables that exist only in production, and which of them the code uses, are listed in
[database-schema.md](database-schema.md), section 4. If production changes, take a new snapshot and run `check`
before recording anything.

## MySQL 9: what was and was not verified

Production runs **MySQL 9.7.2**, so the throwaway test database below is MySQL 9, not 8.

Checked without a server (tests `GeneratedDdlTests` and `ProductionSnapshotTests`, plus a grammar check of all 39
generated statements with a MySQL-dialect parser):

* every statement is a plain `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... ADD`, and every table ends with
  `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`;
* every foreign key points at a whole primary key or unique index with exactly the same column type (MySQL 8.4+
  refuses anything else), and both tables are InnoDB;
* no integer display widths (other than `TINYINT(1)`), no literal default on a TEXT/BLOB column, every
  AUTO_INCREMENT column is the first column of a key, names are at most 64 characters, no TEXT column sits in an
  index, keys stay under 3072 bytes and rows under 65535 bytes;
* all identifiers are back-quoted, so reserved words such as `type`, `status` or `action` are safe;
* replaying the baseline reproduces the production snapshot exactly, including index and constraint names and
  column order, and applying it to production would execute nothing.

**Not verified:** that a real MySQL 9 server accepts the statements. No MySQL server was available where this was
written. Do the scratch run below before relying on a from-scratch build.

## Testing on a scratch MySQL 9 (not done yet)

The unit tests use an in-memory database, so they prove the logic (ordering, checksums, lock, failure
handling, drift detection, read-only snapshot) but **not** that MySQL accepts the generated DDL or that a
from-scratch build behaves. Do this once on a throwaway MySQL 9 (Docker shown; any empty MySQL 9 works).
Use a separate PowerShell window and never copy these values into Railway, Vercel or a `.env` file:

```powershell
# mysql:9 is the latest 9.x; use mysql:9.7 (production reports 9.7.2) if that tag exists
docker run --name jh-scratch -e MYSQL_ROOT_PASSWORD=scratch-only -e MYSQL_DATABASE=jh_scratch -p 3307:3306 -d mysql:9
$env:MYSQL_HOST = "127.0.0.1"; $env:MYSQL_PORT = "3307"; $env:MYSQL_USER = "root"
$env:MYSQL_PASSWORD = "scratch-only"; $env:MYSQL_DATABASE = "jh_scratch"

python backend/tools/migrate.py apply --dry-run      # 38 statements: 36 tables and the 2 indexes of 0002
python backend/tools/migrate.py apply                # builds all tables; expect: Applied 2 migration(s)
python backend/tools/migrate.py check                # expect: 0 difference(s), 0 warning(s); anything else is a finding
python backend/tools/migrate.py apply                # expect: Nothing to do
python backend/tools/schema_snapshot.py --out scratch.json
python backend/tools/migrate.py check --snapshot scratch.json
```

Then exercise the parts the unit tests cannot:

1. **Baseline path:** `docker exec jh-scratch mysql -uroot -pscratch-only jh_scratch -e "DROP TABLE schema_migrations"`,
   then `migrate.py baseline --accept-extras`: it must record 0001, change nothing else, and report exactly two
   warnings (the 0002 indexes on `escalation`, which the baseline does not have).
2. **Runtime code on top:** start the backend against this database and open a few pages (login, chat, quizzes,
   Notion Sync status). Then `migrate.py check` again: the app's own `ensure_*` calls must not have produced new
   differences. This is the real proof that the baseline and the runtime DDL agree.
3. **Lock:** run `apply` in two PowerShell windows at once; one must print `Another migration runner is already
   running.`
4. **Half-way failure:** in a scratch copy of a migration, make the second statement fail (e.g. reference a missing
   table), run `apply`, confirm that migration is not in `status`, fix it, run `apply` again.

Remove it afterwards: `docker rm -f jh-scratch`. If a table fails with a foreign-key error, check
`SHOW CREATE TABLE users` on the scratch server: the migrations assume `users.user_id`, `escalation.escalation_id`
etc. are signed `INT`.

## Phase 2 proposal (not implemented)

Goal: stop changing the schema while requests are being served, and know the version before the new code runs.

1. **Record the baseline first.** `baseline` on production and on staging, `check` clean on both. Nothing below
   starts before that.
2. **2a, warn only.** At startup, read `MAX(version)` from `schema_migrations` and log one line if it is older than
   the newest migration file. No behaviour change, so it cannot take the site down.
3. **2b, apply before deploy.** Add `python tools/migrate.py apply` to Railway's `preDeployCommand` (next to or
   replacing `migrate_escalation_context.py`). The pre-deploy step runs before the new version receives traffic, the
   database lock prevents two deploys from racing, and a failed migration fails the deploy instead of the site.
4. **2c, retire runtime DDL one function at a time.** Each `ensure_*` already has its table in the baseline. Replace
   the body with "check the version, otherwise raise a clear error", one feature per change, each with a test,
   starting with the rarely used ones (`ensure_chat_cancel_table`, `ensure_login_rate_limit_table`) and finishing
   with Notion Sync, which is also driven by a background thread. Delete the dead `ensure_registration_keys_table`.
5. **Non-additive changes** (changing a type, dropping a column, `CONVERT TO CHARACTER SET`) get their own explicit,
   reviewed operation and a rollback note. They are not available in Phase 1 on purpose. Prefer "expand, deploy,
   contract" over in-place changes. Unused production tables (`chat_session`, `escalation_tickets`, `registration_keys`)
   should only ever be dropped that way, after a backup and a separate decision.
6. **Risks to settle before 2c:** workers or tools that start before the pre-deploy step finishes; databases that
   were never baselined (the check must fail loudly rather than guess); the dashboard's `ai_response` query
   (a table production does not have) should be fixed in code, not by adding the table.
