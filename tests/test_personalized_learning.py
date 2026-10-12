from unittest.mock import patch
import pytest
from app.routers.feedback import FeedbackRequest, judgement_feedback
from app.routers.terms import TermExplainRequest, explain_term
from app.services import llm_client

@pytest.mark.parametrize('level,expected', [('beginner','종가는 거래가 끝날 때'),('analyst','중립 범위는 ±0.5%'),('normal','다음엔 판단 근거')])
def test_feedback_level_is_local_and_no_reason_never_praises(level, expected):
    with patch.object(llm_client.config, 'USE_REAL_LLM', False), patch.object(llm_client, '_call_llm') as paid:
        result=judgement_feedback(FeedbackRequest(news_id=1,user_choice='UP',market_result='DOWN',level=level,related_symbol_name='기업',actual_change_percent=-1.76,comparison_date='2026-10-07'))
    assert expected in result.feedback
    assert '기업 2026-10-07 종가 기준 -1.76%' in result.feedback
    assert '잘 연결' not in result.feedback
    paid.assert_not_called()


def test_level_personalization_reuses_base_cache_without_extra_llm_calls():
    base={'definition':'돈을 빌리는 비용','contextExplanation':'기사에서는 금리가 상승했어요.','marketImpact':'비용을 비교하세요.'}
    with patch('app.routers.terms.vector_store.query_similar',return_value=base) as cache, patch.object(llm_client,'explain_term') as llm:
        beginner=explain_term(TermExplainRequest(term='금리',article_context='금리가 2% 상승했다.',level='beginner'))
        analyst=explain_term(TermExplainRequest(term='금리',article_context='금리가 2% 상승했다.',level='analyst'))
    assert '대여료와 비슷' in beginner.contextual_meaning
    assert '금리가 2% 상승했다.' in analyst.market_impact
    assert cache.call_args_list[0]==cache.call_args_list[1]
    assert base['contextExplanation']=='기사에서는 금리가 상승했어요.'
    llm.assert_not_called()


def test_analyst_does_not_invent_numbers_when_no_quantitative_basis():
    result=llm_client.personalize_term({'definition':'금리'},'금리','금리 동결 소식','analyst')
    assert '정량적 시장 영향을 단정할 수 없습니다' in result['marketImpact']
