
from pathlib import Path
import re
from typing import Optional

import pandas as pd
import torch
from torch import nn

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
MODEL_DIR = BASE_DIR.parent / "models"

KNOWLEDGE_FILE = DATA_DIR / "cleaned_knowledge.csv"
MODEL_FILE = MODEL_DIR / "intent_model.pth"

CONFIDENCE_THRESHOLD = 0.45
MID_CONFIDENCE_THRESHOLD = 0.60
HIGH_CONFIDENCE_THRESHOLD = 0.78
MIN_LEXICAL_OVERLAP = 2
ESCALATION_MESSAGE = "This question is not related to the SOP system. Please escalate to team lead."
NO_MATCH_MESSAGE = "No confident SOP match. Please escalate to team lead."


def normalize_text(text: str) -> str:
    text = str(text).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_lower(text: str) -> str:
    return normalize_text(text).lower()


def safe_str(value) -> str:
    if pd.isna(value):
        return ""
    return normalize_text(str(value))


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9']+", normalize_lower(text))


def contains_any(text: str, phrases: list[str]) -> bool:
    q = normalize_lower(text)
    return any(normalize_lower(p) in q for p in phrases)


def vectorize(text: str, vocab: dict[str, int]) -> torch.Tensor:
    vec = torch.zeros(len(vocab), dtype=torch.float32)
    for token in tokenize(text):
        vec[vocab.get(token, 0)] += 1.0
    return vec


class IntentClassifier(nn.Module):
    def __init__(self, input_size: int, num_classes: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_size, 128),
            nn.ReLU(),
            nn.Dropout(0.20),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Linear(64, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def load_model_package():
    if not MODEL_FILE.exists():
        return None, {}, [], f"Model file not found: {MODEL_FILE}"

    try:
        package = torch.load(MODEL_FILE, map_location="cpu")
        vocab = package["vocab"]
        labels = package["labels"]

        model = IntentClassifier(
            input_size=package["input_size"],
            num_classes=package["num_classes"],
        )
        model.load_state_dict(package["state_dict"])
        model.eval()
        return model, vocab, labels, None
    except Exception as error:
        return None, {}, [], str(error)


def predict_intent(question: str) -> tuple[Optional[str], float]:
    if MODEL is None or not VOCAB or not LABELS:
        return None, 0.0

    vec = vectorize(question, VOCAB).unsqueeze(0)

    with torch.no_grad():
        logits = MODEL(vec)
        probs = torch.softmax(logits, dim=1)[0]
        pred_idx = int(torch.argmax(probs).item())
        confidence = float(probs[pred_idx].item())

    return LABELS[pred_idx], confidence


def predict_top_k(question: str, top_k: int = 3) -> list[tuple[str, float]]:
    if MODEL is None or not VOCAB or not LABELS:
        return []

    vec = vectorize(question, VOCAB).unsqueeze(0)
    with torch.no_grad():
        logits = MODEL(vec)
        probs = torch.softmax(logits, dim=1)[0]
        values, indices = torch.topk(probs, k=min(top_k, len(LABELS)))

    return [(LABELS[int(index)], float(value)) for value, index in zip(values.tolist(), indices.tolist())]


def load_knowledge() -> pd.DataFrame:
    if not KNOWLEDGE_FILE.exists():
        raise FileNotFoundError(f"Knowledge file not found: {KNOWLEDGE_FILE}")

    df = pd.read_csv(KNOWLEDGE_FILE)

    required = {"title", "content"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"cleaned_knowledge.csv missing columns: {sorted(missing)}")

    df = df.copy()
    for column in ["category", "section", "image_files"]:
        if column not in df.columns:
            df[column] = ""
    if "step_order" not in df.columns:
        df["step_order"] = None

    df["category"] = df["category"].apply(safe_str)
    df["title"] = df["title"].apply(safe_str)
    df["content"] = df["content"].apply(safe_str)
    df["section"] = df["section"].apply(safe_str)
    df["image_files"] = df["image_files"].apply(safe_str)
    df["step_order"] = pd.to_numeric(df["step_order"], errors="coerce")

    df = df[(df["title"] != "") & (df["content"] != "")].reset_index(drop=True)
    return df


def parse_image_files(value: str) -> list[str]:
    text = safe_str(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"[|,;]", text) if part.strip()]


def build_image_url(relative_path: str) -> str:
    path = safe_str(relative_path).replace("\\", "/").strip()
    if not path:
        return ""
    if path.startswith(("http://", "https://")):
        return path
    path = path.lstrip("/")
    if path.startswith("backend/static/"):
        path = path[len("backend/static/"):]
    if path.startswith("static/"):
        path = path[len("static/"):]
    return f"http://127.0.0.1:5000/static/{path}"


def build_steps(df: pd.DataFrame) -> list[dict]:
    rows = df.copy().sort_values(by=["step_order"], na_position="last").reset_index(drop=True)
    steps = []
    display_step = 1

    for _, row in rows.iterrows():
        image_files = parse_image_files(row.get("image_files", ""))
        step_number = row["step_order"]
        if pd.isna(step_number):
            step_number = display_step
        else:
            step_number = int(step_number)

        image_urls = []
        for path in image_files:
            url = build_image_url(path)
            if url:
                image_urls.append(url)

        steps.append({
            "step_number": int(step_number),
            "section": safe_str(row.get("section", "")),
            "content": safe_str(row.get("content", "")),
            "image_files": image_files,
            "image_urls": image_urls,
        })
        display_step += 1

    return steps


def format_sop_answer(title: str, steps: list[dict], section: str = "") -> str:
    header = title if not section else f"{title} - {section}"
    lines = [header]
    current_section = None

    for step in steps:
        step_section = normalize_text(step.get("section", ""))
        if step_section and step_section != current_section:
            lines.append("")
            lines.append(f"[{step_section}]")
            current_section = step_section
        lines.append(f"{step['step_number']}. {step['content']}")

    return "\n".join(lines).strip()


def format_single_step_answer(title: str, step: dict) -> str:
    lines = [title]
    if step.get("section"):
        lines.append(f"Section: {step['section']}")
    lines.append(f"Step {step['step_number']}: {step['content']}")
    return "\n".join(lines).strip()


def build_section_choice_message(title: str, steps: list[dict]) -> str:
    sections = []
    seen = set()

    for step in steps:
        section = normalize_text(step.get("section", ""))
        if section and section.lower() not in seen:
            sections.append(section)
            seen.add(section.lower())

    if sections:
        bullet_lines = "\n".join([f"- {section}" for section in sections])
        return f"I found {title}. Available sections:\n{bullet_lines}"
    return f"I found {title}. Which step do you need?"


def get_df_by_title(title: str) -> pd.DataFrame:
    return KNOWLEDGE_DF[KNOWLEDGE_DF["title"].str.lower() == normalize_lower(title)].copy()


def extract_requested_step_number(question: str) -> Optional[int]:
    q = normalize_lower(question)
    for pattern in [r"\bstep\s*(\d+)\b", r"\bno\.?\s*(\d+)\b", r"\bnumber\s*(\d+)\b"]:
        match = re.search(pattern, q)
        if match:
            return int(match.group(1))
    return None


TITLE_REGISTRY = {}
for _title in sorted(load_knowledge()["title"].dropna().unique().tolist()):
    lowered = normalize_lower(_title)
    TITLE_REGISTRY[_title] = {"aliases": list(dict.fromkeys([
        lowered,
        lowered.replace(" check list", " checklist"),
        lowered.replace(" checklist", ""),
        lowered.replace(" list", ""),
        lowered.replace(" app ", " "),
    ]))}

TITLE_REGISTRY.update({
    "JHKC Kiosk Opening": {"aliases": ["opening sop", "kiosk opening", "jhkc opening", "open kiosk", "how to open kiosk"]},
    "Kiosk Closing Check List": {"aliases": ["kiosk closing", "closing kiosk", "close kiosk", "kiosk closing checklist"]},
    "Price for new packaging for HWJ and SHVP": {"aliases": ["new packaging price", "hwj new packaging price", "shvp new packaging price", "old and new packaging price"]},
    "Customer signature for card payment": {"aliases": ["card payment signature", "merchant copy signature", "need signature for card payment"]},
    "Eating inside the store is strictly prohibited": {"aliases": ["cannot eat inside store", "eat in store prohibited", "store eating rule"]},
    "Emergency Guide – Responding to Danger or Harassment": {"aliases": ["danger or harassment guide", "what to do if danger happens", "what to do if someone harasses me", "help emergency"]},
    "Fake Jungle House": {"aliases": ["jungle house scam", "scam jungle house", "fake account jungle house"]},
    "Bee Points: Redeem Only When Needed": {"aliases": ["redeem bee points", "customer want redeem point", "can redeem points first or not"]},
    "Bee Green 15": {"aliases": ["sales tactic bee green 15", "when to use bee green 15", "bee green 15 bottle return"]},
    "OT Submission Reminder": {"aliases": ["ot rule", "when submit ot", "late ot submission", "overtime reminder"]},
    "Do not Block The Chiller": {"aliases": ["chiller reminder", "can block chiller or not", "keep chiller visible"]},
    "Place Tissue on Cold drinks": {"aliases": ["cold drinks tissue", "put tissue on cold drinks", "protect furniture cold drinks"]},
    "Can not use KB/QB IDs to check customer history": {"aliases": ["use kb qb to check customer history", "staff id check customer history", "customer history access"]},
    "What is the best answer for client asking how much Honey we are using for our honey Juice?": {"aliases": ["how much honey for honey juice", "what to answer customer honey juice", "30gm honey 250gm water", "tell recipe for honey juice or not"]},
    "Hygiene Compliance Notice – Juice Making (Effective Immediately)": {"aliases": ["juice making hygiene rule", "must wear gloves and mask for juice", "juice making penalty", "rm200 commission penalty hygiene"]},
    "Cashless": {"aliases": ["accept cash or not", "who can decide cash transactions", "cash transaction rule"]},
    "Morning Shift Attendance Responsibility & Penalty Notice": {"aliases": ["morning shift attendance memo", "attendance penalty memo", "morning shift penalty notice"]},
    "New Bee 3rd day Check List": {"aliases": ["new bee 3rd day checklist", "3rd day new bee", "third day checklist for new bee", "wanna bee 3rd day", "what should new bee do on day 3", "new staff 3rd day checklist"]},
    "Wanna-Bee onboarding Check list": {"aliases": ["wanna-bee onboarding checklist", "wanna bee onboarding checklist", "wanna bee onboarding", "onboarding checklist", "onboarding check list", "what should i do for onboarding"]},
})

AMBIGUOUS_GROUPS = {
    "opening": [
        "Aeon Roadshow Opening List",
        "Backend Opening Checklist",
        "JHKC Kiosk Opening",
        "Opening Notes",
        "Receipt printer preparation for opening",
        "Shopify POS app Opening",
        "Spring Roadshow Opening List",
    ],
    "closing": [
        "Aeon Roadshow Closing List",
        "Closing Spring Warehouse",
        "Ice Bin Daily Closing Checklist",
        "Kiosk Closing Check List",
        "Kuching Booth Closing dustbin check list",
        "Shopify POS app Closing",
        "Spring Roadshow Closing List",
    ],
}

IRRELEVANT_PHRASES = [
    "joke", "movie", "football", "bitcoin", "crypto", "love", "dating",
    "boyfriend", "girlfriend", "weather", "politics", "pubg", "mlbb", "hate you",
]

WORK_HINTS = [
    "opening", "closing", "checklist", "roadshow", "kiosk", "warehouse", "ice bin",
    "shopify", "printer", "receipt", "dustbin", "booth", "stock", "step", "section",
    "picture", "photo", "image", "next", "show all", "signature", "card payment",
    "merchant copy", "price", "holiday", "danger", "harassment", "fake", "bee points",
    "bee green", "ot", "overtime", "chiller", "tissue", "customer history", "honey juice",
    "hygiene", "cashless", "attendance", "penalty", "new bee", "third day", "3rd day", "onboarding", "wanna bee", "google group", "whatsapp group", "shopify", "doraemon pocket", "bee buddy", "availability", "uniform",
]

FULL_SOP_PHRASES = ["show all", "all step", "all steps", "full sop", "complete sop", "show everything"]
PICTURE_PHRASES = ["picture", "photo", "image", "show picture", "show image", "need picture"]
NEXT_STEP_PHRASES = ["what next", "next", "next step", "after this", "continue", "then what"]
CORRECTION_PHRASES = ["sorry actually", "sorry i mean", "actually i want", "change to", "switch to", "not this one", "wrong"]


def find_title_by_alias(question: str) -> Optional[str]:
    q = normalize_lower(question)

    for title in TITLE_REGISTRY:
        if normalize_lower(title) == q:
            return title

    for title, meta in TITLE_REGISTRY.items():
        for alias in meta["aliases"]:
            alias = normalize_lower(alias)
            if alias == q or alias in q:
                return title

    return None


def find_ambiguous_group(question: str) -> Optional[list[str]]:
    q = normalize_lower(question)
    if find_title_by_alias(q):
        return None

    opening_triggers = {"opening", "open", "opening sop", "show opening", "need opening", "opening checklist"}
    closing_triggers = {"closing", "close", "closing sop", "show closing", "need closing", "closing checklist"}

    if q in opening_triggers or ("opening" in q and "roadshow" not in q and "kiosk" not in q and "aeon" not in q):
        return AMBIGUOUS_GROUPS["opening"]
    if q in closing_triggers or ("closing" in q and "roadshow" not in q and "kiosk" not in q and "aeon" not in q):
        return AMBIGUOUS_GROUPS["closing"]
    return None


def lexical_title_fallback(question: str) -> tuple[Optional[str], int, float]:
    question_tokens = set(tokenize(question))
    best_title = None
    best_overlap = 0
    best_ratio = 0.0

    for title in KNOWLEDGE_DF["title"].dropna().unique():
        title_tokens = set(tokenize(title))
        overlap = len(question_tokens & title_tokens)
        ratio = overlap / max(1, len(title_tokens))
        if overlap > best_overlap or (overlap == best_overlap and ratio > best_ratio):
            best_overlap = overlap
            best_ratio = ratio
            best_title = title

    if best_overlap >= MIN_LEXICAL_OVERLAP:
        return best_title, best_overlap, best_ratio

    if len(question_tokens) <= 2 and best_overlap >= 1 and best_ratio >= 0.50:
        return best_title, best_overlap, best_ratio

    return None, best_overlap, best_ratio


def choose_best_candidate_from_top_k(question: str, candidates: list[tuple[str, float]]) -> tuple[Optional[str], float]:
    if not candidates:
        return None, 0.0

    q_tokens = set(tokenize(question))
    best_title = None
    best_score = -1.0

    for title, model_score in candidates:
        title_tokens = set(tokenize(title))
        overlap = len(q_tokens & title_tokens)
        combined = model_score + (0.05 * overlap)
        if combined > best_score:
            best_score = combined
            best_title = title

    return best_title, best_score


def detect_requested_section(question: str, title_df: pd.DataFrame) -> Optional[str]:
    q = normalize_lower(question)

    for section in title_df["section"].dropna().unique().tolist():
        section = safe_str(section)
        if section and normalize_lower(section) in q:
            return section

    q_tokens = set(tokenize(q))
    for section in title_df["section"].dropna().unique().tolist():
        section = safe_str(section)
        if section:
            section_tokens = set(tokenize(section))
            if len(section_tokens & q_tokens) >= max(1, min(2, len(section_tokens))):
                return section

    return None


def find_step_by_number(steps: list[dict], step_number: int) -> Optional[dict]:
    for step in steps:
        if int(step.get("step_number", -1)) == int(step_number):
            return step
    return None


def score_step_match(question: str, step: dict) -> int:
    q_tokens = set(tokenize(question))
    section_tokens = set(tokenize(step.get("section", "")))
    content_tokens = set(tokenize(step.get("content", "")))
    score = len(q_tokens & content_tokens) * 3 + len(q_tokens & section_tokens) * 2

    if contains_any(question, PICTURE_PHRASES) and step.get("image_urls"):
        score += 2

    return score


def find_best_step(question: str, steps: list[dict]) -> Optional[dict]:
    best_step = None
    best_score = -1

    for step in steps:
        score = score_step_match(question, step)
        if score > best_score:
            best_score = score
            best_step = step

    return best_step if best_score >= 2 else None


def is_irrelevant_question(question: str, context: Optional[dict] = None) -> bool:
    q = normalize_lower(question)
    context = context or {}

    if context.get("title"):
        if extract_requested_step_number(q) is not None:
            return False
        if contains_any(q, FULL_SOP_PHRASES + PICTURE_PHRASES + NEXT_STEP_PHRASES):
            return False
        if len(tokenize(q)) <= 3:
            return False

    if contains_any(q, IRRELEVANT_PHRASES):
        return True

    if contains_any(q, WORK_HINTS):
        return False

    if find_title_by_alias(q) or find_ambiguous_group(q):
        return False

    return False


def should_use_context(question: str, context: dict) -> bool:
    if not context or not isinstance(context, dict):
        return False

    title = normalize_text(context.get("title", ""))
    if not title:
        return False

    q = normalize_lower(question)

    if contains_any(q, CORRECTION_PHRASES):
        return False
    if find_title_by_alias(q) or find_ambiguous_group(q):
        return False
    if contains_any(q, FULL_SOP_PHRASES + PICTURE_PHRASES + NEXT_STEP_PHRASES):
        return True
    if extract_requested_step_number(q) is not None:
        return True

    return len(tokenize(q)) <= 4


def answer_from_context(question: str, context: dict) -> Optional[dict]:
    title = normalize_text(context.get("title", ""))
    title_df = get_df_by_title(title)
    if title_df.empty:
        return None

    steps = build_steps(title_df)

    if contains_any(question, FULL_SOP_PHRASES):
        return {
            "type": "sop",
            "reply": f"Here is the full SOP for {title}.",
            "title": title,
            "section": None,
            "answer": format_sop_answer(title, steps),
            "steps": steps,
            "score": 1.0,
            "source": "context_full_sop",
        }

    requested_step = extract_requested_step_number(question)
    if requested_step is not None:
        step = find_step_by_number(steps, requested_step)
        if step:
            return {
                "type": "sop",
                "reply": f"Please refer to Step {requested_step} for {title}.",
                "title": title,
                "section": step.get("section") or None,
                "answer": format_single_step_answer(title, step),
                "steps": [step],
                "score": 1.0,
                "source": "context_step",
            }

    if contains_any(question, NEXT_STEP_PHRASES):
        last_step_number = context.get("last_step_number")
        try:
            last_step_number = int(last_step_number)
        except Exception:
            last_step_number = None

        if last_step_number is not None:
            next_step = find_step_by_number(steps, last_step_number + 1)
            if next_step:
                return {
                    "type": "sop",
                    "reply": f"After that, please refer to Step {next_step['step_number']} for {title}.",
                    "title": title,
                    "section": next_step.get("section") or None,
                    "answer": format_single_step_answer(title, next_step),
                    "steps": [next_step],
                    "score": 1.0,
                    "source": "context_next_step",
                }

    requested_section = detect_requested_section(question, title_df)
    if requested_section:
        section_df = title_df[title_df["section"].str.lower() == requested_section.lower()]
        if not section_df.empty:
            section_steps = build_steps(section_df)
            return {
                "type": "sop",
                "reply": f"Here is the {requested_section} section for {title}.",
                "title": title,
                "section": requested_section,
                "answer": format_sop_answer(title, section_steps, requested_section),
                "steps": section_steps,
                "score": 1.0,
                "source": "context_section",
            }

    if contains_any(question, PICTURE_PHRASES):
        image_steps = [step for step in steps if step.get("image_urls")]
        if image_steps:
            step = find_best_step(question, image_steps) or image_steps[0]
            return {
                "type": "sop",
                "reply": f"Here is the picture step for {title}.",
                "title": title,
                "section": step.get("section") or None,
                "answer": format_single_step_answer(title, step),
                "steps": [step],
                "score": 1.0,
                "source": "context_picture_step",
            }

    best_step = find_best_step(question, steps)
    if best_step:
        return {
            "type": "sop",
            "reply": f"Please refer to Step {best_step['step_number']} for {title}.",
            "title": title,
            "section": best_step.get("section") or None,
            "answer": format_single_step_answer(title, best_step),
            "steps": [best_step],
            "score": 1.0,
            "source": "context_best_step",
        }

    message = build_section_choice_message(title, steps)
    return {
        "type": "text",
        "reply": message,
        "title": title,
        "section": None,
        "answer": message,
        "steps": [],
        "score": 1.0,
        "source": "context_section_choice",
    }


def resolve_title(question: str) -> tuple[Optional[str], float, str]:
    direct_title = find_title_by_alias(question)
    if direct_title:
        return direct_title, 1.0, "rule_alias"

    ambiguous_titles = find_ambiguous_group(question)
    if ambiguous_titles:
        return None, 1.0, "ambiguous_family"

    predicted_label, confidence = predict_intent(question)
    top_candidates = predict_top_k(question, top_k=3)
    top_choice, top_score = choose_best_candidate_from_top_k(question, top_candidates)
    fallback_title, lexical_overlap, lexical_ratio = lexical_title_fallback(question)

    if predicted_label and confidence >= HIGH_CONFIDENCE_THRESHOLD:
        return predicted_label, confidence, "pytorch_model_high"
    if top_choice and top_score >= MID_CONFIDENCE_THRESHOLD:
        return top_choice, max(confidence, top_score), "pytorch_model_topk"
    if predicted_label and confidence >= CONFIDENCE_THRESHOLD:
        return predicted_label, confidence, "pytorch_model"
    if fallback_title:
        fallback_score = min(0.74, max(0.50, 0.40 + (0.10 * lexical_overlap) + (0.15 * lexical_ratio)))
        return fallback_title, round(fallback_score, 4), "lexical_fallback"

    return None, confidence, "no_match"


def build_escalation_answer(question: str, reason: str) -> dict:
    return {
        "type": "text",
        "reply": NO_MATCH_MESSAGE if reason == "no_match" else ESCALATION_MESSAGE,
        "title": None,
        "section": None,
        "answer": NO_MATCH_MESSAGE if reason == "no_match" else ESCALATION_MESSAGE,
        "steps": [],
        "score": 0.0,
        "source": "low_confidence_or_model_unavailable" if reason == "no_match" else "irrelevant_question",
    }


def get_model_answer(question: str, context: Optional[dict] = None) -> dict:
    question = normalize_text(question)
    context = context or {}

    if not question:
        return {
            "type": "text",
            "reply": "Please enter a question.",
            "title": None,
            "section": None,
            "answer": "Please enter a question.",
            "steps": [],
            "score": 0.0,
            "source": "empty",
        }

    if is_irrelevant_question(question, context=context):
        return build_escalation_answer(question, "irrelevant")

    if should_use_context(question, context):
        context_answer = answer_from_context(question, context)
        if context_answer:
            return context_answer

    ambiguous_titles = find_ambiguous_group(question)
    if ambiguous_titles:
        message = "Which SOP do you need:\n" + "\n".join([f"- {title}" for title in ambiguous_titles]) + "\nPlease choose one."
        return {
            "type": "text",
            "reply": message,
            "title": None,
            "section": None,
            "answer": message,
            "steps": [],
            "score": 1.0,
            "source": "ambiguous_family",
        }

    matched_title, confidence, source = resolve_title(question)

    if not matched_title:
        return build_escalation_answer(question, "no_match")

    title_df = get_df_by_title(matched_title)
    if title_df.empty:
        return build_escalation_answer(question, "no_match")

    steps = build_steps(title_df)

    if contains_any(question, FULL_SOP_PHRASES):
        return {
            "type": "sop",
            "reply": f"Here is the full SOP for {matched_title}.",
            "title": matched_title,
            "section": None,
            "answer": format_sop_answer(matched_title, steps),
            "steps": steps,
            "score": confidence,
            "source": f"{source}_full_sop",
        }

    requested_step = extract_requested_step_number(question)
    if requested_step is not None:
        step = find_step_by_number(steps, requested_step)
        if step:
            return {
                "type": "sop",
                "reply": f"Here is Step {requested_step} for {matched_title}.",
                "title": matched_title,
                "section": step.get("section") or None,
                "answer": format_single_step_answer(matched_title, step),
                "steps": [step],
                "score": confidence,
                "source": f"{source}_exact_step",
            }

    requested_section = detect_requested_section(question, title_df)
    if requested_section:
        section_df = title_df[title_df["section"].str.lower() == requested_section.lower()]
        if not section_df.empty:
            section_steps = build_steps(section_df)
            return {
                "type": "sop",
                "reply": f"Here is the {requested_section} section for {matched_title}.",
                "title": matched_title,
                "section": requested_section,
                "answer": format_sop_answer(matched_title, section_steps, requested_section),
                "steps": section_steps,
                "score": confidence,
                "source": f"{source}_section",
            }

    if contains_any(question, PICTURE_PHRASES):
        image_steps = [step for step in steps if step.get("image_urls")]
        if image_steps:
            step = find_best_step(question, image_steps) or image_steps[0]
            return {
                "type": "sop",
                "reply": f"Here is the picture step for {matched_title}.",
                "title": matched_title,
                "section": step.get("section") or None,
                "answer": format_single_step_answer(matched_title, step),
                "steps": [step],
                "score": confidence,
                "source": f"{source}_picture_step",
            }

    best_step = find_best_step(question, steps)
    if best_step:
        return {
            "type": "sop",
            "reply": f"Please refer to Step {best_step['step_number']} for {matched_title}.",
            "title": matched_title,
            "section": best_step.get("section") or None,
            "answer": format_single_step_answer(matched_title, best_step),
            "steps": [best_step],
            "score": confidence,
            "source": f"{source}_best_step",
        }

    message = build_section_choice_message(matched_title, steps)
    return {
        "type": "text",
        "reply": message,
        "title": matched_title,
        "section": None,
        "answer": message,
        "steps": [],
        "score": confidence,
        "source": f"{source}_section_choice",
    }


MODEL, VOCAB, LABELS, MODEL_ERROR = load_model_package()
KNOWLEDGE_DF = load_knowledge()
