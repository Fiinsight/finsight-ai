import json
from pathlib import Path
import pytest
from app.routers.chart import DocentRequest,rule_docent
CASES=json.loads((Path(__file__).parent/'fixtures/chart_docent_parity.json').read_text())['cases']
@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_java_authoritative_synthetic_contract(case):
    assert rule_docent(DocentRequest.model_validate(case['request']))==case['expected']
