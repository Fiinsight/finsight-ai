from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from app.services.sentiment_rules import rule_label, topic_label as _topic_direction


@lru_cache(maxsize=1)
def _load_model():
    model_path = os.getenv("ML_SENTIMENT_MODEL_PATH", "").strip()
    if not model_path or not Path(model_path).exists():
        return None
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        return AutoTokenizer.from_pretrained(model_path, local_files_only=True), AutoModelForSequenceClassification.from_pretrained(model_path, local_files_only=True), torch
    except (ImportError, OSError, ValueError, RuntimeError):
        return None


def model_status() -> dict[str, object]:
    """Expose safe model diagnostics for /health without loading secrets."""
    model_path = os.getenv("ML_SENTIMENT_MODEL_PATH", "").strip()
    if not model_path:
        return {"mode": "rule_fallback", "configured": False}
    if not Path(model_path).exists():
        return {"mode": "rule_fallback", "configured": True, "pathExists": False}
    if _load_model() is None:
        return {"mode": "rule_fallback", "configured": True, "pathExists": True, "loadable": False}
    return {"mode": "local_transformer", "configured": True, "pathExists": True, "loadable": True}


def predict_sentiment(title: str, body: str) -> dict[str, object]:
    loaded = _load_model()
    text = f"{title}\n{body}"
    if loaded is not None:
        try:
            tokenizer, model, torch = loaded
            model.eval()
            with torch.no_grad():
                inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
                probabilities = torch.softmax(model(**inputs).logits, dim=-1)[0]
            label_id = int(probabilities.argmax())
            label = str(model.config.id2label.get(label_id, model.config.id2label.get(str(label_id), "NEUTRAL"))).upper()
            confidence = float(probabilities[label_id])
            import math
            if label not in {"POSITIVE", "NEGATIVE", "NEUTRAL"} or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("Unsupported sentiment output")
            return {"label": label if confidence >= 0.6 else "NEUTRAL", "confidence": round(confidence, 4), "basis": "LOCAL_FINANCIAL_TRANSFORMER"}
        except (ValueError, RuntimeError, TypeError, AttributeError, IndexError):
            pass  # Unavailable or incompatible local models retain the keyword fallback.

    return predict_rule_sentiment(title, body)


def predict_rule_sentiment(title: str, body: str) -> dict[str, object]:
    label = rule_label(f"{title}\n{body}")
    return {"label": label, "confidence": 0.35 if label == "NEUTRAL" else 0.7, "basis": "RULE_BASED_FALLBACK"}


def sentiment_note(label: str | None, confidence: float | None) -> str:
    if label in {"POSITIVE", "NEGATIVE"} and confidence is not None and 0.6 <= confidence <= 1:
        direction = "긍정적" if label == "POSITIVE" else "부정적"
        return f"기사 표현은 {direction}으로 분류됐지만 주가 움직임의 원인으로 단정할 수는 없어요."
    if confidence is not None:
        return "기사 감성만으로 호재·악재를 판단하기 어려워요."
    return ""
