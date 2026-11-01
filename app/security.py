"""Bounded service boundary; local deployments must remain bound to loopback."""
import asyncio
import hmac
import time
from starlette.responses import JSONResponse
from app import config


class ServiceBoundary:
    def __init__(self, app, *, token=None, body_limit=None, request_limit=None, concurrency=None, timeout=None):
        self.app = app
        self.token = config.AI_INTERNAL_TOKEN if token is None else token
        self.body_limit = body_limit or config.AI_MAX_BODY_BYTES
        self.request_limit = request_limit or config.AI_REQUESTS_PER_MINUTE
        self.concurrency = concurrency or config.AI_MAX_CONCURRENT_REQUESTS
        self.timeout = timeout or config.AI_REQUEST_TIMEOUT_SECONDS
        self.window = time.monotonic()
        self.requests = 0
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] == '/health':
            return await self.app(scope, receive, send)
        async def reject(status, message):
            await JSONResponse({'detail': message}, status_code=status)(scope, receive, send)
        headers = dict(scope.get('headers', []))
        expected = ('Bearer ' + self.token).encode()
        if self.token and not hmac.compare_digest(headers.get(b'authorization', b''), expected):
            return await reject(401, 'Internal authentication required')
        if time.monotonic() - self.window >= 60:
            self.window, self.requests = time.monotonic(), 0
        if self.requests >= self.request_limit or self.active >= self.concurrency:
            return await reject(429, 'Service request limit reached')
        self.requests += 1
        self.active += 1
        started = False
        async def tracked_send(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
            await send(message)
        try:
            async with asyncio.timeout(self.timeout):
                chunks, size = [], 0
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        return
                    chunk = message.get('body', b'')
                    size += len(chunk)
                    if size > self.body_limit:
                        return await reject(413, 'Request body too large')
                    chunks.append(chunk)
                    if not message.get('more_body', False):
                        break
                async def replay():
                    return {'type': 'http.request', 'body': b''.join(chunks), 'more_body': False}
                await self.app(scope, replay, tracked_send)
        except TimeoutError:
            if not started:
                await reject(504, 'Service request timed out')
        finally:
            self.active -= 1
