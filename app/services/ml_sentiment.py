from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

POSITIVE_WORDS = ("상승", "급등", "강세", "회복", "증가", "흑자", "개선", "호조", "확대", "성장", "수혜")
NEGATIVE_WORDS = ("하락", "급락", "약세", "감소", "적자", "악화", "부진", "축소", "우려", "위기", "손실")


def _topic_direction(text: str) -> str | None:
    rate_topic = any(term in text for term in ("금리", "국채", "채권", "수익률"))
    if rate_topic:
        rises = any(term in text for term in ("금리 상승", "금리 급등", "금리 인상", "국채금리 상승", "국채 금리 상승", "수익률 상승", "수익률 급등"))
        falls = any(term in text for term in ("금리 하락", "금리 급락", "금리 인하", "국채금리 하락", "국채 금리 하락", "수익률 하락", "수익률 급락"))
        if rises and not falls:
            return "NEGATIVE"
        if falls and not rises:
            return "POSITIVE"
    if "환율" in text and not any(term in text for term in ("수출", "수입")):
        return "NEUTRAL"
    return None


@lru_cache(maxsize=1)
def _load_model():
    model_path = os.getenv("ML_SENTIMENT_MODEL_PATH", "").strip()
    if not model_path or not Path(model_path).exists():
        return None
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        return AutoTokenizer.from_pretrained(model_path), AutoModelForSequenceClassification.from_pretrained(model_path), torch
    except (ImportError, OSError):
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
        tokenizer, model, torch = loaded
        model.eval()
        with torch.no_grad():
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
            probabilities = torch.softmax(model(**inputs).logits, dim=-1)[0]
        label_id = int(probabilities.argmax())
        label = model.config.id2label.get(label_id, str(label_id)).upper()
        return {"label": label, "confidence": round(float(probabilities[label_id]), 4), "basis": "KLUE_ROBERTA_FINE_TUNED"}

    topic_label = _topic_direction(text)
    if topic_label is not None:
        return {"label": topic_label, "confidence": 0.7 if topic_label != "NEUTRAL" else 0.35, "basis": "RULE_BASED_FALLBACK"}

    positive = sum(text.count(word) for word in POSITIVE_WORDS)
    negative = sum(text.count(word) for word in NEGATIVE_WORDS)
    if positive == negative:
        label, confidence = "NEUTRAL", 0.35
    elif positive > negative:
        label, confidence = "POSITIVE", min(0.85, 0.5 + 0.1 * (positive - negative))
    else:
        label, confidence = "NEGATIVE", min(0.85, 0.5 + 0.1 * (negative - positive))
    return {"label": label, "confidence": round(confidence, 4), "basis": "RULE_BASED_FALLBACK"}
