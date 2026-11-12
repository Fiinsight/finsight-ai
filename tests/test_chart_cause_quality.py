from scripts.check_chart_cause_quality import evaluate

def test_draft_status_and_evidence_violations_are_not_silenced():
    point=dict(id='synthetic',symbol='005930',symbolName='삼성전자',aliases=['삼성전자'],period='D',timestamp='2026-10-12T00:00:00',
               stockChangePercent=-4,indexName='코스피',indexChangePercent=-1,excessChangePercent=-3,
               expectedNewsIds=[1],expectedRelation='DIRECT',causeSpans=['수출 우려에'])
    labels={'labelStatus':'DRAFT','points':[point]}
    article={'id':1,'title':'삼성전자 수출 우려에 하락','raw_content':'삼성전자 수출이 2% 줄었다.'}
    docent=dict(newsId=2,relation='MARKET',whatHappened='코스피가 999% 하락했다.',possibleReason='외국인 때문에 하락했어요.',marketImpact='매수하세요.')
    output={'charts':[{'symbol':'005930','period':'D','response':{'moveInsights':[{'timestamp':point['timestamp'],'docent':docent}]}}]}
    result=evaluate(labels,output,{'news':[article]})
    assert result['labelStatus']=='DRAFT'
    assert result['metrics']['causeArticleAccuracy']['count']==0
    assert result['metrics']['relationAccuracy']['count']==0
    assert result['metrics']['marketComparisonCoverage']['count']==0
    assert result['metrics']['unrelatedSentenceRate']['count']==1
    assert result['metrics']['unsupportedNumbers']==1
    assert result['metrics']['forbidden']==1
    docent.update(newsId=1,relation='DIRECT',whatHappened=article['raw_content'],
                  possibleReason='수출 우려에 주가가 -4.00% 움직였을 수 있어요. 코스피 -1.00%.',marketImpact='추가 자료가 없어요.')
    result=evaluate(labels,output,{'news':[article]})
    assert result['metrics']['causeArticleAccuracy']['count']==1
    assert result['metrics']['marketComparisonCoverage']['count']==1
    assert result['metrics']['causeClauseRate']['count']==1
    assert result['metrics']['unsupportedNumbers']==result['metrics']['forbidden']==0
