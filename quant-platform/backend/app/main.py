"""FastAPI application entry point: `uvicorn app.main:app --reload`."""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import analytics_routes, auth_routes, data_routes, portfolio_routes, research_routes
from .config import get_settings
from .db import init_db

logging.basicConfig(level=logging.INFO, format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)s}')
log = logging.getLogger("api")


def create_app() -> FastAPI:
    s = get_settings()

    @asynccontextmanager
    async def lifespan(_app):
        init_db()
        yield

    app = FastAPI(title="Quant Research & Portfolio Intelligence", version=__version__, lifespan=lifespan,
                  description="Research, risk and portfolio tracking. No automated trade execution.")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        rid = uuid.uuid4().hex[:12]
        t0 = time.perf_counter()
        response = await call_next(request)
        log.info('{"rid":"%s","method":"%s","path":"%s","status":%d,"ms":%.1f}', rid, request.method, request.url.path,
                 response.status_code, (time.perf_counter() - t0) * 1000)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__}

    for r in (auth_routes, data_routes, analytics_routes, portfolio_routes, research_routes):
        app.include_router(r.router)
    return app


app = create_app()
