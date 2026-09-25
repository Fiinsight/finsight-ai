"""Chroma-backed RAG cache for term explanations.

Chroma itself is free/local, so we always try to talk to a real Chroma
server. Only embedding *generation* is cost-gated: in mock mode (the
default) we derive a deterministic fake embedding from a text hash so the
add/query flow still works end-to-end with zero API cost. If Chroma is not
reachable (e.g. docker-compose not started), we fall back to a tiny
in-process dict-based store so the service still boots and the terms
endpoint still works, just without real vector search across restarts.
"""

from __future__ import annotations

import hashlib
import logging

from app import config

logger = logging.getLogger(__name__)

_TERM_COLLECTION = "term_explanations"
_EMBED_DIM = 128
_DEFAULT_SIMILARITY_THRESHOLD = 0.995

_chroma_client = None
_use_fallback = False
_fallback_warned = False
_fallback_collections: dict[str, "_FallbackCollection"] = {}


class _FallbackCollection:
    """Minimal in-process stand-in for a Chroma collection (add + query)."""

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._embeddings: list[list[float]] = []
        self._metadatas: list[dict] = []
        self._documents: list[str] = []

    def add(self, ids: list[str], embeddings: list[list[float]], metadatas: list[dict], documents: list[str]) -> None:
        for i, doc_id in enumerate(ids):
            if doc_id in self._ids:
                idx = self._ids.index(doc_id)
                self._embeddings[idx] = embeddings[i]
                self._metadatas[idx] = metadatas[i]
                self._documents[idx] = documents[i]
            else:
                self._ids.append(doc_id)
                self._embeddings.append(embeddings[i])
                self._metadatas.append(metadatas[i])
                self._documents.append(documents[i])

    def query(self, query_embeddings: list[list[float]], n_results: int = 1) -> dict:
        query_vec = query_embeddings[0]
        best_idx = None
        best_sim = -2.0
        for idx, vec in enumerate(self._embeddings):
            sim = _cosine_similarity(query_vec, vec)
            if sim > best_sim:
                best_sim = sim
                best_idx = idx

        if best_idx is None:
            return {"ids": [[]], "metadatas": [[]], "distances": [[]]}

        distance = 1 - best_sim
        return {
            "ids": [[self._ids[best_idx]]],
            "metadatas": [[self._metadatas[best_idx]]],
            "distances": [[distance]],
        }


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _warn_fallback(exc: Exception) -> None:
    global _fallback_warned
    if not _fallback_warned:
        logger.warning(
            "Chroma 서버(%s:%s)에 연결할 수 없어 인메모리 폴백 저장소를 사용합니다: %s",
            config.CHROMA_HOST,
            config.CHROMA_PORT,
            exc,
        )
        _fallback_warned = True


def _get_client():
    global _chroma_client, _use_fallback

    if _use_fallback:
        return None
    if _chroma_client is not None:
        return _chroma_client

    try:
        import chromadb

        client = chromadb.HttpClient(host=config.CHROMA_HOST, port=config.CHROMA_PORT)
        client.heartbeat()
        _chroma_client = client
    except Exception as exc:
        _warn_fallback(exc)
        _use_fallback = True
        return None

    return _chroma_client


def _get_collection(name: str):
    global _use_fallback

    client = _get_client()
    if client is None:
        return _fallback_collections.setdefault(name, _FallbackCollection())

    try:
        return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})
    except Exception as exc:
        _warn_fallback(exc)
        _use_fallback = True
        return _fallback_collections.setdefault(name, _FallbackCollection())


def _make_id(term: str, context: str) -> str:
    return hashlib.sha256(f"{term}::{context}".encode("utf-8")).hexdigest()


def _fake_embed(text: str) -> list[float]:
    """Deterministic hash-derived embedding in [-1, 1], fixed length _EMBED_DIM.

    The same input text always maps to the same vector, so Chroma add/query
    calls work structurally end-to-end without calling any embeddings API.
    """
    vector: list[float] = []
    for i in range(_EMBED_DIM):
        digest = hashlib.sha256(f"{text}:{i}".encode("utf-8")).digest()
        value = int.from_bytes(digest[:4], "big")
        normalized = (value / 0xFFFFFFFF) * 2 - 1
        vector.append(normalized)
    return vector


def _real_embed(text: str) -> list[float]:
    import openai

    client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
    response = client.embeddings.create(model="text-embedding-3-small", input=text)
    return list(response.data[0].embedding)


def embed(text: str) -> list[float]:
    """Return an embedding for `text`.

    Uses a real OpenAI embedding call only when the separate
    USE_REAL_EMBEDDINGS opt-in is True and an OPENAI_API_KEY is configured.
    Otherwise (and on any failure) falls back to a deterministic hash vector.
    """
    if config.USE_REAL_EMBEDDINGS and config.OPENAI_API_KEY:
        try:
            return _real_embed(text)
        except Exception as exc:
            logger.warning("OpenAI 임베딩 호출 실패, 폴백(해시 기반) 임베딩을 사용합니다: %s", exc)
    return _fake_embed(text)


def upsert_term_context(term: str, context: str, explanation: dict) -> None:
    """Cache a term explanation, keyed by embedding of term + context."""
    collection = _get_collection(_TERM_COLLECTION)
    doc_id = _make_id(term, context)
    document = f"{term} {context}".strip()
    vector = embed(document)
    metadata = {
        "term": term,
        "context": context,
        "definition": explanation.get("definition") or "",
        "contextExplanation": explanation.get("contextExplanation") or "",
        "marketImpact": explanation.get("marketImpact") or "",
    }
    try:
        collection.add(ids=[doc_id], embeddings=[vector], metadatas=[metadata], documents=[document])
    except Exception as exc:
        logger.warning("Chroma에 용어 설명 저장을 실패했습니다: %s", exc)


def query_similar(term: str, context: str, threshold: float = _DEFAULT_SIMILARITY_THRESHOLD) -> dict | None:
    """Return a cached explanation if a close-enough match exists, else None."""
    collection = _get_collection(_TERM_COLLECTION)
    document = f"{term} {context}".strip()
    vector = embed(document)

    try:
        result = collection.query(query_embeddings=[vector], n_results=1)
    except Exception as exc:
        logger.warning("Chroma 조회를 실패했습니다: %s", exc)
        return None

    ids = (result.get("ids") or [[]])[0]
    if not ids:
        return None

    distances = (result.get("distances") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    if not distances or not metadatas:
        return None

    similarity = 1 - distances[0]
    if similarity < threshold:
        return None

    metadata = metadatas[0]
    return {
        "definition": metadata.get("definition") or "",
        "contextExplanation": metadata.get("contextExplanation") or None,
        "marketImpact": metadata.get("marketImpact") or None,
    }
