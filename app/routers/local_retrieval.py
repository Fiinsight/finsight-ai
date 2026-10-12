"""Bounded, free adapter for the backend's authorized candidate documents."""
import re
from difflib import SequenceMatcher
from app.services.llm_client import _detected_terms
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


_COMPANIES = ('현대로템', '현대백화점', '현대차', '현대자동차', '기아', '삼성전자', '삼성전기', '하이닉스',
              '네이버', '카카오', 'LG에너지솔루션', '셀트리온', '포스코', '인텔', '엔비디아', '애플')
_TOPICS = ({'금리', '기준금리', '국채금리', '물가', '인플레이션'}, {'환율', '원화', '원달러', '수출', '수입'},
           {'영업이익', '매출', '밸류에이션'}, {'반도체', 'HBM', 'AI'}, {'PF', '연체율', '프로젝트파이낸싱'})
_GENERIC = {'증권', '목표가', '목표주가', '전망', '영향', '상승', '하락', '하향', '상향', '예상', '기자'}


def _words(text: str) -> set[str]:
    words = re.findall(r'[가-힣a-z]+', text.lower())
    return {re.sub(r'(?:에서는|에서|으로|은|는|을|를|의|와|과)$', '', word) for word in words if len(word) >= 2} - _GENERIC


def _headline(text: str) -> str:
    return re.sub(r'[^가-힣a-z0-9]', '', re.sub(r'\[(?:속보|종합\d*)\]|\(종합\d*\)', '', text.lower()))


def _news_score(request: SearchRequest, doc: Document) -> float:
    companies = {name for name in _COMPANIES if name in request.query}
    title_companies = {name for name in _COMPANIES if name in doc.title}
    body_companies = {name for name in companies if name in doc.body}
    if companies and title_companies and not companies & title_companies:
        return 0  # Shared broker/target-price wording is not a shared company.
    query_terms = set(_detected_terms(request.query))
    title_terms = set(_detected_terms(doc.title))
    body_terms = set(_detected_terms(doc.body))
    shared_terms = query_terms & (title_terms | body_terms)
    topic_matches = sum(bool(query_terms & topic and (title_terms | body_terms) & topic) for topic in _TOPICS)
    words = _words(request.query)
    word_matches = len(words & _words(doc.title))
    company_matches = len(companies & title_companies)
    symbol_match = bool(request.symbol and request.symbol == doc.symbol)
    if not (company_matches or body_companies or shared_terms or symbol_match or word_matches >= 2):
        return 0
    return (8 * company_matches + 3 * len(body_companies) + 4 * symbol_match
            + 3 * len(query_terms & title_terms) + len(shared_terms) + topic_matches + word_matches)


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
        score = (_news_score(request, doc) if request.kind == 'news' else
                 (2 * len(query & title) + len(query & body)) / (3 * len(query)) if query else 0)
        if score <= 0:
            continue
        results.append({
            'id': doc.id, 'title': doc.title, 'score': round(score, 6),
            'evidence': doc.body[:600], 'url': doc.url, 'source': doc.source,
            'publishedAt': doc.publishedAt.isoformat() if doc.publishedAt else None,
            'synthetic': False,
        })
    results.sort(key=lambda row: (-row['score'], row['id']))
    if request.kind == 'news':
        distinct = []
        for row in results:
            if any(row['url'] and row['url'] == previous['url'] or
                   SequenceMatcher(None, _headline(row['title']), _headline(previous['title'])).ratio() >= 0.88
                   for previous in distinct):
                continue
            distinct.append(row)
        results = distinct
    return {
        'schemaVersion': '1', 'status': 'RULE_FALLBACK' if results else 'DATA_UNAVAILABLE',
        'fallbackReason': 'LOCAL_MODEL_NOT_CONFIGURED', 'qualityValidated': False,
        'confidence': None, 'relationType': 'LEXICAL_MATCH',
        'rankingPolicy': 'LEXICAL_SCORE', 'results': results[:request.topK],
        'note': '무료 로컬 규칙 검색 (fallback). 의미 유사도나 실제 주가 원인은 확인할 수 없습니다.',
    }
