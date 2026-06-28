from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api import router
from backend.app.config import load_config
from backend.app.paths import resource_path
from backend.app.runtime import build_database
from backend.app.security import ApiRateLimitMiddleware, ApiTokenAuthMiddleware

STATIC_DIR = resource_path("backend/app/static")
VUE_INDEX = STATIC_DIR / "vue" / "index.html"

OPENAPI_TAGS = [
    {"name": "stocks", "description": "选股、行情与股票详情查询。"},
    {"name": "analysis", "description": "规则或模型辅助分析。"},
    {"name": "data-health", "description": "数据完整性检查与受控回填。"},
    {"name": "jobs", "description": "数据任务、运行记录与可观测性。"},
    {"name": "settings", "description": "桌面运行配置。"},
    {"name": "watchlist", "description": "埋伏池维护。"},
    {"name": "system", "description": "进程健康状态。"},
]


def create_app() -> FastAPI:
    config = load_config()
    if config.security.auth_enabled and not config.security.api_token:
        raise RuntimeError('API auth is enabled but API_AUTH_TOKEN is empty.')

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        database = build_database(config)
        try:
            database.init_schema()
        finally:
            database.close()
        yield

    app = FastAPI(
        title="stocknew API",
        version="1.0.0",
        description="stockapp 桌面端的本地 HTTP API。稳定业务前缀为 /api/v1。",
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.security.cors_origins or [],
        allow_credentials=True,
        allow_methods=['GET', 'POST', 'PUT', 'OPTIONS'],
        allow_headers=['Authorization', 'Content-Type', 'X-API-Token'],
    )
    app.add_middleware(ApiRateLimitMiddleware, max_requests_per_minute=config.security.rate_limit_per_minute)
    if config.security.auth_enabled:
        app.add_middleware(ApiTokenAuthMiddleware, api_token=config.security.api_token)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(router)

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/picks")

    @app.get("/health", tags=["system"])
    def health():
        return {"status": "ok"}

    # Catch-all for Vue SPA routing
    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_vue_spa():
        return FileResponse(VUE_INDEX)

    return app


app = create_app()
