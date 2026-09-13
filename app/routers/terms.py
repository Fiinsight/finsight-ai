from fastapi import APIRouter
from pydantic import BaseModel

from app.services import llm_client, vector_store

router = APIRouter()


class TermExplainRequest(BaseModel):
    term: str
    article_context: str


class TermExplainResponse(BaseModel):
    term: str
    plain_definition: str
    contextual_meaning: str
    market_impact: str | None = None


@router.post("/explain", response_model=TermExplainResponse)
def explain_term(request: TermExplainRequest) -> TermExplainResponse:
    # RAG 캐시 조회: 같은 용어 + 맥락으로 이미 물어본 적이 있으면 LLM을 다시 호출하지 않고
    # 캐시된 설명을 그대로 반환합니다 (실제 LLM 모드에서 비용을 절약하는 지점).
    cached = vector_store.query_similar(request.term, request.article_context)
    if cached is not None:
        explanation = cached
    else:
        explanation = llm_client.explain_term(request.term, request.article_context or None)
        vector_store.upsert_term_context(request.term, request.article_context, explanation)

    return TermExplainResponse(
        term=request.term,
        plain_definition=explanation["definition"],
        contextual_meaning=explanation.get("contextExplanation") or explanation["definition"],
        market_impact=explanation.get("marketImpact"),
    )
