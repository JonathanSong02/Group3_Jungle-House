"""Image index metadata and owner/chat-scoped attachments. Apply explicitly, never on request."""
from migration_lib import CURRENT_TIMESTAMP, col, index

DESCRIPTION = "Add versioned image indexing and private chat attachment references"


def upgrade(ctx):
    for column in [col("image_hash", "CHAR(64)"), col("source_hash", "CHAR(64)"),
                   col("indexed_at", "DATETIME"), col("index_error", "VARCHAR(100)")]:
        ctx.add_column("image_retrieval", column)
    ctx.add_index("image_retrieval", index("source_type", "source_id", name="idx_image_source"))
    ctx.add_index("image_retrieval", index("embedding_model", "image_hash", name="idx_image_model_hash"))
    ctx.create_table("chat_attachments", [
        col("attachment_id", "CHAR(64)", null=False),
        col("owner_id", "INT", null=False),
        col("chat_key", "VARCHAR(96)", null=False),
        col("storage_name", "VARCHAR(255)", null=False),
        col("mime_type", "VARCHAR(100)", null=False),
        col("image_hash", "CHAR(64)", null=False),
        col("observations", "TEXT"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("expires_at", "DATETIME", null=False),
    ], primary_key="attachment_id", charset="utf8mb4", indexes=[
        index("owner_id", "chat_key", "created_at", name="idx_chat_attachment_owner"),
        index("storage_name", name="idx_chat_attachment_file"),
        index("expires_at", name="idx_chat_attachment_expiry"),
    ])
