"""0005: text of PDF / Word article attachments, for the AI chat.

One row per (article, attached file). The text is extracted on the server with free libraries (pypdf,
python-docx), never by an AI call, when an article is added or edited, and once for older articles shortly after
the app starts (see backend/src/document_text_service.py). The AI chat reads only the passages that match a
question, inside its existing context limit.

The app also creates this table by itself at runtime (`document_text_service.ensure_table`), exactly like the
other runtime tables, so nothing breaks if this migration has not been applied yet. Applying it only records the
version and keeps `migrate.py check` free of an "extra table" warning. Deleting an article permanently removes its
rows (ON DELETE CASCADE); the table can also be emptied at any time and is rebuilt from the files.
"""

from migration_lib import col, fk, unique

DESCRIPTION = "Add article_attachment_text (extracted PDF / Word attachment text for the AI chat)"


def upgrade(ctx):
    ctx.create_table("article_attachment_text", [
        col("attachment_text_id", "INT", null=False, auto_increment=True),
        col("article_id", "INT", null=False),
        col("file_url", "VARCHAR(512)", null=False),
        col("file_hash", "CHAR(64)", null=False, default=""),
        col("status", "VARCHAR(20)", null=False),
        col("text", "MEDIUMTEXT"),
        col("extracted_at", "DATETIME", null=False),
    ], primary_key="attachment_text_id", charset="utf8mb4",
        indexes=[
            unique("article_id", "file_url", name="uq_article_attachment_text_file"),
        ],
        foreign_keys=[
            fk("article_id", "wiki_article", "article_id", on_delete="CASCADE",
               name="fk_article_attachment_text_article"),
        ])
