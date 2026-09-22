from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


def read_news(path: str | Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
            title = str(item["title"])
            body = str(item.get("body", ""))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid news row at line {line_number}: {exc}") from exc
        rows.append({"title": title, "body": body, "text": f"{title}\n{body}".strip()})
    if not rows:
        raise ValueError("At least one news row is required")
    return rows


def build_index(dataset: str, output: str, model_name: str, batch_size: int = 32) -> None:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("Install optional ML dependencies first: pip install -r requirements-ml.txt") from exc

    rows = read_news(dataset)
    model = SentenceTransformer(model_name)
    embeddings = model.encode(
        [row["text"] for row in rows],
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)
    np.save(output_path / "embeddings.npy", np.asarray(embeddings, dtype=np.float32))
    (output_path / "metadata.json").write_text(
        json.dumps({"model": model_name, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def search_index(index_path: str | Path, query: str, top_k: int = 5) -> list[dict[str, Any]]:
    root = Path(index_path)
    embeddings = np.load(root / "embeddings.npy")
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("Install optional ML dependencies first: pip install -r requirements-ml.txt") from exc
    model = SentenceTransformer(metadata["model"])
    query_embedding = model.encode([query], normalize_embeddings=True)[0]
    scores = embeddings @ query_embedding
    indices = np.argsort(scores)[::-1][: max(1, top_k)]
    return [
        {"title": metadata["rows"][int(index)]["title"], "body": metadata["rows"][int(index)]["body"], "score": round(float(scores[index]), 4)}
        for index in indices
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a free local semantic index for Korean news")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", default="artifacts/news-index")
    parser.add_argument("--model", default="jhgan/ko-sroberta-multitask")
    parser.add_argument("--batch-size", type=int, default=32)
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    build_index(args.dataset, args.output, args.model, args.batch_size)
