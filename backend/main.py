from __future__ import annotations

from pathlib import Path

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


def create_app() -> FastAPI:
    config = load_config()
    if config.security.auth_enabled and not config.security.api_token:
        raise RuntimeError('API auth is enabled but API_AUTH_TOKEN is empty.')

    app = FastAPI(title="stocknew API", version="1.0.0")
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

    @app.on_event("startup")
    def init_database_schema():
        database = build_database(config)
        try:
            database.init_schema()
        finally:
            database.close()

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/picks")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # Catch-all for Vue SPA routing
    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_vue_spa():
        return FileResponse(VUE_INDEX)

    return app


app = create_app()
