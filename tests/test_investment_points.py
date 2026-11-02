from unittest.mock import patch
from app.services import llm_client


def test_investment_points_quote_company_metric_and_keep_connection_conditional():
    with patch.object(llm_client, '_call_llm', side_effect=AssertionError('paid call')):
        result = llm_client.rewrite_news('삼성전자 실적 발표', '삼성전자의 매출은 전년 동기 대비 12.5% 증가했다. 관계자는 설명회에 참석했다.')
    for reason in result['importanceReasons'].values():
        assert '삼성전자' in reason and '12.5%' in reason
        assert '살펴볼 단서' in reason and '일회성 요인' in reason
        assert '주가 상승' not in reason
    assert len(set(result['importanceReasons'].values())) == 3


def test_insufficient_evidence_is_explicit_instead_of_generic_sector_claim():
    result = llm_client.rewrite_news('행사 개최', '관계자들은 설명회에 참석했다.')
    assert all('근거가 부족' in reason for reason in result['importanceReasons'].values())
    assert '매출·비용·실적 기대에 영향' not in result['importanceReason']


def test_title_fact_can_support_a_point_without_inventing_numbers():
    result = llm_client.rewrite_news('현대로템 수주 계약 발표', '')
    assert '현대로템 수주 계약 발표' in result['importanceReason']
    assert not any(c.isdigit() for c in result['importanceReason'])
