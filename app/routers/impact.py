from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services import llm_client

router = APIRouter()


class ImpactRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    related_symbol: str | None = Field(default=None, max_length=20)


class ImpactResponse(BaseModel):
    direction: str
    confidence: float
    targets: list[str]
    evidence: list[str]
    caveats: list[str]
    basis: str


@router.post("/impact", response_model=ImpactResponse)
def market_impact(request: ImpactRequest) -> ImpactResponse:
    result = llm_client.analyze_market_impact(
        title=request.title,
        body=request.body,
        related_symbol=request.related_symbol,
    )
    return ImpactResponse(**result)
