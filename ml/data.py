from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

LABELS = ("NEGATIVE", "NEUTRAL", "POSITIVE")
LABEL_TO_ID = {label: index for index, label in enumerate(LABELS)}


@dataclass(frozen=True)
class NewsExample:
    title: str
    body: str
    label: str
    published_at: str = ""

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body}".strip()


def read_jsonl(path: str | Path) -> list[NewsExample]:
    examples: list[NewsExample] = []
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
            label = str(item["label"]).upper()
            title = str(item["title"])
            body = str(item.get("body", ""))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid dataset row at line {line_number}: {exc}") from exc
        if label not in LABEL_TO_ID:
            raise ValueError(f"Unsupported label at line {line_number}: {label}; use {LABELS}")
        examples.append(NewsExample(title, body, label, str(item.get("published_at", ""))))
    if len(examples) < 3:
        raise ValueError("At least 3 labelled examples are required")
    return examples


def chronological_split(examples: Iterable[NewsExample], train_ratio: float = 0.7, valid_ratio: float = 0.15) -> tuple[list[NewsExample], list[NewsExample], list[NewsExample]]:
    """Split in time order to avoid future-news leakage."""
    ordered = list(examples)
    if not 0 < train_ratio < 1 or not 0 < valid_ratio < 1 or train_ratio + valid_ratio >= 1:
        raise ValueError("train_ratio + valid_ratio must be less than 1")
    if any(example.published_at for example in ordered):
        ordered.sort(key=lambda example: example.published_at)
    train_end = max(1, int(len(ordered) * train_ratio))
    valid_end = max(train_end + 1, int(len(ordered) * (train_ratio + valid_ratio)))
    valid_end = min(valid_end, len(ordered) - 1)
    return ordered[:train_end], ordered[train_end:valid_end], ordered[valid_end:]
