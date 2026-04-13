from pathlib import Path
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR.parent / "data" / "cleaned_knowledge.csv"

df = pd.read_csv(DATA_FILE)

df["combined"] = (
    df["title"].fillna("") + " " +
    df["content"].fillna("") + " " +
    df["keywords"].fillna("")
)

vectorizer = TfidfVectorizer()
X = vectorizer.fit_transform(df["combined"])

def get_answer(question):
    q_vec = vectorizer.transform([question])
    sim = cosine_similarity(q_vec, X)
    idx = sim.argmax()
    score = sim[0][idx]

    if score < 0.2:
        return {
            "category": None,
            "title": None,
            "answer": "No confident answer. Escalate to team lead.",
            "score": float(score)
        }

    return {
        "category": df.iloc[idx]["category"],
        "title": df.iloc[idx]["title"],
        "answer": df.iloc[idx]["content"],
        "score": float(score)
    }

if __name__ == "__main__":
    q = input("Ask: ")
    print(get_answer(q))