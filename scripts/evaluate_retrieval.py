"""Compare rules and a local embedding model only against human-reviewed pairs."""
import argparse
import json
from pathlib import Path
from app.routers.local_retrieval import Document, SearchRequest, _news_score


def rule_similar(left,right):
    request=SearchRequest(query=(left['title']+' '+left.get('body',''))[:2000],kind='news',documents=[])
    return _news_score(request,Document(id='eval',kind='news',title=right['title'],body=right.get('body',''))) > 0


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dataset',default='datasets/retrieval_eval.jsonl')
    parser.add_argument('--model',default='jhgan/ko-sroberta-multitask')
    parser.add_argument('--threshold',type=float,default=.7)
    args=parser.parse_args()
    rows=[json.loads(line) for line in Path(args.dataset).read_text().splitlines() if line.strip()]
    labelled=[row for row in rows if isinstance(row.get('similar'),bool) and row.get('labelled_by')]
    if len(labelled)!=30:
        print(json.dumps({'status':'HUMAN_LABELS_REQUIRED','labelled':len(labelled),'required':30}));return
    expected=[row['similar'] for row in labelled]
    rule=[rule_similar(row['left'],row['right']) for row in labelled]
    model_results=None
    try:
        from ml.retrieval import local_model
        model=local_model(args.model)
        text=lambda row:row['title']+'\n'+row.get('body','')[:500]
        vectors=model.encode([text(item) for row in labelled for item in [row['left'],row['right']]],normalize_embeddings=True)
        model_results=[float(vectors[2*i] @ vectors[2*i+1])>=args.threshold for i in range(len(labelled))]
    except (ImportError,OSError,ValueError,RuntimeError):pass
    accuracy=lambda values:sum(a==b for a,b in zip(expected,values))/len(expected)
    print('| 방법 | 정확도 | 표본 |\n|---|---:|---:|')
    print(f'| 규칙 | {accuracy(rule):.2%} | 30 |')
    print(f'| 로컬 임베딩 | {accuracy(model_results):.2%} | 30 |' if model_results is not None else '| 로컬 임베딩 | 미설정/실행 불가 | - |')
    print(json.dumps({'threshold':args.threshold,'rule_accuracy':accuracy(rule),'embedding_accuracy':accuracy(model_results) if model_results is not None else None}))


if __name__=='__main__': main()
