from app.services.llm_client import _mock_rewrite_news, _numbers_in_source
ARTICLE='삼성전자는 3분기 영업이익 12조원을 발표했다. HBM 수요가 늘어날 것으로 예상했다. 다만 환율 변동성과 미국의 반도체 수출 규제는 부담 요인이다.'

def test_risk_is_not_denied_and_normal_separates_forecasts():
    result=_mock_rewrite_news('삼성전자 3분기 영업이익 12조',ARTICLE)
    assert '규제' in result['analyst'].split('리스크·확인할 점')[1]
    assert '별도로 언급된 위험 요인은 없습니다' not in result['analyst']
    assert '[사실]' in result['normal'] and '[전망]' in result['normal']
    assert _numbers_in_source(result['normal'],ARTICLE)

def test_beginner_removes_codes_summarizes_list_and_explains_a_real_glossary_term():
    body='반도체 수출이 증가했다. 원익IPS[240810](9.13%)와 삼성전자[005930](4.12%)가 상승했다.'
    result=_mock_rewrite_news('반도체 종목 상승',body)
    assert '[240810]' not in result['beginner'] and '9.13%' not in result['beginner']
    assert '두 종목' in result['beginner'] and '(' in result['beginner']
    assert _numbers_in_source(result['beginner'],body)

def test_risk_in_only_sentence_is_kept():
    result=_mock_rewrite_news('수출 규제','미국의 수출 규제는 부담 요인이다.')
    assert '규제' in result['analyst'].split('리스크·확인할 점')[1]
