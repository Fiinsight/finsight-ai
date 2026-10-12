import unittest
from datetime import datetime
from fastapi.testclient import TestClient
from app.main import app


class LocalRetrievalTest(unittest.TestCase):
    def test_rank_identity_and_owner_boundary(self):
        client = TestClient(app)
        doc = {'id': '1', 'kind': 'news', 'title': '관계없는 최신 기사', 'body': '본문',
               'publishedAt': '2026-10-01T02:00:00Z', 'url': 'https://publisher.test/1'}
        match = {**doc, 'id': '2', 'title': '반도체 수출', 'body': '반도체 수출 증가' * 100,
                 'publishedAt': '2026-09-30T02:00:00Z', 'url': 'https://publisher.test/2'}
        request = {'query': '반도체 수출', 'kind': 'news', 'documents': [doc, match], 'topK': 3}
        result = client.post('/v1/search', json=request).json()
        self.assertEqual(result['status'], 'RULE_FALLBACK')
        self.assertEqual(result['results'][0]['id'], '2')
        self.assertEqual(result['results'][0]['url'], match['url'])
        self.assertEqual(datetime.fromisoformat(result['results'][0]['publishedAt']), datetime.fromisoformat(match['publishedAt']))
        self.assertLessEqual(len(result['results'][0]['evidence']), 600)
        request['documents'] = [{**match, 'publishedAt': None}, {**match, 'synthetic': True}]
        self.assertEqual(client.post('/v1/search', json=request).json()['results'], [])
        request.update(kind='case', documents=[{**match, 'kind': 'case', 'owner': 'other'}])
        self.assertEqual(client.post('/v1/search', json=request).status_code, 400)
        request['owner'] = 'me'
        self.assertEqual(client.post('/v1/search', json=request).json()['results'], [])
        request['documents'][0]['owner'] = 'me'
        self.assertEqual(client.post('/v1/search', json=request).json()['results'][0]['id'], '2')
        request['topK'] = 1000
        self.assertEqual(client.post('/v1/search', json=request).status_code, 422)

    def test_process_cost_flags_take_precedence_over_dotenv(self):
        import os
        import subprocess
        import sys
        result = subprocess.run([sys.executable, '-c',
            'from app import config; assert not config.USE_REAL_LLM; assert not config.USE_REAL_EMBEDDINGS'],
            env={**os.environ, 'USE_REAL_LLM': 'false', 'USE_REAL_EMBEDDINGS': 'false'}, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_company_topics_and_duplicate_headlines_beat_shared_article_format(self):
        client = TestClient(app)
        base = {'kind':'news', 'body':'환율 변화와 수주 전망', 'publishedAt':'2026-10-01T02:00:00Z'}
        docs = [{**base, 'id':'1', 'title':'현대백화점 목표가 하향', 'url':'https://publisher.test/1'},
                {**base, 'id':'2', 'title':'현대로템 페루 수주 시점 조정', 'url':'https://publisher.test/2'},
                {**base, 'id':'3', 'title':'[종합] 현대로템 페루 수주 시점 조정', 'url':'https://publisher.test/3'},
                {**base, 'id':'4', 'title':'기아 목표가 하향', 'url':'https://publisher.test/4'}]
        response = client.post('/v1/search', json={'query':'현대로템 목표가 하향 환율 영향', 'kind':'news', 'documents':docs}).json()
        self.assertEqual([row['id'] for row in response['results']], ['2'])

    def test_news_on_both_sides_of_reference_date_and_duplicate_articles_excluded(self):
        client = TestClient(app)
        base = {'kind':'news', 'body':'반도체 수출 증가', 'title':'반도체 수출 증가', 'url':'https://publisher.test/a'}
        docs = [{**base, 'id':'1', 'title':'반도체 수출 가격 변화', 'publishedAt':'2026-09-01T00:00:00Z'},
                {**base, 'id':'2', 'title':'HBM 수출 기업의 매출 전망', 'url':'https://publisher.test/b','publishedAt':'2026-10-02T00:00:00Z'},
                {**base, 'id':'3', 'title':'반도체 수출 가격 변화', 'publishedAt':'2026-10-01T00:00:00Z'}]
        response = client.post('/v1/search', json={'query':'반도체 수출 증가','kind':'news','documents':docs,'startAt':'2026-08-01T00:00:00Z','endAt':'2026-10-03T00:00:00Z'}).json()
        self.assertEqual({row['id'] for row in response['results']}, {'1','2'})
