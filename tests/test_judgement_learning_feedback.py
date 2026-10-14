import json
import pytest
from unittest.mock import patch
from app import config
from app.services import llm_client, feedback_budget


def feedback(**updates):
    context = dict(news_title='삼성전자 호실적', related_symbol='005930', related_symbol_name='삼성전자',
                   comparison_date='2026-10-13', judgement_close=100, comparison_close=95.6,
                   index_name='코스피', index_change_percent=-3.7, concept_term='금리', concept_definition='돈을 빌리는 비용')
    context.update(updates)
    return llm_client.generate_feedback('매출이 증가했다.', 'DOWN', 'DOWN', -4.4, **context)


@pytest.mark.parametrize('index,phrase', [(-3.41,'시장 전체 흐름과 함께'),(-3.4,'개별 소식의 영향'),(-3.39,'개별 소식의 영향')])
def test_market_difference_and_article_signal(monkeypatch, index, phrase):
    monkeypatch.setattr(config,'USE_REAL_LLM',False)
    monkeypatch.setattr(config,'FEEDBACK_WITH_LLM',False)
    result = feedback(index_change_percent=index)
    assert phrase in result['summary']
    assert '시장 전체 하락에 묻혔을 수' in result['reasons'][0]['detail']
    assert '-4.40%' in result['reasons'][2]['detail'] and f'{index:+.2f}%' in result['reasons'][2]['detail']
    assert '정확한 판단' not in result['headline']
    assert result['conceptTerm']=='금리'


def test_gemini_opt_in_isolated_and_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(config,'USE_REAL_LLM',False)
    monkeypatch.setattr(config,'FEEDBACK_WITH_LLM',True)
    monkeypatch.setattr(config,'LLM_PROVIDER','gemini')
    monkeypatch.setattr(config,'FEEDBACK_LEDGER_PATH',str(tmp_path/'feedback.db'))
    fallback = llm_client._mock_generate_feedback('매출이 증가했다.','DOWN','DOWN',-4.4,news_title='삼성전자 호실적',related_symbol='005930',related_symbol_name='삼성전자',comparison_date='2026-10-13',judgement_close=100,comparison_close=95.6,index_name='코스피',index_change_percent=-3.7,concept_term='금리',concept_definition='돈을 빌리는 비용')
    with patch.object(llm_client,'_call_gemini',return_value=json.dumps(fallback,ensure_ascii=False)) as gemini, patch.object(llm_client,'_call_llm',side_effect=AssertionError('paid dispatch')), patch.object(llm_client,'_reserve_process_llm_call') as ceiling, patch('app.services.rewrite_budget.status',return_value={'rewriteStoppedToday':False}), patch.object(llm_client.time,'sleep'):
        first = feedback(); second = feedback()
    assert first['mode']=='LLM' and second==first
    gemini.assert_called_once(); ceiling.assert_called_once()


@pytest.mark.parametrize('provider',['claude','openai','ollama'])
def test_feedback_flag_never_opens_paid_provider(monkeypatch, provider):
    monkeypatch.setattr(config,'USE_REAL_LLM',False)
    monkeypatch.setattr(config,'FEEDBACK_WITH_LLM',True)
    monkeypatch.setattr(config,'LLM_PROVIDER',provider)
    with patch.object(llm_client,'_call_gemini',side_effect=AssertionError()), patch.object(llm_client,'_call_llm',side_effect=AssertionError()):
        assert feedback()['mode']=='RULE'


def test_daily_fifty_and_paid_process_ceiling_still_apply(monkeypatch, tmp_path):
    monkeypatch.setattr(config,'FEEDBACK_LEDGER_PATH',str(tmp_path/'feedback.db'))
    monkeypatch.setattr(config,'MAX_DAILY_FEEDBACK_CALLS',50)
    for n in range(50): assert feedback_budget.reserve(str(n),{'mode':'RULE'})[0]
    assert not feedback_budget.reserve('51',{'mode':'RULE'})[0]
    monkeypatch.setattr(config,'USE_REAL_LLM',False); monkeypatch.setattr(config,'FEEDBACK_WITH_LLM',True)
    monkeypatch.setattr(config,'LLM_PROVIDER','gemini')
    monkeypatch.setattr(config,'FEEDBACK_LEDGER_PATH',str(tmp_path/'other.db'))
    with patch.object(llm_client,'_real_llm_calls',config.MAX_REAL_LLM_CALLS_PER_PROCESS), patch.object(llm_client,'_call_gemini') as gemini, patch('app.services.rewrite_budget.status',return_value={'rewriteStoppedToday':False}):
        assert feedback()['mode']=='RULE'
    gemini.assert_not_called()


def test_opt_in_number_failure_is_rule_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(config,'FEEDBACK_WITH_LLM',True);monkeypatch.setattr(config,'LLM_PROVIDER','gemini')
    monkeypatch.setattr(config,'FEEDBACK_LEDGER_PATH',str(tmp_path/'bad.db'))
    with patch.object(llm_client,'_call_gemini',return_value='{"verdict":"CORRECT","summary":"999%"}'), patch.object(llm_client,'_reserve_process_llm_call'), patch('app.services.rewrite_budget.status',return_value={'rewriteStoppedToday':False}), patch.object(llm_client.time,'sleep'):
        assert feedback()['mode']=='RULE'

@pytest.mark.parametrize('title,summary,needle',[
    ('호실적 발표','매출이 전년보다 증가했다. 영업이익이 늘었다.','이익에 대한 기대를 높여'),
    ('실적 부진','매출이 전년보다 감소했다. 영업이익도 줄었다.','이익에 대한 기대를 낮춰'),
    ('외국인 매도 확대','외국인이 국내 주식을 순매도했다. 매도 규모가 늘었다.','매도 압력'),
    ('기준금리 상승','기준금리 상승으로 금융 환경이 달라졌다. 자금 비용을 살폈다.','돈을 빌리는 비용'),
])
def test_feedback_explains_source_to_price_channel_without_real_call(monkeypatch,title,summary,needle):
    monkeypatch.setattr(config,'USE_REAL_LLM',False);monkeypatch.setattr(config,'FEEDBACK_WITH_LLM',False)
    with patch.object(llm_client,'_call_llm',side_effect=AssertionError()),patch.object(llm_client,'_call_gemini',side_effect=AssertionError()):
        result=llm_client.generate_feedback(summary,'UP','UP',2,news_title=title,related_symbol='005930',related_symbol_name='삼성전자')
    detail=result['reasons'][0]['detail']
    assert needle in detail
    assert '때문에 올랐' not in detail and '원인입니다' not in detail
    assert 2 <= llm_client._feedback_sentence_count(detail) <= 4
