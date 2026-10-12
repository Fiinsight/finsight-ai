import json
from unittest.mock import patch
import pytest
from app import config
from app.services import llm_client

SOURCE = '수출액은 261억달러로 증가했다. 지난해보다 102% 늘었다. 물류 비용은 5.5% 올랐다. 앞으로 비용 부담이 우려된다.'
VALID = {'beginner': '수출액이 261억달러로 늘었어요. 수출(해외에 상품을 파는 일)이 증가했어요. 지난해보다 102% 늘었어요. 물류 비용도 올랐어요. 비용 부담을 함께 확인해야 해요.', 'normal': '[사실] 수출액은 261억달러다. 지난해보다 102% 증가했다. [전망] 비용 부담이 우려된다.', 'analyst': {'evidence': '수출액이 증가했다.', 'figures': '수출액은 261억달러로 지난해보다 102% 늘었다.', 'risk': '물류 비용 부담의 지속 여부를 확인해야 한다.'}}

@pytest.mark.parametrize('summary,valid', [('261억달러 증가', True), ('102% 증가', True), ('5% 상승', False), ('262억달러 증가', False), ('5.5% 상승', True), ('15.5% 상승', False)])
def test_source_numbers_are_exact_tokens(summary, valid):
    assert llm_client._numbers_in_source(summary, SOURCE) is valid

def test_rewrite_is_one_call_and_persists_daily_budget_and_article_identity(tmp_path):
    with patch.object(config, 'REWRITE_WITH_LLM', True), patch.object(config, 'USE_REAL_LLM', False), patch.object(config, 'MAX_DAILY_REWRITE_CALLS', 1), patch.object(config, 'REWRITE_LEDGER_PATH', str(tmp_path / 'ledger.db')), patch.object(llm_client, '_call_llm', return_value=json.dumps(VALID, ensure_ascii=False)) as llm:
        first = llm_client.rewrite_news('수출 증가', SOURCE, 'article-1')
        assert first['mode'] == 'REWRITTEN'
        assert llm_client.rewrite_news('수출 증가', SOURCE, 'article-1') == first
        assert llm_client.rewrite_news('다른 기사', SOURCE, 'article-2')['mode'] == 'EXCERPT'
        llm.assert_called_once()

@pytest.mark.parametrize('failure', ['numeric', 'duplicate', 'timeout', 'style'])
def test_validation_and_failure_fall_back_without_retry(tmp_path, failure):
    data = json.loads(json.dumps(VALID))
    if failure == 'numeric': data['beginner'] = data['beginner'].replace('261', '999')
    if failure == 'style': data['beginner'] = data['beginner'].replace('늘었어요', '늘었다')
    if failure == 'duplicate': data['analyst']['risk'] = data['analyst']['evidence']
    with patch.object(config, 'REWRITE_WITH_LLM', True), patch.object(config, 'REWRITE_LEDGER_PATH', str(tmp_path / 'ledger.db')), patch.object(llm_client, '_call_llm', side_effect=TimeoutError() if failure == 'timeout' else None, return_value=json.dumps(data)) as llm:
        assert llm_client.rewrite_news('수출 증가', SOURCE, 'same')['mode'] == 'EXCERPT'
        assert llm_client.rewrite_news('수출 증가', SOURCE, 'same')['mode'] == 'EXCERPT'
        llm.assert_called_once()

def test_other_llm_flag_does_not_enable_rewrite():
    with patch.object(config, 'REWRITE_WITH_LLM', False), patch.object(config, 'USE_REAL_LLM', True), patch.object(llm_client, '_call_llm') as llm:
        assert llm_client.rewrite_news('수출 증가', SOURCE)['mode'] == 'EXCERPT'
        llm.assert_not_called()

def test_fallback_lead_and_analysis_sections_do_not_duplicate():
    body = '수출이 12.5% 증가했다. 실적 전망에는 불확실성이 있다. 비용은 5.5% 늘었다. 판매가 3% 늘어난 결과를 기록했다.'
    beginner = llm_client._reading_summary('실적 전망과 수출', body, 'beginner')
    assert beginner.startswith('수출이 12.5% 늘었어요.')
    assert '3%' in beginner
    analyst = llm_client._reading_summary('실적 전망과 수출', body, 'analyst')
    blocks = analyst.split('\n\n')
    values = [block.split('\n', 1)[1] for block in blocks]
    assert len(set(values)) == 3
    assert '불확실성' in values[2]
    assert '5.5%' in values[1]

def test_korean_number_units_cannot_be_changed():
    assert llm_client._numbers_in_source('5천억원', '투자는 5천억원이다.')
    assert not llm_client._numbers_in_source('5천원', '투자는 5천억원이다.')
    assert not llm_client._numbers_in_source('0.5%', '금리는 0.5%p 올랐다.')
