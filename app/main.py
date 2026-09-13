from fastapi import FastAPI

from app import config
from app.routers import feedback, news, terms

app = FastAPI(title="FinSight AI Service", version="0.1.0")

app.include_router(news.router, prefix="/ai/news", tags=["news"])
app.include_router(terms.router, prefix="/ai/terms", tags=["terms"])
app.include_router(feedback.router, prefix="/ai/feedback", tags=["feedback"])


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "useRealLlm": config.USE_REAL_LLM}

