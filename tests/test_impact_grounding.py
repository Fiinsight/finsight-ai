import json
import pytest
from app import config
from app.services import llm_client as llm

TITLE = '기업 실적 발표'
BODY = '기업의 영업이익은 1,000억원으로 증가했다. 해외 매출이 20% 늘어나 실적 개선에 기여했다.'

@pytest.mark.parametrize('evidence', [
    '기업은 내년 전기차 시장을 독점할 것으로 확실히 전망된다.',
    '기업의 영업이익은 9,000억원으로 증가했다.',
    '기업', '있다',
])
def test_generic_or_invented_evidence_falls_back(monkeypatch, evidence):
    monkeypatch.setattr(config, 'USE_REAL_LLM', True)
    monkeypatch.setattr(llm, '_call_llm', lambda *a, **k: json.dumps({'direction':'POSITIVE','confidence':.9,'evidence':[evidence]}))
    assert llm.analyze_market_impact(TITLE, BODY)['basis'] == 'RULE_BASED_FALLBACK'

@pytest.mark.parametrize('evidence', ['영업이익은 1000억 원으로 증가했다.', '해외 매출이 20퍼센트 늘어나 실적 개선에 기여했다.'])
def test_normalized_near_source_evidence_is_kept(monkeypatch, evidence):
    monkeypatch.setattr(config, 'USE_REAL_LLM', True)
    monkeypatch.setattr(llm, '_call_llm', lambda *a, **k: json.dumps({'direction':'POSITIVE','confidence':.9,'evidence':[evidence]}))
    assert llm.analyze_market_impact(TITLE, BODY)['basis'] == 'LLM'

def test_bad_evidence_is_removed_even_when_another_item_is_grounded(monkeypatch):
    monkeypatch.setattr(config, 'USE_REAL_LLM', True)
    good = '해외 매출이 20% 늘어나 실적 개선에 기여했다.'
    monkeypatch.setattr(llm, '_call_llm', lambda *a, **k: json.dumps({'evidence':[good, '기업의 영업이익은 9000억원으로 증가했다.']}))
    assert llm.analyze_market_impact(TITLE, BODY)['evidence'] == [good]
