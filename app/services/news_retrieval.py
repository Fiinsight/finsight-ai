from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app import config


@lru_cache(maxsize=1)
def _load_index() -> tuple[Path, dict]:
    path = Path(config.ML_NEWS_INDEX_PATH)
    if not config.ML_NEWS_INDEX_PATH or not (path / "embeddings.npy").exists() or not (path / "metadata.json").exists():
        return path, {}
    return path, json.loads((path / "metadata.json").read_text(encoding="utf-8"))


def search_news(query: str, top_k: int = 5) -> dict[str, object]:
    index_path, metadata = _load_index()
    if not metadata:
        return {"results": [], "basis": "INDEX_NOT_CONFIGURED"}
    from ml.retrieval import search_index

    return {"results": search_index(index_path, query, top_k), "basis": "LOCAL_SENTENCE_TRANSFORMER"}
