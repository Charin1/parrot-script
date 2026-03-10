from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Request, WebSocket, status
from fastapi.responses import JSONResponse, Response

from backend.config import settings

PUBLIC_PATHS = {"/health", "/preflight"}


def auth_enabled() -> bool:
    return bool(settings.api_token.strip())


def extract_bearer_token(authorization: str | None) -> Optional[str]:
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def token_valid(candidate: str | None) -> bool:
    expected = settings.api_token.strip()
    if not expected:
        return True
    if not candidate:
        return False
    return secrets.compare_digest(candidate, expected)


async def verify_http_request(request: Request) -> Response | None:
    if request.method == "OPTIONS":
        return None

    if not auth_enabled() or request.url.path in PUBLIC_PATHS:
        return None

    header_token = extract_bearer_token(request.headers.get("Authorization"))
    query_token = request.query_params.get("token")

    if not token_valid(header_token) and not token_valid(query_token):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Missing or invalid API token"},
        )
    return None


async def verify_websocket_request(websocket: WebSocket) -> None:
    if not auth_enabled():
        return

    header_token = extract_bearer_token(websocket.headers.get("authorization"))
    query_token = websocket.query_params.get("token")
    if token_valid(header_token) or token_valid(query_token):
        return

    await websocket.close(code=4401, reason="Unauthorized")
