"""0003: the known-device table of the device-based login lockout.

A device that has signed in to an account before gets a signed device cookie. This table links the SHA-256 hash
of that random id to the account, so a known device can have its own failure counter and is not blocked when
other people type wrong passwords (see backend/src/login_lockout.py). The raw id is never stored.

The app also creates this table by itself at runtime (`ensure_login_lockout_tables`), exactly like the other
runtime tables, so nothing breaks if this migration has not been applied yet. Applying it only records the
version and keeps `migrate.py check` free of an "extra table" warning. The failure counters reuse the existing
`login_rate_limit` table, which is already in the baseline.
"""

from migration_lib import CURRENT_TIMESTAMP, col, fk, index, unique

DESCRIPTION = "Add login_known_devices for the device-based login lockout"


def upgrade(ctx):
    ctx.create_table("login_known_devices", [
        col("known_device_id", "INT", null=False, auto_increment=True),
        col("user_id", "INT", null=False),
        col("device_hash", "CHAR(64)", null=False),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("last_seen_at", "DATETIME", null=False),
        col("expires_at", "DATETIME", null=False),
    ], primary_key="known_device_id", charset="utf8mb4",
        indexes=[
            unique("user_id", "device_hash", name="uq_login_known_devices_user_device"),
            index("expires_at", name="idx_login_known_devices_expires_at"),
        ],
        foreign_keys=[
            fk("user_id", "users", "user_id", on_delete="CASCADE", name="fk_login_known_devices_user"),
        ])
