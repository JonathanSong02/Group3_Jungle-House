"""0002 (optional): the two indexes that mysql/escalation.sql defines but production does not have.

Nothing needs this. Production works without it and the baseline (0001) deliberately does NOT contain these
indexes, because production is the source of truth. They only speed up filtering the escalation list by
status and sorting it by date, which matters once the table is large.

It only adds an index when no index on those columns exists yet (ALTER TABLE ... ADD KEY, which InnoDB builds
in place without blocking reads or writes). It changes no data and no column. Migrations run in order, so the
next `migrate.py apply` runs it; `migrate.py apply --dry-run` shows the exact statements first.
"""

from migration_lib import index

DESCRIPTION = "Optional: add idx_status and idx_created_at to escalation if they are missing"


def upgrade(ctx):
    ctx.add_index("escalation", index("status", name="idx_status"))
    ctx.add_index("escalation", index("created_at", name="idx_created_at"))
