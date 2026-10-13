"""Human labels are required; a missing model is not reported as a model score."""
import argparse
import json
from pathlib import Path
from app.services.ml_sentiment import model_status, predict_rule_sentiment, predict_sentiment
from ml.sentiment import classification_metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', default='datasets/sentiment_eval.jsonl')
    args = parser.parse_args()
    rows = [json.loads(line) for line in Path(args.dataset).read_text().splitlines() if line.strip()]
    labelled = [row for row in rows if row.get('title') and row.get('label') in {'POSITIVE','NEGATIVE','NEUTRAL'} and row.get('labelled_by')]
    if len(labelled) != 100:
        print(json.dumps({'status':'HUMAN_LABELS_REQUIRED','labelled':len(labelled),'required':100}));return
    expected = [row['label'] for row in labelled]
    rule = classification_metrics(expected,[predict_rule_sentiment(row['title'],row.get('body',''))['label'] for row in labelled])
    results = [predict_sentiment(row['title'],row.get('body','')) for row in labelled] if model_status()['mode']=='local_transformer' else []
    model = classification_metrics(expected,[row['label'] for row in results]) if results and all(row['basis']=='LOCAL_FINANCIAL_TRANSFORMER' for row in results) else None
    print('| 방법 | 정확도 | 표본 |\n|---|---:|---:|')
    print(f"| 규칙 | {rule['accuracy']:.2%} | 100 |")
    print(f"| 로컬 모델 | {model['accuracy']:.2%} | 100 |" if model else '| 로컬 모델 | 미설정/실행 불가 | - |')
    print(json.dumps({'rule':rule,'model':model},ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
