from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services import llm_client
from app.services.ml_sentiment import predict_sentiment
from app.services.news_retrieval import search_news, recommend_news

router = APIRouter()


class RewriteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    article_key: str | None = Field(default=None, max_length=1000)
    level: str | None = Field(default=None, pattern="^(beginner|normal|analyst)$")


class RewriteResponse(BaseModel):
    title: str
    summary: str
    beginner: str
    normal: str
    analyst: str
    mode: str
    importance_reason: str | None
    importance_reasons: dict[str, str | None] = Field(default_factory=dict)
    detected_terms: list[str]


class SentimentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)


class SentimentResponse(BaseModel):
    label: str
    confidence: float
    basis: str


class SimilarNewsRequest(BaseModel):
    query: str = Field(min_length=2)
    top_k: int = Field(default=5, ge=1, le=20)


class SimilarNewsResponse(BaseModel):
    results: list[dict[str, object]]
    basis: str


@router.post("/rewrite", response_model=RewriteResponse)
def rewrite_news(request: RewriteRequest) -> RewriteResponse:
    result = llm_client.rewrite_news(title=request.title, raw_content=request.body, article_key=request.article_key)
    return RewriteResponse(
        title=request.title,
        summary=result[request.level or "normal"],
        beginner=result["beginner"], normal=result["normal"], analyst=result["analyst"], mode=result["mode"],
        importance_reason=result["importanceReason"],
        importance_reasons=result.get("importanceReasons", {}),
        detected_terms=result.get("detectedTerms", []),
    )


@router.post("/sentiment", response_model=SentimentResponse)
def sentiment(request: SentimentRequest) -> SentimentResponse:
    return SentimentResponse(**predict_sentiment(request.title, request.body))


@router.post("/similar", response_model=SimilarNewsResponse)
def similar_news(request: SimilarNewsRequest) -> SimilarNewsResponse:
    return SimilarNewsResponse(**search_news(request.query, request.top_k))


class Behavior(BaseModel):
    news_id: int = Field(gt=0)
    weight: float = Field(gt=0, le=1000, allow_inf_nan=False)


class RecommendationRequest(BaseModel):
    behaviors: list[Behavior] = Field(default_factory=list, max_length=500)
    candidate_ids: list[int] = Field(default_factory=list, max_length=300)
    excluded_ids: list[int] = Field(default_factory=list, max_length=5000)


@router.post("/recommendations")
def recommendations(request: RecommendationRequest):
    return recommend_news([item.model_dump() for item in request.behaviors],request.candidate_ids,request.excluded_ids)
