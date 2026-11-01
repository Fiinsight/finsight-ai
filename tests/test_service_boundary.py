import asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.security import ServiceBoundary
from app.main import app as real_app


def make_app(**settings):
    app = FastAPI()
    app.add_middleware(ServiceBoundary, token='test-internal-token', **settings)
    @app.post('/ai/work')
    async def work():
        return {'ok': True}
    @app.get('/health')
    async def health():
        return {'status': 'ok'}
    return app


HEADERS = {'Authorization': 'Bearer test-internal-token'}


def test_authentication_covers_ai_retrieval_and_diagnostics():
    from unittest.mock import patch
    from app import config
    with patch.object(config, 'AI_INTERNAL_TOKEN', 'test-internal-token'):
        # A fresh middleware stack reads the configured deployment token.
        from app.main import diagnostics
        secured = make_app()
        secured.get('/internal/status')(diagnostics)
        with TestClient(secured) as client:
            for path in ['/ai/work', '/v1/search', '/internal/status']:
                assert client.post(path).status_code == 401
                assert client.post(path, headers={'Authorization': 'Bearer wrong'}).status_code == 401
            assert client.post('/ai/work', headers=HEADERS).status_code == 200
            assert client.get('/health').json() == {'status': 'ok'}
    assert TestClient(real_app).get('/health').json() == {'status': 'ok'}


def test_actual_body_limit_without_content_length_and_request_limit():
    with TestClient(make_app(body_limit=8, request_limit=2)) as client:
        assert client.post('/ai/work', content=iter([b'12345', b'6789']), headers=HEADERS).status_code == 413
        assert client.post('/ai/work', headers=HEADERS).status_code == 200
        assert client.post('/ai/work', headers=HEADERS).status_code == 429


def test_timeout_releases_concurrency_slot():
    app = make_app(timeout=.01, concurrency=1)
    @app.post('/ai/slow')
    async def slow():
        await asyncio.sleep(.1)
        return {'ok': True}
    with TestClient(app) as client:
        assert client.post('/ai/slow', headers=HEADERS).status_code == 504
        assert client.post('/ai/work', headers=HEADERS).status_code == 200


def test_concurrent_requests_are_bounded():
    from concurrent.futures import ThreadPoolExecutor
    import threading
    app = make_app(concurrency=1)
    entered, release = threading.Event(), threading.Event()
    @app.post('/ai/held')
    async def held():
        entered.set()
        while not release.is_set():
            await asyncio.sleep(.001)
        return {'ok': True}
    with TestClient(app) as client, ThreadPoolExecutor() as pool:
        first = pool.submit(client.post, '/ai/held', headers=HEADERS)
        try:
            assert entered.wait(2)
            assert client.post('/ai/work', headers=HEADERS).status_code == 429
        finally:
            release.set()
        assert first.result().status_code == 200


def test_empty_ai_token_does_not_require_matching_backend_token():
    # Empty token is explicitly loopback/private-network mode, not a failing auth setup.
    app = FastAPI()
    app.add_middleware(ServiceBoundary, token='')
    @app.get('/ai/probe')
    async def probe():
        return {'mode': 'RULE'}
    with TestClient(app) as client:
        assert client.get('/ai/probe').status_code == 200
        assert client.get('/ai/probe', headers={'Authorization': 'Bearer backend-only-token'}).status_code == 200
