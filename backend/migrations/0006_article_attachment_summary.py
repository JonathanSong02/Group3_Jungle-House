"""0006: a one-time AI summary for each PDF / Word attachment (article_attachment_text.summary).

When an attachment's text is extracted, the AI writes a short summary of the whole document once; it is stored
here and reused for every chat question ("what is this manual about?"), so the document is never re-sent to the
AI. A summary is filled in later if the AI was not available at extraction time.

The app adds this column by itself at runtime (`document_text_service.ensure_table`, guarded by SHOW COLUMNS),
so nothing breaks if this migration has not been applied yet. Applying it only records the version.
"""

from migration_lib import col

DESCRIPTION = "Add article_attachment_text.summary (one-time AI summary of each attachment)"


def upgrade(ctx):
    ctx.add_column("article_attachment_text", col("summary", "TEXT"))
