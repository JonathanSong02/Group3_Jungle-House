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

CONFIDENCE_THRESHOLD = 0.40
ESCALATION_MESSAGE = "This question is not related to the SOP system. Please escalate to team lead."
NO_MATCH_MESSAGE = "No confident SOP match. Please escalate to team lead."


# =========================
# TEXT HELPERS
# =========================
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


# =========================
# MODEL
# =========================
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


# =========================
# KNOWLEDGE
# =========================
def load_knowledge() -> pd.DataFrame:
    if not KNOWLEDGE_FILE.exists():
        raise FileNotFoundError(f"Knowledge file not found: {KNOWLEDGE_FILE}")

    df = pd.read_csv(KNOWLEDGE_FILE)

    required = {"title", "content"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"cleaned_knowledge.csv missing columns: {sorted(missing)}")

    df = df.copy()

    if "category" not in df.columns:
        df["category"] = ""
    if "section" not in df.columns:
        df["section"] = ""
    if "image_files" not in df.columns:
        df["image_files"] = ""
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

    parts = re.split(r"[|,;]", text)
    cleaned = []

    for part in parts:
        part = part.strip()
        if not part:
            continue
        cleaned.append(part)

    return cleaned


def build_image_url(relative_path: str) -> str:
    path = safe_str(relative_path).replace("\\", "/").strip()

    if not path:
        return ""

    if path.startswith("http://") or path.startswith("https://"):
        return path

    path = path.lstrip("/")

    if path.startswith("backend/static/"):
        path = path[len("backend/static/"):]

    if path.startswith("static/"):
        path = path[len("static/"):]

    return f"http://127.0.0.1:5000/static/{path}"


def build_image_urls(image_files: list[str]) -> list[str]:
    urls = []
    for path in image_files:
        url = build_image_url(path)
        if url:
            urls.append(url)
    return urls


def build_steps(df: pd.DataFrame) -> list[dict]:
    rows = df.copy().sort_values(by=["step_order"], na_position="last").reset_index(drop=True)
    steps = []
    display_step = 1

    for _, row in rows.iterrows():
        step_no = row["step_order"]
        if pd.isna(step_no):
            step_no = display_step
        else:
            step_no = int(step_no)

        images = parse_image_files(row.get("image_files", ""))

        steps.append({
            "step_number": step_no,
            "section": safe_str(row.get("section", "")),
            "content": safe_str(row.get("content", "")),
            "image_files": images,
            "image_urls": build_image_urls(images),
        })
        display_step += 1

    return steps


def get_df_by_title(title: str) -> pd.DataFrame:
    return KNOWLEDGE_DF[KNOWLEDGE_DF["title"].str.lower() == normalize_lower(title)].copy()


# =========================
# TITLES / ALIASES
# =========================
TITLE_REGISTRY = {
    "Aeon Roadshow Closing List": {
        "aliases": [
            "aeon roadshow closing list",
            "aeon roadshow closing",
            "aeon closing roadshow",
            "closing aeon roadshow",
        ],
    },
    "Aeon Roadshow Opening List": {
        "aliases": [
            "aeon roadshow opening list",
            "aeon roadshow opening",
            "aeon opening roadshow",
            "opening aeon roadshow",
            "roadshow opening aeon",
        ],
    },
    "Backend Opening Checklist": {
        "aliases": [
            "backend opening checklist",
            "backend opening",
            "opening backend",
            "backend checklist",
            "open backend",
        ],
    },
    "Closing Spring Warehouse": {
        "aliases": [
            "closing spring warehouse",
            "spring warehouse closing",
            "warehouse closing",
            "close warehouse",
            "close spring warehouse",
        ],
    },
    "Ice Bin Daily Closing Checklist": {
        "aliases": [
            "ice bin daily closing checklist",
            "ice bin closing",
            "daily closing ice bin",
            "close ice bin",
            "ice bin checklist",
        ],
    },
    "JHKC Kiosk Opening": {
        "aliases": [
            "jhkc kiosk opening",
            "kiosk opening",
            "opening kiosk",
            "open kiosk",
            "jhkc opening",
        ],
    },
    "Kiosk Closing Check List": {
        "aliases": [
            "kiosk closing check list",
            "kiosk closing checklist",
            "kiosk closing",
            "closing kiosk",
            "close kiosk",
            "kiosk close",
        ],
    },
    "Kuching Booth Closing dustbin check list": {
        "aliases": [
            "kuching booth closing dustbin check list",
            "kuching booth closing",
            "dustbin check list",
            "booth closing dustbin",
            "dustbin checklist",
        ],
    },
    "Opening Notes": {
        "aliases": [
            "opening notes",
            "open notes",
            "notes for opening",
        ],
    },
    "Receipt printer preparation for opening": {
        "aliases": [
            "receipt printer preparation for opening",
            "receipt printer opening",
            "printer preparation for opening",
            "prepare receipt printer",
            "receipt printer prepare",
        ],
    },
    "Shopify POS app Closing": {
        "aliases": [
            "shopify pos app closing",
            "shopify pos closing",
            "shopify closing",
            "close shopify pos",
            "pos app closing",
        ],
    },
    "Shopify POS app Opening": {
        "aliases": [
            "shopify pos app opening",
            "shopify pos opening",
            "shopify opening",
            "open shopify pos",
            "pos app opening",
        ],
    },
    "Spring Roadshow Closing List": {
        "aliases": [
            "spring roadshow closing list",
            "spring roadshow closing",
            "roadshow closing spring",
            "closing spring roadshow",
        ],
    },
    "Spring Roadshow Opening List": {
        "aliases": [
            "spring roadshow opening list",
            "spring roadshow opening",
            "roadshow opening spring",
            "opening spring roadshow",
        ],
    },
}

AMBIGUOUS_GROUPS = {
    "roadshow opening": [
        "Aeon Roadshow Opening List",
        "Spring Roadshow Opening List",
    ],
    "roadshow closing": [
        "Aeon Roadshow Closing List",
        "Spring Roadshow Closing List",
    ],
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
    "boyfriend", "girlfriend", "weather", "politics", "pubg", "mlbb",
    "babi", "bodoh", "idiot", "stupid", "hate you",
]

WORK_HINTS = [
    "opening", "closing", "checklist", "roadshow", "kiosk", "warehouse",
    "ice bin", "shopify", "printer", "receipt", "dustbin", "booth",
    "stock", "stock check", "fridge", "fridge check", "step",
    "section", "picture", "photo", "image", "next", "show all",
    "notes", "opening notes", "test print",
]

FULL_SOP_PHRASES = [
    "show all", "all step", "all steps", "full sop", "complete sop",
    "show full sop", "show everything", "whole sop",
]

PICTURE_PHRASES = [
    "picture", "pictures", "photo", "photos", "image", "images",
    "show picture", "show image", "need picture", "picture for step",
]

NEXT_STEP_PHRASES = [
    "what next", "next", "next step", "what should i do next",
    "after this", "continue", "then what",
]

CORRECTION_PHRASES = [
    "sorry actually", "sorry i mean", "actually i want", "actually i mean",
    "no i mean", "change to", "switch to", "not this one", "wrong",
]

SECTION_KEYWORDS = {
    "stocktake": ["stocktake", "stock take"],
    "settlement": ["settlement", "cash settlement"],
    "device": ["device", "devices", "machine"],
    "terminal machine": ["terminal", "terminal machine"],
    "chiller": ["chiller", "fridge"],
    "daily record sheet": ["daily record", "record sheet"],
    "additional": ["additional"],
    "test print": ["test print", "printer test"],
    "stock check": ["stock check"],
    "fridge check": ["fridge check"],
}

FOLLOW_UP_KEYWORDS = (
    FULL_SOP_PHRASES
    + PICTURE_PHRASES
    + NEXT_STEP_PHRASES
    + [
        "step",
        "section",
        "stocktake",
        "settlement",
        "device",
        "terminal",
        "chiller",
        "test print",
        "stock check",
        "fridge check",
        "notes",
    ]
)


# =========================
# FORMATTERS
# =========================
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
    parts = [title]
    if step.get("section"):
        parts.append(f"Section: {step['section']}")
    parts.append(f"Step {step['step_number']}: {step['content']}")
    return "\n".join(parts).strip()


def build_sections_summary(steps: list[dict]) -> list[str]:
    sections = []
    seen = set()
    for step in steps:
        section = normalize_text(step.get("section", ""))
        if section and section.lower() not in seen:
            seen.add(section.lower())
            sections.append(section)
    return sections


def build_section_choice_message(title: str, steps: list[dict]) -> str:
    sections = build_sections_summary(steps)
    if sections:
        return f"I found {title}. Available sections: {', '.join(sections)}."
    return f"I found {title}. Which step do you need?"


# =========================
# ROUTING HELPERS
# =========================
def is_full_sop_request(question: str) -> bool:
    return contains_any(question, FULL_SOP_PHRASES)


def is_picture_request(question: str) -> bool:
    return contains_any(question, PICTURE_PHRASES)


def is_next_step_request(question: str) -> bool:
    return contains_any(question, NEXT_STEP_PHRASES)


def is_correction_request(question: str) -> bool:
    return contains_any(question, CORRECTION_PHRASES)


def extract_requested_step_number(question: str) -> Optional[int]:
    q = normalize_lower(question)
    for pattern in [r"\bstep\s*(\d+)\b", r"\bno\.?\s*(\d+)\b", r"\bnumber\s*(\d+)\b"]:
        match = re.search(pattern, q)
        if match:
            return int(match.group(1))
    if re.fullmatch(r"\d+", q):
        return int(q)
    return None


def detect_requested_section(question: str, title_df: pd.DataFrame) -> Optional[str]:
    q = normalize_lower(question)
    sections = [safe_str(x) for x in title_df["section"].dropna().tolist() if safe_str(x)]

    for section in sections:
        if normalize_lower(section) in q:
            return section

    for canonical, aliases in SECTION_KEYWORDS.items():
        if any(alias in q for alias in aliases):
            for section in sections:
                if canonical in normalize_lower(section):
                    return section

    return None


def lexical_title_fallback(question: str) -> Optional[str]:
    question_tokens = set(tokenize(question))
    if not question_tokens:
        return None

    best_title = None
    best_score = 0
    for title in KNOWLEDGE_DF["title"].dropna().unique():
        title_tokens = set(tokenize(title))
        score = len(question_tokens & title_tokens)
        if score > best_score:
            best_score = score
            best_title = title

    return best_title if best_score > 0 else None


def find_title_by_alias(question: str) -> Optional[str]:
    q = normalize_lower(question)

    for title in TITLE_REGISTRY.keys():
        if normalize_lower(title) == q:
            return title

    for title, meta in TITLE_REGISTRY.items():
        for alias in meta["aliases"]:
            if normalize_lower(alias) == q:
                return title

    for title in TITLE_REGISTRY.keys():
        if normalize_lower(title) in q:
            return title

    for title, meta in TITLE_REGISTRY.items():
        for alias in meta["aliases"]:
            if normalize_lower(alias) in q:
                return title

    return None


def find_ambiguous_group(question: str) -> Optional[list[str]]:
    q = normalize_lower(question)

    exact_title = find_title_by_alias(q)
    if exact_title:
        return None

    if "roadshow" in q and "opening" in q and "aeon" not in q and "spring" not in q:
        return AMBIGUOUS_GROUPS["roadshow opening"]

    if "roadshow" in q and "closing" in q and "aeon" not in q and "spring" not in q:
        return AMBIGUOUS_GROUPS["roadshow closing"]

    if q in ["opening", "open", "opening sop", "show opening"]:
        return AMBIGUOUS_GROUPS["opening"]

    if q in ["closing", "close", "closing sop", "show closing"]:
        return AMBIGUOUS_GROUPS["closing"]

    return None


def is_irrelevant_question(question: str, context: Optional[dict] = None) -> bool:
    q = normalize_lower(question)
    context = context or {}

    if context.get("title"):
        if extract_requested_step_number(q) is not None:
            return False
        if contains_any(q, FOLLOW_UP_KEYWORDS):
            return False
        if len(tokenize(q)) <= 3:
            return False

    if contains_any(q, IRRELEVANT_PHRASES):
        return True

    if contains_any(q, WORK_HINTS):
        return False

    if find_title_by_alias(q):
        return False

    if find_ambiguous_group(q):
        return False

    return True


def should_use_context(question: str, context: dict) -> bool:
    if not context or not isinstance(context, dict):
        return False

    title = normalize_text(context.get("title", ""))
    if not title:
        return False

    if is_correction_request(question):
        return False

    if find_title_by_alias(question):
        return False

    if find_ambiguous_group(question):
        return False

    q = normalize_lower(question)

    if contains_any(q, FOLLOW_UP_KEYWORDS):
        return True

    if extract_requested_step_number(q) is not None:
        return True

    return len(tokenize(q)) <= 4


def find_step_by_number(steps: list[dict], step_number: int) -> Optional[dict]:
    for step in steps:
        if int(step.get("step_number", -1)) == int(step_number):
            return step
    return None


def score_step_match(question: str, step: dict) -> int:
    q = normalize_lower(question)
    score = 0
    content = normalize_lower(step.get("content", ""))
    section = normalize_lower(step.get("section", ""))

    for token in tokenize(q):
        if len(token) <= 1:
            continue
        if token in content:
            score += 3
        if token in section:
            score += 2

    if is_picture_request(q) and step.get("image_urls"):
        score += 2

    return score


def find_best_step(question: str, steps: list[dict]) -> Optional[dict]:
    best = None
    best_score = -1

    for step in steps:
        score = score_step_match(question, step)
        if score > best_score:
            best_score = score
            best = step

    if best_score < 2:
        return None

    return best


# =========================
# CONTEXT ANSWERS
# =========================
def answer_from_context(question: str, context: dict) -> Optional[dict]:
    title = normalize_text(context.get("title", ""))
    if not title:
        return None

    title_df = get_df_by_title(title)
    if title_df.empty:
        return None

    steps = build_steps(title_df)

    if is_full_sop_request(question):
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

        max_step = max([int(s["step_number"]) for s in steps], default=0)
        message = f"{title} only has {max_step} steps. Please choose a valid step number."
        return {
            "type": "text",
            "reply": message,
            "title": title,
            "section": None,
            "answer": message,
            "steps": [],
            "score": 1.0,
            "source": "context_step_out_of_range",
        }

    if is_next_step_request(question):
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
        section_df = title_df[title_df["section"].str.lower() == requested_section.lower()].copy()
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

    if is_picture_request(question):
        best_picture_step = None
        best_score = -1
        for step in steps:
            if not step.get("image_urls"):
                continue
            score = score_step_match(question, step)
            if score > best_score:
                best_score = score
                best_picture_step = step

        if best_picture_step:
            return {
                "type": "sop",
                "reply": f"Here is the picture step for {title}.",
                "title": title,
                "section": best_picture_step.get("section") or None,
                "answer": format_single_step_answer(title, best_picture_step),
                "steps": [best_picture_step],
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


# =========================
# MAIN RESOLUTION
# =========================
def resolve_title(question: str) -> tuple[Optional[str], float, str]:
    direct_title = find_title_by_alias(question)
    if direct_title:
        return direct_title, 1.0, "rule_alias"

    predicted_label, confidence = predict_intent(question)
    if predicted_label and confidence >= CONFIDENCE_THRESHOLD:
        return predicted_label, confidence, "pytorch_model"

    fallback_title = lexical_title_fallback(question)
    if fallback_title:
        return fallback_title, max(confidence, 0.51), "lexical_fallback"

    return None, confidence, "no_match"


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

    if is_irrelevant_question(question, context):
        return {
            "type": "text",
            "reply": ESCALATION_MESSAGE,
            "title": None,
            "section": None,
            "answer": ESCALATION_MESSAGE,
            "steps": [],
            "score": 1.0,
            "source": "irrelevant_question",
        }

    if should_use_context(question, context):
        context_answer = answer_from_context(question, context)
        if context_answer:
            return context_answer

    matched_title, confidence, source = resolve_title(question)

    if not matched_title:
        ambiguous_titles = find_ambiguous_group(question)
        if ambiguous_titles:
            message = f"Which SOP do you need: {', '.join(ambiguous_titles)}?"
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

        details = f"Model unavailable: {MODEL_ERROR}" if MODEL_ERROR else NO_MATCH_MESSAGE
        return {
            "type": "text",
            "reply": NO_MATCH_MESSAGE,
            "title": None,
            "section": None,
            "answer": details,
            "steps": [],
            "score": confidence,
            "source": "low_confidence_or_model_unavailable",
        }

    title_df = get_df_by_title(matched_title)
    if title_df.empty:
        return {
            "type": "text",
            "reply": f"{matched_title} was matched, but no rows were found in cleaned_knowledge.csv.",
            "title": matched_title,
            "section": None,
            "answer": f"Please check whether cleaned_knowledge.csv contains the title: {matched_title}",
            "steps": [],
            "score": confidence,
            "source": "title_not_found",
        }

    all_steps = build_steps(title_df)

    if is_full_sop_request(question):
        return {
            "type": "sop",
            "reply": f"Here is the full SOP for {matched_title}.",
            "title": matched_title,
            "section": None,
            "answer": format_sop_answer(matched_title, all_steps),
            "steps": all_steps,
            "score": confidence,
            "source": f"{source}_full_sop",
        }

    requested_step = extract_requested_step_number(question)
    if requested_step is not None:
        step = find_step_by_number(all_steps, requested_step)
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

        max_step = max([int(s["step_number"]) for s in all_steps], default=0)
        message = f"{matched_title} only has {max_step} steps. Please choose a valid step number."
        return {
            "type": "text",
            "reply": message,
            "title": matched_title,
            "section": None,
            "answer": message,
            "steps": [],
            "score": confidence,
            "source": "step_not_found",
        }

    requested_section = detect_requested_section(question, title_df)
    if requested_section:
        section_df = title_df[title_df["section"].str.lower() == requested_section.lower()].copy()
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

    if is_picture_request(question):
        best_picture_step = None
        best_score = -1
        for step in all_steps:
            if not step.get("image_urls"):
                continue
            score = score_step_match(question, step)
            if score > best_score:
                best_score = score
                best_picture_step = step

        if best_picture_step:
            return {
                "type": "sop",
                "reply": f"Here is the picture step for {matched_title}.",
                "title": matched_title,
                "section": best_picture_step.get("section") or None,
                "answer": format_single_step_answer(matched_title, best_picture_step),
                "steps": [best_picture_step],
                "score": confidence,
                "source": f"{source}_picture_step",
            }

    best_step = find_best_step(question, all_steps)
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

    message = build_section_choice_message(matched_title, all_steps)
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