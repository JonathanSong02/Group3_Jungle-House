# Chat memory and issue escalation handover

本次实现 Stage 1、Stage 1b、Stage 2。未提交、推送或部署；未连接真实数据库或 provider，未执行 SQL。

## 实现范围

- `backend/src/app.py`：可选文字历史的校验、追问检测和一次检索词解析；主页面会话命名空间；升级上下文校验、服务器触发问题/原因/接收时间、保存状态；管理列表附带可选上下文。
- `backend/src/db_helper.py`：升级去重按员工、会话、议题区分；上下文独立存取；上下文失败不撤销原工单。重试保留原快照；永久删除工单时由新表外键级联清理。
- `jungle-house-wiki-ai/src/pages/Chat.jsx`：发起会话快照、文字历史、所有提交路径的会话 ID、升级上下文、消息时间和保存失败提示。
- `src/utils/chatIssueContext.js`：按主体词重叠、助手上下文词及明确承接/纠正选择一个议题，恢复较早讨论；不只取最后 N 条。
- `src/components/EscalationContext.jsx`：英/中/马展示触发问题、议题描述、原文摘录、角色、客户端时间、附件和升级原因，标明客户端来源及截断。
- `Escalation.jsx`、`admin/ReviewManagement.jsx`：展示同一份上下文，不改变回答、批准或发布操作。

## 行为与限制

原先完整会话已存于按用户分区的浏览器 localStorage。现在仍保留完整保存历史；无服务器完整会话或跨设备聊天历史。

普通文字的记忆请求最多选择最近 4 轮与 4 轮较早相关讨论，上限 16 条、每条 1,000 字符、内容总计 12,000 字符。忽略错误、停止、附件讨论和未选择的候选答案。独立问题不增加记忆 provider 调用；追问最多调用一次现有配置 provider 的单次请求函数，8 秒网络超时，不重试。失败恢复原检索词，取消走停止流程。回答仍由原知识库约束，不把助手旧回答当政策。

输出只接受最多 500 字符的结构化返回，检索词最多 300 字符，并校验引用的用户主体、索引与词项来源。原服务不支持统一的生成 token 上限，因此这不是模型生成量的硬上限；8 秒也不是整个请求的总时限。已发出的同步 HTTP 调用不能即时中断。

主页面在文字、附件和强制升级请求中发送 `main-<local session id>`，三个字典均使用“认证用户＋会话”键。New Chat 不读取旧会话或旧浮动聊天字典。旧客户端不提供 ID 时保留原键。字典仍是进程内临时状态；重启/不同 worker 不保证保留该状态。前端已有的显式 SOP context 和保存消息可用于继续处理，但不等于服务端持久化对话。

升级上下文最多 40 条、每条 2,000 字符、内容总计 40,000 字符，每条最多 4 个私有聊天附件引用。原保存历史不变；省略数量和截断明确展示。议题描述由原问题、较新纠正与触发问题的摘录组合，补充原消息，不替代原消息。新消息记录 ISO 时间；旧消息没有时间就显示未知，不补造。附件只保留已有私有聊天文件路径，不上传历史图片数据或抓取外部链接。

议题归属与旧消息选择都是启发式，不能保证完全召回、纠正所有隐含指代或完美区分相似议题。当前文字澄清/语言桥接、检索和升级流程基本保留。尤其相似词汇、缺少主体和跨议题纠正可能导致保守 fallback 或选择不全。

持久化的是升级时由客户端提交的有界快照，不是经独立核实的服务器历史。服务器确定认证员工、实际触发文字、升级原因和接收时间；以前的内容、角色与时间仍属于客户端提供的数据。它不用于认证、权限判断、自动批准或可信政策学习。建立独立可信历史需要另行设计每轮服务器记录，不在本次范围。

## 部署前必须人工处理

1. 审查 `mysql/escalation_context.sql`。它不包含 `USE`，不更改已有表，也不会被应用自动执行。
2. 确认目标数据库、现有 `escalation` 使用 InnoDB、`escalation_id` 是匹配的 INT 主键，并先在本地隔离数据库应用/验证。不要把历史 SQL 文件批量导入共享数据库。
3. 再由负责部署的人将这份新增表迁移应用到正确目标，验证后部署后端与前端。
4. 未安装新表时原工单照常保存；上下文无法持久化会显示警告。读取旧工单/审核记录仍可用。此时不能宣称 Stage 2 已在运行环境启用。

原 `question`、`ai_answer`、`manual_answer` 字段不被上下文复用。路由路径/方法、共享 Axios、CORS、认证/CSRF、角色、环境变量、Railway/Vercel 配置、依赖和 CSS 导入/层叠顺序未改。Team Lead 回答及审核/批准/发布的现有权限保留；当前后端部分批准接口允许 Team Lead、Manager、Admin，不能描述为只有 Manager。

## 可重跑验证

后端测试只用 Python 标准库，不导入整个 app、不启动 Notion、不调用真实数据库、AI、通知或升级。测试从当前源码提取实际函数与聊天处理函数，在外部边界使用 mocks。这不是 Flask/数据库端到端验证。

```powershell
py backend/src/test_chat_memory.py
```

前端新增纯函数与 React 服务端渲染测试，复用现有依赖，没有新增 npm test script。这不是浏览器交互测试。

```powershell
cd jungle-house-wiki-ai
node --test src/utils/chatIssueContext.test.js src/components/EscalationContext.test.js
npm.cmd run build
npm.cmd run lint
```

已通过：后端语法检查与 78 项隔离测试；16 项前端纯函数/组件服务端渲染测试；前端构建；diff 空白检查。已有 13 项临时前端 mock 检查也复测通过，包含生成期间切换会话后的成功、失败、取消归属。

| 原验收项 | 当前结果 |
| --- | --- |
| 独立问题不增加记忆调用 | Pass：隔离测试，额外调用为 0 |
| 产品追问主体 | Pass：隔离测试；真实 provider 回答 Not tested |
| closing → opening | Pass：隔离测试 |
| 六条以外的旧相关信息 | Pass：历史/议题选择测试；不保证所有隐含指代 |
| New Chat 与旧服务器上下文隔离 | Pass：主页面三个字典的会话键测试；旧无 ID 调用保留原行为 |
| 切换聊天时的历史与响应归属 | Pass：前端 mock 成功/失败/取消 |
| 最新相关纠正 | Pass：隔离与议题选择测试；无法明确关联时保守 fallback |
| 英/中/马追问 | Pass：隔离测试 |
| 问候、无效输入、纠错、新话题 | Pass：隔离测试；完整 slang 联调 Not tested |
| Step N、next、not this | Pass：实际聊天函数隔离测试 |
| 图片、图文、无关图片 | Pass：流程隔离测试；真实 CLIP/OCR/vision Not tested |
| 升级保留原问题 | Pass：实际聊天函数隔离测试 |
| 记忆处理期间取消 | Pass：隔离测试，后续回答/升级未调用 |
| 无 provider、超时、畸形历史 | Pass：隔离测试 |
| 浮动聊天 | Pass：无历史/无会话 ID 旧路径测试；实际 UI Not tested |
| 日志/分析保留原措辞 | Pass：调用参数隔离测试；真实数据库写入 Not tested |
| 手机与语言切换 | Pass：三语言 SSR；实际浏览器/手机交互 Not tested |
| 差异符合最终授权范围 | Pass：未改 API/auth/部署配置、依赖或 CSS 导入 |

lint 仍有既有 36 errors / 10 warnings。三个修改的页面与 HEAD 的诊断相同；四个新增前端文件没有 lint 错误或警告。未屏蔽规则。

尚未验证：真实 Flask 认证/CSRF、MySQL 迁移与持久化/重试/级联删除、真实 provider、完整图片检索、浏览器手机布局与交互，以及跨 worker 联调。本机原 Python 安装和后端环境无效，验证使用临时免安装 Python；没有修复全套后端依赖，也没有可用的本地数据库/AI 配置。

## 提交前范围

仅提交本次相关源文件、测试、本文档和新的独立 SQL。保留既有 `.claude/`、本地配置、缓存和用户其他文件，不执行 `git add .`；不提交临时 Python 运行目录、环境或凭据。

## 2026-11-23 更新：所有文字追问都检查对话（LIONG1934）

经用户批准，改变了上面“独立问题不增加记忆调用”这一条：

- `needs_conversation_context` 不再要求“它 / 这个的 / that one”等指代词。除问候、无效输入、不满意、Step N / next / 下一步 等控制词外，只要有合法历史，就交给 `resolve_conversation_search_query` 判断。解析提示新增一句：问题本身已完整时返回 `{}`，检索词保持不变。目的是支持“你刚才说 A……”这类没有固定字眼的回指。
- 代价：聊天中第二题起，每题多一次最多 8 秒、不重试的 provider 调用；失败或超时仍恢复原检索词。
- `answer_question_with_ai_provider` 新增可选 `conversation_history`：AI 兜底回答的提示里附上最近对话（最多 8 条、4,000 字符，保留最新），明确标为不可信上下文，不能作为事实或政策来源。图片、附件、强制升级和无历史请求的提示与之前逐字相同。
- 测试：`test_chat_memory.py` 改了 4 个原本断言“独立问题不调用”的测试，新增 9 个（三语回指、新话题保留自身检索词、解析失败保留原流程、提示有界与不可信标注、图片/无历史提示不含对话）。全部后端测试 386 项通过（临时环境）。真实 provider 未联调。

## 2026-11-23 更新：聪明模式 Smart chat（LIONG1934）

经用户批准：AI 不再只是找不到答案时的后备，而是为每个普通文字工作问题写答案。

- 新增 `smart_chat_enabled()`：默认开启；Railway 环境变量 `SMART_CHAT_ENABLED=0/false/off/no` 立即恢复旧行为（旧提示逐字相同，已比对）。
- 适用：`needs_conversation_context` 为真（排除问候、无效输入、不满意、Step N / next / 下一步），且不是图片 / `image_query`。Team Lead 批准答案、强制升级等提前返回的路径不受影响。
- `answer_question_with_ai_provider(..., smart=True)`：去掉“一到两句”限制，改为自然回答（先直接答，再解释，约 150 字内，可合并多篇文章）；问题有多个可能时返回 `{"answered": false, "clarify": true, "question": "..."}`，只问一个短问题。
- 合并规则：
  - 已找到 SOP 步骤或选项按钮时，只替换上方文字，步骤、图片、链接、选项不动；SOP 只有在 AI 引用的是同一篇文章时才替换文字，否则保留原文字；SOP 上的反问会被忽略。
  - 其他情况：回答 → `ai_provider_answer`；反问 → `ai_provider_clarify`（不升级）；找不到 → 原升级流程。
  - AI 出错 / 超时 / 未设定：结果与检索原样相同。
- 测试：`test_chat_memory.py` 新增 13 个 smart 测试；后端全部测试通过（临时环境）。真实 provider 未联调。

## 2026-11-23 更新：文件总结、系统资料与系统使用说明（LIONG1934）

- 文件来源：除附件栏外，也读取文章内容里链接的 `/static/uploads/articles/*.pdf|docx`（Notion 同步的文件）。`notion_sync_service.download_and_host_notion_file` 现在把 Word 存成 `.docx` / `.doc`（之前错存成 `.png`），类型不明时按网址后缀判断；图片与 PDF 行为不变。
- 每份文件抽字后请 AI 总结一次（约 120 字，存在 `article_attachment_text.summary`，迁移 0006），之后重复使用；AI 未设定时跳过，下次同步补上。
- 新模块 `backend/src/system_knowledge.py`：问题涉及时才加入 AI 上下文（总上限 3,500 字，排在文章前面）——文章数量与分类、附件清单（含总结、所属文章）、有效 quiz 清单、提问者**自己的** quiz 成绩与未做清单；以及内建系统使用说明（每个左侧选单项与几个常见操作，含中英马名称、可用角色；无权限时说明谁能做、该找谁）。
- 一般工作问题不会触发（有测试，例如 "test strips" 不会被当成 quiz）。`Sidebar.jsx` 新增选单项而说明未更新、或名称与 `translations.js` 不一致时，`test_system_knowledge.py` 会失败。
- 测试：新增 `test_system_knowledge.py`、`test_notion_file_download.py`，扩充文件相关测试；后端全部 463 项通过（临时环境）。真实 provider 与资料库未联调。

## 2026-11-23 更新：修正列表答案被丢弃、反问选项、“更多细节”（LIONG1934）

- 修正：AI 答案字符串内含换行（列清单时常见）时，`json.loads` 严格模式会判为无效 JSON，答案被丢弃并退回相关文章列表。现在用 `strict=False` 解析。
- 反问选项：智能模式的反问 JSON 可带 `options`（2–4 个短答案，后端清理为最多 4 个、每个 ≤ 80 字）；回应字段 `clarify_options`。`Chat.jsx` 在 AI 文字消息下显示按钮（沿用金色选项卡片样式），点击等同输入该文字并送出。测试：`Chat.clarify.test.js`（标准与 Staff 两种布局）。
- 更多细节：`wants_details()` 识别 more details / in detail / tell me more / 详细 / 细节 / terperinci 等；此时 `build_ai_chat_context(detail=True)` 上限 14,000 字，第一份相关文件给 9,000 字（无匹配段落时从文件开头取），提示允许约 400 字。一般问题不变。
- 系统说明的 AI Chat 段落已补上这两项。后端 474 项、前端 117 项测试通过。
