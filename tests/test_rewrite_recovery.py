import copy
import json
from datetime import datetime, timedelta
from unittest.mock import Mock
from zoneinfo import ZoneInfo
import pytest
from app import config
from app.services import llm_client, rewrite_budget
from test_rewrite_llm import VALID, SOURCE


@pytest.mark.parametrize('summary,source,valid', [
    ('1000억 원', '투자액은 1,000억원이다.', True),
    ('3퍼센트', '금리는 3%다.', True),
    ('0.25%포인트', '금리는 0.25%p 내렸다.', True),
    ('３％', '금리는 3%다.', True),
    ('3.00%', '금리는 3%다.', True),
    ('3%', '변동률은 -3%다.', False),
    ('-3%', '변동률은 3%다.', False),
    ('0.25%', '금리는 0.25%p 내렸다.', False),
    ('1001억원', '투자액은 1,000억원이다.', False),
    ('34명', '각 팀은 3 4명이다.', False),
    ('3%', '변동률은 −3%다.', False),
    ('-3%', '변동률은 −3%다.', True),
    ('3%', '변동률은 - 3%다.', False),
])
def test_equivalent_formats_preserve_value_unit_and_sign(summary, source, valid):
    assert llm_client._numbers_in_source(summary, source) is valid


def test_first_json_object_ignores_explanatory_trailing_braces():
    assert llm_client._extract_json('```json\n{"result":"brace } in string"}\n```\n설명: }') == {'result':'brace } in string'}


def test_one_extra_sentence_and_repairable_polite_ending_are_accepted():
    data = copy.deepcopy(VALID)
    data['beginner'] = data['beginner'].replace('늘었어요', '늘었다', 1) + ' 원문의 흐름도 함께 살펴봐요.'
    result = llm_client._validated_rewrite(data, SOURCE)
    assert '늘었어요.' in result['beginner']
    assert len(llm_client._split_sentences(result['beginner'])) == 6


@pytest.fixture
def generation(monkeypatch):
    monkeypatch.setattr(config, 'REWRITE_WITH_LLM', True)
    monkeypatch.setattr(config, 'REWRITE_MIN_INTERVAL_SECONDS', 0)
    call = Mock(return_value=json.dumps(VALID))
    monkeypatch.setattr(llm_client, '_call_gemini', call)
    return call


def test_validation_retries_once_inside_the_daily_budget(generation, monkeypatch):
    monkeypatch.setattr(config, 'MAX_DAILY_REWRITE_CALLS', 2)
    bad = copy.deepcopy(VALID)
    bad['beginner'] = bad['beginner'].replace('261', '999')
    generation.side_effect = [json.dumps(bad), json.dumps(VALID)]
    assert llm_client.rewrite_news('수출 증가', SOURCE, 'retry')['mode'] == 'REWRITTEN'
    assert generation.call_count == 2
    assert rewrite_budget.status()['rewriteUsedCalls'] == 2


def test_validation_retry_cannot_exceed_daily_limit(generation, monkeypatch):
    monkeypatch.setattr(config, 'MAX_DAILY_REWRITE_CALLS', 1)
    generation.return_value = '{}'
    assert llm_client.rewrite_news('수출 증가', SOURCE, 'limited')['mode'] == 'EXCERPT'
    assert generation.call_count == 1
    assert rewrite_budget.status()['rewriteUsedCalls'] == 1


def test_prompt_revision_can_recover_a_validation_failure(generation, monkeypatch):
    generation.return_value = '{}'
    assert llm_client.rewrite_news('수출 증가', SOURCE, 'versioned')['mode'] == 'EXCERPT'
    used = generation.call_count
    assert llm_client.rewrite_news('수출 증가', SOURCE, 'versioned')['mode'] == 'EXCERPT'
    assert generation.call_count == used
    monkeypatch.setattr(llm_client, 'REWRITE_PROMPT_VERSION', 'qa-next-prompt', raising=False)
    generation.return_value = json.dumps(VALID)
    assert llm_client.rewrite_news('수출 증가', SOURCE, 'versioned')['mode'] == 'REWRITTEN'


def test_crashed_reservation_expires_without_refunding_its_daily_slot(monkeypatch):
    now = datetime(2026,11,11,10,tzinfo=ZoneInfo('Asia/Seoul'))
    monkeypatch.setattr(rewrite_budget, '_now', lambda: now)
    assert rewrite_budget.reserve('crashed', {'mode':'EXCERPT'})[0]
    assert not rewrite_budget.reserve('crashed', {'mode':'EXCERPT'})[0]
    now += timedelta(minutes=11)
    assert rewrite_budget.reserve('crashed', {'mode':'EXCERPT'})[0]
    assert rewrite_budget.status()['rewriteUsedCalls'] == 2


def test_expired_reservation_cannot_bypass_the_daily_ceiling(monkeypatch):
    now = datetime(2026,11,11,10,tzinfo=ZoneInfo('Asia/Seoul'))
    monkeypatch.setattr(rewrite_budget, '_now', lambda: now)
    monkeypatch.setattr(config, 'MAX_DAILY_REWRITE_CALLS', 1)
    assert rewrite_budget.reserve('crashed', {'mode':'EXCERPT'})[0]
    now += timedelta(minutes=11)
    assert not rewrite_budget.reserve('crashed', {'mode':'EXCERPT'})[0]
    assert rewrite_budget.status()['rewriteUsedCalls'] == 1
