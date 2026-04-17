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
    if "step_order" not in df.columns:
        df["step_order"] = None

    df["category"] = df["category"].apply(safe_str)
    df["title"] = df["title"].apply(safe_str)
    df["content"] = df["content"].apply(safe_str)
    df["section"] = df["section"].apply(safe_str)
    df["step_order"] = pd.to_numeric(df["step_order"], errors="coerce")

    df = df[(df["title"] != "") & (df["content"] != "")]
    return df.reset_index(drop=True)


def build_title_questions(title: str) -> list[str]:
    t = slug_text(title)

    base = [
        title,
        f"{title} sop",
        f"show me {title}",
        f"show {title}",
        f"what is {title}",
        f"how to do {title}",
        f"i need {title}",
        f"give me {title}",
        f"{title} steps",
        f"{title} checklist",
        f"{title} procedure",
        f"{title} full sop",
        f"{title} full steps",
        f"show all for {title}",
    ]

    extra_map = {
        "aeon roadshow closing list": [
            "aeon roadshow closing",
            "aeon closing roadshow",
            "closing aeon roadshow",
        ],
        "aeon roadshow opening list": [
            "aeon roadshow opening",
            "aeon opening roadshow",
            "opening aeon roadshow",
            "roadshow opening aeon",
        ],
        "backend opening checklist": [
            "backend opening",
            "opening backend",
            "backend checklist",
            "open backend",
        ],
        "closing spring warehouse": [
            "closing spring warehouse",
            "spring warehouse closing",
            "warehouse closing",
            "close spring warehouse",
        ],
        "ice bin daily closing checklist": [
            "ice bin daily closing checklist",
            "ice bin closing",
            "daily closing ice bin",
            "close ice bin",
        ],
        "jhkc kiosk opening": [
            "opening sop",
            "kiosk opening",
            "jhkc opening",
            "jhkc kiosk opening",
            "open kiosk",
            "how to open kiosk",
        ],
        "kiosk closing checklist": [
            "kiosk closing checklist",
            "kiosk closing",
            "closing kiosk",
            "close kiosk",
        ],
        "kuching booth closing dustbin check list": [
            "kuching booth closing",
            "dustbin check list",
            "booth closing dustbin",
            "dustbin checklist",
        ],
        "opening notes": [
            "opening notes",
            "open notes",
            "notes for opening",
        ],
        "receipt printer preparation for opening": [
            "receipt printer opening",
            "printer preparation for opening",
            "prepare receipt printer",
            "receipt printer prepare",
        ],
        "shopify pos app closing": [
            "shopify pos app closing",
            "shopify pos closing",
            "shopify closing",
            "close shopify pos",
        ],
        "shopify pos app opening": [
            "shopify pos app opening",
            "shopify pos opening",
            "shopify opening",
            "open shopify pos",
        ],
        "spring roadshow closing list": [
            "spring roadshow closing",
            "closing spring roadshow",
            "roadshow closing spring",
        ],
        "spring roadshow opening list": [
            "spring roadshow opening",
            "opening spring roadshow",
            "roadshow opening spring",
        ],
    }

    questions = base + extra_map.get(t, [])
    return list(dict.fromkeys(normalize_text(q) for q in questions if normalize_text(q)))


def build_section_questions(title: str, section: str) -> list[str]:
    t = slug_text(title)
    s = slug_text(section)

    if not s:
        return []

    return list(dict.fromkeys([
        f"{section}",
        f"{title} {section}",
        f"{section} section",
        f"show {section}",
        f"show me {section}",
        f"show {section} for {title}",
        f"{section} steps",
        f"{section} checklist",
        f"how to do {section}",
        f"{title} {section} steps",
        f"{title} {section} checklist",
        f"{title} section {section}",
        f"{t} {s}",
    ]))


def build_step_questions(title: str, step_order: int) -> list[str]:
    return list(dict.fromkeys([
        f"{title} step {step_order}",
        f"step {step_order} {title}",
        f"show step {step_order} for {title}",
        f"what is step {step_order} for {title}",
        f"picture for step {step_order} in {title}",
        f"image for step {step_order} in {title}",
    ]))


def build_followup_questions(title: str) -> list[str]:
    return list(dict.fromkeys([
        f"show all for {title}",
        f"full sop for {title}",
        f"all steps for {title}",
        f"picture for {title}",
        f"show image for {title}",
        f"what next for {title}",
        f"next step for {title}",
        f"sorry actually i want {title}",
        f"change to {title}",
        f"switch to {title}",
    ]))


def build_rows(df: pd.DataFrame) -> list[dict]:
    rows = []

    unique_titles = sorted(df["title"].dropna().unique().tolist())

    for title in unique_titles:
        for question in build_title_questions(title):
            rows.append({"question": question, "label": title})

        for question in build_followup_questions(title):
            rows.append({"question": question, "label": title})

    title_section_pairs = (
        df[["title", "section"]]
        .drop_duplicates()
        .fillna("")
        .values
        .tolist()
    )

    for title, section in title_section_pairs:
        if not section:
            continue
        for question in build_section_questions(title, section):
            rows.append({"question": question, "label": title})

    step_pairs = (
        df[["title", "step_order"]]
        .dropna(subset=["step_order"])
        .drop_duplicates()
        .values
        .tolist()
    )

    for title, step_order in step_pairs:
        step_order = int(step_order)
        for question in build_step_questions(title, step_order):
            rows.append({"question": question, "label": title})

    # broad ambiguity training
    ambiguity_rows = [
        {"question": "opening", "label": "JHKC Kiosk Opening"},
        {"question": "closing", "label": "Kiosk Closing Checklist"},
        {"question": "roadshow opening", "label": "Spring Roadshow Opening List"},
        {"question": "roadshow closing", "label": "Spring Roadshow Closing List"},
        {"question": "aeon opening", "label": "Aeon Roadshow Opening List"},
        {"question": "aeon closing", "label": "Aeon Roadshow Closing List"},
    ]
    rows.extend(ambiguity_rows)

    return rows


def main():
    df = load_knowledge()
    rows = build_rows(df)

    out_df = pd.DataFrame(rows).drop_duplicates().reset_index(drop=True)
    out_df.to_csv(OUTPUT_FILE, index=False)

    print("=" * 70)
    print("Training intent data generated")
    print(f"Rows   : {len(out_df)}")
    print(f"Output : {OUTPUT_FILE}")
    print("=" * 70)


if __name__ == "__main__":
    main()