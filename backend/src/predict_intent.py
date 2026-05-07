from __future__ import annotations


import re
from difflib import SequenceMatcher
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

def is_keyboard_or_nonsense_input(text: str) -> bool:
    q = normalize_text(text).lower()

    if not q:
        return False

    safe_short = {"hi", "hello", "hey", "ok", "okay", "thanks", "thank you"}
    if q in safe_short:
        return False

    valid_keywords = {
        "kiosk", "opening", "closing", "sop", "checklist", "roadshow", "shopify",
        "printer", "promotion", "promo", "product", "honey", "holiday", "policy",
        "notice", "training", "onboarding", "bee", "golden", "passion", "cashless",
        "chiller", "badge", "mask", "step", "picture", "image", "show", "all",
        "public", "staff", "customer", "receipt", "price", "packaging"
    }

    if any(keyword in q for keyword in valid_keywords):
        return False

    if not re.search(r"[a-z]", q):
        return True

    keyboard_patterns = [
        "asdf", "sdfg", "dfgh", "fghj", "qwer", "wert", "erty",
        "rtyu", "tyui", "yuio", "zxcv", "xcvb", "cvbn"
    ]
    if any(pattern in q for pattern in keyboard_patterns):
        return True

    words = re.findall(r"[a-z]+", q)
    if len(words) == 1 and len(words[0]) >= 5:
        letters = re.findall(r"[a-z]", words[0])
        vowels = re.findall(r"[aeiou]", words[0])
        if not any(keyword in words[0] for keyword in valid_keywords):
            if len(vowels) / max(len(letters), 1) < 0.35:
                return True
            return True

    return False


COMMON_TYPO_MAP = {
    "opning": "opening",
    "openning": "opening",
    "kios": "kiosk",
    "clsoing": "closing",
    "closng": "closing",
    "shopfy": "shopify",
    "shopif": "shopify",
    "recipt": "receipt",
    "recepit": "receipt",
    "ben": "bin",
    "goldn": "golden",
    "promosion": "promotion",
    "promotoin": "promotion",
    "piont": "point",
    "dres": "dress",
    "adress": "dress",
    "opn": "open",
    "oppen": "open",
    "merchent": "merchant",
    "merchan": "merchant",
    "glovs": "gloves",
    "checklst": "checklist",
    "cheklist": "checklist",
    "roadshw": "roadshow",
}


def fix_common_typos(text: str) -> str:
    text = normalize_text(text).lower()
    tokens = re.findall(r"[a-z0-9']+|[^a-z0-9']+", text)
    fixed_tokens = []
    for token in tokens:
        fixed_tokens.append(COMMON_TYPO_MAP.get(token, token))
    return "".join(fixed_tokens)


def normalize_lower(text: str) -> str:
    return fix_common_typos(text)


def tokenize(text: str) -> list[str]:
    q = normalize_lower(text)
    q = re.sub(r"[^a-z0-9\s]", " ", q)
    return [x for x in q.split() if x]


def meaningful_tokens(text: str) -> list[str]:
    stop_words = {
        "a", "an", "the", "i", "me", "my", "you", "your", "we", "our",
        "what", "which", "who", "when", "where", "why", "how", "do", "does",
        "did", "can", "could", "should", "would", "is", "are", "am", "be",
        "to", "for", "of", "in", "on", "at", "it", "this", "that", "all",
        "show", "give", "tell", "have", "has", "with", "about", "information",
        "info", "guide", "guidance", "answer", "explain", "list", "me",
    }
    return [
        token for token in tokenize(text)
        if token not in stop_words and len(token) >= 4
    ]


def is_generic_category_question(question: str) -> bool:
    q = normalize_lower(question)

    generic_patterns = [
        "show me all sop",
        "show all sop",
        "what sop do you have",
        "what sops do you have",
        "show me sop",
        "show sop",
        "sop list",
        "show me product knowledge",
        "what product information can you answer",
        "what product info can you answer",
        "show me sales information",
        "what sales guide do you have",
        "show me training checklist",
        "what onboarding checklist do you have",
        "show me public holiday information",
        "what policy can you explain",
    ]

    if any(pattern in q for pattern in generic_patterns):
        return True

    if q in {"sop", "sops", "product knowledge", "sales information", "sales guide", "training checklist", "onboarding checklist", "public holiday information", "policy"}:
        return True

    return False


def is_unclear_operational_question(question: str) -> bool:
    q = normalize_lower(question)

    # Do not treat clear category-search questions as unclear.
    clear_topic_words = [
        "sop", "promotion", "product", "sales", "training", "onboarding",
        "public holiday", "policy", "dress code", "bee point", "golden passion",
        "kiosk", "roadshow", "shopify", "printer", "ice bin",
    ]
    if any(word in q for word in clear_topic_words):
        return False

    unclear_patterns = [
        "i don't know what to do",
        "i dont know what to do",
        "i don't know",
        "i dont know",
        "dont know",
        "don't know",
        "not sure",
        "still not sure",
        "i am confused",
        "im confused",
        "confused",
        "i am stuck",
        "im stuck",
        "stuck",
        "what is this",
        "can you explain",
        "i have a problem",
        "something is wrong",
        "got problem",
        "system got problem",
        "the thing cannot work",
        "it still cannot work",
        "cannot work",
        "cannot use",
        "not working",
        "still not working",
        "nothing happens",
        "no result",
        "it failed",
        "failed",
        "error",
        "got error",
        "i need help with something",
        "what should i press",
        "which button",
        "where is the button",
        "where to click",
        "i cannot find it",
        "cannot find it",
        "i still don't understand",
        "i still dont understand",
        "still don't understand",
        "still dont understand",
        "what should i do",
        "what now",
        "now how",
        "then",
        "after this",
        "help again",
    ]

    return any(pattern in q for pattern in unclear_patterns)

def detect_confusion_type(question: str) -> str | None:
    q = normalize_lower(question)

    system_patterns = [
        "cannot login",
        "cant login",
        "can't login",
        "login problem",
        "cannot register",
        "cannot submit",
        "cannot upload",
        "cannot print",
        "cannot scan",
        "button not working",
        "page not loading",
        "screen stuck",
        "nothing happens",
        "no result",
        "error message",
        "got error",
        "system error",
        "app problem",
        "website problem",
    ]

    unclear_patterns = [
        "help",
        "help me",
        "i need help",
        "i need help with something",
        "i don't know",
        "i dont know",
        "dont know",
        "don't know",
        "i don't know what to do",
        "i dont know what to do",
        "not sure",
        "still not sure",
        "what is this",
        "can you explain",
        "i have a problem",
        "something is wrong",
        "the thing cannot work",
        "it still cannot work",
        "cannot work",
        "not working",
        "still not working",
        "i am confused",
        "im confused",
        "confused",
        "i am stuck",
        "im stuck",
        "stuck",
        "what should i press",
        "which button",
        "where is the button",
        "where to click",
        "i cannot find it",
        "cannot find it",
        "what now",
        "now how",
        "then",
        "after this",
        "still don't understand",
        "still dont understand",
    ]

    broad_topic_patterns = [
        "opening",
        "closing",
        "sop",
        "checklist",
        "check list",
        "promotion",
        "promo",
        "product",
        "training",
        "onboarding",
        "notice",
        "policy",
    ]

    # 1. System/app problem should be handled first.
    if any(pattern in q for pattern in system_patterns):
        return "system_problem"

    # 2. Single broad topic should show options.
    if q in broad_topic_patterns:
        return "broad_topic"

    # 3. If the question contains a clear topic, do not mark it as unclear.
    # Example: "help kiosk opening" should still answer kiosk opening.
    clear_topic_words = [
        "sop",
        "promotion",
        "promo",
        "product",
        "sales",
        "training",
        "onboarding",
        "public holiday",
        "policy",
        "dress code",
        "bee point",
        "golden passion",
        "kiosk",
        "roadshow",
        "shopify",
        "printer",
        "ice bin",
        "new bee",
        "opening",
        "closing",
        "packaging",
        "honey",
        "honey juice",
        "chiller",
        "cashless",
        "ot",
        "overtime",
        "attendance",
        "mask",
        "badge",
        "customer signature",
        "card payment",
        "fake jungle house",
        "harassment",
        "danger",
        "tissue",
        "cold drinks",
        "kb",
        "qb",
    ]

    if any(word in q for word in clear_topic_words):
        return None

    # 4. Truly unclear/confusing question.
    if any(pattern == q or pattern in q for pattern in unclear_patterns):
        return "unclear"

    return None

def unclear_clarification_response(context: dict) -> dict:
    unclear_count = get_unclear_count(context)

    if unclear_count >= 1:
        reply = "I’m still not sure which topic you need. Please escalate this question to your team lead."

        return build_response(
            reply=reply,
            answer=reply,
            score=0.0,
            source="repeated_unclear_question",
            escalation_ready=True,
            context={"unclear_count": unclear_count + 1},
        )

    reply = (
        "I’m not sure which topic you need yet.\n\n"
        "Please choose one:\n"
        "1. SOP / checklist\n"
        "2. Promotion\n"
        "3. Product knowledge\n"
        "4. Notice / policy\n"
        "5. Training / onboarding\n"
        "Example: kiosk opening, promotion, new packaging price, or new bee 1st day."
    )

    return build_response(
        reply=reply,
        answer=reply,
        score=0.0,
        source="unclear_question_clarification",
        escalation_ready=False,
        context={"unclear_count": unclear_count + 1},
    )


def system_problem_response(context: dict) -> dict:
    unclear_count = get_unclear_count(context)

    if unclear_count >= 1:
        reply = "This still sounds unresolved. Please escalate this issue to your team lead."

        return build_response(
            reply=reply,
            answer=reply,
            score=0.0,
            source="repeated_system_problem",
            escalation_ready=True,
            context={"unclear_count": unclear_count + 1},
        )

    reply = (
        "This sounds like a system/app issue.\n\n"
        "Please tell me:\n"
        "1. Which page are you on?\n"
        "2. What button did you press?\n"
        "3. What error message do you see?\n\n"
        "Example: login page, register button, or submit button."
    )

    return build_response(
        reply=reply,
        answer=reply,
        score=0.0,
        source="system_problem_clarification",
        escalation_ready=False,
        context={"unclear_count": unclear_count + 1},
    )

def broad_topic_response(question: str, context: dict) -> dict | None:
    q = normalize_lower(question)

    if q == "opening":
        reply = (
            "Which opening SOP do you need?\n\n"
            "1. JHKC Kiosk Opening\n"
            "2. Shopify POS app Opening\n"
            "3. Spring Roadshow Opening List\n"
            "4. Aeon Roadshow Opening List\n"
            "5. Backend Opening Checklist\n"
            "6. Receipt printer preparation for opening"
        )
    elif q == "closing":
        reply = (
            "Which closing SOP do you need?\n\n"
            "1. Kiosk Closing Check List\n"
            "2. Shopify POS app Closing\n"
            "3. Ice Bin Daily Closing Checklist\n"
            "4. Closing Spring Warehouse\n"
            "5. Spring Roadshow Closing List\n"
            "6. Aeon Roadshow Closing List"
        )
    elif q in {"sop", "checklist", "check list"}:
        reply = (
            "Which SOP/checklist do you need?\n\n"
            "You can ask for:\n"
            "- kiosk opening\n"
            "- kiosk closing\n"
            "- shopify opening\n"
            "- shopify closing\n"
            "- roadshow opening\n"
            "- roadshow closing\n"
            "- receipt printer"
        )
    elif q in {"promotion", "promo"}:
        reply = (
            "Which promotion information do you need?\n\n"
            "1. Promotion\n"
            "2. Win the Heart Gift Guide\n"
            "3. Bee Green 15"
        )
    elif q == "product":
        reply = (
            "Which product information do you need?\n\n"
            "1. Golden Passion Honey\n"
            "2. New packaging price\n"
            "3. Purple lavender out of stock\n"
            "4. Free wooden stirrer\n"
            "5. Honey juice customer answer"
        )
    elif q in {"training", "onboarding"}:
        reply = (
            "Which training checklist do you need?\n\n"
            "1. New Bee 1st day Check List\n"
            "2. New Bee 3rd day Check List\n"
            "3. Wanna-Bee onboarding Check list"
        )
    elif q in {"notice", "policy"}:
        reply = (
            "Which notice or policy do you need?\n\n"
            "You can ask about:\n"
            "- bee point policy\n"
            "- public holiday\n"
            "- dress code\n"
            "- OT submission\n"
            "- cashless\n"
            "- chiller\n"
            "- attendance"
        )
    else:
        return None

    return build_response(
        reply=reply,
        answer=reply,
        score=0.85,
        source="broad_topic_clarification",
        escalation_ready=False,
        context={"unclear_count": 0},
    )


def sales_guidance_response() -> dict:
    options = [
        "Sales Closing Reminders Material",
        "What is the best answer for client asking how much Honey we are using for our honey Juice?",
        "Customer signature for card payment",
        "Cashless",
        "Bee Points: Redeem Only When Needed",
    ]
    reply = (
        "Sure — I can help with sales information.\n\n"
        "Please choose one:\n"
        + "\n".join([f"- {x}" for x in options])
    )
    return build_response(
        reply=reply,
        category="sales",
        answer=reply,
        score=0.92,
        source="generic_sales",
        context={"category": "sales", "unclear_count": 0},
    )


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
    "How shifts arrangements are given": [
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
        "merchant copy need signature",
        "merchant copy signature",
        "merchant need signature",
        "need signature for card",
        "card payment merchant copy",
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
        "fake jungle house scam",
        "fake account",
        "scam jungle house",
    ],
    "Bee Points: Redeem Only When Needed": [
        "bee points redeem only when needed",
        "redeem only when needed",
        "bee points redeem",
        "redeem bee points first or not",
        "bee points first",
        "redeem points first",
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
        "when submit ot",
        "submit ot",
        "ot submit",
    ],
    "Do not Block The Chiller": [
        "do not block the chiller",
        "do not block chiller",
        "block the chiller",
        "chiller blocked",
        "can block chiller or not",
        "cannot block chiller",
        "block chiller or not",
    ],
    "Place Tissue on Cold drinks": [
        "place tissue on cold drinks",
        "tissue on cold drinks",
        "cold drinks tissue",
        "put tissue on cold drinks",
        "put tissue cold drink",
    ],
    "Can not use KB/QB IDs to check customer history": [
        "can not use kb qb ids to check customer history",
        "kb qb ids",
        "check customer history ids",
        "kb ids",
        "qb ids",
        "use kb qb ids to check customer history",
        "customer history kb qb",
    ],
    "What is the best answer for client asking how much Honey we are using for our honey Juice?": [
        "how much honey we are using for our honey juice",
        "best answer for client honey juice",
        "honey juice answer",
        "customer ask how much honey",
        "how much honey for honey juice",
        "honey for honey juice",
    ],
    "Hygiene Compliance Notice – Juice Making (Effective Immediately)": [
        "hygiene compliance notice juice making",
        "juice making hygiene compliance",
        "hygiene compliance notice",
        "juice hygiene notice",
        "must wear gloves and mask for juice",
        "wear gloves and mask for juice",
        "gloves and mask juice",
        "juice making gloves mask",
        "mask gloves hygiene",
    ],
    "Cashless": [
        "cashless",
        "cashless payment",
        "no cash",
        "cash transaction",
        "cash transactions",
        "who can decide cash transactions",
        "cash decision",
        "accept cash",
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
        "new staff first day",
        "new staff 1st day",
        "first day new staff",
        "train new staff first day",
        "staff first day checklist",
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
    "help", "help me", "help again", "i need help", "i need help again",
    "what can you do", "guide me", "show me options", "what should i ask",
    "not sure", "still not sure", "dont know", "don't know", "i dont know",
    "i don't know", "still dont know", "still don't know", "i still dont know",
    "i still don't know", "i dont understand", "i don't understand",
    "still dont understand", "still don't understand", "i still dont understand",
    "i still don't understand", "cannot understand", "not understand",
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

    explicit_new_topic_words = {
        "product", "products", "promotion", "promo", "holiday", "public holiday",
        "notice", "policy", "training", "onboarding", "new bee", "opening",
        "closing", "sop", "checklist", "check list", "sales"
    }
    if current_title and q in explicit_new_topic_words:
        return True

    if current_title and contains_any(q, [
        "public holiday", "latest promotion", "golden passion", "new packaging",
        "bee point", "cashless", "dress code", "ot submission", "new bee"
    ]):
        return True

    # Short follow-up words should stay in current topic
    short_follow_up_words = {
        "show all", "all", "picture", "pictures", "image", "images",
        "photo", "photos", "next", "next step", "section"
    }
    if q in short_follow_up_words:
        return False

    return False




def is_context_follow_up(question: str, context: Optional[dict] = None) -> bool:
    q = normalize_lower(question)
    context = normalize_context(context or {})

    if not q or not context.get("title"):
        return False

    if (
        wants_show_all(q)
        or wants_picture(q)
        or wants_next_step(q)
        or extract_step_number(q) is not None
        or extract_step_range(q) is not None
    ):
        return True

    short_follow_ups = {
        "show all", "all", "picture", "pictures", "image", "images",
        "photo", "photos", "next", "next step", "show picture", "show image"
    }
    if q in short_follow_ups:
        return True

    title = safe_str(context.get("title"))
    title_df = KNOWLEDGE_DF[KNOWLEDGE_DF["title"] == title].copy()
    if not title_df.empty:
        steps = build_steps(title_df)
        available_sections = sorted(
            set([safe_str(x["section"]) for x in steps if safe_str(x.get("section"))])
        )
        if detect_section(q, available_sections):
            return True

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
    if "new staff" in q and any(x in q for x in ["first day", "1st day", "day 1", "day one"]) and "new bee 1st day" in title_lower:
        best = max(best, 0.88)

    # Fuzzy fallback helps testing questions with small spelling mistakes,
    # for example: opning, kios, clsoing, shopfy, recipt, promosion.
    # It must not run for broad category questions like "Show me all SOP",
    # otherwise short words such as "sop" can accidentally match "shop".
    q_meaningful_tokens = meaningful_tokens(q)
    if q_meaningful_tokens and not is_generic_category_question(q):
        for variant in title_variants(title):
            v = normalize_lower(variant)
            if not v:
                continue

            ratio = SequenceMatcher(None, q, v).ratio()
            if ratio >= 0.82:
                best = max(best, 0.84)

            v_tokens = [token for token in tokenize(v) if len(token) >= 4]
            if v_tokens:
                fuzzy_hits = 0
                for v_token in v_tokens:
                    if any(
                        SequenceMatcher(None, q_token, v_token).ratio() >= 0.86
                        for q_token in q_meaningful_tokens
                    ):
                        fuzzy_hits += 1
                fuzzy_token_score = fuzzy_hits / max(len(v_tokens), 1)
                if fuzzy_token_score >= 0.75:
                    best = max(best, 0.82)
                elif fuzzy_token_score >= 0.50 and len(q_meaningful_tokens) >= 2:
                    best = max(best, 0.72)

    return min(best, 1.0)


def match_titles(question: str) -> list[tuple[str, float]]:
    scored = []
    q = normalize_lower(question)

    for title in KNOWN_TITLES:
        score = score_title_match(question, title)
        if score >= 0.60:
            scored.append((title, score))

    # When the question clearly says opening/closing, keep the matched list aligned.
    # This prevents "kiosk closing" from tying with "JHKC Kiosk Opening".
    if any(word in q for word in ["closing", "close"]):
        closing_scored = [
            item for item in scored
            if any(word in normalize_lower(item[0]) for word in ["closing", "close"])
        ]
        if closing_scored:
            scored = closing_scored

    if any(word in q for word in ["opening", "open"]):
        opening_scored = [
            item for item in scored
            if any(word in normalize_lower(item[0]) for word in ["opening", "open"])
        ]
        if opening_scored:
            scored = opening_scored

    if "kiosk" in q:
        kiosk_scored = [item for item in scored if "kiosk" in normalize_lower(item[0])]
        if kiosk_scored:
            scored = kiosk_scored

    if "shopify" in q or "pos" in q:
        shopify_scored = [item for item in scored if "shopify" in normalize_lower(item[0]) or "pos" in normalize_lower(item[0])]
        if shopify_scored:
            scored = shopify_scored

    if "printer" in q or "receipt" in q:
        printer_scored = [item for item in scored if "printer" in normalize_lower(item[0]) or "receipt" in normalize_lower(item[0])]
        if printer_scored:
            scored = printer_scored

    if "ice bin" in q:
        ice_scored = [item for item in scored if "ice bin" in normalize_lower(item[0])]
        if ice_scored:
            scored = ice_scored

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


def build_step_out_of_range_response(title: str, category: str, steps: list[dict], source: str) -> dict:
    if steps:
        step_numbers = [int(step.get("step_number", 0) or 0) for step in steps]
        min_step = min(step_numbers)
        max_step = max(step_numbers)
        reply = (
            f"I found {title}, but that step is outside the available range.\n\n"
            f"This topic only has Step {min_step} to Step {max_step}.\n"
            f"Please ask for a valid step, for example:\n"
            f"- step {min_step}\n"
            f"- step {min(min_step + 1, max_step)} to step {min(min_step + 3, max_step)}\n"
            f"- show all"
        )
    else:
        reply = (
            f"I found {title}, but there are no numbered steps available for this topic.\n"
            f"Please ask to show all or choose another topic."
        )

    return build_response(
        response_type="text",
        reply=reply,
        title=title,
        category=category,
        answer=reply,
        steps=[],
        score=0.88,
        source=source,
        escalation_ready=False,
        context={"title": title, "category": category, "unclear_count": 0},
    )


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
        return build_step_out_of_range_response(
            title, category, steps, "context_step_range_out_of_bounds"
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
        return build_step_out_of_range_response(
            title, category, steps, "context_step_out_of_bounds"
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

    if is_keyboard_or_nonsense_input(question):
        message = (
            "I could not understand your question clearly.\n\n"
            "Please ask again using a clearer Jungle House topic, for example:\n"
            "- kiosk opening\n"
            "- kiosk closing\n"
            "- latest promotion\n"
            "- public holiday\n"
            "- new bee 1st day"
        )
        return build_response(
            reply=message,
            answer=message,
            score=0.0,
            source="invalid_input_first_attempt",
            fallback=True,
            escalation_ready=False,
            context={"unclear_count": unclear_count + 1},
        )
    
    confusion_type = detect_confusion_type(question)

    if confusion_type == "system_problem":
        return system_problem_response(context)

    if confusion_type == "broad_topic":
        broad_response = broad_topic_response(question, context)
        if broad_response:
            return broad_response

    if confusion_type == "unclear":
        return unclear_clarification_response(context)

    # Greeting should only show guidance and reset unclear count.
    if is_greeting(question):
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

    # Unclear operational questions should also count toward the 2-time escalation flow.
    if is_unclear_operational_question(question):
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

    # Help / unclear questions must count toward the 2-time escalation flow.
    if wants_help(question):
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

    # Topic switch handling
    if should_clear_context(question, context):
        context = {}
        unclear_count = 0

    # -----------------------------
    # 1. USE CONTEXT ONLY FOR REAL FOLLOW-UP REQUESTS
    # This prevents the AI from dwelling on the previous topic.
    # -----------------------------
    if context.get("title") and is_context_follow_up(question, context):
        context_answer = answer_from_context(question, context)
        if context_answer is not None:
            return context_answer

    # -----------------------------
    # 2. Detect broad category
    # -----------------------------
    high_level_category = detect_high_level_category(question)

    # -----------------------------
    # 2A. Direct category/search-list questions
    # -----------------------------
    q_lower = normalize_lower(question)

    if is_generic_category_question(question):
        if "sales" in q_lower:
            return sales_guidance_response()

        if "training checklist" in q_lower or "onboarding checklist" in q_lower:
            return category_guidance_response("training")

        if "product" in q_lower:
            return category_guidance_response("product")

        if "public holiday" in q_lower:
            matched_title = "PUBLIC HOLIDAY 2026"
            title_df = KNOWLEDGE_DF[KNOWLEDGE_DF["title"] == matched_title].copy()
            content_lines = [safe_str(x) for x in title_df["content"].tolist() if safe_str(x)]
            summary = "\n".join(content_lines[:8]).strip() or f"I found {matched_title}."
            return build_response(
                reply=f"Sure — here’s the information for {matched_title}.",
                title=matched_title,
                category="notice",
                answer=summary,
                score=0.96,
                source="generic_public_holiday",
                context={"title": matched_title, "category": "notice", "unclear_count": 0},
            )

        if "policy" in q_lower:
            return category_guidance_response("notice")

        if "sop" in q_lower:
            return category_guidance_response("sop")

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
            return build_step_out_of_range_response(
                matched_title, category, steps, "matched_title_step_range_out_of_bounds"
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
            return build_step_out_of_range_response(
                matched_title, category, steps, "matched_title_step_out_of_bounds"
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

        # SOP / training default: confirm the matched title, show all steps directly,
        # then ask whether staff need a specific step/range/section/picture.
        if category in {"sop", "training"}:
            available_sections_text = ""
            if available_sections:
                available_sections_text = (
                    "\n\nAvailable sections:\n"
                    + "\n".join([f"- {section_name}" for section_name in available_sections])
                )

            if steps:
                min_step = min([int(step.get("step_number", 0) or 0) for step in steps])
                max_step = max([int(step.get("step_number", 0) or 0) for step in steps])
                reply = (
                    f"I found {matched_title}. If this is the correct title, here are all the steps first.\n\n"
                    f"This topic has Step {min_step} to Step {max_step}.\n\n"
                    f"After reading, you can ask for a specific part, for example:\n"
                    f"- step {min_step}\n"
                    f"- step {min(min_step + 1, max_step)} to step {min(min_step + 3, max_step)}\n"
                    f"- show picture"
                    f"{available_sections_text}"
                )
                answer = reply + "\n\n" + format_full_answer(matched_title, steps)
            else:
                reply = (
                    f"I found {matched_title}. If this is the correct title, here is the available information.\n\n"
                    f"You can ask for a specific step, range, picture, or another topic."
                    f"{available_sections_text}"
                )
                answer = reply

            return build_response(
                response_type="sop" if steps else "text",
                reply=reply,
                title=matched_title,
                category=category,
                answer=answer,
                steps=steps,
                score=confidence,
                source="matched_title_show_all_first",
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
