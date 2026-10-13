import json
import pytest
from types import SimpleNamespace
from app import config
from app.services.news_retrieval import search_news, recommend_news


@pytest.fixture
def index(tmp_path, monkeypatch):
    np=pytest.importorskip('numpy')
    from ml.retrieval import save_index
    rows=[{'news_id':i,'title':title,'body':title+' 본문','url':f'https://fixture.test/{i}'} for i,title in enumerate(['금리 인하','환율 수출','은행 조달 변화','원화와 수출 기업','국채 투자','은행 조달 변화'],1)]
    save_index(rows,[[1,0],[0,1],[1,0],[0,1],[.7,.7],[1,0]],tmp_path,'fixture-local')
    monkeypatch.setattr(config,'ML_NEWS_INDEX_PATH',str(tmp_path))
    return tmp_path


def test_weighted_interest_excludes_read_and_duplicate_events_and_has_real_reason(index):
    result=recommend_news([{'news_id':1,'weight':.6},{'news_id':2,'weight':1.0}],[1,2,3,4,5,6],[1,2])
    assert result['basis']=='LOCAL_SENTENCE_TRANSFORMER'
    assert result['results'][0]['news_id']==5
    assert len(result['results'])==3
    assert {row['news_id'] for row in result['results']} in [{3,4,5},{4,5,6}]
    assert next(row for row in result['results'] if row['news_id']==4)['reason_news_id']==2
    assert all(row['reason_news_id'] in {1,2} for row in result['results'])
    assert recommend_news([], [3],[])['results']==[]


def test_query_search_and_news_a_use_vectors_but_keep_candidate_identity(index,monkeypatch):
    import ml.retrieval as retrieval
    monkeypatch.setattr(retrieval,'local_model',lambda name:SimpleNamespace(encode=lambda *args,**kwargs:[[0,1]]))
    found=search_news('수출과 원화',3,['3','4'])
    assert found['results'][0]['news_id']==4
    from app.routers.local_retrieval import SearchRequest,search
    request=SearchRequest(query='수출과 원화',kind='news',documents=[{'id':str(i),'kind':'news','title':title,'body':'기사 본문','publishedAt':'2026-10-12T00:00:00Z'} for i,title in [(3,'은행 조달 변화'),(4,'원화와 수출 기업')]])
    result=search(request)
    assert result['basis']=='LOCAL_SENTENCE_TRANSFORMER'
    assert result['results'][0]['id']=='4'
    assert result['results'][0]['title']=='원화와 수출 기업'
    assert result['qualityValidated'] is False


def test_optional_dependency_and_corrupt_index_fall_back_without_external_calls(index,monkeypatch):
    import ml.retrieval as retrieval
    retrieval.local_model.cache_clear()
    monkeypatch.setitem(__import__('sys').modules,'sentence_transformers',None)
    assert search_news('반도체')['basis']=='INDEX_UNAVAILABLE_RULE_FALLBACK'
    (index/'index.npz').write_bytes(b'bad archive')
    assert recommend_news([{'news_id':1,'weight':1}], [3],[])['results']==[]


def test_incremental_batch_only_embeds_new_ids_and_atomically_keeps_old_vectors(tmp_path):
    np=pytest.importorskip('numpy')
    from scripts.embed_news import incremental
    from ml.retrieval import load_index
    calls=[]
    def encode(texts,**kwargs):
        calls.append(texts);return [[1,0] for _ in texts]
    encoder=SimpleNamespace(encode=encode)
    rows=[{'id':1,'title':'삼성전자 실적','raw_content':'삼성전자 분기 매출은 지난해 같은 기간보다 늘어났다고 회사는 밝혔다.'}]
    assert incremental(rows,tmp_path,'fixture',encoder)==1
    before=(tmp_path/'index.npz').read_bytes()
    assert incremental(rows,tmp_path,'fixture',encoder)==0
    assert len(calls)==1 and (tmp_path/'index.npz').read_bytes()==before
    rows.append({'id':2,'title':'환율과 수출 기업','raw_content':'원화 환율 변화가 수출 기업의 원화 매출에 영향을 줄 수 있다고 설명했다.'})
    assert incremental(rows,tmp_path,'fixture',encoder)==1
    vectors,metadata=load_index(tmp_path)
    assert len(vectors)==2 and [row['news_id'] for row in metadata['rows']]==[1,2]
    assert len(calls[-1])==1 and len(calls[-1][0])<=len(rows[-1]['title'])+501
    with pytest.raises(ValueError):incremental(rows,tmp_path,'different-model',encoder)
