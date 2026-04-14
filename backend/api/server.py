from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from backend.api.auth import auth_enabled, verify_http_request, verify_websocket_request
from backend.api.routes.meetings import router as meetings_router
from backend.api.routes.native import router as native_router
from backend.api.routes.search import router as search_router
from backend.api.routes.summaries import router as summaries_router
from backend.api.routes.transcripts import router as transcripts_router
from backend.api.websocket import manager
from backend.config import settings
from backend.core.preflight import PreflightResult, run_preflight
from backend.storage.db import init_db

logger = logging.getLogger(__name__)

_preflight_result: PreflightResult | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _preflight_result
    # Ensure backend logs are visible even with uvicorn's default config
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")
    logging.getLogger("backend").setLevel(logging.INFO)

    await init_db()
    _preflight_result = await run_preflight()
    if not _preflight_result.ok:
        logger.error(
            "Server started with preflight failures – some features may not work. "
            "Check the logs above for details."
        )
    yield


app = FastAPI(title="Parrot Script", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meetings_router)
app.include_router(transcripts_router)
app.include_router(summaries_router)
app.include_router(search_router)
app.include_router(native_router)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "auth_required": auth_enabled()}


@app.get("/preflight")
async def preflight_status() -> dict[str, Any]:
    """Return the results of the startup preflight checks."""
    if _preflight_result is None:
        return {"status": "pending", "passed": [], "warnings": [], "failures": []}
    return {
        "status": "ok" if _preflight_result.ok else "degraded",
        "passed": _preflight_result.passed,
        "warnings": _preflight_result.warnings,
        "failures": _preflight_result.failures,
    }


def apply_security_headers(response: Response) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    auth_response = await verify_http_request(request)
    if auth_response is not None:
        return apply_security_headers(auth_response)

    response = await call_next(request)
    return apply_security_headers(response)


@app.websocket("/ws/meetings/{meeting_id}")
async def websocket_endpoint(websocket: WebSocket, meeting_id: str):
    authorized = await verify_websocket_request(websocket)
    if not authorized:
        return
    await manager.connect(websocket, meeting_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket, meeting_id)
