import json
from pathlib import Path
from datetime import datetime,timezone
import re
import pytest
from app.services import llm_client as llm
from app.routers import chart, local_retrieval as search, terms

@pytest.fixture(autouse=True)
def free(monkeypatch,tmp_path):
    for flag in ('USE_REAL_LLM','REWRITE_WITH_LLM','DOCENT_WITH_LLM','FEEDBACK_WITH_LLM'):
        monkeypatch.setattr(llm.config,flag,False)
    monkeypatch.setattr(llm.config,'DOCENT_LEDGER_PATH',str(tmp_path/'docent.db'))
    monkeypatch.setattr(llm,'_call_llm',lambda *a,**k:pytest.fail('paid model'))

@pytest.mark.parametrize('term,expected',[('AI','AI를'),('HBM','HBM을'),('PF','PF를'),('영업이익','영업이익을'),('금리','금리를')])
def test_term_particle_hint_and_context(term,expected,monkeypatch):
    assert llm._with_particle(term,'을/를')==expected
    explanation=llm._mock_explain_term(term,f'{term} 관련 수요가 늘어났다고 밝혔다.')
    value=llm.personalize_term(explanation,term,'','beginner')
    assert '(을/를)' not in str(value) and '낯선 길' not in str(value)
    monkeypatch.setattr(terms.vector_store,'query_similar',lambda *a:None)
    monkeypatch.setattr(terms.vector_store,'upsert_term_context',lambda *a:None)
    response=terms.explain_term(terms.TermExplainRequest(term=term,level='beginner',article_context=f'{term} 수요가 늘어났다고 밝혔다.'))
    assert '(을/를)' not in response.contextual_meaning
    summary=llm._reading_summary('경제 뉴스',f'{term} 수요가 증가했다고 밝혔다.','beginner')
    if term in llm.TERM_DEFINITIONS:
        assert re.search(re.escape(term)+r'\([^\n]+(?<!\.)\)'+re.escape(expected[len(term):])+r' 함께 살펴봐요\.',summary)

@pytest.mark.parametrize('text,label',[
 ('시장 예상을 밑도는 실적을 발표하자 주가가 하락했다.','[사실]'),
 ('영업이익은 12조원을 기록했다.','[사실]'),
 ('매출이 증가할 것으로 예상했다.','[전망]'),
 ('업황이 회복될 전망이다.','[전망]'),
 ('비용이 원인으로 분석된다.','[분석]'),
 ('일회성 요인으로 보인다.','[분석]')])
def test_sentence_labels(text,label):
    assert llm._sentence_label(text)==label

@pytest.mark.parametrize('title,body',[('코스피 급락','코스피 지수는 전날보다 2.5% 하락했다.'),('코스닥 사이드카','코스닥 지수 급락으로 사이드카가 발동됐다고 밝혔다.')])
def test_market_importance_is_source_grounded(title,body):
    r=llm.rewrite_news(title,body,allow_llm=False)
    text=r['importanceReasons']['beginner']
    assert '부족' not in text and body in text and '살펴볼 단서' not in text
    assert text.endswith('요.')

def request(sentiment='POSITIVE',change=3,relation='DIRECT',index=-2):
    return chart.DocentRequest(symbol='005930',symbol_name='삼성전자',date='2026-11-02',change_percent=change,period='D',level='beginner',index_name='코스피',index_change_percent=index,
       news=[chart.RelatedNews(news_id=1,title='기업 실적 발표',summary='AI 수요로 매출이 12% 증가했다고 밝혔다.',published_at=datetime.now(timezone.utc),relation=relation,sentiment_hint=sentiment,sentiment_confidence=.9)])

@pytest.mark.parametrize('sentiment,change',[('POSITIVE',3),('POSITIVE',-3),('NEGATIVE',3),('NEGATIVE',-3)])
def test_docent_four_sign_combinations(sentiment,change):
    r=chart.rule_docent(request(sentiment,change))
    opposite=(sentiment=='POSITIVE' and change<0 or sentiment=='NEGATIVE' and change>0)
    if opposite:assert '소식에도 주가는' in r['possibleReason'] and '받아들여졌을 가능성' not in r['possibleReason']
    else:assert '받아들여졌을 가능성' in r['possibleReason']
    assert '(을/를)' not in r['whatHappened']

@pytest.mark.parametrize('change,index',[(3,-2),(-3,2)])
def test_market_opposite_and_cache_signs(change,index):
    r=chart.docent(request(change=change,relation='MARKET',index=index))
    assert '시장과 반대로' in r['possibleReason']
    opposite=chart.docent(request(change=-change,relation='MARKET',index=index))
    assert '함께 움직였을' in opposite['possibleReason']
    changed_index=chart.docent(request(change=change,relation='MARKET',index=-index))
    assert '함께 움직였을' in changed_index['possibleReason']

@pytest.mark.parametrize('percent',[-.5,0,.5])
def test_neutral_correct(percent):
    r=llm.generate_feedback('시장은 관망세를 나타냈다.','NEUTRAL','NEUTRAL',percent)
    assert r['verdict']=='CORRECT' and '중립 예측' in r['headline']
    assert '중립 예측대로' in r['summary'] and '변동이 작아 우연' not in r['summary']

@pytest.mark.parametrize('query,title',[('HL만도 실적','HL만도, 3분기 영업이익 발표'),('코스피 급락 원인','코스피 급락에 외국인 매도 확대')])
def test_related_search_unknown_company_and_index(query,title,monkeypatch):
    monkeypatch.setattr('app.services.news_retrieval.search_news',lambda *a:{'basis':'RULE_BASED_FALLBACK','results':[]})
    r=search.search(search.SearchRequest(query=query,kind='news',documents=[search.Document(id='1',kind='news',title=title,body='관련 사실을 보도했다.',publishedAt=datetime.now(timezone.utc))]))
    assert [x['id'] for x in r['results']]==['1']

ARTICLES=json.loads((Path(__file__).parent/'fixtures/collected_excerpt_articles.json').read_text())
@pytest.mark.parametrize('article',ARTICLES,ids=lambda a:str(a['id']))
def test_twenty_real_articles_with_publisher_noise(article):
    noise='\n<저작권자 연합뉴스>\n무단 전재 및 재배포 금지\n제보는 카카오톡\n송고 2026-11-02\n재판매 및 DB금지'
    r=llm.rewrite_news(article['title'],article['body']+noise,allow_llm=False)
    text=r['beginner']+' '+r['importanceReasons']['beginner']
    assert not re.search(r'어요고|어요라고|\(을/를\)|요인를|실적를|환율를|시점를|(?<!\d)\d{6}(?!\d)|저작권자|무단 전재|제보는|송고|DB금지',text)

def test_exchange_table_is_not_retryable():
    r=llm.rewrite_news('외국환시세','미국달러 USD 1400 1410 1420 일본엔 JPY 900 910 920 유로 EUR 1500 1510 1520 위안 CNY 180 190 200',allow_llm=False)
    assert r['mode']=='UNAVAILABLE' and r['retryable'] is False
    assert not any(r[level] for level in ('beginner','normal','analyst'))


def test_free_term_explanation_does_not_reuse_old_semantic_cache(monkeypatch):
    monkeypatch.setattr(terms.vector_store,'query_similar',lambda *a:pytest.fail('stale semantic cache'))
    monkeypatch.setattr(terms.vector_store,'upsert_term_context',lambda *a:pytest.fail('unnecessary free cache'))
    r=terms.explain_term(terms.TermExplainRequest(term='AI',level='beginner',article_context='AI 수요가 증가했다.'))
    assert 'AI를' in r.contextual_meaning and '(을/를)' not in r.contextual_meaning


def test_inline_reporter_and_timestamp_noise_preserve_article_numbers():
    body='(서울=연합뉴스) 홍길동 기자 = 영업이익은 12조1000억원을 기록했다.\n2026-11-02 17:20 송고\n재판매 및 DB금지'
    clean=llm._clean_article_text('기업 실적',body)
    assert '12조1000억원' in clean
    assert '기자 =' not in clean and '송고' not in clean and 'DB금지' not in clean


@pytest.mark.parametrize('change',[-.51,-.5,0,.5,.51])
@pytest.mark.parametrize('relation',['DIRECT','MARKET'])
@pytest.mark.parametrize('sentiment',['POSITIVE','NEGATIVE'])
def test_docent_neutral_band_boundaries(change,relation,sentiment):
    text=chart.rule_docent(request(sentiment,change,relation,index=-1.2))['possibleReason']
    neutral=abs(change)<=.5
    if neutral:
        assert ('소식이 나왔지만 주가는 거의 움직이지 않았어요' if relation=='DIRECT' else '시장이 움직인 날에도 주가는 거의 변하지 않았어요') in text
        assert '받아들여졌을 가능성' not in text and '시장과 반대로' not in text and '소식에도 주가는' not in text
        assert (f'{change:+.2f}%' if relation=='DIRECT' else '코스피 -1.20%') in text
    else:
        assert '거의' not in text
        if relation=='MARKET':
            assert ('시장과 반대로' if change>0 else '함께 움직였을') in text
        else:
            opposite=(sentiment=='POSITIVE' and change<0 or sentiment=='NEGATIVE' and change>0)
            assert ('소식에도 주가는' if opposite else '받아들여졌을 가능성') in text
