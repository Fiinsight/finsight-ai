"""Regression examples mirrored in Java JudgementCoachingRulesTest."""
import copy
import json
import logging
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from app.services import llm_client as f


def feedback(reason, choice='UP', direction='UP', percent=2.3, title='매출 증가',
             summary='매출이 전년보다 증가했다.', index=.4, level='normal'):
    return f._mock_generate_feedback(summary, choice, direction, percent, user_reason=reason, news_title=title,
                                    related_symbol='005930', related_symbol_name='삼성전자',
                                    comparison_date='2026-10-13', index_name='코스피', index_change_percent=index, level=level)


@pytest.mark.parametrize('case', json.loads((Path(__file__).parent / 'fixtures/feedback_coaching_contract.json').read_text()), ids=lambda case: case['case'])
def test_shared_python_java_coaching_contract(case):
    result=feedback(case['reason'],case['choice'],case['direction'],case['percent'],case['title'],case['lead'],case['index'],case['level'])
    assert result['verdict']==case['verdict']
    assert result['reasons']==case['reasons']
    assert result['nextTip']==case['nextTip']


def test_a_single_fact_is_not_also_a_price_link_or_strong_reason():
    for reason in ['유가', '유가가 올라서', '유가가 많이 올라서']:
        result = feedback(reason, title='유가 상승', summary='국제 유가가 상승했다.')
        quality = f._feedback_reason_quality(reason, 'UP', '유가 상승 국제 유가가 상승했다.')
        assert quality['has_fact'] and not quality['has_link'] and not quality['strong']
        assert '운이 섞였을 수' in result['reasons'][1]['detail']
        assert not re.search(r'탄탄|타당|잘했|훌륭', result['reasons'][1]['detail'])
    assert not f._feedback_reason_quality('매출 이익', 'UP', '매출 증가')['strong']
    assert not f._feedback_reason_quality('매출 이익.....', 'UP', '매출 증가')['strong']


@pytest.mark.parametrize('reason', ['성장 기대가 커져서', '외국인 매수세가 늘어날 것'])
def test_reason_direction_is_separate_from_article_sentiment(reason):
    result = feedback(reason, choice='DOWN', direction='DOWN', percent=-2, title=reason, summary=reason + '으로 관측됐다.')
    assert '근거는 상승 쪽 이야기인데 하락을 골랐어요' in result['reasons'][1]['detail']
    assert not f._feedback_reason_quality(reason, 'DOWN', reason)['strong']


@pytest.mark.parametrize('reason', ['부담이 줄어 이익이 늘 것', '비용이 감소해 이익이 늘 것', '줄어드는 부담으로 이익 회복'])
def test_lower_burden_is_positive_instead_of_a_contradiction(reason):
    assert f._feedback_reason_direction(reason) == 'UP'
    quality = f._feedback_reason_quality(reason, 'UP', '원가 부담 완화')
    assert not quality['contradicts']
    assert '하락 쪽 이야기' not in feedback(reason, title='원가 부담 완화')['reasons'][1]['detail']


def test_neutral_article_and_large_stock_index_difference_agree_on_individual_factors():
    for choice in ['UP', 'DOWN']:
        result = feedback('정책 일정을 확인했어요.', choice=choice, title='정책 일정', summary='정책 일정이 공지됐다.')
        assert all('개별' in result['reasons'][i]['detail'] for i in (0, 2))
        assert '시장 흐름을 따라' not in result['feedbackText']
        assert '시장 흐름이나 수급을 따라' not in result['feedbackText']


def test_verdict_changes_why_and_wrong_reason_does_not_repeat_article():
    reason = '매출 증가로 이익 개선을 기대해요.'
    correct = feedback(reason)
    same_result_wrong_choice = feedback(reason, choice='DOWN')
    assert correct['reasons'][0]['detail'] != same_result_wrong_choice['reasons'][0]['detail']
    wrong = feedback(reason, direction='DOWN', percent=-4.4, index=-3.7)
    assert correct['reasons'][0]['detail'] != wrong['reasons'][0]['detail']
    last = f._split_sentences(wrong['reasons'][0]['detail'])[-1]
    assert last not in wrong['reasons'][1]['detail']
    assert '타당했지만 시장 전체의 반대 움직임' in wrong['reasons'][1]['detail']
    assert '시장 전체도 같은 방향이라 뉴스만의 효과로 보긴 어려워요' in feedback(reason, index=2)['reasons'][0]['detail']
    partial = feedback(reason, percent=.7)
    assert '±1% 이내' in partial['reasons'][0]['detail']


@pytest.mark.parametrize('signal,choice,direction,percent,index,cause', [
    ('POSITIVE','UP','DOWN',-3,-2,'MARKET'),
    ('POSITIVE','DOWN','UP',2,0,'CHOICE'),
    ('POSITIVE','UP','DOWN',-2,0,'PRICED_IN'),
    ('NEGATIVE','DOWN','UP',2,0,'PRICED_IN'),
    ('NEUTRAL','UP','DOWN',-2,0,'NO_SIGNAL'),
])
def test_wrong_cause_priority(signal, choice, direction, percent, index, cause):
    assert f._feedback_miss_cause(signal, choice, direction, percent, index) == cause


@pytest.mark.parametrize('choice,direction,percent', [('NEUTRAL','DOWN',-1.5), ('NEUTRAL','UP',1.5), ('UP','NEUTRAL',.3), ('DOWN','NEUTRAL',-.3)])
def test_neutral_band_is_explained_in_both_mismatch_directions(choice, direction, percent):
    result = feedback('매출 증가로 이익 개선을 기대해요.', choice, direction, percent)
    assert '±0.5%' in result['reasons'][1]['detail']
    assert f'{percent:+.2f}%' in result['reasons'][1]['detail']


def test_quote_grammar_examples_and_beginner_sentences():
    result = feedback('매출 증가로 이익 개선을 기대해요.', level='beginner')
    assert '남긴 근거: “매출 증가로 이익 개선을 기대해요.”.' in result['reasons'][1]['detail']
    assert not re.search(r'”(?:와|과|은|는) ', result['feedbackText'])
    assert ';' not in result['reasons'][2]['detail']
    assert result['reasons'][2]['detail'].endswith(' 종가는 거래가 끝날 때의 가격이에요.')
    assert f._feedback_sentence_count(result['reasons'][2]['detail']) == 3
    phrase = f._feedback_example_phrase('유가 고영향 물품 조달 안정화 연장하기로 했다.')
    assert phrase == '유가 고영향 물품 조달 안정화 연장' and len(phrase) <= 25
    long = f._feedback_example_phrase('산업통상자원부는 오늘 유가 고영향 물품 조달 안정화 조치를 연장하기로 했다.')
    assert len(long) <= 25 and long.endswith('연장')


def test_tip_uses_first_missing_skill_before_market_and_generic_tips():
    cases = [(None, '판단 근거를 한 줄'), ('수요 회복으로 이익 확대를 기대해요.', '기사에서 확인한 사실'),
             ('매출이 증가했다는 내용이에요.', '무엇을 바꾸는지'), ('매출이 떨어져 이익 감소를 우려해요.', '고른 방향'),
             ('매출 악재 이익', '고른 방향'), ('매출 증가로 이익 개선을 기대해요.', '코스피 흐름')]
    for reason, expected in cases:
        result = feedback(reason, index=2)
        assert expected in result['nextTip']


@pytest.mark.parametrize('case,code', [('verdict','verdict_mismatch'),('count','reason_count'),('title','reason_title'),
    ('sentence','sentence_count'),('number','number_not_in_source'),('quote','missing_quote'),
    ('field','missing_field'),('claim','unsafe_claim'),('repeat',None),('neutral','missing_neutral_band'),
    ('weakpraise','weak_reason_praise'),('market','market_mismatch')])
def test_llm_rejection_logs_only_a_reason_code(monkeypatch, caplog, case, code):
    reason = '유가가 올라서' if case == 'weakpraise' else '매출 증가로 이익 개선을 기대해요.'
    choice, direction, percent = ('NEUTRAL','DOWN',-1.5) if case == 'neutral' else ('UP','DOWN',-2.3) if case == 'repeat' else ('UP','UP',2.3)
    context = dict(user_reason=reason, news_title='매출 증가', related_symbol='005930', related_symbol_name='삼성전자', comparison_date='2026-10-13')
    if case == 'market': context.update(index_name='코스피', index_change_percent=.4)
    candidate = copy.deepcopy(f._mock_generate_feedback('매출이 전년보다 증가했다.',choice,direction,percent,**context))
    if case == 'verdict': candidate['verdict'] = 'WRONG'
    if case == 'count': candidate['reasons'].pop()
    if case == 'title': candidate['reasons'][0]['title'] = '잘못된 제목'
    if case == 'sentence': candidate['reasons'][0]['detail'] += ' 확인해요. 확인해요. 확인해요.'
    if case == 'number': candidate['summary'] += ' 999% 변했어요.'
    if case == 'quote': candidate['reasons'][1]['detail'] = '근거를 다시 확인해보세요.'
    if case == 'field': candidate['nextTip'] = ''
    if case == 'claim': candidate['headline'] = '확실히 맞았어요'
    if case == 'repeat': candidate['reasons'][1]['detail'] += ' ' + f._split_sentences(candidate['reasons'][0]['detail'])[-1]
    if case == 'neutral': candidate['reasons'][1]['detail'] = f'남긴 근거: “{reason}”. 실제 결과를 확인해보세요.'
    if case == 'weakpraise': candidate['headline'] = '판단 과정도 탄탄했어요'
    if case == 'market': candidate['reasons'][2]['detail'] = candidate['reasons'][2]['detail'].replace('시장과의 차이가 커 개별 소식 등 다른 요인도 확인해야 해요.', '시장 전체 흐름과 함께 움직였어요.')
    monkeypatch.setattr(f.config,'USE_REAL_LLM',True); monkeypatch.setattr(f.config,'FEEDBACK_WITH_LLM',False)
    with caplog.at_level(logging.INFO,logger=f.__name__), patch.object(f,'_call_llm',return_value=json.dumps(candidate,ensure_ascii=False)):
        result = f.generate_feedback('매출이 전년보다 증가했다.',choice,direction,percent,**context)
    assert result['mode'] == ('RULE' if code else 'LLM')
    if code: assert f'reason={code}' in caplog.text
    else: assert 'reason=repeated_explanation' not in caplog.text
    assert reason not in caplog.text


def test_prompt_teaches_the_same_quality_and_miss_priority():
    prompt=f._build_feedback_prompt('매출이 전년보다 증가했다.','UP','UP',2.3,user_reason='유가가 올라서')
    for expected in ['다른 단어','중복 인정하지','substantial=false','①','②','③','④','±0.5%','그대로 반복하지','사실 누락 → 연결 누락 → 방향 모순']:
        assert expected in prompt


@pytest.mark.parametrize('mode', ['RULE', 'LLM'])
def test_old_cached_feedback_cannot_bypass_new_coaching_validation(monkeypatch, mode):
    from app.services import feedback_budget
    context = dict(user_reason='유가가 올라서', news_title='유가 상승')
    legacy = copy.deepcopy(f._mock_generate_feedback('국제 유가가 상승했다.','UP','UP',2.3,**context))
    legacy['mode'] = mode
    legacy['reasons'][1]['detail'] = '남긴 근거 “유가가 올라서”는 판단 과정도 탄탄했어요.'
    monkeypatch.setattr(f.config,'USE_REAL_LLM',False);monkeypatch.setattr(f.config,'FEEDBACK_WITH_LLM',True)
    monkeypatch.setattr(f.config,'LLM_PROVIDER','gemini')
    with patch.object(feedback_budget,'reserve',return_value=(False,legacy)), patch('app.services.rewrite_budget.status',return_value={'rewriteStoppedToday':False}), patch.object(f,'_call_gemini') as paid, patch.object(f,'_reserve_process_llm_call') as ceiling:
        result=f.generate_feedback('국제 유가가 상승했다.','UP','UP',2.3,**context)
    assert result['mode']=='RULE' and '탄탄' not in result['reasons'][1]['detail']
    paid.assert_not_called();ceiling.assert_not_called()
