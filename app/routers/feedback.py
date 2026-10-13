from datetime import date
from typing import Literal
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services import llm_client

router = APIRouter()


class FeedbackRequest(BaseModel):
    level: str = Field(default="normal", pattern="^(beginner|normal|analyst)$")
    news_id: int
    user_choice: str = Field(pattern="^(UP|NEUTRAL|DOWN)$")
    user_reason: str | None = Field(default=None, max_length=2000)
    market_result: str = Field(pattern="^(UP|NEUTRAL|DOWN|UNKNOWN)$")
    news_title: str = Field(default="", max_length=300)
    news_summary: str = Field(default="", max_length=600)
    related_symbol: str | None = None
    related_symbol_name: str | None = None
    actual_change_percent: float | None = Field(default=None, allow_inf_nan=False)
    judgement_close: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    comparison_close: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    comparison_date: date | None = None
    sentiment_hint: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"] | None = None
    sentiment_confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    index_name: str | None = Field(default=None, max_length=100)
    index_change_percent: float | None = Field(default=None, allow_inf_nan=False)


class FeedbackReason(BaseModel):
    title: str = Field(min_length=1, max_length=16)
    detail: str


class FeedbackResponse(BaseModel):
    verdict: Literal['CORRECT', 'WRONG', 'PARTIAL'] | None
    headline: str = Field(min_length=1, max_length=255)
    summary: str
    reasons: list[FeedbackReason] = Field(min_length=2, max_length=3)
    nextTip: str
    is_aligned: bool
    feedback: str
    next_learning_point: str


@router.post("/judgement", response_model=FeedbackResponse)
def judgement_feedback(request: FeedbackRequest) -> FeedbackResponse:
    result = llm_client.generate_feedback(
        news_summary=request.news_summary,
        user_choice=request.user_choice,
        actual_direction=request.market_result,
        actual_change_percent=request.actual_change_percent,
        level=request.level, user_reason=request.user_reason, news_title=request.news_title,
        related_symbol=request.related_symbol, related_symbol_name=request.related_symbol_name,
        judgement_close=request.judgement_close, comparison_close=request.comparison_close,
        comparison_date=request.comparison_date.isoformat() if request.comparison_date else None,
        sentiment_hint=request.sentiment_hint, sentiment_confidence=request.sentiment_confidence,
        index_name=request.index_name, index_change_percent=request.index_change_percent,
    )

    reasons = result["reasons"]
    return FeedbackResponse(
        verdict=result["verdict"], headline=result["headline"], summary=result["summary"], nextTip=result["nextTip"],
        is_aligned=result["isAligned"],
        feedback=result["feedbackText"],
        next_learning_point=result["nextTip"],
        reasons=reasons,
    )
