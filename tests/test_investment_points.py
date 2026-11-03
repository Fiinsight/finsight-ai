from unittest.mock import patch
from app.services import llm_client


def test_investment_points_quote_company_metric_and_keep_connection_conditional():
    with patch.object(llm_client, '_call_llm', side_effect=AssertionError('paid call')):
        result = llm_client.rewrite_news('삼성전자 실적 발표', '삼성전자의 매출은 전년 동기 대비 12.5% 증가했다. 관계자는 설명회에 참석했다.')
    for reason in result['importanceReasons'].values():
        assert '삼성전자' in reason and '12.5%' in reason
        assert '일회성인지 다음 실적 발표' in reason
        assert '살펴볼 단서' not in reason and '확인할 변수' not in reason
        assert '주가 상승' not in reason
    assert len(set(result['importanceReasons'].values())) == 3


def test_insufficient_evidence_is_explicit_instead_of_generic_sector_claim():
    result = llm_client.rewrite_news('행사 개최', '관계자들은 설명회에 참석했다.')
    assert all('관계자들은 설명회에 참석했다.' in reason and '후속 공지' in reason for reason in result['importanceReasons'].values())
    assert '매출·비용·실적 기대에 영향' not in result['importanceReason']


def test_title_fact_can_support_a_point_without_inventing_numbers():
    result = llm_client.rewrite_news('현대로템 수주 계약 발표', '')
    assert '현대로템 수주 계약 발표' in result['importanceReason']
    assert not any(c.isdigit() for c in result['importanceReason'])


def test_sentiment_index_quotes_its_own_topic_not_background_fx():
    title = '성장률 오르는데 체감은 냉랭…뉴스심리지수 7개월만 최저'
    body = '원/달러 환율이 1,500원대로 상승했던 지난 3월 이후 최저치다. 뉴스심리지수는 7개월 만에 가장 낮은 수준으로 집계됐다. 경제성장률 전망치가 상향됐지만 체감 경기는 냉랭했다.'
    result = llm_client.rewrite_news(title, body, allow_llm=False)
    for reason in result['importanceReasons'].values():
        assert reason.startswith('“뉴스심리지수는')
        assert '환율' not in reason and '수출입' not in reason
        assert '7개월' in reason and '다음 발표치' in reason
        assert len(reason.splitlines()) == 2


def test_twenty_real_article_excerpts_have_article_specific_points_without_boilerplate():
    import json
    from pathlib import Path
    rows = json.loads((Path(__file__).parent / 'fixtures' / 'collected_excerpt_articles.json').read_text())
    assert len(rows) >= 20
    points = []
    for row in rows[:20]:
        result = llm_client.rewrite_news(row['title'], row['body'], allow_llm=False)
        reason = result['importanceReason']
        assert reason.startswith('“') and len(reason.splitlines()) == 2
        assert all(template not in reason for template in ['살펴볼 단서', '확인할 변수:', '주가 방향은 단정', '기사 지표의 비교 기준'])
        fact = llm_client._strip_stock_codes(llm_client._point_fact(row['title'], llm_client._clean_article_text(row['title'], row['body'])))
        assert reason.splitlines()[0].strip('“”…') in fact
        points.append(reason)
    assert len(set(points)) == len(points)


def test_checkpoint_keeps_compound_korean_amount_instead_of_truncating_its_magnitude():
    point = llm_client.rewrite_news('삼성전자 영업이익 발표', '삼성전자의 영업이익은 12조1000억원을 기록했다.', allow_llm=False)['importanceReason']
    assert '영업이익 12조1000억원' in point.splitlines()[1]


def test_market_outlook_does_not_replace_the_lead_with_an_older_market_move():
    result = llm_client.rewrite_news('[마켓뷰] AI 수익성 우려 지속, 코스피 향방은', '코스피가 AI 수익성 우려에도 반등할 수 있을지 주목된다. 전날 코스피는 2.24% 올랐다. AI 수익성 우려는 코스피의 지난달 30일 3.84% 급락에 선반영된 영향이 있다.', allow_llm=False)
    assert result['importanceReason'].startswith('“코스피가 AI 수익성 우려에도 반등할 수 있을지 주목된다.”')
    assert '3.84%' not in result['importanceReason']


def test_target_price_check_uses_the_revised_target_not_the_previous_target():
    result = llm_client.rewrite_news('하나증권, S-OIL 목표가 하향', '하나증권은 S-OIL의 목표주가를 기존 22만원에서 18만원으로 하향했다.', allow_llm=False)
    assert '목표가 18만원' in result['importanceReason'].splitlines()[1]


def test_uncertain_market_outlook_keeps_a_forecast_badge_in_normal_reading():
    assert llm_client._sentence_label('코스피가 반등 흐름을 이어갈 수 있을지 주목된다.') == '[전망]'


def test_special_listing_is_not_treated_as_an_index_daily_move():
    from app.services.llm_client import _point_check
    check = _point_check('기술특례 주식 5년 보유…75%, 코스닥 수익률 하회', '기업의 75%가 코스닥 지수를 밑돌았다.', '외국인 매매')
    assert '보유기간' in check
    assert '코스닥 75%' not in check


def test_article_specific_checks_for_events_and_funds():
    from app.services.llm_client import _point_check
    assert '13일 배당투자' in _point_check('13일 배당투자 세미나', '증권사가 세미나를 연다.', '')
    assert '편입 종목별 비중' in _point_check('삼성그룹 ETF 상장', 'ETF를 상장했다.', '')
    assert '공시 위반 횟수별' in _point_check('공시의무 1회 위반 과태료 가중', '과태료가 늘어난다.', '')


def test_inflation_checkpoint_never_labels_a_support_budget_as_inflation():
    point = llm_client.rewrite_news('정부 "체감 물가 높아…역대 최대 김장 대책"', '정부는 김장 대책에 640억원을 투입한다. 체감 물가가 여전히 높다고 밝혔다.', allow_llm=False)['importanceReason']
    assert '640억원 상승' not in point
    assert '할인·지원 대상 품목' in point
    assert llm_client._point_check('체감 물가 여전히 높아', '지원액은 640억원이다.', '') == '물가 상승을 이끈 품목을 전국 물가와 비교해요'


def test_mixed_krx_stock_codes_are_removed_without_removing_bracketed_words():
    assert llm_client._strip_stock_codes('래블업[0147B0] (0147B0) [market]') == '래블업 [market]'
