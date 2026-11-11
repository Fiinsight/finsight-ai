import json
from pathlib import Path
import pytest
from app.services.ml_sentiment import predict_rule_sentiment
from app.services.llm_client import _mock_market_impact
CASES=json.loads((Path(__file__).parents[1]/'app/services/rules/sentiment-cases.json').read_text())
@pytest.mark.parametrize('row',CASES,ids=lambda row:row['title'])
def test_same_label_across_rule_entry_points(row):
    assert predict_rule_sentiment(row['title'],'')['label']==row['label']
    assert _mock_market_impact(row['title'],'',None)['direction']==row['label']
