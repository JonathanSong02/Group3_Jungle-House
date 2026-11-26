# AI 离开页面也照常跑（第一步）＋ 手机推送（第二步）设计

日期：2026-11-26 · 状态：等用户批准 · 只做第一步，第二步之后另写设计

## 1. 为什么要做

员工（多数用手机）问 AI 或经理叫 AI 出 quiz 后，一换页面、手机放后台或信号断掉，答案就丢了。
原因：`Chat.jsx` 自己等 `/api/chat` 的回应，页面关掉后回应回来没人接（React state 已卸载，`saveChatSessionsToStorage` 写在 `setChatSessions` 里，不会执行）。`QuizManagement.jsx` 的 AI 出题（最长 150 秒）同理。

用户要的：像 Gemini 一样，问完可以去做别的事，AI 好了会通知；手机放后台也会通知（第二步）。

## 2. 目标 / 不做 / 绝对不能

**目标（第一步）**
- 聊天页、AI 出 quiz：换页面、手机放后台、网络短暂断线后，回来答案都还在。
- 答案好了而你不在那一页：角落跳小框"✓ AI 回答好了，点这里查看"，左边选单对应项目亮小红点，看过就消失。浏览器分页在背景时，分页标题也提示。
- 可以在**另一个对话**问新问题；同一个对话要等上一题答完（像 Gemini）。

**不做**
- 不做"手机问、电脑看"（聊天记录仍存在各自机器的 localStorage）。
- 第一步不做手机系统推送（第二步）。
- 铃铛 🔔 通知清单不放 AI 回答（用户选的）。

**绝对不能（用户明讲）**
- 不能让答案变不准：AI 流程、找文章、提示词、`chat()` 里的判断一律不改。
- 不能让速度变慢：人留在页面时，拿答案的路和现在完全一样；存副本不能让回应晚送出。

## 3. 做法比较（用户已选）

| 做法 | 说明 | 结果 |
|---|---|---|
| 一次做完，装 pywebpush | 稳，但要加新依赖（需批准） | 没选 |
| 一次做完，不装新东西 | 用现有 `cryptography` 自己写推送加密 | 没选为一次做完 |
| **分两步（选这个）** | 先做"答案不丢＋页内通知"；第二步推送用"不装新东西"的方式 | **用户选** |

第一步内部的选择（我的决定）：**不改成"先开工单、再轮询"**。页面照旧直接等 `/api/chat` 回应（零额外等待），服务器另外存一份结果，只在页面没接到时才去拿。轮询式会让每一题都多等至少一次轮询间隔，违反"不能变慢"。

## 4. 第一步设计

### 4.1 后台（`backend/src/app.py` + 新小模块）

- **新表 `ai_task_result`**（需用户批准；按惯例：`backend/migrations/0008_ai_task_result.py` ＋ 执行时 `ensure_table`，定义相同，有测试比对）：
  `ai_task_result_id` PK · `user_id` INT NOT NULL（FK → users ON DELETE CASCADE）· `request_id` VARCHAR(64) NOT NULL · `kind` VARCHAR(20)（`chat` / `quiz`）· `status` VARCHAR(20)（`done` / `error`）· `http_status` INT · `result` MEDIUMTEXT（回应 JSON 原文）· `created_at` DATETIME · 唯一 `(user_id, request_id)`。
- **存副本**：`/api/chat` 与 `/api/admin/quizzes/ai-generate` 有 `request_id` 时，在回应做好后，把**要送出的同一份 JSON** 与状态码交给背景线程写入（不阻塞回应）。用 after_request 接回应主体，不碰每个 return。没有 `request_id`（旧客户端）完全不变。用户按"停止"的请求不存。
- **拿副本**：新路由 `GET /api/ai-tasks/<request_id>` → 只查 `current_auth_user_id()` 自己的。回 `{found: false}` 或 `{found: true, kind, status, http_status, result}`。所有已登入用户可用（不放进经理/组长清单）。
- **清理**：写入时顺手删 7 天前的列（最多每 10 分钟一次）。
- `/api/admin/quizzes/ai-generate` 多收一个**选填** `request_id`；回应不变。
- 服务器重启时正在跑的题：不会有副本 → 前端等到期限后显示"这题没跑完，请再问一次"。

### 4.2 前端

- **新的全站"AI 工作看管员"**（`src/context/AiTaskContext.jsx`，挂在 `StaffLayout`，和 `StaffChatProvider` 同层）：
  - 负责真正发出请求、等回应；页面换掉它还在。
  - 正在跑的工作同时记在 localStorage（`jh_ai_tasks_<userId>`：request_id、种类、对话 id、问题、开始时间），网页被手机杀掉、重开后还能接回。
  - 请求失败但**没有收到服务器回应**（断线、网页被暂停）时，不马上显示"连线错误"，而是每 3 秒问一次 `GET /api/ai-tasks/<id>`，最多 3 分钟；找到就当作正常回应处理。真的找不到才显示原本的错误／"请再问一次"。有收到服务器回应的错误（401、CSRF、500）照旧马上显示。
  - 回应到了：用和现在**同一套**函数（`buildAiMessage` 等）把答案写进那个对话的 localStorage；聊天页开着就即时更新，没开就留红点＋小框。
- **`Chat.jsx`**：发问改交给看管员；`loading` 从"整页一个"改成"每个对话一个"，所以可以在别的对话问。停止按钮照旧（中止＋`/api/chat/cancel`）。送出的内容、显示方式不变。
- **`FloatingAIChat.jsx`**：不改。查过没有任何页面 import 它，画面上不会出现（交接说明写"其他页面有浮动聊天"已过时）。
- **`QuizManagement.jsx`**：出题交给看管员；回到页面时恢复出好的题目草稿（存 localStorage，存档或丢弃后删）。
- **小框与红点**：新元件 `AiTaskNotice.jsx`，用现有 honey 主题的颜色与卡片样式，手机版不挡输入框。点小框跳到那个对话／quiz 页面。分页在背景时标题前加"✓"。
- **三语文字**全部进 `translations.js`；`system_knowledge.GUIDE_SECTIONS` 的 AI Chat 与 Quiz 段落补上"可以离开页面，好了会通知"。

### 4.3 防止服务器太忙

服务器只有一个 worker、4 条线。每人同时最多 2 个正在跑的 AI 工作（前端挡，超过显示"上一题还在回答中"）。和现在一样每题占一条线，没有新增背景工作。

## 5. 速度与准确率怎么证明

- 准确率：`chat()` 的判断逻辑零改动；测试比对"有存副本"和"没有"时回应 JSON 逐字相同。后台现有 600 多个测试全过。
- 速度：存副本在背景线程，`X-Chat-Timing` 的 total 不应增加（上线后用 DevTools 对比几题）。人留在页面时请求路径与现在相同。

## 6. 第二步（之后另写设计，只列重点）

网站加 manifest 与图示（iPhone 要"加到主屏幕"）、service worker、推送订阅表、VAPID 钥匙系统自动产生存在资料库（不用设 Railway）、用 `cryptography` 写 RFC 8291 加密并用 RFC 附录的官方测试例子核对。通知只写"AI 回答好了"，不显示内容；个人资料页可关。iPhone 第一次打开时有图文教学。

## 7. 需要注意的规矩

- 新表、新路由需要用户批准（交接说明 3.1、3.2）；新表走 `mysql/` 或 migration 的审查流程。
- 不加依赖、不碰 `api.js`、登录、部署设定。
- 动到别人的程式：`Chat.jsx`（多人）、`QuizManagement.jsx`——上线前告知相关组员。
- 不提交、不推送，交给用户检查。

## 8. 我自己决定、请用户确认的地方

1. 存副本 7 天后清掉。
2. 断线后最多等 3 分钟找答案。
3. 每人同时最多 2 个 AI 工作。
4. 出好的 quiz 草稿在你存档或丢弃前都保留。
5. 用户按"停止"的题不存副本。
