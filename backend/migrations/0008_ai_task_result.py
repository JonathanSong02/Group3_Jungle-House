"""0008: saved copies of AI chat / AI quiz replies ("AI keeps running after the page is left").

ai_task_result -- the reply to one AI chat question or AI quiz generation, exactly as it was sent, per signed-in
user and the request_id the page chose. A page that was closed, put in the phone background or lost its connection
while waiting fetches it later (GET /api/ai-tasks/<request_id>). Rows older than 7 days are deleted automatically
and removed with the user (ON DELETE CASCADE). See backend/src/ai_task_results.py.

The app creates the table by itself at runtime (`ensure_table`), so nothing breaks if this migration has not been
applied yet; applying it records the version. It can be emptied at any time.
"""

from migration_lib import col, fk, unique

DESCRIPTION = "Add ai_task_result (saved AI replies for pages that missed them)"


def upgrade(ctx):
    ctx.create_table("ai_task_result", [
        col("ai_task_result_id", "INT", null=False, auto_increment=True),
        col("user_id", "INT", null=False),
        col("request_id", "VARCHAR(64)", null=False),
        col("kind", "VARCHAR(20)", null=False),
        col("http_status", "INT", null=False),
        col("result", "MEDIUMTEXT", null=False),
        col("created_at", "DATETIME", null=False),
    ], primary_key="ai_task_result_id", charset="utf8mb4",
        indexes=[
            unique("user_id", "request_id", name="uq_ai_task_result_request"),
        ],
        foreign_keys=[
            fk("user_id", "users", "user_id", on_delete="CASCADE",
               name="fk_ai_task_result_user"),
        ])
