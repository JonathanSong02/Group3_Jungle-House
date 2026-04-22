from pathlib import Path
import json
import random
import re

import numpy as np
import pandas as pd
import torch
from torch import nn
from sklearn.model_selection import train_test_split

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
MODEL_DIR = BASE_DIR.parent / "models"

TRAINING_FILE = DATA_DIR / "training_intents.csv"
MODEL_FILE = MODEL_DIR / "intent_model.pth"
METRICS_FILE = MODEL_DIR / "intent_model_metrics.json"

EPOCHS = 300
LEARNING_RATE = 0.001
SEED = 42
VALID_SIZE = 0.20
EARLY_STOPPING_PATIENCE = 30


REAL_JH_BENCHMARK = [
    {"question": "opening sop", "expected": "JHKC Kiosk Opening"},
    {"question": "kiosk closing checklist", "expected": "Kiosk Closing Check List"},
    {"question": "new packaging price", "expected": "Price for new packaging for HWJ and SHVP"},
    {"question": "merchant copy need signature", "expected": "Customer signature for card payment"},
    {"question": "what to do if someone harasses me", "expected": "Emergency Guide – Responding to Danger or Harassment"},
    {"question": "fake jungle house scam", "expected": "Fake Jungle House"},
    {"question": "redeem bee points first or not", "expected": "Bee Points: Redeem Only When Needed"},
    {"question": "when submit ot", "expected": "OT Submission Reminder"},
    {"question": "can block chiller or not", "expected": "Do not Block The Chiller"},
    {"question": "put tissue on cold drinks", "expected": "Place Tissue on Cold drinks"},
    {"question": "how much honey for honey juice", "expected": "What is the best answer for client asking how much Honey we are using for our honey Juice?"},
    {"question": "must wear gloves and mask for juice", "expected": "Hygiene Compliance Notice – Juice Making (Effective Immediately)"},
    {"question": "who can decide cash transactions", "expected": "Cashless"},
]


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

    label_counts = df["label"].value_counts()
    too_small = label_counts[label_counts < 2]
    if not too_small.empty:
        raise ValueError(
            "Each label must have at least 2 rows for train/validation split. "
            f"These labels have too few rows: {too_small.to_dict()}"
        )

    return df.reset_index(drop=True)


def evaluate(model: nn.Module, X: torch.Tensor, y: torch.Tensor, criterion: nn.Module) -> tuple[float, float]:
    model.eval()
    with torch.no_grad():
        logits = model(X)
        loss = criterion(logits, y).item()
        preds = torch.argmax(logits, dim=1)
        acc = (preds == y).float().mean().item() * 100
    return loss, acc


def predict_label(model: nn.Module, vocab: dict[str, int], labels: list[str], question: str) -> tuple[str, float]:
    vec = vectorize(question, vocab).unsqueeze(0)
    with torch.no_grad():
        logits = model(vec)
        probs = torch.softmax(logits, dim=1)[0]
        pred_idx = int(torch.argmax(probs).item())
        confidence = float(probs[pred_idx].item())
    return labels[pred_idx], confidence


def run_benchmark(model: nn.Module, vocab: dict[str, int], labels: list[str]) -> dict:
    results = []
    correct = 0

    for item in REAL_JH_BENCHMARK:
        predicted, confidence = predict_label(model, vocab, labels, item["question"])
        matched = predicted == item["expected"]
        if matched:
            correct += 1
        results.append({
            "question": item["question"],
            "expected": item["expected"],
            "predicted": predicted,
            "confidence": round(confidence, 4),
            "matched": matched,
        })

    total = len(REAL_JH_BENCHMARK)
    accuracy = (correct / total) * 100 if total else 0.0
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(accuracy, 2),
        "results": results,
    }


def train():
    set_seed()

    df = load_training_data()
    questions = df["question"].tolist()
    labels = sorted(df["label"].unique().tolist())

    vocab = build_vocab(questions)
    label_to_index = {label: i for i, label in enumerate(labels)}

    X_all = torch.stack([vectorize(q, vocab) for q in questions])
    y_all = torch.tensor([label_to_index[label] for label in df["label"]], dtype=torch.long)

    train_idx, valid_idx = train_test_split(
        np.arange(len(df)),
        test_size=VALID_SIZE,
        random_state=SEED,
        stratify=df["label"],
    )

    X_train = X_all[train_idx]
    y_train = y_all[train_idx]
    X_valid = X_all[valid_idx]
    y_valid = y_all[valid_idx]

    model = IntentClassifier(input_size=len(vocab), num_classes=len(labels))
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)

    print("=" * 70)
    print("PyTorch intent training started")
    print(f"Samples         : {len(df)}")
    print(f"Train samples   : {len(train_idx)}")
    print(f"Valid samples   : {len(valid_idx)}")
    print(f"Classes         : {len(labels)}")
    print(f"Vocab size      : {len(vocab)}")
    print("=" * 70)

    best_state = None
    best_valid_loss = float("inf")
    best_epoch = 0
    patience_counter = 0

    for epoch in range(1, EPOCHS + 1):
        model.train()
        optimizer.zero_grad()

        logits = model(X_train)
        train_loss = criterion(logits, y_train)
        train_loss.backward()
        optimizer.step()

        train_preds = torch.argmax(logits, dim=1)
        train_acc = (train_preds == y_train).float().mean().item() * 100
        valid_loss, valid_acc = evaluate(model, X_valid, y_valid, criterion)

        improved = valid_loss < best_valid_loss - 1e-6
        if improved:
            best_valid_loss = valid_loss
            best_epoch = epoch
            patience_counter = 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            patience_counter += 1

        if epoch == 1 or epoch % 10 == 0:
            print(
                f"Epoch {epoch:03d}/{EPOCHS} | "
                f"Train Loss: {train_loss.item():.4f} | Train Acc: {train_acc:.2f}% | "
                f"Valid Loss: {valid_loss:.4f} | Valid Acc: {valid_acc:.2f}%"
            )

        if patience_counter >= EARLY_STOPPING_PATIENCE:
            print(f"Early stopping triggered at epoch {epoch}. Best epoch was {best_epoch}.")
            break

    if best_state is not None:
        model.load_state_dict(best_state)

    final_valid_loss, final_valid_acc = evaluate(model, X_valid, y_valid, criterion)
    benchmark = run_benchmark(model, vocab, labels)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    torch.save({
        "state_dict": model.state_dict(),
        "vocab": vocab,
        "labels": labels,
        "input_size": len(vocab),
        "num_classes": len(labels),
        "best_epoch": best_epoch,
        "best_valid_loss": best_valid_loss,
        "final_valid_acc": final_valid_acc,
        "benchmark_accuracy": benchmark["accuracy"],
    }, MODEL_FILE)

    metrics_payload = {
        "samples": len(df),
        "train_samples": len(train_idx),
        "valid_samples": len(valid_idx),
        "classes": len(labels),
        "vocab_size": len(vocab),
        "best_epoch": best_epoch,
        "best_valid_loss": round(float(best_valid_loss), 6),
        "final_valid_loss": round(float(final_valid_loss), 6),
        "final_valid_acc": round(float(final_valid_acc), 2),
        "benchmark": benchmark,
    }

    with open(METRICS_FILE, "w", encoding="utf-8") as file:
        json.dump(metrics_payload, file, ensure_ascii=False, indent=2)

    print("=" * 70)
    print(f"Best epoch      : {best_epoch}")
    print(f"Best valid loss : {best_valid_loss:.4f}")
    print(f"Final valid acc : {final_valid_acc:.2f}%")
    print(f"Benchmark acc   : {benchmark['accuracy']:.2f}%")
    print(f"Model saved to  : {MODEL_FILE}")
    print(f"Metrics saved   : {METRICS_FILE}")
    print("=" * 70)


if __name__ == "__main__":
    train()
