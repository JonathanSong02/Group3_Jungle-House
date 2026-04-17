from pathlib import Path
import random
import re

import numpy as np
import pandas as pd
import torch
from torch import nn

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
MODEL_DIR = BASE_DIR.parent / "models"

TRAINING_FILE = DATA_DIR / "training_intents.csv"
MODEL_FILE = MODEL_DIR / "intent_model.pth"

EPOCHS = 300
LEARNING_RATE = 0.001
SEED = 42


def set_seed(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9']+", str(text).lower())


def build_vocab(texts: list[str]) -> dict[str, int]:
    vocab = {"<UNK>": 0}
    for text in texts:
        for token in tokenize(text):
            if token not in vocab:
                vocab[token] = len(vocab)
    return vocab


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


def load_training_data() -> pd.DataFrame:
    if not TRAINING_FILE.exists():
        raise FileNotFoundError(f"Training file not found: {TRAINING_FILE}")

    df = pd.read_csv(TRAINING_FILE)

    required = {"question", "label"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"training_intents.csv missing columns: {sorted(missing)}")

    df = df.dropna(subset=["question", "label"]).copy()
    df["question"] = df["question"].astype(str).str.strip()
    df["label"] = df["label"].astype(str).str.strip()
    df = df[(df["question"] != "") & (df["label"] != "")]
    df = df.drop_duplicates()

    if df.empty:
        raise ValueError("No valid training rows found.")

    return df.reset_index(drop=True)


def train():
    set_seed()

    df = load_training_data()
    questions = df["question"].tolist()
    labels = sorted(df["label"].unique().tolist())

    vocab = build_vocab(questions)
    label_to_index = {label: i for i, label in enumerate(labels)}

    X = torch.stack([vectorize(q, vocab) for q in questions])
    y = torch.tensor([label_to_index[label] for label in df["label"]], dtype=torch.long)

    model = IntentClassifier(input_size=len(vocab), num_classes=len(labels))
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)

    print("=" * 70)
    print("PyTorch intent training started")
    print(f"Samples     : {len(df)}")
    print(f"Classes     : {len(labels)}")
    print(f"Labels      : {labels}")
    print(f"Vocab size  : {len(vocab)}")
    print("=" * 70)

    for epoch in range(1, EPOCHS + 1):
        model.train()
        optimizer.zero_grad()

        logits = model(X)
        loss = criterion(logits, y)
        loss.backward()
        optimizer.step()

        if epoch == 1 or epoch % 20 == 0 or epoch == EPOCHS:
            with torch.no_grad():
                preds = torch.argmax(logits, dim=1)
                acc = (preds == y).float().mean().item() * 100
            print(f"Epoch {epoch:03d}/{EPOCHS} | Loss: {loss.item():.4f} | Train Acc: {acc:.2f}%")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    torch.save({
        "state_dict": model.state_dict(),
        "vocab": vocab,
        "labels": labels,
        "input_size": len(vocab),
        "num_classes": len(labels),
    }, MODEL_FILE)

    print("=" * 70)
    print(f"Model saved to: {MODEL_FILE}")
    print("=" * 70)


if __name__ == "__main__":
    train()