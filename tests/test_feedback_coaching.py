import copy
import json
from unittest.mock import patch

import pytest
from app.services import llm_client


def coaching(reason, choice='UP', direction='UP', percent=2, **context):
    return llm_client._mock_generate_feedback(
        '매출이 증가했다.', choice, direction, percent, news_title='매출 증가',
        user_reason=reason, **context)


def test_outcome_and_reason_quality_are_separate():
    weak = coaching('상승할 것 같아요')
    assert weak['verdict'] == 'CORRECT'
    assert [item['title'] for item in weak['reasons']] == ['기사 신호와 결과', '내 근거 점검', '시장 비교']
    assert '운이 섞였을 수' in weak['reasons'][1]['detail']
    assert '기사에서 본 사실' in weak['reasons'][1]['detail']
    assert '그 사실이 이익·수요·금리 중 무엇을 바꾸는지' in weak['reasons'][1]['detail']
    strong = coaching('매출 증가로 이익 개선을 기대해요.')
    assert '판단 과정도 탄탄했어요' in strong['reasons'][1]['detail']
    assert '남긴 근거: “매출 증가로 이익 개선을 기대해요.”' in strong['reasons'][1]['detail']
    wrong = coaching('매출 증가로 이익 개선을 기대해요.', direction='DOWN', percent=-4.4,
                     index_name='코스피', index_change_percent=-3.7)
    assert wrong['verdict'] == 'WRONG'
    assert '타당했지만' in wrong['reasons'][1]['detail']
    assert '시장 전체 하락에 묻혔을 수 있어요' in wrong['reasons'][0]['detail']
    assert '시장 전체의 반대 움직임' in wrong['reasons'][1]['detail']
    assert '좋은 근거도' in wrong['reasons'][1]['detail']


def test_contradiction_missing_link_and_missing_fact_each_explain_the_gap():
    assert '근거는 하락 쪽 이야기인데 상승을 골랐어요' in coaching('매출 감소를 예상해요')['reasons'][1]['detail']
    assert '가격 경로를 연결' in coaching('증가 소식이에요')['reasons'][1]['detail']
    assert '확인한 사실' in coaching('수요를 생각해요')['reasons'][1]['detail']
    partial = coaching('매출 증가로 이익 개선을 기대해요.', percent=.7)
    assert partial['verdict'] == 'PARTIAL'
    assert '변동이 작아' in partial['reasons'][1]['detail']
    wrong = coaching('하락할 것 같아요', direction='DOWN', percent=-2)
    assert '기사 사실과 가격 경로를 충분히 잇지 못했어요' in wrong['reasons'][1]['detail']


@pytest.mark.parametrize('reason', [None, '', '   '])
def test_no_reason_never_praises(reason):
    result = coaching(reason)
    assert result['reasons'][1] == {'title': '근거 남기기', 'detail': '다음엔 판단 근거를 한 줄 남겨보세요.'}
    assert not any(word in result['feedbackText'] for word in ['탄탄', '타당', '잘했', '훌륭', '정확한 판단'])


def test_unknown_neutral_article_compares_choice_without_inventing_a_result():
    result = llm_client._mock_generate_feedback('고객센터 상담 서비스가 운영된다.', 'UP', 'UNKNOWN', None)
    detail = result['reasons'][1]['detail']
    assert '기사에 뚜렷한 방향 신호가 없는데 상승을 골랐어요' in detail
    assert '“고객센터 상담 서비스 운영” → 이익·수요·금리 변화 → 예상 방향' in detail
    assert detail.count('다음엔 판단 근거를 한 줄 남겨보세요') == 1
    assert '순서로 한 줄을 써보세요' not in detail
    assert llm_client._feedback_sentence_count(detail) == 2
    assert result['verdict'] is None
    assert not result['isAligned']
    assert '다른 방향이에요' not in result['summary']


@pytest.mark.parametrize('signal,direction,percent,index,expected', [
    ('POSITIVE', 'UP', 2, 0, '호재 신호대로'),
    ('NEGATIVE', 'DOWN', -2, 0, '악재 신호대로'),
    ('POSITIVE', 'DOWN', -2, -.51, '시장 전체 하락에 묻혔을 수 있어요'),
    ('POSITIVE', 'DOWN', -2, -.5, '다른 악재'),
    ('NEGATIVE', 'UP', 2, 0, '안도감'),
    ('NEUTRAL', 'UP', 2, 0, '다른 개별 요인'),
    ('POSITIVE', 'NEUTRAL', .5, 0, '크게 반영하지 않았을 수'),
    ('NEGATIVE', 'NEUTRAL', -.5, 0, '크게 반영하지 않았을 수'),
])
def test_why_interpretation_branches(signal, direction, percent, index, expected):
    assert expected in llm_client._feedback_interpretation(signal, direction, percent, index)


@pytest.mark.parametrize('index,count,accepted', [(0,1,False),(0,4,True),(0,5,False),(1,3,True),(1,4,False),(2,2,True),(2,3,False)])
def test_llm_sentence_limits_and_full_reason_quote(monkeypatch, index, count, accepted):
    reason = '매출 증가를 봤어요. 이익 개선을 기대해요.'
    context = dict(user_reason=reason)
    fallback = coaching(reason)
    candidate = copy.deepcopy(fallback)
    current = llm_client._feedback_sentence_count(candidate['reasons'][index]['detail'])
    if index == 0 and count == 1:
        candidate['reasons'][index]['detail'] = '기사에서는 “매출이 증가했다.”라고 전했어요.'
    else:
        candidate['reasons'][index]['detail'] += ' 확인해보세요.' * (count - current)
    candidate['headline'] = '결과와 과정을 나눠봐요'
    monkeypatch.setattr(llm_client.config, 'USE_REAL_LLM', True)
    monkeypatch.setattr(llm_client.config, 'FEEDBACK_WITH_LLM', False)
    with patch.object(llm_client, '_call_llm', return_value=json.dumps(candidate, ensure_ascii=False)):
        result = llm_client.generate_feedback('매출이 증가했다.', 'UP', 'UP', 2, news_title='매출 증가', **context)
    assert (result['mode'] == 'LLM') == accepted
    assert f'남긴 근거: “{reason}”' in result['reasons'][1]['detail']
