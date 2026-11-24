"""Retrieval accuracy check on the LIVE articles (AI Model Settings page).

For each article, a few of its own sentences are turned into short questions
the way staff type them (its rarest words plus one word of the title). Each
question goes through the real chat search (build_ai_chat_context), and we
check whether that sentence actually reaches the text the AI reads. No AI is
called, so it costs nothing; it only reads the database once.

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


def run_audit(articles, documents, build_context, progress=None):
    """Ask every generated question; returns the report dict.

    `build_context(question, preloaded)` -> (context_text, candidate_articles).
    """
    started = time.monotonic()
    questions, all_sentences = make_questions(articles)
    duplicates = _NearDuplicates(all_sentences)
    preloaded = (articles, documents)
    passed = 0
    misses = []
    for done, item in enumerate(questions, 1):
        context, candidates = build_context(item["question"], preloaded)
        if duplicates.visible(item["sentence"], context):
            passed += 1
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
        if progress:
            progress(done, len(questions))

    total = len(questions)
    return {
        "articleCount": len(articles),
        "total": total,
        "passed": passed,
        "rate": round(passed / total, 4) if total else None,
        "wrongArticle": sum(1 for m in misses if m["cause"] == "wrong_article"),
        "lineCut": sum(1 for m in misses if m["cause"] == "line_cut"),
        "misses": misses[:MAX_MISSES_SHOWN],
        "durationSeconds": round(time.monotonic() - started, 1),
        "finishedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


_state = {"status": "idle", "done": 0, "total": 0, "result": None, "error": None, "startedAt": None}
_lock = threading.Lock()


def status():
    with _lock:
        return dict(_state)


def start(load_data, build_context):
    """Start the check in a background thread. False if one is already running."""
    with _lock:
        if _state["status"] == "running":
            return False
        _state.update(status="running", done=0, total=0, error=None,
                      startedAt=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def progress(done, total):
        with _lock:
            _state["done"], _state["total"] = done, total

    def work():
        try:
            articles, documents = load_data()
            result = run_audit(articles, documents, build_context, progress)
            with _lock:
                _state.update(status="done", result=result)
        except Exception as error:
            print("RETRIEVAL AUDIT ERROR:", type(error).__name__, error)
            with _lock:
                _state.update(status="failed", error="The check could not finish. Please try again.")

    threading.Thread(target=work, name="retrieval-audit", daemon=True).start()
    return True
