"""Retrieval accuracy check on the LIVE articles (AI Model Settings page).

For each article, a few of its own sentences are turned into short questions
the way staff type them (its rarest words plus one word of the title). Each
question goes through the real chat search (build_ai_chat_context), and we
check whether that sentence actually reaches the text the AI reads. No AI is
called, so it costs nothing; it only reads the database once.

When search picks another article that says the same thing (most of the
sentence's words close together), it counts as found ("foundElsewhere"):
the same step is often written in several articles. The report also lists
duplicate articles (same title, or same text under different titles).

A miss is labelled:
  wrong_article -- search did not pick the article at all;
  line_cut      -- the article was picked but the sentence did not fit.

Runs in one background thread; the result lives in memory (one server
worker), so a restart simply clears it.
"""

import re
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

QUESTIONS_PER_ARTICLE = 3
MAX_QUESTIONS = 1500
MAX_MISSES_SHOWN = 200
SNIPPET_CHARS = 60
NEAR_DUPLICATE = 0.7
SAME_INFO_SHARE = 60  # percent of the sentence's words, close together

_STOP = set("""a an the and or of to in on at for with by from is are be it this that these those you your
we our they their them as if then than so not no do does did can will should must have has had into out
up down over under all any each every some more most other such only own same too very just also there
here when where what which who how why after before during while again once both few near next first last
per via""".split())
_BLOCK_TAGS = re.compile(r"</?(?:p|div|li|ul|ol|h[1-6]|tr|td|th|table|br|blockquote|pre)\b[^>]*>", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?。！？])\s+")


def words(text):
    return [w for w in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(w) > 2 and w not in _STOP]


def _clean(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def article_sentences(article):
    """The article's sentences as plain text, in order (same text the chat search sees)."""
    sentences = []
    for block in _BLOCK_TAGS.split(str(article.get("content") or "")):
        for sentence in _SENTENCE_END.split(_clean(block)):
            if sentence:
                sentences.append(sentence)
    return sentences


def snippet(sentence):
    return re.sub(r"\s+", " ", sentence).strip()[:SNIPPET_CHARS].lower()


def make_questions(articles, per_article=QUESTIONS_PER_ARTICLE, max_questions=MAX_QUESTIONS):
    """Returns (questions, all_sentences).

    questions: [{article_id, title, question, sentence}]; all_sentences:
    [(sentence, word_set)] of every article, for the near-duplicate rule.
    """
    per_article_sentences = []
    all_sentences = []
    doc_freq = Counter()
    for article in articles:
        items = []
        for sentence in article_sentences(article):
            sentence_words = set(words(sentence))
            all_sentences.append((sentence, sentence_words))
            doc_freq.update(sentence_words)
            if len(sentence_words) >= 4 and len(sentence) >= 25:
                items.append((sentence, sentence_words))
        per_article_sentences.append((article, items))

    questions = []
    for article, items in per_article_sentences:
        if not items:
            continue
        # Spread over the article: start, middle, end.
        count = min(per_article, len(items))
        picks = sorted({round(i * (len(items) - 1) / max(count - 1, 1)) for i in range(count)})
        title_words = words(article.get("title"))
        for position, index in enumerate(picks):
            sentence, sentence_words = items[index]
            keywords = sorted(sentence_words, key=lambda w: (doc_freq[w], w))[:4]
            # Staff often leave the topic out, so the middle question has no title word.
            title_word = "" if position == 1 else next((w for w in title_words if w not in keywords), "")
            questions.append({
                "article_id": article.get("article_id"),
                "title": article.get("title") or "",
                "question": " ".join(keywords + ([title_word] if title_word else [])),
                "sentence": sentence,
            })

    if len(questions) > max_questions:
        step = len(questions) / max_questions
        questions = [questions[int(i * step)] for i in range(max_questions)]
    return questions, all_sentences


class _NearDuplicates:
    """Finds the same step written in other articles (e.g. "Clock out using TimeTec")."""

    def __init__(self, all_sentences):
        self.sentences = all_sentences
        self.by_word = defaultdict(list)
        for index, (_, sentence_words) in enumerate(all_sentences):
            for word in sentence_words:
                self.by_word[word].append(index)

    def visible(self, sentence, context):
        context = context.lower()
        if snippet(sentence) in context:
            return True
        mine = set(words(sentence))
        if not mine:
            return False
        rarest = min(mine, key=lambda w: len(self.by_word.get(w, ())))
        for index in self.by_word.get(rarest, ()):
            other, other_words = self.sentences[index]
            if other != sentence and len(mine & other_words) / len(mine | other_words) >= NEAR_DUPLICATE \
                    and snippet(other) in context:
                return True
        return False


def _stem(word):
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def same_info_in(sentence, context):
    """True when one short stretch of the context says the same thing in
    other words, e.g. "Click Shopify app and start the session for iPad." vs
    "Open the Shopify POS app on the iPad and start a session." (another
    article). At least 60% of the sentence's words, and at least 3, must
    appear close together -- the whole context together does not count.
    """
    mine = {_stem(w) for w in words(sentence)}
    if len(mine) < 3:
        return False
    sequence = [_stem(w) for w in words(context)]
    window = max(8, 2 * len(mine))
    needed = max(3, -(-len(mine) * SAME_INFO_SHARE // 100))
    for start in range(0, max(len(sequence) - window, 0) + 1):
        if len(mine.intersection(sequence[start:start + window])) >= needed:
            return True
    return False


def duplicate_articles(articles):
    """Groups of live articles with the same title, or the same text under different titles."""
    def normal(text):
        return re.sub(r"\s+", " ", str(text or "")).strip().casefold()

    groups = []
    by_title = defaultdict(list)
    for article in articles:
        by_title[normal(article.get("title"))].append(article)
    for group in by_title.values():
        if len(group) > 1:
            groups.append(("same_title", group))
    by_content = defaultdict(list)
    for article in articles:
        content = normal(_clean(str(article.get("content") or "")))
        if len(content) >= 50:
            by_content[content].append(article)
    for group in by_content.values():
        if len({normal(a.get("title")) for a in group}) > 1:
            groups.append(("same_content", group))
    return [{
        "reason": reason,
        "titles": sorted({a.get("title") or "" for a in group}),
        "articles": [{"article_id": a.get("article_id"), "title": a.get("title") or "",
                      "category": a.get("category") or ""} for a in group],
    } for reason, group in groups]



# ------------------------------------------------- "other words" questions
# One AI-written question per article, in staff wording with different words
# than the article (e.g. "make ice" for "ice machine"), plus the sentence that
# answers it. Written once and stored; re-written when the article changes.

QUESTION_BATCH = 8
QUESTION_TEXT_CHARS = 1500
QUESTION_WORKERS = 3


def ensure_question_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS retrieval_audit_question (
            audit_question_id INT NOT NULL AUTO_INCREMENT,
            article_id INT NOT NULL,
            content_hash CHAR(64) NOT NULL,
            question VARCHAR(500) NOT NULL,
            quote TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (audit_question_id),
            UNIQUE KEY uq_retrieval_audit_question_article (article_id),
            CONSTRAINT fk_retrieval_audit_question_article FOREIGN KEY (article_id)
                REFERENCES wiki_article (article_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def article_hash(article):
    import hashlib
    text = f"{article.get('title') or ''}\x1f{article.get('content') or ''}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _plain(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def question_prompt(batch):
    parts = []
    for article in batch:
        text = _clean(str(article.get("content") or ""))[:QUESTION_TEXT_CHARS]
        parts.append(f"### id={article.get('article_id')} | title: {article.get('title') or ''}\n{text}")
    return (
        "You write test questions for the search of a retail staff help desk.\n"
        "For EACH article below, write ONE question a shop staff member might type to find one specific fact "
        "in it: short and casual, the way staff really type, using DIFFERENT words from the article where "
        "natural (synonyms, everyday words) and NOT the article title. Then copy, word for word, the one "
        "sentence (or line) from the article text that answers it.\n"
        'Return ONLY a JSON array, no other text: [{"id": <article id>, "question": "...", "quote": "..."}]. '
        "Leave out an article that has no clear fact.\n\n" + "\n\n".join(parts)
    )


def parse_questions(reply, batch):
    """Valid items only: a known id, a question, and a quote really in that article."""
    import json
    match = re.search(r"\[.*\]", str(reply or ""), re.DOTALL)
    if not match:
        return []
    try:
        items = json.loads(match.group(0), strict=False)
    except ValueError:
        return []
    by_id = {str(article.get("article_id")): article for article in batch}
    found = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        article = by_id.get(str(item.get("id")))
        question = re.sub(r"\s+", " ", str(item.get("question") or "")).strip()[:300]
        quote = re.sub(r"\s+", " ", str(item.get("quote") or "")).strip()
        if not article or not question or len(quote) < 15:
            continue
        if _plain(quote) not in _plain(_clean(str(article.get("content") or ""))):
            continue  # the AI changed the sentence: we could not check it
        found.append({"article_id": article.get("article_id"), "question": question, "quote": quote,
                      "content_hash": article_hash(article)})
        by_id.pop(str(item.get("id")))
    return found


def write_questions(articles, ask_ai, progress=None, workers=QUESTION_WORKERS):
    """AI-written questions for `articles` (in batches, a few at a time)."""
    from concurrent.futures import ThreadPoolExecutor
    batches = [articles[i:i + QUESTION_BATCH] for i in range(0, len(articles), QUESTION_BATCH)]
    done = [0]
    lock = threading.Lock()

    def one(batch):
        try:
            result = parse_questions(ask_ai(question_prompt(batch)), batch)
        except Exception as error:
            print("RETRIEVAL AUDIT QUESTION ERROR:", type(error).__name__)
            result = []
        with lock:
            done[0] += 1
            if progress:
                progress(done[0], len(batches))
        return result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return [item for items in pool.map(one, batches) for item in items]


def other_word_questions(cursor, commit, articles, ask_ai, progress=None):
    """Stored questions for unchanged articles; new ones written for the rest.

    Returns [{article_id, title, question, sentence}] for the check.
    """
    ensure_question_table(cursor)
    cursor.execute("SELECT article_id, content_hash, question, quote FROM retrieval_audit_question")
    stored = {row["article_id"]: row for row in cursor.fetchall() or []}
    needing = [article for article in articles
               if len(_clean(str(article.get("content") or ""))) >= 80
               and (stored.get(article["article_id"]) or {}).get("content_hash") != article_hash(article)]
    if needing and ask_ai:
        for item in write_questions(needing, ask_ai, progress):
            cursor.execute("""
                INSERT INTO retrieval_audit_question (article_id, content_hash, question, quote, created_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE content_hash = VALUES(content_hash), question = VALUES(question),
                    quote = VALUES(quote), created_at = VALUES(created_at)
            """, (item["article_id"], item["content_hash"], item["question"], item["quote"]))
            stored[item["article_id"]] = item
        commit()
    titles = {article["article_id"]: article.get("title") or "" for article in articles}
    hashes = {article["article_id"]: article_hash(article) for article in articles}
    return [{"article_id": article_id, "title": titles[article_id], "question": row["question"],
             "sentence": row["quote"]}
            for article_id, row in stored.items()
            if article_id in titles and row.get("content_hash") == hashes[article_id]]


# ------------------------------------------------------------------ the run

def _check(items, duplicates, ask):
    """(passed, found_elsewhere, misses) for one set of questions in one search mode."""
    passed = found_elsewhere = 0
    misses = []
    for item in items:
        context, candidates = ask(item["question"])
        if duplicates.visible(item["sentence"], context):
            passed += 1
        elif same_info_in(item["sentence"], context):
            # Search picked another article that says the same thing.
            passed += 1
            found_elsewhere += 1
        else:
            chosen_ids = [c.get("article_id") for c in candidates]
            misses.append({
                "question": item["question"],
                "article_id": item["article_id"],
                "article_title": item["title"],
                "expected": item["sentence"][:200],
                "cause": "line_cut" if item["article_id"] in chosen_ids else "wrong_article",
                "picked": [c.get("title") for c in candidates[:3]],
            })
    return passed, found_elsewhere, misses


def _rate(passed, total):
    return round(passed / total, 4) if total else None


def run_audit(articles, documents, build_context, progress=None, other_words=(), meaning=False):
    """Ask every question; returns the report dict.

    `build_context(question, preloaded, meaning)` -> (context_text, candidate_articles).
    Own-words questions come from the articles' sentences; `other_words` are
    the AI-written ones. With `meaning` (meaning search available) every set
    is asked twice -- words only, then words + meaning -- to compare; the main
    score and the misses are for what the chat really uses.
    """
    started = time.monotonic()
    own, all_sentences = make_questions(articles)
    for item in own:
        item["set"] = "own"
    other = [dict(item, set="other") for item in other_words]
    duplicates = _NearDuplicates(all_sentences)
    preloaded = (articles, documents)
    modes = [False, True] if meaning else [False]
    total_steps = (len(own) + len(other)) * len(modes)
    done = [0]

    def asker(mode):
        def ask(question):
            result = build_context(question, preloaded, mode)
            done[0] += 1
            if progress:
                progress(done[0], total_steps)
            return result
        return ask

    comparison = {}
    final = None
    for mode in modes:
        results = {name: _check(items, duplicates, asker(mode)) for name, items in (("own", own), ("other", other))}
        for name, items in (("own", own), ("other", other)):
            comparison.setdefault(name, {"total": len(items)})["meaning" if mode else "words"] = \
                _rate(results[name][0], len(items))
        final = results  # the last mode is what the chat uses
    for name, (_, _, misses) in final.items():
        for miss in misses:
            miss["set"] = name

    passed = sum(result[0] for result in final.values())
    misses = final["own"][2] + final["other"][2]
    total = len(own) + len(other)
    return {
        "articleCount": len(articles),
        "total": total,
        "passed": passed,
        "rate": _rate(passed, total),
        "foundElsewhere": sum(result[1] for result in final.values()),
        "meaning": bool(meaning),
        "meaningArticles": meaning if isinstance(meaning, int) and not isinstance(meaning, bool) else None,
        "comparison": comparison,
        "duplicates": duplicate_articles(articles),
        "wrongArticle": sum(1 for m in misses if m["cause"] == "wrong_article"),
        "lineCut": sum(1 for m in misses if m["cause"] == "line_cut"),
        "misses": (final["other"][2] + final["own"][2])[:MAX_MISSES_SHOWN],
        "durationSeconds": round(time.monotonic() - started, 1),
        "finishedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


_state = {"status": "idle", "phase": None, "done": 0, "total": 0, "result": None, "error": None, "startedAt": None}
_lock = threading.Lock()


def status():
    with _lock:
        return dict(_state)


def start(load_data, build_context, prepare=None):
    """Start the check in a background thread. False if one is already running.

    `prepare(articles, progress)` (optional) -> (other_words_questions, meaning_available).
    """
    with _lock:
        if _state["status"] == "running":
            return False
        _state.update(status="running", phase="reading", done=0, total=0, error=None,
                      startedAt=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def progress_for(phase):
        def progress(done, total):
            with _lock:
                _state.update(phase=phase, done=done, total=total)
        return progress

    def work():
        try:
            articles, documents = load_data()
            other, meaning = prepare(articles, progress_for("questions")) if prepare else ((), False)
            result = run_audit(articles, documents, build_context, progress_for("checking"),
                               other_words=other, meaning=meaning)
            with _lock:
                _state.update(status="done", phase=None, result=result)
        except Exception as error:
            print("RETRIEVAL AUDIT ERROR:", type(error).__name__, error)
            with _lock:
                _state.update(status="failed", phase=None, error="The check could not finish. Please try again.")

    threading.Thread(target=work, name="retrieval-audit", daemon=True).start()
    return True
