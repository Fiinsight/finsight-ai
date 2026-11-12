"""Level differences must retain source evidence, not just change text statistics."""
import pytest

from app.services import llm_client as llm
from scripts.check_level_quality import DEFAULT_BODY, DEFAULT_TITLE, analyze, assess


def sections(text):
    return [block.split('\n', 1)[1] for block in text.split('\n\n')]


def test_analyst_keeps_the_cause_that_the_original_smoke_article_lost():
    result = llm.rewrite_news(DEFAULT_TITLE, DEFAULT_BODY, allow_llm=False)
    evidence, figures, risk = sections(result['analyst'])
    assert '[분석] HBM 수요 확대와 서버용 메모리 가격 상승이 실적 개선을 이끌었다는 분석이다.' in evidence
    assert '[전망] 증권가에서는 삼성전자와 SK하이닉스의 4분기 영업이익 전망치를 잇달아 상향 조정하고 있다.' in figures
    for sentence in llm._split_sentences(DEFAULT_BODY):
        assert result['analyst'].count(sentence) == 1
    assert '별도로 언급된 위험 요인은 없습니다' in risk
    assert '추가 확인이 필요합니다' not in risk
    assert result['mode'] == 'EXCERPT'


def test_original_formula_and_order_are_preserved_for_comparable_prose():
    result = llm.rewrite_news(DEFAULT_TITLE, DEFAULT_BODY, allow_llm=False)
    assert analyze('매출은 늘었다.')['difficulty_score'] == len('매출은 늘었다.') * .5 + 3
    assessment = assess(result, DEFAULT_BODY)
    assert assessment['passed'], assessment['issues']
    scores = [assessment['stats'][level]['difficulty_score'] for level in ('beginner', 'normal', 'analyst')]
    assert scores[0] <= scores[1] <= scores[2], scores


def test_analyst_retains_selected_non_numeric_facts_and_labels_a_forecast():
    body = '수출이 증가했다. 가격 상승이 실적 개선을 이끌었다는 분석이다. 내년에는 수요가 늘어날 것으로 예상했다.'
    text = llm._reading_summary('수출과 수요', body, 'analyst')
    evidence, figures, risk = sections(text)
    for sentence in llm._split_sentences(body):
        assert text.count(sentence) == 1
    assert '[사실] 수출이 증가했다.' in evidence
    assert '[분석] 가격 상승' in evidence
    assert '[전망] 내년에는 수요' in evidence
    assert figures == '추가 비교 수치 없음'


@pytest.mark.parametrize('term', ['HBM', 'AI', 'PF'])
def test_beginner_explains_the_visible_acronym_before_a_general_topic(term):
    text = llm._reading_summary('수출과 반도체', f'반도체 수출이 증가했다. {term} 수요가 늘었다.', 'beginner')
    assert term + '(' in text
    assert '반도체(' not in text
    assert llm._numbers_in_source(text, f'반도체 수출이 증가했다. {term} 수요가 늘었다.')


def test_beginner_does_not_explain_a_term_only_present_in_omitted_context():
    body = '수출이 증가했다. HBM 공급은 안정적이다. 매출은 12% 늘었다.'
    text = llm._reading_summary('HBM과 수출', body, 'beginner')
    assert 'HBM(' not in text
    assert '수출(' in text
    assert '12%' in text


def test_no_model_call_or_invented_risk_for_a_numeric_source(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Rule reading must never use a provider')
    monkeypatch.setattr(llm, '_call_llm', forbidden)
    monkeypatch.setattr(llm, '_call_ollama', forbidden)
    body = '수출은 지난해보다 12.5% 증가했다. 매출은 1,000억원으로 집계됐다.'
    result = llm.rewrite_news('수출 실적', body, allow_llm=False)
    for level in ('beginner', 'normal', 'analyst'):
        assert llm._numbers_in_source(result[level], body)
        assert len(result[level]) <= 600
    evidence, figures, risk = sections(result['analyst'])
    assert '12.5%' in evidence and '1,000억원' in figures
    assert '규제' not in risk and '관세' not in risk


def test_a_single_risk_sentence_does_not_leave_the_evidence_section_empty():
    evidence, _, risk = sections(llm._reading_summary('수출 규제', '미국의 수출 규제는 부담 요인이다.', 'analyst'))
    assert '수출 규제' in evidence and '수출 규제' in risk


def test_unused_figure_space_preserves_a_long_source_explanation():
    cause = '기업은 ' + '공급망 안정과 주문 증가, 물류비 감소 및 재고 조정에 따른 생산 효율 개선, ' * 5 + '이 모든 요인이 수익성 회복의 원인이라고 분석했다.'
    body = '반도체 수출이 증가했다. ' + cause + ' 매출은 100억원으로 집계됐다.'
    text = llm._reading_summary('반도체 수출과 매출', body, 'analyst')
    evidence, figures, risk = sections(text)
    assert cause in evidence
    assert '100억원' in figures
    assert '별도로 언급된 위험 요인은 없습니다' in risk
    assert len(text) <= 600
