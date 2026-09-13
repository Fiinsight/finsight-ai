from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services import llm_client

router = APIRouter()


class FeedbackRequest(BaseModel):
    news_id: int
    user_choice: str = Field(pattern="^(UP|NEUTRAL|DOWN)$")
    user_reason: str | None = None
    market_result: str | None = None


class FeedbackResponse(BaseModel):
    is_aligned: bool
    feedback: str
    next_learning_point: str
    reasons: list[str] | None = None


@router.post("/judgement", response_model=FeedbackResponse)
def judgement_feedback(request: FeedbackRequest) -> FeedbackResponse:
    # 이 서비스는 뉴스 본문을 직접 저장하지 않으므로, 백엔드가 넘겨준 사용자 설명(있다면)을
    # 요약 대용으로 사용하고, 없으면 news_id 기반의 최소 문맥을 만들어 사용합니다.
    news_summary = request.user_reason or f"뉴스 ID {request.news_id}에 대한 사용자 판단"
    actual_direction = request.market_result or "NEUTRAL"

    result = llm_client.generate_feedback(
        news_summary=news_summary,
        user_choice=request.user_choice,
        actual_direction=actual_direction,
        actual_change_percent=None,
    )

    reasons = result.get("reasons", [])
    return FeedbackResponse(
        is_aligned=result["isAligned"],
        feedback=result["feedbackText"],
        next_learning_point=reasons[-1] if reasons else "관련 종목의 거래량과 업종 지수를 함께 비교해보세요.",
        reasons=reasons,
    )
