"""0010: private member-message attachments (equivalent to mysql/message_attachments.sql).

Apply with the reviewed migration runner against the intended database.
The app does not run DDL; text messages remain available before this migration.
"""
from migration_lib import col, index

DESCRIPTION = "Add private member-message attachment metadata"


def upgrade(ctx):
    ctx.create_table("message_attachments", [
        col("attachment_id", "CHAR(64)", null=False),
        col("message_id", "INT", null=False),
        col("storage_name", "VARCHAR(100)", null=False),
        col("original_name", "VARCHAR(255)", null=False),
        col("mime_type", "VARCHAR(100)", null=False),
        col("byte_size", "INT UNSIGNED", null=False),
    ], primary_key="attachment_id", charset="utf8mb4",
        indexes=[index("message_id", name="idx_message_attachments_message")])
