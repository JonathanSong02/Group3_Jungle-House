"""What the AI chat knows about the Wiki system itself.

1. Facts about what is in it (anyone may ask): article counts per category,
   the attached documents (with their one-time summaries), the active
   quizzes, and the asker's OWN quiz attempts.
2. A built-in guide to the menus and pages ("where is the quiz?"), with who
   may use each page. If the asker's role cannot use a page, the guide says
   who can and whom to ask.

Each piece is added to the AI context only when the question is about it,
so ordinary work questions cost nothing extra. Every database read here is
optional: on any failure that piece is skipped.

KEEP IN SYNC: every sidebar item in jungle-house-wiki-ai/src/components/
Sidebar.jsx needs a GUIDE_SECTIONS entry, and the labels must equal
translations.js. test_system_knowledge.py fails when they drift.
"""

import re

STATS_LIMIT = 900
DOCUMENTS_LIMIT = 2000
QUIZ_LIMIT = 1200
MY_QUIZ_LIMIT = 1000
GUIDE_SECTION_LIMIT = 1100
MAX_GUIDE_SECTIONS = 2

ROLE_NAMES = {"staff": "Staff", "teamlead": "Team Lead", "manager": "Manager"}

_COUNT_OR_LIST = re.compile(
    r"how many|number of|\bcount\b|\btotal\b|\blist\b|\bwhich\b|what (?:are|kind)|\ball (?:the )?\w+s\b"
    r"|几|多少|总共|一共|有哪些|哪些|列出|清单|berapa|senarai|jumlah|apakah", re.I)
_ARTICLE = re.compile(r"\barticles?\b|knowledge base|categor|文章|知识库|分类|类别|artikel|kategori|pangkalan", re.I)
_DOCUMENT = re.compile(r"\bpdfs?\b|documents?|\bfiles?\b|attachments?|manual|handbook|\bword\b|docx"
                       r"|文件|档案|附件|手册|文档|dokumen|\bfail\b|lampiran", re.I)
# Not "test" / "exam" / 测试 / ujian: they also appear in ordinary work questions ("test strips").
_QUIZ = re.compile(r"quiz|training|测验|考试|培训|kuiz|latihan", re.I)
_MINE = re.compile(r"\bmy\b|\bi\b|\bme\b|\bi've\b|not done|haven'?t|have not|pending|\bscore|\bresult|\bpass"
                   r"|我|没做|还没|分数|成绩|结果|saya|\baku\b|markah|keputusan|lulus", re.I)
_HOW_TO = re.compile(r"\bhow\b|\bwhere\b|\bcan i\b|\bwhat is\b|\bwhat does\b|\bwhich page\b|\bfind\b"
                     r"|怎么|怎样|如何|在哪|哪里|可以|能不能|什么是|bagaimana|di mana|cara|boleh|mana", re.I)


def _normalise_role(role):
    role = re.sub(r"[\s_-]", "", str(role or "")).lower()
    return "manager" if role == "admin" else role


def _words(text):
    return set(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def _cap(text, limit):
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Built-in system guide
# ---------------------------------------------------------------------------
# "roles": who sees the item in the left menu (Sidebar.jsx). "keywords": words
# (en / zh / ms) that point to this section.
GUIDE_SECTIONS = [
    {
        "key": "dashboard", "nav_key": "nav.dashboard",
        "labels": {"en": "Dashboard", "zh": "仪表板", "ms": "Papan Pemuka"},
        "roles": {"staff", "teamlead"},
        "keywords": ["dashboard", "home page", "homepage", "main page", "主页", "首页", "仪表板", "papan pemuka", "laman utama"],
        "text": "The home page after signing in. It has shortcuts to ask the AI, browse the Knowledge Base and check "
                "notifications and training updates.",
    },
    {
        "key": "admin_dashboard", "nav_key": "nav.adminDashboard",
        "labels": {"en": "Admin Dashboard", "zh": "管理仪表板", "ms": "Papan Pemuka Admin"},
        "roles": {"manager"},
        "keywords": ["admin dashboard", "manager dashboard", "管理仪表板", "papan pemuka admin"],
        "text": "The Manager's home page: an overview of the system with shortcuts such as Add Article.",
    },
    {
        "key": "ai_chat", "nav_key": "nav.aiChat",
        "labels": {"en": "AI Chat", "zh": "AI 对话", "ms": "Sembang AI"},
        "roles": {"staff", "teamlead", "manager"},
        "keywords": ["ai chat", "chat", "ask ai", "ask a question", "chat history", "new chat", "upload photo",
                     "upload document", "对话", "聊天", "问ai", "提问", "聊天记录", "sembang", "tanya ai"],
        "text": "Ask questions about SOPs, products, training and daily operations: type the question and press Send. "
                "You can ask follow-up questions, and say \"you said earlier...\". The \"+ Attach file\" button lets you send a photo, "
                "PDF or Word file. The \"Chat History\" tab lists earlier chats and has a search "
                "box. If an answer is not right, choose \"No, escalate to a team lead\" to send the question to a Team Lead.",
    },
    {
        "key": "escalate", "nav_key": None,
        "labels": {"en": "Escalate a question", "zh": "升级问题给组长", "ms": "Eskalasi soalan"},
        "roles": {"staff", "teamlead", "manager"},
        "keywords": ["escalate", "team lead", "teamlead", "send my question", "wrong answer", "not correct",
                     "nobody answered", "升级", "组长", "答错", "答案不对", "eskalasi", "ketua pasukan", "jawapan salah"],
        "text": "When the AI cannot answer, or its answer is wrong, choose \"No, escalate to a team lead\" under the answer "
                "in AI Chat. The question goes to the Team Leads' \"Escalation\" page, where a Team Lead writes the answer. Once "
                "the answer is approved, it is saved so the AI can answer the same question next time.",
    },
    {
        "key": "knowledge_base", "nav_key": "nav.knowledgeBase",
        "labels": {"en": "Knowledge Base", "zh": "知识库", "ms": "Pangkalan Pengetahuan"},
        "roles": {"staff", "teamlead"},
        "keywords": ["knowledge base", "browse", "search article", "find article", "read article", "sop list",
                     "知识库", "找文章", "看文章", "搜索文章", "pangkalan pengetahuan", "cari artikel", "baca artikel"],
        "text": "Browse approved company knowledge by category (SOP, Product, Sales, Training, Notice) or type in "
                "\"Search articles...\". Open an article to read it; attached PDFs can be previewed on the article page.",
    },
    {
        "key": "messages", "nav_key": "nav.messages",
        "labels": {"en": "Messages", "zh": "消息", "ms": "Mesej"},
        "roles": {"staff", "teamlead", "manager"},
        "keywords": ["message", "messages", "chat with", "contact my manager", "contact team lead", "私信", "消息",
                     "发消息", "联系", "mesej", "hantar mesej"],
        "text": "Internal chat between staff, Team Leads and Managers. Choose a chat on the left, type, and press Send.",
    },
    {
        "key": "notifications", "nav_key": "nav.notifications",
        "labels": {"en": "Notifications", "zh": "通知", "ms": "Pemberitahuan"},
        "roles": {"staff", "teamlead", "manager"},
        "keywords": ["notification", "notifications", "alert", "alerts", "通知", "提醒", "pemberitahuan", "makluman"],
        "text": "Your latest system updates and alerts, such as account, password and sign-in alerts (Managers also "
                "get Notion update alerts). "
                "Use \"Mark read\" to clear one. The bell at the top also opens them.",
    },
    {
        "key": "quiz", "nav_key": "nav.quiz",
        "labels": {"en": "Quiz / Training", "zh": "培训测验", "ms": "Kuiz / Latihan"},
        "roles": {"staff", "teamlead"},
        "keywords": ["quiz", "quizzes", "training", "测验", "培训", "考试", "kuiz", "latihan"],
        "text": "Training quizzes. Pick a quiz and press \"Start\", answer the questions, then \"Submit Quiz\". The result "
                "shows your score and the pass mark; \"Retake Quiz\" lets you try again.",
    },
    {
        "key": "content_management", "nav_key": "nav.contentManagement",
        "labels": {"en": "Content Management", "zh": "内容管理", "ms": "Pengurusan Kandungan"},
        "roles": {"teamlead", "manager"},
        "keywords": ["content management", "add article", "new article", "create article", "edit article",
                     "delete article", "article", "retrieve bin", "change category", "upload pdf", "attach",
                     "新增文章", "加文章", "编辑文章", "删除文章", "改分类", "内容管理", "tambah artikel", "edit artikel",
                     "pengurusan kandungan"],
        "text": "Manage Knowledge Base articles: add a new article, edit one (title, content, category, attachments "
                "such as PDF or Word files), or \"Move to Bin\". Articles in the \"Retrieve Bin\" can be restored. "
                "Change an article's category on its Edit page.",
    },
    {
        "key": "quiz_management", "nav_key": "nav.quizManagement",
        "labels": {"en": "Quiz Management", "zh": "测验管理", "ms": "Pengurusan Kuiz"},
        "roles": {"teamlead", "manager"},
        "keywords": ["quiz management", "create quiz", "make quiz", "new quiz", "build quiz", "add question",
                     "ai generate", "出题", "建测验", "新增测验", "测验管理", "cipta kuiz", "pengurusan kuiz"],
        "text": "Build and manage training quizzes: create a quiz, \"Add Question\", or use \"AI Generate\" to draft "
                "questions from Knowledge Base articles.",
    },
    {
        "key": "review_management", "nav_key": "nav.reviewManagement",
        "labels": {"en": "Review Management", "zh": "审核管理", "ms": "Pengurusan Semakan"},
        "roles": {"manager"},
        "keywords": ["review management", "approve answer", "publish answer", "publish knowledge", "审核", "发布答案",
                     "pengurusan semakan", "lulus jawapan"],
        "text": "Review answers that Team Leads wrote for escalated questions, approve them, and publish approved "
                "answers so the AI can use them.",
    },
    {
        "key": "user_management", "nav_key": "nav.userManagement",
        "labels": {"en": "User Management", "zh": "用户管理", "ms": "Pengurusan Pengguna"},
        "roles": {"teamlead", "manager"},
        "keywords": ["user management", "approve account", "approve user", "registration", "new staff account",
                     "用户管理", "批准账号", "注册申请", "pengurusan pengguna", "lulus akaun"],
        "text": "Review access requests from new staff (\"Approve\" or decline) and manage staff accounts. Changing a "
                "user's role or status is for Managers.",
    },
    {
        "key": "ai_settings", "nav_key": "nav.aiSettings",
        "labels": {"en": "AI Model Settings", "zh": "AI 模型设置", "ms": "Tetapan Model AI"},
        "roles": {"manager"},
        "keywords": ["ai settings", "ai model", "api key", "change model", "gemini", "claude", "openai", "deepseek",
                     "模型设置", "换模型", "tetapan model"],
        "text": "Choose which AI provider and model the chat uses, and enter its API key. Lightweight models (such as "
                "Gemini Flash or Claude Haiku) are faster and cheaper.",
    },
    {
        "key": "notion_sync", "nav_key": "nav.notionSync",
        "labels": {"en": "Notion Sync", "zh": "Notion 同步", "ms": "Sinkron Notion"},
        "roles": {"manager"},
        "keywords": ["notion", "sync", "同步", "sinkron"],
        "text": "Connect Notion, press \"Check for Updates\" to find new and edited Notion pages, and review each one "
                "before it is published to the Knowledge Base. It can also sort Notion articles into categories.",
    },
    {
        "key": "analytics", "nav_key": "nav.analytics",
        "labels": {"en": "Analytics", "zh": "数据分析", "ms": "Analitik"},
        "roles": {"teamlead", "manager"},
        "keywords": ["analytics", "statistics report", "usage report", "数据分析", "统计", "analitik"],
        "text": "Track how the AI chat is used and find knowledge gaps (questions it could not answer).",
    },
    {
        "key": "security", "nav_key": "nav.security",
        "labels": {"en": "Security / Monitoring", "zh": "安全 / 监控", "ms": "Keselamatan / Pemantauan"},
        "roles": {"teamlead", "manager"},
        "keywords": ["security", "monitoring", "login history", "audit log", "安全", "监控", "登录记录",
                     "keselamatan", "pemantauan"],
        "text": "Monitor sign-ins and system activity (login history and audit log).",
    },
    {
        "key": "escalation", "nav_key": "nav.escalation",
        "labels": {"en": "Escalation", "zh": "升级处理", "ms": "Eskalasi"},
        "roles": {"teamlead", "manager"},
        "keywords": ["escalation page", "escalated questions", "answer escalation", "manual answer", "升级处理",
                     "回答升级", "eskalasi"],
        "text": "Questions staff escalated from the AI chat. Open one, read the discussion, and write the answer with "
                "\"Submit Manual Answer\".",
    },
    {
        "key": "profile", "nav_key": "nav.profile",
        "labels": {"en": "Profile", "zh": "个人资料", "ms": "Profil"},
        "roles": {"staff", "teamlead", "manager"},
        "keywords": ["profile", "my account", "password", "change password", "my details", "个人资料", "我的账户",
                     "密码", "改密码", "profil", "akaun saya", "kata laluan"],
        "text": "\"My Account\": update your details and press \"Save Changes\". Use \"Change Password\" to set a new "
                "password (at least 8 characters, with an uppercase letter and a number).",
    },
    {
        "key": "language", "nav_key": None,
        "labels": {"en": "Language", "zh": "语言", "ms": "Bahasa"},
        "roles": {"staff", "teamlead", "manager"},
        "keywords": ["language", "chinese", "malay", "english", "translate", "语言", "中文", "华语", "英文",
                     "马来文", "bahasa", "cina", "inggeris"],
        "text": "Switch the screen language (English, 中文, Bahasa Melayu) with the globe \"EN\" button at the top of "
                "the page or at the bottom of the left menu. The AI answers in the language you ask in.",
    },
    {
        "key": "sign_in", "nav_key": None,
        "labels": {"en": "Sign in, sign out and new accounts", "zh": "登录、登出和注册", "ms": "Log masuk, log keluar dan akaun baharu"},
        "roles": {"staff", "teamlead", "manager"},
        "keywords": ["log out", "logout", "sign out", "log in", "login", "sign in", "forgot password", "register",
                     "new account", "登出", "退出", "登录", "忘记密码", "注册", "log keluar", "log masuk",
                     "lupa kata laluan", "daftar"],
        "text": "To sign out, click your name at the bottom of the left menu and choose to log out. Forgot your "
                "password? Use \"Forgot password\" on the sign-in page to get a reset email. New staff register on "
                "the sign-in page; a Team Lead or Manager must approve the account in User Management before it works.",
    },
]


def _keyword_hits(keyword, text_lower):
    if re.search(r"[㐀-鿿]", keyword):
        return keyword in text_lower
    return re.search(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", text_lower) is not None


def _guide_entries(question, role):
    text_lower = str(question or "").lower()
    asked_how = bool(_HOW_TO.search(text_lower))
    scored = []
    for position, section in enumerate(GUIDE_SECTIONS):
        label_hit = any(label.lower() in text_lower for label in section["labels"].values())
        hits = sum(1 for keyword in section["keywords"] if _keyword_hits(keyword.lower(), text_lower))
        if (hits or label_hit) and (asked_how or label_hit):
            scored.append((hits + (2 if label_hit else 0), -position, section))
    scored.sort(reverse=True)

    entries = []
    asker = _normalise_role(role)
    for _, _, section in scored[:MAX_GUIDE_SECTIONS]:
        allowed = [ROLE_NAMES[r] for r in ("staff", "teamlead", "manager") if r in section["roles"]]
        labels = section["labels"]
        body = (f"Menu / page name: {labels['en']} (中文: {labels['zh']}; Bahasa Melayu: {labels['ms']}). "
                f"Who can use it: {' and '.join(allowed)}. "
                + ("It is in the left-hand menu. " if section["nav_key"] else "")
                + section["text"])
        if asker in ROLE_NAMES and asker not in section["roles"]:
            body += (f" Note: the person asking is a {ROLE_NAMES[asker]} and cannot use this; only "
                     f"{' and '.join(allowed)} can. Tell them to ask their Team Lead or Manager.")
        entries.append((f"System guide: {labels['en']}", _cap(body, GUIDE_SECTION_LIMIT)))
    return entries


# ---------------------------------------------------------------------------
# What is in the system
# ---------------------------------------------------------------------------
def _stats_entry(articles):
    counts = {}
    for article in articles:
        category = str(article.get("category") or "Uncategorised")
        counts[category] = counts.get(category, 0) + 1
    by_category = ", ".join(f"{name}: {count}" for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    body = (f"There are {len(articles)} articles in the Knowledge Base (not counting the Retrieve Bin). "
            f"Articles per category: {by_category}. Categories: {', '.join(sorted(counts))}.")
    return "Knowledge Base statistics", _cap(body, STATS_LIMIT)


def _documents_entry(question, articles, documents):
    titles = {article.get("article_id"): article.get("title") or "Untitled" for article in articles}
    files = []
    for article_id, entry in (documents or {}).items():
        if article_id not in titles:
            continue  # article is in the Retrieve Bin
        for file in entry.get("files") or []:
            files.append((titles[article_id], file))
    if not files:
        return "Attached documents", "There are no PDF or Word documents attached to Knowledge Base articles yet."

    question_words = _words(question)

    def relevance(item):
        title, file = item
        return len(question_words & (_words(file.get("name")) | _words(title) | _words(file.get("summary"))))

    ranked = sorted(files, key=lambda item: (-relevance(item), item[1].get("name") or ""))
    lines = [f"There are {len(files)} attached documents (PDF / Word) in the Knowledge Base:"]
    used = len(lines[0])
    for index, (title, file) in enumerate(ranked):
        if index < 5:
            if file.get("status") != "ok":
                detail = "no readable text (scanned or image-only)"
            else:
                detail = file.get("summary") or "summary not ready yet"
            line = f'- {file.get("name")} (attached to "{title}"): {detail}'
        else:
            line = f'- {file.get("name")} (attached to "{title}")'
        remaining = len(ranked) - index
        tail = f"\n…and {remaining} more."
        if used + 1 + len(line) + len(tail) > DOCUMENTS_LIMIT:
            lines.append(tail.strip())
            break
        lines.append(line)
        used += 1 + len(line)
    return "Attached documents", "\n".join(lines)


def _active_quizzes(cursor):
    cursor.execute("""
        SELECT q.quiz_id, q.title, q.category, q.difficulty, q.passing_score,
               COUNT(qq.question_id) AS question_count
        FROM quiz q LEFT JOIN quiz_question qq ON qq.quiz_id = q.quiz_id
        WHERE q.status = 'active'
        GROUP BY q.quiz_id, q.title, q.category, q.difficulty, q.passing_score
        ORDER BY q.title
    """)
    return list(cursor.fetchall() or [])


def _quiz_entry(quizzes):
    lines = [f"There are {len(quizzes)} active quizzes (in Quiz / Training):"]
    for quiz in quizzes:
        lines.append(f"- {quiz.get('title')} ({quiz.get('category') or 'no category'}, {quiz.get('difficulty') or 'Medium'}, "
                     f"{int(quiz.get('question_count') or 0)} questions, pass mark {int(quiz.get('passing_score') or 80)}%)")
    return "Quizzes", _cap("\n".join(lines), QUIZ_LIMIT)


def _my_quiz_entry(cursor, quizzes, user_id):
    cursor.execute("""
        SELECT quiz_id, percentage, completed_at FROM quiz_result
        WHERE user_id = %s ORDER BY completed_at
    """, (user_id,))
    attempts = {}
    for row in cursor.fetchall() or []:
        attempts.setdefault(row["quiz_id"], []).append(row)

    lines = ["The person asking has these quiz results (their own only):"]
    not_done = []
    for quiz in quizzes:
        rows = attempts.get(quiz["quiz_id"])
        if not rows:
            not_done.append(quiz.get("title"))
            continue
        latest = rows[-1]
        percentage = float(latest.get("percentage") or 0)
        pass_mark = int(quiz.get("passing_score") or 80)
        when = latest.get("completed_at")
        when_text = when.strftime("%Y-%m-%d") if hasattr(when, "strftime") else str(when or "")
        lines.append(f"- {quiz.get('title')}: latest score {percentage:g}% on {when_text} "
                     f"({'passed' if percentage >= pass_mark else 'not passed'}; pass mark {pass_mark}%), "
                     f"{len(rows)} attempt{'s' if len(rows) != 1 else ''}")
    if len(lines) == 1:
        lines.append("- No quiz attempted yet.")
    lines.append("Not attempted yet: " + (", ".join(not_done) if not_done else "none"))
    return "Your quiz progress", _cap("\n".join(lines), MY_QUIZ_LIMIT)


def context_entries(cursor, question, articles, documents, user_id=None, role=None):
    """[(title, body)] to add to the AI context for this question (may be empty)."""
    text = str(question or "")
    entries = []
    wants_list = bool(_COUNT_OR_LIST.search(text))

    if wants_list and _ARTICLE.search(text):
        entries.append(_stats_entry(articles))

    if _DOCUMENT.search(text):
        entries.append(_documents_entry(text, articles, documents))

    if _QUIZ.search(text) and (wants_list or _MINE.search(text)):
        try:
            quizzes = _active_quizzes(cursor)
            if wants_list:
                entries.append(_quiz_entry(quizzes))
            if user_id and _MINE.search(text):
                entries.append(_my_quiz_entry(cursor, quizzes, user_id))
        except Exception:
            pass

    entries.extend(_guide_entries(text, role))
    return entries
