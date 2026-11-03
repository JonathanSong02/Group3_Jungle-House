"""0001 baseline: the production database as it is today (MySQL 9.7.2, read-only snapshot of 2026-11-03).

Production is the source of truth. This file was generated from that snapshot with
`migrate.py generate-baseline`, then reviewed and organised by hand. It DESCRIBES what production has; it
never asks production to change. Where production differs from the old SQL scripts in mysql/, production
wins (see the note above each table).

Every operation only adds what is missing, so running this on a database that already has these tables
does nothing, and on an empty database it builds the whole schema. `migrate.py baseline` records it on a
database only after checking that the schema matches.

A snapshot does not capture check constraints, column comments or per-column collations. Production has no
views, triggers, routines or events. After `baseline` has been recorded on any database this file must not
change again (its checksum is stored): add 0002, 0003 ... instead.
"""

from migration_lib import CURRENT_TIMESTAMP, col, fk, index, unique

DESCRIPTION = "Baseline: the production database as of 2026-11-03"


def upgrade(ctx):
    # ------------------------------------------------------------------
    # Accounts and security
    # ------------------------------------------------------------------

    # roles: script (mysql/Query1.sql). Same as production.
    ctx.create_table("roles", [
        col("role_id", "INT", null=False, auto_increment=True),
        col("role_name", "VARCHAR(30)", null=False),
    ], primary_key="role_id", charset="utf8mb4",
        indexes=[
            unique("role_name", name="role_name"),
        ])

    # users: script (mysql/Query1.sql), but production differs: status is ENUM('pending','active','inactive','declined') with
    # default 'pending' (the script has active/inactive, default 'active'). Registration approval needs pending/declined.
    ctx.create_table("users", [
        col("user_id", "INT", null=False, auto_increment=True),
        col("full_name", "VARCHAR(100)", null=False),
        col("email", "VARCHAR(120)", null=False),
        col("password_hash", "VARCHAR(255)", null=False),
        col("role_id", "INT", null=False),
        col("status", "ENUM('pending','active','inactive','declined')", null=False, default="pending"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
    ], primary_key="user_id", charset="utf8mb4",
        indexes=[
            unique("email", name="email"),
            index("role_id", name="role_id"),
        ],
        foreign_keys=[
            fk("role_id", "roles", "role_id", name="users_ibfk_1"),
        ])

    # registration_keys: script (mysql/Query1.sql). No code uses it any more (registration keys were removed); it only exists in
    # production and the script. Its foreign keys to users have no ON DELETE rule.
    ctx.create_table("registration_keys", [
        col("key_id", "INT", null=False, auto_increment=True),
        col("key_code", "VARCHAR(100)", null=False),
        col("allowed_role_id", "INT", null=False),
        col("created_by", "INT", null=False),
        col("is_used", "TINYINT(1)", null=False, default=0),
        col("is_active", "TINYINT(1)", null=False, default=1),
        col("used_by", "INT"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("used_at", "TIMESTAMP"),
        col("expires_at", "TIMESTAMP"),
    ], primary_key="key_id", charset="utf8mb4",
        indexes=[
            index("allowed_role_id", name="allowed_role_id"),
            index("created_by", name="created_by"),
            unique("key_code", name="key_code"),
            index("used_by", name="used_by"),
        ],
        foreign_keys=[
            fk("allowed_role_id", "roles", "role_id", name="registration_keys_ibfk_1"),
            fk("created_by", "users", "user_id", name="registration_keys_ibfk_2"),
            fk("used_by", "users", "user_id", name="registration_keys_ibfk_3"),
        ])

    # staff_registration_keys: created long ago by ensure_registration_keys_table, which nothing calls now (the endpoints return 410). The code only
    # cleans it up when a declined account is removed. Production quirk, kept as is: assigned_email has the text 'NULL' as default.
    ctx.create_table("staff_registration_keys", [
        col("key_id", "INT", null=False, auto_increment=True),
        col("key_code", "VARCHAR(10)", null=False),
        col("status", "ENUM('unused','used','revoked')", null=False, default="unused"),
        col("created_by_user_id", "INT"),
        col("used_by_user_id", "INT"),
        col("used_by_email", "VARCHAR(255)"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("used_at", "DATETIME"),
        col("revoked_at", "DATETIME"),
        col("assigned_email", "VARCHAR(255)", default="NULL"),
        col("assigned_at", "DATETIME"),
        col("email_sent_at", "DATETIME"),
        col("failed_attempts", "INT", null=False, default=0),
        col("last_failed_at", "DATETIME"),
    ], primary_key="key_id", charset="utf8mb4",
        indexes=[
            index("created_by_user_id", name="fk_staff_registration_keys_created_by"),
            index("used_by_user_id", name="fk_staff_registration_keys_used_by"),
            index("status", name="idx_staff_registration_keys_status"),
            unique("key_code", name="key_code"),
        ],
        foreign_keys=[
            fk("created_by_user_id", "users", "user_id", on_delete="SET NULL", name="fk_staff_registration_keys_created_by"),
            fk("used_by_user_id", "users", "user_id", on_delete="SET NULL", name="fk_staff_registration_keys_used_by"),
        ])

    # email_verifications: production only. No code in the repo creates it; app.py only deletes a user's rows from it when a declined account is removed.
    ctx.create_table("email_verifications", [
        col("verification_id", "INT", null=False, auto_increment=True),
        col("user_id", "INT", null=False),
        col("email", "VARCHAR(255)", null=False),
        col("token_hash", "CHAR(64)", null=False),
        col("expires_at", "DATETIME", null=False),
        col("verified_at", "DATETIME"),
        col("used_at", "DATETIME"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
    ], primary_key="verification_id", charset="utf8mb4",
        indexes=[
            index("email", name="idx_email_verifications_email"),
            index("token_hash", name="idx_email_verifications_token_hash"),
            index("user_id", name="idx_email_verifications_user_id"),
        ],
        foreign_keys=[
            fk("user_id", "users", "user_id", on_delete="CASCADE", name="fk_email_verifications_user"),
        ])

    # password_reset_tokens: runtime: app.py ensure_password_reset_tokens_table.
    ctx.create_table("password_reset_tokens", [
        col("reset_id", "INT", null=False, auto_increment=True),
        col("user_id", "INT", null=False),
        col("token_hash", "CHAR(64)", null=False),
        col("expires_at", "DATETIME", null=False),
        col("used_at", "DATETIME"),
        col("requested_ip", "VARCHAR(64)"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
    ], primary_key="reset_id", charset="utf8mb4",
        indexes=[
            index("expires_at", name="idx_password_reset_expires_at"),
            index("token_hash", name="idx_password_reset_token_hash"),
            index("user_id", name="idx_password_reset_user_id"),
            unique("token_hash", name="token_hash"),
        ],
        foreign_keys=[
            fk("user_id", "users", "user_id", on_delete="CASCADE", name="fk_password_reset_user"),
        ])

    # login_history: script (mysql/Query1.sql), but production differs: user_id is nullable (failed logins for unknown emails) and
    # email / full_name were added by hand (app.py record_login_history writes them).
    ctx.create_table("login_history", [
        col("login_id", "INT", null=False, auto_increment=True),
        col("user_id", "INT"),
        col("email", "VARCHAR(120)"),
        col("full_name", "VARCHAR(100)"),
        col("login_time", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("login_status", "ENUM('success','failed')", null=False),
        col("ip_address", "VARCHAR(45)"),
        col("device_info", "VARCHAR(255)"),
    ], primary_key="login_id", charset="utf8mb4",
        indexes=[
            index("user_id", name="user_id"),
        ],
        foreign_keys=[
            fk("user_id", "users", "user_id", name="login_history_ibfk_1"),
        ])

    # login_rate_limit: runtime: app.py ensure_login_rate_limit_table.
    ctx.create_table("login_rate_limit", [
        col("rate_key", "CHAR(64)", null=False),
        col("failed_attempts", "INT", null=False, default=0),
        col("window_started_at", "DATETIME"),
        col("blocked_until", "DATETIME"),
        col("updated_at", "TIMESTAMP", default=CURRENT_TIMESTAMP, on_update="CURRENT_TIMESTAMP"),
    ], primary_key="rate_key", charset="utf8mb4",
        indexes=[
            index("blocked_until", name="idx_login_rate_limit_blocked_until"),
        ])

    # declined_registration_history: runtime: app.py ensure_declined_registration_history_table.
    ctx.create_table("declined_registration_history", [
        col("history_id", "BIGINT", null=False, auto_increment=True),
        col("user_id", "INT", null=False),
        col("full_name", "VARCHAR(255)", null=False),
        col("email", "VARCHAR(255)", null=False),
        col("originally_registered_at", "DATETIME"),
        col("declined_at", "DATETIME"),
        col("declined_by_user_id", "INT"),
        col("declined_by_name", "VARCHAR(255)"),
        col("decision_description", "TEXT"),
        col("archived_at", "TIMESTAMP", null=False, default=CURRENT_TIMESTAMP),
    ], primary_key="history_id", charset="utf8mb4",
        indexes=[
            index("email", name="idx_declined_history_email"),
            index("user_id", name="idx_declined_history_user"),
        ])

    # audit_log: production only, used by the app (app.py add_audit_log, get_audit_logs). No script or code in the repo creates it.
    ctx.create_table("audit_log", [
        col("audit_id", "INT", null=False, auto_increment=True),
        col("actor_id", "INT"),
        col("actor_name", "VARCHAR(100)"),
        col("action", "VARCHAR(255)", null=False),
        col("module", "VARCHAR(100)"),
        col("description", "TEXT"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
    ], primary_key="audit_id", charset="utf8mb4",
        indexes=[
            index("actor_id", name="actor_id"),
        ],
        foreign_keys=[
            fk("actor_id", "users", "user_id", name="audit_log_ibfk_1"),
        ])

    # ------------------------------------------------------------------
    # Knowledge base and images
    # ------------------------------------------------------------------

    # wiki_article: script (mysql/SQL FILE 3.sql) + runtime (content MEDIUMTEXT, the Notion columns, the unique index on notion_page_id)
    # + columns added by hand (is_deleted, deleted_at, deleted_by, attachment_*, image_files, image_keywords).
    ctx.create_table("wiki_article", [
        col("article_id", "INT", null=False, auto_increment=True),
        col("title", "VARCHAR(200)"),
        col("content", "MEDIUMTEXT"),
        col("category", "VARCHAR(50)"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("link", "TEXT"),
        col("sub_category", "VARCHAR(50)"),
        col("display_order", "INT"),
        col("is_deleted", "TINYINT(1)", null=False, default=0),
        col("deleted_at", "TIMESTAMP"),
        col("deleted_by", "INT"),
        col("attachment_url", "TEXT"),
        col("attachment_type", "VARCHAR(100)"),
        col("image_files", "TEXT"),
        col("image_keywords", "TEXT"),
        col("source_type", "VARCHAR(20)", default="manual"),
        col("notion_page_id", "VARCHAR(64)"),
        col("notion_last_edited_time", "DATETIME"),
    ], primary_key="article_id", charset="utf8mb4",
        indexes=[
            unique("notion_page_id", name="idx_wiki_article_notion_page_id"),
        ])

    # article_links: script (mysql/SQL FILE 3.sql). Same as production.
    ctx.create_table("article_links", [
        col("link_id", "INT", null=False, auto_increment=True),
        col("article_id", "INT"),
        col("label", "VARCHAR(100)"),
        col("url", "TEXT"),
    ], primary_key="link_id", charset="utf8mb4",
        indexes=[
            index("article_id", name="article_id"),
        ],
        foreign_keys=[
            fk("article_id", "wiki_article", "article_id", name="article_links_ibfk_1"),
        ])

    # image_retrieval: production only, used by the app (app.py, db_helper.py). No script or code in the repo creates it.
    ctx.create_table("image_retrieval", [
        col("image_id", "INT", null=False, auto_increment=True),
        col("source_type", "VARCHAR(50)", null=False),
        col("source_id", "INT"),
        col("question", "TEXT"),
        col("answer", "TEXT"),
        col("image_url", "TEXT", null=False),
        col("image_type", "VARCHAR(100)"),
        col("image_caption", "TEXT"),
        col("image_keywords", "TEXT"),
        col("approval_status", "VARCHAR(50)", default="approved"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("image_embedding", "LONGTEXT"),
        col("embedding_model", "VARCHAR(100)"),
        col("visual_match_enabled", "TINYINT(1)", default=1),
    ], primary_key="image_id", charset="utf8mb4")

    # qa_knowledge: production only, used by the app (app.py, db_helper.py). No script or code in the repo creates it.
    ctx.create_table("qa_knowledge", [
        col("id", "INT", null=False, auto_increment=True),
        col("question", "TEXT"),
        col("answer", "TEXT"),
        col("source", "VARCHAR(50)"),
        col("confidence", "FLOAT"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("image_url", "TEXT"),
        col("image_type", "VARCHAR(100)"),
    ], primary_key="id", charset="utf8mb4")

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    # chat_session: production only and NOT used by the current code: left over from a reverted commit (bcbd1d27 added it, 9fb6b911
    # reverted it), together with ai_chat_log.session_id and idx_ai_chat_log_session.
    ctx.create_table("chat_session", [
        col("chat_session_id", "INT", null=False, auto_increment=True),
        col("user_id", "INT", null=False),
        col("client_key", "VARCHAR(64)", null=False),
        col("title", "VARCHAR(255)"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("updated_at", "TIMESTAMP", default=CURRENT_TIMESTAMP, on_update="CURRENT_TIMESTAMP"),
    ], primary_key="chat_session_id", charset="utf8mb4",
        indexes=[
            index("user_id", "updated_at", name="idx_chat_session_user_updated"),
            unique("user_id", "client_key", name="uq_chat_session_user_client"),
        ])

    # ai_chat_log: runtime: app.py ensure_ai_chat_log_table, plus session_id and idx_ai_chat_log_session from the reverted chat-session commit.
    ctx.create_table("ai_chat_log", [
        col("log_id", "INT", null=False, auto_increment=True),
        col("user_id", "INT"),
        col("question", "TEXT", null=False),
        col("title", "VARCHAR(255)"),
        col("category", "VARCHAR(100)"),
        col("article_section", "VARCHAR(100)"),
        col("response_type", "VARCHAR(50)", default="text"),
        col("score", "DECIMAL(6,4)", default=0),
        col("confidence", "DECIMAL(6,4)", default=0),
        col("confidence_label", "VARCHAR(20)"),
        col("source", "VARCHAR(100)"),
        col("fallback", "TINYINT", default=0),
        col("fallback_message", "TEXT"),
        col("escalation_ready", "TINYINT", default=0),
        col("reply", "MEDIUMTEXT"),
        col("error", "TEXT"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("session_id", "INT"),
    ], primary_key="log_id", charset="utf8mb4",
        indexes=[
            index("category", name="idx_ai_chat_log_category"),
            index("created_at", name="idx_ai_chat_log_created_at"),
            index("escalation_ready", name="idx_ai_chat_log_escalation"),
            index("fallback", name="idx_ai_chat_log_fallback"),
            index("session_id", name="idx_ai_chat_log_session"),
            index("source", name="idx_ai_chat_log_source"),
        ])

    # chat_cancelled_requests: runtime: app.py ensure_chat_cancel_table.
    ctx.create_table("chat_cancelled_requests", [
        col("request_id", "VARCHAR(64)", null=False),
        col("cancelled_at", "DATETIME", null=False, default=CURRENT_TIMESTAMP),
    ], primary_key="request_id", charset="utf8mb4")

    # ------------------------------------------------------------------
    # Escalation and review
    # ------------------------------------------------------------------

    # escalation: script (mysql/escalation.sql), but production differs: it has no idx_status / idx_created_at (migration 0002 can add
    # them) and has extra columns added by hand (image_url, image_type, is_deleted, deleted_at, deleted_by).
    ctx.create_table("escalation", [
        col("escalation_id", "INT", null=False, auto_increment=True),
        col("question", "TEXT", null=False),
        col("ai_answer", "TEXT"),
        col("ai_score", "DECIMAL(6,4)", default=0),
        col("ai_source", "VARCHAR(100)"),
        col("manual_answer", "TEXT"),
        col("asked_by", "INT"),
        col("handled_by", "INT"),
        col("status", "ENUM('pending','reviewing','resolved')", null=False, default="pending"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("updated_at", "TIMESTAMP", default=CURRENT_TIMESTAMP, on_update="CURRENT_TIMESTAMP"),
        col("resolved_at", "TIMESTAMP"),
        col("image_url", "VARCHAR(500)"),
        col("image_type", "VARCHAR(100)"),
        col("is_deleted", "TINYINT(1)", null=False, default=0),
        col("deleted_at", "DATETIME"),
        col("deleted_by", "INT"),
    ], primary_key="escalation_id", charset="utf8mb4",
        indexes=[
            index("asked_by", name="asked_by"),
            index("handled_by", name="handled_by"),
        ],
        foreign_keys=[
            fk("asked_by", "users", "user_id", on_delete="SET NULL", name="escalation_ibfk_1"),
            fk("handled_by", "users", "user_id", on_delete="SET NULL", name="escalation_ibfk_2"),
        ])

    # escalation_tickets: production only and NOT used: nothing in the repo or its git history mentions it.
    ctx.create_table("escalation_tickets", [
        col("id", "INT", null=False, auto_increment=True),
        col("question", "TEXT"),
        col("ai_response", "TEXT"),
        col("status", "VARCHAR(20)", default="pending"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("resolved_at", "TIMESTAMP"),
    ], primary_key="id", charset="utf8mb4")

    # escalation_context: created by the Railway pre-deploy step: backend/src/migrate_escalation_context.py.
    ctx.create_table("escalation_context", [
        col("escalation_id", "INT", null=False),
        col("conversation_id", "VARCHAR(96)", null=False),
        col("issue_id", "VARCHAR(96)", null=False),
        col("context_json", "MEDIUMTEXT", null=False),
        col("created_at", "TIMESTAMP", null=False, default=CURRENT_TIMESTAMP),
    ], primary_key="escalation_id", charset="utf8mb4",
        foreign_keys=[
            fk("escalation_id", "escalation", "escalation_id", on_delete="CASCADE", name="fk_escalation_context_ticket"),
        ])

    # review_queue: script (mysql/review queue.sql), but production differs: status is VARCHAR(30), not an ENUM.
    ctx.create_table("review_queue", [
        col("review_id", "INT", null=False, auto_increment=True),
        col("escalation_id", "INT"),
        col("question", "TEXT", null=False),
        col("answer", "TEXT", null=False),
        col("submitted_by", "INT"),
        col("reviewed_by", "INT"),
        col("status", "VARCHAR(30)", null=False, default="pending"),
        col("reviewer_comment", "TEXT"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("reviewed_at", "TIMESTAMP"),
        col("published_at", "TIMESTAMP"),
    ], primary_key="review_id", charset="utf8mb4",
        indexes=[
            index("escalation_id", name="escalation_id"),
            index("reviewed_by", name="reviewed_by"),
            index("submitted_by", name="submitted_by"),
        ],
        foreign_keys=[
            fk("escalation_id", "escalation", "escalation_id", name="review_queue_ibfk_1"),
            fk("submitted_by", "users", "user_id", name="review_queue_ibfk_2"),
            fk("reviewed_by", "users", "user_id", name="review_queue_ibfk_3"),
        ])

    # ------------------------------------------------------------------
    # Messages and notifications
    # ------------------------------------------------------------------

    # notification: script (mysql/notification.sql), but production differs: the text column is called detail (no message), user_id is
    # nullable with no foreign key, and the table has target_role / related_id / created_by and a wider type ENUM.
    ctx.create_table("notification", [
        col("notification_id", "INT", null=False, auto_increment=True),
        col("user_id", "INT"),
        col("target_role", "ENUM('manager','teamlead','staff','all')"),
        col("title", "VARCHAR(255)", null=False),
        col("detail", "TEXT", null=False),
        col("type", "ENUM('announcement','message','escalation','quiz','review','system')", null=False, default="system"),
        col("related_id", "INT"),
        col("is_read", "TINYINT(1)", null=False, default=0),
        col("created_by", "INT"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
    ], primary_key="notification_id", charset="utf8mb4",
        indexes=[
            index("is_read", name="idx_is_read"),
            index("target_role", name="idx_target_role"),
            index("type", name="idx_type"),
            index("user_id", name="idx_user_id"),
        ])

    # notification_user_reads: runtime: app.py ensure_notification_user_reads_table.
    ctx.create_table("notification_user_reads", [
        col("notification_id", "BIGINT", null=False),
        col("user_id", "BIGINT", null=False),
        col("read_at", "TIMESTAMP", null=False, default=CURRENT_TIMESTAMP),
    ], primary_key=("notification_id", "user_id"), charset="utf8mb4",
        indexes=[
            index("user_id", name="idx_notification_user_reads_user_id"),
        ])

    # user_message: script (mysql/message.sql) + columns added by hand for threads and per-side delete (thread_id, parent_message_id,
    # is_deleted_by_sender, is_deleted_by_receiver, edited_at).
    ctx.create_table("user_message", [
        col("message_id", "INT", null=False, auto_increment=True),
        col("thread_id", "INT"),
        col("parent_message_id", "INT"),
        col("sender_id", "INT", null=False),
        col("receiver_id", "INT", null=False),
        col("subject", "VARCHAR(255)", null=False),
        col("message", "TEXT", null=False),
        col("is_read", "TINYINT(1)", null=False, default=0),
        col("is_deleted_by_sender", "TINYINT(1)", null=False, default=0),
        col("is_deleted_by_receiver", "TINYINT(1)", null=False, default=0),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("edited_at", "TIMESTAMP"),
    ], primary_key="message_id", charset="utf8mb4",
        indexes=[
            index("is_read", name="idx_is_read"),
            index("receiver_id", name="idx_receiver_id"),
            index("sender_id", name="idx_sender_id"),
        ])

    # ------------------------------------------------------------------
    # Quizzes
    # ------------------------------------------------------------------

    # quiz: script (mysql/quiz.sql) + runtime: app.py ensure_quiz_extra_columns (difficulty, passing_score, source_article_id).
    ctx.create_table("quiz", [
        col("quiz_id", "INT", null=False, auto_increment=True),
        col("title", "VARCHAR(255)", null=False),
        col("description", "TEXT"),
        col("category", "VARCHAR(100)"),
        col("created_by", "INT"),
        col("status", "ENUM('active','inactive')", default="active"),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("updated_at", "TIMESTAMP", default=CURRENT_TIMESTAMP, on_update="CURRENT_TIMESTAMP"),
        col("difficulty", "VARCHAR(20)", null=False, default="Medium"),
        col("passing_score", "INT", null=False, default=80),
        col("source_article_id", "INT"),
    ], primary_key="quiz_id", charset="utf8mb4",
        indexes=[
            index("created_by", name="fk_quiz_created_by"),
        ],
        foreign_keys=[
            fk("created_by", "users", "user_id", on_delete="SET NULL", name="fk_quiz_created_by"),
        ])

    # quiz_question: script (mysql/quiz.sql) + runtime: app.py ensure_quiz_extra_columns (source_article_id, source_title).
    ctx.create_table("quiz_question", [
        col("question_id", "INT", null=False, auto_increment=True),
        col("quiz_id", "INT", null=False),
        col("question_text", "TEXT", null=False),
        col("option_a", "VARCHAR(255)", null=False),
        col("option_b", "VARCHAR(255)", null=False),
        col("option_c", "VARCHAR(255)", null=False),
        col("option_d", "VARCHAR(255)", null=False),
        col("correct_option", "ENUM('A','B','C','D')", null=False),
        col("explanation", "TEXT"),
        col("points", "INT", default=1),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("source_article_id", "INT"),
        col("source_title", "VARCHAR(255)"),
    ], primary_key="question_id", charset="utf8mb4",
        indexes=[
            index("quiz_id", name="fk_quiz_question_quiz"),
        ],
        foreign_keys=[
            fk("quiz_id", "quiz", "quiz_id", on_delete="CASCADE", name="fk_quiz_question_quiz"),
        ])

    # quiz_result: script (mysql/quiz.sql). Same as production.
    ctx.create_table("quiz_result", [
        col("result_id", "INT", null=False, auto_increment=True),
        col("quiz_id", "INT", null=False),
        col("user_id", "INT", null=False),
        col("score", "INT", default=0),
        col("total_questions", "INT", default=0),
        col("percentage", "DECIMAL(5,2)", default=0),
        col("completed_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
    ], primary_key="result_id", charset="utf8mb4",
        indexes=[
            index("quiz_id", name="fk_quiz_result_quiz"),
            index("user_id", name="fk_quiz_result_user"),
        ],
        foreign_keys=[
            fk("quiz_id", "quiz", "quiz_id", on_delete="CASCADE", name="fk_quiz_result_quiz"),
            fk("user_id", "users", "user_id", on_delete="CASCADE", name="fk_quiz_result_user"),
        ])

    # quiz_training_material: runtime: app.py ensure_quiz_extra_columns.
    ctx.create_table("quiz_training_material", [
        col("quiz_id", "INT", null=False),
        col("article_id", "INT", null=False),
        col("sort_order", "INT", null=False, default=0),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
    ], primary_key=("quiz_id", "article_id"), charset="utf8mb4",
        indexes=[
            index("article_id", name="idx_qtm_article_id"),
            index("quiz_id", name="idx_qtm_quiz_id"),
        ])

    # quiz_attempt_answer: runtime: app.py ensure_quiz_attempt_answer_table (no foreign keys, on purpose).
    ctx.create_table("quiz_attempt_answer", [
        col("attempt_answer_id", "BIGINT", null=False, auto_increment=True),
        col("result_id", "BIGINT", null=False),
        col("quiz_id", "INT", null=False),
        col("user_id", "INT", null=False),
        col("question_id", "INT", null=False),
        col("question_order", "INT", null=False),
        col("question_text", "TEXT", null=False),
        col("option_a", "TEXT", null=False),
        col("option_b", "TEXT", null=False),
        col("option_c", "TEXT", null=False),
        col("option_d", "TEXT", null=False),
        col("selected_option", "CHAR(1)", null=False),
        col("correct_option", "CHAR(1)", null=False),
        col("is_correct", "TINYINT(1)", null=False, default=0),
        col("explanation", "TEXT"),
        col("points", "INT", null=False, default=1),
        col("created_at", "TIMESTAMP", default=CURRENT_TIMESTAMP),
        col("source_article_id", "INT"),
        col("source_title", "VARCHAR(255)"),
    ], primary_key="attempt_answer_id", charset="utf8mb4",
        indexes=[
            index("result_id", name="idx_quiz_attempt_answer_result"),
            index("user_id", "quiz_id", name="idx_quiz_attempt_answer_user_quiz"),
            unique("result_id", "question_id", name="uq_quiz_attempt_answer_result_question"),
        ])

    # ------------------------------------------------------------------
    # AI provider
    # ------------------------------------------------------------------

    # ai_provider_configs: runtime: ai_provider_service.py ensure_ai_provider_configs_table.
    ctx.create_table("ai_provider_configs", [
        col("id", "INT", null=False, auto_increment=True),
        col("provider", "VARCHAR(50)", null=False),
        col("model_name", "VARCHAR(100)", null=False),
        col("encrypted_api_key", "TEXT", null=False),
        col("key_hint", "VARCHAR(20)"),
        col("is_active", "TINYINT(1)", null=False, default=1),
        col("test_status", "VARCHAR(50)", null=False, default="not_tested"),
        col("last_tested_at", "DATETIME"),
        col("created_by", "INT"),
        col("updated_by", "INT"),
        col("created_at", "DATETIME", default=CURRENT_TIMESTAMP),
        col("updated_at", "DATETIME", default=CURRENT_TIMESTAMP, on_update="CURRENT_TIMESTAMP"),
    ], primary_key="id", charset="utf8mb4",
        indexes=[
            index("is_active", name="idx_ai_provider_configs_active"),
        ])

    # ------------------------------------------------------------------
    # Notion Sync
    # ------------------------------------------------------------------

    # notion_sync_configs: runtime: notion_sync_service.py ensure_notion_sync_tables.
    ctx.create_table("notion_sync_configs", [
        col("id", "INT", null=False, auto_increment=True),
        col("encrypted_notion_token", "TEXT", null=False),
        col("source_id", "VARCHAR(255)", null=False),
        col("source_name", "VARCHAR(255)"),
        col("is_active", "TINYINT(1)", null=False, default=1),
        col("created_by", "INT"),
        col("updated_by", "INT"),
        col("created_at", "DATETIME", default=CURRENT_TIMESTAMP),
        col("updated_at", "DATETIME", default=CURRENT_TIMESTAMP, on_update="CURRENT_TIMESTAMP"),
        col("encrypted_access_token", "TEXT"),
        col("notion_workspace_id", "VARCHAR(64)"),
        col("notion_workspace_name", "VARCHAR(255)"),
        col("notion_workspace_icon", "VARCHAR(500)"),
        col("notion_bot_id", "VARCHAR(64)"),
        col("connection_status", "VARCHAR(20)", null=False, default="connected"),
        col("last_sync_at", "DATETIME"),
        col("last_error", "TEXT"),
    ], primary_key="id", charset="utf8mb4",
        indexes=[
            index("is_active", name="idx_notion_sync_configs_active"),
        ])

    # notion_sync_jobs: runtime: notion_sync_service.py ensure_notion_sync_tables (last_heartbeat, trigger_source, details were added later).
    ctx.create_table("notion_sync_jobs", [
        col("id", "INT", null=False, auto_increment=True),
        col("status", "VARCHAR(50)", null=False),
        col("imported_count", "INT", default=0),
        col("updated_count", "INT", default=0),
        col("skipped_count", "INT", default=0),
        col("failed_count", "INT", default=0),
        col("error_message", "TEXT"),
        col("started_at", "DATETIME", default=CURRENT_TIMESTAMP),
        col("completed_at", "DATETIME"),
        col("created_by", "INT"),
        col("last_heartbeat", "DATETIME"),
        col("trigger_source", "VARCHAR(20)"),
        col("details", "TEXT"),
    ], primary_key="id", charset="utf8mb4")

    # notion_oauth_states: runtime: notion_sync_service.py ensure_notion_sync_tables.
    ctx.create_table("notion_oauth_states", [
        col("state", "VARCHAR(64)", null=False),
        col("created_by", "INT"),
        col("created_at", "DATETIME", default=CURRENT_TIMESTAMP),
        col("expires_at", "DATETIME", null=False),
    ], primary_key="state", charset="utf8mb4")

    # notion_oauth_apps: runtime: notion_sync_service.py ensure_notion_sync_tables.
    ctx.create_table("notion_oauth_apps", [
        col("id", "INT", null=False, auto_increment=True),
        col("client_id", "VARCHAR(255)", null=False),
        col("encrypted_client_secret", "TEXT", null=False),
        col("client_secret_hint", "VARCHAR(20)"),
        col("is_active", "TINYINT(1)", null=False, default=1),
        col("created_by", "INT"),
        col("updated_by", "INT"),
        col("created_at", "DATETIME", default=CURRENT_TIMESTAMP),
        col("updated_at", "DATETIME", default=CURRENT_TIMESTAMP, on_update="CURRENT_TIMESTAMP"),
    ], primary_key="id", charset="utf8mb4",
        indexes=[
            index("is_active", name="idx_notion_oauth_apps_active"),
        ])

    # notion_pending_updates: runtime: notion_sync_service.py ensure_notion_sync_tables.
    ctx.create_table("notion_pending_updates", [
        col("id", "INT", null=False, auto_increment=True),
        col("article_id", "INT"),
        col("notion_page_id", "VARCHAR(64)", null=False),
        col("proposed_title", "VARCHAR(500)"),
        col("proposed_content", "MEDIUMTEXT"),
        col("previous_title", "VARCHAR(500)"),
        col("previous_content", "MEDIUMTEXT"),
        col("notion_last_edited_time", "DATETIME"),
        col("status", "ENUM('pending','applied','dismissed','trashed')", null=False, default="pending"),
        col("detected_at", "DATETIME", default=CURRENT_TIMESTAMP),
        col("resolved_by", "INT"),
        col("resolved_at", "DATETIME"),
        col("trashed_by", "INT"),
        col("trashed_at", "DATETIME"),
    ], primary_key="id", charset="utf8mb4",
        indexes=[
            index("article_id", "status", name="idx_notion_pending_updates_article"),
        ])

    # notion_obsolete_articles: runtime: notion_sync_service.py ensure_notion_sync_tables.
    ctx.create_table("notion_obsolete_articles", [
        col("id", "INT", null=False, auto_increment=True),
        col("notion_page_id", "VARCHAR(64)", null=False),
        col("page_title", "VARCHAR(500)"),
        col("deleted_at", "DATETIME", default=CURRENT_TIMESTAMP),
        col("deleted_by", "INT"),
        col("last_known_notion_edited_time", "DATETIME"),
        col("last_known_content_hash", "VARCHAR(64)"),
        col("latest_notion_edited_time", "DATETIME"),
        col("latest_content_hash", "VARCHAR(64)"),
        col("obsolete_status", "ENUM('unchanged','updated','missing')", null=False, default="unchanged"),
        col("updated_after_obsolete", "TINYINT(1)", null=False, default=0),
        col("last_checked_at", "DATETIME"),
        col("last_sync_result", "VARCHAR(255)"),
        col("created_at", "DATETIME", default=CURRENT_TIMESTAMP),
        col("updated_at", "DATETIME", default=CURRENT_TIMESTAMP, on_update="CURRENT_TIMESTAMP"),
    ], primary_key="id", charset="utf8mb4",
        indexes=[
            unique("notion_page_id", name="idx_notion_obsolete_page"),
            index("obsolete_status", name="idx_notion_obsolete_status"),
        ])
