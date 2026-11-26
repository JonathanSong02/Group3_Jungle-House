# AI 好了推送到手机（第二步）设计

日期：2026-11-26 · 状态：用户说"直接做第二步"，以下是我替用户做的决定，试用后可改 · 接第一步 `2026-11-26-ai-keeps-running-design.md`

## 目标 / 不做 / 绝对不能

- 目标：AI 聊天答完、AI 出好 quiz，而员工没在看网页（锁屏、切去别的 app、关掉分页）时，手机/电脑跳系统通知；点通知打开那个对话或 quiz 页。
- 不做：通知里显示问题或答案；离线缓存网页（service worker 只处理推送，不拦截网页请求）。
- 绝对不能：改变 AI 答案、拖慢回应；加新依赖；改 `vercel.json`、Railway 设定、环境变量。

## 做法（用户之前选的"不装新东西"）

- **推送标准**：Web Push（RFC 8030）＋ VAPID（RFC 8292）＋ aes128gcm 加密（RFC 8291 / 8188），用已有的 `cryptography` 与 `requests` 手写，`backend/src/web_push.py`。用 RFC 8291 附录 A 的官方例子当测试。
- **钥匙**：第一次需要时自动产生一对 P-256 钥匙，存在新表 `web_push_key`（只有一列）。不用设 Railway。
- **订阅**：新表 `web_push_subscription`（user_id、endpoint 与其 SHA-256、p256dh、auth、通知文字 labels JSON、建立/最后成功时间）。同一 endpoint 再订阅就更新。推送服务回 404/410 就删掉。
- **通知文字**：前端订阅时把 `translations.js` 里当前语言的"AI 回答好了 / AI 出好 quiz 了 / 点这里查看"一起送上，存在订阅里，推送时照用——不另建翻译。
- **什么时候推**（不重复、不打扰）：第一步存副本的背景线程，存完后等 4 秒；这 4 秒内网页若在"看得见"的状态收到答案，会 `POST /api/ai-tasks/<id>/seen`，就不推。按"停止"也会送 seen。只推聊天（不论答案或错误讯息）与成功的 quiz。seen 记在记忆体（单一 worker；重启只会多推一次，可接受）。
- **service worker**（`public/sw.js`）：收到推送一定显示通知（Safari 规定不能静默推送）；点通知时，若网站已开就切过去并告诉网页打开那个对话，否则开新视窗 `/chat?aiSession=<id>` 或 quiz 页。
- **加到主屏幕**：`public/manifest.webmanifest`＋图示（honey 主题色，用 Pillow 一次产生的 PNG，放进 repo），`index.html` 加 manifest、apple-touch-icon、theme-color。
- **开关**：个人资料页"手机通知"卡（开／关／被浏览器挡住时说明怎么在设定里打开／iPhone 未加到主屏幕时教步骤）。第一次问 AI 后，角落问一次"AI 好了要通知你吗？[开启] [不用]"，选过就不再问（每台机器记一次）。

## 新路由（全部只限已登入者，只动自己的资料）

- `GET /api/push/public-key` → `{publicKey}`
- `POST /api/push/subscribe` `{subscription:{endpoint, keys:{p256dh, auth}}, labels:{chat, quiz, view}}`
- `POST /api/push/unsubscribe` `{endpoint}`
- `POST /api/ai-tasks/<request_id>/seen`

## 资料库

migration `0009_web_push.py`：`web_push_key`、`web_push_subscription`（FK → users ON DELETE CASCADE）；执行时 `ensure_tables` 定义相同。

## 限制

- iPhone 要 iOS 16.4 以上，并且从主屏幕打开网站才收得到。
- 推送经 Google / Apple / Mozilla 的免费服务，偶尔慢几秒。
- 本地没有真的手机可测；加密用官方例子核对，真机由用户测。
