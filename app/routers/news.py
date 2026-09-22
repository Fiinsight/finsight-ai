from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services import llm_client
from app.services.ml_sentiment import predict_sentiment

router = APIRouter()


class RewriteRequest(BaseModel):
    title: str
    body: str
    level: str = Field(pattern="^(beginner|normal|analyst)$")


class RewriteResponse(BaseModel):
    title: str
    summary: str
    importance_reason: str
    detected_terms: list[str]


class SentimentRequest(BaseModel):
    title: str
    body: str


class SentimentResponse(BaseModel):
    label: str
    confidence: float
    basis: str


@router.post("/rewrite", response_model=RewriteResponse)
def rewrite_news(request: RewriteRequest) -> RewriteResponse:
    result = llm_client.rewrite_news(title=request.title, raw_content=request.body)
    return RewriteResponse(
        title=request.title,
        summary=result[request.level],
        importance_reason=result["importanceReason"],
        detected_terms=result.get("detectedTerms", []),
    )


@router.post("/sentiment", response_model=SentimentResponse)
def sentiment(request: SentimentRequest) -> SentimentResponse:
    return SentimentResponse(**predict_sentiment(request.title, request.body))
