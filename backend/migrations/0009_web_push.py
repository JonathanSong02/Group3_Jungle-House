"""0009: phone / browser push notifications when the AI is done (step 2 of "AI keeps running").

web_push_key -- the server's own VAPID key pair (one row), made automatically the first time it is needed, so nothing
has to be set in Railway. The private key signs a short token that proves the notifications come from this site.

web_push_subscription -- one row per browser / phone that turned notifications on: the push service address
(endpoint, plus its SHA-256 for the unique key, because endpoints can be long), the browser's public key and secret
for encrypting the message, the site address used as VAPID subject, and the notification words in the user's language
(labels, JSON). Removed with the user (ON DELETE CASCADE) or when the push service says it is gone.

The app creates both tables by itself at runtime (`web_push.ensure_tables`), so nothing breaks if this migration has
not been applied yet; applying it records the version. See backend/src/web_push.py.
"""

from migration_lib import col, fk, index, unique

DESCRIPTION = "Add web_push_key and web_push_subscription (AI-ready notifications)"


def upgrade(ctx):
    ctx.create_table("web_push_key", [
        col("web_push_key_id", "INT", null=False, auto_increment=True),
        col("private_key", "TEXT", null=False),
        col("public_key", "VARCHAR(255)", null=False),
        col("created_at", "DATETIME", null=False),
    ], primary_key="web_push_key_id", charset="utf8mb4")
    ctx.create_table("web_push_subscription", [
        col("web_push_subscription_id", "INT", null=False, auto_increment=True),
        col("user_id", "INT", null=False),
        col("endpoint_hash", "CHAR(64)", null=False),
        col("endpoint", "TEXT", null=False),
        col("p256dh", "VARCHAR(255)", null=False),
        col("auth", "VARCHAR(64)", null=False),
        col("subject", "VARCHAR(255)", null=False),
        col("labels", "TEXT", null=False),
        col("created_at", "DATETIME", null=False),
        col("last_used_at", "DATETIME"),
    ], primary_key="web_push_subscription_id", charset="utf8mb4",
        indexes=[
            unique("endpoint_hash", name="uq_web_push_subscription_endpoint"),
            index("user_id", name="idx_web_push_subscription_user"),
        ],
        foreign_keys=[
            fk("user_id", "users", "user_id", on_delete="CASCADE",
               name="fk_web_push_subscription_user"),
        ])
