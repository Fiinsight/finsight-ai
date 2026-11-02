"""Offline grammar regressions plus short, source-labelled collected-news excerpts."""
import json
from pathlib import Path
import re

import pytest

from app.services import llm_client


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(llm_client.config, 'USE_REAL_LLM', False)
    monkeypatch.setattr(llm_client.config, 'REWRITE_WITH_LLM', False)
    def forbidden(*args, **kwargs):
        pytest.fail('EXCERPT must not call a model')
    for name in ('_call_llm', '_call_gemini', '_call_claude', '_call_ollama'):
        monkeypatch.setattr(llm_client, name, forbidden)


def rewrite(body):
    result = llm_client.rewrite_news('경제 기사', body, allow_llm=False)
    assert result['mode'] == 'EXCERPT'
    return result


def beginner_text(result):
    return result['beginner'] + '\n' + result['importanceReasons']['beginner']


def assert_grammar(result):
    text = beginner_text(result)
    assert not re.search(r'어요(?:고|라고)', text)
    assert not any(bad in text for bad in ('요인를', '시점를', '환율를', '영업이익를', '금리을', '수출와', '예상를', '예상가'))
    reason = result['importanceReasons']['beginner']
    if ' 확인해요.' in reason:
        check = reason.split('예요. ', 1)[1].split(' 확인해요.', 1)[0]
        phrase, particle = check[:-1], check[-1]
        assert llm_client._with_particle(phrase, '을/를') == phrase + particle


@pytest.mark.parametrize(('body', 'expected'), [
    ('삼성전자(005930)가 3분기 영업이익 12조1000억원을 기록했다고 31일 밝혔다.', '12조1000억원을 기록했다고 31일 밝혔어요.'),
    ('매출이 지난해보다 증가할 것으로 내다봤다.', '증가할 것으로 내다봤어요.'),
    ('관계자는 수출이 늘었다고 말했다.', '늘었다고 말했어요.'),
    ('거래가 중단됐다고 전했다.', '중단됐다고 전했어요.'),
    ('주가는 상승했다고 밝혔다.', '상승했다고 밝혔어요.'),
    ('관계자는 "매출이 증가했다"라고 말했다.', '"매출이 증가했다"라고 말했어요.'),
])
def test_reported_speech_only_changes_the_sentence_ending(body, expected):
    result = rewrite(body)
    assert expected in result['beginner']
    assert body in result['normal']
    assert_grammar(result)


@pytest.mark.parametrize(('word', 'pair', 'expected'), [
    ('영업이익', '을/를', '영업이익을'), ('금리', '을/를', '금리를'),
    ('수출', '은/는', '수출은'), ('주가', '은/는', '주가는'),
    ('실적', '이/가', '실적이'), ('매출추이', '이/가', '매출추이가'),
    ('수출', '과/와', '수출과'), ('금리', '과/와', '금리와'),
    ('AI', '을/를', 'AI(을/를)'),
])
def test_particles(word, pair, expected):
    assert llm_client._with_particle(word, pair) == expected


@pytest.mark.parametrize(('body', 'expected'), [
    ('매출과 영업이익이 증가했다.', '일회성 요인을 확인해요.'),
    ('수출 계약이 늘었다.', '실제 실적을 확인해요.'),
    ('원재료 비용이 증가했다.', '실제 이익 변화를 확인해요.'),
    ('국내 기준금리가 0.25%포인트 상승했다.', '금리 적용 시점을 확인해요.'),
    ('원/달러 환율이 1350원으로 하락했다.', '적용 환율을 확인해요.'),
])
def test_investment_point_particles(body, expected):
    result = rewrite(body)
    assert expected in result['importanceReasons']['beginner']
    assert_grammar(result)


@pytest.mark.parametrize(('body', 'expected'), [
    ('실적은 컨센서스를 웃돌았다.', '시장 전문가들의 예상을'),
    ('컨센서스가 상향됐다.', '시장 전문가들의 예상이'),
    ('컨센서스와 비교했다.', '시장 전문가들의 예상과'),
    ('전년 동기는 비교 기준이다.', '지난해 같은 기간은'),
])
def test_simplified_terms_keep_the_right_particle(body, expected):
    result = rewrite(body)
    assert expected in result['beginner']
    assert_grammar(result)


@pytest.mark.parametrize('code', ['(005930)', '[005930]', ' 005930 ', ' 005930,'])
def test_beginner_removes_stock_codes_without_changing_years_or_amounts(code):
    body = f'삼성전자{code} 2026년 매출은 123456원, 영업이익은 12조1000억원을 기록했다고 밝혔다.'
    result = rewrite(body)
    text = beginner_text(result)
    assert '005930' not in text
    assert '2026년' in text and '123456원' in text and '12조1000억원' in text
    assert '005930' in result['normal']
    assert_grammar(result)


@pytest.mark.parametrize('amount', ['123456 원', '123456 달러', '123456.78원', '123456,000원', '$123456', '$ 123456', '₩ 123456', '2026년'])
def test_stock_code_cleanup_preserves_financial_numbers(amount):
    assert amount in llm_client._strip_stock_codes(f'금액은 {amount}이며 코드는 005930.')
    assert '005930' not in llm_client._strip_stock_codes('코드 005930.')


ARTICLES = json.loads((Path(__file__).parent / 'fixtures/collected_excerpt_articles.json').read_text())


@pytest.mark.parametrize('article', ARTICLES, ids=lambda article: str(article['id']))
def test_twenty_collected_article_excerpts_have_no_generated_grammar_errors(article):
    assert len(ARTICLES) == 20 and article['source'] and article['url'].startswith('https://')
    assert len(article['body']) <= 300
    result = llm_client.rewrite_news(article['title'], article['body'], allow_llm=False)
    assert result['mode'] == 'EXCERPT'
    assert_grammar(result)
    # The fixtures' standalone six-digit numbers are ticker codes, not monetary amounts.
    assert not re.search(r'(?<!\d)\d{6}(?!\d)', beginner_text(result))


def test_multi_stock_simplification_does_not_drop_years_or_monetary_facts():
    result = rewrite('2026년 삼성전자[005930](4.12%)와 SK하이닉스[000660](5.1%)의 매출은 123456원이었다.')
    assert '2026년' in result['beginner'] and '123456원' in result['beginner']
    assert '005930' not in beginner_text(result) and '000660' not in beginner_text(result)
