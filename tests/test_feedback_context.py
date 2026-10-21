import json
from pathlib import Path
from datetime import date
import pytest
from app.routers.feedback import FeedbackRequest, judgement_feedback

@pytest.mark.parametrize('reason,percent,symbol,choice,expected', [
    (None, -1.76, '035720', 'DOWN', '다음엔 판단 근거를 한 줄 남겨보세요.'),
    ('실적 부담을 예상했어요', -1.76, '035720', 'DOWN', '남긴 근거: “실적 부담을 예상했어요”'),
    ('작은 상승을 예상했어요', 0.7, '035720', 'UP', '방향은 맞았지만 변동이 작아 우연일 수 있어요.'),
    ('시장 약세를 예상했어요', -1.76, 'KOSPI', 'DOWN', '개별 종목이 아니라 시장 전체 움직임'),
    ('상승을 예상했어요', -1.76, '035720', 'UP', '다른 방향이에요.'),
])
def test_feedback_snapshots(reason, percent, symbol, choice, expected):
    name = '코스피' if symbol == 'KOSPI' else '카카오'
    result = judgement_feedback(FeedbackRequest(news_id=153, news_title='실적 전망', news_summary='기업 실적이 하락했다. 비용이 증가했다.', user_choice=choice, user_reason=reason, market_result='UP' if percent > 0.5 else 'DOWN', related_symbol=symbol, related_symbol_name=name, actual_change_percent=percent, judgement_close=100, comparison_close=100 + percent, comparison_date=date(2026, 10, 7)))
    snapshots = json.loads((Path(__file__).parent / 'fixtures' / 'feedback_context.json').read_text())
    key = 'no_reason' if reason is None else 'small' if percent > 0 else 'index' if symbol == 'KOSPI' else 'mismatch' if choice == 'UP' else 'with_reason'
    assert result.model_dump() == snapshots[key]
    assert f'{name} 2026-10-07 종가 기준 {percent:+.2f}%.' in result.feedback
    assert expected in result.feedback
    assert '잘 연결' not in result.feedback
    assert '주요 원인과 일치' not in result.feedback
    if reason: assert '기업 실적이 하락했다.' in result.feedback
    assert '단정할 수는 없어요' in result.feedback

def test_missing_market_result_is_not_invented_as_neutral():
    from pydantic import ValidationError
    with pytest.raises(ValidationError): FeedbackRequest(news_id=1, user_choice='UP')


@pytest.mark.parametrize('choice,direction,percent,verdict',[
    ('UP','UP',1.01,'CORRECT'),('UP','UP',1.0,'PARTIAL'),('UP','UP',1.0000000000000002,'PARTIAL'),('DOWN','DOWN',-1.0,'PARTIAL'),
    ('NEUTRAL','NEUTRAL',0,'PARTIAL'),('UP','DOWN',-1.76,'WRONG')])
def test_structured_verdict_and_grounded_reasons(choice,direction,percent,verdict):
    from app.services.llm_client import generate_feedback, _feedback_sentence_count
    result=generate_feedback('매출이 12% 늘었다.',choice,direction,percent,user_reason='수익 개선을 예상했어요.',related_symbol_name='삼성전자',comparison_date='2026-10-07',judgement_close=100,comparison_close=100+percent,index_name='코스피',index_change_percent=-.3)
    assert result['verdict']==verdict
    assert len(result['reasons'])==3
    assert '매출이 12% 늘었다.' in result['reasons'][0]['detail']
    assert '수익 개선을 예상했어요.' in result['reasons'][1]['detail']
    assert '코스피' in result['reasons'][2]['detail'] and '-0.30%' in result['reasons'][2]['detail']
    for item, (minimum, maximum) in zip(result['reasons'], [(2,4),(1,3),(1,2)]):
        assert minimum <= _feedback_sentence_count(item['detail']) <= maximum

@pytest.mark.parametrize('case',['valid','number','sign','praise','praise_process','verdict','missing_reason'])
def test_llm_structure_and_fallback_are_mocked(monkeypatch,case):
    from unittest.mock import patch
    from app.services import llm_client
    context=dict(user_reason=None if case.startswith('praise') else '실적 개선을 예상했어요.',news_title='실적',related_symbol_name='카카오',comparison_date='2026-10-07')
    fallback=llm_client._mock_generate_feedback('매출이 12% 늘었다.','UP','UP',1.76,**context)
    candidate={key:fallback[key] for key in ['verdict','headline','summary','reasons','nextTip']}
    if case=='valid':candidate['headline']='예측 방향을 확인했어요'
    if case=='number':candidate['summary']+=' 매출이 999% 늘었어요.'
    if case=='sign':
        candidate['reasons']=[dict(item) for item in candidate['reasons']]
        candidate['reasons'][2]['detail']=candidate['reasons'][2]['detail'].rstrip('.')+'이고 별도로 -1.76% 움직였어요.'
    if case=='praise':candidate['headline']='정확한 판단이에요!'
    if case=='praise_process':candidate['headline']='판단 과정도 탄탄했어요'
    if case=='verdict':candidate['verdict']='WRONG'
    if case=='missing_reason':candidate['reasons']=candidate['reasons'][:1]
    monkeypatch.setattr(llm_client.config,'USE_REAL_LLM',True)
    with patch.object(llm_client,'_call_llm',return_value=json.dumps(candidate,ensure_ascii=False)) as paid:
        result=llm_client.generate_feedback('매출이 12% 늘었다.','UP','UP',1.76,**context)
    paid.assert_called_once()
    assert result['reasons']==fallback['reasons'] and result['verdict']==fallback['verdict']
    if case=='valid':assert result['headline']==candidate['headline']
    else:assert result==fallback
