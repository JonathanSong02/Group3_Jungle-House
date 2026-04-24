from __future__ import annotations


import re
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from training_data import (
    get_all_titles,
    get_title_aliases,
    get_category_keywords,
    get_title_to_category,
    get_greeting_phrases,
    get_help_phrases,
    get_topic_switch_phrases,
    get_irrelevant_phrases,
    get_escalation_phrases,
    get_show_all_phrases,
    get_picture_phrases,
    get_next_step_phrases,
    get_titles_by_category,
    infer_category_from_title,
)


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
STATIC_DIR = BASE_DIR.parent / "static"
KNOWLEDGE_FILE = DATA_DIR / "cleaned_knowledge.csv"


# =========================================================
# BASIC HELPERS
# =========================================================
def safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def normalize_text(text: str) -> str:
    text = safe_str(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_lower(text: str) -> str:
    return normalize_text(text).lower()


def tokenize(text: str) -> list[str]:
    q = normalize_lower(text)
    q = re.sub(r"[^a-z0-9\s]", " ", q)
    return [x for x in q.split() if x]


def contains_any(text: str, phrases: list[str]) -> bool:
    q = normalize_lower(text)
    return any(normalize_lower(p) in q for p in phrases if safe_str(p))


def unique_keep_order(values: list[Any]) -> list[Any]:
    seen = set()
    result = []
    for item in values:
        key = repr(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


# =========================================================
# LOAD KNOWLEDGE
# =========================================================
def load_knowledge() -> pd.DataFrame:
    if not KNOWLEDGE_FILE.exists():
        return pd.DataFrame(columns=["title", "section", "content", "step_order", "image_path"])

    df = pd.read_csv(KNOWLEDGE_FILE).copy()

    for col in ["title", "section", "content", "image_path"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].apply(safe_str)

    if "step_order" not in df.columns:
        df["step_order"] = None

    df["step_order"] = pd.to_numeric(df["step_order"], errors="coerce")
    return df


KNOWLEDGE_DF = load_knowledge()
KNOWN_TITLES = sorted([safe_str(x) for x in KNOWLEDGE_DF["title"].dropna().unique().tolist() if safe_str(x)])

TITLE_TO_CATEGORY = get_title_to_category()


# =========================================================
# TITLES / ALIASES
# =========================================================
TITLE_ALIASES = {
    "Aeon Roadshow Closing List": [
        "aeon roadshow closing list",
        "aeon roadshow closing",
        "aeon closing roadshow",
        "aeon closing",
        "aeon close",
    ],
    "Aeon Roadshow Opening List": [
        "aeon roadshow opening list",
        "aeon roadshow opening",
        "aeon opening roadshow",
        "aeon opening",
        "aeon open",
    ],
    "Backend Opening Checklist": [
        "backend opening checklist",
        "backend opening",
        "backend checklist",
        "open backend",
    ],
    "Closing Spring Warehouse": [
        "closing spring warehouse",
        "spring warehouse closing",
        "warehouse closing",
        "close warehouse",
    ],
    "Ice Bin Daily Closing Checklist": [
        "ice bin daily closing checklist",
        "ice bin closing checklist",
        "ice bin daily closing",
        "ice bin closing",
        "close ice bin",
        "ice bin",
    ],
    "JHKC Kiosk Opening": [
        "jhkc kiosk opening",
        "kiosk opening",
        "opening kiosk",
        "open kiosk",
        "jhkc opening",
        "spring kiosk opening",
        "kiosk open",
        "kiosk",
    ],
    "Kiosk Closing Check List": [
        "kiosk closing check list",
        "kiosk closing checklist",
        "kiosk closing",
        "closing kiosk",
        "close kiosk",
        "spring kiosk closing",
        "kiosk close",
    ],
    "Kuching Booth Closing dustbin check list": [
        "kuching booth closing dustbin check list",
        "kuching booth dustbin check list",
        "kuching booth closing",
        "dustbin checklist",
        "dustbin check list",
        "booth dustbin",
        "dustbin closing",
    ],
    "Opening Notes": [
        "opening notes",
        "opening note",
        "important opening notes",
        "notes for opening",
        "open notes",
    ],
    "Receipt printer preparation for opening": [
        "receipt printer preparation for opening",
        "receipt printer opening",
        "printer preparation for opening",
        "printer opening",
        "receipt printer",
        "printer prepare",
        "printer setup",
        "test print receipt printer",
    ],
    "Sales Closing Reminders Material": [
        "sales closing reminders material",
        "sales closing reminder",
        "closing reminders",
        "sales reminder",
        "sales closing reminders",
    ],
    "Shopify POS app Closing": [
        "shopify pos app closing",
        "shopify pos closing",
        "shopify closing",
        "close shopify pos",
        "shopify pos close",
    ],
    "Shopify POS app Opening": [
        "shopify pos app opening",
        "shopify pos opening",
        "shopify opening",
        "open shopify pos",
        "shopify pos open",
    ],
    "Spring Roadshow Closing List": [
        "spring roadshow closing list",
        "spring roadshow closing",
        "roadshow closing spring",
        "closing spring roadshow",
        "roadshow closing",
        "close roadshow",
    ],
    "Spring Roadshow Opening List": [
        "spring roadshow opening list",
        "spring roadshow opening",
        "roadshow opening spring",
        "opening spring roadshow",
        "roadshow opening",
        "open roadshow",
        "roadshow",
    ],
    "Win the Heart Gift Guide": [
        "win the heart gift guide",
        "gift guide",
        "heart gift guide",
    ],
    "Promotion": [
        "promotion",
        "promo",
        "latest promotion",
        "current promotion",
        "promo details",
        "promotion info",
        "promotion details",
        "promotions",
    ],
    "Lab Report in Website - temporarily removed": [
        "lab report in website",
        "lab report removed",
        "lab report temporarily removed",
        "website lab report",
    ],
    "Golden Passion Honey (New Product)": [
        "golden passion honey",
        "golden passion",
        "golden passion honey new product",
        "new product golden passion honey",
    ],
    "How shifts arrangements are given​": [
        "how shifts arrangements are given",
        "shift arrangement",
        "shift arrangements",
        "shift schedule",
        "how shift is given",
        "shift",
        "shifts",
    ],
    "Bee Point Policy – Crew Member Guideline": [
        "bee point policy",
        "bee points policy",
        "crew member guideline",
        "bee point guideline",
        "bee points",
    ],
    "Hari Raya Aidilfitri Public Holiday – Retail (2026)": [
        "hari raya aidilfitri public holiday retail 2026",
        "hari raya public holiday 2026",
        "retail public holiday 2026",
        "hari raya retail holiday",
    ],
    "Hari Raya Aidilfitri – Dress Code": [
        "hari raya dress code",
        "aidilfitri dress code",
        "dress code hari raya",
        "raya dress code",
    ],
    "Kuching incentive data submission": [
        "kuching incentive data submission",
        "kuching incentive",
        "incentive data submission",
        "incentive submission",
    ],
    "PUBLIC HOLIDAY 2026": [
        "public holiday 2026",
        "holiday 2026",
        "public holiday",
        "holiday notice",
        "holiday",
    ],
    "Do not open raw honey tester without permission.": [
        "do not open raw honey tester without permission",
        "raw honey tester",
        "honey tester permission",
        "tester without permission",
    ],
    "Purple lavender out of stock": [
        "purple lavender out of stock",
        "purple lavender",
        "lavender out of stock",
    ],
    "Free wooden stirrer": [
        "free wooden stirrer",
        "wooden stirrer",
        "stirrer",
    ],
    "Mask and Badge": [
        "mask and badge",
        "badge",
        "mask",
        "wear badge",
    ],
    "Proper way to stack HDPC": [
        "proper way to stack hdpc",
        "stack hdpc",
        "hdpc stacking",
        "hdpc",
    ],
    "Price for new packaging for HWJ and SHVP": [
        "price for new packaging for hwj and shvp",
        "new packaging price",
        "hwj shvp packaging price",
        "packaging price",
    ],
    "Customer signature for card payment": [
        "customer signature for card payment",
        "card payment signature",
        "customer signature",
        "signature for card payment",
    ],
    "Eating inside the store is strictly prohibited": [
        "eating inside the store is strictly prohibited",
        "eating inside store",
        "no eating inside store",
        "eating prohibited",
    ],
    "Emergency Guide – Responding to Danger or Harassment": [
        "emergency guide responding to danger or harassment",
        "danger or harassment",
        "emergency guide",
        "harassment guide",
        "danger guide",
    ],
    "Fake Jungle House": [
        "fake jungle house",
        "fake jh",
        "fake shop",
    ],
    "Bee Points: Redeem Only When Needed": [
        "bee points redeem only when needed",
        "redeem only when needed",
        "bee points redeem",
    ],
    "Bee Green 15": [
        "bee green 15",
        "bee green",
    ],
    "OT Submission Reminder": [
        "ot submission reminder",
        "ot reminder",
        "overtime reminder",
        "overtime submission reminder",
    ],
    "Do not Block The Chiller": [
        "do not block the chiller",
        "do not block chiller",
        "block the chiller",
        "chiller blocked",
    ],
    "Place Tissue on Cold drinks": [
        "place tissue on cold drinks",
        "tissue on cold drinks",
        "cold drinks tissue",
    ],
    "Can not use KB/QB IDs to check customer history": [
        "can not use kb qb ids to check customer history",
        "kb qb ids",
        "check customer history ids",
        "kb ids",
        "qb ids",
    ],
    "What is the best answer for client asking how much Honey we are using for our honey Juice?": [
        "how much honey we are using for our honey juice",
        "best answer for client honey juice",
        "honey juice answer",
        "customer ask how much honey",
    ],
    "Hygiene Compliance Notice – Juice Making (Effective Immediately)": [
        "hygiene compliance notice juice making",
        "juice making hygiene compliance",
        "hygiene compliance notice",
        "juice hygiene notice",
    ],
    "Cashless": [
        "cashless",
        "cashless payment",
        "no cash",
    ],
    "Morning Shift Attendance Responsibility & Penalty Notice": [
        "morning shift attendance responsibility penalty notice",
        "morning shift attendance",
        "attendance penalty notice",
        "attendance responsibility",
    ],
    "New Bee 3rd day Check List": [
        "new bee 3rd day check list",
        "new bee 3rd day checklist",
        "new bee third day",
        "new bee 3rd day",
        "new bee day 3",
        "3rd day checklist",
        "third day checklist",
        "3rd day",
        "third day",
        "day 3",
        "day three",
    ],
    "New Bee 1st day Check List": [
        "new bee 1st day check list",
        "new bee 1st day checklist",
        "new bee first day",
        "new bee 1st day",
        "new bee day 1",
        "1st day checklist",
        "first day checklist",
        "1st day",
        "first day",
        "day 1",
        "day one",
    ],
    "Wanna-Bee onboarding Check list": [
        "wanna-bee onboarding check list",
        "wanna-bee onboarding checklist",
        "wanna bee onboarding",
        "onboarding checklist",
        "onboarding",
        "wanna bee",
    ],
}


CATEGORY_KEYWORDS = {
    "sop": [
        "sop", "checklist", "check list", "step", "steps", "show all", "picture",
        "image", "images", "photo", "photos", "section", "next step", "opening",
        "closing", "kiosk", "roadshow", "warehouse", "shopify", "printer", "notes",
        "backend", "ice bin", "dustbin",
    ],
    "promotion": [
        "promotion", "promo", "gift guide", "discount", "bundle", "campaign",
    ],
    "product": [
        "product", "product knowledge", "new product", "honey", "packaging",
        "customer ask", "customer answer", "sales guidance",
    ],
    "notice": [
        "notice", "update", "latest update", "announcement", "policy", "guideline",
        "public holiday", "holiday", "dress code", "badge", "mask", "ot",
        "attendance", "chiller", "cashless", "harassment", "danger",
    ],
    "training": [
        "new bee", "onboarding", "training", "first day", "1st day", "day 1",
        "third day", "3rd day", "day 3", "wanna-bee",
    ],
}


SECTION_ALIASES = {
    "Stocktake": ["stocktake", "stock take"],
    "Settlement": ["settlement", "cash settlement"],
    "Devices": ["devices", "device"],
    "Terminal Machine": ["terminal", "terminal machine"],
    "Chiller": ["chiller", "fridge"],
    "Display Closing": ["display closing", "display"],
    "Daily Record Sheet": ["daily record sheet", "daily record"],
    "Additional": ["additional"],
    "Test Print": ["test print", "printer test"],
    "Stock Check": ["stock check"],
    "Fridge Check": ["fridge check"],
    "Cleaning": ["cleaning", "clean"],
    "Attendance": ["attendance"],
    "Penalty": ["penalty"],
    "Onboarding": ["onboarding"],
    "Sales": ["sales", "sales closing"],
}


GREETING_PHRASES = [
    "hi", "hello", "hey", "hai", "morning", "good morning",
    "good afternoon", "good evening", "hi ai", "hello ai",
]

GUIDE_PHRASES = [
    "help", "what can you do", "guide me", "show me options", "what should i ask",
    "not sure", "dont know", "don't know", "i dont know", "i don't know",
]

SHOW_ALL_PHRASES = [
    "show all", "all step", "all steps", "full sop", "full checklist",
    "show full", "full guide", "entire sop", "whole sop",
]

PICTURE_PHRASES = [
    "picture", "pictures", "image", "images", "photo", "photos", "show picture",
]

NEXT_STEP_PHRASES = [
    "what should i do next", "what next", "next", "next step",
    "after this what should i do", "after that what should i do",
]

NEGATIVE_SWITCH_PHRASES = [
    "not this", "wrong", "wrong one", "other one", "another one", "actually i want",
    "sorry actually", "change topic", "switch", "instead",
]

IRRELEVANT_ONLY_PHRASES = [
    "babi", "fuck", "movie", "relationship", "weather",
]


# =========================================================
# FAMILY / CATEGORY
# =========================================================
def infer_family_from_title(title: str) -> str:
    lower = normalize_lower(title)

    if title in {
        "Aeon Roadshow Closing List",
        "Aeon Roadshow Opening List",
        "Backend Opening Checklist",
        "Closing Spring Warehouse",
        "Ice Bin Daily Closing Checklist",
        "JHKC Kiosk Opening",
        "Kiosk Closing Check List",
        "Kuching Booth Closing dustbin check list",
        "Opening Notes",
        "Receipt printer preparation for opening",
        "Sales Closing Reminders Material",
        "Shopify POS app Closing",
        "Shopify POS app Opening",
        "Spring Roadshow Closing List",
        "Spring Roadshow Opening List",
    }:
        return "sop"

    if title in {
        "Promotion",
        "Win the Heart Gift Guide",
        "Bee Green 15",
    }:
        return "promotion"

    if title in {
        "Golden Passion Honey (New Product)",
        "Price for new packaging for HWJ and SHVP",
        "What is the best answer for client asking how much Honey we are using for our honey Juice?",
    }:
        return "product"

    if title in {
        "New Bee 1st day Check List",
        "New Bee 3rd day Check List",
        "Wanna-Bee onboarding Check list",
    }:
        return "training"

    if any(x in lower for x in ["opening", "closing", "check list", "checklist", "shopify", "printer", "warehouse"]):
        return "sop"

    return "notice"


def detect_high_level_category(question: str) -> Optional[str]:
    q = normalize_lower(question)
    best_category = None
    best_score = 0

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if normalize_lower(kw) in q)
        if score > best_score:
            best_score = score
            best_category = category

    return best_category if best_score > 0 else None


# =========================================================
# CONTEXT HELPERS
# =========================================================
def normalize_context(context: Any) -> dict:
    if not isinstance(context, dict):
        return {}

    return {
        "title": safe_str(context.get("title")),
        "category": safe_str(context.get("category")),
        "section": safe_str(context.get("section")),
        "unclear_count": int(context.get("unclear_count", 0) or 0),
    }


def get_unclear_count(context: dict) -> int:
    try:
        return int(context.get("unclear_count", 0))
    except Exception:
        return 0


def should_clear_context(question: str, context: dict) -> bool:
    q = normalize_lower(question)
    current_title = normalize_lower(safe_str(context.get("title")))
    current_category = normalize_lower(safe_str(context.get("category")))

    if not q:
        return False

    # Explicit topic switch
    if contains_any(q, [
        "not this",
        "wrong",
        "wrong one",
        "other one",
        "another one",
        "actually i want",
        "sorry actually",
        "change topic",
        "switch topic",
        "switch",
        "instead",
        "different topic",
        "different one",
    ]):
        return True

    # These are follow-up requests, so keep current context
    if (
        wants_show_all(q)
        or wants_picture(q)
        or wants_next_step(q)
        or extract_step_number(q) is not None
        or extract_step_range(q) is not None
    ):
        return False

    # Section request should also keep context
    if current_title:
        title_df = KNOWLEDGE_DF[KNOWLEDGE_DF["title"] == safe_str(context.get("title"))].copy()
        if not title_df.empty:
            steps = build_steps(title_df)
            available_sections = sorted(
                set([safe_str(x["section"]) for x in steps if safe_str(x.get("section"))])
            )
            if detect_section(q, available_sections):
                return False

    detected_category = detect_high_level_category(q)
    if detected_category and current_category and detected_category != current_category:
        return True

    matched_titles = match_titles(q)
    if matched_titles:
        best_title = matched_titles[0][0]
        if normalize_lower(best_title) != current_title:
            return True

    # Short follow-up words should stay in current topic
    short_follow_up_words = {
        "show all", "all", "picture", "pictures", "image", "images",
        "photo", "photos", "next", "next step", "section"
    }
    if q in short_follow_up_words:
        return False

    return False


# =========================================================
# IMAGE HELPERS
# =========================================================
def split_image_values(raw: str) -> list[str]:
    raw = safe_str(raw)
    if not raw:
        return []

    parts = re.split(r"[|;,]+", raw)
    values = []
    for part in parts:
        item = normalize_text(part)
        if item:
            values.append(item)
    return unique_keep_order(values)


def to_static_url(image_path: str) -> str:
    path = safe_str(image_path).replace("\\", "/").lstrip("/")
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    path = re.sub(r"^static/", "", path, flags=re.IGNORECASE)
    return f"/static/{path}"

SOP_IMAGE_FOLDER_MAP = {
    "Aeon Roadshow Closing List": "aeon_roadshow_closing",
    "Aeon Roadshow Opening List": "aeon_roadshow_opening",
    "JHKC Kiosk Opening": "kiosk_opening",
    "Kiosk Closing Check List": "kiosk_closing",
    "Spring Roadshow Closing List": "spring_roadshow_closing",
    "Spring Roadshow Opening List": "spring_roadshow_opening",
    "Backend Opening Checklist": "backend_opening",
    "Closing Spring Warehouse": "closing_spring_warehouse",
    "Ice Bin Daily Closing Checklist": "ice_bin_daily_closing",
    "Shopify POS app Closing": "shopify_pos_app_closing",
    "Shopify POS app Opening": "shopify_pos_app_opening",
    "Receipt printer preparation for opening": "receipt_printer_preparation_for_opening",
    "Kuching Booth Closing dustbin check list": "kuching_booth_closing_dustbin",
}


def auto_find_step_images(title: str, step_number: int) -> list[str]:
    """
    Auto-detect images from:
    static/sop_images/<folder>/step13_1.jpg
    static/sop_images/<folder>/step13_2.jpg
    static/sop_images/<folder>/step13.jpg
    """

    title = safe_str(title)
    folder = SOP_IMAGE_FOLDER_MAP.get(title)

    if not folder:
        folder = normalize_lower(title)
        folder = re.sub(r"\bcheck\s*list\b", "", folder)
        folder = re.sub(r"\blist\b", "", folder)
        folder = re.sub(r"[^a-z0-9]+", "_", folder)
        folder = folder.strip("_")

    image_dir = STATIC_DIR / "sop_images" / folder

    if not image_dir.exists():
        return []

    found = []
    extensions = ["jpg", "jpeg", "png", "webp", "gif"]

    # step13.jpg
    for ext in extensions:
        file_path = image_dir / f"step{step_number}.{ext}"
        if file_path.exists():
            found.append(f"sop_images/{folder}/{file_path.name}")

    # step13_1.jpg, step13_2.jpg, etc.
    for image_index in range(1, 20):
        for ext in extensions:
            file_path = image_dir / f"step{step_number}_{image_index}.{ext}"
            if file_path.exists():
                found.append(f"sop_images/{folder}/{file_path.name}")

    return unique_keep_order(found)

# =========================================================
# STEP / RANGE / SECTION
# =========================================================
def extract_step_number(question: str) -> Optional[int]:
    q = normalize_lower(question)
    match = re.search(r"\bstep\s*(\d+)\b", q)
    if match:
        return int(match.group(1))
    return None


def extract_step_range(question: str) -> Optional[tuple[int, int]]:
    q = normalize_lower(question)

    patterns = [
        r"\bstep\s*(\d+)\s*(?:to|-|until|hingga)\s*step\s*(\d+)\b",
        r"\bstep\s*(\d+)\s*(?:to|-|until|hingga)\s*(\d+)\b",
        r"\bfrom\s*step\s*(\d+)\s*(?:to|until|hingga)\s*step\s*(\d+)\b",
        r"\bfrom\s*step\s*(\d+)\s*(?:to|until|hingga)\s*(\d+)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            start_step = int(match.group(1))
            end_step = int(match.group(2))
            if start_step > end_step:
                start_step, end_step = end_step, start_step
            return start_step, end_step

    return None


def detect_section(question: str, available_sections: list[str]) -> Optional[str]:
    q = normalize_lower(question)

    for section in available_sections:
        if normalize_lower(section) in q:
            return section

    for canonical, aliases in SECTION_ALIASES.items():
        if canonical not in available_sections:
            continue
        for alias in aliases:
            if normalize_lower(alias) in q:
                return canonical

    return None


# =========================================================
# TITLE MATCH
# =========================================================
def title_variants(title: str) -> list[str]:
    variants = [title, normalize_lower(title)]
    variants.extend(TITLE_ALIASES.get(title, []))
    return unique_keep_order([normalize_text(v) for v in variants if safe_str(v)])


def score_title_match(question: str, title: str) -> float:
    q = normalize_lower(question)
    q_tokens = set(tokenize(q))
    best = 0.0

    for variant in title_variants(title):
        v = normalize_lower(variant)
        if not v:
            continue

        if q == v:
            best = max(best, 1.0)
            continue

        if v in q:
            best = max(best, 0.96)

        v_tokens = set(tokenize(v))
        overlap = len(q_tokens & v_tokens)
        token_score = overlap / max(len(v_tokens), 1)

        if token_score >= 0.75:
            best = max(best, 0.88)
        elif token_score >= 0.5:
            best = max(best, 0.76)
        elif token_score >= 0.34:
            best = max(best, 0.64)

    title_lower = normalize_lower(title)

    if "roadshow" in q and "roadshow" in title_lower:
        best += 0.05
    if "kiosk" in q and "kiosk" in title_lower:
        best += 0.05
    if "opening" in q and "opening" in title_lower:
        best += 0.05
    if "closing" in q and "closing" in title_lower:
        best += 0.05
    if "aeon" in q and "aeon" in title_lower:
        best += 0.05
    if "spring" in q and "spring" in title_lower:
        best += 0.03
    if any(x in q for x in ["1st day", "first day", "day 1", "day one"]) and "new bee 1st day" in title_lower:
        best += 0.12
    if any(x in q for x in ["3rd day", "third day", "day 3", "day three"]) and "new bee 3rd day" in title_lower:
        best += 0.12
    if "onboarding" in q and "onboarding" in title_lower:
        best += 0.10
    if "new bee" in q and "new bee" in title_lower:
        best += 0.10

    return min(best, 1.0)


def match_titles(question: str) -> list[tuple[str, float]]:
    scored = []

    for title in KNOWN_TITLES:
        score = score_title_match(question, title)
        if score >= 0.60:
            scored.append((title, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


# =========================================================
# STEP BUILDERS
# =========================================================
def build_steps(df_title: pd.DataFrame) -> list[dict]:
    rows = df_title.copy()
    if "step_order" in rows.columns:
        rows = rows.sort_values(by=["step_order"], na_position="last")

    steps = []
    for _, row in rows.iterrows():
        content = safe_str(row.get("content"))
        if not content:
            continue

        raw_step = row.get("step_order")
        try:
            step_number = int(raw_step)
        except Exception:
            step_number = len(steps) + 1

        title = safe_str(row.get("title"))

        image_values = split_image_values(
        row.get("image_files", row.get("image_path", ""))
        )

        # Auto-detect images from static/sop_images/... also
        auto_image_values = auto_find_step_images(title, step_number)

        image_values = unique_keep_order(image_values + auto_image_values)

        image_urls = [to_static_url(x) for x in image_values if to_static_url(x)]

        print("STEP DEBUG:", title, step_number, image_urls)

        section = safe_str(row.get("section"))

        steps.append({
            "step_number": step_number,
            "section": section or None,
            "content": content,

            # Keep both names so old/new frontend can read images
            "image_urls": image_urls,
            "images": image_urls,
        })

    steps.sort(key=lambda x: x["step_number"])
    return steps


def find_step(steps: list[dict], step_number: int) -> Optional[dict]:
    for step in steps:
        if int(step.get("step_number", -1)) == step_number:
            return step
    return None


def find_steps_in_range(steps: list[dict], start_step: int, end_step: int) -> list[dict]:
    return [
        step for step in steps
        if start_step <= int(step.get("step_number", -1)) <= end_step
    ]


def filter_steps_by_section(steps: list[dict], section_name: str) -> list[dict]:
    target = normalize_lower(section_name)
    return [
        step for step in steps
        if normalize_lower(safe_str(step.get("section"))) == target
    ]


def format_full_answer(title: str, steps: list[dict]) -> str:
    if not steps:
        return f"No steps found for {title}."

    lines = [title]
    for step in steps:
        lines.append(f"Step {step['step_number']}")
        if step.get("section"):
            lines.append(f"Section: {step['section']}")
        lines.append(step["content"])
        if step.get("images"):
            for image_url in step["images"]:
                lines.append(f"Image: {image_url}")
        lines.append("")

    return "\n".join(lines).strip()


# =========================================================
# RESPONSE BUILDERS
# =========================================================
def build_response(
    response_type: str = "text",
    reply: str = "",
    title: Optional[str] = None,
    category: Optional[str] = None,
    section: Optional[str] = None,
    answer: str = "",
    steps: Optional[list[dict]] = None,
    score: float = 0.0,
    source: str = "unknown",
    fallback: bool = False,
    escalation_ready: bool = False,
    context: Optional[dict] = None,
) -> dict:
    if steps is None:
        steps = []
    if context is None:
        context = {}

    if score >= 0.90:
        confidence_label = "high"
    elif score >= 0.72:
        confidence_label = "medium"
    else:
        confidence_label = "low"

    return {
        "type": response_type,
        "reply": reply,
        "title": title,
        "category": category,
        "section": section,
        "answer": answer,
        "steps": steps,
        "score": round(float(score), 4),
        "confidence_label": confidence_label,
        "source": source,
        "fallback": fallback,
        "escalation_ready": escalation_ready,
        "context": context,
    }


def guidance_message() -> str:
    return (
        "Hi — I can help with work information.\n\n"
        "You can ask me about:\n"
        "- SOP / checklist\n"
        "- promotion\n"
        "- product knowledge\n"
        "- notice / latest update\n"
        "- training / onboarding\n\n"
        "Examples:\n"
        "- kiosk opening\n"
        "- roadshow closing\n"
        "- show all for kiosk opening\n"
        "- step 3 for kiosk opening\n"
        "- step 2 to step 5 for new bee 1st day\n"
        "- settlement section for spring roadshow closing\n"
        "- show picture for step 3\n"
        "- latest promotion\n"
        "- public holiday notice\n"
        "- golden passion honey"
    )


def reply_ask_which_sop(options: list[str]) -> str:
    lines = ["I found multiple SOPs. Which one do you need?\n"]
    for option in options:
        lines.append(f"- {option}")
    lines.append("\nYou can also ask:")
    lines.append("- show all")
    lines.append("- step 3")
    lines.append("- step 2 to step 5")
    lines.append("- stocktake section")
    lines.append("- show picture")
    return "\n".join(lines)


def reply_ask_which_topic(category: str, options: list[str]) -> str:
    lines = [f"I found these {category} topics. Which one do you need?\n"]
    for option in options:
        lines.append(f"- {option}")
    return "\n".join(lines)


def clarification_response(reply: str, count: int) -> dict:
    return build_response(
        response_type="text",
        reply=reply,
        answer=reply,
        score=0.35 if count == 1 else 0.25,
        source=f"clarification_round_{count}",
        fallback=True,
        escalation_ready=False,
        context={"unclear_count": count},
    )


def escalation_response() -> dict:
    message = "I’m still not fully sure which topic you need. Please escalate this question to team lead."
    return build_response(
        response_type="text",
        reply=message,
        answer=message,
        score=0.15,
        source="escalate_after_two_unclear_attempts",
        fallback=True,
        escalation_ready=True,
        context={"unclear_count": 2},
    )


def reply_irrelevant() -> str:
    return "This question is not related to the SOP / knowledge system. Please escalate to team lead."


# =========================================================
# INTENT FLAGS
# =========================================================
def is_greeting(question: str) -> bool:
    q = normalize_lower(question)
    return q in [normalize_lower(x) for x in GREETING_PHRASES]


def wants_help(question: str) -> bool:
    return contains_any(question, GUIDE_PHRASES)


def wants_show_all(question: str) -> bool:
    return contains_any(question, SHOW_ALL_PHRASES)


def wants_picture(question: str) -> bool:
    return contains_any(question, PICTURE_PHRASES)


def wants_next_step(question: str) -> bool:
    return contains_any(question, NEXT_STEP_PHRASES)


def is_irrelevant_question(question: str) -> bool:
    q = normalize_lower(question)

    if not q:
        return False

    if is_greeting(q) or wants_help(q):
        return False

    if contains_any(q, IRRELEVANT_ONLY_PHRASES):
        return True

    if match_titles(q):
        return False

    if detect_high_level_category(q):
        return False

    if q in {"ok", "okay", "hmm", "huh"}:
        return True

    return False


# =========================================================
# CONTEXT ANSWER
# =========================================================
def answer_from_context(question: str, context: dict) -> Optional[dict]:
    title = safe_str(context.get("title"))
    category = safe_str(context.get("category"))
    section = safe_str(context.get("section"))

    if not title:
        return None

    title_df = KNOWLEDGE_DF[KNOWLEDGE_DF["title"] == title].copy()
    if title_df.empty:
        return None

    steps = build_steps(title_df)

    requested_range = extract_step_range(question)
    if requested_range:
        start_step, end_step = requested_range
        matched_steps = find_steps_in_range(steps, start_step, end_step)
        if matched_steps:
            return build_response(
                response_type="sop",
                reply=f"Got it — here are Steps {start_step} to {end_step} for {title}.",
                title=title,
                category=category,
                answer=format_full_answer(title, matched_steps),
                steps=matched_steps,
                score=0.95,
                source="context_step_range",
                context={"title": title, "category": category, "unclear_count": 0},
            )

    requested_step = extract_step_number(question)
    if requested_step is not None:
        step = find_step(steps, requested_step)
        if step:
            return build_response(
                response_type="sop",
                reply=f"Got it — this is Step {requested_step} for {title}.",
                title=title,
                category=category,
                section=step.get("section"),
                answer=format_full_answer(title, [step]),
                steps=[step],
                score=0.96,
                source="context_step",
                context={
                    "title": title,
                    "category": category,
                    "section": step.get("section"),
                    "unclear_count": 0,
                },
            )

    if wants_show_all(question):
        return build_response(
            response_type="sop",
            reply=f"Here is the full SOP / checklist for {title}.",
            title=title,
            category=category,
            answer=format_full_answer(title, steps),
            steps=steps,
            score=0.95,
            source="context_show_all",
            context={"title": title, "category": category, "unclear_count": 0},
        )

    if wants_picture(question):
        image_steps = [s for s in steps if s.get("images")]
        if image_steps:
            return build_response(
                response_type="sop",
                reply=f"Here are the steps with pictures for {title}.",
                title=title,
                category=category,
                answer=format_full_answer(title, image_steps),
                steps=image_steps,
                score=0.95,
                source="context_picture",
                context={"title": title, "category": category, "unclear_count": 0},
            )

    available_sections = sorted(
        set([safe_str(x["section"]) for x in steps if safe_str(x.get("section"))])
    )
    selected_section = detect_section(question, available_sections)
    if selected_section:
        section_steps = filter_steps_by_section(steps, selected_section)
        if section_steps:
            return build_response(
                response_type="sop",
                reply=f"Here is the {selected_section} section for {title}.",
                title=title,
                category=category,
                section=selected_section,
                answer=format_full_answer(title, section_steps),
                steps=section_steps,
                score=0.95,
                source="context_section",
                context={
                    "title": title,
                    "category": category,
                    "section": selected_section,
                    "unclear_count": 0,
                },
            )

    if tokenize(question):
        reply = (
            f"I’m currently helping you with {title}.\n"
            f"Tell me what you need next — for example:\n"
            f"- step 3\n"
            f"- step 2 to step 5\n"
            f"- stocktake section\n"
            f"- show picture\n"
            f"- show all\n\n"
            f"If you want another topic, just type it directly, like promotion or public holiday."
        )
        return build_response(
            response_type="text",
            reply=reply,
            title=title,
            category=category,
            answer=reply,
            score=0.78,
            source="context_guidance",
            context={"title": title, "category": category, "unclear_count": 0},
        )

    return None


# =========================================================
# CATEGORY GUIDANCE
# =========================================================
def get_titles_by_family(family: str) -> list[str]:
    return [title for title in KNOWN_TITLES if infer_family_from_title(title) == family]


def category_guidance_response(category: str) -> dict:
    options = get_titles_by_family(category)

    if category == "sop":
        reply = (
            "Sure — I can help with SOP / checklist questions.\n\n"
            "Please choose one:\n"
            + "\n".join([f"- {x}" for x in options])
            + "\n\nYou can also ask:\n"
            "- show all\n"
            "- step 3\n"
            "- step 2 to step 5\n"
            "- stocktake section\n"
            "- show picture"
        )
    elif category == "promotion":
        reply = (
            "Sure — I can help with promotion info.\n\n"
            "Please choose one:\n"
            + "\n".join([f"- {x}" for x in options])
        )
    elif category == "product":
        reply = (
            "Sure — I can help with product knowledge.\n\n"
            "Please choose one:\n"
            + "\n".join([f"- {x}" for x in options])
        )
    elif category == "notice":
        reply = (
            "Sure — I can help with notices and updates.\n\n"
            "Please choose one:\n"
            + "\n".join([f"- {x}" for x in options])
        )
    elif category == "training":
        reply = (
            "Sure — I can help with training and onboarding.\n\n"
            "Please choose one:\n"
            + "\n".join([f"- {x}" for x in options])
            + "\n\nYou can also ask:\n"
            "- 1st day\n"
            "- 3rd day\n"
            "- onboarding\n"
            "- step 2\n"
            "- step 2 to step 5"
        )
    else:
        reply = "Please tell me which topic you need."

    return build_response(
        reply=reply,
        category=category,
        answer=reply,
        score=0.92,
        source=f"generic_{category}",
        context={"category": category, "unclear_count": 0},
    )


# =========================================================
# MAIN
# =========================================================
def get_model_answer(question: str, context: Optional[dict] = None) -> dict:
    question = normalize_text(question)
    context = normalize_context(context)
    unclear_count = get_unclear_count(context)

    if not question:
        message = "Please enter a question."
        return build_response(
            reply=message,
            answer=message,
            score=0.0,
            source="empty_question",
            fallback=True,
            context={"unclear_count": unclear_count},
        )

    # Greeting / help guidance
    if is_greeting(question) or wants_help(question):
        message = (
            "Hi — I can help with SOP, checklist, promotion, product knowledge, notice, or training questions.\n\n"
            "You can ask things like:\n"
            "- kiosk opening\n"
            "- roadshow closing\n"
            "- show all for kiosk opening\n"
            "- step 2 to step 5\n"
            "- promotion\n"
            "- public holiday\n"
            "- new bee 1st day\n"
            "- golden passion honey"
        )
        return build_response(
            reply=message,
            answer=message,
            score=1.0,
            source="greeting_guidance",
            context={"unclear_count": 0},
        )

    # Topic switch handling
    if should_clear_context(question, context):
        context = {}
        unclear_count = 0

    # -----------------------------
    # 1. PRIORITIZE CONTEXT FIRST
    # -----------------------------
    if context.get("title"):
        context_answer = answer_from_context(question, context)
        if context_answer is not None:
            return context_answer

    # -----------------------------
    # 2. Detect broad category
    # -----------------------------
    high_level_category = detect_high_level_category(question)

    # -----------------------------
    # 3. Try exact / close title match
    # -----------------------------
    matched_titles = match_titles(question)
    if matched_titles:
        top_score = matched_titles[0][1]
        close_matches = [title for title, score in matched_titles if (top_score - score) <= 0.08]

        if len(close_matches) >= 2 and top_score < 0.97:
            family = infer_family_from_title(close_matches[0])
            if family == "sop":
                reply = reply_ask_which_sop(close_matches)
            else:
                reply = reply_ask_which_topic(family, close_matches)

            return build_response(
                reply=reply,
                category=family,
                answer=reply,
                score=top_score,
                source="ambiguous_title_choice",
                context={"category": family, "unclear_count": 0},
            )

        matched_title, confidence = matched_titles[0]
        title_df = KNOWLEDGE_DF[KNOWLEDGE_DF["title"] == matched_title].copy()
        category = infer_family_from_title(matched_title)
        steps = build_steps(title_df)
        available_sections = sorted(
            set([safe_str(x["section"]) for x in steps if safe_str(x.get("section"))])
        )

        # step range
        requested_range = extract_step_range(question)
        if requested_range:
            start_step, end_step = requested_range
            matched_steps = find_steps_in_range(steps, start_step, end_step)
            if matched_steps:
                return build_response(
                    response_type="sop",
                    reply=f"Got it — here are Steps {start_step} to {end_step} for {matched_title}.",
                    title=matched_title,
                    category=category,
                    answer=format_full_answer(matched_title, matched_steps),
                    steps=matched_steps,
                    score=confidence,
                    source="matched_title_step_range",
                    context={"title": matched_title, "category": category, "unclear_count": 0},
                )

        # single step
        requested_step = extract_step_number(question)
        if requested_step is not None:
            step = find_step(steps, requested_step)
            if step:
                return build_response(
                    response_type="sop",
                    reply=f"Got it — this is Step {requested_step} for {matched_title}.",
                    title=matched_title,
                    category=category,
                    section=step.get("section"),
                    answer=format_full_answer(matched_title, [step]),
                    steps=[step],
                    score=confidence,
                    source="matched_title_step",
                    context={
                        "title": matched_title,
                        "category": category,
                        "section": step.get("section"),
                        "unclear_count": 0,
                    },
                )

        # section
        selected_section = detect_section(question, available_sections)
        if selected_section:
            section_steps = filter_steps_by_section(steps, selected_section)
            if section_steps:
                return build_response(
                    response_type="sop",
                    reply=f"Here is the {selected_section} section for {matched_title}.",
                    title=matched_title,
                    category=category,
                    section=selected_section,
                    answer=format_full_answer(matched_title, section_steps),
                    steps=section_steps,
                    score=confidence,
                    source="matched_title_section",
                    context={
                        "title": matched_title,
                        "category": category,
                        "section": selected_section,
                        "unclear_count": 0,
                    },
                )

        # picture
        if wants_picture(question):
            image_steps = [s for s in steps if s.get("images")]
            if image_steps:
                return build_response(
                    response_type="sop",
                    reply=f"Here are the steps with pictures for {matched_title}.",
                    title=matched_title,
                    category=category,
                    answer=format_full_answer(matched_title, image_steps),
                    steps=image_steps,
                    score=confidence,
                    source="matched_title_picture",
                    context={"title": matched_title, "category": category, "unclear_count": 0},
                )

        # show all
        if wants_show_all(question):
            return build_response(
                response_type="sop",
                reply=f"Here is the full SOP / checklist for {matched_title}.",
                title=matched_title,
                category=category,
                answer=format_full_answer(matched_title, steps),
                steps=steps,
                score=confidence,
                source="matched_title_show_all",
                context={"title": matched_title, "category": category, "unclear_count": 0},
            )

        # text-based categories
        if category in {"promotion", "product", "notice"}:
            content_lines = [safe_str(x) for x in title_df["content"].tolist() if safe_str(x)]
            summary = "\n".join(content_lines[:8]).strip() or f"I found {matched_title}."
            return build_response(
                reply=f"Sure — here’s the information for {matched_title}.",
                title=matched_title,
                category=category,
                answer=summary,
                score=confidence,
                source="matched_text_topic",
                context={"title": matched_title, "category": category, "unclear_count": 0},
            )

        # SOP / training guidance
        if category in {"sop", "training"}:
            section_text = f" Available sections: {', '.join(available_sections)}." if available_sections else ""
            reply = (
                f"I found {matched_title}.{section_text}\n\n"
                f"You can ask:\n"
                f"- step 3\n"
                f"- step 2 to step 5\n"
                f"- show picture\n"
                f"- show all"
            )
            return build_response(
                reply=reply,
                title=matched_title,
                category=category,
                answer=reply,
                score=confidence,
                source="matched_title_guidance",
                context={"title": matched_title, "category": category, "unclear_count": 0},
            )

    # -----------------------------
    # 4. Broad category guidance
    # -----------------------------
    if high_level_category:
        broad_words = {
            "sop",
            "promotion",
            "promo",
            "product",
            "product knowledge",
            "sales guidance",
            "notice",
            "latest update",
            "training",
            "onboarding",
            "new bee",
            "1st day",
            "first day",
            "day 1",
            "3rd day",
            "third day",
            "day 3",
        }

        if normalize_lower(question) in broad_words:
            return category_guidance_response(high_level_category)

        if high_level_category != "sop":
            return category_guidance_response(high_level_category)

        # SOP but still too broad
        sop_titles = sorted([title for title, cat in TITLE_TO_CATEGORY.items() if cat == "sop"])
        reply = (
            "Sure — I can help with SOP / checklist questions.\n\n"
            "Please choose one:\n- " + "\n- ".join(sop_titles)
        )
        return build_response(
            reply=reply,
            category="sop",
            answer=reply,
            score=0.82,
        )

    # -----------------------------
    # 5. Irrelevant question
    # -----------------------------
    if is_irrelevant_question(question):
        message = "This question is not related to the SOP or knowledge system. Please check with your team lead."
        return build_response(
            reply=message,
            answer=message,
            score=0.25,
            source="irrelevant_question",
            fallback=True,
            escalation_ready=True,
            context={"unclear_count": unclear_count},
        )

        # -----------------------------
    # 6. Clarify once, then escalate on second unclear attempt
    # -----------------------------
    unclear_count += 1

    if unclear_count == 1:
        message = (
            "I’m not fully sure which topic you want yet.\n\n"
            "Please choose one area:\n"
            "- SOP / checklist\n"
            "- Promotion\n"
            "- Product knowledge\n"
            "- Notice / latest update\n"
            "- Training / onboarding\n\n"
            "Examples:\n"
            "- kiosk opening\n"
            "- roadshow closing\n"
            "- promotion\n"
            "- public holiday\n"
            "- new bee 1st day"
        )
        return clarification_response(message, unclear_count)

    return escalation_response()

    # Clarify twice, then escalate
    unclear_count += 1

    if unclear_count == 1:
        message = (
            "I’m not fully sure which topic you want yet.\n\n"
            "Please choose one area:\n"
            "- SOP / checklist\n"
            "- Promotion\n"
            "- Product knowledge\n"
            "- Notice / latest update\n"
            "- Training / onboarding\n\n"
            "Examples:\n"
            "- kiosk opening\n"
            "- roadshow closing\n"
            "- promotion\n"
            "- public holiday notice\n"
            "- new bee 1st day"
        )
        return clarification_response(message, unclear_count)

    if unclear_count == 2:
        message = (
            "I’m still not fully sure which topic you need.\n\n"
            "Please type one of these more specifically:\n"
            "- JHKC Kiosk Opening\n"
            "- Kiosk Closing Check List\n"
            "- Spring Roadshow Opening List\n"
            "- Spring Roadshow Closing List\n"
            "- Promotion\n"
            "- Golden Passion Honey\n"
            "- PUBLIC HOLIDAY 2026\n"
            "- New Bee 1st day Check List\n"
            "- New Bee 3rd day Check List\n"
            "- Wanna-Bee onboarding Check list"
        )
        return clarification_response(message, unclear_count)

    return escalation_response()