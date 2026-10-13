from __future__ import annotations

from app import config


def search_news(query: str, top_k: int = 5, candidate_ids=None) -> dict[str, object]:
    if not config.ML_NEWS_INDEX_PATH:
        return {"results": [], "basis": "INDEX_NOT_CONFIGURED"}
    try:
        from ml.retrieval import search_index
        return {"results": search_index(config.ML_NEWS_INDEX_PATH, query, top_k, candidate_ids), "basis": "LOCAL_SENTENCE_TRANSFORMER"}
    except Exception:
        return {"results": [], "basis": "INDEX_UNAVAILABLE_RULE_FALLBACK"}


def recommend_news(behaviors, candidate_ids, excluded_ids):
    if not config.ML_NEWS_INDEX_PATH:
        return {"results": [], "basis": "INDEX_NOT_CONFIGURED"}
    try:
        from ml.retrieval import recommend_index
        return {"results": recommend_index(config.ML_NEWS_INDEX_PATH, behaviors, candidate_ids, excluded_ids), "basis": "LOCAL_SENTENCE_TRANSFORMER"}
    except Exception:
        return {"results": [], "basis": "INDEX_UNAVAILABLE_RULE_FALLBACK"}
