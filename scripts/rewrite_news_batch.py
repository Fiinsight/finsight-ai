"""Guarded manual rewriting; EXCERPT mode is free and limited to seven publication days."""
import argparse
import json
from datetime import datetime, timezone, timedelta
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


EXCERPT_COLUMNS = ('rewritten_beginner', 'rewritten_normal', 'rewritten_analyst',
                   'importance_reason', 'importance_reason_beginner', 'importance_reason_normal',
                   'importance_reason_analyst', 'rewrite_retry_pending')


def persist_excerpt(connection, row, result):
    reasons = result.get('importanceReasons', {})
    updates = {**{'rewritten_' + level: result.get(level) for level in ('beginner', 'normal', 'analyst')},
               'importance_reason': result.get('importanceReason'),
               **{'importance_reason_' + level: reasons.get(level) for level in ('beginner', 'normal', 'analyst')},
               'rewrite_retry_pending': False}
    if row['rewrite_mode'] != 'EXCERPT' or result.get('mode') != 'EXCERPT' or any(not isinstance(value, str) or not value.strip()
                                             for key, value in updates.items() if key != 'rewrite_retry_pending'):
        return 0
    if all(row[key] == value for key, value in updates.items()):
        return 0
    guards = ('title', 'url', 'raw_content', 'published_at', 'rewrite_mode', *EXCERPT_COLUMNS)
    return connection.execute(
        'UPDATE news SET ' + ','.join(key + '=%s' for key in updates)
        + " WHERE id=%s AND rewrite_mode='EXCERPT' AND "
        + ' AND '.join(key + ' IS NOT DISTINCT FROM %s' for key in guards),
        (*updates.values(), row['id'], *(row[key] for key in guards))).rowcount


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
    parser=argparse.ArgumentParser(description='Guarded manual rewrite: local Ollama, or free last-seven-day EXCERPT with --excerpt')
    parser.add_argument('--since',required=True,help='ISO lower bound: published_at for --excerpt (clamped to seven days), otherwise created_at')
    parser.add_argument('--limit',type=int,default=10)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--excerpt', action='store_true', help='Guarded free EXCERPT regeneration, published in the last seven days only')
    parser.add_argument('--output',help='Optional JSONL for human quality comparison; only written with --apply')
    args=parser.parse_args()
    try: since=datetime.fromisoformat(args.since)
    except ValueError: parser.error('since must be an ISO timestamp with timezone')
    if since.tzinfo is None: parser.error('since must include timezone')
    if not 1<=args.limit<=(1000 if args.excerpt else 50): parser.error('limit must be 1..1000 for EXCERPT, otherwise 1..50')
    now = datetime.now(timezone.utc)
    if args.excerpt:
        since = max(since, now - timedelta(days=7))
        if since > now: parser.error('since must not be in the future')
    if args.apply and not args.excerpt and (not config.REWRITE_WITH_LLM or config.LLM_PROVIDER!='ollama' or not config.OLLAMA_MODEL):
        raise RuntimeError('Enable only the configured local rewrite provider before applying')
    date_column = 'published_at' if args.excerpt else 'created_at'
    mode_filter = "rewrite_mode='EXCERPT'" if args.excerpt else "coalesce(rewrite_mode,'EXCERPT')='EXCERPT'"
    extra = ',published_at,' + ','.join(EXCERPT_COLUMNS[3:]) if args.excerpt else ''
    with database() as db:
        rows=db.execute(
            'SELECT id,title,url,raw_content,rewrite_mode,rewritten_beginner,rewritten_normal,rewritten_analyst'
            + extra + ' FROM news WHERE ' + date_column + '>=%s AND ' + date_column + '<=%s AND ' + mode_filter
            + " AND length(trim(coalesce(raw_content,'')))>0 AND coalesce(source,'') NOT LIKE 'SYNTHETIC%%'"
            + " AND url NOT LIKE '%%example.invalid%%' ORDER BY " + date_column + ' DESC,id DESC LIMIT 1000',
            (since,now)).fetchall()
    rows=(rows if args.excerpt else pending(rows))[:args.limit]
    print(json.dumps({'selected':len(rows),'would_process':len(rows),'apply':args.apply}),flush=True)
    if not args.apply: return
    results=[]
    for row in rows:
        if not args.excerpt and llm_client._real_llm_calls>=config.MAX_REAL_LLM_CALLS_PER_PROCESS: break
        result=(llm_client.rewrite_news(row['title'],row['raw_content'],allow_llm=False) if args.excerpt else
                llm_client.rewrite_news(row['title'],row['raw_content'],row['url'],local_batch=True))
        with database(readonly=False) as db:
            updated=persist_excerpt(db,row,result) if args.excerpt else persist(db,row,result)
        results.append({'id':row['id'],'title':row['title'],'body':row['raw_content'],**result,'persisted':updated==1})
    if args.output:
        output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in results),encoding='utf-8')
    print(json.dumps({'processed':len(results),'rewritten':sum(row['mode']=='REWRITTEN' for row in results),'excerpt':sum(row['mode']=='EXCERPT' for row in results),'stored':sum(row['persisted'] for row in results)}))


if __name__=='__main__':
    try: main()
    except Exception:
        raise SystemExit('Local rewrite batch failed; check configuration, local service, and DB schema') from None
