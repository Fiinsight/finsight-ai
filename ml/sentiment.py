from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from .data import LABELS, LABEL_TO_ID, NewsExample, chronological_split, read_jsonl


def _require_training_dependencies() -> tuple[Any, Any, Any, Any, Any, Any]:
    try:
        import numpy as np
        import torch
        from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
        from torch.utils.data import DataLoader, Dataset
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("Install optional ML dependencies first: pip install -r requirements-ml.txt") from exc
    return np, torch, DataLoader, Dataset, (accuracy_score, balanced_accuracy_score, f1_score), (AutoModelForSequenceClassification, AutoTokenizer)


def _set_seed(torch: Any, seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def train(args: argparse.Namespace) -> dict[str, Any]:
    np, torch, DataLoader, Dataset, metrics, model_classes = _require_training_dependencies()
    accuracy_score, balanced_accuracy_score, f1_score = metrics
    AutoModelForSequenceClassification, AutoTokenizer = model_classes
    _set_seed(torch, args.seed)

    train_rows, valid_rows, test_rows = chronological_split(read_jsonl(args.dataset))
    tokenizer = AutoTokenizer.from_pretrained(args.model)

    class NewsDataset(Dataset):
        def __init__(self, rows: list[NewsExample]) -> None:
            self.rows = rows

        def __len__(self) -> int:
            return len(self.rows)

        def __getitem__(self, index: int) -> dict[str, Any]:
            row = self.rows[index]
            encoded = tokenizer(row.text, truncation=True, max_length=args.max_length)
            encoded["labels"] = LABEL_TO_ID[row.label]
            return encoded

    def collate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        labels = torch.tensor([row.pop("labels") for row in rows], dtype=torch.long)
        batch = tokenizer.pad(rows, padding=True, return_tensors="pt")
        batch["labels"] = labels
        return batch

    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    model = AutoModelForSequenceClassification.from_pretrained(args.model, num_labels=len(LABELS), id2label=dict(enumerate(LABELS)), label2id=LABEL_TO_ID).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    train_loader = DataLoader(NewsDataset(train_rows), batch_size=args.batch_size, shuffle=False, collate_fn=collate)
    valid_loader = DataLoader(NewsDataset(valid_rows), batch_size=args.batch_size, shuffle=False, collate_fn=collate)
    test_loader = DataLoader(NewsDataset(test_rows), batch_size=args.batch_size, shuffle=False, collate_fn=collate)

    best_valid_f1 = -1.0
    for epoch in range(args.epochs):
        model.train()
        for batch in train_loader:
            batch = {key: value.to(device) for key, value in batch.items()}
            loss = model(**batch).loss
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
        valid = evaluate(model, valid_loader, device, torch, np, f1_score, accuracy_score, balanced_accuracy_score)
        print(json.dumps({"epoch": epoch + 1, "device": str(device), "valid": valid}, ensure_ascii=False))
        if valid["macro_f1"] > best_valid_f1:
            best_valid_f1 = valid["macro_f1"]
            model.save_pretrained(args.output)
            tokenizer.save_pretrained(args.output)

    model = AutoModelForSequenceClassification.from_pretrained(args.output).to(device)
    result = evaluate(model, test_loader, device, torch, np, f1_score, accuracy_score, balanced_accuracy_score)
    Path(args.output, "metrics.json").write_text(json.dumps({"model": args.model, "labels": LABELS, "device": str(device), "test": result}, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def evaluate(model: Any, loader: Any, device: Any, torch: Any, np: Any, f1_score: Any, accuracy_score: Any, balanced_accuracy_score: Any) -> dict[str, float]:
    model.eval()
    predictions: list[int] = []
    expected: list[int] = []
    with torch.no_grad():
        for batch in loader:
            labels = batch.pop("labels").to(device)
            logits = model(**{key: value.to(device) for key, value in batch.items()}).logits
            predictions.extend(logits.argmax(dim=-1).cpu().tolist())
            expected.extend(labels.cpu().tolist())
    return {
        "accuracy": float(accuracy_score(expected, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(expected, predictions)),
        "macro_f1": float(f1_score(expected, predictions, average="macro", zero_division=0)),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train a free Korean financial-news sentiment classifier")
    parser.add_argument("--dataset", required=True, help="JSONL with title, body, label and optional published_at")
    parser.add_argument("--model", default="klue/roberta-base")
    parser.add_argument("--output", default="artifacts/sentiment")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cpu", action="store_true")
    return parser


if __name__ == "__main__":
    train(build_parser().parse_args())
