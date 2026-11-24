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

## 2026-11-23 更新：加速与“更多细节”追问（LIONG1934）

- 慢的主因：Gemini 3/4 默认先思考（3.8 Flash 默认 medium，3 Flash Preview 默认 high），一题追问要叫 AI 两次（中文再加翻译一次），常超过 30 秒，8 秒的追问解析也常超时。
- `ai_provider_service._call_gemini`：模型名为 `gemini-3*` / `gemini-4*` 时送 `generationConfig.thinkingConfig.thinkingLevel = "low"`（Google 文档写法）；若该模型回 400，去掉设定再送一次；只取非 thought 的文字部分。旧型号请求不变。测试：`test_ai_provider_gemini.py`。
- 提示要求纯文字、不用 Markdown（网页不显示粗体，`**` 会直接露出）。
- “更多细节”追问若解析失败，检索时带上上一题用户问题；详细回答时限 40 秒（一般仍 25 秒）。
- AI Settings 已由用户改为正式版 `gemini-3.8-flash`（原 `gemini-3-flash-preview` 为预览版，同代其他预览版已被 Google 关闭）。

## 2026-11-24 更新：短问题不再当乱打；AI 与旧规则选不同文章时听 AI（LIONG1934）

- `looks_like_known_term()`：系统词（pdf、quiz、sop…）或线上文章标题里的字（缓存 10 分钟）组成的短问题，不再被 `is_nonsense` 当无效输入，聊天入口与 `needs_conversation_context` 都适用。读不到标题时只认系统词。
- 旧规则（`predict_intent.py` 读 4 月的固定 CSV）与 AI 选了不同文章时（AI 的 sourceTitle 必须是交给它的候选文章之一），改信 AI：用该标题重跑 `process_question` 取得那篇的步骤与图片；取不到就只显示 AI 答案、清掉错误的步骤。AI 指名的文章不在候选内时仍保留原结果。

## 2026-11-24 更新：AI 先答、Show more details、Related articles、计时器（LIONG1934）

- AI 先答：智能模式下，AI 的回答取代旧规则（`process_question`）的步骤卡片或选项清单；旧规则只在 AI 失败、AI 无法回答，或 AI 婉拒、却说不出依据的文章（而旧规则找到了步骤）时作为备用。组长批准答案、问候、Step/next 控制、图片聊天不变。
- 回应新增 `related_articles`（最多 3 篇其他候选文章）；`result.context.title` 记住本次文章，下一题以 `focus_title` 把该文章放在 AI 上下文第一位（`build_ai_chat_context(focus_title=...)`）。
- 提示加强：理解口语、错字、混合语言；笼统问题（例如只打 "opening"）匹配多篇时，以文章标题当选项反问。
- 计时器：`record_chat_stage()` 记录 translate / follow_up / rules / ai_answer 秒数，`log_chat_timing` 每题印一行 `CHAT TIMING total=…`（不含问题内容）。刻意不包装函数，以免 `log_chat_failure` 的错误位置变成包装函数。
- 翻译与追问理解**未**并行：并行会让中文追问时 Alan 的“关键词必须来自用户原话”检查更常失败，影响准确率；先看计时数据再决定。
- 前端：`ArticleDetail.jsx` 的内容、附件、相关链接拆成共用元件 `components/ArticleBody.jsx`（改前改后 HTML 完全相同、截图逐像素相同）；`components/ChatArticleDetails.jsx` 在聊天答案下提供可展开的 Show more details（同一元件、同一样式，不跳页）；Related articles 用编号按钮，点选即以该标题提问。测试：`Chat.details.test.js`。

## 2026-11-24 更新：找文章与段落的准确率（LIONG1934）

- 问题：“how many cabinet i need to open when opening” 找不到 JHKC 的 cabinet 那一句。原因是每篇文章从开头整篇放入，6,000 字被前面的长文章用完。
- `build_ai_chat_context`：
  - 每篇只放与问题相关的段落（`best_passages`，保持原顺序）；最相关的一篇约占 40%，其余平分；短文章照旧整篇。
  - 罕见词加权（IDF，例如 timetec、maybank 比 check、using 重要），用于排序与段落挑选；标题词权重为常数 `TITLE_WORD_WEIGHT = 3`。
  - 交给 AI 的文章由 5 篇改为 7 篇。
- 新测试 `test_retrieval_audit.py`：用 `backend/data/cleaned_knowledge.csv` 的每个步骤自动出题，检查答案那句有没有进入 AI 的上下文（无 AI、无数据库、约 5 秒）。2026-11-24 实测：带主题词 99%（433/436）、只有关键词 95%（414/436）；另钉住真实失败的问题。
- 限制：CSV 只有 4 月的 48 篇；正式数据库约 500 篇，真正的准确率需要用正式数据检查。

## 2026-11-24 更新：正式数据的搜索准确率检查（AI Model Settings）（LIONG1934）

- 新卡片“检查搜索准确率”（`pages/admin/RetrievalAuditCard.jsx`，放在 AI Model Settings 页下方，沿用 `ais-*` 样式）：经理按“开始检查”，后台用网站上现在的每一篇文章出题（每篇约 3 句，最多 1,500 题；中间那题不带标题词，像员工常常不打主题），走真正的聊天搜索，检查那一句有没有交到 AI 手上。不叫 AI、不花钱；每 2 秒更新进度。
- 报告：找到答案的百分比、选错文章（`wrong_article`）与文章对但那一句被切掉（`line_cut`）的数量、每题的问题／答案所在文章／原句／搜索选了哪几篇（最多列 200 题）。
- 后端：`retrieval_audit.py`（出题、判定、同一步骤出现在别篇也算找到、后台线程与内存状态；一台 worker，重启即清空）；`load_chat_search_data()`；`build_ai_chat_context(preloaded=(articles, documents))` 让检查只读一次数据库（聊天不传，行为不变；有测试证明结果与读数据库时完全相同）。路由 `POST/GET /api/ai-settings/retrieval-audit`，列入 `_MANAGER_ENDPOINTS`（只限经理），已在跑时回 409。
- 用 CSV 的 48 篇试跑：119 题对 118 题（99%），约 3 秒；以 500 篇长文章估计约 3–4 分钟。
- 速度：用 500 篇长文章实测 `build_ai_chat_context` 每题约 0.15 秒，所以聊天慢不是找文章造成，没有加缓存。
- 测试：`test_retrieval_audit_live.py`、`test_retrieval_audit.py::LiveCheckTests`、`RetrievalAuditCard.test.js`；系统使用说明（`system_knowledge.GUIDE_SECTIONS` 的 AI Model Settings）已加入此功能。
- 第二版（同日，看过正式结果 85.6%、662 篇、193 题选错文章之后）：
  - 搜索选到另一篇讲同一件事的文章也算找到（`same_info_in`：该句至少 60%、且至少 3 个字，要在上下文里靠在一起出现；整段上下文零散出现不算），另计 `foundElsewhere`。用 CSV 随机配对测过，误判 2/499（两句本来就在两份 roadshow 清单里都有）。
  - 报告新增重复的文章（`duplicate_articles`：同标题，或标题不同但内容完全相同），附文章编号与分类，方便在内容管理清掉多余的。
  - “开始检查”按钮固定一行（不再被说明文字挤成两行）。

## 2026-11-24 更新：聊天加速（AI 与旧规则同时跑、图片搜索少查数据库）（LIONG1934）

- 计时：聊天回应附 `X-Chat-Timing` / `Server-Timing` 标头（与 `CHAT TIMING` 记录相同），没有 Railway 权限也可在浏览器 DevTools → Network → chat → Headers 看到。新增细项：`team_lead`、`rules_articles`、`rules_images`、`rules_similar`、`rules_model`、`ai_context`、`ai_wait`。
- 实测（正式站，改前）：普通问题 9.6–14 秒；Gemini 本身约 4.7 秒、准备资料 1.9 秒，旧规则 1.6–5.4 秒（图片搜索 0.2–2.7 秒），追问理解出现时 5.5 秒。
- A：智能模式下，AI 回答在旧规则**之前**就在背景开始（`EarlyCall`，用 contextvars 让背景线程看到同一个 request 与 `g`），旧规则同时进行。AI 的输入由 `ai_answer_arguments()` 统一产生；只有第一题、或页面送来上一题文章标题时才提早开始（此时输入不会被旧规则改变），而且使用前比对输入完全相同，否则照旧在旧规则之后再问。结果与原本一样；员工按停止时，已开始的 AI 呼叫会用掉少量额度。测试：`test_chat_parallel_ai.py`。
- B：`db_helper.search_image_retrieval`（Alan）由每张图各查一次文章／升级单，改为每种来源一次查完（约 20 次 → 3 次查询），比对规则不变；`process_question` 的图片搜索由两次（limit 1 与 10）改为一次，取第一个当最佳结果。与旧版随机比对 600 次（228 次有找到图片）结果完全相同。测试：`test_image_search_speed.py`。

## 2026-11-24 更新：看意思搜索（semantic search）（LIONG1934）

- 用户选择：用 Google（同一把 Gemini key）、不是 Gemini 时自动只看字、用 AI 写换字考题证明效果、AI Settings 不加开关（紧急关闭：环境变量 `SEMANTIC_SEARCH_ENABLED=0`）。
- `semantic_search.py`：每篇文章（加 PDF/Word 附件文字，最多 40 段）切成约 900 字的段落（是 clean 文字的原样片段），用 `gemini-embedding-2`（不行时 `gemini-embedding-001`）转成 768 个数字，存在 `article_chunk_embedding`（migration 0007）。背景每 5 分钟检查，只重做内容 hash 有变的文章；多篇共用一次 Google 呼叫（每次最多 100 段）。索引放在记忆体，只在背景同步时重读数据库，员工提问时不读。
- `build_ai_chat_context`：问题也转成数字（每题一次，有缓存），找出意思最接近的段落；看字的排名与看意思的排名用 reciprocal rank fusion 合并（`FUSION_RANK_OFFSET = 20`、`SEMANTIC_WEIGHT = 1.0`），完全确定的标题命中仍排第一；每篇被选文章，意思最接近的那段一定放进给 AI 的内容（`with_section`）。没有 Gemini key、出错、超时（4 秒）都回到只看字，结果与以前完全相同（有测试）。
- 检查搜索准确率：新增「换字题」——AI 为每篇写 1 题员工口吻、用不同字的问题，加上文章里回答它的原句（原句必须真的在文章里才收），存在 `retrieval_audit_question`，文章改了才重写；第一次约 80 次 AI 呼叫（几分钱）。报告新增对照表：原字题／换字题 × 只看字／看字+看意思；错题标示「换字题」。题目的「意思」先分批一次取得。
- 测试：`test_semantic_search.py`（段落、Google 请求格式与换型号、批次、只重做有变的文章、合并排名、换字题验证与对照）、`test_retrieval_audit.py::MeaningSearchFallbackTests`、`RetrievalAuditCard.test.js`；`test_schema_migrations.py` 加入 0007。
- 本地无法用真的 Google 测试（没有 key）；上线后由「检查搜索准确率」的对照表看实际效果，再调整 `FUSION_RANK_OFFSET` / `SEMANTIC_WEIGHT`。

## 2026-11-23 至 11-24 总览（LIONG1934）

两天内 AI 聊天的改动一览（细节见上面各日期段落）。全部经用户同意，由用户提交。

| 日期 | 提交 | 改了什么 |
|---|---|---|
| 11-23 | 567f7ae | 聊天记得对话、自然回答、会反问；读得懂 PDF 和 Word 附件（`article_attachment_text`，migration 0005） |
| 11-23 | c4612af | 文件一次性总结（migration 0006）；AI 能回答系统里有什么（文章数、分类、quiz）；内建系统使用说明 `GUIDE_SECTIONS` |
| 11-23 | f7435c0 | 反问时给选项按；"详细"给更完整答案；修好清单答案被丢掉 |
| 11-23 | 9536256 | Gemini 少思考（`thinkingLevel=low`）加速；答案不再出现 `**`；"更多细节"追问找得到文件 |
| 11-23 | 263075c | AI Settings：型号下拉选单（即时清单、推荐标示）、钥匙遮住加 Edit、测试成功才能存 |
| 11-23 | 832da31 | 反问选项改成直排编号 1 2 3，可打数字选，选过会标示 |
| 11-24 | b7d89fe | 短问题（PDF / AEON / SOP）不再被当乱打；AI 与旧规则选不同文章时听 AI |
| 11-24 | 4a3b00c | AI 先答；答案下可展开整篇文章（Show more details）与相关文章；计时器 `CHAT TIMING` |
| 11-24 | c705d20 | 找段落更准（只放相关段落、罕见词加权、7 篇）；AI Settings 加「检查搜索准确率」 |
| 11-24 | 25176a7 | 检查更会判断（别篇讲同一件事也算对）；列出重复文章；按钮固定一行；回应附 `X-Chat-Timing` |
| 11-24 | d5334b6 | 聊天加速：AI 与旧规则同时跑（`EarlyCall`）；图片搜索约 20 次查询减为 3 次 |
| 11-24 | 9bc5370 | 看意思搜索（Gemini embedding，migration 0007）；检查加入换字题与「只看字 vs 看字+看意思」对照 |

动到他人代码（已告知或待告知）：XinWei（旧规则 `process_question`，现为后备；图片搜索只跑一次、加计时）、Alan（追问理解；`db_helper.search_image_retrieval` 改为批次查询，规则不变）、Jonathan（`ArticleDetail` 拆出共用的 `ArticleBody`）。

待办：上线后跑「检查搜索准确率」看对照表，再调 `FUSION_RANK_OFFSET` / `SEMANTIC_WEIGHT`；看 `X-Chat-Timing` 决定是否做 C（追问理解只在像追问时叫 AI，Alan 的功能，需同意）与 D（换 gemini-3.6-flash 用 minimal 思考）。

## 2026-11-24 更新：删除旧规则，聊天只由 AI 回答（LIONG1934，XinWei 已同意）

- 删除：`predict_intent.py`、`train_model.py`、`backend/models/intent_model.pth` 与 metrics（PyTorch 意图模型，只认得 4 月 CSV 的 48 篇）；`app.py` 的 `process_question`、`call_model_answer`、`build_training_data_options_from_model_reply`、`should_escalate_generic_answer`、`update_ai_fail_count`、`search_related_knowledge_base_articles`、`smart_chat_enabled`（`SMART_CHAT_ENABLED` 不再有作用）、`EarlyCall`；没有人呼叫的 `create_quiz_and_questions`；开发用 `/api/chat/test`（`chat_test`）。`/` 与 `/api/health` 不再回报 `model_available` 等栏位。`backend/data/cleaned_knowledge.csv` 保留（准确率测试的考卷）。
- 新流程（`chat()` 在组长批准答案之后）：
  1. "show step 4"：有上一题文章 → 那一步的卡片（`build_step_answer_from_last_topic`，读线上文章）；没有主题、也没有对话 → 问哪个主题；有对话 → 交给 AI。
  2. 其余文字问题与照片问题都交给 AI（`answer_question_with_ai_provider`）。
  3. AI 回答 / 反问选项 / 礼貌拒绝 → 照旧显示（Show more details、Related articles）。
  4. AI 读了文章但找不到 → `source: ai_not_found`，"知识库里找不到…"（三语）+ 搜索找到的相关文章卡片（`related_article_options`，看字+看意思，不用 AI）+ "这些内容有帮助吗？/ 转交给组长" 按钮。**不会自动开单**（连续找不到也不会）。
  5. AI 服务出错、超时、额度用完或没设定 → `source: ai_unavailable`，只显示 "AI chat is currently unavailable. Please try again later."（三语，`CHAT_FAILURE_MESSAGES["ai_unavailable"]`），不转组长、不显示 fallback 标签。
  6. 照片问题：AI 答不出时，用新搜索找前 3 篇，逐篇用 Alan 的 `hybrid_image_service.verify_text_result` 检查有没有确切句子（`verify_image_question_with_search`）。
- 回应一律经 `chat_reply()`：保留我们设定的 fallback / escalation 旗标（`standardize_ai_response` 会把答案里有 "escalate" 字眼当成升级）。
- 前端：拿掉回答上的 "Match score" 与 "Source" 标签、文章卡片上的 "来源 · 百分比" 标签；没有 Show more details 的回答（例如照片答案）保留文章名称连结 ↗。聊天记录页与复制文字不变。
- 不变：问候、乱打字过滤、"不是这个"→ 组长、员工自己按"转交给组长"、组长批准的答案优先、追问理解、看意思搜索。
- 测试：`test_chat_memory.py`（Alan）、`test_chat_failure_messages.py`、`test_dev_only_routes.py`、`test_hybrid_image_pipeline.py`、`Chat.image.test.js` 改为检查 AI 收到的搜索内容与新的三种结果；删除 `test_chat_parallel_ai.py`（旧规则与 AI 同时跑已不存在）；新增 `test_retrieval_audit.py::AiOnlyChatHelperTests`。
