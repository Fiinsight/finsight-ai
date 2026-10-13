import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from app import config
from app.services import llm_client
from scripts.check_level_quality import report
from scripts.rewrite_news_batch import main

SOURCE='수출액은 261억달러로 증가했다. 지난해보다 102% 늘었다. 물류 비용은 5.5% 올랐다. 앞으로 비용 부담이 우려된다.'
VALID={'beginner':'수출액이 261억달러로 늘었어요. 수출(해외에 상품을 파는 일)이 증가했어요. 지난해보다 102% 늘었어요. 물류 비용도 올랐어요. 비용 부담을 함께 확인해야 해요.', 'normal':'[사실] 수출액은 261억달러다. 지난해보다 102% 증가했다. [전망] 비용 부담이 우려된다.', 'analyst':{'evidence':'수출액이 증가했다.','figures':'수출액은 261억달러로 지난해보다 102% 늘었다.','risk':'물류 비용 부담의 지속 여부를 확인해야 한다.'}}


@pytest.fixture
def local(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'LLM_PROVIDER','ollama')
    monkeypatch.setattr(config,'REWRITE_WITH_LLM',True)
    monkeypatch.setattr(config,'USE_REAL_LLM',False)
    monkeypatch.setattr(config,'OLLAMA_MODEL','fixture')
    monkeypatch.setattr(config,'OLLAMA_BASE_URL','http://localhost:11434')
    monkeypatch.setattr(config,'REWRITE_LEDGER_PATH',str(tmp_path/'budget.db'))
    monkeypatch.setattr(llm_client,'_real_llm_calls',0)
    monkeypatch.setattr(config,'MAX_REAL_LLM_CALLS_PER_PROCESS',20)
    monkeypatch.setattr(config,'MAX_DAILY_REWRITE_CALLS',50)
    connection=MagicMock()
    connection.getresponse.return_value.status=200
    connection.getresponse.return_value.read.return_value=json.dumps({'done':True,'response':json.dumps(VALID,ensure_ascii=False)}).encode()
    factory=MagicMock(return_value=connection)
    monkeypatch.setattr('http.client.HTTPConnection',factory)
    return factory,connection


def test_all_levels_one_http_call_and_cached_article_never_regenerates(local):
    factory,connection=local
    result=llm_client.rewrite_news('수출 증가',SOURCE,'article-1',local_batch=True)
    assert result['mode']=='REWRITTEN'
    assert llm_client.rewrite_news('수출 증가',SOURCE,'article-1',local_batch=True)==result
    assert llm_client.rewrite_news('수출 변경',SOURCE.replace('261','262'),'article-1',local_batch=True)['mode']=='EXCERPT'
    connection.request.assert_called_once()
    factory.assert_called_once_with('localhost',11434,timeout=120)
    payload=json.loads(connection.request.call_args.kwargs['body'])
    assert payload['stream'] is False and payload['format']=='json'
    assert payload['model']=='fixture' and 'beginner' in payload['prompt']


def test_json_parse_retry_once_but_not_number_validation(local):
    _,connection=local
    connection.getresponse.return_value.read.side_effect=[json.dumps({'done':True,'response':'not json'}).encode(),json.dumps({'done':True,'response':json.dumps(VALID)}).encode()]
    assert llm_client.rewrite_news('수출 증가',SOURCE,'retry',local_batch=True)['mode']=='REWRITTEN'
    assert connection.request.call_count==2


@pytest.mark.parametrize('failure',['number','sign','timeout','bad_json','redirect','advice'])
def test_failures_stay_excerpt_without_external_fallback(local,failure):
    _,connection=local
    data=json.loads(json.dumps(VALID))
    if failure=='number':data['beginner']=data['beginner'].replace('261','999')
    if failure=='sign':data['beginner']=data['beginner'].replace('102%','-102%')
    if failure=='advice':data['normal']='수출액은 261억달러다. 지난해보다 102% 증가했다. 매수하세요.'
    connection.getresponse.return_value.read.return_value=json.dumps({'done':True,'response':json.dumps(data)}).encode()
    if failure=='timeout':connection.request.side_effect=TimeoutError()
    if failure=='bad_json':connection.getresponse.return_value.read.return_value=b'not json'
    if failure=='redirect':connection.getresponse.return_value.status=302
    assert llm_client.rewrite_news('수출 증가',SOURCE,'failed',local_batch=True)['mode']=='EXCERPT'
    assert llm_client.rewrite_news('수출 증가',SOURCE,'failed',local_batch=True)['mode']=='EXCERPT'
    assert connection.request.call_count==(2 if failure=='bad_json' else 1)


def test_daily_and_process_caps_remain_active(local,monkeypatch):
    _,connection=local
    monkeypatch.setattr(config,'MAX_DAILY_REWRITE_CALLS',1)
    assert llm_client.rewrite_news('수출 증가',SOURCE,'one',local_batch=True)['mode']=='REWRITTEN'
    assert llm_client.rewrite_news('다른 기사',SOURCE,'two',local_batch=True)['mode']=='EXCERPT'
    connection.request.assert_called_once()
    monkeypatch.setattr(config,'MAX_DAILY_REWRITE_CALLS',50)
    monkeypatch.setattr(config,'MAX_REAL_LLM_CALLS_PER_PROCESS',1)
    assert llm_client.rewrite_news('또 다른 기사',SOURCE,'three',local_batch=True)['mode']=='EXCERPT'
    connection.request.assert_called_once()


def test_batch_dry_run_has_no_generation_or_writes(local,monkeypatch,capsys):
    import scripts.rewrite_news_batch as batch
    calls=[]
    @contextmanager
    def db(**kwargs):
        calls.append(kwargs)
        yield SimpleNamespace(execute=lambda *args:SimpleNamespace(fetchall=lambda:[]))
    monkeypatch.setattr(batch,'database',db)
    monkeypatch.setattr('sys.argv',['rewrite_news_batch','--since','2026-10-13T00:00:00+09:00'])
    main()
    assert calls==[{}]
    local[1].request.assert_not_called()
    assert '"apply": false' in capsys.readouterr().out


def test_human_comparison_uses_only_saved_outputs(local):
    markdown=report([{'title':'수출 | 증가','body':SOURCE,'mode':'REWRITTEN',**{key:VALID[key] if isinstance(VALID[key],str) else '분석 결과' for key in ['beginner','normal','analyst']}}]*11)
    assert '| 원문 | 발췌 | 로컬 LLM |' in markdown
    assert markdown.count('수출 &#124; 증가')==10
    assert '261억달러' in markdown and '초보자' in markdown
    local[1].request.assert_not_called()


def test_explicit_batch_applies_only_snapshot_guarded_results(local,monkeypatch,capsys):
    import scripts.rewrite_news_batch as batch
    row={'id':7,'title':'수출 증가','url':'https://fixture.test/7','raw_content':SOURCE,'rewrite_mode':'EXCERPT','rewritten_beginner':'old excerpt','rewritten_normal':'old excerpt','rewritten_analyst':'old excerpt'}
    calls=[]
    @contextmanager
    def db(**kwargs):
        calls.append(kwargs)
        if kwargs.get('readonly') is False:
            def execute(sql,parameters):
                assert 'raw_content IS NOT DISTINCT FROM' in sql and 'title IS NOT DISTINCT FROM' in sql
                assert parameters[3]=='REWRITTEN' and parameters[4]==7
                assert parameters[5]==row['title'] and parameters[6]==SOURCE
                assert parameters[-3:]==('old excerpt','old excerpt','old excerpt')
                return SimpleNamespace(rowcount=1)
            yield SimpleNamespace(execute=execute)
        else:yield SimpleNamespace(execute=lambda *args:SimpleNamespace(fetchall=lambda:[row]))
    monkeypatch.setattr(batch,'database',db)
    monkeypatch.setattr('sys.argv',['rewrite_news_batch','--since','2026-10-13T00:00:00+09:00','--apply'])
    main()
    assert calls==[{}, {'readonly':False}]
    local[1].request.assert_called_once()
    assert '"stored": 1' in capsys.readouterr().out


def test_completed_fallback_does_not_block_new_articles_and_cached_success_can_recover_db(local):
    from scripts.rewrite_news_batch import pending
    first=llm_client.rewrite_news('수출 증가',SOURCE,'https://fixture.test/one',local_batch=True)
    row={'id':1,'title':'수출 증가','url':'https://fixture.test/one','raw_content':SOURCE,'rewrite_mode':'EXCERPT','rewritten_beginner':'old','rewritten_normal':'old','rewritten_analyst':'old'}
    assert pending([row])==[row]  # The cached success can be saved after a previous DB failure.
    assert llm_client.rewrite_news(row['title'],SOURCE,row['url'],local_batch=True)==first
    local[1].request.assert_called_once()
    row.update(rewrite_mode=first['mode'],**{'rewritten_'+level:first[level] for level in ['beginner','normal','analyst']})
    fresh={**row,'id':2,'url':'https://fixture.test/two','rewrite_mode':'EXCERPT'}
    assert pending([row,fresh])==[fresh]
