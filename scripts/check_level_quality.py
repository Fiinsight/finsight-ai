"""Render saved results for human inspection; no model generation or DB mutation."""
import argparse
import html
import json
from pathlib import Path
from app.services.llm_client import _clean_article_text, _mock_rewrite_news


def cell(value):
    return html.escape(str(value)).replace('|','&#124;').replace('\n','<br>')


def report(rows):
    lines=['# 수준별 리라이팅 비교','', '제공된 저장 결과만 비교하며 모델을 호출하지 않습니다.', '', '| 원문 | 발췌 | 로컬 LLM |','|---|---|---|']
    for row in rows[:10]:
        title=row['title'];body=row.get('body',row.get('raw_content',''))
        excerpt=_mock_rewrite_news(title,_clean_article_text(title,body))
        excerpts='\n\n'.join(label+'\n'+excerpt[level] for level,label in [('beginner','초보자'),('normal','일반'),('analyst','분석')])
        generated='\n\n'.join(label+'\n'+row.get(level,'결과 없음') for level,label in [('beginner','초보자'),('normal','일반'),('analyst','분석')]) if row.get('mode')=='REWRITTEN' else 'EXCERPT: 저장된 LLM 리라이팅 없음'
        lines.append('| '+cell(title+'\n'+body)+' | '+cell(excerpts)+' | '+cell(generated)+' |')
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description='Compare up to ten saved article rewrites without generation')
    parser.add_argument('--input',required=True,help='JSONL exported by rewrite_news_batch')
    parser.add_argument('--output',default='artifacts/level-quality.md')
    args=parser.parse_args()
    rows=[json.loads(line) for line in Path(args.input).read_text().splitlines() if line.strip()]
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(report(rows),encoding='utf-8')
    print(f'Compared {min(10,len(rows))} saved articles; no model calls')


if __name__=='__main__': main()
