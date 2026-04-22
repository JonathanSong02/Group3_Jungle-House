from pathlib import Path
import re

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
KNOWLEDGE_FILE = DATA_DIR / "cleaned_knowledge.csv"
OUTPUT_FILE = DATA_DIR / "training_intents.csv"


def normalize_text(text: str) -> str:
    text = str(text).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def slug_text(text: str) -> str:
    return normalize_text(text).lower()


def safe_str(value) -> str:
    if pd.isna(value):
        return ""
    return normalize_text(str(value))


def infer_family(title: str, category: str, section: str) -> str:
    t = slug_text(title)
    c = slug_text(category)
    s = slug_text(section)

    if any(word in t for word in ["opening", "closing", "checklist", "roadshow", "shopify", "warehouse", "printer", "dustbin", "kiosk", "opening notes"]):
        return "sop"
    if any(word in t for word in ["promotion", "gift guide", "promo", "win the heart", "bee green"]):
        return "promotion"
    if any(word in t for word in ["honey", "juice", "product", "tester"]):
        return "product"
    if any(word in t for word in ["policy", "notice", "guide", "penalty", "cashless", "holiday", "signature", "price", "fake", "danger", "harassment", "prohibited", "points", "attendance", "chiller", "history", "tissue"]):
        return "notice"
    if c in {"sop", "promotion", "product", "notice", "policy", "sales"}:
        return c
    if any(word in s for word in ["rule", "policy", "notice", "warning", "reminder", "memo"]):
        return "notice"
    return "general"


def title_specific_aliases(title: str) -> list[str]:
    title_key = slug_text(title)
    alias_map = {
        "jhkc kiosk opening": ["opening sop", "kiosk opening", "jhkc opening", "open kiosk", "how to open kiosk"],
        "kiosk closing check list": ["kiosk closing", "closing kiosk", "close kiosk", "kiosk closing checklist"],
        "price for new packaging for hwj and shvp": ["new packaging price", "hwj new packaging price", "shvp new packaging price", "old and new packaging price"],
        "customer signature for card payment": ["card payment signature", "merchant copy signature", "need signature for card payment"],
        "eating inside the store is strictly prohibited": ["cannot eat inside store", "eat in store prohibited", "store eating rule"],
        "emergency guide – responding to danger or harassment": ["danger or harassment guide", "what to do if danger happens", "what to do if someone harasses me", "help emergency"],
        "fake jungle house": ["jungle house scam", "scam jungle house", "fake account jungle house"],
        "bee points: redeem only when needed": ["redeem bee points", "customer want redeem point", "can redeem points first or not"],
        "bee green 15": ["sales tactic bee green 15", "when to use bee green 15", "bee green 15 bottle return"],
        "ot submission reminder": ["ot rule", "when submit ot", "late ot submission", "overtime reminder"],
        "do not block the chiller": ["chiller reminder", "can block chiller or not", "keep chiller visible"],
        "place tissue on cold drinks": ["cold drinks tissue", "put tissue on cold drinks", "protect furniture cold drinks"],
        "can not use kb/qb ids to check customer history": ["use kb qb to check customer history", "staff id check customer history", "customer history access"],
        "what is the best answer for client asking how much honey we are using for our honey juice?": ["how much honey for honey juice", "what to answer customer honey juice", "30gm honey 250gm water", "tell recipe for honey juice or not"],
        "hygiene compliance notice – juice making (effective immediately)": ["juice making hygiene rule", "must wear gloves and mask for juice", "juice making penalty", "rm200 commission penalty hygiene"],
        "cashless": ["accept cash or not", "who can decide cash transactions", "cash transaction rule"],
        "morning shift attendance responsibility & penalty notice": ["morning shift attendance memo", "attendance penalty memo", "morning shift penalty notice"],
    }
    return alias_map.get(title_key, [])


def build_title_questions(title: str, category: str, section: str) -> list[str]:
    family = infer_family(title, category, section)

    questions = [
        title,
        f"show me {title}",
        f"show {title}",
        f"what is {title}",
        f"explain {title}",
        f"i need {title}",
        f"give me {title}",
        f"summarize {title}",
        f"show all for {title}",
    ]

    if family == "sop":
        questions.extend([
            f"{title} sop",
            f"{title} steps",
            f"{title} checklist",
            f"{title} full steps",
            f"step by step for {title}",
            f"full checklist for {title}",
        ])
    elif family == "promotion":
        questions.extend([
            f"promotion for {title}",
            f"show promo details for {title}",
            f"discount for {title}",
            f"sales tactic for {title}",
        ])
    elif family == "product":
        questions.extend([
            f"product details for {title}",
            f"benefits of {title}",
            f"how to answer customer about {title}",
        ])
    else:
        questions.extend([
            f"rule for {title}",
            f"notice for {title}",
            f"what should staff know about {title}",
        ])

    if section:
        questions.extend([
            f"{title} {section}",
            f"explain {section} for {title}",
        ])

    questions.extend(title_specific_aliases(title))
    return [normalize_text(q) for q in questions if normalize_text(q)]


def build_section_questions(title: str, section: str) -> list[str]:
    if not section:
        return []

    questions = [
        section,
        f"{title} {section}",
        f"{section} section",
        f"show {section}",
        f"show {section} for {title}",
        f"{section} steps",
        f"{title} {section} steps",
        f"{title} {section} checklist",
        f"how to do {section}",
    ]
    return [normalize_text(q) for q in questions if normalize_text(q)]


def build_step_questions(title: str, step_number: int) -> list[str]:
    questions = [
        f"{title} step {step_number}",
        f"step {step_number} {title}",
        f"show step {step_number} for {title}",
        f"what is step {step_number} for {title}",
        f"picture for step {step_number} in {title}",
        f"image for step {step_number} in {title}",
    ]
    return [normalize_text(q) for q in questions if normalize_text(q)]


def build_content_questions(title: str, content: str) -> list[str]:
    content_key = slug_text(content)
    questions = []

    if "gloves" in content_key or "mask" in content_key:
        questions.extend(["juice gloves and mask rule", "must wear gloves and face mask for juice"])
    if "rm200" in content_key:
        questions.extend(["rm200 penalty hygiene", "commission penalty for hygiene"])
    if "king bee" in content_key or "bee leader" in content_key:
        questions.extend(["who can decide cash transaction", "who can accept cash"])
    if "30gm honey" in content_key or "250gm water" in content_key:
        questions.extend(["30gm honey 250gm water", "how much honey for honey juice"])
    if "merchant copy" in content_key or "signature" in content_key:
        questions.extend(["merchant copy need signature", "card payment need customer signature"])
    if "customer history" in content_key:
        questions.extend(["check customer history using kb qb ids", "customer history by staff id"])
    if "eat" in content_key and "store" in content_key:
        questions.append("can eat inside store or not")
    if "fake" in content_key or "scam" in content_key:
        questions.append("fake jungle house scam")
    if "ot" in content_key or "overtime" in content_key:
        questions.extend(["submit ot same day", "late ot submission"])
    if "chiller" in content_key:
        questions.append("do not block chiller")

    return [normalize_text(q) for q in questions if normalize_text(q)]


def load_knowledge() -> pd.DataFrame:
    if not KNOWLEDGE_FILE.exists():
        raise FileNotFoundError(f"Knowledge file not found: {KNOWLEDGE_FILE}")

    df = pd.read_csv(KNOWLEDGE_FILE)

    required = {"title", "content"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"cleaned_knowledge.csv missing columns: {sorted(missing)}")

    for column in ["category", "section"]:
        if column not in df.columns:
            df[column] = ""
    if "step_order" not in df.columns:
        df["step_order"] = None

    df["category"] = df["category"].apply(safe_str)
    df["title"] = df["title"].apply(safe_str)
    df["content"] = df["content"].apply(safe_str)
    df["section"] = df["section"].apply(safe_str)
    df["step_order"] = pd.to_numeric(df["step_order"], errors="coerce")

    df = df[(df["title"] != "") & (df["content"] != "")]
    df = df.drop_duplicates().reset_index(drop=True)
    return df


def build_rows(df: pd.DataFrame) -> list[dict]:
    rows = []

    title_meta = df[["title", "category", "section"]].drop_duplicates().values.tolist()
    for title, category, section in title_meta:
        for question in build_title_questions(title, category, section):
            rows.append({"question": question, "label": title})

        for question in [
            f"picture for {title}",
            f"show image for {title}",
            f"what next for {title}",
            f"next step for {title}",
            f"change to {title}",
        ]:
            rows.append({"question": normalize_text(question), "label": title})

    for title, section in df[["title", "section"]].drop_duplicates().values.tolist():
        for question in build_section_questions(title, section):
            rows.append({"question": question, "label": title})

    step_pairs = df[["title", "step_order"]].dropna(subset=["step_order"]).drop_duplicates().values.tolist()
    for title, step_number in step_pairs:
        for question in build_step_questions(title, int(step_number)):
            rows.append({"question": question, "label": title})

    content_pairs = df[["title", "content"]].drop_duplicates().values.tolist()
    for title, content in content_pairs:
        for question in build_content_questions(title, content):
            rows.append({"question": question, "label": title})

    rows.extend([
        {"question": "opening", "label": "JHKC Kiosk Opening"},
        {"question": "closing", "label": "Kiosk Closing Check List"},
        {"question": "roadshow opening", "label": "Spring Roadshow Opening List"},
        {"question": "roadshow closing", "label": "Spring Roadshow Closing List"},
        {"question": "aeon opening", "label": "Aeon Roadshow Opening List"},
        {"question": "aeon closing", "label": "Aeon Roadshow Closing List"},
        {"question": "cashless rule", "label": "Cashless"},
        {"question": "juice hygiene", "label": "Hygiene Compliance Notice – Juice Making (Effective Immediately)"},
        {"question": "morning shift attendance", "label": "Morning Shift Attendance Responsibility & Penalty Notice"},
    ])

    return rows


def main():
    df = load_knowledge()
    rows = build_rows(df)

    out_df = pd.DataFrame(rows).drop_duplicates().reset_index(drop=True)
    out_df.to_csv(OUTPUT_FILE, index=False)

    label_counts = out_df["label"].value_counts().sort_index().to_dict()
    print("=" * 70)
    print("Training intent data generated")
    print(f"Knowledge rows   : {len(df)}")
    print(f"Intent rows      : {len(out_df)}")
    print(f"Unique labels    : {out_df['label'].nunique()}")
    print(f"Output file      : {OUTPUT_FILE}")
    print("Label coverage   :")
    for label, count in label_counts.items():
        print(f"  - {label}: {count}")
    print("=" * 70)


if __name__ == "__main__":
    main()
