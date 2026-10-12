from datetime import date
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


class FeedbackResponse(BaseModel):
    is_aligned: bool
    feedback: str
    next_learning_point: str
    reasons: list[str] | None = None


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
    )

    reasons = result.get("reasons", [])
    return FeedbackResponse(
        is_aligned=result["isAligned"],
        feedback=result["feedbackText"],
        next_learning_point=reasons[-1] if reasons else "관련 종목의 거래량과 업종 지수를 함께 비교해보세요.",
        reasons=reasons,
    )
