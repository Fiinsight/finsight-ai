"""Offline chart-cause evaluation. Draft labels never become user-confirmed truth."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.llm_client import _numbers_in_source

FORBIDDEN = re.compile(r'때문에\s*(?:올랐|내렸|상승|하락)|원인(?:이다|입니다)|확실히|수익\s*보장|매수하세요|매도하세요')

def evaluate(labels, predictions, corpus):
    articles = {n['id']: n for n in corpus['news']}
    moves = {(chart['symbol'], chart['period'], m['timestamp']): m
             for chart in predictions['charts'] for m in chart['response']['moveInsights']}
    rows=[]
    for point in labels['points']:
        move=moves.get((point['symbol'],point['period'],point['timestamp']),{})
        docent=move.get('docent') or {}
        expected=point['expectedNewsIds']
        chosen=docent.get('newsId',move.get('newsId'))
        relation=docent.get('relation','NONE')
        text=' '.join(docent.get(field,'') or '' for field in ('whatHappened','possibleReason','marketImpact'))
        reason=docent.get('possibleReason','') or ''
        what=docent.get('whatHappened','') or ''
        article=articles.get(chosen,{})
        source=' '.join(str(article.get(k,'')) for k in ('title','raw_content'))
        # Include only observed, calculated numeric values; never arbitrary model output.
        for value in (point.get('stockChangePercent'),point.get('indexChangePercent'),point.get('excessChangePercent')):
            if value is not None:
                source+=f' {value:+.2f}% {abs(value):.2f}% {value:+.2f}%p {abs(value):.2f}%p'
        index=point.get('indexChangePercent')
        index_shown=index is not None and point.get('indexName','') in text and f'{index:+.2f}%' in text
        title=article.get('title','')
        opposite=(bool(re.search('급등|상승|강세|호실적|수혜',title)) and point['stockChangePercent']<0
                  or bool(re.search('급락|하락|약세|부진',title)) and point['stockChangePercent']>0)
        contradiction=opposite and bool(re.search('(?:호재|악재)로 받아들여졌',reason))
        own=any(alias.lower() in what.lower() for alias in point.get('aliases',[point['symbolName']]))
        other=bool(re.search('코스피|코스닥|삼성전자|SK하이닉스|현대차|네이버|카카오|셀트리온|LG화학|삼성SDI',what))
        spans=point.get('causeSpans',[])
        rows.append({'id':point['id'],'articleCorrect':chosen in expected if expected else chosen is None,
                     'relationCorrect':relation==point['expectedRelation'],
                     'movePresent':bool(move),'marketEligible':point['period'] in ('D','W'),
                     'marketShown':bool(index_shown),'directionContradiction':bool(contradiction),
                     'unrelatedSentence':not own and other,
                     'unrelatedDirectSentence':relation=='DIRECT' and not own and other,
                     'causeClauseIncluded':any(span in reason for span in spans),
                     'causeClauseEligible':bool(spans),
                     'forbidden':bool(FORBIDDEN.search(text)),
                     'unsupportedNumbers':not _numbers_in_source(text,source),
                     'fakeMove':bool(point.get('priceAdjustmentEvent')) and bool(move)})
    count=len(rows)
    def rate(key,eligible=None):
        selected=[r for r in rows if eligible is None or r[eligible]]
        return {'count':sum(bool(r[key]) for r in selected),'denominator':len(selected),
                'percent':round(100*sum(bool(r[key]) for r in selected)/len(selected),2) if selected else None}
    return {'labelStatus':labels.get('labelStatus','DRAFT'),'points':count,
            'metrics':{'causeArticleAccuracy':rate('articleCorrect'),'relationAccuracy':rate('relationCorrect'),
                       'marketComparisonCoverage':rate('marketShown','marketEligible'),
                       'directionContradictionRate':rate('directionContradiction'),
                       'unrelatedSentenceRate':rate('unrelatedSentence'),
                       'unrelatedDirectSentenceRate':rate('unrelatedDirectSentence'),
                       'causeClauseRate':rate('causeClauseIncluded'),
                       'causeClauseRateEligible':rate('causeClauseIncluded','causeClauseEligible'),
                       'fakeMoves':sum(r['fakeMove'] for r in rows),
                       'forbidden':sum(r['forbidden'] for r in rows),
                       'unsupportedNumbers':sum(r['unsupportedNumbers'] for r in rows)},'rows':rows,
            'definitions':{'causeClauseRate':'Literal user-labelled causal phrase, all points; eligible-only rate also shown.',
                           'unrelatedSentenceRate':'Literal no-own-alias + other company/index, including legitimate MARKET/SECTOR subjects; direct-only rate also shown.',
                           'fakeMoves':'Only labelled corporate-action events; zero without such real examples is not proof of adjustment handling.'}}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('labels','predictions','corpus','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    result=evaluate(*(json.loads(getattr(args,k).read_text()) for k in ('labels','predictions','corpus')))
    actual=hashlib.sha256(args.corpus.read_bytes()).hexdigest()
    declared=json.loads(args.labels.read_text()).get('inputSha256')
    if declared and declared!=actual:raise SystemExit('Frozen corpus hash mismatch; refusing evaluation.')
    result['inputSha256']=actual
    result['predictionSha256']=hashlib.sha256(args.predictions.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('labelStatus','points','metrics')},ensure_ascii=False))

if __name__=='__main__':main()
