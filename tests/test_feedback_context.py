import json
from pathlib import Path
from datetime import date
import pytest
from app.routers.feedback import FeedbackRequest, judgement_feedback

@pytest.mark.parametrize('reason,percent,symbol,choice,expected', [
    (None, -1.76, '035720', 'DOWN', '다음엔 판단 근거를 한 줄 남겨보세요.'),
    ('실적 부담을 예상했어요', -1.76, '035720', 'DOWN', '남긴 근거 “실적 부담을 예상했어요”'),
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
