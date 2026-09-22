from __future__ import annotations

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a trained FinSight sentiment model")
    parser.add_argument("--model", default="artifacts/sentiment")
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", required=True)
    args = parser.parse_args()

    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError as exc:
        raise SystemExit("Install optional ML dependencies: pip install -r requirements-ml.txt") from exc

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(args.model)
    model.eval()
    with torch.no_grad():
        inputs = tokenizer(f"{args.title}\n{args.body}", return_tensors="pt", truncation=True, max_length=256)
        probabilities = torch.softmax(model(**inputs).logits, dim=-1)[0]
    label_id = int(probabilities.argmax())
    label = model.config.id2label.get(label_id, str(label_id))
    print(json.dumps({"label": label, "confidence": round(float(probabilities[label_id]), 4), "probabilities": [round(float(value), 4) for value in probabilities]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
