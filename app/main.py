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

    selected_key = (
        config.GEMINI_API_KEY
        if config.LLM_PROVIDER == "gemini"
        else config.ANTHROPIC_API_KEY
        if config.LLM_PROVIDER == "claude"
        else ""
    )
    llm_enabled = config.USE_REAL_LLM and bool(selected_key)
    return {
        "status": "ok",
        "useRealLlm": llm_enabled,
        "llmEnabled": llm_enabled,
        "llmProvider": config.LLM_PROVIDER if llm_enabled else "disabled",
        "llmFallback": not llm_enabled,
        "llmMode": "real" if llm_enabled else "fallback",
        "llmTimeoutSeconds": config.LLM_REQUEST_TIMEOUT_SECONDS,
        "realEmbeddingsEnabled": (
            config.USE_REAL_EMBEDDINGS and bool(config.OPENAI_API_KEY)
        ),
        "sentimentModel": model_status(),
    }
