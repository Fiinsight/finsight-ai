from fastapi import FastAPI

from app import config
from app.routers import feedback, impact, news, terms

app = FastAPI(title="FinSight AI Service", version="0.1.0")

app.include_router(news.router, prefix="/ai/news", tags=["news"])
app.include_router(impact.router, prefix="/ai/news", tags=["news"])
app.include_router(terms.router, prefix="/ai/terms", tags=["terms"])
app.include_router(feedback.router, prefix="/ai/feedback", tags=["feedback"])


@app.get("/health")
def health() -> dict[str, object]:
    # Keep this endpoint useful on a laptop or school GPU server without
    # revealing API keys. It makes it explicit whether the optional local
    # classifier is active instead of presenting a rule fallback as deep learning.
    from app.services.ml_sentiment import model_status

    return {
        "status": "ok",
        "useRealLlm": config.USE_REAL_LLM,
        "llmProvider": config.LLM_PROVIDER if config.USE_REAL_LLM else "disabled",
        "sentimentModel": model_status(),
    }
