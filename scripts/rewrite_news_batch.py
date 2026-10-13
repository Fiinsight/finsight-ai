"""Explicit new-collection cohort only; dry-run never calls a model or writes DB."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from app import config
from app.services import llm_client, rewrite_budget
from scripts.news_batch import database


def persist(connection,row,result):
    return connection.execute("""
        UPDATE news SET rewritten_beginner=%s,rewritten_normal=%s,rewritten_analyst=%s,rewrite_mode=%s
        WHERE id=%s AND title IS NOT DISTINCT FROM %s AND raw_content IS NOT DISTINCT FROM %s
          AND rewrite_mode IS NOT DISTINCT FROM %s
          AND rewritten_beginner IS NOT DISTINCT FROM %s AND rewritten_normal IS NOT DISTINCT FROM %s
          AND rewritten_analyst IS NOT DISTINCT FROM %s
        """, (result['beginner'],result['normal'],result['analyst'],result['mode'],row['id'],row['title'],row['raw_content'],row['rewrite_mode'],row['rewritten_beginner'],row['rewritten_normal'],row['rewritten_analyst'])).rowcount


def pending(rows):
    selected=[]
    for row in rows:
        saved=rewrite_budget.peek(row['url'])
        if saved is not None:
            cleaned=llm_client._clean_article_text(row['title'],row['raw_content'])
            if saved.get('_source_hash')!=llm_client._rewrite_source_hash(row['title'],cleaned): continue
            if row['rewrite_mode']==saved['mode'] and all(row['rewritten_'+level]==saved[level] for level in ['beginner','normal','analyst']): continue
        selected.append(row)
    return selected


def main():
    parser=argparse.ArgumentParser(description='Rewrite a specified newly collected cohort using only local Ollama')
    parser.add_argument('--since',required=True,help='Collection created_at lower bound, ISO timestamp with timezone')
    parser.add_argument('--limit',type=int,default=10)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--output',help='Optional JSONL for human quality comparison; only written with --apply')
    args=parser.parse_args()
    try: since=datetime.fromisoformat(args.since)
    except ValueError: parser.error('since must be an ISO timestamp with timezone')
    if since.tzinfo is None: parser.error('since must include timezone')
    if not 1<=args.limit<=50: parser.error('limit must be 1..50')
    if args.apply and (not config.REWRITE_WITH_LLM or config.LLM_PROVIDER!='ollama' or not config.OLLAMA_MODEL):
        raise RuntimeError('Enable only the configured local rewrite provider before applying')
    with database() as db:
        rows=db.execute("""
            SELECT id,title,url,raw_content,rewrite_mode,rewritten_beginner,rewritten_normal,rewritten_analyst
            FROM news WHERE created_at>=%s AND created_at<=%s AND coalesce(rewrite_mode,'EXCERPT')='EXCERPT'
              AND length(trim(coalesce(raw_content,'')))>0 AND coalesce(source,'') NOT LIKE 'SYNTHETIC%%'
              AND url NOT LIKE '%%example.invalid%%' ORDER BY created_at DESC,id DESC LIMIT 1000
            """,(since,datetime.now(timezone.utc))).fetchall()
    rows=pending(rows)[:args.limit]
    print(json.dumps({'selected':len(rows),'would_process':len(rows),'apply':args.apply}),flush=True)
    if not args.apply: return
    results=[]
    for row in rows:
        if llm_client._real_llm_calls>=config.MAX_REAL_LLM_CALLS_PER_PROCESS: break
        result=llm_client.rewrite_news(row['title'],row['raw_content'],row['url'],local_batch=True)
        with database(readonly=False) as db:
            updated=persist(db,row,result)
        results.append({'id':row['id'],'title':row['title'],'body':row['raw_content'],**result,'persisted':updated==1})
    if args.output:
        output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in results),encoding='utf-8')
    print(json.dumps({'processed':len(results),'rewritten':sum(row['mode']=='REWRITTEN' for row in results),'excerpt':sum(row['mode']=='EXCERPT' for row in results),'stored':sum(row['persisted'] for row in results)}))


if __name__=='__main__':
    try: main()
    except Exception:
        raise SystemExit('Local rewrite batch failed; check configuration, local service, and DB schema') from None
