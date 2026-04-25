import re
from typing import Dict, List


# =========================
# BASIC HELPERS
# =========================

def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    output = []
    for item in items:
        key = normalize_text(item)
        if key and key not in seen:
            seen.add(key)
            output.append(item)
    return output


# =========================
# MASTER TITLE LIST
# =========================

ALL_WIKI_TITLES = [
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
    "Win the Heart Gift Guide",
    "Promotion",
    "Lab Report in Website - temporarily removed",
    "Golden Passion Honey (New Product)",
    "How shifts arrangements are given",
    "Bee Point Policy – Crew Member Guideline",
    "Hari Raya Aidilfitri Public Holiday – Retail (2026)",
    "Hari Raya Aidilfitri – Dress Code",
    "Kuching incentive data submission",
    "PUBLIC HOLIDAY 2026",
    "Do not open raw honey tester without permission.",
    "Purple lavender out of stock",
    "Free wooden stirrer",
    "Mask and Badge",
    "Proper way to stack HDPC",
    "Price for new packaging for HWJ and SHVP",
    "Customer signature for card payment",
    "Eating inside the store is strictly prohibited",
    "Emergency Guide – Responding to Danger or Harassment",
    "Fake Jungle House",
    "Bee Points: Redeem Only When Needed",
    "Bee Green 15",
    "OT Submission Reminder",
    "Do not Block The Chiller",
    "Place Tissue on Cold drinks",
    "Can not use KB/QB IDs to check customer history",
    "What is the best answer for client asking how much Honey we are using for our honey Juice?",
    "Hygiene Compliance Notice – Juice Making (Effective Immediately)",
    "Cashless",
    "Morning Shift Attendance Responsibility & Penalty Notice",
    "New Bee 3rd day Check List",
    "New Bee 1st day Check List",
    "Wanna-Bee onboarding Check list",
]


# =========================
# TITLE GROUPS
# =========================

SOP_TITLES = [
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
]

PROMOTION_TITLES = [
    "Promotion",
    "Win the Heart Gift Guide",
    "Bee Green 15",
]

PRODUCT_TITLES = [
    "Golden Passion Honey (New Product)",
    "Price for new packaging for HWJ and SHVP",
    "Purple lavender out of stock",
    "Free wooden stirrer",
    "What is the best answer for client asking how much Honey we are using for our honey Juice?",
]

NOTICE_TITLES = [
    "Lab Report in Website - temporarily removed",
    "How shifts arrangements are given",
    "Bee Point Policy – Crew Member Guideline",
    "Hari Raya Aidilfitri Public Holiday – Retail (2026)",
    "Hari Raya Aidilfitri – Dress Code",
    "Kuching incentive data submission",
    "PUBLIC HOLIDAY 2026",
    "Do not open raw honey tester without permission.",
    "Mask and Badge",
    "Proper way to stack HDPC",
    "Customer signature for card payment",
    "Eating inside the store is strictly prohibited",
    "Emergency Guide – Responding to Danger or Harassment",
    "Fake Jungle House",
    "Bee Points: Redeem Only When Needed",
    "OT Submission Reminder",
    "Do not Block The Chiller",
    "Place Tissue on Cold drinks",
    "Can not use KB/QB IDs to check customer history",
    "Hygiene Compliance Notice – Juice Making (Effective Immediately)",
    "Cashless",
    "Morning Shift Attendance Responsibility & Penalty Notice",
]

TRAINING_TITLES = [
    "New Bee 3rd day Check List",
    "New Bee 1st day Check List",
    "Wanna-Bee onboarding Check list",
]

CATEGORY_TITLE_MAP: Dict[str, List[str]] = {
    "sop": SOP_TITLES,
    "promotion": PROMOTION_TITLES,
    "product": PRODUCT_TITLES,
    "notice": NOTICE_TITLES,
    "training": TRAINING_TITLES,
}

TITLE_TO_CATEGORY: Dict[str, str] = {}
for category_name, title_list in CATEGORY_TITLE_MAP.items():
    for title in title_list:
        TITLE_TO_CATEGORY[title] = category_name


# =========================
# TITLE ALIASES / SYNONYMS
# =========================

TITLE_ALIASES: Dict[str, List[str]] = {
    "Aeon Roadshow Closing List": [
        "aeon roadshow closing",
        "aeon closing",
        "aeon close",
        "aeon roadshow close",
        "roadshow closing aeon",
    ],
    "Aeon Roadshow Opening List": [
        "aeon roadshow opening",
        "aeon opening",
        "aeon open",
        "aeon roadshow open",
        "roadshow opening aeon",
    ],
    "Backend Opening Checklist": [
        "backend opening",
        "backend open",
        "backend checklist",
        "backend opening checklist",
    ],
    "Closing Spring Warehouse": [
        "warehouse closing",
        "closing warehouse",
        "spring warehouse closing",
        "closing spring warehouse",
    ],
    "Ice Bin Daily Closing Checklist": [
        "ice bin",
        "ice bin closing",
        "ice bin daily closing",
        "ice bin checklist",
        "ice ben closing",
    ],
    "JHKC Kiosk Opening": [
        "jhkc kiosk opening",
        "kiosk opening",
        "jhkc opening",
        "spring kiosk opening",
        "kiosk open",
        "open kiosk",
    ],
    "Kiosk Closing Check List": [
        "kiosk closing",
        "kiosk closing checklist",
        "kiosk close",
        "close kiosk",
        "spring kiosk closing",
    ],
    "Kuching Booth Closing dustbin check list": [
        "kuching booth closing",
        "dustbin check list",
        "dustbin checklist",
        "booth dustbin",
        "kuching booth dustbin",
    ],
    "Opening Notes": [
        "opening notes",
        "notes for opening",
        "opening reminder",
        "open notes",
    ],
    "Receipt printer preparation for opening": [
        "receipt printer",
        "printer opening",
        "receipt printer opening",
        "printer preparation",
        "receipt printer preparation",
        "recipt printer",
        "recepit printer",
    ],
    "Sales Closing Reminders Material": [
        "sales closing reminder",
        "closing reminders",
        "sales reminder",
        "closing material",
    ],
    "Shopify POS app Closing": [
        "shopify closing",
        "shopify pos closing",
        "pos app closing",
        "shopify app closing",
        "shopfy pos closing",
    ],
    "Shopify POS app Opening": [
        "shopify opening",
        "shopify pos opening",
        "pos app opening",
        "shopify app opening",
        "shopfy pos opening",
    ],
    "Spring Roadshow Closing List": [
        "spring roadshow closing",
        "roadshow closing",
        "spring roadshow close",
        "roadshow close",
    ],
    "Spring Roadshow Opening List": [
        "spring roadshow opening",
        "roadshow opening",
        "spring roadshow open",
        "roadshow open",
    ],
    "Win the Heart Gift Guide": [
        "win the heart",
        "gift guide",
        "heart gift guide",
    ],
    "Promotion": [
        "promotion",
        "promo",
        "latest promotion",
        "current promotion",
        "promosion",
    ],
    "Lab Report in Website - temporarily removed": [
        "lab report",
        "website lab report",
        "lab report removed",
    ],
    "Golden Passion Honey (New Product)": [
        "golden passion honey",
        "new product",
        "golden passion",
        "goldn passion honey",
    ],
    "How shifts arrangements are given": [
        "shift arrangement",
        "shift arrangements",
        "how shift arrange",
        "roster arrangement",
    ],
    "Bee Point Policy – Crew Member Guideline": [
        "bee point policy",
        "bee point",
        "crew member guideline",
        "bee points policy",
        "bee piont policy",
    ],
    "Hari Raya Aidilfitri Public Holiday – Retail (2026)": [
        "hari raya public holiday",
        "aidilfitri public holiday",
        "raya public holiday",
        "retail public holiday 2026",
    ],
    "Hari Raya Aidilfitri – Dress Code": [
        "hari raya dress code",
        "aidilfitri dress code",
        "raya dress code",
        "dress code raya",
        "raya dres code",
    ],
    "Kuching incentive data submission": [
        "kuching incentive",
        "incentive submission",
        "kuching data submission",
    ],
    "PUBLIC HOLIDAY 2026": [
        "public holiday",
        "public holiday 2026",
        "holiday 2026",
    ],
    "Do not open raw honey tester without permission.": [
        "raw honey tester",
        "do not open raw honey tester",
        "tester permission",
    ],
    "Purple lavender out of stock": [
        "purple lavender",
        "lavender out of stock",
        "out of stock lavender",
    ],
    "Free wooden stirrer": [
        "wooden stirrer",
        "free stirrer",
        "free wooden stirrer",
    ],
    "Mask and Badge": [
        "mask and badge",
        "badge",
        "mask",
    ],
    "Proper way to stack HDPC": [
        "stack hdpc",
        "hdpc",
        "proper way to stack hdpc",
    ],
    "Price for new packaging for HWJ and SHVP": [
        "new packaging price",
        "packaging price",
        "hwj shvp price",
        "price for packaging",
    ],
    "Customer signature for card payment": [
        "customer signature",
        "card payment signature",
        "signature for card payment",
    ],
    "Eating inside the store is strictly prohibited": [
        "eating inside store",
        "cannot eat inside",
        "no eating in store",
    ],
    "Emergency Guide – Responding to Danger or Harassment": [
        "emergency guide",
        "danger or harassment",
        "harassment guide",
        "responding to danger",
    ],
    "Fake Jungle House": [
        "fake jungle house",
        "fake account",
        "fake page",
        "fake shop",
    ],
    "Bee Points: Redeem Only When Needed": [
        "redeem bee points",
        "bee points redeem",
        "redeem only when needed",
    ],
    "Bee Green 15": [
        "bee green 15",
        "green 15",
    ],
    "OT Submission Reminder": [
        "ot submission",
        "overtime reminder",
        "ot reminder",
    ],
    "Do not Block The Chiller": [
        "do not block chiller",
        "block chiller",
        "chiller",
    ],
    "Place Tissue on Cold drinks": [
        "place tissue on cold drinks",
        "tissue on cold drinks",
        "cold drinks tissue",
    ],
    "Can not use KB/QB IDs to check customer history": [
        "kb qb ids",
        "customer history ids",
        "check customer history",
    ],
    "What is the best answer for client asking how much Honey we are using for our honey Juice?": [
        "how much honey we use",
        "client asking honey juice",
        "best answer for client",
        "honey juice answer",
    ],
    "Hygiene Compliance Notice – Juice Making (Effective Immediately)": [
        "hygiene compliance",
        "juice making hygiene",
        "effective immediately hygiene",
    ],
    "Cashless": [
        "cashless",
        "cashless payment",
        "no cash",
    ],
    "Morning Shift Attendance Responsibility & Penalty Notice": [
        "morning shift attendance",
        "attendance penalty",
        "attendance responsibility",
    ],
    "New Bee 3rd day Check List": [
        "new bee 3rd day",
        "new bee third day",
        "3rd day",
        "third day",
        "day 3",
        "3rd",
    ],
    "New Bee 1st day Check List": [
        "new bee 1st day",
        "new bee first day",
        "new staff first day",
        "new staff 1st day",
        "first day new staff",
        "train new staff first day",
        "staff first day checklist",
        "1st day",
        "first day",
        "day 1",
        "1st",
    ],
    "Wanna-Bee onboarding Check list": [
        "wanna-bee onboarding",
        "wannabee onboarding",
        "onboarding checklist",
        "onboarding",
    ],
}


# =========================
# CATEGORY KEYWORDS
# =========================

CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "sop": [
        "sop",
        "checklist",
        "check list",
        "step",
        "steps",
        "section",
        "picture",
        "image",
        "show all",
        "opening",
        "closing",
        "open",
        "close",
        "kiosk",
        "roadshow",
        "warehouse",
        "backend",
        "printer",
        "shopify",
        "ice bin",
        "dustbin",
        "notes",
    ],
    "promotion": [
        "promotion",
        "promo",
        "discount",
        "gift guide",
        "campaign",
        "bundle",
        "offer",
        "bee green",
        "win the heart",
        "bee points redeem",
    ],
    "product": [
        "product",
        "new product",
        "golden passion honey",
        "honey",
        "packaging",
        "lavender",
        "stirrer",
        "price",
    ],
    "notice": [
        "notice",
        "latest update",
        "announcement",
        "policy",
        "guideline",
        "public holiday",
        "holiday",
        "dress code",
        "attendance",
        "penalty",
        "ot",
        "cashless",
        "danger",
        "harassment",
        "fake",
        "badge",
        "mask",
        "chiller",
        "customer history",
        "signature",
        "hygiene",
    ],
    "training": [
        "training",
        "onboarding",
        "new bee",
        "wanna-bee",
        "wannabee",
        "1st day",
        "first day",
        "day 1",
        "3rd day",
        "third day",
        "day 3",
    ],
}


# =========================
# GREETING / HELP / ESCALATION
# =========================

GREETING_PHRASES = [
    "hi",
    "hello",
    "hey",
    "hii",
    "helo",
    "morning",
    "good morning",
    "good afternoon",
    "good evening",
]

HELP_PHRASES = [
    "help",
    "help me",
    "help again",
    "i need help",
    "i need help again",
    "what can you do",
    "how to ask",
    "how should i ask",
    "guide me",
    "i dont know what to ask",
    "not sure what to ask",
    "can you help me",
    "not sure",
    "still not sure",
    "dont know",
    "don't know",
    "i dont know",
    "i don't know",
    "still dont know",
    "still don't know",
    "i still dont understand",
    "i still don't understand",
]

TOPIC_SWITCH_PHRASES = [
    "not this",
    "wrong",
    "wrong one",
    "other one",
    "another one",
    "actually i want",
    "sorry actually",
    "change topic",
    "switch topic",
    "instead",
    "different one",
]

IRRELEVANT_PHRASES = [
    "babi",
    "stupid",
    "joke",
    "movie",
    "game",
    "relationship",
    "dating",
    "love",
    "sing a song",
]

ESCALATION_PHRASES = [
    "team lead",
    "escalate",
    "not helpful",
    "still wrong",
]


# =========================
# STEP / IMAGE / SHOW ALL PHRASES
# =========================

SHOW_ALL_PHRASES = [
    "show all",
    "all step",
    "all steps",
    "full sop",
    "full checklist",
    "show full",
    "show everything",
]

PICTURE_PHRASES = [
    "picture",
    "pictures",
    "photo",
    "photos",
    "image",
    "images",
    "show picture",
    "show photo",
]

NEXT_STEP_PHRASES = [
    "what should i do next",
    "what next",
    "next step",
    "after this what should i do",
    "after this what next",
    "then what",
]


# =========================
# TRAINING EXAMPLES
# =========================

TRAINING_EXAMPLES = [
    {"text": "kiosk opening", "label": "sop"},
    {"text": "show me spring roadshow opening", "label": "sop"},
    {"text": "roadshow closing", "label": "sop"},
    {"text": "backend opening checklist", "label": "sop"},
    {"text": "show all step for opening notes", "label": "sop"},
    {"text": "receipt printer opening", "label": "sop"},
    {"text": "shopify pos app closing", "label": "sop"},
    {"text": "ice bin closing", "label": "sop"},
    {"text": "step 3 for kiosk opening", "label": "sop"},
    {"text": "step 2 to step 5 for new bee 1st day", "label": "training"},
    {"text": "new bee", "label": "training"},
    {"text": "1st day checklist", "label": "training"},
    {"text": "first day checklist", "label": "training"},
    {"text": "day 1 checklist", "label": "training"},
    {"text": "3rd day checklist", "label": "training"},
    {"text": "third day checklist", "label": "training"},
    {"text": "day 3 checklist", "label": "training"},
    {"text": "onboarding checklist", "label": "training"},
    {"text": "promotion", "label": "promotion"},
    {"text": "latest promotion", "label": "promotion"},
    {"text": "gift guide", "label": "promotion"},
    {"text": "bee green 15", "label": "promotion"},
    {"text": "product knowledge", "label": "product"},
    {"text": "golden passion honey", "label": "product"},
    {"text": "new product", "label": "product"},
    {"text": "lavender out of stock", "label": "product"},
    {"text": "public holiday", "label": "notice"},
    {"text": "dress code", "label": "notice"},
    {"text": "ot reminder", "label": "notice"},
    {"text": "cashless", "label": "notice"},
    {"text": "mask and badge", "label": "notice"},
]


# =========================
# API FUNCTIONS
# =========================

def get_titles_by_category(category: str) -> List[str]:
    return CATEGORY_TITLE_MAP.get(normalize_text(category), [])


def get_title_aliases() -> Dict[str, List[str]]:
    return TITLE_ALIASES


def get_category_keywords() -> Dict[str, List[str]]:
    return CATEGORY_KEYWORDS


def get_greeting_phrases() -> List[str]:
    return GREETING_PHRASES


def get_help_phrases() -> List[str]:
    return HELP_PHRASES


def get_topic_switch_phrases() -> List[str]:
    return TOPIC_SWITCH_PHRASES


def get_irrelevant_phrases() -> List[str]:
    return IRRELEVANT_PHRASES


def get_escalation_phrases() -> List[str]:
    return ESCALATION_PHRASES


def get_show_all_phrases() -> List[str]:
    return SHOW_ALL_PHRASES


def get_picture_phrases() -> List[str]:
    return PICTURE_PHRASES


def get_next_step_phrases() -> List[str]:
    return NEXT_STEP_PHRASES


def get_training_examples() -> List[Dict[str, str]]:
    return TRAINING_EXAMPLES


def get_all_titles() -> List[str]:
    return ALL_WIKI_TITLES


def get_title_to_category() -> Dict[str, str]:
    return TITLE_TO_CATEGORY


def infer_category_from_title(title: str) -> str:
    normalized = normalize_text(title)

    for category, titles in CATEGORY_TITLE_MAP.items():
        for item in titles:
            if normalize_text(item) == normalized:
                return category

    return "sop"


def build_title_search_phrases(title: str) -> List[str]:
    phrases = [title]
    phrases.extend(TITLE_ALIASES.get(title, []))
    return unique_keep_order(phrases)


def get_all_search_phrases() -> Dict[str, List[str]]:
    return {
        title: build_title_search_phrases(title)
        for title in ALL_WIKI_TITLES
    }