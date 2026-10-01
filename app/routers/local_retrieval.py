"""Bounded, free adapter for the backend's authorized candidate documents."""
import re
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import AwareDatetime, BaseModel, Field

router = APIRouter()


class Document(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    kind: Literal['news', 'term', 'case']
    title: str = Field(max_length=2000)
    body: str = Field(max_length=20000)
    publishedAt: AwareDatetime | None = None
    symbol: str | None = Field(default=None, max_length=30)
    owner: str | None = Field(default=None, max_length=100)
    url: str | None = Field(default=None, max_length=2000)
    source: str | None = Field(default=None, max_length=1000)
    synthetic: bool = False


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    kind: Literal['news', 'term', 'case']
    documents: list[Document] = Field(max_length=500)
    topK: int = Field(default=3, ge=1, le=20)
    owner: str | None = Field(default=None, max_length=100)
    startAt: AwareDatetime | None = None
    endAt: AwareDatetime | None = None
    symbol: str | None = Field(default=None, max_length=30)
    term: str | None = Field(default=None, max_length=100)


def tokens(text: str) -> set[str]:
    # ponytail: Korean character bigrams are lexical fallback, use an installed local model for semantic ranking.
    words = re.findall(r'[가-힣a-z0-9]+', text.lower())
    return {part for word in words for part in ([word] if len(word) < 2 else
            [word[i:i + 2] for i in range(len(word) - 1)])}


@router.post('/v1/search')
def search(request: SearchRequest) -> dict:
    if request.kind == 'case' and not request.owner:
        raise HTTPException(400, 'Case search requires an owner')
    if request.startAt and request.endAt and request.startAt >= request.endAt:
        raise HTTPException(400, 'Invalid time window')
    query = tokens(request.query)
    results = []
    for doc in request.documents:
        if doc.kind != request.kind or doc.synthetic:
            continue
        if request.kind == 'case' and doc.owner != request.owner:
            continue
        if request.kind != 'term':
            if doc.publishedAt is None:
                continue
            if request.startAt and doc.publishedAt < request.startAt:
                continue
            if request.endAt and doc.publishedAt >= request.endAt:
                continue
        title = tokens(doc.title)
        body = tokens(doc.body)
        score = (2 * len(query & title) + len(query & body)) / (3 * len(query)) if query else 0
        if score <= 0:
            continue
        results.append({
            'id': doc.id, 'title': doc.title, 'score': round(score, 6),
            'evidence': doc.body[:600], 'url': doc.url, 'source': doc.source,
            'publishedAt': doc.publishedAt.isoformat() if doc.publishedAt else None,
            'synthetic': False,
        })
    results.sort(key=lambda row: (-row['score'], row['id']))
    return {
        'schemaVersion': '1', 'status': 'RULE_FALLBACK' if results else 'DATA_UNAVAILABLE',
        'fallbackReason': 'LOCAL_MODEL_NOT_CONFIGURED', 'qualityValidated': False,
        'confidence': None, 'relationType': 'LEXICAL_MATCH',
        'rankingPolicy': 'LEXICAL_SCORE', 'results': results[:request.topK],
        'note': '무료 로컬 규칙 검색 (fallback). 의미 유사도나 실제 주가 원인은 확인할 수 없습니다.',
    }
