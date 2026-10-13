from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from app.services import ml_sentiment
from app.routers.chart import DocentRequest, rule_docent
from app.routers.feedback import FeedbackRequest, judgement_feedback
from scripts.score_sentiment import changes, main
from ml.sentiment import classification_metrics


class Probabilities(list):
    def argmax(self):
        return self.index(max(self))


@pytest.mark.parametrize('probabilities,label', [([.1,.2,.7],'POSITIVE'),([.59,.2,.21],'NEUTRAL'),([.6,.2,.2],'NEGATIVE')])
def test_local_model_mapping_and_confidence(monkeypatch, probabilities, label):
    model = MagicMock()
    model.config.id2label = {0:'negative',1:'neutral',2:'positive'}
    model.return_value = SimpleNamespace(logits=None)
    torch = MagicMock()
    torch.softmax.return_value = [Probabilities(probabilities)]
    monkeypatch.setattr(ml_sentiment,'_load_model',lambda:(MagicMock(return_value={}),model,torch))
    result = ml_sentiment.predict_sentiment('제목','리드')
    assert result['label'] == label
    assert result['basis'] == 'LOCAL_FINANCIAL_TRANSFORMER'


def test_missing_or_broken_model_uses_existing_free_rules(monkeypatch):
    monkeypatch.setattr(ml_sentiment,'_load_model',lambda:None)
    assert ml_sentiment.predict_sentiment('금리 인상','')['label']=='NEGATIVE'
    broken=MagicMock(side_effect=RuntimeError('broken'))
    monkeypatch.setattr(ml_sentiment,'_load_model',lambda:(broken,MagicMock(),MagicMock()))
    assert ml_sentiment.predict_sentiment('실적 증가','')['basis']=='RULE_BASED_FALLBACK'


def test_batch_is_readonly_without_apply_and_counts_changes(monkeypatch,capsys):
    from contextlib import contextmanager
    import scripts.score_sentiment as batch
    row={'id':1,'title':'호실적','raw_content':'매출이 늘었다. 다른 내용.','sentiment_hint':'POSITIVE','sentiment_confidence':.8}
    assert changes([row],lambda title,lead:{'label':'POSITIVE','confidence':.8})==[]
    low=changes([row],lambda title,lead:{'label':'POSITIVE','confidence':.59})
    assert low[0]['label']=='NEUTRAL'
    calls=[]
    @contextmanager
    def db(**kwargs):
        calls.append(kwargs)
        yield SimpleNamespace(execute=lambda *args:SimpleNamespace(fetchall=lambda:[row]))
    monkeypatch.setattr(batch,'database',db)
    monkeypatch.setattr(batch,'changes',lambda rows:low)
    monkeypatch.setattr('sys.argv',['score_sentiment'])
    main()
    assert calls==[{}]
    assert '"would_change": 1' in capsys.readouterr().out


@pytest.mark.parametrize('confidence,contains',[(.59,False),(.6,True)])
def test_docent_confidence_never_changes_relation(confidence,contains):
    request=DocentRequest(symbol='005930',symbol_name='삼성전자',date='2026-10-12',change_percent=2,period='D',news=[{'news_id':1,'title':'호실적','summary':'매출이 늘었다.','published_at':'2026-10-12T00:00:00Z','relation':'DIRECT','sentiment_hint':'POSITIVE','sentiment_confidence':confidence}])
    result=rule_docent(request)
    assert result['relation']=='DIRECT'
    assert ('호재로' in result['possibleReason']) is contains


def test_feedback_uses_confidence_without_praise_or_new_market_facts(monkeypatch):
    from app import config
    monkeypatch.setattr(config,'USE_REAL_LLM',False)
    request=FeedbackRequest(news_id=1,user_choice='UP',market_result='UP',news_title='삼성전자 분기 실적',news_summary='삼성전자의 분기 매출은 전년 같은 기간보다 늘었다.',sentiment_hint='POSITIVE',sentiment_confidence=.8)
    result=judgement_feedback(request)
    assert '긍정적' in result.reasons[0].detail
    assert '단정할 수는 없어요' in result.reasons[0].detail
    assert '정확한 판단' not in result.headline
    low=judgement_feedback(request.model_copy(update={'sentiment_confidence':.59}))
    assert '판단하기 어려워요' in low.reasons[0].detail


def test_confusion_matrix_is_actual_rows_predicted_columns():
    result=classification_metrics(['POSITIVE','NEGATIVE','NEUTRAL'],['POSITIVE','NEUTRAL','NEUTRAL'])
    assert result['accuracy']==pytest.approx(2/3)
    assert result['confusion_matrix']==[[0,1,0],[0,1,0],[0,0,1]]
