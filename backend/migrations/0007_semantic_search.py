"""0007: meaning-based article search ("看意思") and its accuracy-check questions.

article_chunk_embedding -- every live article (and the readable text of its PDF / Word attachments) cut into short
sections, each with Google's embedding (a list of numbers describing its meaning, stored as float32 bytes). The chat
compares a question's embedding with these to find articles that mean the same thing even with other words. Rows
are re-made only when an article's text changes (content_hash) and removed with the article (ON DELETE CASCADE).
See backend/src/semantic_search.py.

retrieval_audit_question -- one AI-written test question per article, in staff wording with different words than
the article, plus the sentence of the article that answers it (quote). Used only by "Check search accuracy" on the
AI Model Settings page; re-written when the article changes. See backend/src/retrieval_audit.py.

The app creates both tables by itself at runtime (`ensure_table`), so nothing breaks if this migration has not been
applied yet; applying it records the version. Both can be emptied at any time and are rebuilt automatically.
"""

from migration_lib import col, fk, unique

DESCRIPTION = "Add article_chunk_embedding (meaning search) and retrieval_audit_question (accuracy check)"


def upgrade(ctx):
    ctx.create_table("article_chunk_embedding", [
        col("chunk_embedding_id", "INT", null=False, auto_increment=True),
        col("article_id", "INT", null=False),
        col("chunk_index", "INT", null=False),
        col("source", "VARCHAR(20)", null=False),
        col("content_hash", "CHAR(64)", null=False),
        col("model", "VARCHAR(64)", null=False),
        col("chunk_text", "TEXT", null=False),
        col("vector", "MEDIUMBLOB", null=False),
        col("created_at", "DATETIME", null=False),
    ], primary_key="chunk_embedding_id", charset="utf8mb4",
        indexes=[
            unique("article_id", "chunk_index", name="uq_article_chunk_embedding"),
        ],
        foreign_keys=[
            fk("article_id", "wiki_article", "article_id", on_delete="CASCADE",
               name="fk_article_chunk_embedding_article"),
        ])
    ctx.create_table("retrieval_audit_question", [
        col("audit_question_id", "INT", null=False, auto_increment=True),
        col("article_id", "INT", null=False),
        col("content_hash", "CHAR(64)", null=False),
        col("question", "VARCHAR(500)", null=False),
        col("quote", "TEXT", null=False),
        col("created_at", "DATETIME", null=False),
    ], primary_key="audit_question_id", charset="utf8mb4",
        indexes=[
            unique("article_id", name="uq_retrieval_audit_question_article"),
        ],
        foreign_keys=[
            fk("article_id", "wiki_article", "article_id", on_delete="CASCADE",
               name="fk_retrieval_audit_question_article"),
        ])
