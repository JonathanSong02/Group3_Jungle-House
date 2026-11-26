"""AI quiz written in small batches at the same time (2026-11-26).

The quiz used to be one long AI call (all questions at once, up to 90 s, and a
second 90 s call when the JSON was bad); when the AI failed, stiff template
questions were used instead. Now:
  * the quiz is split into batches of about BATCH_SIZE questions (at most
    MAX_BATCHES), all written by the configured AI at the same time, so the
    wait is about that of one small batch;
  * each batch reads different articles (a whole category) or a different
    part of one long article, and reads much more of each article than the
    old 500-character cut, so questions go deeper and repeat less;
  * a failed batch is retried once on its own; nothing ever falls back to a
    template. The same question written twice (ignoring case, spaces and
    punctuation) is kept once; questions that differ in any word are kept,
    because one store name or number can make a different question.
Pure helpers; app.py does the database and AI calls.
"""

import math
import re
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor

BATCH_SIZE = 5
MAX_BATCHES = 4
BATCH_TIMEOUT_SECONDS = 60
CHARS_PER_BATCH = 14000
CHARS_PER_ARTICLE = 1500
SINGLE_ARTICLE_MAX_CHARS = 24000
MIN_PART_CHARS = 1500

_SENTENCE_END = re.compile(r"(?<=[.!?。！？])\s+")
_NOT_WORD = re.compile(r"[^0-9a-z一-鿿]+")

BatchResult = namedtuple("BatchResult", "questions failures")


def batch_sizes(question_count):
    count = max(1, int(question_count))
    batches = min(MAX_BATCHES, math.ceil(count / BATCH_SIZE))
    base, extra = divmod(count, batches)
    return [base + 1] * extra + [base] * (batches - extra)


def share_out(items, groups):
    """Deal items out in turn; with fewer items than groups, every group gets all of them."""
    if len(items) < groups:
        return [list(items) for _ in range(groups)]
    return [list(items[start::groups]) for start in range(groups)]


def source_text(articles, max_chars=CHARS_PER_BATCH, per_article=CHARS_PER_ARTICLE):
    """'### title\\nbody' blocks, each body cut at per_article, the whole text at max_chars."""
    blocks, total = [], 0
    for title, body in articles:
        body = str(body or "")
        if len(body) > per_article:
            body = body[:per_article].rstrip() + "..."
        block = f"### {title}\n{body}\n"
        if blocks and total + len(block) + 1 > max_chars:
            break
        if not blocks and len(block) > max_chars:
            block = block[:max_chars]
        blocks.append(block)
        total += len(block) + 1
    return "\n".join(blocks)


def article_parts(body, parts):
    """One long article cut into `parts` pieces of whole sentences, in order; a short one is not cut."""
    body = str(body or "")
    if parts <= 1 or len(body) < MIN_PART_CHARS * parts:
        return [body] * max(1, parts)
    sentences = _SENTENCE_END.split(body)
    target = len(body) / parts
    pieces, current = [], []
    size = 0
    for sentence in sentences:
        current.append(sentence)
        size += len(sentence) + 1
        if size >= target * (len(pieces) + 1) and len(pieces) < parts - 1:
            pieces.append(" ".join(current))
            current = []
    pieces.append(" ".join(current))
    while len(pieces) < parts:
        pieces.append(pieces[-1])
    return pieces


def _key(text):
    return _NOT_WORD.sub("", str(text or "").lower())


def dedupe(questions):
    kept, keys = [], set()
    for item in questions:
        key = _key(item.get("question"))
        if not key or key in keys:
            continue
        kept.append(item)
        keys.add(key)
    return kept


def run_batches(jobs, write_batch, stop_on=()):
    """Run write_batch(job) for every job at the same time; each failed job is tried once more.

    write_batch gets the job plus "retry" (False, then True) and returns a list
    of questions. An exception listed in stop_on (e.g. "AI not set up") is
    raised at once. Returns BatchResult(questions in job order, failures).
    """
    def attempt(job):
        last_error = None
        for retry in (False, True):
            try:
                questions = write_batch({**job, "retry": retry})
                if questions:
                    return questions, None
                last_error = ValueError("AI returned zero valid questions.")
            except stop_on:
                raise
            except Exception as error:  # noqa: BLE001 -- any provider / format failure retries once
                last_error = error
        return [], last_error

    if not jobs:
        return BatchResult([], [])
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        outcomes = [future.result() for future in [pool.submit(attempt, job) for job in jobs]]
    questions = [item for found, _ in outcomes for item in found]
    failures = [error for _, error in outcomes if error is not None]
    return BatchResult(questions, failures)
