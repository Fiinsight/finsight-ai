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
