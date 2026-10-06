"""Free, source-grounded reading aid. Never dispatches to an LLM or embedding provider."""
from typing import Literal
from fastapi import APIRouter
from pydantic import BaseModel, Field
from app.services.llm_client import _clean_article_text, _split_sentences

router = APIRouter()

class LearningRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    level: Literal['beginner', 'normal', 'analyst']

class LearningResponse(BaseModel):
    level: str
    summary: str
    readingGuide: str
    mode: str = 'RULE_FALLBACK'

def reading_aid(request: LearningRequest) -> LearningResponse:
    content = _clean_article_text(request.title, request.body)
    limit = {'beginner': 2, 'normal': 3, 'analyst': 5}[request.level]
    sentences = _split_sentences(content)[:limit]
    summary = '\n\n'.join(sentences)
    if request.level == 'beginner':
        for term, plain in [('전년 동기', '지난해 같은 기간'), ('전 거래일', '직전 거래일'), ('전장 대비', '직전 거래일과 비교해'), ('상승했다', '올랐다'), ('하락했다', '내렸다')]:
            summary = summary.replace(term, plain)
    if len(summary) > 600:
        summary = summary[:600].rstrip() + '…'
    guide = {
        'beginner': '누가 무엇을 했는지 먼저 읽고, 아래 용어를 확인하세요.',
        'normal': '기사에서 확인한 사실과 앞으로의 기대를 구분해 읽어보세요.',
        'analyst': '비교 시점·수치의 기준·불확실성을 확인하세요. 기사만으로 주가 방향을 단정하지 않습니다.'
    }[request.level]
    return LearningResponse(level=request.level, summary=summary, readingGuide=guide)

@router.post('/learning', response_model=LearningResponse)
def learning(request: LearningRequest) -> LearningResponse:
    return reading_aid(request)
