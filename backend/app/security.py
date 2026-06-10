from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


def _is_api_path(path: str) -> bool:
    return path.startswith('/api/v1/')


def _extract_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get('x-forwarded-for')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    if request.client:
        return request.client.host
    return 'unknown'


def _extract_auth_token(request: Request) -> str:
    bearer = request.headers.get('authorization', '').strip()
    if bearer.lower().startswith('bearer '):
        return bearer[7:].strip()
    return request.headers.get('x-api-token', '').strip()


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: int


class InMemoryRateLimiter:
    def __init__(self, max_requests_per_minute: int):
        self.max_requests_per_minute = max(max_requests_per_minute, 1)
        self.window_seconds = 60.0
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str) -> RateLimitResult:
        now = time.time()
        bucket = self._buckets[key]
        while bucket and now - bucket[0] >= self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.max_requests_per_minute:
            reset_after = max(int(self.window_seconds - (now - bucket[0])), 1)
            return RateLimitResult(
                allowed=False,
                limit=self.max_requests_per_minute,
                remaining=0,
                reset_after_seconds=reset_after,
            )
        bucket.append(now)
        return RateLimitResult(
            allowed=True,
            limit=self.max_requests_per_minute,
            remaining=max(self.max_requests_per_minute - len(bucket), 0),
            reset_after_seconds=60,
        )


class ApiTokenAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_token: str):
        super().__init__(app)
        self.api_token = api_token

    async def dispatch(self, request: Request, call_next):
        if not _is_api_path(request.url.path):
            return await call_next(request)
        if request.method.upper() == 'OPTIONS':
            return await call_next(request)
        token = _extract_auth_token(request)
        if not token or token != self.api_token:
            return JSONResponse(
                status_code=401,
                content={'code': 401, 'msg': 'unauthorized'},
            )
        return await call_next(request)


class ApiRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests_per_minute: int):
        super().__init__(app)
        self.limiter = InMemoryRateLimiter(max_requests_per_minute=max_requests_per_minute)

    async def dispatch(self, request: Request, call_next):
        if not _is_api_path(request.url.path):
            return await call_next(request)
        if request.method.upper() == 'OPTIONS':
            return await call_next(request)
        client_ip = _extract_client_ip(request)
        result = self.limiter.check(client_ip)
        if not result.allowed:
            return JSONResponse(
                status_code=429,
                headers={
                    'X-RateLimit-Limit': str(result.limit),
                    'X-RateLimit-Remaining': str(result.remaining),
                    'Retry-After': str(result.reset_after_seconds),
                },
                content={'code': 429, 'msg': 'rate limit exceeded'},
            )
        response = await call_next(request)
        response.headers['X-RateLimit-Limit'] = str(result.limit)
        response.headers['X-RateLimit-Remaining'] = str(result.remaining)
        return response
