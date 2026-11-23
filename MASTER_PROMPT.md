# Jungle House Wiki AI: Master Prompt / Handover

> Paste this whole file into an AI coding assistant before asking it to work on this repo.
> Teammates can read it as a project handover too.
> Last updated: 2026-11-02. The most recent work is the **system audit (section 5)**. Before that: **Notion article auto-categorize (section 4)**.

---

## 0. Your role and working rules

You are working on a live, deployed internal tool used by Jungle House retail staff. Several team members push to the same `main` branch, so keep changes small and easy to review.

Rules that apply to every change:

1. **Plan first, then code.** Before editing, reply with: the files you will touch, the functions you will add or change, and how existing behaviour stays unaffected. Wait for approval.
2. **Do not change existing logic without asking.** That covers existing functions, routes, queries, response shapes and UI flows. New code next to them is fine. If a change to existing logic seems necessary, stop and explain why.
3. **Smallest possible diff.** No drive-by refactors, renames, reformatting or unrelated fixes, even when you notice something wrong. Report those instead (see section 5).
4. **Do not commit, push or deploy.** Leave changes in the working tree for a human to review.
5. **Match the surrounding code.** Same naming, comment style and patterns as the code next to it. `app.py` uses long explanatory `# ===` section comments. Follow that.
6. **When unsure, ask.** Do not guess about business rules, roles or the database. The user prefers questions explained in plain language: what changes for staff, not function names.

---

## 1. What the project is

An AI-assisted internal knowledge base ("wiki") for Jungle House staff (a honey retail brand with kiosks, roadshows and booths). Staff ask questions in the AI Chat and get answers from the company's own SOPs, notices and product articles. Questions the AI can't answer confidently are escalated to a team lead, whose approved answer goes back into the knowledge base. Many articles are synced in from the company's Notion workspace.

### Tech stack and deployment

| Layer | Tech | Location | Deployed to |
|---|---|---|---|
| Frontend | React 19 + Vite 8, react-router-dom 7, axios, jodit-react (rich text) | `jungle-house-wiki-ai/` | Vercel |
| Backend | Python Flask (single large `app.py`, ~16.8k lines, ~123 routes), gunicorn | `backend/src/` | Railway |
| Database | MySQL | schema scripts in `mysql/*.sql` | Railway MySQL |
| AI | Configurable AI provider (set in the admin **AI Settings** page: Gemini / OpenAI / DeepSeek / Claude) via `ai_provider_service.generate_ai_reply`, plus a local PyTorch intent model, CLIP-style image embeddings and a vision model for photos | `ai_provider_service.py`, `predict_intent.py`, `image_embedding_helper.py` | Railway |
| Integrations | Notion sync (OAuth), Resend (password-recovery and registration email) | `notion_sync_service.py`, `app.py` | |

- In production, the frontend calls a same-origin `/api` and `/static`. `vercel.json` forwards these to `https://group3jungle-house-production.up.railway.app`. `src/services/api.js` resolves the base URL.
- **The frontend axios client times out after 60 s** (`services/api.js`). Any request that may run long must finish well inside that.
- Backend start command (`railway.json` / `Procfile`): `gunicorn --chdir src wsgi:app --workers 1 --threads 4 --timeout 180`. **One worker**, so in-process dictionaries are shared by all requests, but they are lost on every restart or redeploy.
- `jungle-house-wiki-ai/ai_module/` is an older standalone retrieval prototype. Do not use it or change it.

### Roles

`staff`, `teamlead`, `manager`, `admin` (normalised to lowercase without spaces, `_` or `-`).
- Everyone: AI Chat (home page `/chat`), Knowledge Base, Quiz, Notifications, Messages, Profile.
- `teamlead` and above: Escalation, Content Management (add/edit articles), Quiz Management, Review, User Management, Analytics, Security Monitoring.
- `manager` and `admin`: Admin Dashboard, AI Settings, Notion Sync.
- On the backend, one central check (`require_authenticated_api` in `app.py`, with the `_MANAGER_ENDPOINTS` and `_APPROVER_ENDPOINTS` lists) covers the API. A new route must be added to the right list, and code must take the user from `current_auth_user_id()`, never from the request body.

---

## 2. What has been built (feature inventory)

- **Auth and accounts:** session-cookie login with CSRF (`/api/auth/csrf`, `/api/auth/me`), registration with manager approval and registration keys, forgot/reset password over Resend email (including recovery from expired links), profile and password change, login history, audit logs.
- **AI Chat** (`pages/Chat.jsx`, plus `components/FloatingAIChat.jsx` on other pages):
  - Multiple chat sessions per user, stored in **browser localStorage**.
  - Text and **image questions**, English / 中文 / Bahasa Melayu questions (cross-lingual retrieval bridge, Malay slang, Chinese typo and homophone handling, English typo normalisation), SOP step navigation, "not this" handling, a pause/cancel button.
  - **In-thread conversation memory and escalation issue context** (by Alan-040604, commits `a5a05de` and `6fa8a78`). Follow-ups are resolved from earlier turns. Escalations carry a bounded snapshot of the discussion. There's a clarification step before escalating an explicit "that's wrong", and a "standard question" field in escalation, review and approval. **Full design, limits and tests: `docs/CHAT_MEMORY_ENHANCEMENTS.md`. Read it before touching chat or escalation.**
  - **2026-11-23 change (LIONG1934, user-approved):** every text follow-up is now checked against the conversation, not only questions containing "it / 这个的". This supports "you said earlier…". The cost is one extra provider call of up to 8 s per follow-up; on failure the original search is kept. The AI fallback answer also sees the recent conversation (max 8 messages, 4,000 chars), marked untrusted and never a source of facts. Image, attachment, force-escalation and no-history paths are unchanged. This reverses Alan's original "standalone questions add no memory call" rule (see the dated section at the end of the doc).
  - **2026-11-23 Smart chat (LIONG1934, user-approved):** the AI now writes the answer for every ordinary text work question. It is no longer only a fallback, and the "one or two sentences" limit is gone. It asks one clarifying question when unclear (source `ai_provider_clarify`, no escalation).
    - When retrieval already found SOP steps or option buttons, only the text above them changes. Steps, images, links and options are untouched, and SOP text is replaced only when the AI used the same article.
    - Any AI failure keeps the retrieval result.
    - Excluded: images, greetings, nonsense, "not satisfied", step controls (Step N / next), and Team Lead approved answers.
    - **Emergency off switch:** Railway env var `SMART_CHAT_ENABLED=0`, which gives the old behaviour with a byte-identical prompt.
    - Cost: one AI call on almost every question. Use a fast model (Gemini Flash / Claude Haiku class) in AI Settings.
    - Next planned: word-by-word streaming.
  - **2026-11-23 AI reads PDF / Word attachments (LIONG1934, user-approved):** text of `.pdf` and `.docx` article attachments is extracted on the server (pypdf, python-docx; free, no AI call) into a new table `article_attachment_text`.
    - The table is created at runtime and recorded as migration 0005.
    - Extraction runs in a background thread after an article is added or edited, and once for old articles 30 s after start (`DOCUMENT_TEXT_BACKFILL=0` turns it off; tests and CI set it off).
    - `build_ai_chat_context` uses the text to pick articles and adds only the best-matching excerpt (≤1,500 chars), inside the same 6,000-char cap, so per-question cost is unchanged. Texts are cached in memory for 5 minutes and cleared after every sync.
    - Not read: old `.doc`, images, scanned PDFs, and Notion file links.
    - Code: `backend/src/document_text_service.py`.
  - **Escalation flow:** a low-confidence answer offers escalation. A team lead answers, then approves or rejects, and approved answers go back into the knowledge base.
- **Knowledge Base:** articles with images, categories, recycle bin, restore, bulk actions, permanent delete, upload clean-up. Categories in use: `SOP`, `PRODUCT`, `SALES`, `Training`, `Notice`, plus `Notion`, which means "synced from Notion, not categorized yet".
- **Notion Sync:** OAuth connect/reconnect, change detection, pending updates (apply, dismiss, trash, restore, bulk), tracking of obsolete pages, storage audit and clean-up, job log, and **auto-categorize** (section 4).
- **Quiz:** staff take quizzes, with attempt history and review, an in-quiz training material reader, and mastery tracking. Admins create them manually or **AI-generate** them from chosen articles or categories, with editable draft review and detailed results.
- **Review queue**, **internal messages**, **notifications**, **analytics**, **security monitoring**.
- **UI language switcher** (English / 中文 / Bahasa Melayu) across all pages.

---

## 3. Frozen: do not change

Changes in these areas are **additive only**. Never rename, remove, retype or change the behaviour of anything that already exists without explicit approval.

### 3.1 API contract
- All existing routes in `backend/src/app.py` keep their path, HTTP method, auth/role checks, request fields and **response JSON shape** (same keys, types and meaning).
- Allowed: **new optional** request fields, and new response keys that are optional and safely ignored by existing clients. A request without the new fields must behave exactly as before.
- Do not change `src/services/api.js` (base-URL resolution, CSRF, cookies, 60 s timeout).

### 3.2 Database
- Do not `ALTER`, `DROP` or rename existing tables or columns, and do not change existing queries' results.
- New tables only with approval, as a separate reviewed SQL file in `mysql/` that is never applied automatically (see `mysql/escalation_context.sql` for the pattern).
- Note: `wiki_article.source_type`, `notion_page_id` and `notion_last_edited_time` are only added when Notion sync first runs (`notion_sync_service.ensure_notion_columns_on_wiki_article`). Code that reads them outside Notion sync must cope with them being missing (see `wiki_article_source_type_select` in `app.py`).

### 3.3 Auth, roles and deployment
- Do not touch login/session/CSRF logic, `ProtectedRoute`, `RoleRoute`, the role lists in `App.jsx`, or the backend role checks.
- Do not touch `vercel.json`, `railway.json`, `Procfile`, `wsgi.py`, `requirements.txt`, `package.json` or `package-lock.json`, or environment variables. **Do not add dependencies.**

### 3.4 UI theme and i18n
- The visual language is the **honey theme** in `src/styles/global.css` (`:root` tokens: `--bg #fbf4e6`, `--primary #c88918`, `--secondary #6f8f63`, `--text #342414`, `--border #ead8b7`, the `--shadow-*` and status colour tokens; font Manrope). Use these tokens or the page's existing classes. **No new hard-coded colours, fonts or design system.** The staff workspace also has light and dark variants (`StaffWorkspace.css`), so reuse existing pill and card classes rather than writing new colours. (`src/index.css` holds leftover Vite template tokens. Ignore it.)
- Keep the existing layouts, sidebar, cards, badges and mobile layout.
- **Every new user-visible string goes into `src/i18n/translations.js` in all three languages** (`en`, `zh`, `ms`) and is used through `src/i18n/LanguageContext.jsx` (`t`, `tOr`). Do not create a second translation system. Category labels use the keys `cat.<Category>`.

### 3.5 Chat and escalation
- Do not change the chat pipeline, the chat memory or the escalation context without reading `docs/CHAT_MEMORY_ENHANCEMENTS.md` and getting approval. Invariant: the raw `question` the staff member typed is never overwritten. Derived text only feeds `question_for_search`.

---

## 4. Notion article auto-categorize

**Commits:** `b37c991` (first version) and `198736f` (speed-up: keywords first, then batched AI). Both are on `main`.

### 4.1 Problem and goal
Every Notion page applied to the Knowledge Base used to get `category = 'Notion'`, so hundreds of articles sat in one bucket. Now they are sorted automatically into `SOP` / `PRODUCT` / `SALES` / `Training` / `Notice`. Mistakes are fixed by hand.

Category definitions, agreed with the user and used by both the AI and the keywords:
- **SOP:** step-by-step operating procedures (opening, closing, stocktake, settlement).
- **PRODUCT:** product introductions, benefits, ingredients, prices.
- **SALES:** selling techniques, promotions, incentives, sales reports.
- **Training:** new-staff training and onboarding checklists. "New bee 1st day check list" goes here, not in SOP.
- **Notice:** announcements, rules, penalties, public holidays.
- If neither method can decide, the article **stays `Notion`**, meaning "to be categorized by hand".

### 4.2 How it works (backend, `app.py`, section `# NOTION ARTICLE AUTO-CATEGORIZE`, just before the apply route)
- `auto_categorize_notion_articles(article_ids=None, time_budget_seconds=...)`:
  1. Loads non-deleted rows with `category = 'Notion' AND source_type = 'notion'`.
  2. **Pass 1, keywords** (`match_notion_category_by_keywords`, `NOTION_CATEGORY_KEYWORDS`). Instant, run for every article. A title hit scores 3 and a content hit 1. The article needs a score of at least 3 and a clear winner.
  3. **Pass 2, AI in batches** (`classify_notion_categories_with_ai`): 20 articles per call (`NOTION_AUTO_CATEGORY_AI_BATCH_SIZE`), 500 content chars each, a 15 s timeout, and a reply format of `number: CATEGORY`. A new batch only starts if it can finish inside the time budget. If no provider is configured it stops calling AI, and any other AI error leaves that batch as `Notion`.
  4. Saves with `save_notion_article_categories`. Every `UPDATE` is guarded with `AND category = 'Notion'`, so **a category changed by hand is never overwritten**, even if someone edits it during the run.
  5. Returns `[{articleId, title, category|None, method}]`, where `method` is one of `keywords`, `ai`, `unsure`, `time_limit` or `skipped`.
- **On Apply / Bulk Apply** (`/api/notion-sync/pending-updates/<id>/apply`, `/bulk-apply`): `notion_sync_service.apply_pending_update` is **unchanged** and still inserts `'Notion'`. After `conn.commit()` and the audit log, the route calls `auto_categorize_notion_articles_after_apply(new_article_ids)` with a 20 s budget. That covers **brand-new pages only**: a re-sync of an existing article never re-categorizes it. Failures are logged and swallowed, so a successful Apply is never turned into an error. Response JSON is unchanged.
- **Manual button:** `POST /api/notion-sync/auto-categorize` (manager/admin only, 45 s budget, writes an audit log). Response: `{success, message, categorizedCount, leftCount, results}`. Unfinished articles stay `Notion`, and the next press continues with them.
- `GET /api/articles` and `GET /api/articles/<id>` now also return `source_type` (or `NULL` if the column doesn't exist yet). All other fields are unchanged.
- `sub_category` and recycle-bin articles are never touched.

### 4.3 Frontend
- `pages/admin/NotionSync.jsx`: an "Auto-categorize Notion articles" card above Storage Cleanup (it reuses the `ns-storage-card` styles). It shows counts and a per-article result table, plus a "press again to continue" note when the time limit was hit.
- `components/SourceBadge.jsx`: a small "Notion" label, shown only when `source_type === 'notion'` and the category is no longer `Notion`. Used in `KnowledgeBase.jsx` (both card renderers, class `kb-article-category`), `admin/ContentManagement.jsx` (class `cm-category-badge`) and `ArticleDetail.jsx` (PageHeader `actions`, class `status-badge success`).
- `admin/EditArticle.jsx`: `'Notion'` was added to the category dropdown, so an uncategorized Notion article no longer appears as `SOP`.
- `i18n/translations.js`: `ns.autoCat.*` and `source.notion*` keys in en, zh and ms.

### 4.4 How people fix mistakes
Content Management → filter by category or search → **Edit** → change **Category** → Save. Team leads and managers can both do this. The Notion Sync button is manager-only, by the user's choice.

### 4.5 Decisions the user made (don't reverse without asking)
- Sort into the existing 5 categories. No new categories, no sub-categories.
- Fully automatic, with manual correction afterwards. There's no approve-each-suggestion step.
- Keep the `Notion` category as the "uncategorized" bucket. Keep the `Notion` filter in Content Management.
- Show the Notion source label using the existing `source_type`.
- Don't move auto-categorize into a background job for now. Pressing the button 2 to 4 times for the first big backlog (~500 articles) is acceptable.

### 4.6 Known limitations
- Keywords run before AI, so a title with a misleading keyword (for example "opening" in a product article) can be put in the wrong category. Spot-check the lists in Content Management.
- Chinese or Malay article titles almost never match keywords, so they rely on AI and more of them stay `Notion`.
- Tested only with syntax checks, lint and build, and isolated simulations (fake DB and fake AI: AI working, AI not configured, time limit, manual change preserved). **No end-to-end test against the real database or AI yet.**

---

## 5. System audit (2026-11-02)

A read-only review of the code at commit `22b89aa`. Nothing was tested against the live site or production database. Full findings and fixes: [System Audit Report](https://claude.ai/artifact/RrAwbGiAaxq6NDC5ncHt4y) (private until the owner shares it). IDs below match the report.

General rule: **never commit passwords, API keys or personal data.** Anything committed stays in git history even after it's deleted.

### 5.1 Done
- **H3, step 1:** `stripExecutableHtml` in `pages/admin/NotionSync.jsx` (commit `05e5935`) cleans the Notion Sync compare view. It removes only executable content (`script`, `base`, `meta`, `animate`, `set`, `on*` handlers, `srcdoc`, and `javascript:`, `vbscript:` and `data:text/html` values). Tested in Edge against the filter only: 16 kinds of normal content unchanged, and 0 of 17 attack payloads fired (11 fired before).

- **M2:** the backend change-password route now requires 8 characters, an uppercase letter and a number, the same as the Profile page, registration and password reset. Existing passwords keep working.

- **M3, part 1:** `vercel.json` now sends `X-Frame-Options: SAMEORIGIN`, so other sites can't frame the app. It must stay `SAMEORIGIN`, not `DENY`, because `ArticleDetail.jsx` previews PDFs in an iframe. HSTS needs no work, because Vercel already sends it.

- **L4:** chat cancel records are keyed per signed-in user (`chat_cancel_key` in `app.py`), so one user can't cancel another's request. The pause button and the table are unchanged.
- **L3:** removed the unused `build_article_search_segments` from `app.py`.

### 5.2 Decisions (don't reverse without asking)
- **Links, images, video, fonts and all other formatting must not change** in any sanitizer work. This is why the compare view doesn't use the stricter cleaner from the other pages.
- **Don't remove, blur or move the images in `backend/static/`, including the public image folders (C2).** The client asked for them to stay as they are.
- **Default manager account and the login fallback for old plaintext passwords (H1):** the owner chose to leave these alone. Don't change them without asking.
- **Images broken in the compare preview:** accepted. They display correctly once applied to the Knowledge Base, so no URL rewrite was added to that page.

### 5.3 Deferred
- **Make the repo private (H2):** do it when the system is finished. Only the repo owner (JonathanSong02) can change it. Check the Vercel plan first: its free plan only deploys the owner's commits from a private repo. Then confirm that Railway still deploys.
- **Login lockout (M1):** do it near delivery, or sooner if someone reports being locked out. It needs verifying that the backend reads the real client IP through the Vercel proxy, and limits must allow for staff sharing one shop Wi-Fi.

### 5.4 Open, not decided yet
- **H3, steps 2 and 3:** other pages' HTML cleaners still only block known-bad patterns, and content isn't cleaned when saved. Any stricter cleaner must respect the rule in 5.2. DOMPurify would be a new dependency, so it needs approval.
- **H2:** stop tracking `backend/logs/`.
- **M3, part 2 (Content-Security-Policy):** not added, because it could block images, video, fonts or the editor. If it's added near delivery, start in report-only mode.
- **M4 to M7, L1, L2 and L5 to L7** in the report haven't been decided yet.
- **Empty list items in some Notion articles:** for example under "Related Question". Possibly Notion page links that `notion_blocks_to_html` doesn't convert. Not confirmed.

### 5.5 Other known issues
- `mysql/escalation_context.sql` (chat issue context) must be reviewed and applied manually by whoever deploys. Until then, escalation context isn't saved and the UI shows a warning (details in `docs/CHAT_MEMORY_ENHANCEMENTS.md`).
---

## 6. Before handing back any change

Run the backend locally (`backend/readme.txt`) and the frontend (`npm run dev` in `jungle-house-wiki-ai/`), log in, and check what your change touches, plus:

- [ ] `npm run build` and `npx eslint <changed files>` pass. `python -c "import ast; ast.parse(open('backend/src/app.py', encoding='utf-8').read())"` passes.
- [ ] If chat or escalation was touched, the tests in `docs/CHAT_MEMORY_ENHANCEMENTS.md` pass (`py backend/src/test_chat_memory.py`, `node --test …`).
- [ ] AI Chat: a normal question, an image question, escalation, and New Chat all behave as before.
- [ ] Notion Sync: Apply, Bulk Apply, trash, restore and the auto-categorize button work. A hand-changed category survives another button press.
- [ ] Knowledge Base, Content Management and Article Detail load. The Notion label only shows on categorized Notion articles.
- [ ] Language switch (en/zh/ms) has no missing keys and no new hard-coded English. The mobile layout is unchanged.
- [ ] `git diff --stat` shows only the files in your approved plan. No changes to routes' existing responses, tables, auth or deployment files.

When you're done, report: a summary of the diff, each check with pass, fail or not tested (be honest), and anything you noticed but deliberately did not fix.
