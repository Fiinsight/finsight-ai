"""Synthetic sources only; no collected article body is committed."""
import pytest
from app.services import llm_client as llm


@pytest.mark.parametrize(('link', 'ending', 'connector'), [
    ('증가했으며', '늘었어요.', ''), ('증가했고', '늘었어요.', ''),
    ('확대하면서', '확대해요.', '이와 함께 '), ('증가했지만', '늘었어요.', '하지만 '),
    ('증가했는데', '늘었어요.', ''), ('늘어서', '늘어요.', '그래서 '),
    ('오르며', '올라요.', ''), ('증가했으며,', '늘었어요.', ''),
])
def test_long_finite_clauses_are_completed_without_changing_numbers(link, ending, connector):
    text = f'가온전자와 나래전자 국내외 사업장의 올해 매출은 지난해보다 12.5% {link} 두 회사는 내년 생산 설비에 3만4천500억원을 투자할 계획이다.'
    parts = llm._split_beginner_sentence(text)
    assert len(parts) == 2
    assert parts[0].endswith(ending) and parts[1].startswith(connector)
    for value in ('가온전자', '나래전자', '12.5%', '3만4천500억원'):
        assert value in ' '.join(parts)
    assert llm._numbers_in_source(' '.join(parts), text)


@pytest.mark.parametrize('quotation', [
    '"수요가 증가했으며, 공급도 확대했다"', '“수요가 증가했지만 공급도 확대했다”',
    "'수요가 증가했고 공급도 확대했다'", '‘수요가 늘어서 생산도 늘었다’',
])
def test_quoted_facts_are_not_split_or_reconjugated(quotation):
    text = f'가온전자 관계자는 해외 시장의 수요와 공급에 대해 {quotation}라고 말했으며 국내 공장의 매출은 1,234억원을 기록했다고 밝혔다.'
    result = ' '.join(llm._split_beginner_sentence(text))
    assert quotation in result
    assert '1,234억원' in result
    assert '기록했다고 밝혔어요.' in result


def test_company_names_lists_dates_units_and_parentheses_are_not_split():
    text = '가온전자, 나래전자, 가온전자연구소(첨단 연구를 수행하고 제품을 설계하는 기관)는 11월 12일 매출 1,234억원을 기록했다.'
    parts = llm._split_beginner_sentence(text)
    assert len(parts) == 1
    assert '가온전자, 나래전자, 가온전자연구소' in parts[0]
    assert '(첨단 연구를 수행하고 제품을 설계하는 기관)' in parts[0]


def test_short_article_has_no_added_analysis_or_fabricated_comparison():
    body = '가온은행은 해외 지점에 원화 계좌를 개설했다고 밝혔다.'
    result = llm._mock_rewrite_news('가온은행 계좌 개설', body)
    assert '원화 계좌를 개설했다고 밝혔어요.' in result['beginner']
    assert body in result['normal'] and body in result['analyst']
    assert '추가 비교 수치 없음' in result['analyst']


def test_periods_inside_reported_speech_remain_inside_the_quote():
    body = '관계자는 "매출이 증가했다. 공급도 확대했다."라고 밝혔다. 매출은 100억원을 기록했다.'
    text = llm._reading_summary('기업 매출',body,'beginner')
    assert '"매출이 증가했다. 공급도 확대했다."라고 밝혔어요.' in text


def test_glossary_substitution_does_not_change_a_direct_quote():
    text = llm._reading_summary('기업 매출', '관계자는 "전망치가 컨센서스를 웃돌았다"라고 밝혔다.', 'beginner')
    assert '"전망치가 컨센서스를 웃돌았다"라고 밝혔어요.' in text


@pytest.mark.parametrize(('source','expected'), [
    ('매출은 늘었습니다.', '매출은 늘었어요.'), ('투자를 확대했습니다.', '투자를 확대했어요.'),
    ('공장은 국내에 있습니다.', '공장은 국내에 있어요.'), ('본사는 연구 회사입니다.', '본사는 연구 회사예요.'),
])
def test_formal_endings_are_not_turned_into_malformed_reported_speech(source, expected):
    assert llm._polite_article_sentence(source) == expected


def test_beginner_does_not_select_publisher_address_or_a_reporter_as_an_outcome():
    body = '가온전자는 매출이 증가했다고 밝혔다. 매출은 100억원을 기록했다. 주소 : 서울시 가온로 1 전화 : 02-1234-5678 신문등록번호 가1234. 홍길동 한경닷컴 기자'
    result = llm._mock_rewrite_news('가온전자 매출', body)
    assert '100억원' in result['beginner']
    assert '주소' not in result['beginner'] and '홍길동' not in result['beginner']


def test_shorter_factual_outcome_is_preferred_to_a_long_reported_outcome():
    body = '가온전자 매출이 증가했다. 매출은 100억원을 기록했다. 관계자는 "해외 사업장과 국내 사업장의 모든 제품군을 대상으로 ' + '새로운 공급 계약을 확대하고 ' * 5 + '매출이 증가하고 있다"고 밝혔다.'
    result = llm._mock_rewrite_news('가온전자 매출', body)
    assert '100억원' in result['beginner']
    assert '관계자는' not in result['beginner']


def test_extra_short_analyst_evidence_is_kept_even_if_it_reduces_average_length():
    body = '가온전자는 해외 공장의 생산 일정을 조정하고 국내 부품 공급망을 확충했다고 밝혔다. 수요는 안정적이다. 내년 생산량은 10% 늘어날 것으로 예상했다.'
    result = llm._mock_rewrite_news('가온전자 생산 일정', body)
    for sentence in llm._select_article_facts('가온전자 생산 일정', body, 4, 'analyst'):
        assert sentence in result['analyst']
