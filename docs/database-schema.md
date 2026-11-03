# Database schema: where it comes from today

Status: **Phase 1 (record and check)**. The app still creates and changes its own tables while it runs.
Nothing about that was changed. This page lists every place that does it, and how the baseline
migration (`backend/migrations/0001_baseline.py`) relates to production. How to use the tools is in
[database-migrations.md](database-migrations.md).

## What we found

* There is **no record of which schema version a database is on**. Each feature creates what it needs
  the first time it is used.
* Nothing creates tables in the web process at import time. Schema changes happen in four ways:
  1. **Lazily, inside a request** (an `ensure_*` function the first time a feature is used).
  2. **In a background thread**: `app.py` starts `_notion_auto_sync_loop` when it is imported. About 30
     seconds after the web process starts, and then every 5 minutes, it calls
     `ensure_notion_sync_tables`. So the Notion tables and the `wiki_article` Notion columns appear
     shortly after every boot even if nobody opens Notion Sync.
  3. **Before a deploy goes live**: Railway runs `python src/migrate_escalation_context.py`
     (`backend/src/railway.json` → `preDeployCommand`).
  4. **By hand**: the scripts in `mysql/`.
* Every runtime change is "add if missing" (`CREATE TABLE IF NOT EXISTS`, or look at
  `INFORMATION_SCHEMA` first), so running it twice is safe. Two things are not additive:
  `MODIFY COLUMN` (widening `wiki_article.content`, fixing two ENUMs) and
  `CONVERT TO CHARACTER SET` (three Notion tables). Both only run when the check says they are needed.
* **The repo did not describe the real database.** The SQL scripts are older than the code, and production has
  8 tables and many columns that no script or runtime code creates (sections 4 and 5). So the baseline was
  generated from a read-only snapshot of production (2026-11-03, MySQL 9.7.2) and **production is the source of
  truth**: the baseline describes it, and nothing is changed in production to match the baseline.

## 1. Runtime schema changes in Python

"Safe twice" is *yes* for every row unless stated. The reason is in the last column.

| File · function | When it runs | What it does | Why running it twice is safe |
|---|---|---|---|
| `app.py` · `ensure_login_rate_limit_table` | login request | creates `login_rate_limit` | `CREATE TABLE IF NOT EXISTS` |
| `app.py` · `ensure_password_reset_tokens_table` | forgot / validate / reset password requests | creates `password_reset_tokens` (FK → `users`, ON DELETE CASCADE) | `IF NOT EXISTS` |
| `app.py` · `ensure_declined_registration_history_table` | register request (called before the registration transaction, because DDL commits) | creates `declined_registration_history` | `IF NOT EXISTS` |
| `app.py` · `ensure_ai_chat_log_table` | chat, chat test, analytics requests | creates `ai_chat_log` + 5 indexes | `IF NOT EXISTS` |
| `app.py` · `ensure_notification_user_reads_table` | dashboard, notifications requests | creates `notification_user_reads` | `IF NOT EXISTS` |
| `app.py` · `ensure_chat_cancel_table` | chat, chat cancel requests | creates `chat_cancelled_requests` | `IF NOT EXISTS` |
| `app.py` · `ensure_wiki_article_content_capacity` | create / edit article requests | `MODIFY COLUMN wiki_article.content MEDIUMTEXT` | skipped when the column is already `mediumtext`/`longtext` |
| `app.py` · `ensure_quiz_extra_columns` | create / edit / submit quiz requests (once per process) | adds `quiz.difficulty`, `quiz.passing_score`, `quiz.source_article_id`, `quiz_question.source_article_id`, `quiz_question.source_title`; creates `quiz_training_material` | each column is added only if `INFORMATION_SCHEMA` does not list it; `IF NOT EXISTS` |
| `app.py` · `ensure_quiz_attempt_answer_table` | quiz submit / attempts requests | creates `quiz_attempt_answer` (no foreign keys, on purpose); adds `source_article_id`, `source_title` if missing | `IF NOT EXISTS`; column check first |
| `app.py` · `ensure_registration_keys_table` | **never called** (dead code; the registration-key endpoints now return 410) | would create / upgrade `staff_registration_keys` | n/a. The table may or may not exist in production. The live code only reads it after `SHOW TABLES` |
| `ai_provider_service.py` · `ensure_ai_provider_configs_table` | AI settings requests, AI quiz generation | creates `ai_provider_configs` | `IF NOT EXISTS` |
| `notion_sync_service.py` · `ensure_notion_sync_tables` | every Notion Sync request **and** the background thread (30 s after boot, then every 5 min) | creates `notion_sync_configs`, `notion_sync_jobs`, `notion_oauth_states`, `notion_oauth_apps`, `notion_pending_updates`, `notion_obsolete_articles`; adds later columns (8 on configs, `last_heartbeat` / `trigger_source` / `details` on jobs, `trashed_by` / `trashed_at` on pending); re-asserts two column definitions with `MODIFY COLUMN` | `IF NOT EXISTS`; every `ADD COLUMN` is guarded by a column check; the `MODIFY` is a no-op when the definition already matches |
| `notion_sync_service.py` · `_ensure_utf8mb4_table` | called for `notion_sync_configs`, `notion_pending_updates`, `notion_obsolete_articles` | `ALTER TABLE … CONVERT TO CHARACTER SET utf8mb4` | skipped once the table is already utf8mb4. Not additive: it rewrites the table |
| `notion_sync_service.py` · `ensure_notion_columns_on_wiki_article` | same as above | adds `wiki_article.source_type`, `notion_page_id` (+ unique index `idx_wiki_article_notion_page_id`), `notion_last_edited_time` | column check first |
| `notion_sync_service.py` · `_ensure_notion_page_id_unique_index` | same as above | adds the unique index on `wiki_article.notion_page_id` | skipped when it exists, and **skipped (with a log line) while two articles share one page id** |

Functions that only *look* at the schema (no change): `get_table_columns_safe`, `_get_table_columns`,
`_table_columns_for_cleanup`, `get_quiz_result_id_column`, `create_notification_safe` (adapts its INSERT
to the columns `notification` has), `revoke_legacy_unused_registration_keys`, `_column_exists`,
`_describe_table`, and the read-only tools in `backend/tools/`.

## 2. Pre-deploy script

| File | When | What | Safe twice |
|---|---|---|---|
| `backend/src/migrate_escalation_context.py` | Railway `preDeployCommand`, before each deploy goes live | creates `escalation_context` (FK → `escalation`, ON DELETE CASCADE) after checking that `escalation.escalation_id` is a signed INT primary key on InnoDB; exits with a clear message otherwise | yes, `IF NOT EXISTS`. Has its own test, `test_escalation_context_migration.py` |

`mysql/escalation_context.sql` is the same statement as a manual script.

## 3. SQL scripts in `mysql/` (run by hand, never by the app)

| Script | Defines | Notes |
|---|---|---|
| `Query1.sql` | `roles`, `users`, `registration_keys` (legacy), `login_history` | plain `CREATE TABLE` (fails if it exists) **and sample INSERTs** (a demo manager account, demo keys). Do not run on a live database |
| `SQL FILE 3.sql` | `wiki_article`, `article_links`, columns `link`, `sub_category`, `display_order` | contains `UPDATE wiki_article SET content = …` for specific article ids. **Re-running it overwrites articles.** Do not run on a live database |
| `escalation.sql` | `escalation` | `IF NOT EXISTS` |
| `notification.sql` | `notification` | **defines it twice, differently** (first nullable, second `NOT NULL`); the first one wins when the file is run top to bottom |
| `message.sql` | `user_message` | `IF NOT EXISTS` |
| `quiz.sql` | `quiz`, `quiz_question`, `quiz_result` | `IF NOT EXISTS`, plus sample INSERTs |
| `review queue.sql` | `review_queue` | `IF NOT EXISTS` |
| `escalation_context.sql` | `escalation_context` | see section 2 |
| `command file.sql`, `JH.database.sql` | older copies for a local database `jungle_house_ai` | superseded, e.g. `wiki_article.title` is `VARCHAR(255)` there but `VARCHAR(200)` in `SQL FILE 3.sql`. Ignored by the baseline |
| `audit log.sql`, `image_retrieval.sql`, `register email.sql`, `uploadimage.sql` | **empty files** | the tables `audit_log` and `image_retrieval` are used by the code but defined nowhere in the repo |

## 4. Every table in production, and where it comes from

The baseline (`0001_baseline.py`) was generated from a read-only snapshot of production taken on 2026-11-03
(MySQL 9.7.2: 36 tables, 350 columns, 61 indexes, 21 foreign keys, no views, triggers, routines or events) and
then reviewed by hand. **Production is the source of truth.** The baseline describes it; it never asks
production to change. `migrate.py check --snapshot schema_production.json` shows 0 differences and 0 warnings,
and a stricter test also compares index and constraint names and column order.

| Origin | Tables |
|---|---|
| Created by the app at runtime (code in section 1) | `login_rate_limit`, `password_reset_tokens`, `declined_registration_history`, `ai_chat_log`, `notification_user_reads`, `chat_cancelled_requests`, `quiz_training_material`, `quiz_attempt_answer`, `ai_provider_configs`, `notion_sync_configs`, `notion_sync_jobs`, `notion_oauth_states`, `notion_oauth_apps`, `notion_pending_updates`, `notion_obsolete_articles` |
| Created by the pre-deploy step | `escalation_context` |
| From the scripts in `mysql/` (production differs, see section 5) | `roles`, `users`, `login_history`, `wiki_article`, `article_links`, `escalation`, `review_queue`, `notification`, `user_message`, `quiz`, `quiz_question`, `quiz_result` |
| **Only in production**: nothing in the repo creates them | `audit_log`, `chat_session`, `email_verifications`, `escalation_tickets`, `image_retrieval`, `qa_knowledge`, `registration_keys`, `staff_registration_keys` |

### Does the code use the tables that exist only in production?

Nothing was dropped or renamed. This is what the repo says (searched in `backend/`, `jungle-house-wiki-ai/` and `mysql/`):

| Table | Used by the current code? | Detail |
|---|---|---|
| `audit_log` | **Yes, actively** | `app.py`: `add_audit_log` inserts, `get_audit_logs` and the registration history read it, declined-account cleanup deletes from it. Foreign key to `users`. |
| `image_retrieval` | **Yes, actively** | `app.py` and `db_helper.py` read, insert, update and delete; image search depends on it. Also read by `tools/notion_duplicate_report.py`. |
| `qa_knowledge` | **Yes, actively** | `app.py` and `db_helper.py` read, insert, update and delete (approved Q&A). |
| `staff_registration_keys` | Only for cleanup | The registration-key endpoints return 410 and nothing creates the table any more. `app.py` still deletes or revokes its rows when a declined account is removed, after checking the table and columns exist. |
| `email_verifications` | Only for cleanup | `app.py` deletes a user's rows when a declined account is removed (`# legacy-table cleanup only`). The table has an `ON DELETE CASCADE` foreign key to `users`. |
| `registration_keys` | **No** | Only `mysql/Query1.sql` mentions it. Its three foreign keys (to `roles` and `users`, no `ON DELETE` rule) mean a user referenced as `created_by` or `used_by` cannot be deleted while key rows point at them. |
| `chat_session` | **No** | Left over from a reverted commit: `bcbd1d27` (2026-10-03, "multi-turn chat memory + server-side session history") created it and `9fb6b911` reverted that commit. The same commit added `ai_chat_log.session_id` and `idx_ai_chat_log_session`, which are also unused now. |
| `escalation_tickets` | **No** | No mention in the code, scripts, docs or git history. |

Also found: the dashboard query `SELECT ROUND(AVG(confidence), 2) FROM ai_response` (`app.py`, `get_dashboard`)
refers to a table that **does not exist in production**. The call is wrapped in try/except, so the dashboard
silently shows `0%` for AI accuracy. This is a code problem, not a schema one, and nothing was changed.

## 5. Where production differs from the old SQL scripts

These are the 9 differences `check` reported before the baseline was generated from production, plus the
warnings (extras the scripts do not know about). Production wins in all of them.

| Table | Script (`mysql/`) says | Production has |
|---|---|---|
| `users` | `status ENUM('active','inactive')`, default `'active'` | `ENUM('pending','active','inactive','declined')`, default `'pending'` |
| `login_history` | `user_id NOT NULL` | `user_id` nullable (failed logins for unknown emails); extra `email`, `full_name` |
| `notification` | `user_id NOT NULL` with a foreign key; text column `message`; `type` ENUM of 4 values | `user_id` nullable and **no foreign key**; the text column is called `detail` (there is no `message`); `type` has 6 values; extra `target_role`, `related_id`, `created_by` and indexes `idx_is_read`, `idx_target_role`, `idx_type` |
| `review_queue` | `status ENUM('pending','approved','rejected','published')` | `status VARCHAR(30)` |
| `escalation` | indexes `idx_status`, `idx_created_at` | **neither index** (optional migration 0002 adds them); extra `image_url`, `image_type`, `is_deleted`, `deleted_at`, `deleted_by` |
| `wiki_article` | no soft-delete or attachment columns | extra `is_deleted`, `deleted_at`, `deleted_by`, `attachment_url`, `attachment_type`, `image_files`, `image_keywords` |
| `user_message` | no thread columns | extra `thread_id`, `parent_message_id`, `is_deleted_by_sender`, `is_deleted_by_receiver`, `edited_at` |
| `ai_chat_log` | (runtime DDL) | extra `session_id` and `idx_ai_chat_log_session` (see `chat_session` above) |

Smaller things worth knowing:

* `staff_registration_keys.assigned_email` has the **text** `'NULL'` as its default (not SQL NULL). Harmless and
  kept as is; it is the only column like that.
* Every table uses `utf8mb4` (`utf8mb4_0900_ai_ci`) and InnoDB. The baseline states the character set; the
  collation is not part of the comparison.
* MySQL created some indexes by itself to back foreign keys. They are written into the baseline with their
  production names so a new database ends up identical.

## 6. Optional follow-up: migration 0002

`0002_escalation_indexes.py` adds `idx_status` and `idx_created_at` to `escalation` **only if missing**. It is
not in the baseline because production does not have them. Nothing depends on it. See
[database-migrations.md](database-migrations.md).
