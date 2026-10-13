"""Incremental, manual offline embeddings. DB connection is read-only."""
import argparse
import os
from pathlib import Path
import numpy as np
from ml.retrieval import load_index, local_model, save_index
from scripts.news_batch import cleaned_input, database


def incremental(rows, output, model_name, encoder=None):
    import fcntl
    root=Path(output)
    root.mkdir(parents=True,exist_ok=True)
    with (root/'.embed.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _incremental(rows,output,model_name,encoder)


def _incremental(rows, output, model_name, encoder=None):
    root=Path(output)
    vectors, metadata = load_index(root) if (root/'index.npz').exists() or (root/'metadata.json').exists() else (None,{'model':model_name,'rows':[]})
    if metadata['model'] != model_name or any(row.get('news_id') is None for row in metadata['rows']):
        raise ValueError('Existing index model/identities differ; use a separate index directory')
    indexed={str(row['news_id']) for row in metadata['rows']}
    fresh=[]
    for row in rows:
        if str(row['id']) in indexed: continue
        body,_=cleaned_input(row['title'],row.get('raw_content'))
        if not body.strip(): continue
        fresh.append({'news_id':row['id'],'title':row['title'],'body':body[:500],'url':row.get('url'),'published_at':str(row.get('published_at') or ''),'symbol':row.get('related_symbol')})
        indexed.add(str(row['id']))
    if not fresh: return 0
    model=encoder or local_model(model_name)
    encoded=np.asarray(model.encode([row['title']+'\n'+row['body'] for row in fresh],normalize_embeddings=True,batch_size=32,show_progress_bar=False),dtype=np.float32)
    combined=encoded if vectors is None else np.concatenate([vectors,encoded])
    save_index(metadata['rows']+fresh,combined,root,model_name)
    return len(fresh)


def main():
    parser=argparse.ArgumentParser(description='Embed only new article IDs; never writes DB records')
    parser.add_argument('--output',default=os.getenv('ML_NEWS_INDEX_PATH') or 'artifacts/news-index')
    parser.add_argument('--model',default='jhgan/ko-sroberta-multitask')
    args=parser.parse_args()
    with database() as db:
        rows=db.execute("SELECT id,title,raw_content,url,published_at,related_symbol FROM news WHERE coalesce(source,'') NOT LIKE 'SYNTHETIC%%' AND url NOT LIKE '%%example.invalid%%' ORDER BY id").fetchall()
    print({'scanned':len(rows),'embedded_new':incremental(rows,args.output,args.model)})


if __name__=='__main__':
    try: main()
    except Exception:
        raise SystemExit('Embedding batch unavailable; check optional dependencies, local model, and index') from None
