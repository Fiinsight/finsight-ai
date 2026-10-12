from unittest.mock import patch
import json
import pytest
from app.routers.chart import DocentRequest, docent
from app.services import llm_client
from app import config

@pytest.fixture(autouse=True)
def storage(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DOCENT_LEDGER_PATH',str(tmp_path/'docent.db'))
    monkeypatch.setattr(config,'DOCENT_WITH_LLM',False)

def request(relation='DIRECT',**extra):
    data=dict(symbol='005930',symbol_name='삼성전자',date='2026-10-07',period='D',change_percent=3.25,
              news=[] if relation=='NONE' else [dict(news_id=1,title='삼성전자 호실적 발표',summary='삼성전자의 영업이익이 전년 동기보다 12.5% 증가했다.',published_at='2026-10-07T10:00:00+09:00',source='뉴스',relation=relation)])
    return DocentRequest(**{**data,**extra})

@pytest.mark.parametrize('relation',['DIRECT','MARKET','NONE'])
def test_rule_relations_and_no_causal_claims(relation):
    with patch.object(llm_client,'_call_llm') as paid:
        result=docent(request(relation))
    assert result['relation']==relation and result['mode']=='RULE'
    assert '때문에' not in ' '.join(str(v) for v in result.values())
    assert result['marketImpact'] and result['possibleReason']
    if relation=='DIRECT': assert '+3.25%' in result['possibleReason'] and '호재' in result['possibleReason']
    if relation=='MARKET': assert '%' not in result['possibleReason']
    paid.assert_not_called()

def test_market_numbers_only_when_supplied():
    assert '코스피 -1.20%' in docent(request('MARKET',index_name='코스피',index_change_percent=-1.2))['possibleReason']

def test_persistent_reuse_and_daily_ceiling(monkeypatch):
    monkeypatch.setattr(config,'DOCENT_WITH_LLM',True);monkeypatch.setattr(config,'MAX_DAILY_DOCENT_CALLS',1)
    good={'whatHappened':'삼성전자 영업이익이 12.5% 증가했어요.','possibleReason':'실적 소식이 영향을 줬을 수 있어요.','marketImpact':'기업 가치 평가에 영향을 줬을 수 있어요.'}
    with patch.object(llm_client,'_call_llm',return_value=json.dumps(good,ensure_ascii=False)) as paid:
        first=docent(request()); assert first['mode']=='LLM'
        assert docent(request())==first
        assert docent(request(date='2026-10-08'))['mode']=='RULE'
        paid.assert_called_once()

@pytest.mark.parametrize('bad',['number','certainty','error'])
def test_invalid_llm_falls_back_and_never_retries(monkeypatch,bad):
    monkeypatch.setattr(config,'DOCENT_WITH_LLM',True)
    payload={'whatHappened':'매출이 999% 증가했어요.','possibleReason':'실적이 영향을 줬을 수 있어요.','marketImpact':'가치 평가에 영향을 줬을 수 있어요.'}
    if bad=='certainty':payload.update(whatHappened='실적 소식이 있었어요.',possibleReason='실적 때문에 올랐습니다.')
    with patch.object(llm_client,'_call_llm',return_value=json.dumps(payload),side_effect=TimeoutError() if bad=='error' else None) as paid:
        assert docent(request())['mode']=='RULE';assert docent(request())['mode']=='RULE';paid.assert_called_once()

def test_minute_never_calls_llm_and_level_has_separate_cache(monkeypatch):
    monkeypatch.setattr(config,'DOCENT_WITH_LLM',True)
    with patch.object(llm_client,'_call_llm') as paid:
        assert docent(request(period='MINUTE',date='2026-10-07T10:00:00'))['mode']=='RULE'
        assert docent(request('NONE',level='analyst'))['mode']=='RULE'
    paid.assert_not_called()


def test_unavailable_storage_does_not_spend_a_call(tmp_path,monkeypatch):
    blocked=tmp_path/'file';blocked.write_text('not a directory')
    monkeypatch.setattr(config,'DOCENT_LEDGER_PATH',str(blocked/'docent.db'))
    monkeypatch.setattr(config,'DOCENT_WITH_LLM',True)
    with patch.object(llm_client,'_call_llm') as paid:
        assert docent(request())['mode']=='RULE'
    paid.assert_not_called()

def test_cache_survives_flag_change_and_new_level_is_distinct(monkeypatch):
    first=docent(request())
    monkeypatch.setattr(config,'DOCENT_WITH_LLM',True)
    with patch.object(llm_client,'_call_llm',side_effect=TimeoutError()) as paid:
        assert docent(request())==first
        docent(request(level='analyst'))
    paid.assert_called_once()


def test_http_contract_and_input_limits():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers.chart import router
    app=FastAPI();app.include_router(router,prefix='/ai/chart')
    client=TestClient(app)
    payload=request().model_dump(mode='json')
    response=client.post('/ai/chart/docent',json=payload)
    assert response.status_code==200
    assert response.json()['newsId']==1 and response.json()['mode']=='RULE'
    assert client.post('/ai/chart/docent',json={**payload,'news':payload['news']*4}).status_code==422
    assert client.post('/ai/chart/docent',json={**payload,'date':'bad'}).status_code==422
