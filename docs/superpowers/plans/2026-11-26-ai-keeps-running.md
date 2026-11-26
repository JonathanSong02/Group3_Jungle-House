# AI Keeps Running (Step 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chat answers and AI quiz drafts survive page changes, phone backgrounding, short network drops and page reloads, with an in-app "done" notice. No change to how the AI answers.

**Architecture:** The page still waits on the same `/api/chat` or `/api/admin/quizzes/ai-generate` request as today (no added wait). The backend also saves a copy of the final JSON reply in a background thread, keyed by `(user_id, request_id)`. A frontend module (`aiTasks.js`, module-level, so it outlives page changes) runs the requests; on a no-response failure it fetches the saved copy. Chat writes answers through localStorage so they land even when the page is unmounted.

**Tech Stack:** Flask + MySQL (backend/src), React 19 + Vite (jungle-house-wiki-ai), `node --test`, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-26-ai-keeps-running-design.md`

## Global Constraints

- AI logic in `chat()` and `ai_generate_quiz()` is not touched. Response JSON of every existing route is byte-identical.
- No new dependencies. Do not touch `services/api.js`, auth/CSRF, role lists, deployment files.
- New table only via `backend/migrations/0008_ai_task_result.py` + identical runtime `ensure_table`.
- Saved copies deleted after 7 days. Recovery polling every 3 s, until start + 180 s (chat) / 240 s (quiz).
- At most 2 running AI tasks per user; one per chat session.
- Notice text never shows question or answer content.
- All new strings in `translations.js` in en / zh / ms. Honey theme tokens only.
- **No commits** (MASTER_PROMPT rule 4). The user reviews the working tree.

## Review Focus

1. Answer arrives while the user is on another page → must be in that chat after returning (Task 3 test: storage write without mounted state).
2. Server returns 4xx/5xx → shown immediately as today, never polled (Task 2 test).
3. Stop pressed → no polling, "stopped" message as today (Task 2 test).
4. Page reloaded mid-request → result recovered into the right session, or "unfinished, ask again" (Task 2 resume test + Task 3 inbox).
5. Two users on one browser → saved copies and pending lists are per user id (Task 1 route scoping test, Task 2 storage key test).

---

### Task 1: Backend — save and fetch reply copies

**Files:**
- Create: `backend/src/ai_task_results.py`, `backend/migrations/0008_ai_task_result.py`, `backend/src/test_ai_task_results.py`
- Modify: `backend/src/app.py` (new section after `/api/chat/cancel`), `backend/src/test_schema_migrations.py` (table count 41→42, migration lists + `ai_task_result`)

**Interfaces — Produces:**
- `ai_task_results.ensure_table(cursor)`; `save_result(get_connection, user_id:int, request_id:str, kind:str, http_status:int, body:str) -> None` (upsert, swallows errors, cleanup of rows older than 7 days at most every 10 min); `fetch_result(get_connection, user_id, request_id) -> dict|None` (`{kind, http_status, result}` with `result` parsed JSON).
- `GET /api/ai-tasks/<request_id>` endpoint `get_ai_task_result` → `{"found": false}` or `{"found": true, "kind", "http_status", "result"}`; any active user; only own rows.
- after_request hook `save_ai_task_result_copy` inserted at index 0 of `app.after_request_funcs[None]` (runs after all other hooks, sees the final body). Acts only for endpoints `chat` and `ai_generate_quiz`, JSON responses, non-empty `request_id` (JSON body or form, ≤64 chars). Starts a daemon thread; never changes the response.

Table `ai_task_result`: `ai_task_result_id` INT AI PK · `user_id` INT NOT NULL FK users ON DELETE CASCADE · `request_id` VARCHAR(64) NOT NULL · `kind` VARCHAR(20) NOT NULL · `http_status` INT NOT NULL · `result` MEDIUMTEXT NOT NULL · `created_at` DATETIME NOT NULL · UNIQUE `uq_ai_task_result_request (user_id, request_id)`.

- [ ] Tests (`test_ai_task_results.py`): hook saves exact body bytes + status for `/api/chat` with request_id; response bytes unchanged; no save without request_id, for other endpoints, for non-JSON; hook is first in `after_request_funcs[None]`; route returns found/not-found with SQL scoped to the session user; `save_result` swallows DB errors; ensure_table DDL equals migration (schema test covers it via code scan).
- [ ] Run, see fail; implement; run `python -m unittest discover -s backend/src -p "test_*.py"` → all pass.

### Task 2: Frontend task runner `aiTasks.js`

**Files:** Create `jungle-house-wiki-ai/src/services/aiTasks.js`, `jungle-house-wiki-ai/src/services/aiTasks.test.js`

**Interfaces — Produces:**
- `createAiTaskManager({ api, storage, now, sleep })` and default `aiTasks` instance.
- `run({ userId, kind:'chat'|'quiz', requestId, meta, send:(signal)=>Promise }) -> Promise<response>`: records pending in `storage['jh_ai_tasks_<userId>']`; on reject without `error.response` and not cancelled, polls `api.get('/ai-tasks/<id>')` every 3 s until deadline; found with http_status < 400 → resolves `{ data: result, status }`; ≥ 400 → rejects `{ response: { status, data: result } }`; none → rejects original error. Removes pending at the end; emits `{type:'done', kind, meta, requestId, ok}`.
- `cancel(requestId)` aborts. `running(userId)` list; `runningCount(userId)`; `subscribe(fn)` (for `useSyncExternalStore`), `getSnapshot()`.
- `resume(userId)`: for stored pending tasks not live in this page load, poll until deadline; result → `storage['jh_ai_task_inbox_<userId>']` entry `{requestId, kind, meta, ok, status, data}` (or `{failed:true}`), emit done. `takeInbox(userId, kind)` returns and removes that kind's entries.
- On `visibilitychange` → visible, live tasks older than 10 s get one immediate check of the saved copy.
- Unseen notices: `unseen(userId)`, `markSeen(userId, predicate)` in `storage['jh_ai_unseen_<userId>']`.

- [ ] Tests: success passes through; 500 response not polled; cancel not polled; network error then found → resolves with saved data; network error, never found → original error after deadline; pending added/removed per user key; resume writes inbox; runningCount.

### Task 3: Chat page uses the runner

**Files:** Modify `jungle-house-wiki-ai/src/pages/Chat.jsx`; Create `jungle-house-wiki-ai/src/pages/Chat.background.test.js`

- `updateCurrentSessionMessages` and `addChatHistory` read the latest list from localStorage (fallback current state), save, then set state — so a reply landing after unmount is stored.
- `handleSend` calls `aiTasks.run({ kind:'chat', meta:{ sessionId, title } , send })`; `loading` becomes "a chat task is running for the active session" (from `aiTasks` snapshot) or escalation-offer in progress (local state). Over 2 running → show `aiTask.busy` without sending.
- Stop → `aiTasks.cancel(requestId)` + existing `/chat/cancel`.
- On mount and on done events: `takeInbox(userId,'chat')` → append `buildAiMessage(data)` (or `aiTask.unfinished` message) to that session; `markSeen` for the active session.
- [ ] Test: storage helper appends a reply to a session that isn't mounted/active; inbox entry becomes an AI message in the right session.

### Task 4: Quiz page uses the runner

**Files:** Modify `jungle-house-wiki-ai/src/pages/admin/QuizManagement.jsx`
- Generate via `aiTasks.run({ kind:'quiz', send })` with new optional `request_id`; draft saved to `jh_ai_quiz_draft_<userId>`; restored on mount (opens the AI tab); cleared on save. Inbox entries (resume) restore too. `markSeen(quiz)` on mount.

### Task 5: Notice, red dot, tab title, texts, guide

**Files:** Create `jungle-house-wiki-ai/src/components/AiTaskNotice.jsx`; Modify `StaffLayout.jsx` (mount notice + `aiTasks.resume(user.id)`, dot on recent-chat rows and Quiz Management link), `src/styles/` existing staff stylesheet (notice + dot using tokens), `i18n/translations.js`, `backend/src/system_knowledge.py` (`GUIDE_SECTIONS` AI Chat + Quiz Management lines)
- Done event while not on the matching page → corner notice (`aiTask.doneChat` / `aiTask.doneQuiz`, `aiTask.view`, close) + unseen entry; click → chat: `request('select', sessionId)` + `/chat`; quiz: `/admin/quiz-management`. Hidden tab → title prefixed "✓ " until visible.
- [ ] `test_system_knowledge.py`, `node --test`, `npm run lint`, `npm run build` pass.

### Task 6: Docs

- Update `MASTER_PROMPT.md` (feature, 0008, FloatingAIChat not mounted), `docs/CHAT_MEMORY_ENHANCEMENTS.md` (dated entry), `docs/database-schema.md` + `docs/database-migrations.md` (0008).
