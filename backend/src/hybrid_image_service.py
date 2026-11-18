"""Image observations are search hints. Only current published KB text is policy."""
import json
import re
import time
from html.parser import HTMLParser

import chat_attachment_service as attachments
import image_index_service as index
from db_helper import get_db_connection
from image_embedding_helper import decode_image


def language(question):
    if re.search(r"[\u3400-\u9fff]", question):
        return "zh"
    return "ms" if re.search(r"\b(mana|simpan|letak|bagaimana|boleh|gambar|ini|itu|apa)\b", question, re.I) else "en"


MESSAGES = {
    "clarify": {
        "en": "What would you like to know about this image?",
        "zh": "你想了解这张图片的什么内容？",
        "ms": "Apakah yang anda ingin tahu tentang gambar ini?",
    },
    "ambiguous": {
        "en": "Which image do you mean? Please attach the intended image with your question.",
        "zh": "你指的是哪张图片？请将对应图片和问题一起发送。",
        "ms": "Gambar yang manakah anda maksudkan? Sila lampirkan gambar itu bersama soalan anda.",
    },
    "unknown": {
        "en": "I could not verify an applicable Knowledge Base instruction for this image. Please name the object or clarify your question; a team lead can help if no guide applies.",
        "zh": "我无法从知识库核实适用于这张图片的指引。请说明物品名称或具体问题；若没有相关指引，可请组长协助。",
        "ms": "Saya tidak dapat mengesahkan panduan Pangkalan Pengetahuan untuk gambar ini. Sila nyatakan objek atau jelaskan soalan; ketua pasukan boleh membantu jika tiada panduan.",
    },
}


def control(kind, question, references, language_hint=None):
    selected = language_hint if not question.strip() and language_hint in {"en", "zh", "ms"} else language(question)
    text = MESSAGES[kind][selected]
    return {"type": "text", "answer": text, "reply": text, "source": "image_only_clarification" if kind == "clarify" else f"image_{kind}",
            "confidence": 0.0, "score": 0.0, "confidence_kind": "not_calibrated",
            "answer_evidence": "not_established", "attachment_refs": references,
            "fallback": False, "escalation_ready": False, "escalation_required": False}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1
        if tag in {"p", "li", "br", "div", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.skip = max(0, self.skip - 1)
        if tag in {"p", "li", "div", "tr"}:
            self.parts.append("\n")

    def handle_data(self, value):
        if not self.skip:
            self.parts.append(value)


def plain(value):
    parser = _Text()
    parser.feed(str(value or ""))
    return "".join(parser.parts)


def question_subjects(question):
    stop = set("where should would could can do does did i we you my our it its this that these those put keep store place how what when is are to the a an of in on at for with please image photo picture know about explain me tell show use using opening closing open close steps step".split())
    return {word.rstrip("s") for word in re.findall(r"[a-z]{3,}", question.lower()) if word not in stop}


def extract_evidence(question, article):
    """Conservative extractive shortcut. Ambiguity/missing action evidence never becomes an answer."""
    if language(question) != "en":
        return None  # Multilingual answers use the existing grounded provider fallback.
    body = plain(article.get("content"))
    subjects = question_subjects(question)
    location = bool(re.search(r"\b(where|put|keep|store|place)\b", question, re.I))
    action = bool(re.search(r"\b(how|opening|closing|open|close|clean|use)\b", question, re.I))
    if not location and not action:
        return None
    matches = []
    for sentence in re.split(r"\n+|(?<=[.!?])\s+", body):
        sentence = sentence.strip()
        words = {word.rstrip("s") for word in re.findall(r"[a-z]{3,}", sentence.lower())}
        if not sentence or (subjects and not subjects.issubset(words)):
            continue
        if location and not re.search(r"\b(put|keep|store|place|located|area|inside|under|shelf|cabinet)\b", sentence, re.I):
            continue
        if action and not subjects:
            continue
        matches.append(sentence)
    matches = list(dict.fromkeys(matches))
    if len(matches) == 1:
        return matches[0]
    # A usage guide can contain several relevant steps in the same article.
    # Multiple storage locations still need clarification rather than guessing.
    if matches and action and not location:
        return "\n".join(matches)
    return None


def text_articles(query):
    """No default arbitrary articles: require object/question token evidence."""
    subjects = question_subjects(query)
    if not subjects:
        return []
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM wiki_article WHERE COALESCE(is_deleted, 0) = 0")
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    ranked = []
    for row in rows:
        words = {word.rstrip("s") for word in re.findall(r"[a-z]{3,}", plain(str(row.get("title")) + " " + str(row.get("content"))).lower())}
        overlap = len(subjects & words) / len(subjects)
        if index.published(row) and overlap >= 0.72:
            ranked.append({**row, "retrieval_relevance": overlap})
    return sorted(ranked, key=lambda row: row["retrieval_relevance"], reverse=True)[:5]


def grounded_result(question, articles, references):
    matches = [(article, extract_evidence(question, article)) for article in articles]
    matches = [(article, quote) for article, quote in matches if quote]
    if len(matches) != 1:
        return None
    article, quote = matches[0]
    return {"type": "text", "question": question, "answer": quote, "reply": quote,
            "title": article["title"], "article_id": article["article_id"],
            "source": "image_approved_review_evidence" if article.get("approved_review_id") else "image_kb_evidence", "confidence_kind": "not_calibrated",
            "confidence": 0.0, "score": 0.0, "answer_evidence": "current_kb_quote",
            "evidence_quote": quote, "image_similarity": article.get("image_similarity"),
            "approved_review_id": article.get("approved_review_id"),
            "retrieval_relevance": article.get("retrieval_relevance"),
            "context": {"title": article["title"], "article_id": article["article_id"]},
            "attachment_refs": references, "fallback": False,
            "escalation_ready": False, "escalation_required": False}


def verify_text_result(question, query, result, references):
    article_id = result.get("article_id")
    if not article_id:
        return None
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM wiki_article WHERE article_id = %s", (article_id,))
        article = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()
    if not index.published(article):
        return None
    verified = grounded_result(query, [article], references)
    if verified:
        verified["question"] = question
    return verified


def process(owner, chat, question, folder, references, *, new_path=None, mime=None,
            analyze=None, cancelled=lambda: False, vision_identity=None, language_hint=None, stage=lambda value: None):
    """Return (response or None, search hint, refs). Text chat is not routed here."""
    if new_path is not None:
        stage("decode")
        try:
            decode_image(new_path)
        except Exception:
            raise attachments.AttachmentError("This image could not be decoded safely. Please use a valid PNG, JPEG or WebP image.") from None
        stage("attachment_register")
        reference = attachments.register_attachment(owner, chat, new_path, mime)
        references = [reference]
    if not isinstance(references, list) or not 1 <= len(references) <= 4:
        raise attachments.AttachmentError("Invalid attachment selection.")
    references = list(dict.fromkeys(references))
    # Validate every reference before responding, including ambiguous selections.
    stage("attachment_load")
    records = [attachments.load_attachment(owner, chat, ref, folder) for ref in references]
    if any(not row["mime_type"].startswith("image/") for row in records):
        raise attachments.AttachmentError("Please select an image for visual questions.")
    if not question.strip():
        return control("clarify", question, references, language_hint), question, references
    if len(records) != 1:
        return control("ambiguous", question, references), question, references
    if cancelled():
        return control("unknown", question, references), question, references
    record = records[0]
    stage("visual_retrieval")
    candidates = index.visual_candidates(record["path"])
    articles = index.current_articles(candidates)
    # Article-level ambiguity gap. A weak photo cannot make an authoritative match.
    clear = bool(articles and articles[0]["image_similarity"] >= 0.78 and
                 (len(articles) == 1 or articles[0]["image_similarity"] - articles[1]["image_similarity"] >= 0.04))
    article_request = bool(re.fullmatch(
        r"(?:please\s+)?(?:show|find|give)(?:\s+me)?\s+(?:(?:the|a|relevant|related|matching)\s+)*"
        r"articles?(?:\s+for\s+(?:this|the)\s+(?:image|photo|picture))?[.!?]*",
        question.strip(), re.I))
    if clear and articles[0].get("exact_image") and articles[0].get("article_id") and article_request:
        article = articles[0]
        return {"type": "text", "answer": article["title"], "reply": article["title"],
                "title": article["title"], "article_id": article["article_id"],
                "source": "image_article_match", "answer_evidence": "current_kb",
                "confidence_kind": "not_calibrated", "confidence": 0.0, "score": 0.0,
                "image_similarity": article["image_similarity"], "attachment_refs": references,
                "context": {"title": article["title"], "article_id": article["article_id"]},
                "fallback": False, "escalation_ready": False, "escalation_required": False}, question, references
    result = grounded_result(question, articles[:1], references) if clear else None
    if result:
        return result, question, references
    # An explicit named-object question can already be answerable without Vision.
    stage("kb_evidence")
    result = grounded_result(question, text_articles(question), references)
    if result:
        return result, question, references
    needs_visual = not question_subjects(question) or bool(re.search(
        r"\b(it|its|this|that|image|photo|picture|identify|recognize|recognise|object|ini|itu|dia|gambar)\b|它|这个|這個|这张|這張|识别|識別",
        question, re.I))
    if not needs_visual:
        # An independent named text topic should not spend Vision tokens merely
        # because the employee also attached a photo.
        return None, question, references
    observations = record.get("observations")
    try:
        identity = vision_identity() if vision_identity else None
    except Exception:
        identity = None
    if observations and observations.get("vision_identity") != identity:
        observations = None
    if observations and observations.get("retry_after", float("inf")) < time.time():
        observations = None
    if observations is None and analyze and not cancelled():
        stage("vision")
        observations = analyze(record["path"], record["image_hash"])
        if observations is None:
            observations = {"retry_after": time.time() + 600, "unavailable": True}
        observations["vision_identity"] = identity
        attachments.save_observations(owner, chat, references[0], observations)
    terms = " ".join((observations or {}).get("detectedObjects", []) + (observations or {}).get("possibleAliases", []))
    # Work-related classification is an observation, never a veto on KB evidence.
    query = f"{question} {terms}".strip()
    if terms:
        stage("kb_evidence")
        result = grounded_result(query, text_articles(query), references)
        if result:
            result["question"] = question
            return result, query, references
    if not terms and not clear and not question_subjects(question):
        return control("unknown", question, references), question, references
    # Existing text retrieval / grounded provider / escalation handles unresolved questions.
    # Only current article titles and observed object words are search hints, never policy.
    if clear:
        query += " " + articles[0]["title"]
    return None, query, references
