from __future__ import annotations

import argparse
import json
import os
import tempfile
from functools import lru_cache
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
        rows.append({**item, "title": title, "body": body, "text": f"{title}\n{body}".strip()})
    if not rows:
        raise ValueError("At least one news row is required")
    return rows


def build_index(dataset: str, output: str, model_name: str, batch_size: int = 32) -> None:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("Install optional ML dependencies first: pip install -r requirements-ml.txt") from exc

    rows = read_news(dataset)
    model = local_model(model_name)
    embeddings = model.encode(
        [row["text"] for row in rows],
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    save_index(rows, embeddings, output, model_name)


def save_index(rows, embeddings, output, model_name):
    array = np.asarray(embeddings, dtype=np.float32)
    if array.ndim != 2 or len(rows) != len(array) or not np.isfinite(array).all() or (len(array) and np.any(np.linalg.norm(array, axis=1) == 0)):
        raise ValueError("Invalid news embeddings")
    if len(array): array = array / np.linalg.norm(array, axis=1, keepdims=True)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    # One atomic archive prevents metadata/vector generation mismatches.
    fd, temporary = tempfile.mkstemp(dir=root, suffix=".npz")
    try:
        with os.fdopen(fd, "wb") as handle:
            np.savez_compressed(handle, embeddings=array, metadata=np.asarray(json.dumps({"model":model_name,"rows":rows},ensure_ascii=False)))
        os.replace(temporary, root / "index.npz")
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def load_index(index_path):
    root = Path(index_path)
    if (root / "index.npz").exists():
        with np.load(root / "index.npz", allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata"].item()))
            embeddings = archive["embeddings"].copy()
    else:
        embeddings = np.load(root / "embeddings.npy", allow_pickle=False)
        metadata = json.loads((root / "metadata.json").read_text())
    rows = metadata.get("rows")
    if not isinstance(rows,list) or embeddings.ndim != 2 or len(rows) != len(embeddings) or not np.isfinite(embeddings).all():
        raise ValueError("Invalid news index")
    norms=np.linalg.norm(embeddings,axis=1,keepdims=True)
    if np.any(norms==0): raise ValueError("Zero news vector")
    return embeddings / norms,metadata


@lru_cache(maxsize=1)
def local_model(model_name):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name,local_files_only=True)


def search_index(index_path: str | Path, query: str, top_k: int = 5, candidate_ids=None):
    embeddings, metadata = load_index(index_path)
    query_embedding = np.asarray(local_model(metadata["model"]).encode([query],normalize_embeddings=True)[0])
    if query_embedding.shape != embeddings.shape[1:] or not np.isfinite(query_embedding).all() or not np.linalg.norm(query_embedding):
        raise ValueError("Invalid query vector")
    scores = embeddings @ (query_embedding / np.linalg.norm(query_embedding))
    allowed = None if candidate_ids is None else {str(value) for value in candidate_ids}
    indices = [index for index in range(len(scores)) if allowed is None or str(metadata["rows"][index].get("news_id")) in allowed]
    indices.sort(key=lambda index:(-float(scores[index]),index))
    return [{**metadata["rows"][index],"score":round(float(scores[index]),6)} for index in indices[:max(1,top_k)]]


def recommend_index(index_path, behaviors, candidate_ids, excluded_ids, top_k=3):
    from difflib import SequenceMatcher
    import re
    embeddings,metadata=load_index(index_path)
    rows=metadata["rows"]
    by_id={str(row.get("news_id")):index for index,row in enumerate(rows) if row.get("news_id") is not None}
    observations=[(by_id[str(item["news_id"])],float(item["weight"])) for item in behaviors if str(item["news_id"]) in by_id and 0 < float(item["weight"]) <= 1000]
    if not observations: return []
    interest=sum(embeddings[index]*weight for index,weight in observations)
    norm=np.linalg.norm(interest)
    if not norm: return []
    scores=embeddings @ (interest/norm)
    excluded={str(value) for value in excluded_ids} | {str(item["news_id"]) for item in behaviors}
    allowed={str(value) for value in candidate_ids}
    candidates=[index for identifier,index in by_id.items() if identifier in allowed and identifier not in excluded]
    candidates.sort(key=lambda index:(-float(scores[index]),str(rows[index]['news_id'])))
    def same_event(left,right):
        normalize=lambda title:re.sub(r'[^가-힣a-z0-9]','',title.lower())
        return bool(left.get('url') and left['url']==right.get('url')) or SequenceMatcher(None,normalize(left['title']),normalize(right['title'])).ratio() >= .88
    chosen=[]
    seen_rows=[rows[by_id[value]] for value in excluded if value in by_id]
    for index in candidates:
        if scores[index] <= 0 or any(same_event(rows[index],other) for other in seen_rows): continue
        closest=max(observations,key=lambda pair:float(embeddings[index] @ embeddings[pair[0]]))[0]
        chosen.append({"news_id":rows[index]["news_id"],"score":round(float(scores[index]),6),"reason_news_id":rows[closest]["news_id"],"reason_title":rows[closest]["title"]})
        seen_rows.append(rows[index])
        if len(chosen)==top_k: break
    return chosen


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
