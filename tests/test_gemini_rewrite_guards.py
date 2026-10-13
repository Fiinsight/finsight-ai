import json
import sys
from types import ModuleType, SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event, Lock
from unittest.mock import Mock
from zoneinfo import ZoneInfo
import pytest
from fastapi.testclient import TestClient
from app import config
from app.main import app
from app.services import llm_client, rewrite_budget
from app.services.llm_client import _call_gemini as generate_gemini
from test_rewrite_llm import VALID, SOURCE


@pytest.fixture
def generation(monkeypatch):
    monkeypatch.setattr(config, 'REWRITE_WITH_LLM', True)
    monkeypatch.setattr(config, 'MAX_DAILY_REWRITE_CALLS', 30)
    monkeypatch.setattr(config, 'MAX_REAL_LLM_CALLS_PER_PROCESS', 20)
    monkeypatch.setattr(config, 'REWRITE_MIN_INTERVAL_SECONDS', 6)
    current = [0.0]
    monkeypatch.setattr(llm_client.time, 'monotonic', lambda: current[0])
    monkeypatch.setattr(llm_client.time, 'sleep', lambda delay: current.__setitem__(0, current[0]+delay))
    call = Mock(return_value=json.dumps(VALID, ensure_ascii=False))
    monkeypatch.setattr(llm_client, '_call_gemini', call)
    return current, call


def test_concurrent_rewrites_serialize_and_leave_six_seconds_between_calls(generation):
    current, call = generation
    active = 0
    maximum = 0
    starts = []
    counter = Lock()
    def generate(*args, **kwargs):
        nonlocal active, maximum
        with counter:
            active += 1; maximum = max(maximum, active); starts.append(current[0])
        Event().wait(.02)
        with counter: active -= 1
        return json.dumps(VALID)
    call.side_effect = generate
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda key: llm_client.rewrite_news('수출 증가',SOURCE,str(key)),range(4)))
    assert maximum == 1 and len(starts) == 4
    assert all(right-left >= 6 for left,right in zip(starts,starts[1:]))
    assert all(result['mode']=='REWRITTEN' for result in results)


def test_429_refunds_daily_slot_and_article_is_retryable_then_circuit_stops(generation,monkeypatch):
    _, call = generation
    class QuotaError(Exception): code = 429
    call.side_effect = QuotaError('RESOURCE_EXHAUSTED quota')
    now = datetime(2026,10,13,23,58,tzinfo=ZoneInfo('Asia/Seoul'))
    monkeypatch.setattr(rewrite_budget,'_now',lambda:now)
    for count in range(1,4):
        result=llm_client.rewrite_news('수출 증가',SOURCE,'same')
        assert result['mode']=='EXCERPT' and result['retryable']
        status=rewrite_budget.status()
        assert status['rewriteUsedCalls']==0 and status['rewrite429Count']==count
    assert status['rewriteStoppedToday'] and status['rewriteFailureCount']==3 and status['rewriteLast429At']
    assert llm_client.rewrite_news('새 기사',SOURCE,'new')['mode']=='EXCERPT'
    assert call.call_count==3
    now += timedelta(days=1)
    call.side_effect=None
    assert llm_client.rewrite_news('수출 증가',SOURCE,'same')['mode']=='REWRITTEN'
    assert rewrite_budget.status()['rewriteSuccessCount']==1
    assert not rewrite_budget.status()['rewriteStoppedToday']


def test_quota_response_crossing_midnight_counts_on_new_kst_day(monkeypatch):
    now = datetime(2026, 10, 13, 23, 59, 59, tzinfo=ZoneInfo('Asia/Seoul'))
    monkeypatch.setattr(rewrite_budget, '_now', lambda: now)
    assert rewrite_budget.reserve('midnight', {'mode': 'EXCERPT'})[0]
    now += timedelta(seconds=2)
    rewrite_budget.finish('midnight', {'mode': 'EXCERPT', 'retryable': True}, failed=True, quota=True)
    assert rewrite_budget.status()['rewrite429Count'] == 1
    assert rewrite_budget.status()['rewriteUsedCalls'] == 0


@pytest.mark.parametrize('provider',['claude','openai','ollama','unknown'])
def test_collection_rejects_non_gemini_provider_without_call(generation,monkeypatch,provider):
    _, call = generation
    monkeypatch.setattr(config,'LLM_PROVIDER',provider)
    assert llm_client.rewrite_news('수출 증가',SOURCE,'one')['mode']=='EXCERPT'
    call.assert_not_called()


def test_daily_cap_and_process_cap_both_hold(generation,monkeypatch):
    _, call = generation
    for key in range(21):llm_client.rewrite_news('수출 증가',SOURCE,str(key))
    assert call.call_count==20 and llm_client._real_llm_calls==20
    assert rewrite_budget.status()['rewriteUsedCalls']<=30
    monkeypatch.setattr(llm_client,'_real_llm_calls',0)
    for key in range(21,41):llm_client.rewrite_news('수출 증가',SOURCE,str(key))
    assert call.call_count<=30
    assert rewrite_budget.status()['rewriteUsedCalls']==30


def test_invalid_numbers_and_non_eligible_article_stay_excerpt(generation):
    _, call = generation
    bad=json.loads(json.dumps(VALID));bad['beginner']=bad['beginner'].replace('261','999')
    call.return_value=json.dumps(bad)
    result=llm_client.rewrite_news('수출 증가',SOURCE,'bad')
    assert result['mode']=='EXCERPT' and not result['retryable']
    assert rewrite_budget.status()['rewriteFailureCount']==1
    llm_client.rewrite_news('수출 증가',SOURCE,'outside-top-ten',allow_llm=False)
    assert call.call_count==1
    assert rewrite_budget.status()['rewriteUsedCalls']==1


def test_other_features_never_dispatch_and_health_has_no_secrets(generation,monkeypatch):
    _, call = generation
    client=TestClient(app)
    for route,payload in [('/ai/terms/explain',{'term':'금리','article_context':'금리가 변했다.'}),('/ai/feedback/judgement',{'news_id':1,'user_choice':'UP','market_result':'UP'})]:
        assert client.post(route,json=payload).status_code == 200
    llm_client.explain_term('금리','금리가 변했다.')
    llm_client.generate_feedback('금리 변화','UP','UP',1.2)
    llm_client.analyze_market_impact('금리 변화',SOURCE,None)
    call.assert_not_called()
    monkeypatch.setattr(config,'GEMINI_API_KEY','test-secret-not-a-real-key')
    health=client.get('/health').json()
    assert health['rewriteEnabled'] and health['provider']=='gemini'
    assert health['rewriteDailyLimit']==30 and health['processCallLimit']==20
    assert 'test-secret-not-a-real-key' not in json.dumps(health)


def test_gemini_rewrite_requests_json_without_changing_other_features(monkeypatch):
    def configuration(**options):
        return SimpleNamespace(**{'response_mime_type': None, 'temperature': None, **options})
    google = ModuleType('google')
    genai = ModuleType('google.genai')
    genai.types = SimpleNamespace(GenerateContentConfig=configuration)
    google.genai = genai
    monkeypatch.setitem(sys.modules, 'google', google)
    monkeypatch.setitem(sys.modules, 'google.genai', genai)
    client = Mock()
    client.models.generate_content.return_value.text = '{}'
    monkeypatch.setattr(llm_client, '_get_gemini_client', lambda: client)
    # Exercise the SDK configuration without an HTTP request.
    generate_gemini(llm_client._build_rewrite_prompt('수출 증가', SOURCE), 2200)
    options = client.models.generate_content.call_args.kwargs['config']
    assert options.response_mime_type == 'application/json' and options.temperature == 0
    generate_gemini('용어 설명', 1024)
    assert client.models.generate_content.call_args.kwargs['config'].response_mime_type is None
